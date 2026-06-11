# Qdrant Runtime Observability v1

## Document status

```text
slice: retrieval/qdrant-runtime-observability-v1
checkpoint date: 2026-06-11
implementation commit: f89574e
implementation state: green on feature branch, pending PR merge
previous main checkpoint: 7539dd4
previous slice: Qdrant Failure Contract v1 merged in PR #17
public Qdrant promotion: not performed
public /search behavior changed: no
```

---

## 1. Purpose

This slice adds bounded runtime observability for the experimental Qdrant
dense-serving path.

The previous failure-contract slice already provided:

- typed backend errors;
- stable API error codes;
- explicit hydration failure;
- no hidden fallback;
- health isolation;
- restart and reload recovery.

The remaining gap was operational visibility.

Before this slice, `/runtime` could probe the Qdrant collection, but:

- every request could perform live network calls;
- probe state was not cached;
- the runtime did not retain request/success/failure counters;
- success, failure, and recovery were not visible;
- last failure category and stage were not visible;
- stage timings were only present in successful search responses;
- requested and effective backend state were not explicit.

This slice closes that gap without changing public search defaults.

---

## 2. Architectural boundaries

The existing responsibility split remains:

```text
query validation
→ common query encoder
→ DenseSearchRequest
→ QdrantDenseBackend
→ backend-neutral candidates
→ canonical hydration
→ API response
```

Runtime observability belongs to `ApiRuntime` because it spans:

- backend creation;
- backend search;
- service-layer hydration;
- API lifecycle;
- runtime reload.

`QdrantDenseBackend` remains responsible only for dense candidate retrieval and
backend compatibility/result validation.

The runtime does not make Qdrant part of canonical truth or general readiness.

---

## 3. Cached live-probe contract

The Qdrant collection probe is now explicitly controlled.

```text
GET /runtime?refresh_qdrant=true
→ forced live probe

GET /runtime
→ cached probe while cache age <= TTL
```

Default configuration:

```text
qdrant_runtime_diagnostics_ttl_sec = 30.0
```

Probe metadata:

- `probe_cached`;
- `probe_checked_at`;
- `probe_cache_age_sec`;
- `probe_ttl_sec`.

Probe payload retains collection diagnostics:

- `configured`;
- `ok`;
- host and port;
- collection name;
- timeout;
- compatibility-check setting;
- collection existence;
- point count;
- expected corpus count;
- corpus-count match;
- vector size;
- distance;
- collection status;
- optimizer status;
- bounded error text.

The cache prevents uncontrolled repeated Qdrant network calls from ordinary
`/runtime` polling.

---

## 4. Profile, build, and backend lifecycle diagnostics

The runtime exposes:

```text
profile_name
exact
hnsw_ef
build_id
backend_created
compatibility_checked
compatibility_ok
```

These fields answer distinct questions:

```text
configured profile
→ what search profile would be used

backend_created
→ whether the lazy runtime backend exists

compatibility_checked
→ whether the backend has performed lifecycle validation

compatibility_ok
→ whether the checked backend is ready
```

The active experimental profile remains:

```text
profile_name = ef_256
exact = false
hnsw_ef = 256
```

---

## 5. Bounded operational state

The runtime records one bounded aggregate state:

```text
request_count
success_count
failure_count

last_status
last_request_at
last_success_at
last_failure_at

last_failure_category
last_failure_stage
last_failure_message

last_result_count
last_timing_ms

requested_vector_backend
effective_vector_backend
fallback_applied
```

Allowed `last_status` values:

```text
never
ok
error
```

The failure message is bounded to 500 characters.

The runtime does not store:

- query text;
- query vectors;
- response documents;
- payload history;
- exception objects;
- tracebacks;
- unbounded event history;
- secrets.

Root cause and traceback remain server-log concerns.

---

## 6. Success, failure, and recovery semantics

### Request start

```text
request_count += 1
last_request_at = now
requested_vector_backend = qdrant
effective_vector_backend = null
fallback_applied = false
```

### Success

```text
success_count += 1
last_status = ok
last_success_at = now
last_result_count = returned candidates
effective_vector_backend = qdrant
last_timing_ms = current request timings
```

### Failure

```text
failure_count += 1
last_status = error
last_failure_at = now
last_failure_category = stable category
last_failure_stage = encode | backend_init | backend_search | hydration
last_failure_message = bounded message
last_result_count = null
effective_vector_backend = null
fallback_applied = false
```

### Recovery

A successful request after a failure sets:

```text
last_status = ok
effective_vector_backend = qdrant
```

It intentionally retains:

```text
last_failure_at
last_failure_category
last_failure_stage
last_failure_message
```

This makes current recovery and previous failure simultaneously observable.

No sticky failed state, circuit breaker, or retry framework is introduced.

---

## 7. Stage timing contract

Successful requests record:

```text
encode_ms
qdrant_search_ms
hydrate_ms
total_ms
```

Failures record all timings available before the failure plus `total_ms`.

Examples:

```text
backend-search failure
→ encode_ms
→ total_ms

hydration failure
→ encode_ms
→ qdrant_search_ms
→ total_ms
```

These timings are operational evidence. They are not yet a benchmark suite.

A first cold request may be much slower than later warm requests because model
and device execution are not yet warm.

---

## 8. API surface

`GET /runtime` remains the diagnostics endpoint.

New query parameter:

```text
refresh_qdrant: bool = false
```

Usage:

```text
/runtime
/runtime?refresh_qdrant=true
```

`/health` remains unchanged and Qdrant-independent.

The experimental search endpoint remains:

```text
/experimental/search/qdrant
```

Public retrieval remains:

```text
/search?mode=lexical
/search?mode=dense
/search?mode=hybrid
```

No public `vector_backend` parameter is introduced.

---

## 9. Reload lifecycle

A successful runtime load or reload resets:

- cached Qdrant backend;
- Qdrant live-probe cache;
- probe timestamp and monotonic age;
- operational counters;
- last status;
- last failure;
- last result count;
- last timings;
- requested and effective backend state.

The reset is centralized in `ApiRuntime.load()` after a successful backend load.

A failed runtime load does not pretend to create a clean successful lifecycle.

---

## 10. Failure classification

The observability state uses the stable API categories introduced by the
failure-contract slice:

| Failure class | Category |
|---|---|
| request error | `dense_backend_bad_request` |
| unavailable backend | `dense_backend_unavailable` |
| incompatible backend | `dense_backend_incompatible` |
| invalid result | `dense_backend_invalid_result` |
| unexpected service failure | `internal_error` |

The stage is recorded separately.

This keeps error category and execution stage orthogonal.

---

## 11. Files changed

Production:

```text
services/api/settings.py
services/api/runtime.py
services/api/schemas.py
services/api/search_service.py
services/api/app.py
```

Tests:

```text
tests/smoke/test_api_qdrant_backend_composition.py
tests/integration/test_api_smoke.py
tests/integration/test_api_reload.py
```

Not changed:

```text
radar_core/retrieval/dense_backend.py
radar_core/retrieval/qdrant_store.py
services/api/logging.py
services/api/db.py
services/api/discovery_service.py
public /search strategy implementation
canonical and retrieval artifacts
```

The existing backend contract and failure hierarchy were sufficient.

---

## 12. Test evidence

Targeted test results:

```text
test_api_qdrant_backend_composition.py
→ 6 passed

test_api_smoke.py
→ 7 passed

test_api_errors.py
→ 4 passed

test_api_reload.py
→ 4 passed

test_api_discovery.py
→ 34 passed, 4 expected DB-only skips
```

The tests verify:

- backend creation and reuse;
- success-state recording;
- unavailable-backend recording;
- hydration-failure recording;
- bounded failure messages;
- TTL caching;
- forced refresh;
- runtime schema;
- health isolation;
- reload reset.

---

## 13. Live validation evidence

### Forced and cached probe

```text
forced probe
→ ok = true
→ probe_cached = false
→ cache age = 0

immediate repeated probe
→ probe_cached = true
→ same checked timestamp
→ age within 30-second TTL
```

### Successful request

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
```

### Failure

```text
Qdrant stopped
→ HTTP 503 dense_backend_unavailable
→ request_count = 2
→ success_count = 1
→ failure_count = 1
→ last_status = error
→ last_failure_stage = backend_search
→ effective_vector_backend = null
→ fallback_applied = false
```

General service behavior during failure:

```text
/health = 200
ready = true
public file dense /search = 200
```

### Recovery

```text
Qdrant restarted
→ next request succeeds without API reload
→ request_count = 3
→ success_count = 2
→ failure_count = 1
→ last_status = ok
→ effective_vector_backend = qdrant
→ previous last_failure evidence retained
```

---

## 14. Integrated validation

Green validation evidence:

- strict Qdrant collection check;
- strict experimental Qdrant API check;
- 34-query Golden Set check;
- 34-query file/Qdrant comparison;
- selected `ef_256` full match;
- exact full match;
- Discovery integration;
- Discovery strict validation;
- topic clusters;
- topic projection;
- Streamlit static validation;
- integrated Discovery API regression;
- full strict Definition of Done.

Milestone result:

```text
canonical_doc_count = 60954
canonical_multisource_docs = 9192
dod_passed = true
required_failed_count = 0
```

---

## 15. Known limitations

### Probe error locale text

The low-level Windows socket error included in the best-effort live-probe
`error` field may be displayed with incorrect locale decoding.

This does not affect:

- HTTP status;
- public `error_code`;
- `last_failure_category`;
- `last_failure_stage`;
- server exception logging;
- readiness semantics.

Automation should rely on stable fields, not operating-system prose.

### In-memory state

Observability state is process-local and resets on runtime load, reload, or
process restart.

This is intentional for v1.

There is no persistent event history, cross-process aggregation, metrics
backend, or tracing system.

### No benchmark conclusion

The slice exposes timings but does not provide statistically controlled
performance or concurrency conclusions.

---

## 16. Definition of Done

- [x] Live Qdrant probe has a bounded TTL cache.
- [x] Forced refresh is explicit.
- [x] Collection/profile/build diagnostics are exposed.
- [x] Backend creation and compatibility state are exposed.
- [x] Request/success/failure counters are exposed.
- [x] Timestamps are exposed.
- [x] Current status is exposed.
- [x] Last failure category, stage, and bounded message are exposed.
- [x] Result count and stage timings are exposed.
- [x] Requested/effective backend is exposed for the experimental path.
- [x] Fallback is explicitly false.
- [x] Recovery returns the current status to `ok`.
- [x] Recovery retains previous failure evidence.
- [x] Reload resets backend, probe cache, and operational state.
- [x] `/health` remains Qdrant-independent.
- [x] Public dense and hybrid remain file-backed.
- [x] No hidden fallback exists.
- [x] Targeted tests are green.
- [x] Live success/failure/recovery smoke is green.
- [x] Integrated regression is green.
- [x] Full strict DoD is green.
- [x] No public promotion is included.

---

## 17. Non-goals

This slice does not add:

- public `vector_backend`;
- public Qdrant promotion;
- Qdrant-backed hybrid search;
- fallback orchestration;
- retry framework;
- circuit breaker;
- persistent failed state;
- persistent telemetry history;
- Prometheus;
- Grafana;
- OpenTelemetry;
- Jaeger;
- distributed tracing;
- performance/concurrency benchmark results;
- filter pushdown;
- similar-paper migration;
- new embeddings;
- UI redesign;
- canonical or source changes.

---

## 18. Next slice

Recommended next slice:

```text
retrieval/qdrant-serving-performance-v1
```

Scope:

- warm and cold latency;
- sequential and concurrent requests;
- p50, p95, and max;
- file versus Qdrant;
- encode, search, hydration, ranking, and total timing;
- process RSS, committed memory, and VRAM;
- deterministic benchmark inputs;
- no public promotion.

Then:

```text
controlled hybrid evaluation
→ explicit promotion decision
```

Keeping Qdrant experimental remains a valid evidence-based outcome.
