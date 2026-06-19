# Retrieval Serving Checkpoint v1

## Document status

```text
status: proposed checkpoint / anti-duplication audit
slice: Retrieval Serving Checkpoint v1
suggested branch: maintenance/retrieval-serving-checkpoint-v1
public behavior change: none
implementation change: none in this checkpoint
purpose: prevent duplicate work before the next retrieval/serving slice
```

This checkpoint records the current accepted state of the retrieval, dense-backend,
Qdrant, runtime, hybrid-evaluation, and ranking-evaluation layers.

The purpose is not to add another serving implementation. The purpose is to make
the next slice safer by explicitly separating:

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

Current public search behavior:

```text
/search?mode=lexical -> file-backed lexical search
/search?mode=dense   -> file-backed dense search
/search?mode=hybrid  -> file-backed hybrid search
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

- the backend abstraction;
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
/search?mode=dense  -> file dense
/search?mode=hybrid -> file dense component
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

may include Qdrant diagnostics.

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

## 4. Work that is explicitly deferred

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

## 5. Remaining gaps that are actually new

The following workstreams appear to be valid new work rather than duplicate
runtime/Qdrant implementation.

### 5.1 Retrieval Serving Regression Wrapper v1

Problem:

```text
Retrieval/Qdrant/ranking validators exist, but the project lacks one compact
serving-checkpoint command that explains what is being validated and why.
```

Possible goal:

```text
scripts/validation/check_retrieval_serving_checkpoint.py
```

Potential responsibilities:

- validate accepted ranking evidence regression;
- validate Qdrant collection compatibility where Qdrant artifacts are available;
- validate experimental Qdrant API evidence or mark it intentionally skipped;
- validate Qdrant hybrid evidence freshness or accepted-report integrity;
- validate API/runtime smoke expectations;
- emit a compact JSON/Markdown checkpoint report;
- distinguish required checks from optional environment-dependent checks.

Non-goals:

- do not rerun heavy benchmarks by default;
- do not rebuild retrieval artifacts;
- do not require Qdrant for general file-runtime health;
- do not change `/search` behavior.

### 5.2 Search API Semantics Cleanup v1

Problem:

```text
API docs, runtime docs, Qdrant docs, and ranking docs now contain overlapping
search semantics. This is manageable but can drift.
```

Possible goal:

- consolidate `/search`, `/experimental/search/qdrant`, `/runtime`, and
  ranking semantics in `api_reference.md`;
- cross-link to the accepted checkpoint docs;
- clearly separate public behavior from experimental behavior;
- document that public dense/hybrid remain file-backed.

Non-goals:

- no API behavior change;
- no new endpoint;
- no Qdrant promotion.

### 5.3 Dataset Export Contract v0.1

Problem:

```text
The project plans a future Kaggle/Hugging Face dataset release, but public
dataset release requires schema, provenance, license, and versioning policy.
```

Possible goal:

- define metadata-only public export schema;
- define excluded fields;
- define build ID / checksum / version policy;
- define dataset card requirements;
- define whether embeddings are included in the first release.

Non-goals:

- no public upload in this slice;
- no corpus rebuild;
- no licensing shortcuts.

### 5.4 Deployment-Level Vector Backend Selector Design v1

Problem:

```text
Qdrant has strong experimental evidence, but public promotion is a separate
deployment/API semantics decision.
```

Possible goal:

```text
ML_RADAR_VECTOR_BACKEND=file|qdrant
```

Only as design first.

Non-goals:

- do not enable by default;
- do not silently switch `/search`;
- do not introduce fallback;
- do not remove file dense as reference.

---

## 6. Recommended next slice

Recommended immediate next code slice:

```text
Retrieval Serving Regression Wrapper v1
```

Suggested branch:

```text
validation/retrieval-serving-regression-v1
```

Suggested files to inspect before implementation:

```text
scripts/validation/run_discovery_api_regression.py
scripts/validation/check_qdrant_collection.py
scripts/validation/check_qdrant_hybrid_evaluation.py
scripts/validation/check_qdrant_serving_performance.py
scripts/validation/check_ranking_evidence_regression.py
scripts/validation/check_retrieval_eval.py
scripts/validation/run_retrieval_checks.py

configs/qdrant_hybrid_evaluation_v1.yaml
configs/qdrant_serving_performance_v1.yaml
configs/qdrant_parity_v2.yaml
configs/ranking_evaluation_v1.yaml

tests/smoke/test_qdrant_regression_runner.py
tests/smoke/test_qdrant_hybrid_evaluation_validator.py
tests/smoke/test_qdrant_serving_performance.py
tests/smoke/test_ranking_evidence_regression.py
tests/integration/test_api_smoke.py
tests/integration/test_api_errors.py
tests/integration/test_api_reload.py
```

Suggested output:

```text
artifacts/reports/validation/retrieval_serving_checkpoint_latest.json
artifacts/reports/validation/retrieval_serving_checkpoint_latest.md
artifacts/reports/validation/history/retrieval_serving_checkpoint_<timestamp>.json
artifacts/reports/validation/history/retrieval_serving_checkpoint_<timestamp>.md
```

Suggested acceptance:

```text
required_failed_count = 0
public_search_behavior_changed = false
qdrant_required_for_health = false
fallback_allowed = false
ranking_recommendation = reject_heuristic_reranking
file_dense_reference_preserved = true
```

---

## 7. Definition of Done for this checkpoint

This checkpoint is complete when:

- [ ] this document is committed;
- [ ] it records completed retrieval/Qdrant/ranking slices;
- [ ] it explicitly lists work that must not be redone;
- [ ] it identifies the next non-duplicative code slice;
- [ ] no public API behavior changes are made;
- [ ] no runtime behavior changes are made;
- [ ] no generated reports are committed.

Recommended commit:

```text
docs: record retrieval serving checkpoint
```

---

## 8. Operational interpretation

This checkpoint changes how the project plans work, not how the application
runs.

The accepted interpretation is:

```text
Dense/Qdrant/runtime hardening is already substantially complete.
Do not start another dense-backend or Qdrant-failure slice from scratch.
The next useful engineering layer is a compact retrieval-serving regression
wrapper or an API/docs consolidation slice.
```

A future public Qdrant promotion remains possible, but it must be handled as a
separate deployment-level decision with explicit API semantics and regression
evidence.
