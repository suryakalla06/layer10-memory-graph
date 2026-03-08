import networkx as nx
from datetime import datetime
from schema import Entity, Claim, Evidence

class MemoryGraph:
    def __init__(self):
        self.G = nx.MultiDiGraph() # MultiDiGraph allows multiple evidence-edges between nodes [cite: 58]
        self.entity_lookup = {}    # Maps aliases to primary entity_id 

    def add_or_update_entity(self, entity: Entity):
        """Handles Entity Canonicalization."""
        # If an alias already exists, we map to the existing ID
        for alias in entity.aliases + [entity.name]:
            if alias in self.entity_lookup:
                return self.entity_lookup[alias]
        
        # New entity registration
        self.G.add_node(entity.entity_id, **entity.model_dump())
        self.entity_lookup[entity.name] = entity.entity_id
        for alias in entity.aliases:
            self.entity_lookup[alias] = entity.entity_id
        return entity.entity_id

    def add_claim(self, claim: Claim):
        """
        Modified to support Claim Dedup: 
        If a relation between nodes exists, append evidence.
        """
        u, v = claim.subject_id, claim.object_id
        
        # Check if an edge with this relation already exists
        if self.G.has_edge(u, v):
            # Iterate through ALL edges between u and v to find the matching relation
            edges_dict = self.G.get_edge_data(u, v)
            for edge_key, edge_data in edges_dict.items():
                if edge_data['relation'] == claim.relation:
                    # Merge repeated statement: append new evidence to existing edge 
                    edge_data['evidence'].extend(claim.evidence)
                    return

        # Otherwise, add new edge dynamically using the FULL schema!
        # model_dump() safely unpacks every field (version, claim_id, valid_until, etc.)
        edge_attrs = claim.model_dump()
        
        # Keep evidence as Pydantic objects inside the graph for easier merging later
        edge_attrs['evidence'] = claim.evidence 
        
        self.G.add_edge(u, v, **edge_attrs)

# --- Example Usage below to test graph ---


# Hide this behind the main guard so it doesn't run during imports!
if __name__ == "__main__":
    mgr = MemoryGraph()

    # 1. Create Entities with Aliases (Canonicalization) 
    person = Entity(
        entity_id="user_01", 
        entity_type="Person", 
        name="Surya", 
        aliases=["S. Kumar", "surya@enron.com"]
    )
    mgr.add_or_update_entity(person)

    # 2. Add a Grounded Claim 
    evidence = Evidence(
        source_id="msg_99", 
        excerpt="Surya is now lead on Issue 101", 
        start_offset=10, 
        end_offset=40, 
        timestamp=datetime.now()
    )

    claim = Claim(
        claim_id="c_01",
        subject_id="user_01",
        relation="LEAD_ON",
        object_id="Issue_101",
        evidence=[evidence],
        valid_from=datetime.now()
    )

    mgr.add_claim(claim)

    print(f"Nodes in graph: {mgr.G.nodes(data=True)}")
    print(f"Edges (Claims) with evidence: {mgr.G.edges(data=True)}")