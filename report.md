# Grounded Memory Graph — Engineering Report

A pipeline that turns an unstructured email corpus into a **grounded knowledge
graph**, where every stored fact points back to an exact character span in a
specific source document.

The README covers setup and how to run the pipeline. This report covers the
architecture, the decisions behind it, and — with equal weight — the places where
the current implementation does not yet live up to its own thesis.

---

## 1. Problem and scope

Organisational knowledge lives in communication, not in databases. The obvious
approach is to feed emails to an LLM and store what it says. That fails in a
specific way: an LLM asked for structured facts will happily invent an
identifier, approximate a date, or paraphrase a quote it is citing. The graph
then contains claims that look sourced and are not.

The thesis of this project is a division of labour:

> **The model is allowed to produce meaning. It is never allowed to produce a
> fact about provenance.**

Every identifier, timestamp, UUID and source reference in the graph is written by
Python. The LLM contributes only semantics — which entities exist, what relation
holds between them, and which verbatim span supports it.

**In scope:** ingestion and parsing, LLM extraction under a strict schema,
grounding, three-tier deduplication, a temporal claim model, keyword retrieval
with citations, and a visual explorer.

**Out of scope:** embedding-based or vector retrieval, a persistent database,
multi-user access, and evaluation against a labelled ground-truth graph. The last
of those is the most significant absence and is discussed in §6.

---

## 2. Architecture and data flow

```
data/emails_subset_1000.csv
        │
        ▼
parse_emails.py ──► EmailArtifact (Pydantic)          ← per-email try/except:
        │            message_id, date, sender,          a malformed record is
        │            recipients, subject, body          skipped, not fatal
        ▼
normalize.py ──► lowercased addresses, angle brackets stripped from Message-ID
        │
        ▼
build_graph.py ─┬─► HEADER PATH  (all 1,000 emails)
                │     sender/recipient → Entity, SENT_EMAIL_TO → Claim
                │
                └─► SEMANTIC PATH (first 10 emails, rate-limited)
                      llm_extractor.py
                          │
                          ├─ Gemini returns: entities, relations, excerpt, offsets
                          └─ Python injects: message_id, UUID, timestamp
                          │
                      quality.py gate ──► rejected claims never enter the graph
                          │
                          ▼
                    MemoryGraph (networkx.MultiDiGraph)
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
  retrieval.py    generate_context_packs   app.py
  (cited packs)      (text export)      (Streamlit + pyvis)
                          │
                          ▼
              memory_graph_output.json  — 343 nodes, 368 edges
```

The two extraction paths exist because they have opposite cost profiles. Header
extraction is free and runs on the whole corpus; semantic extraction costs an API
call per email and is capped. That split is what makes the project runnable on a
free-tier key at all, and it is a real design constraint rather than an
unfinished feature.

---

## 3. Module walkthrough

| File | What it owns |
|---|---|
| `schema.py` | The four Pydantic models — `EmailArtifact`, `Entity`, `Evidence`, `Claim`. The contract everything else obeys. |
| `extraction/parse_emails.py` | CSV → `EmailArtifact`. Multipart body extraction, recipient splitting, RFC date parsing, and fallbacks for missing Message-ID and sender. |
| `extraction/normalize.py` | Canonical form for addresses and Message-IDs. Returns a **new** model via `model_copy(update=…)` rather than mutating. |
| `extraction/llm_extractor.py` | The Gemini call, the LLM-side schema, the grounding injection, retry/backoff, and the quality-gate application. |
| `extraction/quality.py` | Three checks a claim must pass to be stored at all. |
| `graph/build_graph.py` | Orchestration: dedup by message id, header path, semantic path, orphan-node safety net, JSON serialisation. |
| `main.py` | `MemoryGraph` — entity canonicalisation and the evidence-appending `add_claim`. |
| `retrieval.py` | Keyword → entities → claims → deduplicated, recency-ranked, cited context pack. |
| `generate_context_packs.py` | Writes text context packs from the serialised graph. |
| `app.py` | Streamlit explorer with a pyvis graph view, entity-type filtering, and an evidence panel. |

---

## 4. Design decisions

### 4.1 A separate, smaller schema for the LLM

`schema.py` defines the durable models. `llm_extractor.py` defines a **second,
deliberately reduced set** — `LLMEntity`, `LLMClaim`, `LLMEvidence` — and that is
what the model is asked to fill:

```python
class LLMEvidence(BaseModel):
    excerpt: str
    start_offset: int
    end_offset: int
```

Note what is absent: no `source_id`, no `timestamp`, no `claim_id`. The model
*cannot* supply them because the schema it is handed has nowhere to put them.
Python then constructs the real objects:

```python
Evidence(**ev.model_dump(), source_id=email.message_id,
         timestamp=email.date or datetime.now())
Claim(**c.model_dump(exclude={'evidence'}), claim_id=str(uuid.uuid4()), …)
```

This is the central decision. Making provenance *structurally unreachable* by the
model is stronger than asking it politely in the prompt and validating afterwards.

The call also uses Gemini's structured-output mode — `response_mime_type
="application/json"` with `response_schema=ExtractionResult` — at `temperature=0.1`,
so the response is schema-conformant before any of my code touches it.

### 4.2 The prompt carries four explicit rules

Semantics still need constraining. The extraction prompt fixes a closed relation
vocabulary (`WORKS_FOR`, `DISCUSSED_TOPIC`, `MANAGES`, `COMMITTED_TO`), demands
verbatim substrings for excerpts, demands exact character offsets, and requires
**referential integrity** — every `subject_id` and `object_id` used in a claim
must also appear in the entity list.

A closed vocabulary is the difference between a graph you can query and a pile of
free-text edges where `MANAGES`, `manages` and `is_manager_of` are three
relations.

### 4.3 Deduplication at three tiers

A memory system fails if it stores the same fact many ways. Each tier catches a
different duplicate:

| Tier | Mechanism | Catches |
|---|---|---|
| **Artifact** | `processed_msg_ids` set in `build_graph` | the same email ingested twice, or a retry |
| **Entity** | `entity_lookup` maps every alias and name to one canonical id | `Phillip Allen` / `phillip.allen@enron.com` / `P. Allen` |
| **Claim** | `add_claim` scans existing edges for a matching relation and **appends evidence** | the same relationship asserted in ten emails |

The third is the interesting one. `MemoryGraph.add_claim` does not overwrite and
does not add a parallel edge:

```python
for edge_key, edge_data in edges_dict.items():
    if edge_data['relation'] == claim.relation:
        edge_data['evidence'].extend(claim.evidence)
        return
```

Restating a fact therefore **strengthens** it — the same edge accumulates more
evidence — instead of cluttering the graph. That is the behaviour a memory system
should have, and it falls out of one branch.

### 4.4 A `MultiDiGraph`, chosen for what it permits

`networkx.MultiDiGraph` allows several distinct relations between the same pair
of nodes (`A MANAGES B` and `A DISCUSSED_TOPIC B` coexist) while §4.3 keeps any
single relation to one edge. A simple `DiGraph` would have forced those two facts
to collide; an un-deduplicated multigraph would have produced one edge per
mention.

### 4.5 Time modelled as supersession, not mutation

`Claim` carries `valid_from`, `valid_until`, and a `status` of
`active` / `superseded` / `deleted`, plus an extraction `version`. Facts are
never destroyed when contradicted — a new claim supersedes the old one and the
timeline is preserved, so "what did we believe, and when" stays answerable. In a
system whose purpose is long-term memory, deleting history is the one operation
that defeats the point.

### 4.6 Failing softly at the edges, strictly at the centre

The pipeline is deliberately lenient about *input* and strict about *storage*:

- a corrupted email is skipped with a message, not fatal (`load_and_parse_emails`)
- a missing Message-ID gets a generated one; a missing sender gets a fallback
- an LLM claim referencing an undefined entity gets that entity auto-created with
  `entity_type="Inferred"` rather than being dropped — visible in the graph as
  exactly what it is

But `quality.py` refuses any claim without a subject, an object, or at least one
piece of evidence carrying a `source_id`. Robustness at the boundary, no
compromise on grounding.

### 4.7 Living within a free-tier quota

Semantic extraction is capped at the first 10 emails with `time.sleep(4)` between
calls, and the API call retries **3 attempts** with exponential backoff on HTTP
429. Header extraction still runs across all 1,000 emails, so the graph has real
scale (343 nodes) even though only 10 emails were semantically parsed.

**When the quota is exhausted, extraction returns nothing.** That is worth
stating explicitly, because it used to do the opposite. An earlier version
injected a hardcoded `Western Trading Desk` entity and a synthetic `MANAGES`
claim so the explorer always had something to render — and those entered the
graph indistinguishable from extracted ones, in a pipeline whose entire purpose
is that no ungrounded fact is ever stored. It also quietly falsified every
downstream count, context pack and citation built on top.

An empty graph is an honest failure; a populated one built from invented facts is
not. Because the header path is unaffected, an exhausted quota now degrades the
semantic layer rather than corrupting the graph.

### 4.8 Retrieval that cites

`RetrievalEngine.search` matches a query against entity names, aliases and node
ids, collects incoming and outgoing edges, then deduplicates evidence by the
signature `subject-relation-object-source_id-start_offset` — so the same span
reached through two different edges is not repeated. Results are ranked by
recency and capped at `top_k`, and the output is formatted with the source id,
the offsets and the verbatim excerpt.

Recency is a placeholder ranking, chosen because it is honest about what it is;
it is not relevance. See §6.

---

## 5. Results

Running the pipeline over the committed 1,000-email subset produces a graph that
is checked into the repository as `memory_graph_output.json`:

| Measure | Value |
|---|---|
| Nodes (entities) | **343** |
| Edges (claims) | **368** |
| Emails ingested | 1,000 (header path) |
| Emails semantically extracted | 10 (rate-limited) |
| Serialised graph | ~724 KB |

Every claim in that file carries at least one `Evidence` object with a
`source_id`, character offsets and a timestamp — that is what `quality.py`
enforces, and it is checkable by reading the JSON.

**There is no accuracy number here, and there should not be one.** No labelled
ground-truth graph exists for this corpus, so extraction precision and recall are
unmeasured. What the artifact demonstrates is that the pipeline runs end to end
and that the grounding contract holds structurally — not that the extracted facts
are correct.

---

## 6. Limitations

Listed worst-first.

1. **No tests.** There are zero test files. The dedup logic in §4.3 and the
   grounding injection in §4.1 are the two things most worth pinning down, and
   both are currently protected only by reading the code.
2. **Offsets are never re-validated.** The prompt demands exact character offsets
   and verbatim excerpts, but nothing checks `body[start:end] == excerpt` before
   storing. This is now the one remaining path by which the model can assert
   something about provenance and be believed — and closing it is a handful of
   lines.
3. **Only 10 emails are semantically extracted.** The 343 nodes are
   overwhelmingly header-derived. The semantic layer — the part the architecture
   is actually about — is demonstrated, not exercised.
4. **Retrieval ranks by recency, not relevance.** Keyword matching plus a
   newest-first sort will miss a paraphrase and will bury an older, better
   answer.
5. **Extraction quality is unmeasured.** No ground truth, so no precision or
   recall figure exists for the pipeline.
6. **State is a JSON file.** Nothing is persistent, concurrent, or incremental;
   re-running rebuilds from scratch.

## 7. What I would do next

In the order I would actually do it:

1. **Verify offsets in Python** — assert `body[start:end] == excerpt` and reject
   the claim otherwise (§6.2).
2. Tests for the three dedup tiers and the grounding injection.
3. Hand-label ~50 emails to get a real precision/recall number.
4. Swap keyword retrieval for embeddings, keeping the citation format.

---

## 8. Reproduction

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your_key_here"

python -m graph.build_graph      # → memory_graph_output.json
python -m generate_context_packs # → text context packs
streamlit run app.py             # → interactive explorer
```

The repository ships `data/emails_subset_1000.csv` (1,000 rows) so it is clonable
and runnable immediately. For the full corpus, download the Enron dataset from
Kaggle and replace that file. Semantic extraction stays capped at 10 emails by
default; raise `LIMIT` in `graph/build_graph.py` if the key allows it.
