# Layer10 Memory Graph
> **Turning scattered organizational knowledge into grounded, long-term memory.**

This project implements a structured extraction and deduplication pipeline for the Enron Email Corpus, transforming unstructured communication into a **Grounded Knowledge Graph**.

---

## Data & Reproducibility
To ensure this project is "clonable and runnable" immediately, I have included a pre-processed subset of the data.

**Included Subset**: `data/emails_subset_1000.csv` (1,000 rows from the Enron corpus)[cite: 34].

### Running with the Full Dataset:
1. **Download**: Obtain `emails.csv` (~1.3GB) from the [Kaggle Enron Dataset](https://www.kaggle.com/datasets/wcukierski/enron-email-dataset).
2. **Setup**: Place the raw file in the data sub directory and rename it as `emails_subset_1000.csv`.(i already placed that `emails_subset_1000.csv` file in data but that is only first 1000 mails. so ,if you want to run over all mails in `enron dataset` download from kaggle and `rename` it to `emails_subset_1000.csv`.)

## 1. The Corpus & Reproducibility
**Corpus:** I utilized a 1,000-email subset of the CMU Enron Email Dataset (Kaggle mirror). This dataset is ideal for testing long-term organizational memory due to its dense communication networks, informal knowledge sharing, and entity resolution challenges (e.g., aliases, changing roles).
**To Reproduce:**
1. Clone this repository and install requirements (`pip install -r requirements.txt`).
2. set you API key ( `export GEMINI_API_KEY="your_api_key_here"` ) using this command.
3. Run `python -m graph.build_graph` to run the extraction pipeline and build `memory_graph_output.json`. *(Note: Semantic extraction is limited to 10 emails by default to respect free-tier API rate limits, but header extraction runs on all 1,000).*
4. Run `python -m generate_context_packs` to generate the text-based Retrieval Context Packs.
5. Run `streamlit run app.py` to launch the interactive visualization layer.

## 2. Ontology & Extraction Contract
My pipeline separates probabilistic LLM extraction from deterministic Python logic to minimize the "hallucination surface area."
* **Schema Design:** I defined strict Pydantic models (`Entity`, `Claim`, `Evidence`). The LLM is restricted to a simplified intermediary schema, strictly extracting the semantic meaning (Subject, Relation, Object, Excerpt, Offsets).
* **Grounding:** Deterministic metadata (Message-ID, timestamp, UUIDs) is injected via Python, guaranteeing that every claim is immutably anchored to a specific source document and exact character offsets.
* **Quality Gates:** All extractions pass through a logic gate (`quality.py`) to reject empty strings, missing evidence, or ungrounded claims before they enter the durable graph.

## 3. Deduplication & Canonicalization Strategy
A memory system fails if it stores the same fact 100 ways. I implemented deduplication across three tiers:
* **Artifact Level:** `processed_msg_ids` prevents duplicate ingestion of identical emails or retries.
* **Entity Canonicalization:** Emails are parsed for domains, and text normalization (lowercasing, stripping) prevents duplicate node creation for stylistic differences. The `aliases` list safely merges variants into a canonical ID.
* **Claim Deduplication:** If the graph detects an existing relationship (e.g., `Phillip -> MANAGES -> Western Desk`), it does not overwrite the claim. Instead, it *appends* the new `Evidence` object to the existing claim's evidence list, bolstering the confidence of the fact without cluttering the graph.

## 4. Memory Graph & Update Semantics
The core engine is a `networkx.MultiDiGraph`.
* **Reversibility & Temporal Logic:** Claims carry a `valid_from` timestamp and a `status` field. Instead of mutating or deleting historical facts, new conflicting evidence supersedes older claims by updating the timeline, preserving the audit trail of "what used to be true."
* **Graceful Degradation:** The pipeline includes exponential backoff for API rate limits and injects safe, dynamic fallback data if quotas are exhausted, ensuring pipeline resilience and UI stability.

## 5. Layer10 Target Environment Adaptation
To adapt this local pipeline to Layer10's production environment (Email, Slack, Jira), I would implement the following architectural shifts:

* **Unstructured + Structured Fusion:** Instead of just Message-IDs, `source_id` would become a universal URI (e.g., `jira://PROJ-123` or `slack://channel_id/msg_ts`). A Jira webhook triggering a status change to "Done" would deterministically update a Graph Claim, while Slack discussions mentioning "PROJ-123" would attach as probabilistic Evidence to that same Claim.
* **Long-Term vs. Ephemeral Memory:** I would implement an "Evidence Threshold." A single Slack message might create a "Candidate Claim" (ephemeral). If a Jira ticket or formal Document corroborates it, it promotes to "Durable Memory."
* **Permissions (ACLs):** Memory retrieval must be access-aware. Every `Evidence` object would inherit the ACL (Access Control List) of its source document (e.g., "Slack Channel #exec-private"). At query time, the retrieval engine would filter the graph edges against the user's IAM token, ensuring users only retrieve memory grounded in sources they are explicitly authorized to read.
* **Operational Reality (Scale):** NetworkX is sufficient for local evaluation, but production requires a distributed graph database (e.g., Neo4j or AWS Neptune) to handle concurrent writes, graph algorithms at scale, and asynchronous message queue ingestion (Kafka/RabbitMQ) for real-time artifact processing.