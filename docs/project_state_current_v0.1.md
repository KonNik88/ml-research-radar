# ML Research Radar — Current State Checkpoint v0.1

## Document status

```text
document = consolidated current-state checkpoint
checkpoint_version = v0.1
checkpoint_date = 2026-07-06
scope = documentation / transfer / design-hardening baseline
canonical_truth = false
may_be_used_as_reconcile_input = false
mutates_canonical_documents = false
mutates_retrieval_artifacts = false
mutates_qdrant = false
mutates_postgres = false
mutates_api = false
mutates_ui = false
mutates_ranking = false
publishes_dataset = false
creates_runtime_graph = false
```

This document is a compact transfer and orientation checkpoint for **ML Research Radar**.
It records the current validated project model, accepted layer boundaries, current counters,
completed work, and recommended next slices.

It is not a new source of truth. The paper-level source of truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

All retrieval artifacts, Postgres tables, artifact evidence tables, graph outputs,
reports, API responses, UI state, and packages are derived/rebuildable layers.

---

## 1. Project identity

ML Research Radar is a paper-centric research-discovery platform for ML/AI research.

It is designed to:

- collect partially overlapping paper observations from multiple sources;
- reconcile them into canonical paper-level entities;
- preserve source provenance;
- build lexical/dense/hybrid retrieval artifacts;
- materialize optional Postgres serving tables;
- extract and validate implementation/evidence artifacts;
- enrich artifact metadata from providers such as GitHub and Hugging Face;
- build paper-level features, ranking profiles, paper detail views, similar-paper views, and topic-cluster views;
- expose a Discovery API and Streamlit UI over derived layers;
- build local derived graph lines for review/evidence analysis;
- protect every promotion/publication/runtime step through validation, reports, and manual-review gates.

It is not:

- an arXiv-only parser;
- a vector database wrapper;
- a RAG demo;
- a graph database project by default;
- a public dataset publication pipeline by default;
- a runtime graph API by default;
- a collection of unrelated scripts.

---

## 2. Non-negotiable architecture boundaries

### 2.1 Paper truth

```text
canonical_documents.jsonl = paper-level source of truth
```

Everything below is derived and rebuildable:

- retrieval artifacts;
- Qdrant collections;
- Postgres serving tables;
- artifact entities / observations / trusted links;
- provider metadata snapshots;
- paper features;
- ranking outputs;
- similar-paper outputs;
- topic clusters and projections;
- API responses;
- Streamlit UI state;
- graph outputs;
- graph packages;
- validation reports.

No derived layer may redefine paper identity or mutate canonical paper truth.

### 2.2 Identity separation

```text
source_doc_id / doc_id      = source-level observation identity
canonical_id                = reconciled paper-level identity
artifact_id                 = normalized external artifact identity
dense_index / Qdrant point  = retrieval-serving mapping in one build
graph node id               = typed derived graph identity
```

Paper identity priority:

```text
DOI
→ external DOI
→ arXiv ID
→ external arXiv ID
→ normalized title + year fallback
```

### 2.3 Provenance semantics

`canonical_documents.sources` is row-level provenance.

`source_count` is the number of source/provenance rows.

`unique_source_count` is the number of unique source families.

`source_ids` is a merged identifier map and must not be treated as strict provenance by itself.

Graph source-family evidence must derive from canonical provenance rows, not from `source_ids` alone.

---

## 3. Accepted current baseline

### 3.1 Canonical and retrieval baseline

```text
canonical_doc_count = 60,954
canonical_multisource_docs = 9,192
doi_count = 10,183
arxiv_backbone = 60,000
acl_family_docs = 957
acl_only_docs = 954
acl_enriched_existing_docs = 3
retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]
topic_clusters_count = 80
topic_assignments_count = 60,954
```

### 3.2 Artifact evidence baseline

Current accepted artifact-layer orientation:

```text
artifact_entities_db_count ≈ 7,333
artifact_entities_file_count ≈ 7,336
artifact_observations_db_count ≈ 38,246
paper_artifact_links_db_count ≈ 7,430
github_found_count ≈ 5,339
huggingface_found_count ≈ 77
```

Older slice-local numbers inside historical docs must not override the latest accepted checkpoint.
When in doubt, prefer the latest validation/export/read reports over historical narrative docs.

### 3.3 Qdrant baseline

```text
collection = ml_radar_dense_benchmark_v1
points_count = 60,954
vector_size = 384
distance = Cosine
selected profile = ef_256
transport = gRPC
public_qdrant_promotion = not performed
fallback = absent
```

Public `/search` dense/hybrid behavior remains file-backed.
Qdrant remains optional/experimental and is exposed through the experimental path only.

---

## 4. Implemented layers

## 4.1 Canonical corpus and merge policy

Completed:

- source normalization;
- source-level identity separation;
- paper-level reconciliation;
- conservative identity resolution;
- provenance-preserving merge;
- DOI/arXiv/title+year identity policy;
- arXiv backbone;
- OpenAlex, Semantic Scholar, Crossref, ACL alignment;
- canonical contract validation;
- controlled candidate promotion.

Important boundary:

```text
artifact/provider metadata never becomes paper truth
```

## 4.2 Retrieval layer

Implemented:

- compact BM25 lexical index;
- dense embeddings with `sentence-transformers/all-MiniLM-L6-v2`;
- lexical/dense/hybrid retrieval;
- backend-neutral hybrid score merge;
- retrieval artifacts save/load;
- retrieval manifest;
- retrieval artifact smoke tests;
- file dense exact backend;
- Qdrant dense backend abstraction;
- Qdrant parity helpers.

Reference dense semantics:

```text
scores = stored_embeddings @ normalized_float32_query
order = np.argsort(scores)[::-1]
```

Stored embeddings are used as persisted and are not silently re-normalized by parity/reference helpers.

## 4.3 API runtime layer

Implemented backend modes:

```text
file
db
```

File backend:

- public `/search?mode=lexical|dense|hybrid`;
- retrieval artifacts and embedding model;
- optional experimental Qdrant endpoint;
- Qdrant-independent health.

DB backend:

- document browse/filter;
- DB lexical search v1;
- artifact endpoints;
- document-artifact filters.

Intentional DB v1 limitation:

```text
DB backend supports lexical search only.
DB dense/hybrid search is intentionally rejected.
```

Qdrant failure contract:

```text
DenseBackendRequestError       -> 400 dense_backend_bad_request
DenseBackendUnavailableError   -> 503 dense_backend_unavailable
DenseBackendCompatibilityError -> 503 dense_backend_incompatible
DenseBackendResultError        -> 503 dense_backend_invalid_result
```

Qdrant failures must not make file runtime unhealthy.

## 4.4 Artifact evidence plane

Implemented artifact model:

```text
artifact_entities      = normalized external artifact identities
artifact_observations  = broad evidence rows
paper_artifact_links   = trusted serving links
```

Trusted link invariant:

```text
unique key = canonical_id + artifact_id + relation_type
```

Evidence multiplicity is preserved in metadata, not duplicated as multiple trusted links.

Shared trusted-link policy:

```text
policy_source = radar_core.artifacts.trusted_links
policy_version = artifact_trusted_links_policy_v1
```

Provider-specific trusted artifact types are trusted at `confidence >= 0.65`.
Generic links are trusted only when confidence is high, the source field is trusted, and the domain is not bibliographic/resolver/technical noise.

Legacy source-layer flag and trusted artifact evidence must remain separate:

```text
has_code_link ≠ has_trusted_code_artifact
```

## 4.5 GitHub and Hugging Face enrichment

GitHub/Hugging Face enrichment is artifact metadata enrichment, not paper-source enrichment.

GitHub date-filter semantics:

```text
pushed_*  -> metadata.github.pushed_at
updated_* -> artifact_entities.updated_at / materialized repository updated_at
```

Rows without the required provider metadata/date do not match provider-specific date filters.

## 4.6 Postgres serving layer

Postgres is a serving/materialization layer, not canonical truth.

Paper tables include:

```text
source_documents
canonical_documents
canonical_source_links
document_references
```

Artifact tables include:

```text
artifact_entities
artifact_observations
paper_artifact_links
```

Operational note:

```text
paper export with --replace may cascade to dependent artifact links;
full refresh should run artifact export after paper export.
```

## 4.7 Discovery layer

Implemented:

- paper features;
- ranking profiles;
- feature ranking filters/sorts;
- paper detail workspace;
- similar papers semantic and radar-adjusted modes;
- topic clusters;
- topic projection/map;
- Discovery API;
- Streamlit Discovery UI.

Known profile orientation:

```text
default_profile = recent_artifact_ready
required profiles include:
  - huggingface_ready
  - recent_artifact_ready
  - acl_radar
```

Discovery API is a product layer over derived features/evidence, not a source of truth.

---

## 5. Graph lines

There are two separate local derived graph lines.

Both are:

- local;
- derived;
- rebuildable;
- evidence/review artifacts;
- not canonical truth;
- not reconcile inputs;
- not DB replacements;
- not API/runtime features by default;
- not GraphRAG;
- not publication-ready without manual review.

## 5.1 Paper–Artifact Graph v0.1

Purpose:

```text
paper -> trusted artifact evidence graph
```

Node types:

```text
paper
artifact
provider
source_family
topic_cluster
```

Edge types:

```text
paper_has_artifact
artifact_from_provider
paper_observed_in_source_family
paper_assigned_to_topic_cluster
```

Accepted counters:

```text
nodes_count = 68,385
edges_count = 163,757
paper nodes = 60,954
artifact nodes = 7,336
provider nodes = 10
source_family nodes = 5
topic_cluster nodes = 80
paper_has_artifact edges = 7,430
artifact_from_provider edges = 7,336
paper_observed_in_source_family edges = 88,037
paper_assigned_to_topic_cluster edges = 60,954
trusted_links_used_count = 7,430
topic_edges_count = 60,954
```

Critical rule:

```text
paper_has_artifact edges derive from trusted paper_artifact_links semantics,
not directly from broad artifact_observations.
```

Completed line:

```text
contract
→ builder
→ output validator
→ inspection / QA
→ query CLI
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
→ analytics report
```

Manual review status:

```text
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

## 5.2 Citation / Reference Graph v0.1

Purpose:

```text
paper -> paper / paper -> external reference evidence graph
```

Input scope:

```text
referenced_dois
referenced_ids
referenced_arxiv_ids
```

Non-inputs:

```text
full text
PDF
HTML
raw bibliography strings
in-text citation context
```

Node types:

```text
paper
external_reference
source_family
```

Edge types:

```text
paper_references_paper
paper_references_external
paper_has_reference_source_family
```

Accepted counters:

```text
nodes_count = 529,295
edges_count = 745,516
paper nodes = 60,954
external_reference nodes = 468,336
source_family nodes = 5
paper_references_paper edges = 6,165
paper_references_external edges = 703,234
paper_has_reference_source_family edges = 36,117
resolved_reference_edges = 6,165
unresolved_reference_edges = 703,234
reference_resolution_ratio = 0.00869
```

Normalization rule:

```text
OpenAlex URL / ID references from referenced_ids -> reference_type = openalex_id
DOI references -> reference_type = doi only when DOI syntax matches
```

Completed line:

```text
contract
→ builder
→ output validator
→ inspection / QA
→ query CLI
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
→ analytics report
```

Manual review status:

```text
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Manual-review validator semantics:

```text
pending categories block publication;
pending categories do not fail the validator;
summary.ok=true means structural/safety gate is valid,
not that human review is complete.
```

---

## 6. Regression, reports, and DoD

The project uses validation/report gates instead of implicit trust.

Refresh DoD can aggregate:

- canonical summary;
- retrieval manifest/checks;
- DB smoke;
- canonical contract;
- artifact quality/export/read reports;
- artifact API filters;
- GitHub/Hugging Face enrichment;
- paper features;
- similar papers;
- Discovery API;
- topic clusters/projection;
- Streamlit UI;
- golden queries.

Optional gates remain opt-in unless the active slice requires them.

Artifact API filters are correctly modeled as an opt-in DB-backed regression gate, not as a mandatory requirement for every refresh.

---

## 7. Current safest development direction

The next work should be:

```text
review / regression / design-hardening first
runtime / public API / GraphRAG / Qdrant promotion only after accepted design slice
```

Recommended next slices:

1. **Graph Review Evidence Pack v0.1**
   - local review/evidence report over both graph lines;
   - no runtime/API/UI/DB/Qdrant/retrieval/ranking changes;
   - no publication;
   - no graph rebuild unless explicitly scoped.

2. **Citation / Reference Graph API Design v0.1**
   - design-only;
   - describe safe future query modes, caveats, failure semantics, boundaries;
   - no endpoint implementation;
   - no runtime graph loading.

3. **Regression / DoD / docs hardening**
   - optional gates;
   - checkpoint validation;
   - stale-counter protection;
   - accepted counter summaries.

4. **Project State / Accepted Checkpoint doc hardening**
   - maintain this document as the transfer baseline;
   - link it from roadmap / architecture docs.

---

## 8. Explicit non-goals for the immediate next slice

Do not do these without a separate accepted design:

- public graph API implementation;
- GraphRAG;
- Neo4j/NetworkX runtime;
- DB materialization of graph as serving truth;
- Qdrant public promotion;
- hidden Qdrant fallback;
- publication/upload;
- replacing canonical truth with graph/artifact/DB metadata;
- changing public `/search` behavior;
- changing ranking formulas silently.

---

## 9. Suggested immediate plan

Current dialogue should start with a documentation checkpoint slice:

```text
Current State Checkpoint v0.1
```

Minimal implementation:

```text
docs/project_state_current_v0.1.md
roadmap status update / link to the checkpoint
```

Suggested validation:

```text
git diff --check
python -m pytest tests/smoke/test_retrieval_artifacts_smoke.py -q  # optional, if env supports it
python -m pytest tests/smoke/test_trusted_artifact_links.py -q      # optional, if env supports it
```

For docs-only changes, the minimum acceptable check is:

```text
git diff --check
```

Suggested commit message:

```text
docs: add current project state checkpoint
```
