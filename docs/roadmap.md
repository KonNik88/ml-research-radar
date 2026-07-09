# ML Research Radar — Roadmap

## Document status

```text
document = primary living roadmap
accepted checkpoint = Current State Checkpoint v0.1
base checkpoint = Discovery Regression Runner Summary Report v1
current active direction = review / regression / design-hardening
current active slice = Citation Graph outgoing references endpoint documentation sync
public Qdrant promotion = not performed
public dense/hybrid backend = file
experimental Qdrant serving transport = gRPC
fallback = absent
scope of current branch = docs sync after first citation graph outgoing-references endpoint; no canonical/retrieval/Qdrant/Postgres/UI/ranking/graph-output/publication behavior changes
```

This roadmap describes the current validated state of **ML Research Radar**, the
architectural invariants that must remain stable, and the recommended order of
future work.

The project prefers complete, validated vertical slices over broad feature
expansion. After the completed local graph lines, the next safe direction is
review, regression, and design-hardening before any new runtime, public API,
GraphRAG, graph DB, or Qdrant-promotion work.

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
review / regression / design-hardening first
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
11. **Citation Graph Outgoing References Endpoint v0.1** — first narrow read-only traversal endpoint; outgoing references only, no incoming/external/source-family/top endpoints and no full graph runtime loader.

Recommended next safe slices:

1. **Citation Graph Outgoing References Endpoint Docs Sync v0.1** — align API reference, roadmap, current-state checkpoint, runbook, and graph API design docs with the implemented first traversal endpoint.
2. **Citation Graph Incoming Citations Endpoint v0.1** — next narrow endpoint only after docs sync; preserve status/compatibility gates and caveats.
3. **Regression / DoD hardening** — optional gates, accepted-checkpoint checks, and validation wiring only.

Explicit immediate non-goals:

- no GraphRAG implementation;
- no Neo4j/NetworkX runtime;
- no additional graph traversal endpoints beyond the implemented outgoing-references route;
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
source_doc_id = source-level observation identity
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
streamlit_graph_ui = not implemented
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
streamlit_graph_ui = not implemented
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
test_api_citation_graph_references.py = 5 passed
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
incoming citations endpoint is not implemented
external-reference lookup endpoint is not implemented
source-family/top-reference endpoints are not implemented
full graph runtime loader is not implemented
graph DB materialization is not implemented
Streamlit graph UI is not implemented
GraphRAG is not implemented
/search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, and publication state are unchanged
```


## 5. Current active direction

### 5.1 Citation graph API narrow traversal hardening

Status: **current direction after completed outgoing-references endpoint**

Goal:

```text
Keep the graph API path deliberately staged: status/compatibility first,
internal store semantics second, and then one traversal endpoint at a time.
```

Current accepted API state:

```text
GET /citation-graph/status = implemented
GET /citation-graph/papers/{canonical_id}/references = implemented
GET /citation-graph/papers/{canonical_id}/citations = not implemented
GET /citation-graph/external-references/{reference_id}/papers = not implemented
GET /citation-graph/source-families = not implemented
GET /citation-graph/top-referenced-papers = not implemented
GET /citation-graph/top-external-references = not implemented
full graph runtime loader = not implemented
```

Definition of done for the current docs-hardening direction:

- roadmap records the outgoing references endpoint as the first completed traversal code slice;
- API reference documents the endpoint, parameters, caveats, and graph error mapping;
- docs do not imply that incoming citations, external-reference lookup, source-family diagnostics, top-reference endpoints, full graph runtime loading, GraphRAG, DB materialization, or Streamlit graph UI exists;
- next code work may add only one narrow endpoint, preferably incoming citations;
- no canonical, retrieval, Qdrant, Postgres, UI, ranking, graph-output, package, or publication behavior is changed in this docs sync.

Boundary:

```text
docs/checkpoint sync only
no graph rebuild
no package rebuild
no additional API endpoint implementation
no full runtime graph loader
no GraphRAG
no Qdrant promotion
no publication
```

Next safe directions:

1. **Citation Graph Incoming Citations Endpoint v0.1** — one narrow endpoint, only after this docs sync.
2. **Regression / DoD hardening** — optional gates and accepted-checkpoint validation wiring.
3. **Graph API endpoint contract cleanup** — if app.py route helpers become too large, extract a small query service without changing behavior.


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
no incoming-citation endpoint
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
test_api_citation_graph_references.py = 5 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py = 7 passed
```

Non-goals:

```text
no incoming-citation endpoint
no external-reference lookup endpoint
no source-family/top-reference endpoints
no full graph runtime loader
no DB materialization
no Streamlit graph UI
no GraphRAG
no publication
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
