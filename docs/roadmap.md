# ML Research Radar — Roadmap

## Document status

```text
document: primary living roadmap
checkpoint: Qdrant Hybrid Evaluation v1
checkpoint date: 2026-06-13
implementation state: implemented / validated on feature branch, pending PR merge
feature branch: retrieval/qdrant-hybrid-evaluation-v1
base main checkpoint: 6358164
previous checkpoint: Qdrant Serving Performance v1 merged in PR #19
public Qdrant promotion: not performed
public dense/hybrid backend: file
experimental Qdrant transport: gRPC
fallback: absent
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

Status: **implemented / validated on feature branch; pending PR merge**

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

## 5. Validation evidence for the current feature branch

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

---

## 6. Near-term roadmap

Recommended order after merge:

```text
1. Explicit public/deployment Qdrant exposure decision.
2. Hydration and cold-start investigation if latency work is prioritized.
3. Integration-test memory/lifecycle hardening.
4. Stronger embeddings and retrieval profiles.
5. Topic labeling and product polish.
6. New sources through the viability gate.
7. Full text / RAG / personalization / dataset releases.
```

### 6.1 Public or deployment-level Qdrant exposure decision

Status: **next retrieval decision slice**

The evidence question is now answered for the active build:

```text
Replacing only the dense component of hybrid search preserves the complete
final result set across all 136 evaluated scenarios and introduces no measured
quality regression, fallback, integrity defect, or nondeterminism.
```

The next decision is contractual and product-facing.

Possible outcomes:

- keep Qdrant experimental;
- expose an explicit opt-in backend selector;
- select the backend at deployment composition;
- run a limited explicit rollout;
- postpone promotion.

No promotion remains a valid outcome.

Any approved exposure must define:

- requested and effective backend metadata;
- public/default behavior;
- OpenAPI and configuration contract;
- no-fallback or explicit-fallback semantics;
- health/readiness behavior;
- rollout and rollback procedure;
- build-scoped compatibility gates.

Preferred API direction, if public selection is approved:

```text
/search?mode=dense&vector_backend=file
/search?mode=dense&vector_backend=qdrant
/search?mode=hybrid&vector_backend=qdrant
```

Backend-specific strategy modes remain discouraged.

### 6.2 Optional exact diagnostic for depth-100 differences

Status: **optional, not a blocker**

An exact Qdrant diagnostic at `candidate_k=100` may be run for:

```text
diffusion_models_001
rag_evaluation_001
```

This could further confirm that the four stable differences are HNSW recall or
score-boundary effects. The current slice does not require it because final-set
parity is complete and the strict evidence gate is green.

### 6.3 Hydration and cold-start investigation

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
- profile copy/validation costs;
- preserve explicit missing-document semantics;
- avoid backend-specific hydration logic.

Fresh Qdrant first-request overhead is also significant because backend/channel
creation is lazy.

### 6.4 Integration-test memory/lifecycle hardening

Status: **technical debt**

A previous monolithic heavy pytest process produced a transient memory failure,
while separate processes passed.

Potential work:

- instrument RSS, committed memory, and VRAM;
- verify object release between TestClient sessions;
- consider lightweight fixtures;
- consider CPU-only integration mode;
- keep heavy groups separate until hardened.

### 6.5 Stronger embeddings and retrieval profiles

Status: **planned**

Potential profiles:

```text
fast_default
scientific_semantic
citation_aware
hybrid
```

Any embedding change requires:

- new retrieval build;
- build-scoped Qdrant collection;
- dimension/normalization/distance validation;
- Golden Set rerun;
- profile sweep;
- hybrid comparison and performance rerun.

### 6.6 Topic interpretation and UI polish

Status: **planned**

Potential improvements:

- stronger labels;
- representative-term cleanup;
- cluster naming/versioning;
- cluster stability checks;
- paper comparison;
- clearer evidence presentation.

### 6.7 Source expansion

Status: **planned through source viability gate**

Possible sources:

- Papers with Code;
- PubMed / Europe PMC;
- selective Semantic Scholar enrichment;
- additional conference/repository sources.

Every source must pass identity, value, overlap, access, provenance, refresh,
and reconcile-safety gates.

### 6.8 Full text, RAG, personalization, datasets

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

Not part of Qdrant Hybrid Evaluation v1:

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
one validated vertical slice at a time
```

The controlled hybrid question is now answered for the active build:

```text
Qdrant ef_256 preserves the complete final hybrid result set across the full
34-query, 136-scenario evaluation matrix without measured quality regression.
```

The next retrieval question is:

```text
Should Qdrant remain experimental, become an explicit opt-in backend, or be
selected at deployment composition—and what observable rollout and rollback
contract would make that decision safe?
```

No promotion is required merely because the technical evidence is positive.
