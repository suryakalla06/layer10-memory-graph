import json
import os

def generate_packs():
    json_path = "memory_graph_output.json"
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {json_path} not found. Please run 'python graph/build_graph.py' first.")
        return

    # 1. The NetworkX Compatibility Fix: Look for "edges" first, fallback to "links"
    claims = data.get("edges", data.get("links", []))
    
    if not claims:
        print("⚠️ No claims found in the graph JSON!")
        return

    output_path = "example_context_packs.txt"
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("LAYER10 RETRIEVED CONTEXT PACKS\n")
        out.write("===============================\n\n")
        
        # --- PACK 1: Deterministic Headers ---
        out.write("Question 1: Who did Phillip Allen send emails to recently?\n")
        out.write("Retrieved Context:\n")
        
        count = 0
        for c in claims:
            # 2. Use NetworkX's standard "source" and "target" keys
            source_node = c.get("source", "")
            target_node = c.get("target", "")
            relation = c.get("relation", "")
            
            # Use 'in' to catch aliases like "phillip_allen" or "phillip.allen@enron.com"
            if "phillip.allen" in source_node.lower() and relation == "SENT_EMAIL_TO":
                out.write(f"- Entity Linked: {target_node}\n")
                
                evidence_list = c.get("evidence", [])
                if evidence_list:
                    ev = evidence_list[0]
                    # Safely extract dictionary keys
                    source_id = ev.get('source_id', 'Unknown')
                    excerpt = ev.get('excerpt', 'No excerpt')
                    out.write(f"  Grounding: Source {source_id} | Excerpt: '{excerpt}'\n")
                
                count += 1
                if count >= 5: # Show up to 5 examples instead of 3
                    break
        
        if count == 0:
            out.write("- No emails found for Phillip Allen in this dataset.\n")
                
        # --- PACK 2: LLM Semantic Claims ---
        out.write("\nQuestion 2: What semantic relationships were extracted by the LLM?\n")
        out.write("Retrieved Context:\n")
        
        semantic_count = 0
        for c in claims:
            source_node = c.get("source", "")
            target_node = c.get("target", "")
            relation = c.get("relation", "")
            
            # Find all claims that are NOT basic header emails
            if relation and relation != "SENT_EMAIL_TO":
                out.write(f"- Semantic Claim: {source_node} -> {relation} -> {target_node}\n")
                
                evidence_list = c.get("evidence", [])
                if evidence_list:
                    # Loop through ALL evidence for this claim to show deduplication
                    for idx, ev in enumerate(evidence_list):
                        source_id = ev.get('source_id', 'Unknown')
                        excerpt = ev.get('excerpt', 'No excerpt')
                        offsets = f"[{ev.get('start_offset')}:{ev.get('end_offset')}]"
                        out.write(f"  Grounding {idx+1}: Source {source_id} {offsets} | Excerpt: '{excerpt}'\n")
                semantic_count += 1
        
        if semantic_count == 0:
            out.write("- No semantic claims found. Did the LLM run successfully?\n")

    print(f"✅ Created {output_path} successfully!")

if __name__ == "__main__":
    generate_packs()