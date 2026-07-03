# ML Research Radar — Roadmap

## Document status

```text
document = primary living roadmap
accepted checkpoint = Paper–Artifact Graph Manual Review Checklist v0.1
base checkpoint = Discovery Regression Runner Summary Report v1
current active slice = Paper–Artifact Graph Analytics v0.1
public Qdrant promotion = not performed
public dense/hybrid backend = file
experimental Qdrant serving transport = gRPC
fallback = absent
scope of current branch = read-only graph analytics/report only; no publication/graph rebuild/package rebuild/API/UI/runtime behavior changes
```

This roadmap describes the current validated state of **ML Research Radar**, the
architectural invariants that must remain stable, and the recommended order of
future work.

The project prefers complete, validated vertical slices over broad feature
expansion.

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

## 5. Current active slice

### 5.1 Paper–Artifact Graph Analytics v0.1

Status: **current / read-only analytics and report layer**

Goal:

```text
Add a local analytics/report layer over the already generated Paper-Artifact Graph v0.1 output so manual review and future exposure decisions have compact evidence about coverage, distributions, and limitations.
```

This slice exists after the completed local governance sequence:

```text
contract
→ builder
→ output validator
→ inspection
→ query CLI
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
→ analytics report
```

Scope:

- add `configs/paper_artifact_graph_analytics.yaml`;
- add `docs/paper_artifact_graph_analytics_v0.md`;
- add `scripts/validation/check_paper_artifact_graph_analytics.py`;
- add `tests/smoke/test_paper_artifact_graph_analytics.py`;
- update `docs/roadmap.md`;
- update `docs/refresh_contract_v1.md`;
- compute compact read-only analytics over existing graph output;
- emit JSON/Markdown reports for local review;
- preserve all canonical, serving, retrieval, Qdrant, ranking, API, UI, package, and publication boundaries.

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

Required validation sequence:

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_analytics.py
python -m pytest tests/smoke/test_paper_artifact_graph_analytics.py -q
python -m scripts.validation.check_paper_artifact_graph_analytics --strict
```

Accepted local validation result:

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

Expected generated reports, not committed:

```text
artifacts/reports/validation/paper_artifact_graph_analytics_latest.json
artifacts/reports/validation/paper_artifact_graph_analytics_latest.md
artifacts/reports/validation/history/paper_artifact_graph_analytics_<run_ts>.json
artifacts/reports/validation/history/paper_artifact_graph_analytics_<run_ts>.md
```

Non-goals:

```text
no graph publication
no external sharing
no public graph API
no Streamlit graph UI
no graph runtime
no Neo4j / NetworkX / GraphRAG runtime
no graph rebuild
no package rebuild
no canonical truth change
no reconcile input change
no DB/Postgres change
no Qdrant change
no retrieval behavior change
no ranking behavior change
no API behavior change
no UI behavior change
no trusted-link policy redefinition
no manual approval state change
```

Generated analytics reports are local operational evidence and are not committed by default.

## 6. Near-term roadmap

### 6.1 Finish and merge Paper–Artifact Graph Analytics v0.1

Purpose:

```text
Close the read-only analytics/report layer that supports manual review with compact graph coverage and distribution evidence.
```

Definition of done:

- analytics config exists and validates;
- analytics validator is read-only and strict green;
- smoke tests cover valid graph analytics, unsafe config, broken graph, missing files, and report-writing behavior;
- docs explain what analytics reports are and are not;
- roadmap and refresh contract are updated;
- no graph/package/runtime/publication layer is changed.

### 6.2 Paper–Artifact Graph Manual Review Evidence Pack v0.1

Potential next read-only slice after analytics.

Purpose:

```text
Bundle manual-review-relevant evidence from line checkpoint, manual-review gate, package, release candidate, inspection, query CLI, and analytics reports without publishing the graph package.
```

Possible scope:

- collect paths and summaries of existing graph-line reports;
- create one local review index document;
- list manual-review categories and matching evidence references;
- preserve pending-category semantics;
- keep publication blocked.

Non-goals:

- no publication;
- no package rebuild;
- no manual approval automation;
- no API/UI/runtime;
- no canonical/reconcile changes.

### 6.3 Paper–Artifact Graph API Design v0.1

Purpose:

```text
Design possible future API semantics before implementing any graph endpoint.
```

This should be a design-only slice unless separately approved.

Questions to resolve:

- which graph queries are safe to expose;
- whether graph output remains local/offline or becomes a serving artifact;
- how to prevent graph from being interpreted as canonical truth;
- how to document provenance and trust boundaries;
- whether endpoint output should mirror Query CLI semantics;
- whether API needs additional manual-review/publication gates.

Non-goals:

- no endpoint implementation;
- no Streamlit graph UI;
- no runtime graph database;
- no GraphRAG.

### 6.4 Publication Preparation v0.1

Only after manual review is actually completed.

Purpose:

```text
Prepare a separate publication or external-sharing decision for the graph/package candidate.
```

Possible scope:

- publication target selection;
- license and redistribution decision;
- final README limitations;
- release notes;
- archive retention policy;
- explicit public-upload procedure.

Publication must remain a separate PR/slice from validators and local evidence reports.

### 6.5 Citation / Reference Graph Contract v0.1

Potential separate future line.

Important boundary:

```text
Citation/reference graph should be a separate derived paper→paper graph line.
It should not be mixed directly into Paper-Artifact Graph v0.1.
```

### 6.6 Deployment Vector Backend Selector Design v1

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

### 6.7 Public Qdrant Promotion v1

Prerequisites:

- deployment selector design accepted;
- regression gate green;
- failure semantics accepted;
- rollback plan accepted;
- API docs updated;
- no fallback ambiguity.

Promotion must be a separate PR.

### 6.8 Ranking / reranking research

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
