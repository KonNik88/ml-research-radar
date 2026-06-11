# Qdrant Failure Contract v1

## Document status

```text
slice: retrieval/qdrant-failure-contract-v1
checkpoint date: 2026-06-09
implementation commit: 7f90785
merge commit: 7539dd4
implementation state: merged into main in PR #17
public Qdrant promotion: not performed
public /search behavior changed: no
```

## 1. Purpose

This slice preserves typed dense-backend failure semantics across the API/runtime boundary.

Before this change, the dense backend already distinguished:

```text
DenseBackendRequestError
DenseBackendUnavailableError
DenseBackendCompatibilityError
DenseBackendResultError
```

However, FastAPI exposed most of these failures through the generic:

```text
HTTP 503
error_code = runtime_not_ready
```

The API therefore lost the internal failure category.

The experimental Qdrant service also silently skipped a candidate when its `canonical_id` could not be hydrated from the active file runtime.

This slice closes both gaps without changing public search behavior or promoting Qdrant.

---

## 2. Architectural boundaries

The existing responsibility split remains unchanged:

```text
query text validation
→ common query encoder
→ DenseSearchRequest
→ selected DenseSearchBackend
→ backend-neutral candidates
→ canonical hydration in the API service
→ response serialization
```

The dense backend owns only:

```text
prepared dense vector
→ dense candidates
```

It does not own:

- query encoding;
- document hydration;
- lexical retrieval;
- hybrid merge;
- ranking;
- API serialization;
- fallback;
- public backend selection.

Qdrant remains an optional derived vector-serving backend.

The public retrieval strategies remain:

```text
lexical
dense
hybrid
```

The public dense and hybrid paths remain file-backed.

---

## 3. Stable API failure mapping

The existing common `ErrorResponse` schema is retained:

```json
{
  "error_code": "...",
  "message": "...",
  "details": null
}
```

Typed dense-backend exceptions now map as follows:

| Internal exception | HTTP status | API error code |
|---|---:|---|
| `DenseBackendRequestError` | 400 | `dense_backend_bad_request` |
| `DenseBackendUnavailableError` | 503 | `dense_backend_unavailable` |
| `DenseBackendCompatibilityError` | 503 | `dense_backend_incompatible` |
| `DenseBackendResultError` | 503 | `dense_backend_invalid_result` |

The HTTP class for non-request failures remains `503`.

The main improvement is stable machine-readable categorization without prematurely introducing additional status semantics.

Generic API handlers remain in place for unrelated:

- `ValueError`;
- `FileNotFoundError`;
- `RuntimeError`;
- request validation failures;
- unexpected exceptions.

---

## 4. Logging behavior

Typed dense-backend handlers preserve the internal root cause in server logs.

The client receives a stable and bounded error response.

The server log retains:

- typed exception class;
- internal message;
- chained root cause;
- traceback.

Secrets, environment dumps, and credentials are not added to the public response.

A real unavailable-Qdrant smoke produced:

```text
HTTP 503
error_code = dense_backend_unavailable
message = Failed to check Qdrant collection availability
```

while the underlying Qdrant/HTTP connection error remained visible in the server log.

---

## 5. Hydration mismatch

Previous experimental Qdrant behavior:

```python
doc = id_to_doc.get(candidate.canonical_id)

if doc is None:
    continue
```

This silently reduced the returned result count when a Qdrant candidate could not be joined to the active canonical runtime.

Current behavior:

```text
candidate canonical_id missing during hydration
→ DenseBackendResultError
→ HTTP 503
→ dense_backend_invalid_result
```

Hydration remains a service-layer responsibility.

`QdrantDenseBackend` does not load or own canonical documents.

---

## 6. No-fallback guarantee

The experimental Qdrant endpoint does not fall back to file dense retrieval.

The contract is:

```text
Qdrant success
→ Qdrant result

Qdrant failure
→ explicit structured failure
```

It is not:

```text
Qdrant failure
→ hidden FileDenseBackend call
→ successful response
```

Public file search remains available independently.

---

## 7. Health isolation

Qdrant remains optional for general file-runtime readiness.

Verified behavior:

```text
file runtime ready
+ Qdrant stopped

/health
→ HTTP 200
→ ready = true
→ backend_mode = file

/runtime
→ HTTP 200
→ qdrant.ok = false
→ qdrant.error populated

/experimental/search/qdrant
→ HTTP 503
→ dense_backend_unavailable

/search?mode=dense
→ HTTP 200
→ file dense results
```

Qdrant failure does not make the general API unhealthy.

---

## 8. Recovery and reload behavior

Transient Qdrant failures are not stored as a permanent failed state.

Verified live sequence:

```text
Qdrant running
→ experimental search succeeds

Qdrant stopped
→ structured 503

Qdrant started again
→ the next experimental request succeeds
```

No API restart or runtime reload was required for transient recovery.

Runtime reload behavior is also preserved:

```text
cached Qdrant backend exists
→ runtime reload
→ cached backend cleared
→ next request creates a new backend instance
```

No circuit breaker or sticky failure state is introduced.

---

## 9. Files changed

Production code:

```text
services/api/app.py
services/api/search_service.py
```

Tests:

```text
tests/smoke/test_api_qdrant_backend_composition.py
tests/integration/test_api_errors.py
tests/integration/test_api_reload.py
```

The following files did not require modification:

```text
radar_core/retrieval/dense_backend.py
radar_core/retrieval/qdrant_store.py
services/api/runtime.py
services/api/schemas.py
services/api/logging.py
tests/integration/test_api_smoke.py
```

The existing backend hierarchy, runtime lifecycle, and response schema were sufficient.

---

## 10. Test evidence

Targeted tests:

```text
test_api_qdrant_backend_composition.py
→ 4 passed

test_api_errors.py
→ 4 passed

test_api_reload.py
→ 4 passed

test_api_smoke.py
→ 6 passed

test_qdrant_dense_backend.py
→ 17 passed

test_api_discovery.py
→ 34 passed, 4 expected DB-only skips
```

The new tests verify:

- stable typed API mapping;
- backend exception propagation;
- explicit hydration failure;
- absence of fallback;
- health isolation;
- public file dense availability;
- Qdrant backend recreation after reload.

---

## 11. Live and integrated validation

Strict collection validator:

```text
collection = ml_radar_dense_benchmark_v1
points = 60954
corpus documents = 60954
payload audit failures = 0
required failures = 0
```

Experimental Qdrant validator:

```text
status = 200
mode = dense_qdrant
result count > 0
required failures = 0
```

File/Qdrant comparison:

```text
queries = 34
errors = 0
selected profile = ef_256
selected full match = true
exact full match = true
blocking classifications = 0
```

Integrated Discovery regression:

```text
passed
```

Full strict Definition of Done:

```text
canonical documents = 60954
multisource documents = 9192
dod_passed = true
required_failed_count = 0
```

---

## 12. Definition of Done

- [x] Existing typed backend errors preserved.
- [x] Stable API error mapping implemented.
- [x] Request failure maps to stable HTTP 400 response.
- [x] Unavailable backend maps to stable HTTP 503 response.
- [x] Compatibility failure maps to stable HTTP 503 response.
- [x] Invalid backend result maps to stable HTTP 503 response.
- [x] Hydration mismatch is no longer silently skipped.
- [x] Hydration remains outside the dense backend.
- [x] Root cause remains in server logs.
- [x] No hidden file fallback exists.
- [x] General health remains Qdrant-independent.
- [x] Public file dense search remains available.
- [x] Public dense and hybrid remain file-backed.
- [x] Transient stop/start recovery works.
- [x] Runtime reload recreates the Qdrant backend.
- [x] Successful experimental response remains compatible.
- [x] Targeted tests are green.
- [x] Integrated Discovery regression is green.
- [x] Strict Qdrant validators are green.
- [x] Full strict DoD is green.
- [x] No public promotion, performance, or hybrid changes are included.

---

## 13. Non-goals

This slice does not add:

- public `vector_backend`;
- public Qdrant promotion;
- Qdrant-backed hybrid search;
- hidden or explicit fallback;
- circuit breaker;
- retry framework;
- persistent failed state;
- last-failure observability;
- Prometheus metrics;
- OpenTelemetry tracing;
- performance or concurrency benchmarks;
- filter pushdown;
- similar-paper migration;
- new embeddings;
- DB-native dense search;
- UI changes.

---

## 14. Known limitations

The slice deliberately does not yet provide:

- timeout-specific failure injection as a distinct test case;
- persistent last-failure diagnostics;
- production metrics or tracing;
- deployment rollback exercise;
- concurrency or soak-test evidence.

These remain promotion gates or follow-up engineering work.

---

## 15. Follow-up

The recommended follow-up slice was:

```text
retrieval/qdrant-runtime-observability-v1
```

That follow-up has now been implemented on feature branch commit:

```text
f89574e api: add Qdrant runtime observability
```

It adds:

- bounded live-probe caching;
- forced runtime refresh;
- requested/effective backend state;
- bounded last-failure visibility;
- stage-level timings;
- success/failure/recovery counters;
- reload reset.

The next promotion gate is:

```text
performance and concurrency evidence
→ controlled hybrid evaluation
→ explicit promotion decision
```

Keeping Qdrant experimental remains a valid evidence-based outcome.
