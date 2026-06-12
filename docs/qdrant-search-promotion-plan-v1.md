# Qdrant Search Promotion Plan v1

## Document status

```text
version: v1
status: active promotion-gate and implementation-tracking document
last updated: 2026-06-12

internal DenseSearchBackend abstraction: implemented / green
experimental API adoption: implemented / green
evaluation tooling adoption: implemented / green
Qdrant failure contract: merged / green
Qdrant runtime observability: merged / green
Qdrant serving performance: implemented / validated on feature branch
experimental transport: gRPC
feature branch: retrieval/qdrant-serving-performance-v1

public /search backend change: none
public API strategy change: none
Qdrant required for /health: no
public promotion decision: not made
fallback: absent
```

This document defines the controlled path for evolving Qdrant from an
experimental vector-serving implementation into a possible dense candidate
backend for public search.

It records:

1. the implemented backend abstraction;
2. reliability and observability guarantees;
3. completed serving-performance and transport evidence;
4. remaining hybrid and product-decision gates.

This document does not authorize hidden switching, hidden fallback,
backend-specific public modes, or Qdrant-dependent general readiness.

---

## 1. Core distinction

The central contract is:

```text
mode = retrieval strategy
vector backend = implementation of the dense candidate component
```

Public retrieval strategies:

```text
lexical
dense
hybrid
```

Internal dense implementations:

```text
file
qdrant
```

The project does not add public modes such as:

```text
dense_qdrant
hybrid_qdrant
hybrid_ranked_qdrant
```

`dense_qdrant` remains an experimental endpoint label, not a public strategy
enum.

---

## 2. Architecture context

ML Research Radar is a paper-centric canonical corpus and discovery platform.

Relevant flow:

```text
canonical corpus
→ retrieval build
→ common query encoder
→ dense candidate backend
→ canonical hydration
→ optional hybrid merge
→ optional ranking
→ API response
```

Qdrant belongs to the derived retrieval-serving plane.

Invariants:

```text
canonical_documents.jsonl = paper truth
retrieval artifacts = reference derived build
Qdrant collection = optional derived serving materialization
Postgres = rebuildable serving materialization
Discovery/API/UI = product layers
```

Qdrant must never mutate canonical paper truth.

---

## 3. Current stable baseline

Active corpus and retrieval build:

```text
canonical corpus documents = 60954
canonical multisource documents = 9192
retrieval build_id = 20260504T164021Z
embedding model = sentence-transformers/all-MiniLM-L6-v2
embedding dimension = 384
dense vectors normalized = true
```

Active Qdrant collection:

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

Active Golden Set:

```text
enabled queries = 34
explicit canonical-labeled queries = 34
weak-pattern-only enabled queries = 0
```

Current parity evidence:

```text
default → 33/34 exact order, one stable ANN recall mismatch
ef_128  → 33/34 exact order, one stable ANN recall mismatch
ef_256  → 34/34 exact order
ef_512  → 34/34 exact order
exact   → 34/34 exact order
```

Selected experimental ANN profile:

```text
QdrantSearchProfile(
    name="ef_256",
    exact=False,
    hnsw_ef=256,
)
```

Diagnostic oracle:

```text
QdrantSearchProfile(
    name="exact",
    exact=True,
    hnsw_ef=None,
)
```

`ef_256` is build- and evaluation-scoped. It must be re-evaluated after
material changes to the corpus, embedding model, Qdrant version/configuration,
index, or Golden Set.

Current serving-performance evidence:

```text
preset = full
queries = 34
top_k = [10, 20]
backend concurrency = [1, 2, 4, 8]
API concurrency = [1, 2, 4, 8]
quality comparisons = 681
exact comparisons = 681
serving errors = 0
strict validator failures = 0
```

Transport reliability evidence:

```text
REST shared client, Windows, direct concurrency 8
→ first full run: 678 / 680 successful
→ diagnostic rerun: 679 / 680 successful
→ root-cause path ended in WinError 10038

gRPC
→ backend full run #1: 680 / 680
→ backend full run #2: 680 / 680
→ final full backend: 680 / 680
→ final full API: 204 / 204
```

---

## 4. Current architectural decision

1. File dense remains the public and reference implementation.
2. Qdrant remains optional.
3. `/experimental/search/qdrant` remains the explicit serving boundary.
4. Public `/search` modes remain `lexical|dense|hybrid`.
5. Public dense and hybrid remain file-backed.
6. Experimental Qdrant serving uses gRPC.
7. No hidden fallback exists.
8. Public exposure requires a separate evidence-based decision.

---

## 5. Implemented internal abstraction

Implementation location:

```text
radar_core/retrieval/dense_backend.py
```

Implemented structure:

```text
DenseSearchBackend Protocol
├── FileDenseBackend
└── QdrantDenseBackend
```

Implemented data contracts:

```python
DenseSearchRequest
DenseSearchCandidate
DenseSearchBackendInfo
DenseSearchBackendResult
QdrantSearchProfile
```

Implemented typed errors:

```python
DenseBackendError
DenseBackendRequestError
DenseBackendUnavailableError
DenseBackendCompatibilityError
DenseBackendResultError
```

The interface intentionally excludes speculative filters in v1.

---

## 6. Responsibility boundary

Backends own only dense candidate retrieval.

Input:

```text
prepared normalized query vector
top_k
```

Output:

```text
canonical_id
score
rank
dense_index when available
backend point ID when available
bounded backend metadata
```

Backends do not own:

- query text normalization;
- embedding model loading;
- query encoding;
- canonical document hydration;
- lexical retrieval;
- hybrid score normalization or merge;
- product ranking;
- API fallback policy;
- pagination;
- response serialization;
- Streamlit rendering.

Common flow:

```text
query text
→ common validation
→ common encoder
→ DenseSearchRequest
→ DenseSearchBackend.search()
→ backend-neutral candidates
→ common hydration
→ optional common hybrid/ranking
→ response
```

---

## 7. Exact file reference semantics

`dense_backend.py` owns the authoritative exact file candidate kernel.

Reference behavior:

```python
query = np.asarray(query_vector, dtype=np.float32)
scores = np.asarray(stored_embeddings @ query, dtype=np.float32)
order = np.argsort(scores)[::-1]
```

Rules:

- query encoding and normalization happen before backend invocation;
- stored matrix is used as persisted;
- no silent renormalization;
- full descending sort preserves reference behavior;
- IDs, dimensions, finite values, and result invariants are validated;
- `FileDenseBackend` requires normalized retrieval artifacts.

`parity.py` depends on the backend layer and provides report adapters and
diagnostics. Runtime backend code does not depend on evaluation code.

---

## 8. Qdrant profile-aware and transport-aware store

`QdrantRetrievalStore.search_vector()` supports:

```text
exact: bool
hnsw_ef: int | None
```

The store also supports explicit transport configuration:

```text
grpc_port: int
prefer_grpc: bool
transport: rest | grpc
```

Core adapter defaults remain backward compatible:

```text
prefer_grpc = false
transport = REST
```

The experimental API and serving-performance benchmark explicitly select:

```text
grpc_port = 6334
prefer_grpc = true
transport = gRPC
```

The store remains:

- read-only;
- collection-creation free;
- upload free;
- canonical-truth agnostic;
- responsible only for low-level Qdrant access and normalization.

No retry framework, hidden fallback, or collection mutation was introduced.

---

## 9. QdrantDenseBackend behavior

`QdrantDenseBackend` receives dependencies through constructor injection:

- read-only store;
- explicit `QdrantSearchProfile`;
- expected build ID;
- expected corpus count;
- expected vector size;
- expected distance;
- optional dense IDs for strict mapping;
- point-ID mapping policy.

Core code does not read environment variables.

API composition and evaluation scripts construct the profile and transport.

### Lifecycle compatibility checks

Checked once per backend instance:

```text
collection exists
points_count matches corpus count
vector_size matches retrieval build
distance matches expected distance
```

Compatibility state is cached.

Runtime reload creates a new backend and invalidates the old cache.

### Per-result checks

Checked on every search:

```text
result type is valid
canonical_id is present
score is finite
candidate IDs are unique
payload exists
payload canonical_id matches
dense_index is valid
normalized dense_index matches payload
payload build_id matches active build
dense_ids[dense_index] matches canonical_id when available
point_id matches dense_index when required
returned count <= top_k
```

No fallback to file occurs.

---

## 10. Filter semantics

The v1 request contract does not include filters.

Future filter support requires:

- a concrete product use case;
- explicit capability semantics;
- equivalent or documented backend behavior;
- validation and regression tests;
- a separate interface change.

Silently ignored filters are prohibited.

---

## 11. Experimental API adoption

`GET /experimental/search/qdrant` uses:

```text
common query encoder
→ runtime-owned lazy QdrantDenseBackend
→ Qdrant gRPC transport
→ backend-neutral candidates
→ common canonical hydration
→ experimental response schema
```

API response compatibility is preserved:

```text
mode = dense_qdrant
build_id
collection_name
rank
document
retrieval score
point_id
dense_index
payload
```

The runtime:

- creates the backend lazily;
- caches it for the runtime lifecycle;
- recreates it after reload;
- exposes transport and gRPC port in diagnostics;
- keeps Qdrant outside core file-runtime readiness.

Public `/search` remains file-backed.

---

## 12. Evaluation tooling adoption

The common abstraction is used by:

```text
scripts/evaluation/compare_qdrant_file_dense.py
scripts/evaluation/run_qdrant_search_profile_sweep.py
scripts/evaluation/run_qdrant_serving_performance.py
```

The serving benchmark measures:

- backend-only file/Qdrant search;
- fresh-process API behavior;
- warm sequential API behavior;
- concurrency `1`, `2`, `4`, and `8`;
- stage timings;
- resource capability summaries;
- exact quality comparisons;
- bounded failure diagnostics.

The collection build/upload benchmark remains outside the read-only backend
abstraction.

---

## 13. Current adoption boundary

Current consumers:

```text
FileDenseBackend:
- public dense/hybrid reference path
- exact comparison reference
- profile-sweep reference
- serving benchmark reference
- contract tests

QdrantDenseBackend:
- experimental API
- selected ef_256 comparison
- exact diagnostic comparison
- profile sweep
- serving benchmark
- contract tests
```

Current non-consumers:

```text
public /search?mode=dense
public /search?mode=hybrid
similar papers
Discovery ranking
topic clusters
topic projection
DB backend
```

This is intentional.

---

## 14. Failure and fallback policy

### Experimental endpoint

| Internal exception | HTTP status | API error code |
|---|---:|---|
| `DenseBackendRequestError` | 400 | `dense_backend_bad_request` |
| `DenseBackendUnavailableError` | 503 | `dense_backend_unavailable` |
| `DenseBackendCompatibilityError` | 503 | `dense_backend_incompatible` |
| `DenseBackendResultError` | 503 | `dense_backend_invalid_result` |

Covered failures include:

- Qdrant unavailable;
- collection missing;
- incompatible count;
- incompatible vector size;
- distance mismatch;
- query failure;
- invalid payload;
- build mismatch;
- mapping mismatch;
- non-finite score;
- hydration miss.

A candidate that cannot be hydrated fails explicitly instead of being silently
skipped.

### Recovery semantics

```text
Qdrant unavailable
→ structured 503

Qdrant restored
→ next experimental request may succeed
```

Transient failures are not sticky.

Runtime reload clears the cached backend.

No circuit breaker, retry framework, or persistent failed state exists.

### Future fallback

Fallback may exist only as an explicit and observable policy.

Required future metadata:

```json
{
  "requested_vector_backend": "qdrant",
  "effective_vector_backend": "file",
  "fallback_applied": true,
  "fallback_reason": "qdrant_unavailable"
}
```

Hidden fallback is prohibited.

---

## 15. Health and runtime diagnostics

General health rule:

```text
file runtime ready + Qdrant unavailable
→ /health remains ready
```

Runtime diagnostics expose:

- collection availability;
- point count and corpus-count match;
- vector size and distance;
- collection and optimizer status;
- selected profile;
- `exact` and `hnsw_ef`;
- transport and ports;
- retrieval build ID;
- probe cache timestamp, age, and TTL;
- backend creation and compatibility state;
- request/success/failure counters;
- last request/success/failure timestamps;
- bounded last-failure category, stage, and message;
- last result count;
- encode/search/hydration/total timings;
- requested/effective backend;
- explicit fallback status.

The runtime does not store:

- query text;
- query vectors;
- response payloads;
- traceback objects;
- unbounded history.

Runtime load or reload resets:

- backend cache;
- probe cache;
- bounded operational state.

---

## 16. Validation evidence

### Runtime reliability and observability

Verified live behavior:

```text
Qdrant stopped
→ /health = 200, ready = true
→ /runtime.qdrant.ok = false
→ experimental endpoint = 503 dense_backend_unavailable
→ public file dense /search = 200

Qdrant restarted
→ next experimental request = 200
→ last_status returns to ok
→ previous last-failure evidence remains available
```

### REST failure diagnosis

Initial REST performance evidence:

```text
quality comparisons = 681 exact

first full REST run:
678 / 680 successful at direct concurrency 8

diagnostic REST rerun:
679 / 680 successful at direct concurrency 8
```

Preserved exception chain:

```text
DenseBackendUnavailableError
→ ResponseHandlingException
→ httpx.ReadError
→ httpcore.ReadError
→ WinError 10038
```

The strict zero-error policy remained in force.

### gRPC evidence

```text
backend gRPC full run #1, concurrency 8 = 680 / 680
backend gRPC full run #2, concurrency 8 = 680 / 680
final full backend, concurrency 8 = 680 / 680
final full API, concurrency 8 = 204 / 204
```

Final full benchmark:

```text
preset = full
query_count = 34
qdrant_transport = grpc
error_count = 0
quality_ok = true
source_comparison_count = 681
mean_overlap_at_k = 1.0
minimum_overlap_at_k = 1.0
required_failed_count = 0
```

Backend sequential result:

```text
file:
p50 = 8.258 ms
p95 = 10.239 ms
throughput = 113.819 rps

Qdrant gRPC:
p50 = 4.415 ms
p95 = 5.149 ms
throughput = 218.431 rps
```

Warm API stage result:

```text
hydrate p50 = 31.376 ms
encode p50 = 11.590 ms
Qdrant search p50 = 5.216 ms
total p50 = 48.475 ms
```

The dominant warm API stage is hydration.

### Integrated closure

```text
core/API/performance suite = 145 passed
Discovery integration = 34 passed, 4 expected DB-only skips
selected ef_256 = 34 / 34 exact
exact oracle = 34 / 34 exact
serving comparisons = 681 exact
serving errors = 0
DB total documents = 60954
dod_passed = true
required_failed_count = 0
Discovery API regression passed
```

---

## 17. Performance interpretation

The current machine shows a meaningful backend-level advantage for Qdrant
gRPC.

At the API boundary, the improvement is smaller because encoding, hydration,
and response construction dominate total time.

Qdrant backend throughput peaked at measured concurrency `4` and declined at
`8`, while remaining error-free.

The result is positive evidence for the experimental path, not a public
promotion decision.

Cold first-request overhead remains significant because backend/channel
creation is lazy.

---

## 18. Remaining promotion gates

Internal abstraction, failure handling, observability, transport reliability,
and serving-performance evidence are complete.

### Controlled hybrid evaluation

Required next slice:

```text
lexical + FileDenseBackend
vs
lexical + QdrantDenseBackend
```

Keep common:

- encoder;
- lexical component;
- candidate budgets;
- normalization;
- hybrid merge;
- ranking;
- response schema;
- Golden Set.

Measure:

- candidate and final-result overlap;
- query-level relevance;
- exact-order differences;
- latency;
- failure semantics;
- requested/effective backend evidence.

### Product decision

Possible outcomes:

- remain experimental;
- expose an explicit opt-in backend;
- choose backend at deployment composition;
- postpone promotion.

No promotion is a valid outcome.

### Deployment-level reliability

Before production-like adoption, consider:

- timeout-specific failure injection;
- rollback drill;
- longer soak/restart evidence;
- deployed-network benchmark;
- metrics and tracing only if justified.

### Public observability

If a public choice is approved, define:

- requested/effective backend metadata;
- OpenAPI selection contract;
- explicit fallback reason if fallback is approved;
- rollout and rollback procedure.

---

## 19. Future public API direction

If public selection is approved, preferred semantics are:

```text
/search?mode=dense&vector_backend=file
/search?mode=dense&vector_backend=qdrant
/search?mode=hybrid&vector_backend=qdrant
```

This is preferable to backend-specific modes.

Before adding it:

- define default and opt-in behavior;
- add response metadata;
- add structured errors;
- add OpenAPI enums;
- add rollback;
- add no-fallback or explicit-fallback policy;
- pass hybrid and public-exposure gates.

A deployment-level selector may be preferable. That decision remains open.

---

## 20. Hybrid semantics

A Qdrant-backed hybrid path replaces only dense candidate generation.

```text
lexical candidates
+
selected DenseSearchBackend candidates
→ common normalization
→ common hybrid merge
→ optional common ranking
→ common response
```

`QdrantDenseBackend` must never own hybrid merge or ranking.

---

## 21. Similar papers and Discovery scope

Similar papers remain a separate contract:

- input is a paper vector, not text query;
- self-exclusion is required;
- enrichment differs;
- evaluation differs.

No automatic migration follows from the text-query backend work.

Discovery remains unchanged until a separate evaluated slice is approved.

---

## 22. Report and artifact policy

Generated reports are operational evidence.

The repository workflow ignores `artifacts/`.

Therefore:

- report generation does not normally create commit candidates;
- `git status` remains the source of truth;
- do not use broad `git add .`;
- commit tracked generated baselines only under an explicit policy.

Experiments must not overwrite accepted stable data artifacts.

---

## 23. Validation commands

Core tests:

```bat
python -m pytest ^
  tests/smoke/test_dense_backend_contract.py ^
  tests/smoke/test_qdrant_dense_backend.py ^
  tests/smoke/test_api_qdrant_backend_composition.py ^
  tests/smoke/test_qdrant_parity.py ^
  tests/smoke/test_qdrant_file_dense_comparison_v2.py ^
  tests/smoke/test_qdrant_collection_validation.py ^
  tests/smoke/test_qdrant_serving_performance.py ^
  tests/smoke/test_qdrant_serving_performance_validator.py ^
  tests/smoke/test_qdrant_regression_runner.py ^
  -q
```

Heavy API groups should run separately:

```bat
set ML_RADAR_SEARCH_BACKEND=file

python -m pytest tests/integration/test_api_smoke.py -q
python -m pytest tests/integration/test_api_errors.py -q
python -m pytest tests/integration/test_api_reload.py -x -vv
python -m pytest tests/integration/test_api_discovery.py -q
```

Live validators:

```bat
python -m scripts.validation.check_qdrant_collection --strict
python -m scripts.validation.check_qdrant_api_experimental --strict
```

Comparison and profile sweep:

```bat
python -m scripts.evaluation.compare_qdrant_file_dense
python -m scripts.validation.check_qdrant_file_dense_comparison --strict

python -m scripts.evaluation.run_qdrant_search_profile_sweep
python -m scripts.validation.check_qdrant_search_profile_sweep --strict
```

Serving performance:

```bat
python -m scripts.evaluation.run_qdrant_serving_performance ^
  --preset full

python -m scripts.validation.check_qdrant_serving_performance --strict
```

Final integrated regression:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-qdrant-serving-poc ^
  --include-qdrant-profile-sweep ^
  --include-qdrant-serving-performance ^
  --include-qdrant-api ^
  --include-db-smoke ^
  --include-dod
```

---

## 24. Implementation phase status

### Phase 0 — experimental baseline

Status: **complete**

### Phase 1 — design and Golden Set hardening

Status: **complete**

### Phase 2 — internal abstraction

Status: **complete / green**

### Phase 3 — experimental and evaluation adoption

Status: **complete / green**

### Phase 4a — failure contract

Status: **complete / green**

### Phase 4b — runtime observability

Status: **complete / green**

### Phase 4c — serving performance and transport reliability

Status: **complete / green on feature branch**

Completed:

- full read-only benchmark;
- strict validator;
- opt-in regression integration;
- REST failure diagnosis;
- explicit gRPC transport;
- repeated backend stress evidence;
- full API evidence;
- exact quality;
- integrated regression and DoD.

### Phase 4d — controlled hybrid evaluation

Status: **next**

### Phase 5 — controlled public exposure decision

Status: **not started**

### Phase 6 — optional explicit fallback

Status: **not planned until Phase 5 is stable**

---

## 25. Promotion checklist

### Architecture

- [x] Dense backend responsibility documented.
- [x] Query encoding remains common and outside backends.
- [x] Hydration remains outside backends.
- [x] Hybrid merge remains outside backends.
- [x] File dense remains the reference implementation.
- [x] Qdrant read path does not mutate collections.
- [x] Runtime backend does not depend on parity/evaluation code.
- [x] Filters are omitted from v1 rather than silently ignored.

### Compatibility

- [x] Point count checked.
- [x] Vector dimension checked.
- [x] Distance checked.
- [x] Payload canonical ID checked.
- [x] Payload build ID checked.
- [x] Dense index and dense-ID mapping checked.
- [x] Collection mismatch fails explicitly.
- [x] Compatibility behavior tested through deterministic failure injection.

### Quality

- [x] Golden Set expanded to 34 explicit labels.
- [x] Collection validator passes.
- [x] File/Qdrant comparison passes.
- [x] Profile sweep passes.
- [x] `ef_256` and exact match 34/34.
- [x] Performance/concurrency evidence completed.
- [ ] Controlled hybrid comparison completed.
- [ ] Public-exposure query-level review completed.

### Reliability

- [x] Missing collection behavior covered.
- [x] Count/dimension/distance mismatch covered.
- [x] Invalid payload/mapping covered.
- [x] Stable API failure categories implemented.
- [x] Hydration mismatch fails explicitly.
- [x] No implicit fallback exists.
- [x] Live stop/start recovery verified.
- [x] Runtime reload backend recreation verified.
- [x] REST concurrency failure reproduced and diagnosed.
- [x] gRPC validated under repeated full load.
- [ ] Explicit timeout failure injection completed.
- [ ] Deployment rollback drill completed.

### Observability

- [x] Experimental endpoint exposes collection and build.
- [x] Runtime exposes profile and compatibility.
- [x] Runtime exposes transport and gRPC port.
- [x] Live probe has bounded TTL cache.
- [x] Forced refresh is explicit.
- [x] Requested/effective backend state is recorded.
- [x] Stage timings are recorded.
- [x] Bounded failure state is recorded.
- [x] Recovery retains failure evidence.
- [x] Reload resets runtime state.
- [x] Strict evidence validates transport/config agreement.
- [ ] Public `/search` backend metadata designed.
- [ ] Fallback reason metadata designed if approved.
- [ ] Production metrics/tracing implemented if justified.

### Regression

- [x] Public file search tests pass.
- [x] API smoke/error/reload tests pass.
- [x] Discovery integration passes.
- [x] Discovery strict regression passes.
- [x] Topic validators pass.
- [x] Streamlit static validator passes.
- [x] Qdrant performance validator passes.
- [x] Postgres smoke passes.
- [x] Milestone strict DoD passes.

---

## 26. Rollout and rollback

Preferred sequence:

```text
internal abstraction
→ experimental adoption
→ reliability and observability
→ performance and transport evidence
→ controlled hybrid evaluation
→ explicit decision
```

Rollback target:

```text
FileDenseBackend
```

Rollback must not require:

- canonical changes;
- retrieval artifact rebuild;
- Postgres rebuild;
- UI migration.

File dense remains available throughout the promotion path.

---

## 27. Current PR boundary

The Qdrant Serving Performance v1 PR includes:

- read-only backend/API benchmark;
- full 34-query preset;
- sequential and concurrent load;
- compact repeated-result evidence;
- full quality-comparison evidence;
- failure exception chains and task context;
- strict serving validator;
- opt-in regression integration;
- explicit Qdrant gRPC support;
- experimental API gRPC configuration;
- runtime transport diagnostics;
- diagnosis of REST `WinError 10038`;
- repeated backend gRPC full runs;
- final full backend and API benchmark;
- 681 exact comparisons;
- integrated regression, DB smoke, and DoD;
- checkpoint documentation.

It does not include:

- public backend selection;
- public success-response metadata;
- hybrid Qdrant serving;
- similar-paper migration;
- fallback orchestration;
- retry or circuit-breaker framework;
- persistent telemetry history;
- metrics/tracing platform;
- new embeddings;
- source or canonical changes.

---

## 28. Final recommendation

Merge Qdrant Serving Performance v1 after final documentation review and PR
checks.

Then proceed with:

```text
controlled hybrid file-vs-Qdrant evaluation
→ explicit public-promotion decision
```

Do not promote Qdrant merely because gRPC serving is stable and faster on the
current local benchmark.

The remaining question is whether replacing the dense component of the public
hybrid strategy preserves or improves query-level behavior while remaining
observable, reversible, and compatible with the active retrieval build.
