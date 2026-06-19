# Retrieval Serving Checkpoint v1

## Document status

```text
status: implemented / green / accepted checkpoint
slice: Retrieval Serving Checkpoint v1
branch: maintenance/search-runtime-checkpoint-v1
public behavior change: none
implementation behavior change: none to API/search/runtime semantics
purpose: prevent duplicate retrieval/Qdrant/runtime/ranking work and provide a lightweight serving gate
```

This checkpoint records the current accepted state of the retrieval,
dense-backend, Qdrant, runtime, hybrid-evaluation, and ranking-evaluation layers.

The purpose is not to add another serving implementation. The purpose is to make
future slices safer by explicitly separating:

```text
already completed work
from
valid future work
from
deferred / out-of-scope work
```

The project has already completed several retrieval-serving hardening slices.
Before writing new scripts or changing runtime behavior, this document defines
what must not be reimplemented.

---

## 1. Current accepted baseline

Current corpus and retrieval baseline:

```text
canonical_doc_count = 60954
canonical_multisource_docs = 9192
doi_count = 10183
arXiv backbone = 60000
ACL-family docs = 957

retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]
dense_vectors_normalized = true
```

Current Golden Set baseline:

```text
enabled_queries = 34
explicit_canonical_labeled_queries = 34
weak_pattern_only_enabled_queries = 0
```

Current public search behavior:

```text
/search?mode=lexical -> file-backed lexical search
/search?mode=dense   -> exact file dense search
/search?mode=hybrid  -> file lexical + exact file dense hybrid search
```

Current experimental Qdrant behavior:

```text
/experimental/search/qdrant -> explicit experimental Qdrant dense search
```

Current operational guarantees:

```text
Qdrant is optional.
Qdrant is not canonical truth.
Qdrant is not required for /health readiness.
Qdrant does not change /search defaults.
Qdrant does not introduce fallback.
```

Current ranking-evaluation decision:

```text
reference_behavior = unranked hybrid
recommended_outcome = reject_heuristic_reranking
public_default_change = false
```

---

## 2. Already completed / do not redo

### 2.1 Dense Search Backend Abstraction v1

Status:

```text
done / green / merged
```

Completed:

```text
DenseSearchBackend
├── FileDenseBackend
└── QdrantDenseBackend
```

The dense backend abstraction already defines:

- backend-neutral dense candidate retrieval;
- `DenseSearchRequest`;
- `DenseSearchCandidate`;
- `DenseSearchBackendInfo`;
- `DenseSearchBackendResult`;
- exact file-dense reference semantics;
- Qdrant search profiles;
- typed dense backend exceptions;
- lazy runtime composition;
- experimental Qdrant endpoint integration;
- file/Qdrant comparison tooling migration;
- profile-sweep migration;
- backend/parity/regression tests.

Do not redo:

- backend abstraction;
- `FileDenseBackend`;
- `QdrantDenseBackend`;
- Qdrant profile objects;
- exact file dense kernel;
- backend-neutral candidate result types.

### 2.2 Qdrant Failure Contract v1

Status:

```text
done / green / merged
```

Completed typed mapping:

```text
DenseBackendRequestError       -> 400 dense_backend_bad_request
DenseBackendUnavailableError   -> 503 dense_backend_unavailable
DenseBackendCompatibilityError -> 503 dense_backend_incompatible
DenseBackendResultError        -> 503 dense_backend_invalid_result
```

Completed guarantees:

- typed dense backend failures are preserved across the API boundary;
- Qdrant hydration miss fails explicitly;
- experimental Qdrant endpoint does not silently skip missing canonical IDs;
- experimental Qdrant endpoint does not fall back to file dense retrieval;
- `/health` remains Qdrant-independent;
- `/runtime` can expose Qdrant unavailable state without making the API unhealthy;
- Qdrant stop/start recovery is supported;
- runtime reload clears the cached Qdrant backend.

Do not redo:

- typed dense backend exception mapping;
- hydration-miss error semantics for experimental Qdrant;
- no-fallback guarantee;
- Qdrant-independent health behavior.

### 2.3 Qdrant Runtime Observability v1

Status:

```text
done / green / merged
```

Completed runtime behavior:

```text
GET /runtime
GET /runtime?refresh_qdrant=true
```

Completed diagnostics include:

- Qdrant configured/unconfigured state;
- collection existence;
- collection compatibility;
- corpus/point count comparison;
- vector size and distance;
- profile/build information;
- backend creation state;
- request/success/failure counters;
- bounded last failure evidence;
- encode/search/hydration/total timings;
- requested/effective backend;
- explicit `fallback_applied=false`;
- reload reset behavior.

Do not redo:

- basic Qdrant runtime diagnostics;
- Qdrant health isolation;
- request/success/failure counters;
- cached/fresh runtime probe semantics.

### 2.4 Qdrant File-Dense Parity Checkpoint v1

Status:

```text
done / green / merged
```

Completed evidence:

- exact file-dense reference semantics;
- Qdrant mapping and payload audit;
- selected ANN profile comparison;
- exact Qdrant diagnostic profile;
- deterministic repeated-run evidence;
- root-cause classification of default HNSW mismatch;
- strict validation requirements.

Selected profile:

```text
name = ef_256
exact = false
hnsw_ef = 256
```

Exact diagnostic profile:

```text
name = exact
exact = true
```

Do not redo:

- basic file/Qdrant dense parity investigation;
- exact Qdrant diagnostic oracle;
- `ef_256` selection for the current build and Golden Set;
- mapping/payload audit contract.

### 2.5 Qdrant Serving Performance v1

Status:

```text
done / green / merged
```

Completed evidence:

- backend-only FileDenseBackend vs QdrantDenseBackend benchmark;
- end-to-end public file-dense `/search` vs experimental Qdrant endpoint;
- gRPC serving transport validation;
- repeated zero-error concurrency evidence;
- strict read-only benchmark behavior;
- integrated regression / DoD closure.

Do not redo:

- baseline Qdrant serving performance slice;
- basic gRPC vs unstable REST serving decision;
- read-only serving benchmark contract.

### 2.6 Qdrant Hybrid Evaluation v1

Status:

```text
done / green / merged
```

Completed controlled comparison:

```text
lexical candidates + FileDenseBackend
vs
lexical candidates + QdrantDenseBackend
```

Held constant:

- query normalization;
- encoder;
- lexical branch;
- candidate budgets;
- hybrid normalization;
- hybrid weights;
- merge kernel;
- optional ranking;
- Golden Set metrics.

Accepted evidence:

```text
queries = 34
scenarios = 136
successful_scenarios = 136
errors = 0
fallback = 0
blocking_classifications = 0
determinism_failures = 0
final_result_set_parity = 136 / 136
exact_final_order = 134 / 136
exact_dense_plus_final_parity = 132 / 136
```

Interpretation:

```text
Qdrant preserves final hybrid result sets under the controlled evaluation matrix,
but public dense and hybrid search remain file-backed.
```

Do not redo:

- paired file/Qdrant hybrid comparison;
- shared hybrid merge extraction;
- strict evaluation hydration;
- Qdrant hybrid evidence validator.

### 2.7 Ranking Evaluation and Hardening v1

Status:

```text
done / green / merged
```

Accepted evidence:

```text
evaluation_build_id = 20260504T164021Z
corpus_doc_count = 60954
enabled_queries = 34
ranking_profiles = 9
candidate_depths = 2
evaluation_runs = 612
runtime_errors = 0
determinism_failures = 0
candidate_pool_sensitivity_rows = 306
recommended_outcome = reject_heuristic_reranking
reference_behavior = unranked hybrid
```

Accepted conclusion:

```text
No evaluated heuristic ranking profile exceeded the unranked hybrid baseline.
The current heuristic ranking materially reduces query-relevance quality and
removes explicitly relevant papers from top-k results.
```

Do not redo:

- current heuristic ranking evaluation;
- ranking evidence validator;
- ranking evidence freshness check;
- ranking evidence regression wrapper;
- the decision to keep unranked hybrid as reference.

---

## 3. Current accepted serving semantics

### 3.1 Public search

Public search modes remain:

```text
lexical
dense
hybrid
```

Dense implementation is internal:

```text
file
qdrant
```

Current public behavior:

```text
/search?mode=lexical -> file lexical / DB lexical depending on runtime
/search?mode=dense   -> exact file dense
/search?mode=hybrid  -> file lexical + exact file dense hybrid
```

### 3.2 Experimental Qdrant

Qdrant remains exposed only through:

```text
/experimental/search/qdrant
```

The endpoint:

- requires file runtime;
- uses the current embedding model;
- uses `QdrantDenseBackend`;
- uses the configured Qdrant profile;
- hydrates against the active file runtime;
- fails explicitly on backend, compatibility, or result errors;
- does not fall back to file dense retrieval.

### 3.3 Runtime and health

```text
/health
```

is Qdrant-independent.

```text
/runtime
```

includes Qdrant diagnostics when requested by the runtime snapshot.

If Qdrant is unavailable:

```text
/health -> still healthy if file runtime is ready
/runtime -> qdrant.ok=false with diagnostic error
/experimental/search/qdrant -> structured 503
/search?mode=dense -> file dense remains available
```

### 3.4 Ranking

Default search remains unranked:

```text
rank = false
```

Optional ranking remains explicit:

```text
rank = true
```

The accepted ranking evidence rejects promotion of the current heuristic
reranking formula.

---

## 4. Implemented lightweight checkpoint gate

The checkpoint now includes:

```text
scripts/validation/check_retrieval_serving_checkpoint.py
tests/smoke/test_retrieval_serving_checkpoint.py
```

Default command:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint
```

Default required steps:

```text
ranking_evidence_regression
qdrant_hybrid_evidence
```

Optional steps:

```text
qdrant_serving_performance_evidence
qdrant_collection_live
api_runtime_smoke
```

Extended command:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint ^
  --include-serving-performance-evidence ^
  --include-qdrant-collection-live ^
  --include-api-smoke
```

The wrapper:

- composes existing validators;
- validates accepted evidence;
- does not rerun heavy benchmarks by default;
- does not rebuild retrieval artifacts;
- does not require Qdrant for `/health`;
- does not change `/search`;
- does not promote Qdrant;
- does not introduce fallback.

Generated outputs:

```text
artifacts/reports/validation/retrieval_serving_checkpoint_latest.json
artifacts/reports/validation/retrieval_serving_checkpoint_latest.md
artifacts/reports/validation/history/retrieval_serving_checkpoint_<timestamp>.json
artifacts/reports/validation/history/retrieval_serving_checkpoint_<timestamp>.md
```

Generated outputs are local evidence artifacts and should not be committed unless
a separate artifact-retention policy explicitly says otherwise.

Accepted local evidence:

```text
pytest tests/smoke/test_retrieval_serving_checkpoint.py -q
→ 9 passed

python -m scripts.validation.check_retrieval_serving_checkpoint
→ required_failed_count = 0

python -m scripts.validation.check_retrieval_serving_checkpoint ^
  --include-serving-performance-evidence ^
  --include-qdrant-collection-live ^
  --include-api-smoke
→ required_failed_count = 0
```

---

## 5. Work explicitly deferred

The following are valid future topics, but are not part of this checkpoint:

```text
public Qdrant promotion
deployment-level vector backend selector
Qdrant-backed public dense search
Qdrant-backed public hybrid search
Qdrant-backed similar-paper migration
filter pushdown into Qdrant
new embedding model
retrieval rebuild
larger Golden Set expansion
dataset release
RAG / full-text retrieval
Airflow / Kafka / Kubernetes orchestration
```

Important deferred candidate:

```text
ML_RADAR_VECTOR_BACKEND=file|qdrant
```

This should be treated as a future deployment-level selector design, not an
immediate public behavior change.

---

## 6. Remaining gaps that are actually new

Valid next workstreams:

### 6.1 Search API Semantics Cleanup v1

Synchronize API, README, architecture, roadmap, runtime, Qdrant, ranking, and
checkpoint documentation.

Non-goals:

```text
no API behavior change
no Qdrant promotion
no fallback
no retrieval rebuild
no ranking change
```

### 6.2 Dataset Export Contract v0.1

Define future metadata-only public export schema, provenance, license, checksum,
and data-card policy. No public upload in that slice.

### 6.3 Deployment-Level Vector Backend Selector Design v1

Design:

```text
ML_RADAR_VECTOR_BACKEND=file|qdrant
```

Only as a future deployment-level design. No default change.

---

## 7. Definition of Done for this checkpoint

Complete when:

- [x] checkpoint document exists;
- [x] completed retrieval/Qdrant/ranking slices are recorded;
- [x] work that must not be redone is listed;
- [x] retrieval-serving checkpoint gate exists;
- [x] smoke tests exist;
- [x] default gate is lightweight;
- [x] extended local gate is available;
- [x] no public API behavior changes were made;
- [x] no runtime behavior changes were made;
- [x] no Qdrant promotion was performed;
- [x] no generated reports are committed.

---

## 8. Operational interpretation

This checkpoint changes how the project plans and validates retrieval-serving
work. It does not change how public search runs.

Accepted interpretation:

```text
Dense/Qdrant/runtime hardening is already substantially complete.
Do not start another dense-backend or Qdrant-failure slice from scratch.
The current lightweight gate validates accepted retrieval-serving evidence.
Public /search remains file-backed.
Qdrant remains explicitly experimental.
```

A future public Qdrant promotion remains possible, but it must be handled as a
separate deployment-level decision with explicit API semantics, regression
evidence, and rollback policy.
