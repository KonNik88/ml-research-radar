# ML Research Radar — Roadmap

## Document status

```text
document: primary living roadmap
checkpoint: Qdrant Runtime Observability v1
checkpoint date: 2026-06-11
implementation state: green on feature branch, pending PR merge
implementation commit: f89574e
previous checkpoint: Qdrant Failure Contract v1 merged in PR #17
main merge commit before current branch: 7539dd4
public Qdrant promotion: not performed
```

This roadmap describes the current validated state of **ML Research Radar**, the architectural invariants that must remain stable, and the recommended order of future work.

The project prefers complete, validated vertical slices over broad feature expansion.

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

The platform collects partially overlapping observations from multiple sources, reconciles them into paper-level canonical entities, and builds rebuildable retrieval, serving, evidence, analytics, API, and UI layers above the canonical corpus.

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

The following layers are derived and rebuildable:

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

### 2.2 Postgres

```text
Postgres = rebuildable materialized serving layer
```

It supports browse/filter, DB lexical search, source/reference inspection, artifact serving, and API queries.

It is not canonical paper truth.

### 2.3 Retrieval

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

### 2.4 Artifact evidence

GitHub, Hugging Face, datasets, models, demos, and repositories are separate artifact entities linked to papers through evidence.

```text
CanonicalDocument
↕ trusted relation / provenance
ArtifactEntity
```

Artifact metadata must not overwrite paper bibliography or paper identity.

### 2.5 Qdrant

```text
Qdrant = optional derived dense-serving backend
```

Qdrant is not:

- a paper source;
- canonical truth;
- a retrieval strategy;
- a required dependency of general service health.

The public retrieval strategies remain:

```text
lexical
dense
hybrid
```

The dense implementation backend is an internal concern:

```text
file
qdrant
```

### 2.6 Streamlit

```text
Streamlit = thin client over FastAPI
```

Business logic, retrieval, ranking, canonical merge, artifact normalization, and clustering remain outside the UI.

---

## 3. Current green checkpoint

Current corpus and retrieval baseline:

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

Current Qdrant collection:

```text
collection = ml_radar_dense_benchmark_v1
points_count = 60954
vector_size = 384
distance = Cosine
status = green
optimizer_status = ok
```

Current Golden Set:

```text
enabled_queries_count = 34
explicit_canonical_labeled_enabled_count = 34
weak_pattern_enabled_count = 0
```

Current Qdrant profile evidence:

```text
default → exact order 33/34, one stable ANN recall mismatch
ef_128  → exact order 33/34, one stable ANN recall mismatch
ef_256  → exact order 34/34
ef_512  → exact order 34/34
exact   → exact order 34/34
```

Selected experimental ANN profile:

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

`ef_256` is the minimum currently tested ANN profile that restores full order parity on the active build and 34-query Golden Set. It is not a permanent universal constant.

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
- aligned OpenAlex, Semantic Scholar, and Crossref enrichment;
- ACL Anthology integration;
- canonical contract validation;
- controlled promotion of candidate corpus states.

### 4.2 Incremental refresh and promotion safety

Status: **done / green**

Implemented lifecycle:

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
- retrieval build manifest;
- artifact validation;
- file runtime;
- query evaluation;
- search-quality experiments;
- controlled experiments;
- Golden Set validation;
- similar-paper retrieval.

Current public file-dense semantics:

```python
query_vector = encoder.encode(
    [query],
    convert_to_numpy=True,
    normalize_embeddings=True,
)[0].astype(np.float32)

scores = stored_embeddings @ query_vector
order = np.argsort(scores)[::-1]
```

The full sort is the current exact reference behavior. Scale optimization is a separate future concern.

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

### 4.6 Paper features, ranking, paper detail, similar papers

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

These are transparent derived heuristics, not canonical truth or learned quality labels.

### 4.7 Discovery API

Status: **done / green**

Current product endpoints include:

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

Discovery validation is green.

### 4.8 Streamlit Discovery UI

Status: **done / green**

The UI is a thin API client and supports:

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

Current topic layer:

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

Cluster IDs and labels are build-scoped derived navigation aids, not canonical taxonomy.

### 4.10 Retrieval evaluation and Golden Set Expansion v2

Status: **done / green**

Completed:

- 34 enabled Golden Set queries;
- 34 explicit canonical relevance labels;
- no weak-pattern-only enabled queries;
- parity, ranking, search-quality, and controlled evaluation tooling;
- query-group expansion across modern ML topics.

Important rule:

```text
Do not change retrieval defaults by intuition.
Use measured query-level and group-level evidence.
```

### 4.11 Qdrant serving parity

Status: **done / green**

The parity slice established:

- collection mapping is correct;
- persisted vectors and Qdrant vectors are compatible;
- build ID and dense index mapping are correct;
- exact Qdrant matches exact file dense;
- the previous mismatch was an approximate HNSW recall difference;
- `ef_256` restores full parity on the current Golden Set.

Public `/search` was intentionally not switched to Qdrant.

### 4.12 Dense Search Backend Abstraction v1

Status: **done / green; merged into `main` in PR #16**

Implemented internal architecture:

```text
DenseSearchBackend
├── FileDenseBackend
└── QdrantDenseBackend
```

Implemented contracts:

- `DenseSearchRequest`;
- `DenseSearchCandidate`;
- `DenseSearchBackendInfo`;
- `DenseSearchBackendResult`;
- typed backend exceptions;
- `QdrantSearchProfile`;
- read-only `QdrantStore` protocol.

Implemented responsibility boundary:

```text
prepared query vector
→ dense backend
→ backend-neutral candidates
```

Backends do not own:

- text validation;
- model loading;
- query encoding;
- document hydration;
- hybrid merge;
- product ranking;
- pagination;
- fallback policy;
- API serialization.

`dense_backend.py` is now the authoritative runtime owner of exact file-dense candidate semantics.

`parity.py` depends on the backend layer and provides report adapters, comparison, mapping audit, determinism, mismatch details, and classification.

Qdrant improvements:

- explicit `exact` and `hnsw_ef`;
- selected `ef_256` runtime profile;
- constructor injection;
- compatibility validation cached per backend lifecycle;
- per-result payload/build/mapping validation;
- strict dense-ID mapping when artifacts are available;
- no hidden fallback;
- no collection mutation.

Adoption completed in:

- experimental Qdrant API;
- file/Qdrant comparison;
- selected `ef_256` comparison;
- exact diagnostic comparison;
- full profile sweep.

Public behavior unchanged:

```text
/search?mode=dense  → file dense
/search?mode=hybrid → file dense component
/health             → Qdrant-independent
similar papers      → unchanged
Discovery API       → unchanged
Streamlit           → unchanged
```

### 4.13 Qdrant Failure Contract v1

Status: **done / green; merged into `main` in PR #17**

The API/runtime boundary now preserves the existing typed dense-backend failure categories:

```text
DenseBackendRequestError       → 400 dense_backend_bad_request
DenseBackendUnavailableError   → 503 dense_backend_unavailable
DenseBackendCompatibilityError → 503 dense_backend_incompatible
DenseBackendResultError        → 503 dense_backend_invalid_result
```

Additional guarantees:

- Qdrant candidates that cannot be hydrated from the active canonical runtime now fail explicitly;
- no hidden fallback to file dense exists;
- general `/health` remains independent of optional Qdrant availability;
- public `/search?mode=dense` and `/search?mode=hybrid` remain file-backed;
- transient Qdrant stop/start recovery succeeds without an API restart;
- runtime reload clears and recreates the cached Qdrant backend;
- successful experimental Qdrant responses remain compatible.

The slice does not add public backend selection, observability state, performance benchmarks, hybrid Qdrant serving, or fallback orchestration.

### 4.14 Qdrant Runtime Observability v1

Status: **implemented / green on feature branch; pending PR merge**

The runtime now exposes bounded, non-persistent operational diagnostics for the
experimental Qdrant dense-serving path without changing public search defaults.

Implemented probe semantics:

```text
GET /runtime?refresh_qdrant=true
→ forced live Qdrant probe

GET /runtime
→ cached probe while cache age <= TTL

default probe TTL
→ 30 seconds
```

Implemented runtime diagnostics include:

- Qdrant collection health and point-count compatibility;
- selected profile, `exact`, and `hnsw_ef`;
- retrieval build ID;
- whether the backend object has been created;
- whether backend compatibility has been checked;
- request, success, and failure counters;
- last request, success, and failure timestamps;
- current last status: `never`, `ok`, or `error`;
- bounded last-failure category, stage, and message;
- last result count;
- stage timings for encode, Qdrant search, hydration, and total time;
- requested and effective vector backend;
- explicit `fallback_applied=false`.

Operational-state rules:

```text
successful request
→ last_status = ok
→ effective_vector_backend = qdrant

failed request
→ last_status = error
→ effective_vector_backend = null
→ stable failure category retained

successful recovery
→ last_status returns to ok
→ last_failure_* evidence remains available

runtime load or reload
→ backend cache, probe cache, and bounded operational state reset
```

The runtime does not store query text, vectors, response payloads, traceback
objects, or unbounded history.

Public behavior remains unchanged:

```text
/search?mode=dense  → file dense
/search?mode=hybrid → file dense component
/health             → Qdrant-independent
Qdrant fallback     → absent
```

---


## 5. Validation evidence for the current feature branch

Qdrant Runtime Observability v1 targeted tests:

```text
Qdrant backend composition / observability = 6 passed
API runtime smoke = 7 passed
API error contract = 4 passed
API reload lifecycle = 4 passed
Discovery integration = 34 passed, 4 expected DB-only skips
```

Verified live probe semantics:

```text
forced /runtime probe
→ probe_cached = false
→ probe_cache_age_sec = 0.0

immediate repeated /runtime probe
→ probe_cached = true
→ same probe_checked_at
→ cache age within 30-second TTL
```

Verified successful experimental request state:

```text
request_count = 1
success_count = 1
failure_count = 0
last_status = ok
backend_created = true
compatibility_checked = true
compatibility_ok = true
requested_vector_backend = qdrant
effective_vector_backend = qdrant
fallback_applied = false
last_result_count = 3
last_timing_ms contains encode/search/hydrate/total
```

Verified failure and health-isolation state:

```text
Qdrant stopped
→ /experimental/search/qdrant = 503 dense_backend_unavailable
→ /runtime.qdrant.ok = false
→ failure_count increments
→ last_status = error
→ last_failure_stage = backend_search
→ effective_vector_backend = null
→ fallback_applied = false
→ /health remains 200 and ready = true
→ public file dense /search remains 200
```

Verified recovery state:

```text
Qdrant restarted
→ next experimental request succeeds without API reload
→ request_count = 3
→ success_count = 2
→ failure_count = 1
→ last_status = ok
→ effective_vector_backend = qdrant
→ previous last_failure_* evidence remains available
```

Green validators and integrated checks:

- Qdrant collection strict validator;
- experimental Qdrant API strict validator;
- 34-query file/Qdrant comparison;
- Golden Set strict validator;
- Discovery API strict validator;
- topic clusters strict validator;
- topic projection strict validator;
- Streamlit static strict validator;
- integrated Discovery regression;
- full strict Definition of Done.

Current retrieval comparison evidence:

```text
enabled queries = 34
selected profile = ef_256
selected full match = true
exact full match = true
error_count = 0
blocking_classification_count = 0
```

Milestone closure:

```text
canonical_doc_count = 60954
canonical_multisource_docs = 9192
dod_passed = true
required_failed_count = 0
```

Known non-blocking observation:

- the low-level Windows socket error copied into the best-effort live-probe
  `error` field may be locale-encoded poorly;
- stable failure classification remains available through
  `last_failure_category=dense_backend_unavailable`;
- the public error response and server-side exception logging remain correct.


## 6. Near-term roadmap

Recommended order after merge of the observability PR:

```text
1. Warm/cold latency and concurrency evidence.
2. Integration-test memory/lifecycle hardening.
3. Controlled hybrid file-vs-Qdrant evaluation.
4. Explicit public-promotion decision.
5. Retrieval-quality profiles and stronger scientific embeddings.
6. Topic labeling and product polish.
7. New sources through the viability gate.
8. Full text / RAG / personalization / dataset releases.
```

### 6.1 Latency and concurrency evaluation

Status: **next**

Measure separately:

- encode time;
- backend search time;
- hydration time;
- ranking time where applicable;
- total API time;
- warm versus cold execution;
- p50, p95, and max;
- file versus Qdrant;
- sequential versus concurrent requests;
- local versus deployed network conditions;
- process RSS, Windows committed memory, and VRAM;
- behavior after corpus growth.

The first live observability smoke already showed a large cold/warm encode
difference. That is useful evidence, not a benchmark conclusion.

Qdrant does not need to beat local NumPy at 60,954 documents to remain
architecturally useful, but its operational value must be demonstrated rather
than assumed.

### 6.2 Integration-test memory/lifecycle hardening

Status: **next technical debt**

A combined heavy pytest process previously produced a transient memory failure,
while the same files passed in separate Python processes.

Likely contributors:

- repeated app startup and shutdown;
- repeated loading of 60,954 canonical objects and retrieval artifacts;
- PyTorch/CUDA allocator retention;
- TestClient/module lifecycle;
- reload cycles.

Observed runtime behavior is correct:

```text
initial model load → model_reused=false
runtime reload     → model_reused=true
Qdrant backend     → recreated after reload
observability      → reset after reload
```

Future work:

- instrument process RSS, commit memory, and VRAM;
- verify object release between TestClient sessions;
- consider session-scoped lightweight fixtures;
- consider CPU-only integration mode;
- keep heavy integration groups in separate processes until hardened.

This debt is separate from Qdrant backend correctness.

### 6.3 Controlled hybrid evaluation

Status: **planned**

Compare:

```text
lexical + FileDenseBackend
vs
lexical + QdrantDenseBackend
```

Keep common:

- query encoder;
- lexical candidate generation;
- score normalization;
- hybrid merge;
- ranking;
- response schema;
- Golden Set.

Do not implement hybrid logic inside `QdrantDenseBackend`.

### 6.4 Public Qdrant promotion decision

Status: **blocked on performance and hybrid evidence**

Possible outcomes:

- keep Qdrant experimental;
- expose an opt-in `vector_backend`;
- select backend at deployment composition with explicit metadata;
- postpone promotion until corpus size or request load grows.

No promotion is a valid evidence-based outcome.

### 6.5 Stronger embeddings and retrieval profiles

Status: **planned**

Potential profiles:

```text
fast_default
scientific_semantic
citation_aware
hybrid
```

Any change requires:

- a new retrieval build;
- a new build-scoped Qdrant collection or controlled rebuild;
- revalidation of vector dimension, normalization, and distance;
- Golden Set rerun;
- profile sweep rerun;
- comparison and regression rerun;
- explicit update of the selected profile.

### 6.6 Topic cluster interpretation and UI polish

Status: **planned**

Potential improvements:

- stronger cluster label generation;
- representative-term cleanup;
- cluster naming/versioning;
- cluster stability checks;
- paper-comparison UI;
- better evidence presentation.

Clusters remain derived and build-scoped.

### 6.7 Source expansion

Status: **planned through source viability gate**

Possible sources include:

- Papers with Code;
- PubMed / Europe PMC;
- Semantic Scholar selective enrichment;
- additional conference and repository sources.

Every source must pass:

- identity quality;
- metadata value;
- overlap analysis;
- rate-limit and access viability;
- provenance requirements;
- incremental refresh behavior;
- canonical reconcile safety.

### 6.8 Full text, RAG, personalization, datasets

Status: **later product layers**

Potential directions:

- full-text acquisition and chunking;
- evidence-grounded RAG;
- citation-preserving answer generation;
- saved papers and watchlists;
- personalized feed;
- why-recommended explanations;
- paper comparison;
- dataset releases.

## 7. Engineering and MLOps backlog

Add only when justified by real operational need:

- structured logging;
- Prometheus and Grafana;
- Loki/ELK;
- OpenTelemetry and Jaeger;
- secrets management;
- Alembic;
- Airflow for batch pipelines;
- Ray for distributed workloads;
- Kafka for real event-driven flows;
- Kubernetes after service and deployment complexity justify it;
- full React/Next.js frontend after backend contracts stabilize.

Avoid technology-driven architecture.

---

## 8. Explicit non-goals of the current checkpoint

Not part of the Qdrant Runtime Observability v1 PR:

- public `vector_backend` parameter;
- public Qdrant promotion;
- hidden or explicit fallback orchestration;
- public `/search` success-response schema expansion;
- switching public dense/hybrid to Qdrant;
- DB-native dense or hybrid;
- lexical backend abstraction;
- similar-paper migration;
- filter pushdown;
- circuit breaker or retry framework;
- unbounded or persistent failure-history storage;
- Prometheus/OpenTelemetry integration;
- latency or concurrency benchmarking;
- embedding-model replacement;
- reranking redesign;
- canonical refresh;
- new sources;
- full text;
- RAG;
- topic-cluster rebuild;
- Streamlit redesign.

---

## 9. Working and validation conventions

### Git

- Git operations are run in Git Bash.
- Python, pytest, validators, and scripts are run in Anaconda Prompt.
- Avoid `git add .`.
- Stage intentional files explicitly.
- Keep local `notebooks/Untitled.ipynb` outside project commits.

### Generated artifacts

`artifacts/` is ignored in the active repository workflow.

Therefore:

- report-generating commands do not require `git restore` when files are ignored and untracked;
- always confirm with `git status`;
- ignored reports are not part of routine commits;
- tracked baselines, if introduced later, require an explicit policy.

### Heavy tests

Until memory lifecycle is hardened:

- run heavy API integration files in separate Python processes;
- run comparison and profile sweep as separate commands;
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

The current next product/engineering question is no longer “can Qdrant return neighbors?” It is:

```text
Does Qdrant provide enough operational, scaling, filtering, isolation,
or concurrency value to justify controlled public exposure?
```

That decision must be made from evidence, not from the presence of a vector database.
