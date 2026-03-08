import sys
import os
# 1. Clean Pathing: Add parent directory to path AT THE TOP
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
import time
import json
from typing import Dict, List
from datetime import datetime
from networkx.readwrite import json_graph

from schema import Entity, Claim, Evidence, EmailArtifact
from extraction.parse_emails import load_and_parse_emails
from extraction.normalize import normalize_email_artifact
from extraction.quality import passes_quality_gate
from extraction.llm_extractor import extract_knowledge_from_email 
from main import MemoryGraph 


def get_domain(email: str) -> str:
    """Extract domain from email safely."""
    if "@" in email:
        return email.split("@")[-1]
    return ""

def generate_header_claim(sender: str, recipient: str, email: EmailArtifact) -> Claim:
    """Creates a basic communication claim from email headers."""
    evidence = Evidence(
        source_id=email.message_id,
        excerpt=f"Subject: {email.subject}" if email.subject else "No Subject",
        start_offset=-1, 
        end_offset=-1,
        timestamp=email.date or datetime.now()
    )

    # 2. Removed redundant status/version (Pydantic handles defaults automatically)
    return Claim(
        claim_id=str(uuid.uuid4()),
        subject_id=sender,
        relation="SENT_EMAIL_TO",
        object_id=recipient,
        evidence=[evidence],
        valid_from=email.date or datetime.now()
    )

def build_memory_graph(emails: List[EmailArtifact]) -> MemoryGraph:
    """
    Extract entities and claims from parsed emails and build the graph.
    """
    mgr = MemoryGraph()
    processed_msg_ids = set() 

    for index, email in enumerate(emails):
        # 1. Artifact Deduplication
        if email.message_id in processed_msg_ids:
            continue
        processed_msg_ids.add(email.message_id)

        # 2. Normalization
        email = normalize_email_artifact(email)
        sender = email.sender
        if not sender: continue

        # 3. Header Extraction (Fast - do for all emails)
        mgr.add_or_update_entity(Entity(
            entity_id=sender, entity_type="Person", name=sender, 
            metadata={"domain": get_domain(sender)}
        ))

        for recipient in email.recipients:
            if not recipient: continue
            mgr.add_or_update_entity(Entity(
                entity_id=recipient, entity_type="Person", name=recipient, 
                metadata={"domain": get_domain(recipient)}
            ))
            
            header_claim = generate_header_claim(sender, recipient, email)
            mgr.add_claim(header_claim)

        # 4. LLM Semantic Extraction (Slow - limit to first 10 for demonstration)
        LIMIT = 10
        if index < LIMIT:
            print(f"Running LLM Extraction on email {index + 1}/10...")
            llm_data = extract_knowledge_from_email(email)
            
            # Add LLM Entities
            for ent in llm_data["entities"]:
                mgr.add_or_update_entity(ent)
                
            # Add LLM Claims (3. Removed redundant quality gate check here!)
            # Add LLM Claims with a Safety Net for Orphan Nodes
            for claim in llm_data["claims"]:
                # If the LLM forgot to define the subject, auto-create a basic one
                if not mgr.G.has_node(claim.subject_id):
                    mgr.add_or_update_entity(Entity(
                        entity_id=claim.subject_id, entity_type="Inferred", name=claim.subject_id
                    ))
                # If the LLM forgot to define the object, auto-create a basic one
                if not mgr.G.has_node(claim.object_id):
                    mgr.add_or_update_entity(Entity(
                        entity_id=claim.object_id, entity_type="Inferred", name=claim.object_id
                    ))
                
                mgr.add_claim(claim)
                    
            # Prevent hitting free-tier rate limits
            time.sleep(4) 

    return mgr


if __name__ == "__main__":
    emails = load_and_parse_emails("data/emails_subset_1000.csv")

    print(f"Loaded {len(emails)} emails. Building Graph Engine...\n")
    mgr = build_memory_graph(emails)
    graph = mgr.G

    print("\nGraph construction complete!")
    print(f"Nodes: {graph.number_of_nodes()}")
    print(f"Edges: {graph.number_of_edges()}")

    print("\nPreparing graph for serialization...")
    
    # Convert Pydantic Evidence objects to standard dictionaries so NetworkX can export them
    for u, v, d in mgr.G.edges(data=True):
        if 'evidence' in d:
            d['evidence'] = [
                ev.model_dump() if hasattr(ev, 'model_dump') else ev.dict() 
                for ev in d['evidence']
            ]

    # Convert NetworkX graph to a JSON-compatible format for the evaluator
    data = json_graph.node_link_data(mgr.G)
    with open("memory_graph_output.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, default=str)

    print("Graph serialized to memory_graph_output.json")