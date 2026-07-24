# ML Research Radar — Roadmap

## Document status

```text
document = primary living roadmap
accepted checkpoint = Current State Checkpoint v0.1
base checkpoint = Discovery Regression Runner Summary Report v1
current active direction = field-level provenance contract complete / bounded evidence builder next
current active slice = Field-Level Canonical Provenance Contract v0.1 completed / living-docs sync
public Qdrant promotion = not performed
public dense/hybrid backend = file
experimental Qdrant serving transport = gRPC
fallback = absent
scope of current branch = document and statically validate current field-selection semantics for all 61 CanonicalDocument fields; synchronize living docs; preserve the completed source-observation promotion and rollback evidence; perform no canonical, reconciliation, Postgres, retrieval, Qdrant, graph, ranking, API, UI, or publication behavior change
```

This roadmap describes the current validated state of **ML Research Radar**, the
architectural invariants that must remain stable, and the recommended order of
future work.

The project prefers complete, validated vertical slices over broad feature
expansion. The Field-Level Canonical Provenance Contract is now complete and
green. The next safe architecture direction is a bounded, file-first, read-only
Field-Level Canonical Provenance Evidence Builder before any full-corpus
materialization, runtime/API/UI surface, GraphRAG, graph DB, or Qdrant-promotion
work.

---

## 0. Current State Checkpoint v0.1

Status: **accepted documentation / transfer / design-hardening baseline**

The current accepted project-state checkpoint is documented in:

```text
docs/project_state_current_v0.1.md
```

The checkpoint is intentionally documentation-only:

```text
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

Accepted current direction:

```text
operational source-observation identity = completed
Field-Level Canonical Provenance Contract v0.1 = completed
next = Field-Level Canonical Provenance Evidence Builder v0.1
runtime / public API / GraphRAG / Qdrant promotion only after a separate accepted design slice
```

Recently completed safe slices:

1. **Current State Checkpoint v0.1** — consolidate the accepted project state and layer boundaries.
2. **Graph Review Evidence Pack v0.1** — local read-only evidence pack for Citation / Reference Graph and Paper–Artifact Graph manual review support.
3. **Citation / Reference Graph API Design v0.1** — design-only API contract; no endpoint implementation.
4. **Graph API Response Fixture Design v0.1** — expected JSON response/error/caveat fixtures before endpoint implementation.
5. **Graph Runtime Stale-Version Compatibility Design v0.1** — compatibility rules for graph package/output freshness and canonical baseline matching.
6. **Citation / Reference Graph API Implementation Plan v0.1** — implementation plan only, with gates and rollback.
7. **Citation Graph API Disabled Status Endpoint v0.1** — first narrow code slice: status-only, disabled by default, no graph traversal/runtime loader.
8. **Citation Graph API Docs Sync v0.1** — align API reference, roadmap, current-state checkpoint, and restart/runbook docs with the disabled status endpoint.
9. **Citation Graph Status Compatibility Probe v0.1** — second narrow code slice: read-only compatibility/status probe over existing local graph/package/report state; no graph traversal/runtime loader.
10. **Citation Graph Fixture Store v0.1** — internal read-only fixture-backed query core.
11. **Citation Graph Outgoing References Endpoint v0.1** — first narrow read-only traversal endpoint; outgoing references only, no external/source-family/top endpoints and no full graph runtime loader.
12. **Citation Graph Incoming Citations Endpoint v0.1** — second narrow read-only traversal endpoint; incoming resolved internal citations only, no external/source-family/top endpoints and no full graph runtime loader.
13. **Citation Graph Incoming Citations Endpoint Docs Sync v0.1** — shared docs synchronized with the second traversal endpoint.
14. **Citation Graph Traversal API Checkpoint v0.1** — docs/regression-hardening checkpoint over `status + references + citations`; no new endpoint.
15. **Citation Graph External Reference Papers Endpoint v0.1** — third narrow read-only traversal endpoint; external reference to referencing papers only, no source-family/top/full-runtime endpoints.
16. **Citation Graph Source Families Endpoint v0.1** — fourth narrow read-only diagnostics endpoint; source-family reference-evidence summary only, no top/full-runtime endpoints.
17. **Citation Graph Source Families Endpoint Docs Sync v0.1** — shared docs synchronized with the fourth graph endpoint.
18. **Citation Graph Traversal API Checkpoint v0.2** — docs/regression-hardening checkpoint over `status + references + citations + external-reference papers + source-families`; no new endpoint.
19. **Citation Graph Top Referenced Papers Endpoint v0.1** — fifth narrow read-only diagnostics endpoint; top resolved internal reference counts only.
20. **Citation Graph Top Referenced Papers Endpoint Docs Sync v0.1** — shared docs synchronized with the fifth graph diagnostics endpoint.
21. **Citation Graph Top External References Endpoint v0.1** — sixth narrow read-only diagnostics endpoint; top unresolved external-reference counts only, no full-runtime endpoints.
22. **Citation Graph Top External References Endpoint Docs Sync v0.1** — shared docs synchronized with the sixth graph diagnostics endpoint.
23. **Citation Graph Traversal API Checkpoint v0.3** — completed docs/regression-hardening checkpoint over the seven implemented graph routes; no new endpoint.
24. **Citation Graph API Regression Check v0.1** — completed static regression validator over the accepted seven-route graph API block.
25. **Citation Graph API Regression DoD Wiring v0.1** — completed opt-in DoD gate wiring for the regression report; no endpoint or runtime behavior change.
26. **Graph API / Streamlit Productization Design v0.1** — completed design-only bridge from accepted graph APIs to future Streamlit UI slices; no UI code or API behavior change.
27. **Citation Graph Streamlit Status Panel v0.1** — completed first UI code slice; Streamlit reads `/citation-graph/status` and renders availability/caveats only.
28. **Citation Graph Paper Workspace Panel v0.1** — completed second UI code slice; Streamlit reads selected-paper `/references` and `/citations` endpoints and renders evidence tables only.
29. **Citation Graph Diagnostics UI v0.1** — completed third UI code slice; Streamlit reads `/source-families`, `/top-referenced-papers`, and `/top-external-references` endpoints and renders diagnostic tables only.
30. **Citation Graph External Reference Lookup UI v0.1** — completed fourth UI code slice; Streamlit reads `/external-references/{reference_id}/papers` with explicit URL/path quoting and renders referencing-paper evidence only.
31. **Citation Graph UI Productization Checkpoint v0.1** — completed validator-light checkpoint over seven accepted API routes and four implemented thin Streamlit evidence consumers; no new runtime behavior.
32. **Citation Graph Store Cache & Reload Regression v0.1** — completed regression-hardening slice over the bounded file-backed store cache and `/reload` invalidation semantics; no new endpoint or graph mutation.
33. **Citation Graph Failure Isolation & Error Recovery v0.1** — completed regression-hardening slice over graph-file failures, graph-scoped error mapping, cache non-poisoning, and recovery without process restart.
34. **Citation Graph Live Smoke & Known-Issues Hardening v0.1** — completed operator-facing validation/docs slice over the existing seven-route local-inspection API; no runtime-surface expansion.
35. **Citation Graph Manual-Review Evidence Preparation v0.1** — completed read-only review-support slice over the existing 18-category checklist; no automated approval or publication.
36. **Manual Citation Graph Review Execution v0.1** — completed human-governance slice; 18/18 categories passed, checklist approved, publication remains separate.
37. **Source Observation Materialization Identity v0.1** — completed deterministic physical identity for all selected source observations.
38. **Source Observation Materialization Operational Promotion v0.1** — completed default-DB promotion with checked backups, retained rollback DB, and green product gates.
39. **Field-Level Canonical Provenance Contract v0.1** — classified all 61 canonical fields, added a read-only 99-check validator and eight deterministic smoke tests, and preserved current reconcile behavior.

Recommended next safe slices:

1. **Field-Level Canonical Provenance Evidence Builder v0.1** — bounded derived JSONL evidence over synthetic fixtures and selected audit samples; no full-corpus generation or runtime surface.
2. **Semantic Scholar Public Release Boundary Remediation v0.1** — separate publication-governance track after the rejected release review.
3. **Paper–Artifact Graph API Design v0.1** — only if existing Artifact API surfaces prove insufficient for a concrete product requirement.

Explicit immediate non-goals:

- no GraphRAG implementation;
- no Neo4j/NetworkX runtime;
- no additional graph traversal endpoints beyond the implemented outgoing-references, incoming-citations, external-reference-papers, source-families, top-referenced-papers, and top-external-references routes in this checkpoint;
- no Qdrant promotion;
- no graph DB materialization layer;
- no publication/upload;
- no mutation of canonical truth, retrieval, DB, API, UI, ranking, or Qdrant.

Core invariants to preserve:

```text
canonical_documents.jsonl = paper truth
retrieval / DB / artifacts / graph / reports / API / UI = derived layers
Qdrant = optional/experimental derived vector-serving layer
graph outputs = local derived evidence/review artifacts
trusted artifact links ≠ raw artifact observations
legacy has_code_link ≠ trusted artifact evidence
manual_review summary.ok ≠ publication approval
```

Current baseline markers:

```text
canonical_doc_count = 60,954
multisource_doc_count = 9,192
retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_dim = 384
topic_clusters_count = 80
topic_assignments_count = 60,954
```

Graph line markers:

Citation / Reference Graph v0.1:

```text
nodes_count = 529,295
edges_count = 745,516
paper_references_paper = 6,165
paper_references_external = 703,234
reference_resolution_ratio = 0.00869
publication_ready = false
manual_review_required = true
```

Paper–Artifact Graph v0.1:

```text
nodes_count = 68,385
edges_count = 163,757
paper_has_artifact = 7,430
artifact_from_provider = 7,336
paper_observed_in_source_family = 88,037
paper_assigned_to_topic_cluster = 60,954
publication_ready = false
manual_review_required = true
```

Boundary:

```text
Current State Checkpoint v0.1 is not a new runtime layer.
It is not a graph API.
It is not a GraphRAG step.
It is not Qdrant promotion.
It is not publication.
It is a transfer-safe architectural checkpoint for future slices.
```

---

## 1. Project identity

ML Research Radar is a:

```text
paper-centric canonical corpus and research-discovery platform
for ML/AI research
```

It is not:

- an arXiv-only parser;
- a JSONL search demo;
- a vector-database wrapper;
- a RAG demo;
- a collection of unrelated scripts.

The platform collects partially overlapping observations from multiple sources,
reconciles them into paper-level canonical entities, and builds rebuildable
retrieval, serving, evidence, analytics, API, and UI layers above the canonical
corpus.

---

## 2. Architectural invariants

### 2.1 Paper truth

```text
data/analytics/reconciled/canonical_documents.jsonl
= paper-level source of truth
```

Derived and rebuildable layers:

- Postgres serving tables;
- lexical and dense retrieval artifacts;
- Qdrant collections;
- artifact evidence tables;
- paper features;
- ranking outputs;
- similar-paper outputs;
- topic clusters;
- UMAP projection;
- API responses;
- UI state.

None of these layers may redefine paper identity.

### 2.2 Identity separation

```text
source_observation_id = deterministic operational source-observation identity
doc_id = legacy normalized-document id, not globally unique across sources
canonical_id = reconciled paper-level identity
artifact_id = normalized artifact identity
dense_index / Qdrant point_id = serving mapping inside one retrieval generation
```

Paper identity priority:

```text
DOI
→ external DOI
→ arXiv ID
→ external arXiv ID
→ normalized title + year fallback
```

### 2.3 Qdrant

```text
Qdrant = optional derived dense-serving implementation
```

Qdrant is not:

- a paper source;
- canonical truth;
- a retrieval strategy exposed as a public mode;
- a required dependency of general service health.

Public retrieval strategies remain:

```text
lexical
dense
hybrid
```

Dense implementation is an internal concern:

```text
file
qdrant
```

---

## 3. Current green checkpoint

### 3.1 Corpus and retrieval

```text
canonical_doc_count = 60954
canonical_multisource_docs = 9192
doi_count = 10183

arXiv backbone = 60000
ACL-family docs = 957
ACL-only docs = 954
ACL-enriched existing docs = 3

retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]
dense_vectors_normalized = true
```

### 3.1.1 Operational source-observation materialization

```text
operational_db = ml_radar
source_documents = 88,178
canonical_source_links = 88,037
resolved_links = 88,037
non_contributing_source_observations = 141
null_links = 0
dangling_links = 0
missing_selected_observations = 0
full_parity_ok = true
rollback_db = ml_radar_pre_source_identity_v01_20260722t101620z
```

Canonical documents remain 60,954 and the active retrieval build remains
`20260504T164021Z`. This was a derived serving-layer identity correction, not a
reconciliation or canonical promotion.

### 3.2 Golden Set

```text
enabled_queries_count = 34
explicit_canonical_labeled_enabled_count = 34
weak_pattern_enabled_count = 0
```

### 3.3 Qdrant collection

```text
collection = ml_radar_dense_benchmark_v1
points_count = 60954
vector_size = 384
distance = Cosine
status = green
optimizer_status = ok
experimental transport = gRPC
grpc_port = 6334
selected profile = ef_256
```

### 3.4 Qdrant hybrid evaluation

```text
queries = 34
scenarios = 136
successful = 136 / 136
errors = 0
fallback = 0
blocking classifications = 0
determinism failures = 0

final result-set parity = 136 / 136
exact final order = 134 / 136
exact dense + final parity = 132 / 136
```

Public behavior remains:

```text
/search?mode=dense  -> file dense
/search?mode=hybrid -> file dense component
/experimental/search/qdrant -> Qdrant gRPC
/health -> Qdrant-independent
fallback -> absent
```

### 3.5 Ranking evaluation

```text
recommended_outcome = reject_heuristic_reranking
reference_behavior = unranked hybrid
public_behavior_change = false
```

This means `rank=false` remains the reference behavior and `rank=true` remains
explicit optional/experimental behavior.

---

## 4. Completed stages

### 4.1 Canonical corpus foundation

Status: **done / green**

Completed:

- source normalization;
- source-level identity separation;
- paper-level reconcile;
- conservative identity resolution;
- provenance-preserving merge;
- DOI normalization and conflict protection;
- arXiv backbone;
- OpenAlex, Semantic Scholar, and Crossref alignment;
- ACL Anthology integration;
- canonical contract validation;
- controlled candidate promotion.

### 4.2 Incremental refresh and promotion safety

Status: **done / green**

Lifecycle:

```text
capture baseline
→ detect changes
→ extract candidates
→ selective enrichment
→ candidate reconcile
→ audit
→ provenance consistency
→ explicit promotion
→ rebuild derived layers
→ strict Definition of Done
```

Rule:

```text
candidate / experiment
≠ stable latest
```

### 4.3 Retrieval foundation

Status: **done / green**

Completed:

- lexical retrieval;
- exact dense retrieval;
- hybrid retrieval;
- retrieval manifest;
- artifact validation;
- file runtime;
- retrieval evaluation;
- search-quality experiments;
- controlled experiments;
- Golden Set validation;
- similar-paper retrieval.

### 4.4 Postgres serving foundation

Status: **done / green**

Completed:

- canonical document materialization;
- source and provenance links;
- document browse/filter;
- DB lexical search v1;
- artifact tables;
- artifact API;
- dual file/DB runtime boundaries.

Intentional asymmetry:

```text
file backend = retrieval-first runtime
DB backend = browse/filter/artifact/lexical runtime
```

### 4.5 Artifact evidence plane

Status: **done / green**

Completed:

- artifact extraction and normalization;
- artifact entities;
- artifact observations;
- trusted paper-artifact links;
- GitHub enrichment;
- Hugging Face enrichment;
- Postgres materialization;
- artifact API and filters;
- operational validation.

### 4.6 Discovery API and Streamlit UI

Status: **done / green**

Completed:

- discovery ranking profiles;
- paper detail/card API;
- similar papers;
- topic clusters;
- topic projection/map;
- artifact explorer;
- Streamlit thin client;
- runtime status and reload surfaces.

### 4.7 Dense Search Backend Abstraction v1

Status: **done / green**

Implemented:

```text
DenseSearchBackend
├── FileDenseBackend
└── QdrantDenseBackend
```

Backends own only dense candidate generation.

### 4.8 Qdrant Failure Contract v1

Status: **done / green**

Implemented stable mapping:

```text
DenseBackendRequestError       -> 400 dense_backend_bad_request
DenseBackendUnavailableError   -> 503 dense_backend_unavailable
DenseBackendCompatibilityError -> 503 dense_backend_incompatible
DenseBackendResultError        -> 503 dense_backend_invalid_result
```

Additional guarantees:

- hydration miss fails explicitly;
- no hidden fallback;
- `/health` remains Qdrant-independent;
- public dense/hybrid remain file-backed;
- stop/start recovery works;
- reload recreates Qdrant backend.

### 4.9 Qdrant Runtime Observability v1

Status: **done / green**

Implemented:

```text
GET /runtime
GET /runtime?refresh_qdrant=true
```

Runtime diagnostics include collection compatibility, profile/build information,
backend creation and compatibility state, request/success/failure counters,
last-failure evidence, timings, requested/effective backend, and
`fallback_applied=false`.

### 4.10 Qdrant Serving Performance v1

Status: **done / green**

Coverage:

```text
backend-only:
FileDenseBackend vs QdrantDenseBackend

end-to-end:
public file-dense /search
vs
experimental /experimental/search/qdrant
```

Established:

- read-only serving benchmark;
- explicit gRPC transport;
- repeated zero-error concurrency evidence;
- exact quality comparisons;
- runtime transport diagnostics.

Public dense/hybrid remained file-backed.

### 4.11 Qdrant Hybrid Evaluation v1

Status: **done / green**

Implemented controlled comparison:

```text
lexical candidates + FileDenseBackend
vs
lexical candidates + QdrantDenseBackend
```

No public Qdrant promotion was performed.

### 4.12 Ranking Evaluation and Hardening v1

Status: **done / green**

Accepted decision:

```text
reject_heuristic_reranking
```

The current heuristic ranking remains explicit optional behavior only.

### 4.13 Retrieval Serving Checkpoint v1

Status: **done / green**

Implemented lightweight checkpoint gate:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint
```

Default required checks:

```text
ranking_evidence_regression
qdrant_hybrid_evidence
```

Optional checks:

```text
qdrant_serving_performance_evidence
qdrant_collection_live
api_runtime_smoke
```

The gate does not rerun heavy benchmark jobs by default.

### 4.14 Regression Runner DB Preflight v1

Status: **done / green**

Implemented an early read-only DB preflight in the Discovery API regression
runner for DB-backed regression paths.

Covered flags:

```text
--include-artifact-api-filters
--include-db-smoke
```

Preflight checks:

```text
ML_RADAR_SEARCH_BACKEND resolves to db for the preflight
Postgres ping succeeds
canonical_documents exists and is non-empty
artifact_entities exists and is non-empty
paper_artifact_links exists and is non-empty
```

The preflight fails before the longer file-backed regression sequence when the
local DB serving layer is unavailable or incomplete. It does not replace the
Artifact API filters validator and does not write validation reports.

---

### 4.15 Discovery Regression Runner Summary Report v1

Status: **done / green**

Implemented one lightweight JSON/Markdown summary report for every Discovery API
regression runner execution, including DB preflight and all subprocess steps.

Report outputs:

```text
artifacts/reports/validation/discovery_api_regression_runner_latest.json
artifacts/reports/validation/discovery_api_regression_runner_latest.md
artifacts/reports/validation/history/discovery_api_regression_runner_<timestamp>.json
artifacts/reports/validation/history/discovery_api_regression_runner_<timestamp>.md
```

The report is operational evidence. It does not replace individual validator
reports and is not currently a DoD input.

### 4.16 Dataset Release Track v0.1

Status: **implemented local candidate pipeline / not published**

Implemented the metadata-only dataset-release track:

```text
contract
→ config validation
→ local export runner
→ output validation
→ data-quality summary
→ review-readiness gate
```

Current boundary:

```text
dataset_name = ml_research_radar_metadata
version = v0.1
release_family = clean_research_metadata
publication_status = not_published
manual_review_required_before_publication = true
```

Generated local candidate layout:

```text
data/datasets_release/ml_research_radar_metadata/v0.1/
├── data.parquet
├── schema.json
├── manifest.json
├── README.md
├── data_quality_summary.json
└── checksums.txt
```

Correct green review-readiness interpretation:

```text
technical_candidate_ready = true
manual_review_required = true
publication_ready = false
publication_block_reason = manual_review_not_completed
```

No public upload is performed in this track.

### 4.17 Paper-Artifact Graph v0.1 local candidate line

Status: **done / green local derived graph line / not published**

Implemented sequence:

```text
contract
→ builder
→ output validator
→ inspection / QA
→ query CLI
→ release candidate
→ package
→ line checkpoint
```

Current accepted local graph counters:

```text
nodes_count = 68385
edges_count = 163757
paper nodes = 60954
artifact nodes = 7336
provider nodes = 10
source_family nodes = 5
topic_cluster nodes = 80
paper_has_artifact edges = 7430
artifact_from_provider edges = 7336
paper_observed_in_source_family edges = 88037
paper_assigned_to_topic_cluster edges = 60954
trusted_links_used_count = 7430
topic_edges_count = 60954
```

Line checkpoint interpretation:

```text
paper_artifact_graph_line_complete = true
technical local graph/package candidate = green
manual_review_required = true
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Boundary:

```text
graph/package/reports are derived and rebuildable
graph is not canonical truth
graph is not a reconcile input
graph is not a DB source
graph is not a runtime requirement
graph is not an API/UI feature
graph is not GraphRAG
graph/package are not publication-ready without manual review
```

### 4.18 Paper-Artifact Graph Manual Review Checklist v0.1

Status: **done / green local read-only governance gate / not published**

Implemented after the completed local graph line and package candidate:

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
```

Accepted local validation:

```text
9 passed
ok = true
required_failed_count = 0
strict = true
total_checks = 20
warning_count = 0
```

Key semantic contract:

```text
pending manual-review categories block publication
pending manual-review categories do not fail the validator
```

Default verdict:

```text
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Boundary:

```text
manual-review gate is read-only
manual-review reports are derived evidence
graph/package/manual-review are not canonical truth
graph/package/manual-review are not reconcile inputs
manual-review does not publish anything
manual-review does not rebuild graph or package outputs
manual-review does not redefine trusted-link policy
manual-review does not change DB/Qdrant/API/UI/retrieval/ranking behavior
```

### 4.19 Paper-Artifact Graph Analytics v0.1

Status: **done / green local read-only analytics report / not published**

Implemented after the completed local graph line, manual-review gate, and package candidate:

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

Accepted local validation:

```text
8 passed
ok = true
required_failed_count = 0
strict = true
total_checks = 40
warning_count = 0
```

Analytics report focus:

```text
node and edge type counters
provider distribution over artifact nodes
provider distribution over paper-artifact links
source-family distribution
topic-cluster artifact readiness
papers with trusted artifacts
artifacts linked to papers
multi-paper artifact diagnostics
isolated artifact diagnostics
top multi-paper artifacts
small sample IDs for manual inspection
```

Boundary:

```text
analytics report is read-only
analytics reports are derived evidence
graph/package/manual-review/analytics are not canonical truth
graph/package/manual-review/analytics are not reconcile inputs
analytics does not publish anything
analytics does not rebuild graph or package outputs
analytics does not change manual-review approval state
analytics does not redefine trusted-link policy
analytics does not change DB/Qdrant/API/UI/retrieval/ranking behavior
```


### 4.20 Citation / Reference Graph Contract v0.1

Status: **done / green local contract-only graph definition**

Implemented the first contract for a separate citation/reference graph line:

```text
Paper-Artifact Graph = paper → artifact evidence graph
Citation / Reference Graph = paper → paper / paper → external reference evidence graph
```

Accepted local validation:

```text
10 passed
ok = true
required_failed_count = 0
total_checks = 48
warning_count = 0

--check-paths:
ok = true
required_failed_count = 0
total_checks = 50
warning_count = 0
```

Contract semantics:

```text
references_count / cited_by_count are diagnostic metadata
explicit reference fields create graph edge evidence
unresolved references remain external_reference nodes
source_family nodes derive from canonical provenance rows, not source_ids only
citation/reference graph is derived evidence, not paper truth
```

Boundary:

```text
contract is read-only and contract-only
contract does not build graph output
contract does not change canonical truth
contract is not a reconcile input
contract does not change DB/Qdrant/API/UI/retrieval/ranking behavior
contract does not introduce NetworkX/Neo4j/GraphRAG runtime
```

### 4.21 Citation / Reference Graph Builder v0.1

Status: **done / green local file-first derived graph builder and output validator**

Implemented after the accepted citation/reference graph contract:

```text
contract
→ builder
→ output validator
```

Accepted local validation after reference-id normalization fix:

```text
13 passed

builder:
ok = true
nodes_count = 529295
edges_count = 745516

output validator:
ok = true
required_failed_count = 0
total_checks = 36
warning_count = 0
```

Accepted local graph counters:

```text
nodes_count = 529295
edges_count = 745516

paper nodes = 60954
external_reference nodes = 468336
source_family nodes = 5

paper_references_paper edges = 6165
paper_references_external edges = 703234
paper_has_reference_source_family edges = 36117
```

Current v0.1 interpretation after reference-id normalization fix:

```text
Most explicit references currently remain unresolved external references.
This is expected for v0.1 and is not treated as a builder failure.
The internal paper→paper links are conservative resolved links only.
OpenAlex references from referenced_ids are normalized as openalex_id, not DOI-like URL values.
```

Boundary:

```text
builder is file-first
local graph output is derived and rebuildable
local graph output is not canonical truth
local graph output is not a reconcile input
builder does not change canonical truth
builder does not change DB/Qdrant/API/UI/retrieval/ranking behavior
builder does not introduce NetworkX/Neo4j/GraphRAG runtime
builder does not publish or package anything
```


### 4.22 Citation / Reference Graph Reference Normalization Fix v0.1.1

Status: **done / green local builder bugfix**

Implemented after the first Query CLI smoke exposed that OpenAlex URLs from `referenced_ids` could be mislabeled as DOI-like references.

Accepted fix:

```text
OpenAlex URL / ID references from referenced_ids -> reference_type = openalex_id
DOI references -> reference_type = doi only when they match DOI syntax
```

Accepted local validation:

```text
13 passed
builder ok = true
output validator ok = true
inspection ok = true
required_failed_count = 0
warning_count = 0
```

Updated local graph counters after rebuild:

```text
nodes_count = 529295
edges_count = 745516
paper nodes = 60954
external_reference nodes = 468336
source_family nodes = 5
paper_references_paper edges = 6165
paper_references_external edges = 703234
paper_has_reference_source_family edges = 36117
reference_resolution_ratio = 0.00869
```

Boundary:

```text
normalization fix does not add new source fields
normalization fix does not parse full text
normalization fix does not change canonical truth
normalization fix does not change DB/Qdrant/API/UI/retrieval/ranking behavior
```

### 4.23 Citation / Reference Graph Inspection v0.1

Status: **done / green local read-only inspection/report layer**

Implemented after the builder/output-validator checkpoint and updated after the reference-id normalization fix.

Accepted local validation:

```text
7 passed
ok = true
required_failed_count = 0
total_checks = 35
warning_count = 0
```

Accepted local inspection counters after reference-id normalization fix:

```text
nodes_count = 529295
edges_count = 745516
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference_resolution_ratio = 0.00869
```

Boundary:

```text
inspection is read-only
inspection reports are derived evidence
graph/inspection must not be used as reconcile input
inspection does not rebuild graph output
inspection does not change DB/Qdrant/API/UI/retrieval/ranking behavior
```

### 4.24 Citation / Reference Graph Query CLI v0.1

Status: **done / green local read-only offline query CLI**

Implemented after the accepted builder, output validator, inspection layer, and reference-id normalization fix.

Supported query modes:

```text
paper -> outgoing references
paper <- incoming internal citing papers
external_reference -> citing papers
top internal referenced canonical papers
top unresolved external references
source_family -> reference-bearing papers
```

Accepted local validation:

```text
8 passed
JSON output works
Markdown output works
```

Accepted local graph/query counters:

```text
nodes_count = 529295
edges_count = 745516
paper_references_paper = 6165
paper_references_external = 703234
reference_resolution_ratio = 0.00869
```

Boundary:

```text
CLI is read-only
CLI does not rebuild graph output
CLI writes no validation reports by default
CLI does not change canonical truth
CLI does not change DB/Qdrant/API/UI/retrieval/ranking behavior
CLI does not introduce NetworkX/Neo4j/GraphRAG runtime
```


### 4.25 Citation / Reference Graph Docs Counter Refresh v0.1

Status: **done / green docs-only counter and status refresh**

Implemented after the reference-id normalization fix and Query CLI v0.1 merge.

Purpose:

```text
Remove stale pre-normalization counters from shared docs and align citation/reference graph docs with the accepted post-normalization baseline.
```

Accepted validation:

```text
grep over stale counters returned empty
citation/reference smoke set = 28 passed
output validator ok = true
inspection validator ok = true
```

Accepted post-normalization counters:

```text
nodes_count = 529295
edges_count = 745516
paper_references_paper = 6165
paper_references_external = 703234
external_reference_nodes_count = 468336
reference_resolution_ratio = 0.00869
```

Boundary:

```text
docs refresh is docs-only
no graph rebuild
no validator code changes
no DB/Qdrant/API/UI/retrieval/ranking behavior change
no package
no publication
```

### 4.26 Citation / Reference Graph Release Candidate v0.1

Status: **done / green local read-only release-candidate readiness gate / not published**

Implemented after the accepted citation/reference graph Query CLI and docs counter refresh.

Accepted local validation:

```text
6 passed
ok = true
required_failed_count = 0
strict = true
total_checks = 17
warning_count = 0
```

Accepted release-candidate counters:

```text
nodes_count = 529295
edges_count = 745516
paper nodes = 60954
external_reference nodes = 468336
source_family nodes = 5
paper_references_paper edges = 6165
paper_references_external edges = 703234
paper_has_reference_source_family edges = 36117
reference_resolution_ratio = 0.00869
```

Expected release-candidate verdict:

```text
technical_graph_candidate_ready = true
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Boundary:

```text
release-candidate validator is read-only
release-candidate reports are derived evidence
graph/release-candidate must not be used as reconcile input
release-candidate does not rebuild graph output
release-candidate does not package or publish graph output
release-candidate does not change DB/Qdrant/API/UI/retrieval/ranking behavior
```


### 4.26 Citation / Reference Graph Package v0.1

Status: **done / green local package candidate layer / not published**

Implemented after the accepted release-candidate readiness gate:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection / QA report
→ query CLI
→ docs counter refresh
→ release candidate
→ package
```

Accepted local validation:

```text
5 passed
release candidate ok = true
package build ok = true
package validator ok = true
required_failed_count = 0
warning_count = 0
```

Accepted local package evidence:

```text
included_files_count = 9
zip_size_bytes = 65516030
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Boundary:

```text
package is local generated output
package is not canonical truth
package is not a reconcile input
package is not publication-ready
package does not rebuild graph output
package does not change DB/Qdrant/API/UI/retrieval/ranking behavior
package does not parse full text, PDFs, or bibliography sections
```


### 4.27 Citation / Reference Graph Line Checkpoint v0.1

Status: **done / green local read-only line checkpoint / not published**

Implemented after the local citation/reference graph package candidate:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection
→ query CLI
→ docs counter refresh
→ release candidate
→ package
→ line checkpoint
```

Accepted local validation:

```text
5 passed
ok = true
required_failed_count = 0
strict = true
total_checks = 20
warning_count = 0
full citation/reference smoke set = 44 passed
```

Line checkpoint interpretation:

```text
citation_reference_graph_line_complete = true
line_checkpoint_ready = true
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Boundary:

```text
line checkpoint is read-only
line checkpoint does not rebuild graph or package output
line checkpoint does not publish anything
line checkpoint does not change canonical/reconcile/DB/API/UI/retrieval/Qdrant/ranking behavior
line checkpoint does not parse full text, PDFs, or bibliography/reference sections
```

### 4.28 Citation / Reference Graph Manual Review Checklist v0.1

Status: **done / green local read-only manual-review governance gate / not published**

Implemented after the completed local citation/reference graph line checkpoint:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection
→ query CLI
→ docs counter refresh
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
```

Accepted local validation:

```text
11 passed
ok = true
required_failed_count = 0
strict = true
total_checks = 21
warning_count = 0
full citation/reference smoke set = 55 passed
```

Key semantics:

```text
pending manual-review categories block publication
pending manual-review categories do not fail the validator
summary.ok=true means the gate is structurally valid, not that human review is complete
```

Default verdict:

```text
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Citation/reference caveats preserved by the gate:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
raw_reference_strings_without_identifiers_parsed = false
unresolved_references_preserved_as_external_reference_nodes = true
reference_resolution_ratio = 0.00869
```

Boundary:

```text
manual-review gate is read-only
manual-review gate does not rebuild graph or package output
manual-review gate does not publish anything
manual-review gate does not change canonical/reconcile/DB/API/UI/retrieval/Qdrant/ranking behavior
manual-review gate does not parse full text, PDFs, or bibliography/reference sections
```

### 4.29 Citation / Reference Graph Analytics v0.1

Status: **done / green local read-only analytics/report layer / not published**

Implemented after the completed local citation/reference graph line, package candidate,
line checkpoint, and manual-review gate:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection
→ query CLI
→ docs counter refresh
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
→ analytics report
```

Accepted local validation:

```text
analytics smoke tests = 11 passed
strict analytics validator = green
```

Analytics report focus:

```text
resolved / unresolved reference coverage
reference type distribution
reference field distribution
source-family distribution
top internal referenced papers
top unresolved external references
manual-review samples
metadata-only / no-full-text / no-bibliography caveats
```

Accepted post-normalization counters remain:

```text
nodes_count = 529295
edges_count = 745516
paper nodes = 60954
external_reference nodes = 468336
source_family nodes = 5
paper_references_paper edges = 6165
paper_references_external edges = 703234
paper_has_reference_source_family edges = 36117
reference_resolution_ratio = 0.00869
```

Boundary:

```text
analytics report is read-only
analytics reports are derived evidence
analytics does not rebuild graph output
analytics does not rebuild package output
analytics does not approve manual review
analytics does not publish anything
analytics does not change canonical/reconcile/DB/API/UI/retrieval/Qdrant/ranking behavior
analytics does not parse full text, PDFs, or bibliography/reference sections
```

### 4.30 Citation / Reference Graph API Design v0.1

Status: **done / green design-only API contract / no endpoint implementation**

Implemented after the completed local citation/reference graph line, analytics
report, current-state checkpoint, and graph review evidence pack:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection
→ query CLI
→ docs counter refresh
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
→ analytics report
→ graph review evidence pack
→ API design contract
```

Accepted local validation:

```text
python -m scripts.validation.check_citation_reference_graph_api_design --strict
ok = true
required_failed_count = 0
warning_count = 0

python -m pytest tests/smoke/test_citation_reference_graph_api_design.py -q
4 passed
```

Design contract scope:

```text
possible future citation/reference graph API surface
query modes
response envelope and caveats
error semantics
runtime/storage options
implementation gates
open design questions
```

Boundary:

```text
design-only
no endpoint implementation
no runtime graph loader
no graph DB materialization
no Postgres schema change
no Streamlit graph UI
no GraphRAG
no Qdrant promotion
no retrieval rebuild
no ranking change
no canonical refresh
no publication
```

Required interpretation:

```text
accepted API design does not authorize endpoint implementation by itself
implementation requires a separate accepted implementation plan and gates
manual_review_required = true
manual_review_complete = false
publication_ready = false
```


### 4.31 Graph API Response Fixture Design v0.1

Status: **done / green design-only response fixture contract**

Implemented after the accepted API design checkpoint.

Purpose:

```text
Define expected JSON response, error, pagination, and caveat fixtures for the
candidate citation/reference graph API before endpoint implementation.
```

Accepted scope:

```text
status response fixture
outgoing references response fixture
incoming citations response fixture
external reference linked-papers response fixture
source-family diagnostics fixture
top referenced papers fixture
top external references fixture
unsafe/missing/stale graph error fixtures
manual-review incomplete caveat fixture
response envelope marker checks
```

Boundary:

```text
design-only
no endpoint implementation
no runtime graph loader
no DB materialization
no API behavior change
no UI behavior change
no GraphRAG
no publication
```

### 4.32 Graph Runtime Stale-Version Compatibility Design v0.1

Status: **done / green design-only runtime compatibility contract**

Implemented before the first code slice.

Purpose:

```text
Define how any future graph runtime/package loader must compare graph output
versions against the active canonical corpus, retrieval build, graph manifest,
package metadata, and latest validation reports before serving graph evidence.
```

Accepted compatibility principles:

```text
graph_version = v0.1
canonical_doc_count = 60954
retrieval_build_id = 20260504T164021Z
stale graph outputs must fail closed
unsafe or missing graph package/report state must fail closed
/health remains independent
/search remains independent
Qdrant remains independent
manual_review_complete=false and publication_ready=false must remain visible
```

Boundary:

```text
design-only
no endpoint implementation
no runtime graph loader
no DB materialization
no graph rebuild
no publication
```

### 4.33 Citation / Reference Graph API Implementation Plan v0.1

Status: **done / green implementation-plan-only checkpoint**

Implemented after API design, response fixtures, and runtime compatibility design.

Purpose:

```text
Define a safe implementation sequence for the future citation/reference graph API
without implementing traversal endpoints immediately.
```

Accepted first code slice:

```text
Citation Graph API Disabled Status Endpoint v0.1
```

Plan boundaries:

```text
no traversal endpoints in the first slice
no graph runtime loader in the first slice
no graph DB materialization
no Streamlit graph UI
no GraphRAG
no Qdrant dependency
no /search behavior change
no publication
```

### 4.34 Citation Graph API Disabled Status Endpoint v0.1

Status: **done / green first narrow code slice**

Implemented the first API code slice for Citation / Reference Graph API status.

Current API surface:

```text
GET /citation-graph/status
```

Current semantics:

```text
status_only = true
disabled_by_default = true
feature_flag = ML_RADAR_CITATION_GRAPH_API_ENABLED
graph_runtime_loader = not implemented
graph_traversal_endpoints = not implemented
graph_db_materialization = not implemented
streamlit_graph_evidence_panels = implemented
full_graph_visualization_ui = not implemented
graphrag = not implemented
publication_ready = false
manual_review_required = true
```

Accepted local validation:

```text
python -m py_compile services/api/settings.py services/api/schemas.py services/api/citation_graph_service.py services/api/app.py

ML_RADAR_SEARCH_BACKEND=file:
test_api_citation_graph_status.py = 3 passed
test_api_smoke.py = 7 passed
test_api_reload.py = 4 passed
test_api_search_filters.py = 7 passed
test_api_errors.py = 4 passed

ML_RADAR_SEARCH_BACKEND=db:
test_api_db_smoke.py = 7 passed
test_api_search_db_backend.py = 2 passed
test_api_citation_graph_status.py = 3 passed
```

Boundary:

```text
status endpoint is read-only
status endpoint does not load graph nodes/edges
status endpoint does not expose graph traversal
status endpoint does not mutate canonical truth
status endpoint does not mutate graph output/package/reports
status endpoint does not mutate Postgres
status endpoint does not change /search
status endpoint does not change Discovery API
status endpoint does not require Qdrant
status endpoint does not publish anything
```




### 4.35 Citation Graph Status Compatibility Probe v0.1

Status: **done / green second narrow code slice**

Implemented the read-only compatibility/status probe for the existing
`GET /citation-graph/status` endpoint.

Current API surface remains:

```text
GET /citation-graph/status
```

Current semantics:

```text
status_only = true
compatibility_probe = implemented
read_only = true
disabled_by_default = true
feature_flag = ML_RADAR_CITATION_GRAPH_API_ENABLED
graph_runtime_loader = not implemented
graph_traversal_endpoints = not implemented
graph_db_materialization = not implemented
streamlit_graph_evidence_panels = implemented
full_graph_visualization_ui = not implemented
graphrag = not implemented
publication_ready = false
manual_review_required = true
```

When `ML_RADAR_CITATION_GRAPH_API_ENABLED=false`, the endpoint reports disabled
status:

```text
runtime_enabled = false
available = false
error_code = graph_runtime_not_enabled
```

When `ML_RADAR_CITATION_GRAPH_API_ENABLED=true`, the endpoint probes local graph
artifacts and validation reports read-only. It may report:

```text
graph_artifacts_not_found
graph_artifacts_invalid
graph_artifacts_unsafe
graph_version_unsupported
graph_canonical_baseline_mismatch
graph_package_stale
graph_manual_review_incomplete
```

Compatible local-inspection state means:

```text
runtime_enabled = true
available = true
safe_to_serve_locally = true
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

Important interpretation:

```text
manual_review_complete=false does not fail local status compatibility;
it remains a caveat and publication/public-exposure blocker.
```

Accepted local validation:

```text
python -m py_compile services/api/schemas.py services/api/citation_graph_service.py tests/integration/test_api_citation_graph_status.py
test_api_citation_graph_status.py = 6 passed
ML_RADAR_SEARCH_BACKEND=file test_api_smoke.py = 7 passed
git diff --check = passed, CRLF warnings only on Windows
```

Boundary:

```text
status compatibility probe is read-only
status compatibility probe does not load graph nodes/edges as a query store
status compatibility probe does not expose graph traversal
status compatibility probe does not mutate canonical truth
status compatibility probe does not mutate graph output/package/reports
status compatibility probe does not mutate Postgres
status compatibility probe does not change /search
status compatibility probe does not change Discovery API
status compatibility probe does not require Qdrant
status compatibility probe does not publish anything
```


### 4.36 Citation Graph Fixture Store v0.1

Status: **done / green internal read-only fixture-backed query core**

Implemented after the disabled status endpoint and status compatibility probe:

```text
GET /citation-graph/status
→ status compatibility probe
→ internal fixture-backed CitationGraphStore
```

Implemented files:

```text
services/api/citation_graph_store.py
tests/fixtures/citation_graph_v0_1/
tests/smoke/test_citation_graph_fixture_store.py
```

Current store methods:

```text
graph_summary
outgoing_references
incoming_citations
external_reference_papers
source_family_diagnostics
top_referenced_papers
top_external_references
```

Accepted local validation:

```text
python -m py_compile services/api/citation_graph_store.py tests/smoke/test_citation_graph_fixture_store.py
test_citation_graph_fixture_store.py = 7 passed
test_api_citation_graph_status.py = 6 passed
```

Boundary:

```text
fixture store is internal
fixture store is read-only
fixture store is not wired to FastAPI traversal routes
fixture store is not a runtime loader over the full local graph
fixture store does not change /citation-graph/status
fixture store does not change /search, /health, /runtime, Discovery API, DB, Qdrant, Streamlit, or ranking
fixture store does not implement GraphRAG
fixture store does not publish anything
```


### 4.37 Citation Graph Outgoing References Endpoint v0.1

Status: **done / green first narrow read-only traversal endpoint**

Implemented after the internal fixture store and docs sync:

```text
GET /citation-graph/status
→ status compatibility probe
→ internal fixture-backed CitationGraphStore
→ GET /citation-graph/papers/{canonical_id}/references
```

Implemented files:

```text
services/api/app.py
services/api/schemas.py
tests/integration/test_api_citation_graph_references.py
tests/integration/test_api_citation_graph_status.py
```

Current endpoint behavior:

```text
feature flag disabled -> 503 graph_runtime_not_enabled
compatible local graph -> 200 graph/query/items/page/caveats
unknown canonical_id -> 404 canonical_id_not_found
limit above configured max -> 400 graph_result_limit_exceeded
missing/incompatible graph -> 503 graph_artifacts_* / graph_*_mismatch
```

Accepted local validation:

```text
python -m py_compile services/api/app.py services/api/schemas.py services/api/citation_graph_store.py tests/integration/test_api_citation_graph_references.py tests/integration/test_api_citation_graph_status.py
test_api_citation_graph_references.py = 15 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py = 7 passed
git diff --check = passed, CRLF warnings only on Windows
```

Boundary:

```text
outgoing references endpoint is read-only
outgoing references endpoint is feature-flagged and compatibility-gated
outgoing references endpoint may expose resolved paper references and unresolved external_reference evidence
external-reference papers endpoint is implemented
source-family endpoint, top-referenced-papers endpoint, and top-external-references endpoint are implemented
full graph runtime loader is not implemented
graph DB materialization is not implemented
Streamlit graph UI is not implemented
GraphRAG is not implemented
/search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, and publication state are unchanged
```


### 4.38 Citation Graph Traversal API Checkpoint v0.1


Status: **active docs-only local-inspection checkpoint**

This checkpoint freezes the current narrow citation/reference graph API surface as
a stable local-inspection block before adding any further traversal endpoint.

Implemented and checkpointed routes:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
```

Checkpointed behavior:

```text
status endpoint = compatibility/status surface
outgoing references endpoint = resolved paper references + unresolved external_reference evidence
incoming citations endpoint = resolved internal paper_references_paper edges only
response envelope = graph/query/items/page/caveats
disabled feature flag = fail closed with graph_runtime_not_enabled
unknown canonical_id = canonical_id_not_found
limit above max = graph_result_limit_exceeded
missing/incompatible graph artifacts = graph_artifacts_* / graph_*_mismatch
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

Checkpoint validation evidence:

```text
test_api_citation_graph_references.py = 15 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py with ML_RADAR_SEARCH_BACKEND=file = 7 passed
manual live API check = green for status, references, citations, unknown ids, and limit guards
```

Boundary:

```text
checkpoint is docs/regression-hardening only
no new endpoint is added
external-reference papers endpoint = implemented
source-family endpoint = implemented
top-referenced-papers endpoint = implemented
top-external-references endpoint = implemented
full graph runtime loader = not implemented
graph DB materialization = not implemented
Streamlit graph UI = not implemented
GraphRAG = not implemented
/search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, and publication state = unchanged
```


### 4.39 Source Observation Materialization Operational Promotion v0.1

Status: **done / green operational promotion / rollback retained**

Implemented after the source-observation materialization identity slice:

```text
validated candidate materialization
→ read-only preflight
→ checked operational and candidate dumps
→ controlled database-name swap
→ post-promotion validation
→ DB / artifact / parity / Artifact API product gates
```

Accepted evidence:

```text
source_documents = 88,178
canonical_source_links = 88,037
resolved_links = 88,037
non_contributing_source_observations = 141
preflight = 24 / 24
backup-required preflight = 28 / 28
post-promotion = 29 / 29
promotion validator tests = 10 passed
```

Rollback state:

```text
rollback database = ml_radar_pre_source_identity_v01_20260722t101620z
rollback source_documents = 70,244
operational and candidate dumps = retained and SHA-256 recorded
legacy database drop = not performed
```

Boundary:

```text
no canonical ID or reconcile change
no retrieval or embedding rebuild
no Qdrant change
no artifact-policy change
no graph/ranking/API/UI behavior change
no publication action
```

## 5. Current active direction

### 5.0 Current immediate direction after field-level contract completion

Completed:

```text
Field-Level Canonical Provenance Contract v0.1
canonical fields classified = 61 / 61
static validator = 99 / 99
contract smoke tests = 8 passed
related reconciliation regression = 38 passed
```

Current next slice:

```text
Field-Level Canonical Provenance Evidence Builder v0.1
```

The builder should generate bounded, read-only evidence over deterministic
fixtures and selected audit samples. It must reuse the accepted identities:

```text
source_observation_id = physical source observation identity
canonical_id = paper identity
doc_id = legacy diagnostic only
field evidence record id = derived evidence identity only
```

It must not mutate canonical documents, run a stable-corpus reconcile, add a new
serving truth, alter Postgres, rebuild retrieval, promote Qdrant, change ranking,
expand graph runtime, or publish data. Full-corpus evidence generation is not
authorized in the bounded builder slice.

The rejected public metadata release remains a separate governance track. A
Semantic Scholar exclusion/permission remediation must not be mixed into this
architecture slice.

### 5.1 Citation Graph Top External References Endpoint Docs Sync v0.1

Status: **completed docs synchronization after top-external-references endpoint**

Goal:

```text
Synchronize shared docs after adding the sixth narrow local-inspection graph diagnostics endpoint.
```

Current accepted API state:

```text
GET /citation-graph/status = implemented
GET /citation-graph/papers/{canonical_id}/references = implemented
GET /citation-graph/papers/{canonical_id}/citations = implemented
GET /citation-graph/external-references/{reference_id}/papers = implemented
GET /citation-graph/source-families = implemented
GET /citation-graph/top-referenced-papers = implemented
GET /citation-graph/top-external-references = implemented
full graph runtime loader = not implemented
```

Docs-sync scope:

- document the sixth narrow diagnostics endpoint;
- confirm that top external references are unresolved external-reference diagnostics only;
- record manual live API validation for top-external-references success and limit guard;
- preserve the boundary against full graph runtime loading, GraphRAG, graph DB, publication, and `/search` changes.

Boundary:

```text
docs/checkpoint sync only
no graph rebuild
no package rebuild
no additional API endpoint implementation beyond already merged top-external-references route
no full runtime graph loader
no GraphRAG
no Qdrant promotion
no publication
```

Next safe directions:

1. **Citation Graph Traversal API Checkpoint v0.3** — checkpoint over the seven implemented graph routes.
2. **Regression / DoD hardening** — optional gates and accepted-checkpoint validation wiring.
3. **Graph API endpoint contract cleanup** — if app.py route helpers become too large, extract a small query service without changing behavior.



### 5.2 Citation Graph Traversal API Checkpoint v0.3

Status: **current docs/regression-hardening checkpoint**

Purpose:

```text
Freeze the implemented seven-route citation graph API block after the paired top-reference diagnostics endpoints.
```

Checkpointed routes:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

This slice is deliberately documentation/regression-hardening only:

```text
no new endpoint
no graph runtime loader
no graph DB materialization
no Streamlit graph UI
no GraphRAG
no /search, Qdrant, ranking, canonical, DB, retrieval, graph-output, package, or publication behavior change
```

After this checkpoint, the preferred direction is regression/DoD hardening, not
continued graph API expansion.


### 5.3 Citation Graph API Regression DoD Wiring v0.1

Status: **completed opt-in DoD wiring slice**

Purpose:

```text
Wire the accepted Citation Graph API regression report into the refresh Definition of Done aggregator as an optional required gate.
```

Implemented gate:

```text
python -m scripts.update.check_refresh_definition_of_done --require-citation-graph-api-regression
```

Required report:

```text
artifacts/reports/validation/citation_graph_api_regression_latest.json
```

Required-gate checks:

```text
citation_graph_api_regression_check_exists = true
citation_graph_api_regression_check_ok = true
citation_graph_api_regression_required_failed_count_zero = true
citation_graph_api_regression_routes_count_is_7 = true
citation_graph_api_regression_traversal_routes_count_is_6 = true
citation_graph_api_regression_current_routes_checkpointed = true
citation_graph_api_regression_runtime_loader_not_implemented = true
citation_graph_api_regression_publication_not_ready = true
citation_graph_api_regression_manual_review_required = true
```

Boundary:

```text
DoD wiring only
does not run graph endpoints
does not rebuild graph output
does not write graph reports directly
does not enable the citation graph API
does not implement full graph runtime loader
does not add graph DB materialization
does not add Streamlit graph UI
does not implement GraphRAG
does not change /search, Qdrant, ranking, canonical truth, DB, retrieval, graph-output, package, or publication behavior
```



### 5.4 Graph API / Streamlit Productization Design v0.1

Status: **current design-only productization slice**

Purpose:

```text
Define how the accepted graph evidence surfaces should be consumed by Streamlit
without adding new API endpoints, graph runtime loaders, graph DB materialization,
GraphRAG, or UI code in this slice.
```

Accepted starting point:

```text
Citation Graph API = implemented seven-route local-inspection API block
Citation Graph API regression = implemented and wired into optional DoD
Streamlit UI = thin API client
Paper–Artifact evidence = already available through Artifact API and paper workspace artifact surfaces
```

Planned Streamlit rollout order:

```text
1. Citation Graph Streamlit Status Panel v0.1
   - consume GET /citation-graph/status only
   - show runtime_enabled / available / safe_to_serve_locally
   - show manual_review_required and publication_ready=false caveats

2. Citation Graph Paper Workspace Panel v0.1
   - consume GET /citation-graph/papers/{canonical_id}/references
   - consume GET /citation-graph/papers/{canonical_id}/citations
   - render evidence tables, not graph-as-truth visualization

3. Citation Graph Diagnostics UI v0.1
   - consume GET /citation-graph/source-families
   - consume GET /citation-graph/top-referenced-papers
   - consume GET /citation-graph/top-external-references
   - label top counts as diagnostics, not global citation metrics

4. Citation Graph External Reference Lookup UI v0.1
   - consume GET /citation-graph/external-references/{reference_id}/papers
   - handle URL encoding and unknown external references explicitly

5. Paper–Artifact Graph API Design v0.1, if needed
   - only if existing Artifact API surfaces do not cover needed graph evidence
```

Paper–Artifact Graph productization rule:

```text
Do not add a parallel paper-artifact graph API while the existing Artifact API
already serves paper -> artifact and artifact -> paper evidence.
First extend Streamlit over existing /artifacts and /documents/{canonical_id}/artifacts surfaces.
Only design a dedicated Paper–Artifact Graph API if a concrete UI/use-case gap remains.
```

Boundary:

```text
design-only
no Streamlit code change
no API endpoint change
no graph output/package/report rebuild
no full graph runtime loader
no graph DB materialization
no NetworkX/Neo4j/GraphRAG runtime
no Qdrant promotion
no /search or ranking behavior change
no canonical/reconcile change
no publication
```


### 5.5 Citation Graph Streamlit Status Panel v0.1

Status: **active first UI code slice**

Purpose:

```text
Add the first safe Streamlit productization surface for the accepted Citation Graph API:
a status-only panel that consumes GET /citation-graph/status.
```

Implemented UI behavior:

```text
Streamlit calls /citation-graph/status through FastAPI.
The panel renders runtime_enabled, available, safe_to_serve_locally, and runtime_loader_implemented.
The panel exposes manual_review_required / publication_ready caveats when present.
The panel stores its response in citation_graph_status_payload session state.
The panel does not fetch references, citations, source families, top referenced papers, or top external references.
```

Validation hook:

```text
scripts/validation/check_streamlit_discovery_ui.py checks citation_graph_status_ui_snippets_present.
```

Boundary:

```text
status panel only
no graph traversal UI
no citation/reference evidence tables yet
no external-reference lookup UI
no source-family/top-reference diagnostics UI yet
no graph visualization
no direct Streamlit reads from data/graphs/*
no CitationGraphStore import from Streamlit
no NetworkX/Neo4j/GraphRAG runtime
no full graph runtime loader
no graph DB materialization
no API endpoint change
no graph output/package/report rebuild
no canonical/reconcile/retrieval/Qdrant/Postgres/ranking/publication change
```


### 5.5 Citation Graph Paper Workspace Panel v0.1

Status: **active UI code slice**

Purpose:

```text
Expose selected-paper citation/reference evidence in Streamlit Paper workspace by calling the already implemented Citation Graph API traversal endpoints.
```

Implemented/allowed UI behavior in this slice:

```text
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
render outgoing references and incoming resolved citations as evidence tables
preserve metadata-only / not-complete-citation-index / manual-review / publication caveats
```

Explicit non-goals:

```text
no source-family diagnostics UI
no top-referenced/top-external-reference diagnostics UI
no external-reference lookup UI
no graph visualization
no direct Streamlit reads from data/graphs/*
no CitationGraphStore import from Streamlit
no NetworkX / Neo4j / GraphRAG
no full graph runtime loader
no graph DB materialization
no canonical/retrieval/Qdrant/Postgres/ranking/publication changes
```

## 6. Near-term roadmap

### 6.1 Graph Review Evidence Pack v0.1

Status: **done / green local read-only evidence pack / not published**

Purpose:

```text
Bundle manual-review-relevant evidence from both completed local graph lines
without publishing graph packages or exposing graph runtime/API/UI surfaces.
```

Expected inputs:

- Citation / Reference Graph line checkpoint;
- Citation / Reference Graph manual-review checklist;
- Citation / Reference Graph release candidate and package reports;
- Citation / Reference Graph inspection/query/analytics reports;
- Paper–Artifact Graph line checkpoint;
- Paper–Artifact Graph manual-review checklist;
- Paper–Artifact Graph release candidate and package reports;
- Paper–Artifact Graph inspection/query/analytics reports.

Expected output:

```text
local JSON/Markdown review evidence pack
publication_ready = false
manual_review_required = true
```

Non-goals:

```text
no publication
no package rebuild unless explicitly requested
no manual approval automation
no public graph traversal API
no Streamlit graph UI
no runtime graph database
no GraphRAG
no canonical/reconcile changes
no retrieval/Qdrant/ranking changes
```

### 6.2 Citation / Reference Graph API Design v0.1

Status: **done / green design-only API contract / no endpoint implementation**

Purpose:

```text
Design possible future API semantics before implementing any citation/reference graph endpoint.
```

This was completed as a design-only slice. It does not authorize endpoint
implementation by itself.

Questions to resolve:

- which citation/reference graph queries are safe to expose;
- whether graph output remains local/offline or becomes a serving artifact;
- how to prevent graph from being interpreted as canonical truth;
- how to document unresolved references and source-family evidence;
- how to expose metadata-only/no-full-text/no-bibliography caveats;
- whether endpoint output should mirror Query CLI semantics;
- whether DB materialization is required before API exposure;
- which validators must be green before implementation.

Non-goals:

```text
no endpoint implementation
no Streamlit graph UI
no runtime graph database
no GraphRAG
no DB materialization
no publication
```

### 6.3 Graph API Response Fixture Design v0.1

Status: **done / green design-only slice**.

Purpose:

```text
Define expected JSON response, error, pagination, and caveat fixtures for the
candidate citation/reference graph API before any endpoint implementation.
```

Possible scope:

- status response fixture;
- outgoing references response fixture;
- incoming citations response fixture;
- external reference linked-papers response fixture;
- source-family diagnostics fixture;
- top referenced papers fixture;
- top external references fixture;
- unsafe/missing graph error fixtures;
- manual-review incomplete caveat fixture;
- response envelope marker checks.

Non-goals:

```text
no endpoint implementation
no runtime graph loader
no DB materialization
no API behavior change
no UI behavior change
no GraphRAG
no publication
```

### 6.4 Graph Runtime Stale-Version Compatibility Design v0.1

Status: **done / green design-only slice**.

Purpose:

```text
Define how future graph runtime/package loaders compare graph output versions
against active canonical corpus, retrieval build, graph manifest, and package
metadata before serving graph evidence.
```

Possible scope:

- accepted graph version markers;
- canonical corpus count/build compatibility;
- graph manifest checksum expectations;
- package/report freshness checks;
- failure semantics for stale or unsafe graph outputs;
- explicit local-only/public exposure distinction.

Non-goals:

```text
no endpoint implementation
no runtime graph loader
no DB materialization
no graph rebuild
no publication
```

### 6.5 Citation Graph Status Compatibility Probe v0.1

Status: **done / green code-adjacent slice**.

Purpose:

```text
Adds a read-only compatibility/status probe for the existing citation/reference
graph output, package, and validation reports. At the time of that slice, all
traversal endpoints remained closed; a later slice implemented only outgoing references.
```

Possible scope:

- check graph output directory presence;
- check graph manifest version;
- check canonical_doc_count and retrieval_build_id compatibility;
- check latest output/inspection/release/package/manual-review/analytics reports;
- report stale/missing/unsafe state through status response;
- fail closed without making /health unhealthy;
- keep /search, Discovery API, DB, Qdrant, ranking, and Streamlit unchanged.

Non-goals:

```text
no outgoing-reference endpoint in the compatibility-probe slice
no graph traversal in the compatibility-probe slice
no graph runtime query service
no DB materialization
no Streamlit graph UI
no GraphRAG
no publication
```


### 6.6 Citation Graph Fixture Store v0.1

Status: **done / green internal store slice**.

Purpose:

```text
Add a read-only file-backed store over a tiny citation/reference graph fixture to
harden query semantics before exposing traversal endpoints. A later slice wires
only outgoing references to a public route.
```

Implemented scope:

```text
load fixture graph files
index outgoing references
index incoming citations
index external_reference -> papers
source-family diagnostics
top referenced papers
top external references
limit/offset validation
unknown ids return found=false
```

Non-goals:

```text
no public traversal endpoint in the fixture-store slice
no full graph runtime loader
no DB materialization
no Streamlit graph UI
no GraphRAG
no publication
```


### 6.7 Citation Graph Outgoing References Endpoint v0.1

Status: **done / green first narrow traversal endpoint slice**.

Purpose:

```text
Expose one read-only, compatibility-gated route for paper outgoing references,
using the existing CitationGraphStore semantics.
```

Implemented endpoint:

```text
GET /citation-graph/papers/{canonical_id}/references
```

Accepted local validation:

```text
test_api_citation_graph_references.py = 15 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py = 7 passed
```

Non-goals:

```text
external-reference papers endpoint = implemented
source-family endpoint = implemented
no top-reference endpoints
no full graph runtime loader
no DB materialization
no Streamlit graph UI
no GraphRAG
no publication
```


### 6.8 Citation Graph Incoming Citations Endpoint v0.1

Status: **done / green second narrow traversal endpoint slice**.

Purpose:

```text
Expose one read-only, compatibility-gated route for incoming resolved internal
citations, using the existing CitationGraphStore semantics.
```

Implemented endpoint:

```text
GET /citation-graph/papers/{canonical_id}/citations
```

Accepted local validation:

```text
test_api_citation_graph_references.py = 15 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py = 7 passed
manual live API check = passed
```

Non-goals:

```text
external-reference papers endpoint = implemented
source-family endpoint = implemented
no top-reference endpoints
no full graph runtime loader
no DB materialization
no Streamlit graph UI
no GraphRAG
no publication
```


### 6.9 Citation Graph External Reference Papers Endpoint v0.1

Status: **done / green third narrow traversal endpoint slice**.

Purpose:

```text
Expose one read-only, compatibility-gated route for papers that reference a given unresolved external_reference node.
```

Implemented endpoint:

```text
GET /citation-graph/external-references/{reference_id}/papers
```

Accepted semantics:

```text
reference_id may be external_reference node id, reference_key, or normalized value
DOI-like normalized values containing `/` require URL encoding
items are canonical papers with paper_references_external edges to the selected external_reference
external references remain unresolved evidence nodes, not publication-grade bibliography entities
```

Accepted local validation:

```text
test_api_citation_graph_references.py = 15 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py = 7 passed
manual live API check = passed for node id, normalized DOI, normalized OpenAlex value, unknown reference, and limit guard
```

Non-goals:

```text
source-family endpoint = implemented
no top-reference endpoints
no full graph runtime loader
no DB materialization
no Streamlit graph UI
no GraphRAG
no publication
no /search/Qdrant/ranking/canonical changes
```


### 6.6 Regression / DoD hardening

Potential later validation slice.

Purpose:

```text
Wire accepted checkpoint and graph-review evidence into optional regression/DoD gates
without making optional graph/API/artifact checks mandatory by default.
```

Possible scope:

- add optional accepted-checkpoint validation gate;
- add optional graph-review evidence pack validation gate;
- ensure Artifact API filter checks remain opt-in DB-backed gates;
- preserve current file/DB/Qdrant boundaries;
- improve report naming and failure summaries.

Non-goals:

```text
no canonical refresh
no retrieval rebuild
no graph rebuild
no API behavior change
no UI behavior change
no Qdrant promotion
```

### 6.6 Paper–Artifact Graph API Design v0.1

Potential later design-only slice.

Purpose:

```text
Design possible future API semantics before implementing any paper-artifact graph endpoint.
```

Questions to resolve:

- which graph queries are safe to expose;
- whether graph output remains local/offline or becomes a serving artifact;
- how to prevent graph from being interpreted as canonical truth;
- how to document provenance and trust boundaries;
- whether endpoint output should mirror Query CLI semantics;
- whether API needs additional manual-review/publication gates.

Non-goals:

```text
no endpoint implementation
no Streamlit graph UI
no runtime graph database
no GraphRAG
```

### 6.7 Publication Preparation v0.1

Only after manual review is actually completed.

Purpose:

```text
Prepare a separate publication or external-sharing decision for graph/package candidates.
```

Possible scope:

- publication target selection;
- license and redistribution decision;
- final README limitations;
- release notes;
- archive retention policy;
- explicit public-upload procedure.

Publication must remain a separate PR/slice from validators and local evidence reports.

### 6.8 Deployment Vector Backend Selector Design v1

Purpose:

```text
Design ML_RADAR_VECTOR_BACKEND=file|qdrant as a deployment-level selector.
```

Design principles:

- default remains file;
- one vector backend per deployment;
- no request-level public selector unless separately justified;
- no hidden fallback;
- `/health` semantics explicit;
- strict regression gate required;
- rollback path documented.

Non-goals:

- do not enable Qdrant by default;
- do not silently switch `/search`;
- do not remove file dense as reference.

### 6.9 Public Qdrant Promotion v1

Prerequisites:

- deployment selector design accepted;
- regression gate green;
- failure semantics accepted;
- rollback plan accepted;
- API docs updated;
- no fallback ambiguity.

Promotion must be a separate PR.

### 6.10 Ranking / reranking research

Potential future slices:

- cross-encoder reranking study;
- ranking normalization study;
- metadata-quality tie-break study;
- larger relevance labels;
- query-group-specific diagnostics.

The current heuristic ranking must not be promoted without new evidence.

### 6.9 Next retrieval generation

Potential future work:

- stronger scientific embedding model;
- larger Golden Set;
- retrieval rebuild;
- Qdrant rebuild;
- parity/evaluation re-run;
- new retrieval manifest and build-scoped docs.

Any material retrieval rebuild invalidates current build-scoped evidence and requires fresh validators.

### 6.10 Full text / RAG

Future staged path:

```text
full-text acquisition policy
→ text extraction and chunk contract
→ chunk provenance
→ chunk retrieval
→ grounded answer generation
→ citation/evidence checks
```

RAG must not be introduced as an ungrounded chat layer.

### 6.11 Observability and orchestration

Future staged path:

- structured logging;
- metrics;
- Prometheus/Grafana;
- OpenTelemetry/Jaeger or Tempo;
- Airflow;
- Ray;
- Kafka;
- Kubernetes;
- Alembic migrations.

These remain future architecture options, not immediate tasks.


## 7. Work explicitly deferred

Deferred:

```text
public Qdrant promotion
public graph API
Citation / Reference Graph DB/API/UI/runtime exposure
Citation / Reference Graph packaging/publication
Streamlit graph UI
graph runtime / Neo4j / NetworkX runtime
GraphRAG over Paper-Artifact Graph
deployment-level vector backend selector implementation
Qdrant-backed public hybrid
Qdrant-backed similar-paper migration
filter pushdown into Qdrant
new embedding model
retrieval rebuild
larger Golden Set expansion
dataset publication
Neo4j / graph runtime
GraphRAG
NER/entity extraction promotion
full-text RAG
Airflow / Kafka / Kubernetes
production observability stack
```

---

## 8. Operating principles

```text
Prefer evidence-backed vertical slices.
Do not change retrieval defaults by intuition.
Do not conflate public API modes with internal backend implementations.
Do not treat Qdrant availability as a reason to promote Qdrant.
Do not treat generated reports as source truth.
Do not treat graph contracts as generated graph artifacts.
Do not let docs drift from accepted behavior.
```

The project should remain a coherent research-discovery platform rather than a
collection of unrelated infrastructure experiments.

<!-- PAPER_ARTIFACT_GRAPH_BUILDER_V01_START -->
## Paper-Artifact Graph Builder v0.1

Status: implemented local derived builder.

This slice builds the first local derived paper-artifact graph artifact from accepted file-backed layers.

Implemented components:

- shared trusted-link helper: `radar_core/artifacts/trusted_links.py`
- builder execution config: `configs/paper_artifact_graph_builder.yaml`
- builder config validator: `scripts/validation/check_paper_artifact_graph_builder_config.py`
- graph builder: `scripts/export/build_paper_artifact_graph.py`
- graph output validator: `scripts/validation/check_paper_artifact_graph_output.py`
- smoke tests for helper, config, builder, and output validator
- generated output ignored via `/data/graphs/`

Validated local graph output:

- nodes: `68385`
- edges: `163757`
- papers: `60954`
- artifacts: `7336`
- providers: `10`
- source families: `5`
- topic clusters: `80`
- trusted paper-artifact edges: `7430`
- topic assignment edges: `60954`

Boundaries preserved:

- graph is derived, not canonical truth
- graph is not a reconcile input
- no live DB dependency
- no Qdrant/retrieval/ranking changes
- no API/UI changes
- no latest pointer
- no global `paper_artifact_links_latest.jsonl` bridge
- generated graph output is not committed

See: `docs/paper_artifact_graph_builder_v0.md`.
<!-- PAPER_ARTIFACT_GRAPH_BUILDER_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_INSPECTION_V01_START -->
## Paper-Artifact Graph Inspection v0.1

Status: implemented local read-only inspection layer.

This slice adds a compact QA/reporting layer over the generated Paper-Artifact Graph Builder v0.1 output.

It validates that the generated graph is not only structurally valid, but also meaningful enough for human inspection:

- provider distribution over artifact nodes
- provider distribution over paper-artifact edges
- source-family distribution
- papers with trusted artifacts
- artifacts linked to multiple papers
- topic clusters with artifact-ready papers
- sample paper -> artifact edges
- sample topic -> paper -> artifact paths

Accepted local inspection result:

```text
ok=True
required_failed_count=0
nodes_count=68385
edges_count=163757
papers_with_artifacts_count=6673
topic_clusters_with_artifact_ready_papers_count=80
```

Boundary:

- read-only inspection/report layer
- no graph rebuild
- no canonical truth changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- generated reports are not committed

See: `docs/paper_artifact_graph_inspection_v0.md`.
<!-- PAPER_ARTIFACT_GRAPH_INSPECTION_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_QUERY_CLI_V01_START -->
## Paper-Artifact Graph Query CLI v0.1

Status: implemented local read-only query CLI.

This slice adds an offline command-line query layer over the generated Paper-Artifact Graph Builder v0.1 output.

It supports:

- paper → artifacts / topic clusters / source families
- artifact → linked papers / providers
- provider → top artifacts ranked by linked paper count
- topic cluster → artifact-ready papers

Implemented files:

- `scripts/graph/__init__.py`
- `scripts/graph/query_paper_artifact_graph.py`
- `tests/smoke/test_paper_artifact_graph_query_cli.py`
- `docs/paper_artifact_graph_query_cli_v0.md`

Accepted local validation:

```text
python -m py_compile scripts/graph/query_paper_artifact_graph.py
python -m pytest tests/smoke/test_paper_artifact_graph_query_cli.py -q
7 passed
```

Accepted local graph-query examples:

```text
provider=github
artifacts=5953
paper_artifact_links=6019

topic_cluster=7
papers=465
artifact_ready_papers=21
paper_artifact_links=21
```

Boundary:

- read-only CLI over generated graph output
- no graph rebuild
- no canonical truth changes
- no reconcile input
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no generated reports
- no Neo4j/NetworkX/GraphRAG runtime

See: `docs/paper_artifact_graph_query_cli_v0.md`.
<!-- PAPER_ARTIFACT_GRAPH_QUERY_CLI_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_RELEASE_CANDIDATE_V01_START -->
## Paper-Artifact Graph Release Candidate v0.1

Status: implemented local read-only release-candidate readiness gate.

This slice adds a release-candidate style validator over the already generated Paper-Artifact Graph Builder v0.1 output.

It answers:

```text
Can the generated graph output be treated as a local reviewable candidate artifact?
```

Implemented files:

- `scripts/validation/check_paper_artifact_graph_release_candidate.py`
- `tests/smoke/test_paper_artifact_graph_release_candidate.py`
- `docs/paper_artifact_graph_release_candidate_v0.md`

Generated reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_release_candidate_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_release_candidate_<run_ts>.md`

Accepted local validation:

```text
python -m py_compile scripts/validation/check_paper_artifact_graph_release_candidate.py
python -m pytest tests/smoke/test_paper_artifact_graph_release_candidate.py -q
python -m scripts.validation.check_paper_artifact_graph_release_candidate --strict
```

Accepted result:

```text
5 passed
ok=True
required_failed_count=0
warning_count=0
```

The validator checks:

- graph output files exist
- graph JSON/JSONL files are readable
- manifest safety flags preserve derived-layer boundaries
- builder input mode is file
- data quality summary is ok
- duplicate node/edge IDs are absent
- accepted graph v0.1 counters match
- checksums match
- inspection report is ok in strict mode
- GitHub provider smoke counters match accepted diagnostics

Expected release-candidate verdict:

```text
technical_graph_candidate_ready=true
manual_review_required=true
publication_ready=false
publication_block_reason=manual_review_not_completed
```

Boundary:

- read-only validator over generated graph output
- no graph rebuild
- no canonical truth changes
- no reconcile input changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no dataset publication
- no generated graph/package files committed
- no Neo4j/NetworkX/GraphRAG runtime

See: `docs/paper_artifact_graph_release_candidate_v0.md`.
<!-- PAPER_ARTIFACT_GRAPH_RELEASE_CANDIDATE_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_PACKAGE_V01_START -->
## Paper-Artifact Graph Package v0.1

Status: implemented local package candidate layer.

This slice adds a conservative local packaging step for the already generated and already release-candidate-validated Paper-Artifact Graph Builder v0.1 output.

It answers:

```text
Can the local graph candidate be packaged into a portable local archive without changing graph data or runtime behavior?
```

Implemented files:

- `configs/paper_artifact_graph_package.yaml`
- `scripts/export/package_paper_artifact_graph.py`
- `scripts/validation/check_paper_artifact_graph_package.py`
- `tests/smoke/test_paper_artifact_graph_package.py`
- `docs/paper_artifact_graph_package_v0.md`

Generated local package output, not committed:

- `data/graphs/paper_artifact_graph/packages/v0.1/paper_artifact_graph_v0.1.zip`
- `data/graphs/paper_artifact_graph/packages/v0.1/package_manifest.json`
- `data/graphs/paper_artifact_graph/packages/v0.1/README.md`
- `data/graphs/paper_artifact_graph/packages/v0.1/checksums.txt`

Accepted local validation:

```text
python -m py_compile scripts/export/package_paper_artifact_graph.py
python -m py_compile scripts/validation/check_paper_artifact_graph_package.py
python -m pytest tests/smoke/test_paper_artifact_graph_package.py -q
python -m scripts.export.package_paper_artifact_graph --dry-run
python -m scripts.export.package_paper_artifact_graph --force
python -m scripts.validation.check_paper_artifact_graph_package --strict
```

Accepted result:

```text
5 passed
package build ok=True
included_files_count=9
zip_size_bytes=14930380
package validator ok=True
required_failed_count=0
warning_count=0
```

Archive contents:

```text
paper_artifact_graph_v0.1/nodes.jsonl
paper_artifact_graph_v0.1/edges.jsonl
paper_artifact_graph_v0.1/schema.json
paper_artifact_graph_v0.1/manifest.json
paper_artifact_graph_v0.1/data_quality_summary.json
paper_artifact_graph_v0.1/README.md
paper_artifact_graph_v0.1/checksums.txt
paper_artifact_graph_v0.1/validation/paper_artifact_graph_release_candidate_latest.json
paper_artifact_graph_v0.1/validation/paper_artifact_graph_release_candidate_latest.md
```

Boundary:

- local package candidate only
- no graph rebuild
- no canonical truth changes
- no reconcile input changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no dataset publication
- no latest pointer
- no graph runtime
- generated package output is not committed
- no Neo4j/NetworkX/GraphRAG runtime

See: `docs/paper_artifact_graph_package_v0.md`.
<!-- PAPER_ARTIFACT_GRAPH_PACKAGE_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_LINE_CHECKPOINT_V01_START -->
## Paper-Artifact Graph Line Checkpoint v0.1

Status: implemented local read-only line checkpoint.

This slice adds a final read-only checkpoint gate over the completed local Paper-Artifact Graph v0.1 line.

It answers:

```text
Is the whole local paper-artifact graph line internally complete and safe to treat as a closed checkpoint?
```

Implemented files:

- `configs/paper_artifact_graph_line_checkpoint.yaml`
- `scripts/validation/check_paper_artifact_graph_line_checkpoint.py`
- `tests/smoke/test_paper_artifact_graph_line_checkpoint.py`
- `docs/paper_artifact_graph_line_checkpoint_v0.md`

Generated reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_line_checkpoint_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_line_checkpoint_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_line_checkpoint_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_line_checkpoint_<run_ts>.md`

Accepted local validation:

```text
python -m py_compile scripts/validation/check_paper_artifact_graph_line_checkpoint.py
python -m pytest tests/smoke/test_paper_artifact_graph_line_checkpoint.py -q
python -m scripts.validation.check_paper_artifact_graph_line_checkpoint --strict
```

Accepted result:

```text
4 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 14,
  "warning_count": 0
}
```

The checkpoint covers:

- contract
- builder
- output validator
- inspection
- query CLI
- release-candidate gate
- package builder/validator

Boundary:

- read-only checkpoint only
- no graph rebuild
- no package rebuild
- no canonical truth changes
- no reconcile input changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no dataset publication
- no latest pointer
- no graph runtime
- generated checkpoint reports are not committed
- no Neo4j/NetworkX/GraphRAG runtime

See: `docs/paper_artifact_graph_line_checkpoint_v0.md`.
<!-- PAPER_ARTIFACT_GRAPH_LINE_CHECKPOINT_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_MANUAL_REVIEW_V01_START -->
## Paper-Artifact Graph Manual Review Checklist v0.1

Status: implemented local read-only manual-review gate.

This slice adds a structured manual-review checklist and validator over the already completed local Paper-Artifact Graph v0.1 line and package candidate.

It answers:

```text
What must a human review before the Paper-Artifact Graph v0.1 package can be published, shared externally, or exposed through a public runtime/API/UI surface?
```

Tracked files:

- `configs/paper_artifact_graph_manual_review.yaml`
- `scripts/validation/check_paper_artifact_graph_manual_review.py`
- `tests/smoke/test_paper_artifact_graph_manual_review.py`
- `docs/paper_artifact_graph_manual_review_v0.md`

Generated reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_manual_review_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_manual_review_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_manual_review_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_manual_review_<run_ts>.md`

Accepted local validation:

```text
python -m py_compile scripts/validation/check_paper_artifact_graph_manual_review.py
python -m pytest tests/smoke/test_paper_artifact_graph_manual_review.py -q
python -m scripts.validation.check_paper_artifact_graph_manual_review --strict
```

Accepted result:

```text
9 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 20,
  "warning_count": 0
}
```

Key v0.1 semantics:

```text
pending categories block publication
pending categories do not fail the validator
```

Default verdict:

```text
manual_review_required=true
manual_review_complete=false
publication_ready=false
publication_block_reason=manual_review_not_completed
```

Boundary:

- read-only manual-review validator only
- no publication
- no graph rebuild
- no package rebuild
- no canonical truth changes
- no reconcile input changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no latest pointer
- no graph runtime
- no Neo4j/NetworkX/GraphRAG runtime
- no trusted-link policy redefinition

See: `docs/paper_artifact_graph_manual_review_v0.md`.
<!-- PAPER_ARTIFACT_GRAPH_MANUAL_REVIEW_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_ANALYTICS_V01_START -->
## Paper-Artifact Graph Analytics v0.1

Status: implemented local read-only analytics/report layer.

This slice adds a compact analytics report over the already generated Paper-Artifact Graph v0.1 output.

It answers:

```text
What does the local Paper-Artifact Graph v0.1 candidate look like in terms of provider coverage, artifact readiness, source-family evidence, topic-cluster coverage, and multi-paper artifact structure?
```

Tracked files:

- `configs/paper_artifact_graph_analytics.yaml`
- `scripts/validation/check_paper_artifact_graph_analytics.py`
- `tests/smoke/test_paper_artifact_graph_analytics.py`
- `docs/paper_artifact_graph_analytics_v0.md`

Generated reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_analytics_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_analytics_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_analytics_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_analytics_<run_ts>.md`

Accepted local validation:

```text
python -m py_compile scripts/validation/check_paper_artifact_graph_analytics.py
python -m pytest tests/smoke/test_paper_artifact_graph_analytics.py -q
python -m scripts.validation.check_paper_artifact_graph_analytics --strict
```

Accepted result:

```text
8 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 40,
  "warning_count": 0
}
```

The report covers:

```text
node and edge counts
node and edge type counts
papers with trusted artifacts
artifacts linked to papers
multi-paper artifacts
isolated artifacts
provider distribution over artifact nodes
provider distribution over paper-artifact links
source-family distribution
topic-cluster artifact-ready paper coverage
top multi-paper artifacts
small sample IDs for manual inspection
```

Boundary:

- read-only analytics/report layer only
- no publication
- no graph rebuild
- no package rebuild
- no canonical truth changes
- no reconcile input changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no latest pointer
- no graph runtime
- no Neo4j/NetworkX/GraphRAG runtime
- no trusted-link policy redefinition
- no manual approval state change

See: `docs/paper_artifact_graph_analytics_v0.md`.
<!-- PAPER_ARTIFACT_GRAPH_ANALYTICS_V01_END -->

<!-- CITATION_REFERENCE_GRAPH_CONTRACT_V01_START -->
## Citation / Reference Graph Contract v0.1

Status: implemented local contract-only derived citation/reference graph definition.

This slice defines the first contract for a future citation/reference graph line separate from Paper-Artifact Graph v0.1.

It answers:

```text
What should a derived paper→paper and paper→external-reference graph look like before any builder, DB materialization, API, UI, graph runtime, or GraphRAG work begins?
```

Tracked files:

- `configs/citation_reference_graph.yaml`
- `scripts/validation/check_citation_reference_graph_contract.py`
- `tests/smoke/test_citation_reference_graph_contract.py`
- `docs/citation_reference_graph_v0.md`

Generated reports, not committed:

- `artifacts/reports/validation/citation_reference_graph_contract_latest.json`
- `artifacts/reports/validation/citation_reference_graph_contract_latest.md`
- `artifacts/reports/validation/history/citation_reference_graph_contract_<run_ts>.json`
- `artifacts/reports/validation/history/citation_reference_graph_contract_<run_ts>.md`

Accepted local validation:

```text
python -m py_compile scripts/validation/check_citation_reference_graph_contract.py
python -m pytest tests/smoke/test_citation_reference_graph_contract.py -q
python -m scripts.validation.check_citation_reference_graph_contract --strict
python -m scripts.validation.check_citation_reference_graph_contract --strict --check-paths
```

Accepted result:

```text
10 passed

{
  "ok": true,
  "required_failed_count": 0,
  "total_checks": 48,
  "warning_count": 0
}

{
  "ok": true,
  "required_failed_count": 0,
  "total_checks": 50,
  "warning_count": 0
}
```

Required future node types:

```text
paper
external_reference
source_family
```

Required future edge types:

```text
paper_references_paper
paper_references_external
paper_has_reference_source_family
```

Key v0.1 semantics:

```text
references_count / cited_by_count are diagnostic metadata
explicit reference fields create future graph edge evidence
unresolved references remain external_reference nodes
source_family nodes derive from canonical provenance rows, not source_ids only
```

Boundary:

- contract-only validator and documentation only
- no builder
- no generated graph output
- no package
- no publication
- no manual approval
- no DB materialization
- no DB schema change
- no public graph traversal API
- no Streamlit graph UI
- no NetworkX/Neo4j/GraphRAG runtime
- no canonical refresh/reconcile
- no retrieval rebuild
- no embedding model replacement
- no Qdrant promotion
- no ranking changes

See: `docs/citation_reference_graph_v0.md`.
<!-- CITATION_REFERENCE_GRAPH_CONTRACT_V01_END -->

<!-- CITATION_REFERENCE_GRAPH_BUILDER_V01_START -->
## Citation / Reference Graph Builder v0.1

Status: implemented local file-first derived graph builder and output validator.

This slice builds the first local derived citation/reference graph artifact from the accepted contract and current canonical reference fields.

Tracked files:

- `scripts/export/build_citation_reference_graph.py`
- `scripts/validation/check_citation_reference_graph_output.py`
- `tests/smoke/test_citation_reference_graph_builder.py`
- `tests/smoke/test_citation_reference_graph_output_validator.py`
- `docs/citation_reference_graph_builder_v0.md`

Generated local output, not committed:

- `data/graphs/citation_reference_graph/v0.1/nodes.jsonl`
- `data/graphs/citation_reference_graph/v0.1/edges.jsonl`
- `data/graphs/citation_reference_graph/v0.1/schema.json`
- `data/graphs/citation_reference_graph/v0.1/manifest.json`
- `data/graphs/citation_reference_graph/v0.1/data_quality_summary.json`
- `data/graphs/citation_reference_graph/v0.1/README.md`
- `data/graphs/citation_reference_graph/v0.1/checksums.txt`

Accepted local validation:

```text
python -m py_compile scripts/export/build_citation_reference_graph.py
python -m py_compile scripts/validation/check_citation_reference_graph_output.py
python -m pytest tests/smoke/test_citation_reference_graph_builder.py tests/smoke/test_citation_reference_graph_output_validator.py -q
python -m scripts.export.build_citation_reference_graph --dry-run
python -m scripts.export.build_citation_reference_graph --force
python -m scripts.validation.check_citation_reference_graph_output --strict
```

Accepted result after reference-id normalization fix:

```text
13 passed

builder:
ok = true
nodes_count = 529295
edges_count = 745516

output validator:
ok = true
required_failed_count = 0
total_checks = 36
warning_count = 0
```

Accepted local graph counters:

```text
nodes_count = 529295
edges_count = 745516

paper = 60954
external_reference = 468336
source_family = 5

paper_references_paper = 6165
paper_references_external = 703234
paper_has_reference_source_family = 36117
```

Boundary:

- builder is file-first
- graph output is derived, local, and rebuildable
- graph output is not canonical truth
- graph output must not be used as reconcile input
- unresolved references remain external_reference nodes
- no DB materialization
- no DB schema change
- no public graph traversal API
- no Streamlit graph UI
- no NetworkX/Neo4j/GraphRAG runtime
- no canonical refresh/reconcile
- no retrieval rebuild
- no embedding model replacement
- no Qdrant promotion
- no ranking changes

See: `docs/citation_reference_graph_builder_v0.md`.
<!-- CITATION_REFERENCE_GRAPH_BUILDER_V01_END -->

<!-- CITATION_REFERENCE_GRAPH_INSPECTION_V01_START -->
## Citation / Reference Graph Inspection v0.1

Status: implemented local read-only inspection/report layer.

This slice adds a compact QA/reporting layer over the generated Citation / Reference Graph Builder v0.1 output.

It answers:

```text
What does the local Citation / Reference Graph v0.1 candidate look like in terms of reference resolution, unresolved external references, source-family evidence, and high-level paper/reference connectivity?
```

Tracked files:

- `scripts/validation/check_citation_reference_graph_inspection.py`
- `tests/smoke/test_citation_reference_graph_inspection.py`
- `docs/citation_reference_graph_inspection_v0.md`

Generated reports, not committed:

- `artifacts/reports/validation/citation_reference_graph_inspection_latest.json`
- `artifacts/reports/validation/citation_reference_graph_inspection_latest.md`
- `artifacts/reports/validation/history/citation_reference_graph_inspection_<run_ts>.json`
- `artifacts/reports/validation/history/citation_reference_graph_inspection_<run_ts>.md`

Accepted local validation:

```text
python -m py_compile scripts/validation/check_citation_reference_graph_inspection.py
python -m pytest tests/smoke/test_citation_reference_graph_inspection.py -q
python -m scripts.validation.check_citation_reference_graph_inspection --strict
```

Accepted result:

```text
7 passed

{
  "ok": true,
  "required_failed_count": 0,
  "total_checks": 35,
  "warning_count": 0
}
```

Accepted local inspection counters:

```text
nodes_count = 529295
edges_count = 745516
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference_resolution_ratio = 0.00869
```

The report covers:

```text
resolved versus unresolved reference edges
reference_resolution_ratio
papers with outgoing reference edges
papers with internal reference edges
papers with external reference edges
papers with incoming internal reference edges
papers without outgoing explicit reference edges
reference type distribution
reference field distribution
source-family distribution
top referenced canonical papers
top external references
sample paper→paper edges
sample paper→external_reference edges
```

Boundary:

- read-only inspection/report layer only
- no graph rebuild
- no canonical truth changes
- no reconcile input changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no package
- no publication
- no latest pointer
- no graph runtime
- no Neo4j/NetworkX/GraphRAG runtime

See: `docs/citation_reference_graph_inspection_v0.md`.
<!-- CITATION_REFERENCE_GRAPH_INSPECTION_V01_END -->



<!-- CITATION_REFERENCE_GRAPH_QUERY_CLI_V01_START -->
## Citation / Reference Graph Query CLI v0.1

Status: implemented local read-only offline query CLI.

This slice adds a small offline command-line query surface over the generated Citation / Reference Graph v0.1 output.

Tracked files:

- `scripts/graph/query_citation_reference_graph.py`
- `tests/smoke/test_citation_reference_graph_query_cli.py`
- `docs/citation_reference_graph_query_cli_v0.md`

Accepted local validation:

```text
python -m py_compile scripts/graph/query_citation_reference_graph.py
python -m pytest tests/smoke/test_citation_reference_graph_query_cli.py -q
python -m scripts.graph.query_citation_reference_graph --top-referenced-papers --top-k 5
python -m scripts.graph.query_citation_reference_graph --top-external-references --top-k 5 --format markdown
```

Accepted result:

```text
8 passed
JSON output works
Markdown output works
```

Accepted local graph/query counters:

```text
nodes_count = 529295
edges_count = 745516
paper_references_paper = 6165
paper_references_external = 703234
reference_resolution_ratio = 0.00869
```

Supported selectors:

```text
paper -> outgoing references
paper <- incoming internal citing papers
external_reference -> citing papers
top internal referenced canonical papers
top unresolved external references
source_family -> reference-bearing papers
```

Boundary:

- read-only CLI over generated graph output
- no graph rebuild
- no canonical truth changes
- no reconcile input
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no generated reports by default
- no Neo4j/NetworkX/GraphRAG runtime

See: `docs/citation_reference_graph_query_cli_v0.md`.
<!-- CITATION_REFERENCE_GRAPH_QUERY_CLI_V01_END -->


<!-- CITATION_REFERENCE_GRAPH_PACKAGE_V01_START -->
## Citation / Reference Graph Package v0.1

Status: implemented local package candidate layer.

This slice packages the already generated and already release-candidate-validated Citation / Reference Graph Builder v0.1 output into a local non-public portable archive.

Implemented files:

- `configs/citation_reference_graph_package.yaml`
- `scripts/export/package_citation_reference_graph.py`
- `scripts/validation/check_citation_reference_graph_package.py`
- `tests/smoke/test_citation_reference_graph_package.py`
- `docs/citation_reference_graph_package_v0.md`

Generated local package output, not committed:

- `data/graphs/citation_reference_graph/packages/v0.1/citation_reference_graph_v0.1.zip`
- `data/graphs/citation_reference_graph/packages/v0.1/package_manifest.json`
- `data/graphs/citation_reference_graph/packages/v0.1/README.md`
- `data/graphs/citation_reference_graph/packages/v0.1/checksums.txt`

Accepted local validation:

```text
python -m py_compile scripts/export/package_citation_reference_graph.py
python -m py_compile scripts/validation/check_citation_reference_graph_package.py
python -m pytest tests/smoke/test_citation_reference_graph_package.py -q
python -m scripts.export.package_citation_reference_graph --dry-run
python -m scripts.export.package_citation_reference_graph --force
python -m scripts.validation.check_citation_reference_graph_package --strict
```

Expected result:

```text
5 passed
package build ok=True
included_files_count=9
package validator ok=True
required_failed_count=0
warning_count=0
```

Boundary:

- local package candidate only
- no graph rebuild
- no canonical truth changes
- no reconcile input changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no full-text/PDF/bibliography parsing
- no dataset publication
- no latest pointer
- no graph runtime
- generated package output is not committed
- no Neo4j/NetworkX/GraphRAG runtime

See: `docs/citation_reference_graph_package_v0.md`.
<!-- CITATION_REFERENCE_GRAPH_PACKAGE_V01_END -->


### Citation Graph External Reference Lookup UI v0.1

Status: **completed UI-only local-inspection slice**

Scope:

```text
Streamlit calls GET /citation-graph/external-references/{reference_id}/papers through FastAPI.
The UI URL-quotes reference_id before inserting it into the path.
The panel renders referencing-paper evidence rows for one unresolved external_reference.
```

Boundary:

```text
no API endpoint changes
no CitationGraphStore changes
no direct Streamlit reads from data/graphs/*
no graph visualization
no NetworkX/Neo4j/GraphRAG
no full graph runtime loader
no graph DB materialization
no canonical/retrieval/Qdrant/Postgres/ranking/publication change
```


### Citation Graph UI Productization Checkpoint v0.1

Status: **completed validator-light checkpoint**

Accepted implementation baseline:

```text
Citation Graph API routes = 7
Citation Graph traversal/diagnostics routes = 6
streamlit_graph_evidence_panels = implemented
streamlit_graph_status_panel = implemented
streamlit_graph_paper_workspace_panel = implemented
streamlit_graph_diagnostics_ui = implemented
streamlit_graph_external_reference_lookup_ui = implemented
full_graph_runtime_loader = not implemented
full_graph_visualization_ui = not implemented
graph_db_materialization = not implemented
graphrag = not implemented
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

Checkpoint scope:

```text
living docs synchronization
existing validator synchronization
terminology cleanup
status-only comments/docstrings cleanup
no new endpoint or store method
no response-schema change
no graph output/package rebuild
no canonical/retrieval/Qdrant/Postgres/ranking/publication change
```


### Citation Graph Store Cache & Reload Regression v0.1

Status: **completed regression-hardening slice**

```text
citation_graph_store_cache = bounded_by_graph_root
citation_graph_store_cache_maxsize = 2
citation_graph_store_cache_clear_on_reload = implemented
graph_reload_rebuilds_artifacts = false
graph_reload_mutates_artifacts = false
reload_disabled_clears_graph_cache = false
```

The slice adds regression evidence around behavior that already exists in
`services/api/app.py`. Repeated access to the same graph root must reuse the
same in-memory `CitationGraphStore`. A successful `POST /reload` must clear the
bounded graph-store cache before the main runtime and Discovery caches are
reloaded. The next graph read may then reload the current files from the same
root.

The reload endpoint remains an invalidation/re-read operation only. It must not
rebuild graph output, write graph files, change graph counters, approve manual
review, publish the graph, or introduce a promoted full graph runtime loader.


### Citation Graph Failure Isolation & Error Recovery v0.1

Status: **completed regression-hardening slice**

```text
citation_graph_failure_isolation = implemented
graph_store_oserror_maps_to_graph_artifacts_invalid = true
graph_store_failed_load_cached = false
graph_runtime_failure_affects_general_health = false
graph_runtime_recovery_requires_process_restart = false
```

The existing status probe already fails closed for missing or unreadable graph
artifacts. This slice closes the remaining store-loading gap by mapping ordinary
file-system `OSError` failures from every traversal route to the stable
`503 graph_artifacts_invalid` contract instead of the generic API `500` path.

Failed `CitationGraphStore.load(...)` calls are not retained by the bounded
`lru_cache`. After files are repaired, the next request may load successfully
without restarting the FastAPI process. A previously cached valid store remains
usable until explicit `/reload` invalidation; after invalidation, current files
are read and any failure remains isolated to `/citation-graph/*`.

Boundary:

```text
no new endpoint or store query method
no response schema change
no graph rebuild or graph-file mutation
no dependency of /health, /info, /runtime, /search, Discovery, DB, or Qdrant on graph availability
no full graph runtime loader
no graph DB / GraphRAG
no canonical/retrieval/Postgres/Qdrant/ranking/UI/publication change
```


### Citation Graph Live Smoke & Known-Issues Hardening v0.1

Status: **completed operator-facing validation/docs slice**

```text
citation_graph_live_smoke = implemented_operator_facing_opt_in
citation_graph_live_smoke_dod_gate = not_required
citation_graph_live_smoke_auto_samples = graph_jsonl
citation_graph_known_issues = documented_v0.1
```

The live validator calls an already running FastAPI process over HTTP. It checks
`/health`, `/info`, `/runtime`, the status route, all six traversal/diagnostics
routes, stable 404 contracts, the result-limit guard, and post-graph general
health. Real paper and external-reference samples are resolved from the current
`nodes.jsonl` / `edges.jsonl` rather than hard-coded into the validator.

Reports are operator evidence only:

```text
artifacts/reports/validation/citation_graph_live_smoke_latest.json
artifacts/reports/validation/citation_graph_live_smoke_latest.md
artifacts/reports/validation/history/citation_graph_live_smoke_<timestamp>.json
artifacts/reports/validation/history/citation_graph_live_smoke_<timestamp>.md
```

`docs/citation_graph_known_issues_v0.1.md` records metadata-only coverage, low
reference resolution, unresolved external-reference semantics, non-bibliometric
diagnostics, whole-file local store loading, manual-review/publication blocks,
and the absence of a promoted graph runtime. A green live smoke does not approve
manual review or publication.

Boundary:

```text
no API route or response schema change
no CitationGraphStore method change
no graph rebuild or graph artifact mutation
no default DoD dependency on a running HTTP server
no full graph runtime loader
no graph DB / GraphRAG
no canonical/retrieval/Postgres/Qdrant/ranking/UI/publication change
```


### Citation Graph Manual-Review Evidence Preparation v0.1

Status: **completed read-only review-support slice**

```text
citation_reference_graph_manual_review_evidence = implemented_read_only
manual_review_evidence_categories = 18
automated_support_categories = 13
human_decision_categories = 5
category_status_changed = false
approval_state_changed = false
manual_review_complete = false
publication_ready = false
```

This slice assembles deterministic evidence from the accepted manual-review,
analytics, inspection, release-candidate, package, line-checkpoint, live-smoke,
API-regression, graph-review-pack, manifest, data-quality, README, source-matrix,
merge-policy, and known-issues inputs. It does not reread the full graph JSONL.

`evidence_ready=true` means review material is present. The preparation validator
did not set categories or approval itself. Those five categories remained
explicitly human-owned until the subsequent review-execution slice:
license/redistribution, provider terms, README clarity, publication target, and
final approval state.

Boundary:

```text
no manual-review config/status mutation
no automated category or final approval
no graph/package rebuild
no API/UI/runtime change
no canonical/retrieval/Postgres/Qdrant/ranking change
no graph DB / GraphRAG
no publication or upload
```


### Manual Citation Graph Review Execution v0.1

Status: **completed human-governance closure slice / not published**

```text
required_categories = 18
passed_categories = 18
failed_categories = 0
pending_categories = 0
approval_state = approved
manual_review_complete = true
publication_ready = false
publication_block_reason = publication_action_not_in_scope
```

The project owner/maintainer reviewed the prepared evidence and accepted the
Citation / Reference Graph v0.1 checklist for the declared non-commercial,
educational, portfolio, metadata-first scope. Future targets are a Kaggle
metadata/graph dataset, GitHub release, and public Radar website with explicit
provider attribution and links to original publications. PDFs and full text are
not redistributed.

Tracked decision evidence:

```text
docs/citation_reference_graph_manual_review_decision_record_v0.1.md
```

Boundary:

```text
manual-review approval != publication
no upload or package promotion
no graph/package rebuild
no canonical/retrieval/Postgres/Qdrant/ranking/API/UI change
no GraphRAG / graph DB / full graph runtime promotion
```

After this slice, the recommended project direction returns to the public
metadata dataset/Kaggle release track rather than extending Citation Graph
runtime surface by default.

### Public Metadata Release Policy & Kaggle Packaging v0.1

Status: **implemented local policy/packaging slice / not published**

```text
public_metadata_release_policy = implemented
policy_validator = implemented
selected_field_policy_coverage = 34/34
current_source_policy_coverage = 5/5
source_aware_abstract_filter = implemented
kaggle_metadata = template_only
technical_candidate_ready = expected_true_after_regeneration
public_policy_ready = expected_true_after_regeneration
manual_release_decision_required = true
publication_ready = false
publication_block_reason = public_release_decision_not_completed
```

The slice extends the existing dataset exporter rather than creating a second
pipeline. It generates `DATASET_CARD.md`, `ATTRIBUTION.md`, field/source policy
JSON, and `kaggle_metadata.template.json` beside the existing Parquet, schema,
manifest, quality summary, README, and checksums.

Boundary:

```text
no Kaggle/Hugging Face/GitHub upload
no final compilation-license selection
no canonical/retrieval/Postgres/Qdrant/ranking/API/UI change
no PDF/full-text/raw-payload/embedding export
```

The evidence-preparation checkpoint is followed by the explicit human execution
recorded below. Actual Kaggle/GitHub publication remains a later separate action.


### Public Metadata Release Manual-Review Evidence Preparation v0.1

Status: **completed read-only governance/evidence slice / pre-execution state / not published**

Implemented sequence:

```text
public metadata policy and local package
→ green config/policy/output/readiness reports
→ 20-category manual-review checklist
→ deterministic evidence preparation
```

Accepted pre-execution verdict:

```text
manual_review_evidence_ready = true
evidence_ready_category_count = 20
automated_support_category_count = 15
human_decision_category_count = 5
approval_state = not_reviewed
category_status_counts = {pending: 20}
manual_review_complete = false
publication_ready = false
publication_block_reason = public_release_decision_not_completed
```

Boundary:

```text
no automatic category approval
no final compilation-license choice
no publication-target choice
no Kaggle/Hugging Face/GitHub API call
no dataset/package rebuild in the evidence validators
no canonical/retrieval/Postgres/Qdrant/graph/ranking/API/UI change
```

### Manual Public Metadata Release Review Execution v0.1

Status: **active human-governance closure slice / completed and rejected / not published**

```text
approval_state = rejected
category_status_counts = {failed: 5, passed: 15}
manual_review_complete = true
publication_ready = false
publication_block_reason = manual_release_rejected
```

The technical candidate, package checksums, policy, and evidence remain green.
The human review rejects publication because the current candidate cannot prove a
sufficiently clear redistribution boundary for Semantic Scholar-derived data in
a downloadable Kaggle dataset.

Completed architecture slice:

```text
Field-Level Canonical Provenance Contract v0.1
```

Primary next architecture slice:

```text
Field-Level Canonical Provenance Evidence Builder v0.1
```

Separate publication-governance slice:

```text
Semantic Scholar Public Release Boundary Remediation v0.1
```

Two valid remediation paths:

```text
obtain written AI2/Semantic Scholar redistribution permission
or
rebuild and validate a public candidate with Semantic Scholar-derived data excluded
```

No automatic upload, GraphRAG, graph DB materialization, Qdrant promotion, or
unrelated runtime expansion is authorized.

## Source Observation Materialization Operational Promotion v0.1

Status: **completed / operationally promoted / rollback retained**

Purpose:

```text
Promote the fully validated source-observation materialization candidate to the
default operational Postgres database without changing canonical paper truth.
```

Completed database-name transition:

```text
ml_radar
→ ml_radar_pre_source_identity_v01_20260722t101620z

ml_radar_source_identity_candidate_v01
→ ml_radar
```

Current operational schema:

```text
source_documents.source_observation_id = PRIMARY KEY
source_documents.doc_id = NOT NULL, non-unique legacy diagnostic
canonical_source_links.source_observation_id = NOT NULL
canonical_source_links.source_observation_id
  → source_documents(source_observation_id) ON DELETE RESTRICT
canonical_source_links.doc_id = nullable legacy diagnostic
UNIQUE(canonical_id, source_observation_id)
```

Accepted operational counters:

```text
canonical_documents = 60,954
source_documents = 88,178
canonical_source_links = 88,037
document_references = 709,662
artifact_entities = 7,333
artifact_observations = 38,246
paper_artifact_links = 7,430
non_contributing_source_observations = 141
null_links = 0
dangling_links = 0
missing_selected_observations = 0
```

Accepted validation evidence:

```text
promotion validator smoke tests = 10 passed
preflight = 24 / 24
backup-required preflight = 28 / 28
post-promotion = 29 / 29
DB smoke = green
artifact DB smoke = green
full source-observation parity = green
Artifact API strict filter gate = green
```

Backup and rollback evidence:

```text
operational dump SHA-256 = af40c266cf12f284b20ccad6f1877ff85c3c3b05d4ccc4a36fcd114a92e71303
candidate dump SHA-256 = 8f9e4ee2765a7eeb6f368adec263787402b0a030ff305bfcfcb634509e684b4f
rollback DB retained = true
rollback DB source_documents = 70,244
rollback DB deletion = not performed
```

Architectural interpretation:

```text
source_observation_id fixes physical source-row identity in the derived serving layer
doc_id remains useful legacy/diagnostic metadata but is not globally unique
canonical_documents.jsonl remains paper truth
reconciliation behavior and canonical IDs are unchanged
Postgres remains rebuildable and derived
```

The **Field-Level Canonical Provenance Contract v0.1** is now completed and
green against the current implementation.

The next architectural slice is **Field-Level Canonical Provenance Evidence
Builder v0.1**. It must remain bounded, file-first, read-only, and derived; it
must not create a second canonical truth or add a Postgres/API/UI provenance
surface in the same slice.
## Field-Level Canonical Provenance Contract v0.1

Status: **done / green static contract and validation slice**

Tracked package:

```text
docs/field_level_canonical_provenance_contract_v0.1.md
scripts/validation/check_field_level_canonical_provenance_contract.py
tests/smoke/test_field_level_canonical_provenance_contract.py
```

Accepted evidence:

```text
CanonicalDocument fields = 61
classified fields = 61
contract validator = 99 / 99
contract smoke tests = 8 passed
related reconciliation regression = 38 passed
contract_matches_current_reconciliation = true
bounded audit sample selected papers = 12
bounded audit sample matched source documents = 33
bounded audit sample unmatched links = 0
```

The contract freezes the current executable semantics without changing them:

```text
identity-derived fields
scalar winners and ordered-first values
ordered unions and merged identifier maps
min/max aggregates and co-winners
boolean evidence and derived flags
post-selection normalization
recomputed scores
row-level provenance
runtime-default timestamps
```

Boundary:

```text
documentation plus static validation only
no stable-corpus reconcile execution
no canonical corpus mutation
no CanonicalDocument schema change
no Postgres provenance table
no API or Streamlit provenance surface
no retrieval/Qdrant/ranking/graph change
no publication action
```

## Field-Level Canonical Provenance Evidence Builder v0.1

Status: **recommended next bounded implementation slice**

Initial allowed scope:

```text
synthetic deterministic fixtures
selected bounded reconciliation audit samples
one derived evidence record per canonical field/sample
result fingerprints and bounded previews
selected/co-winning observation IDs
element-level contributors for union/map fields
transformations and caveats
read-only local JSON/JSONL output
```

Initial non-goals:

```text
no full 60,954-paper corpus generation
no canonical truth mutation
no reconcile selector changes
no Postgres schema/materialization
no API/UI product surface
no public dataset/package publication
no GraphRAG, graph DB, or Qdrant promotion
```

Acceptance should require a separate builder validator, deterministic smoke
fixtures, and explicit proof that generated evidence cannot be used as a
reconcile input.
