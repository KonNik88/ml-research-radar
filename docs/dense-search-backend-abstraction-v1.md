# Dense Search Backend Abstraction v1

## Checkpoint status

```text
checkpoint: Dense Search Backend Abstraction v1
date: 2026-06-07
branch: retrieval/dense-backend-abstraction-v1
implementation: complete
validation: green
PR state: ready for final documentation commit and review
public search behavior changed: no
public Qdrant promotion performed: no
```

---

## 1. Purpose

This checkpoint records the behavior-preserving internal refactor that introduced a common dense candidate-retrieval contract for file-based exact retrieval and Qdrant.

The slice solves a concrete duplication problem:

```text
production file dense
parity file oracle
experimental Qdrant endpoint
file/Qdrant comparison
Qdrant profile sweep
```

previously contained partially separate candidate-retrieval implementations.

The new architecture centralizes runtime dense semantics without changing public retrieval strategies or canonical truth.

---

## 2. Scope

Implemented:

- backend-neutral contracts;
- authoritative exact file kernel;
- `FileDenseBackend`;
- explicit Qdrant search profiles;
- profile-aware read-only Qdrant store;
- `QdrantDenseBackend`;
- typed validation/failure semantics;
- lazy runtime composition;
- experimental endpoint adoption;
- comparison tooling adoption;
- profile-sweep adoption;
- contract and regression tests.

Not implemented:

- public backend selector;
- public Qdrant dense/hybrid;
- hidden or explicit fallback;
- similar-paper migration;
- DB dense/hybrid;
- filter pushdown;
- new embedding model;
- collection build/upload changes;
- canonical refresh;
- RAG/full text.

---

## 3. Architectural invariants preserved

```text
canonical_documents.jsonl = paper truth
retrieval artifacts = active reference build
Qdrant = optional derived serving layer
Postgres = rebuildable serving materialization
```

Public strategies remain:

```text
lexical
dense
hybrid
```

Backend is an internal implementation detail:

```text
file
qdrant
```

No backend-specific public modes were introduced.

---

## 4. Implemented contracts

Location:

```text
radar_core/retrieval/dense_backend.py
```

### DenseSearchRequest

Contains:

```text
query_vector
top_k
```

The query vector must already be encoded and normalized.

Filters are intentionally absent from v1.

### DenseSearchCandidate

Typed fields:

```text
canonical_id
score
rank
dense_index
backend_point_id
backend_metadata
```

Core join key:

```text
canonical_id
```

### DenseSearchBackendInfo

Provides:

```text
backend name
implementation
build ID
ready state
diagnostics
```

### DenseSearchBackendResult

Provides:

```text
immutable candidate tuple
backend info
timing map
```

### DenseSearchBackend Protocol

Defines:

```text
search(request)
info()
```

Implementations use structural typing and do not need explicit inheritance.

---

## 5. Error model

Implemented typed exceptions:

```text
DenseBackendError
DenseBackendRequestError
DenseBackendUnavailableError
DenseBackendCompatibilityError
DenseBackendResultError
```

This separates:

- invalid caller requests;
- unavailable serving dependency;
- incompatible artifacts/collection;
- invalid backend result.

The experimental API preserves its existing external error boundary while internal tests can assert precise failure semantics.

---

## 6. Authoritative file-dense semantics

`dense_backend.py` is the runtime owner of exact file candidate semantics.

```python
query = np.asarray(query_vector, dtype=np.float32)
scores = np.asarray(embeddings @ query, dtype=np.float32)
order = np.argsort(scores)[::-1]
```

Validation includes:

- positive non-boolean `top_k`;
- 2D embedding matrix;
- 1D query vector;
- matching dimensions;
- matching ID count;
- finite query values;
- finite scores;
- non-empty unique IDs;
- continuous ranks;
- no input mutation.

No normalization is silently performed inside the backend.

`FileDenseBackend` requires `normalized=true` artifacts.

---

## 7. Dependency direction

Correct dependency:

```text
dense_backend.py
→ authoritative runtime kernel and contracts

parity.py
→ imports backend kernel/result contracts
→ adapts results to report rows
→ compares results
→ audits mapping
→ builds mismatch diagnostics
→ checks determinism
→ classifies differences
```

Forbidden dependency avoided:

```text
runtime backend
→ evaluation/parity module
```

Legacy `exact_file_dense_search()` remains available as a compatibility adapter.

---

## 8. QdrantSearchProfile

Implemented profile:

```python
QdrantSearchProfile(
    name: str,
    exact: bool = False,
    hnsw_ef: int | None = None,
)
```

Validation:

- non-empty name;
- boolean `exact`;
- positive non-boolean `hnsw_ef` when present;
- exact profile cannot define HNSW breadth.

Current profiles:

```text
default
ef_128
ef_256
ef_512
exact
```

Selected experimental profile:

```text
ef_256
```

Exact diagnostic profile:

```text
exact
```

Core receives profiles through constructor injection.

Environment variables and evaluation YAML are composition concerns, not core concerns.

---

## 9. QdrantRetrievalStore changes

The read-only store now accepts:

```text
exact
hnsw_ef
```

It creates Qdrant `SearchParams` only when an explicit profile is requested.

Compatibility with `query_points` and legacy `search` paths is retained.

The store still does not:

- create collections;
- recreate collections;
- upload points;
- load embedding models;
- hydrate canonical documents;
- implement fallback.

---

## 10. QdrantDenseBackend lifecycle

Constructor inputs:

- store;
- search profile;
- expected build ID;
- expected corpus count;
- expected vector size;
- expected distance;
- optional dense IDs;
- point-ID mapping policy.

### Compatibility checks cached per lifecycle

Checked once:

```text
collection exists
points_count matches
vector_size matches
distance matches
```

Backend info reports whether compatibility has been checked.

### Per-search request checks

```text
request type
positive top_k
float32 conversion
1D vector
expected dimension
finite vector
```

### Per-result checks

```text
expected result type
non-empty canonical ID
unique canonical IDs
finite numeric score
mapping payload present
payload canonical ID matches
valid dense index
normalized dense index matches payload
payload build ID matches
dense IDs mapping matches when available
point ID matches dense index when required
returned count <= top_k
```

No fallback occurs.

---

## 11. API runtime composition

Files:

```text
services/api/settings.py
services/api/runtime.py
services/api/search_service.py
```

Settings provide internal experimental profile configuration:

```text
ML_RADAR_QDRANT_SEARCH_PROFILE_NAME
ML_RADAR_QDRANT_SEARCH_EXACT
ML_RADAR_QDRANT_SEARCH_HNSW_EF
```

`ApiRuntime`:

- owns an optional cached experimental backend;
- creates it lazily;
- uses active manifest, embeddings, dense IDs, and metadata;
- does not include it in core readiness;
- invalidates it during runtime reload.

Observed lifecycle:

```text
same runtime before reload → same backend instance
after reload               → new backend instance
embedding model on reload  → reused
```

---

## 12. Experimental endpoint flow

Current flow:

```text
validate text query
→ common encoder
→ DenseSearchRequest
→ runtime QdrantDenseBackend
→ backend-neutral candidates
→ canonical document hydration
→ existing QdrantSearchResponse
```

Preserved response contract:

```text
mode = dense_qdrant
build_id
collection_name
result count
timings
rank
document
score
point_id
dense_index
payload
```

The endpoint fails explicitly when Qdrant is unavailable or incompatible.

---

## 13. Evaluation migration

### File/Qdrant comparison

Now uses:

```text
FileDenseBackend
QdrantDenseBackend(ef_256)
QdrantDenseBackend(exact)
```

Preserved:

- report schema;
- selected/exact sections;
- mapping audit;
- mismatch details;
- determinism;
- classifications;
- latency;
- validator.

### Profile sweep

Now uses:

```text
FileDenseBackend
QdrantDenseBackend(default)
QdrantDenseBackend(ef_128)
QdrantDenseBackend(ef_256)
QdrantDenseBackend(ef_512)
QdrantDenseBackend(exact)
```

Preserved:

- report schema;
- profile summaries;
- query-level rows;
- mapping audit;
- determinism;
- exact-oracle policy;
- validator.

### Result adapters

`parity.py` adapts typed results to legacy report row contracts.

This prevents report/API schemas from leaking into core backend types.

---

## 14. No-public-change guarantees

Explicitly preserved:

```text
/search?mode=lexical
/search?mode=dense
/search?mode=hybrid
```

Public dense/hybrid remain file-backed.

Also unchanged:

- public mode enum;
- hybrid normalization/merge;
- ranking;
- general `/health`;
- similar papers;
- Discovery API;
- topic clusters;
- topic projection;
- Streamlit;
- canonical corpus;
- retrieval build;
- DB backend.

---

## 15. Validation evidence

### Tests

```text
69 backend/parity/regression smoke tests passed
4 retrieval smoke tests passed
5 retrieval artifact smoke tests passed
6 API smoke tests passed
3 API error tests passed
3 API reload tests passed
34 Discovery integration tests passed
4 DB-only artifact tests skipped as expected in file mode
```

### Live validators

Passed:

- Qdrant collection strict;
- experimental Qdrant API strict;
- Golden Set strict;
- Discovery API strict;
- topic clusters strict;
- topic projection strict;
- Streamlit static strict;
- integrated Discovery regression.

### Full comparison

```text
queries = 34
errors = 0
selected profile = ef_256
selected full match = true
exact full match = true
blocking classifications = 0
```

### Full profile sweep

```text
default = 33/34
ef_128 = 33/34
ef_256 = 34/34
ef_512 = 34/34
exact = 34/34
errors = 0
strict failures = 0
```

The known default/`ef_128` mismatch remains a stable approximate HNSW recall difference for the mixture-of-experts query.

---

## 16. Memory incident and test execution policy

One monolithic heavy pytest process caused a transient system OOM/commit-pressure failure.

The same tests passed when separated into independent Python processes.

Likely contributors:

- repeated TestClient startup;
- repeated canonical/retrieval artifact loading;
- CUDA/PyTorch allocator retention;
- runtime reload cycles;
- delayed object collection.

This does not currently indicate a functional backend error.

Until a dedicated memory-hardening slice:

```text
run heavy API files separately
run comparison separately
run profile sweep separately
avoid one monolithic integration process
```

Future diagnostics should record:

- process RSS;
- Windows commit;
- available RAM;
- VRAM allocated/reserved;
- object lifetime across clients/reloads.

---

## 17. Files added or changed by the slice

Core:

```text
radar_core/retrieval/dense_backend.py
radar_core/retrieval/qdrant_store.py
radar_core/retrieval/parity.py
```

API:

```text
services/api/settings.py
services/api/runtime.py
services/api/search_service.py
```

Evaluation:

```text
scripts/evaluation/compare_qdrant_file_dense.py
scripts/evaluation/run_qdrant_search_profile_sweep.py
```

Tests:

```text
tests/smoke/test_dense_backend_contract.py
tests/smoke/test_qdrant_dense_backend.py
tests/smoke/test_api_qdrant_backend_composition.py
tests/smoke/test_qdrant_parity.py
```

Documentation:

```text
docs/dense-search-backend-abstraction-v1.md
docs/qdrant-search-promotion-plan-v1.md
roadmap.md
```

---

## 18. Definition of Done

- [x] Backend-neutral protocol and contracts exist.
- [x] Exact file kernel moved to runtime backend module.
- [x] `parity.py` depends on backend, not the reverse.
- [x] `FileDenseBackend` preserves exact reference semantics.
- [x] Qdrant store supports explicit profiles.
- [x] `QdrantDenseBackend` is read-only.
- [x] Compatibility checks are cached.
- [x] Per-result checks always run.
- [x] No hidden fallback exists.
- [x] Core does not read environment variables.
- [x] Experimental API uses the abstraction.
- [x] Comparison uses the abstraction.
- [x] Profile sweep uses the abstraction.
- [x] Report schemas remain stable.
- [x] Public `/search` remains unchanged.
- [x] General health remains Qdrant-independent.
- [x] Similar papers remain unchanged.
- [x] Discovery and Streamlit remain unchanged.
- [x] Tests and strict validators are green.
- [x] Documentation records the checkpoint.

---

## 19. Remaining non-goals

Not completed by this checkpoint:

- public `vector_backend`;
- Qdrant-backed public dense;
- Qdrant-backed public hybrid;
- explicit public fallback;
- public backend metadata;
- concurrency benchmark;
- deployment latency study;
- filter pushdown;
- similar-paper backend abstraction;
- DB dense;
- lexical backend abstraction;
- scientific embedding replacement;
- full text/RAG.

---

## 20. Recommended next slice

Recommended order:

```text
failure injection and typed error mapping
→ runtime/backend observability design
→ memory/lifecycle test hardening
→ warm/cold latency and concurrency benchmark
→ controlled file-vs-Qdrant hybrid evaluation
→ explicit promotion decision
```

A valid decision may be to keep Qdrant experimental.

The abstraction is useful even without promotion because it:

- removes duplicated retrieval implementations;
- preserves exact reference semantics;
- enables controlled backend comparison;
- makes failure and compatibility contracts explicit;
- keeps public API independent of storage technology;
- creates a reversible path for future serving decisions.
