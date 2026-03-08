import streamlit as st
import streamlit.components.v1 as components
import json
import networkx as nx
from networkx.readwrite import json_graph
from pyvis.network import Network

# --- Predefined Professional Palettes ---
NODE_PALETTE = ["#FF4B4B", "#1C83E1", "#00C07F", "#7D44CF", "#FFA421", "#E74C3C", "#3498DB", "#2ECC71", "#9B59B6"]
EDGE_PALETTE = ["#8E44AD", "#2980B9", "#27AE60", "#F39C12", "#D35400", "#C0392B", "#16A085", "#34495E"]

# --- Page Setup ---
st.set_page_config(layout="wide", page_title="Layer10 Memory Explorer")
st.title("Layer10 Knowledge Graph Explorer")
st.markdown("Explore grounded organizational memory extracted from the Enron Corpus.")

# --- Data Loading (Fast JSON Load) ---
@st.cache_resource
def get_graph():
    """Loads the serialized memory graph directly from disk."""
    try:
        with open("memory_graph_output.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return json_graph.node_link_graph(data)
    except FileNotFoundError:
        st.error("No graph data found. Please run 'python graph/build_graph.py' first.")
        return nx.MultiDiGraph()

with st.spinner("Loading Memory Graph from Database..."):
    G = get_graph()

# --- Sidebar: Controls & Legend ---
st.sidebar.header("Controls & Filters")
if st.sidebar.button("🔄 Refresh Data from Database"):
    st.cache_resource.clear()
    st.rerun()

# 1. Filter by Entity Type
all_node_types = list(set([data.get('entity_type', 'Unknown') for _, data in G.nodes(data=True)]))
selected_types = st.sidebar.multiselect("Filter by Entity Types", all_node_types, default=all_node_types)

# 2. Dynamic Color Allocators
node_color_map = {}
edge_color_map = {}

def get_node_color(ent_type):
    if ent_type not in node_color_map:
        node_color_map[ent_type] = NODE_PALETTE[len(node_color_map) % len(NODE_PALETTE)]
    return node_color_map[ent_type]

def get_edge_color(relation):
    if relation not in edge_color_map:
        edge_color_map[relation] = EDGE_PALETTE[len(edge_color_map) % len(EDGE_PALETTE)]
    return edge_color_map[relation]

# --- Main Interface Layout ---
col_graph, col_evidence = st.columns([2, 1])

with col_graph:
    st.subheader("Interactive Graph View")
    
    if G.number_of_nodes() > 0:
        net = Network(height="700px", width="100%", bgcolor="#ffffff", font_color="#333333", directed=True)
        net.force_atlas_2based() 

        # Add Nodes & Assign Colors
        for node, data in G.nodes(data=True):
            ent_type = data.get('entity_type', 'Unknown')
            if ent_type in selected_types:
                label = data.get('name', str(node))
                color = get_node_color(ent_type)
                net.add_node(node, label=label, title=f"Type: {ent_type}", color=color)

        valid_node_ids = net.get_nodes()
        
        # Add Edges & Assign Colors
        for u, v, data in G.edges(data=True):
            if u in valid_node_ids and v in valid_node_ids:
                relation = data.get('relation', 'UNKNOWN')
                edge_color = get_edge_color(relation)
                net.add_edge(u, v, label=relation, color=edge_color, width=2)

        # Render Graph
        path = "temp_graph.html"
        net.write_html(path)
        with open(path, 'r', encoding='utf-8') as f:
            components.html(f.read(), height=750)
    else:
        st.warning("Graph is empty. Check your data pipeline.")

# --- Sidebar: Render The Dynamic Legend ---
st.sidebar.markdown("---")
st.sidebar.subheader("Graph Type")

st.sidebar.markdown("**Entity Types (Nodes):**")
for ent_type, color in node_color_map.items():
    if ent_type in selected_types: # Only show in legend if currently filtered in
        st.sidebar.markdown(f"<span style='color:{color}; font-size:18px;'>⬤</span> {ent_type}", unsafe_allow_html=True)

st.sidebar.markdown("<br>**Relationships (Edges):**", unsafe_allow_html=True)
for rel, color in edge_color_map.items():
    st.sidebar.markdown(f"<span style='color:{color}; font-size:18px;'>▬</span> {rel}", unsafe_allow_html=True)


# --- Sidebar: Alias Inspector ---
st.sidebar.markdown("---")
st.sidebar.subheader("👯 Alias Inspector")
nodes_with_aliases = [n for n, d in G.nodes(data=True) if d.get('aliases')]
if nodes_with_aliases:
    inspect_node = st.sidebar.selectbox("Inspect Merged Entities:", ["Select Entity..."] + nodes_with_aliases)
    if inspect_node != "Select Entity...":
        data = G.nodes[inspect_node]
        st.sidebar.success(f"**Canonical ID:** {inspect_node}")
        st.sidebar.write(f"**Aliases Merged:** {', '.join(data.get('aliases', []))}")
else:
    st.sidebar.info("No merged aliases found.")


# --- Right Panel: Evidence Inspector ---
with col_evidence:
    st.subheader("Evidence Panel")
    st.caption("Select a relationship to view supporting grounding.")

    if G.number_of_edges() > 0:
        claims_list = []
        edge_map = {}
        for u, v, data in G.edges(data=True):
            claim_str = f"{u} → {data.get('relation', 'UNKNOWN')} → {v}"
            claims_list.append(claim_str)
            edge_map[claim_str] = data
        
        claims_list.sort()
        selected_claim = st.selectbox("Select a Claim to verify:", ["Choose a claim..."] + claims_list)

        if selected_claim != "Choose a claim...":
            actual_data = edge_map[selected_claim]
            st.markdown(f"**Relation Status:** `{actual_data.get('status', 'active')}`")
            st.write("---")
            
            evidence_list = actual_data.get('evidence', [])
            st.write(f"**Total Supporting Evidence:** {len(evidence_list)}")
            
            for i, ev in enumerate(evidence_list):
                source_id = ev.get('source_id', 'Unknown')
                timestamp = ev.get('timestamp', 'Unknown')
                start_off = ev.get('start_offset', -1)
                end_off = ev.get('end_offset', -1)
                excerpt = ev.get('excerpt', 'No excerpt provided.')

                with st.expander(f"Evidence #{i+1} (Source: {source_id})"):
                    st.warning(f"**Grounding Metadata**")
                    st.write(f"**Date:** {timestamp}")
                    st.write(f"**Offsets:** {start_off} to {end_off}")
                    st.info(f"**Excerpt:**\n\n> {excerpt}")