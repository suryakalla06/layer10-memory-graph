import sys
import os

# 1. Clean Pathing: Ensure Python can find your 'graph' and 'extraction' folders
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from graph.build_graph import build_memory_graph
from extraction.parse_emails import load_and_parse_emails

class RetrievalEngine:
    def __init__(self, memory_graph):
        self.mgr = memory_graph
        self.G = memory_graph.G

    def search(self, query: str, top_k: int = 5):
        """
        Maps a question/keyword to candidate entities and returns a ranked context pack.
        """
        query = query.lower()
        matched_entities = []
        
        # 1. Map query to entities using keyword matching 
        for node, data in self.G.nodes(data=True):
            name = str(data.get('name', '')).lower()
            aliases = [str(a).lower() for a in data.get('aliases', [])]
            # Safety enhancement: Also check if the query matches the node ID directly!
            if query in name or any(query in a for a in aliases) or query in str(node).lower():
                matched_entities.append(node)
                
        if not matched_entities:
            return f"No entities found matching '{query}'."

        # 2. Extract Claims & Evidence connected to these entities
        context_pack = []
        seen_evidence_signatures = set() # <-- 2. The Senior Deduplication Check!

        for entity in matched_entities:
            # Get outgoing and incoming edges for the matched entity
            edges = list(self.G.out_edges(entity, data=True)) + list(self.G.in_edges(entity, data=True))
            
            for u, v, claim_data in edges:
                relation = claim_data.get('relation', 'UNKNOWN')
                evidence_list = claim_data.get('evidence', [])
                
                for ev in evidence_list:
                    # Create a unique mathematical signature for this exact fact
                    sig = f"{u}-{relation}-{v}-{ev.source_id}-{ev.start_offset}"
                    
                    if sig not in seen_evidence_signatures:
                        seen_evidence_signatures.add(sig)
                        context_pack.append({
                            "subject": u,
                            "relation": relation,
                            "object": v,
                            "evidence": ev
                        })

        # 3. Rank evidence: Sorting by Recency (newest first) to prune and prevent exploding context 
        context_pack.sort(
            key=lambda x: x['evidence'].timestamp if x['evidence'].timestamp else datetime.min, 
            reverse=True
        )
        context_pack = context_pack[:top_k]

        # 4. Format Citations and Context Pack to ensure grounding 
        output = f"--- CONTEXT PACK FOR: '{query}' ---\n"
        output += f"Entities Matched: {len(matched_entities)}\n\n"
        
        if not context_pack:
            return output + "No relational evidence found for these entities."

        for i, item in enumerate(context_pack, 1):
            ev = item['evidence']
            output += f"[{i}] {item['subject']} [{item['relation']}] {item['object']}\n"
            output += f"    Citation: Source ID '{ev.source_id}' (Offsets: {ev.start_offset} to {ev.end_offset})\n"
            output += f"    Excerpt: \"{ev.excerpt}\"\n"
            output += f"    Date: {ev.timestamp}\n\n"
            
        return output

if __name__ == "__main__":
    print("Initializing Retrieval Engine and building memory graph...")
    
    # We load a smaller subset if you just want to test it quickly without waiting 40 seconds
    emails = load_and_parse_emails("data/emails_subset_1000.csv")
    mgr = build_memory_graph(emails)
    
    engine = RetrievalEngine(mgr)
    
    print("\n" + "="*60)
    print("TEST 1: Querying LLM Semantic Data")
    print("="*60)
    # Testing for the mock data we injected earlier to prove it works!
    print(engine.search("western_desk"))  
    
    print("="*60)
    print("TEST 2: Querying Header Data")
    print("="*60)
    print(engine.search("phillip.allen"))