# ML Research Radar — Roadmap

## Document status

```text
document: primary living roadmap
base checkpoint: Qdrant Hybrid Evaluation v1 merged / green
active checkpoint: Current-State and Evidence Sync v1
active branch: maintenance/current-state-evidence-sync-v1
current-state scope: evidence and documentation synchronization only
public Qdrant promotion: not performed
public dense/hybrid backend: file
experimental Qdrant serving transport: gRPC
parity/profile-sweep compatibility transport: REST
fallback: absent
scaling strategy: accepted / documented
```

This roadmap describes the current validated state of **ML Research Radar**,
the architectural invariants that must remain stable, and the recommended order
of future work.

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

The platform collects partially overlapping observations from multiple
sources, reconciles them into paper-level canonical entities, and builds
rebuildable retrieval, serving, evidence, analytics, API, and UI layers above
the canonical corpus.

High-level architecture:

```text
paper sources
→ raw source records
→ normalized source observations
→ alignment / enrichment
→ identity resolution / reconcile
→ canonical paper corpus
→ retrieval artifacts
→ Postgres serving materialization
→ artifact evidence layer
→ paper features
→ ranking / paper cards / similar papers
→ topic clusters / topic projection
→ Discovery API
→ Streamlit thin client
→ evaluation / validators / Definition of Done
→ future full text / RAG / personalization / datasets
```

---

## 2. Architectural invariants

### 2.1 Paper truth

```text
data/analytics/reconciled/canonical_documents.jsonl
= paper-level source of truth
```

`CanonicalDocument` is the central paper-level entity.

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
```

Paper identity priority remains:

```text
DOI
→ external DOI
→ arXiv ID
→ external arXiv ID
→ normalized title + year fallback
```

A canonical URL is useful metadata but is not the sole paper identity rule.

### 2.3 Postgres

```text
Postgres = rebuildable materialized serving layer
```

It supports browse/filter, DB lexical search, source/reference inspection,
artifact serving, and API queries.

It is not canonical paper truth.

### 2.4 Retrieval

```text
retrieval artifacts = derived retrieval layer
```

The active retrieval build is tied to:

- corpus count and fingerprint;
- build ID;
- lexical artifacts;
- dense embeddings and dense IDs;
- embedding model;
- normalized-vector contract.

### 2.5 Artifact evidence

GitHub, Hugging Face, datasets, models, demos, and repositories are separate
artifact entities linked to papers through evidence.

```text
CanonicalDocument
↕ trusted relation / provenance
ArtifactEntity
```

Artifact metadata must not overwrite paper bibliography or identity.

### 2.6 Qdrant

```text
Qdrant = optional derived dense-serving backend
```

Qdrant is not:

- a paper source;
- canonical truth;
- a retrieval strategy;
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

### 2.7 Streamlit

```text
Streamlit = thin client over FastAPI
```

Business logic, retrieval, ranking, canonical merge, artifact normalization,
and clustering remain outside the UI.

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

### 3.2 Qdrant collection

```text
collection = ml_radar_dense_benchmark_v1
points_count = 60954
vector_size = 384
distance = Cosine
status = green
optimizer_status = ok
experimental transport = gRPC
grpc_port = 6334
```

### 3.3 Golden Set and profile

```text
enabled_queries_count = 34
explicit_canonical_labeled_enabled_count = 34
weak_pattern_enabled_count = 0
```

Profile evidence:

```text
default → exact order 33/34
ef_128  → exact order 33/34
ef_256  → exact order 34/34
ef_512  → exact order 34/34
exact   → exact order 34/34
```

Selected profile:

```text
name = ef_256
exact = false
hnsw_ef = 256
```

Diagnostic oracle:

```text
name = exact
exact = true
```

`ef_256` is build-scoped and must be re-evaluated after material changes.

### 3.4 Serving performance

```text
transport = gRPC
full benchmark queries = 34
top_k = [10, 20]
backend concurrency = [1, 2, 4, 8]
API concurrency = [1, 2, 4, 8]

quality comparisons = 681
exact comparisons = 681
mean overlap@k = 1.0
minimum overlap@k = 1.0
serving errors = 0
strict validator failures = 0
```

Reliability evidence:

```text
REST shared client on Windows at direct concurrency 8
→ reproducible WinError 10038

gRPC backend full run #1
→ 680 / 680 successful at concurrency 8

gRPC backend full run #2
→ 680 / 680 successful at concurrency 8

final full benchmark
→ backend Qdrant concurrency 8 = 680 / 680
→ API Qdrant concurrency 8 = 204 / 204
```

### 3.5 Controlled hybrid evaluation

```text
transport = gRPC
profile = ef_256
queries = 34
scenarios = 136

scenario matrix:
- top_k=10, candidate_k=50, rank=false
- top_k=10, candidate_k=50, rank=true
- top_k=20, candidate_k=100, rank=false
- top_k=20, candidate_k=100, rank=true

successful = 136 / 136
errors = 0
fallback = 0
blocking classifications = 0
determinism failures = 0

final result-set parity = 136 / 136
exact final order = 134 / 136
exact dense + final parity = 132 / 136
```

Four stable non-blocking differences occur only at `candidate_k=100` for:

```text
diffusion_models_001
rag_evaluation_001
```

They preserve the complete final top-20 set. Two have no final-order effect;
two produce only a rank-9/rank-10 swap. No Hit, Precision, Recall, or MRR
regression was observed. The only non-zero metric delta is
`nDCG = +0.002368` for Qdrant in one ranked scenario.

Public behavior remains:

```text
/search?mode=dense  → file dense
/search?mode=hybrid → file dense component
/experimental/search/qdrant → Qdrant gRPC
/health → Qdrant-independent
fallback → absent
```

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

Important rule:

```text
candidate / experiment
≠ stable latest
```

Selective snapshots must not overwrite full accepted snapshots.

### 4.3 Retrieval foundation

Status: **done / green**

Completed:

- lexical retrieval;
- dense retrieval;
- hybrid retrieval;
- retrieval manifest;
- artifact validation;
- file runtime;
- retrieval evaluation;
- search-quality experiments;
- controlled experiments;
- Golden Set validation;
- similar-paper retrieval.

Exact file reference semantics:

```python
query_vector = encoder.encode(
    [query],
    convert_to_numpy=True,
    normalize_embeddings=True,
)[0].astype(np.float32)

scores = stored_embeddings @ query_vector
order = np.argsort(scores)[::-1]
```

The full sort is the current exact reference behavior.

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

DB-native dense or hybrid parity is not required now.

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

### 4.6 Paper features, ranking, detail, similar papers

Status: **done / green**

Completed:

- rebuildable paper feature layer;
- implementation readiness;
- source confidence;
- citation signal;
- recency;
- radar score;
- ranking profiles;
- query overrides;
- paper detail cards;
- semantic and radar-adjusted similar papers.

These are transparent derived heuristics, not canonical truth.

### 4.7 Discovery API

Status: **done / green**

Current endpoints include:

```text
/discovery/profiles
/discovery/ranking/{profile}
/discovery/papers/{canonical_id}
/discovery/papers/{canonical_id}/similar
/discovery/papers/{canonical_id}/cluster
/discovery/clusters
/discovery/clusters/{cluster_id}
/discovery/clusters/map
```

### 4.8 Streamlit Discovery UI

Status: **done / green**

The thin client supports:

- discovery ranking;
- search;
- filters and sorting;
- paper workspace;
- similar papers;
- topic clusters;
- topic map;
- artifact exploration;
- runtime status;
- API reload.

### 4.9 Topic clusters and projection

Status: **done / green**

```text
algorithm = MiniBatchKMeans
cluster_count = 80
assignments = 60954
empty_clusters = 0

projection_algorithm = UMAP
projection_points = 2080
centroids = 80
representatives = 800
sampled_papers = 1200
```

Cluster IDs and labels are build-scoped navigation aids, not canonical taxonomy.

### 4.10 Retrieval evaluation and Golden Set Expansion v2

Status: **done / green**

Completed:

- 34 enabled queries;
- 34 explicit canonical relevance labels;
- no weak-pattern-only enabled queries;
- parity, ranking, search-quality, and controlled evaluation tooling;
- query-group expansion across modern ML topics.

Rule:

```text
Do not change retrieval defaults by intuition.
Use measured query-level and group-level evidence.
```

### 4.11 Qdrant serving parity

Status: **done / green**

Established:

- collection mapping is correct;
- persisted and Qdrant vectors are compatible;
- build ID and dense-index mapping are correct;
- exact Qdrant matches exact file dense;
- the old mismatch was approximate HNSW recall;
- `ef_256` restores full parity at the dense comparison depth.

Public search was not switched.

### 4.12 Dense Search Backend Abstraction v1

Status: **done / green; merged in PR #16**

Implemented:

```text
DenseSearchBackend
├── FileDenseBackend
└── QdrantDenseBackend
```

Backends own only dense candidate generation.

They do not own:

- text validation;
- model loading;
- query encoding;
- hydration;
- hybrid merge;
- product ranking;
- fallback;
- API serialization.

### 4.13 Qdrant Failure Contract v1

Status: **done / green; merged in PR #17**

Typed mappings:

```text
DenseBackendRequestError       → 400 dense_backend_bad_request
DenseBackendUnavailableError   → 503 dense_backend_unavailable
DenseBackendCompatibilityError → 503 dense_backend_incompatible
DenseBackendResultError        → 503 dense_backend_invalid_result
```

Additional guarantees:

- hydration miss fails explicitly;
- no hidden fallback;
- `/health` remains Qdrant-independent;
- public dense/hybrid remain file-backed;
- stop/start recovery works;
- reload recreates the backend.

### 4.14 Qdrant Runtime Observability v1

Status: **done / green; merged in PR #18**

Implemented:

```text
GET /runtime?refresh_qdrant=true
→ forced live Qdrant probe

GET /runtime
→ cached probe within 30-second TTL
```

Runtime diagnostics include:

- collection compatibility;
- profile/build information;
- backend creation and compatibility state;
- request/success/failure counters;
- timestamps;
- bounded last-failure evidence;
- encode/search/hydration/total timings;
- requested/effective backend;
- explicit `fallback_applied=false`;
- reset on reload.

No public promotion or fallback was introduced.

### 4.15 Qdrant Serving Performance v1

Status: **done / green; merged in PR #19**

Coverage:

```text
backend-only:
FileDenseBackend vs QdrantDenseBackend

end-to-end:
public file-dense /search
vs
experimental /experimental/search/qdrant

Golden Set = 34 queries
top_k = [10, 20]
concurrency = [1, 2, 4, 8]
```

The slice established:

- strict read-only serving benchmark;
- explicit gRPC transport;
- repeated zero-error concurrency evidence;
- 681 exact quality comparisons;
- runtime transport diagnostics;
- integrated regression, DB smoke, and strict DoD closure.

Public dense/hybrid remained file-backed.

### 4.16 Qdrant Hybrid Evaluation v1

Status: **done / green; merged into main**

Implemented:

```text
shared hybrid merge kernel
paired FileDenseBackend/QdrantDenseBackend executor
strict evaluation-only hydration
common optional ranking
query-vector and lexical-input fingerprints
determinism repeats
classification of non-exact outcomes
strict evidence validator
opt-in Discovery regression integration
```

Full evidence:

```text
queries = 34
scenarios = 136
successful scenarios = 136
errors = 0
quality_ok = true
strict required_failed_count = 0

mean dense overlap = 0.999412
minimum dense overlap = 0.98
mean final overlap = 1.0
minimum final overlap = 1.0

exact_match = 132
dense_candidate_difference_no_final_effect = 2
same_set_different_order = 2
```

Interpretation:

- the complete final result set is preserved in every scenario;
- all differences are deterministic and non-blocking;
- no mapping, build, hydration, fallback, or integrity defect was observed;
- public dense and hybrid remain file-backed;
- the slice supplies evidence for a separate exposure decision rather than
  performing promotion.

---

## 5. Validation evidence for the current main checkpoint

Focused hybrid slice suite:

```text
test_qdrant_hybrid_evaluation.py = 34 passed
test_run_qdrant_hybrid_evaluation.py = 10 passed
test_qdrant_hybrid_evaluation_validator.py = 8 passed
test_hybrid_merge_contract.py = 13 passed
test_dense_backend_contract.py = 19 passed
test_qdrant_regression_runner.py = 9 passed
focused total = 93 passed
```

Full hybrid evidence:

```text
build_id = 20260504T164021Z
collection = ml_radar_dense_benchmark_v1
transport = gRPC
profile = ef_256
queries = 34
scenarios = 136
successful = 136
errors = 0
strict validator failures = 0
```

Parity and quality:

```text
final result-set parity = 136 / 136
exact final order = 134 / 136
exact dense + final parity = 132 / 136
stable non-blocking differences = 4 / 136

Hit delta = 0
Precision delta = 0
Recall delta = 0
MRR delta = 0
nDCG delta range = [0, +0.002368]
```

Integrated Discovery regression included:

```text
check_golden_queries --strict
Discovery API integration
check_discovery_api --strict
check_topic_clusters --strict
check_topic_projection --strict
check_streamlit_discovery_ui --strict
run_qdrant_hybrid_evaluation
check_qdrant_hybrid_evaluation --strict
```

Result:

```text
Golden Set = 34 enabled / strict green
Discovery integration = 34 passed, 4 expected DB-only skips
Qdrant hybrid = 136 / 136 successful
Qdrant hybrid strict required_failed_count = 0
Discovery API regression passed
```

The previous merged Qdrant Serving Performance v1 checkpoint retains its DB
smoke and strict Definition-of-Done closure. This hybrid slice does not modify
canonical data, retrieval artifacts, Postgres materialization, or the Qdrant
collection.

Current full-corpus provenance evidence:

```text
report = canonical_provenance_consistency_v2
documents checked = 60954
structural errors = 0
warnings = 0
informational doc_ids_shorter_than_sources = 9095
```

The informational count follows the documented semantics: `doc_ids` are
deduplicated while `sources` preserve contributing provenance rows.

---

## 6. Near-term roadmap

### 6.0 Current-State and Evidence Sync v1

Status: **active maintenance slice**

Scope:

```text
refresh full-corpus provenance evidence
synchronize ACL/source/artifact status
clarify source-config responsibilities
document REST/gRPC evaluation roles
refresh README, architecture, roadmap, and dataset placeholder
preserve all public runtime and retrieval defaults
```

Non-goals:

```text
no canonical or retrieval rebuild
no public Qdrant promotion
no vector-backend selector
no embedding or hybrid-weight change
no ranking redesign
no new source ingestion
```

After merge, choose one focused technical slice:

```text
Ranking Evaluation and Hardening v1
Retrieval Generation Study v1
Graph/Evidence Contract v1
Lexical Performance Profiling v1
Discovery Product Enhancement
```

The project will not scale the corpus aggressively before the main product,
retrieval, evaluation, refresh, and promotion semantics are sufficiently
stable.

The accepted sequencing is documented in:

```text
docs/scaling-and-vector-serving-strategy-v1.md
```

Recommended order:

```text
1. Complete and stabilize the functional MVP on the current representative corpus.
2. Strengthen product features, retrieval quality, ranking, and code ownership.
3. Select and validate the next embedding/retrieval generation.
4. Run a medium-scale rehearsal on a larger candidate corpus.
5. Operationalize Qdrant through a deployment-level vector-backend selector.
6. Promote Qdrant to the primary vector-serving role when scale evidence justifies it.
7. Expand the accepted corpus substantially.
8. Add orchestration and distributed infrastructure only when real operating needs appear.
```

### 6.1 Scaling and vector-serving strategy

Status: **accepted / documented**

Core decision:

```text
The current 60954-document corpus remains the representative development and
validation corpus while the functional MVP and its contracts are still evolving.
```

Current role split:

```text
FileDenseBackend
= exact reference backend, offline evaluation oracle, rebuildable artifact path

QdrantDenseBackend
= validated future scalable vector-serving backend
```

The completed Qdrant work is therefore a scale-readiness proof, not an
immediate requirement to switch public search.

The project must avoid both extremes:

```text
premature scale
→ slower iteration, harder debugging, expensive rebuilds

late operationalization
→ forced migration only after the corpus has already become too large
```

Preferred transition point:

```text
functional MVP stabilized
→ next embedding model selected
→ medium-scale rehearsal
→ deployment-level Qdrant selector
→ large corpus expansion
```

A public request-level `vector_backend` parameter remains deferred. It should
be introduced only if a concrete product use case requires per-request backend
selection.

### 6.2 Functional MVP completion on the current corpus

Status: **current planning horizon**

The current corpus is large enough to exercise real project behavior while
remaining cheap enough to rebuild and inspect.

Suitable work before major scale-up includes:

- graph and relation layers;
- additional paper features;
- ranking and reranking improvements;
- retrieval-model experiments;
- stronger discovery workflows;
- refresh and promotion hardening;
- source viability experiments;
- code ownership and architecture review;
- API/UI product polish;
- evaluation and failure-injection improvements.

The next concrete vertical slice should be selected separately. The roadmap
does not force Qdrant deployment selector work to be the immediate next PR.

### 6.3 Next embedding and retrieval generation

Status: **planned before large-scale corpus growth**

Potential profiles:

```text
fast_default
scientific_semantic
citation_aware
hybrid
```

A stronger model may improve scientific retrieval, but any model change
creates a new retrieval generation.

Required lifecycle:

```text
select candidate model
→ build file embeddings and IDs
→ validate normalization and dimensions
→ create a new build-scoped Qdrant collection
→ run Golden Set evaluation
→ run profile sweep
→ run controlled hybrid evaluation
→ run serving benchmark
→ promote or reject the generation explicitly
```

The current MiniLM build and Qdrant collection remain valid evidence for the
existing generation, not permanent defaults for every future corpus.

### 6.4 Medium-scale rehearsal

Status: **planned gate before major corpus expansion**

Before moving directly to millions of papers, create a larger candidate build,
for example:

```text
100000–300000 documents
or
approximately 500000 documents
```

This rehearsal need not become stable canonical latest.

Measure:

- ingest, normalize, align, and reconcile time;
- identity-conflict and provenance behavior;
- Postgres materialization time and size;
- embedding throughput and artifact size;
- Qdrant upload and index-build time;
- RAM, VRAM, storage, and pagefile pressure;
- exact file-search latency;
- Qdrant latency and concurrency;
- incremental refresh behavior;
- validator and report duration;
- candidate promotion and rollback;
- full rebuild recovery.

The result determines whether Qdrant operationalization, model changes,
partitioning, or pipeline orchestration must happen before further growth.

### 6.5 Deployment-level Qdrant selector

Status: **approved future slice; intentionally deferred**

Preferred future contract:

```text
ML_RADAR_VECTOR_BACKEND=file|qdrant
```

Default:

```text
file
```

Initial scope:

```text
/search?mode=dense
/search?mode=hybrid
```

Behavior:

```text
mode = retrieval strategy
vector backend = deployment-selected dense implementation
```

Expected v1 rules:

- one vector backend per deployment;
- no request-level selector;
- no hidden fallback;
- lexical search remains independent;
- Qdrant-selected deployments expose explicit readiness failures;
- file remains the rollback and exact-reference backend;
- experimental Qdrant endpoint remains until a separate lifecycle decision;
- similar-paper migration is a separate evaluated slice.

This selector should be implemented after MVP semantics and the next retrieval
generation are clearer, but before large corpus growth makes file serving an
operational constraint.

### 6.6 Similar-paper vector serving

Status: **separate future decision**

Current similar-paper search already uses paper embeddings and file-based
nearest-neighbour search.

Potential future path:

```text
paper embedding
→ Qdrant nearest neighbours
→ self-exclusion
→ existing semantic or radar-adjusted ranking
```

This is not automatically included in deployment selector v1 because the
contract differs from text-query search:

- paper vector instead of query text;
- mandatory self-exclusion;
- different enrichment;
- different evaluation cases;
- `semantic` and `radar_adjusted` result modes.

Migration is justified only by measured latency, memory, update, or
operational benefits.

### 6.7 Hydration and cold-start investigation

Status: **measured opportunity, not current blocker**

Warm Qdrant API p50:

```text
hydrate = 31.376 ms
encode = 11.590 ms
Qdrant search = 5.216 ms
total = 48.475 ms
```

Potential work:

- inspect canonical ID lookup layout;
- separate hydration from serialization;
- profile copy and validation costs;
- preserve explicit missing-document semantics;
- avoid backend-specific hydration logic;
- evaluate eager channel/backend initialization for deployed Qdrant mode.

Hydration optimization may deliver more API-level benefit than further ANN
micro-optimization on the current corpus.

### 6.8 Integration-test memory and lifecycle hardening

Status: **technical debt**

A previous monolithic heavy pytest process produced a transient memory failure,
while separate processes passed.

Potential work:

- instrument RSS, committed memory, and VRAM;
- verify object release between TestClient sessions;
- consider lightweight fixtures;
- consider CPU-only integration mode;
- keep heavy groups separate until hardened.

### 6.9 Source expansion

Status: **planned through source viability gates**

Current stable paper-source set already includes ACL Anthology.

Possible future sources:

- OpenReview;
- PubMed / Europe PMC;
- bioRxiv / medRxiv;
- selective additional conference and repository sources.

Papers with Code live integration remains blocked/archived under the current access contract. Any future use must be an explicit offline/historical viability experiment rather than a default live-source plan.

Every source must pass identity, value, overlap, access, provenance, refresh,
and reconcile-safety gates.

Large-scale source ingestion must wait until the relevant refresh,
reconciliation, retrieval-generation, validation, and rollback paths are
reproducible.

### 6.10 Orchestration and distributed infrastructure

Status: **trigger-based, not schedule-based**

Airflow or another orchestrator becomes justified when:

- the pipeline runs regularly;
- multiple dependent stages need scheduling;
- retries and restart-from-failure are needed;
- run history and operational visibility are required;
- manual CLI composition becomes an operational risk.

Kafka becomes justified when:

- ingestion is event-driven or near-real-time;
- several independent consumers need the same events;
- replay is operationally valuable;
- batch refresh is no longer sufficient.

Kubernetes becomes justified when:

- several services need independent scaling;
- replicas and rolling rollout are required;
- automated recovery is needed;
- a production-like deployment topology exists.

These tools remain options, not mandatory portfolio decorations.

### 6.11 Full text, RAG, personalization, and datasets

Status: **later product layers**

Potential directions:

- full-text acquisition and chunking;
- evidence-grounded RAG;
- citation-preserving answers;
- saved papers and watchlists;
- personalized feeds;
- why-recommended explanations;
- paper comparison;
- dataset releases.

These layers must build on stable canonical identity, retrieval generations,
provenance, and evaluation rather than bypass them.

---

## 7. Engineering and MLOps backlog

Add only when justified by real operational need:

- structured logging;
- Prometheus and Grafana;
- Loki/ELK;
- OpenTelemetry and Jaeger;
- secrets management;
- Alembic;
- Airflow;
- Ray;
- Kafka;
- Kubernetes;
- full React/Next.js frontend.

Avoid technology-driven architecture.

---

## 8. Explicit non-goals of the current checkpoint

Not part of Current-State and Evidence Sync v1:

- public `vector_backend` parameter;
- public Qdrant promotion;
- switching public dense/hybrid to Qdrant;
- hidden or explicit fallback orchestration;
- public `/search` response expansion;
- backend-specific public modes;
- similar-paper migration;
- DB-native dense or hybrid;
- lexical backend abstraction;
- filter pushdown;
- retry or circuit-breaker framework;
- persistent telemetry history;
- Prometheus/OpenTelemetry platform;
- embedding replacement;
- reranking redesign;
- canonical refresh;
- retrieval rebuild;
- Qdrant collection mutation;
- new sources;
- full text;
- RAG;
- topic rebuild;
- Streamlit redesign.

---

## 9. Working and validation conventions

### Git

- Git operations run in Git Bash.
- Python, pytest, validators, and scripts run in Anaconda Prompt.
- Avoid `git add .`.
- Stage intentional files explicitly.
- Keep `notebooks/Untitled.ipynb` outside project commits.

### Generated artifacts

`artifacts/` is ignored in the active workflow.

Therefore:

- report generation does not normally create commit candidates;
- `git status` remains the source of truth;
- ignored reports are not routine commits;
- tracked baselines require an explicit policy.

### Heavy tests

Until memory lifecycle is hardened:

- run heavy API files separately;
- run comparison, profile sweep, serving performance, and hybrid evaluation as
  separate commands when diagnosing failures;
- avoid one monolithic process that repeatedly loads model/corpus/runtime.

---

## 10. Guiding principles

```text
canonical truth first
derived layers rebuildable
evidence before defaults
explicit failure over hidden fallback
candidate integration before stable promotion
stabilize semantics before scaling data
introduce infrastructure only when operating needs justify it
one validated vertical slice at a time
```

The controlled hybrid question is answered for the active build:

```text
Qdrant ef_256 preserves the complete final hybrid result set across the full
34-query, 136-scenario evaluation matrix without measured quality regression.
```

The accepted scaling decision is:

```text
Use the current representative corpus to finish and validate the functional
MVP. Keep file dense as the exact reference. Operationalize Qdrant after the
next retrieval generation and a medium-scale rehearsal, but before major
corpus expansion makes file serving an operational constraint.
```

The next project question is therefore not automatically "switch to Qdrant".

After the current evidence/documentation sync is merged, the decision is:

```text
Which single focused vertical slice most increases product value or
architectural confidence while preserving the validated scaling path?
```
