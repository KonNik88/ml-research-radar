# Qdrant Serving Performance v1

## Document status

```text
version: v1
status: implemented / validated / pending PR merge
checkpoint date: 2026-06-12
feature branch: retrieval/qdrant-serving-performance-v1

public /search backend change: none
public API strategy change: none
public Qdrant promotion: not performed
fallback added: no
canonical or retrieval build change: none
```

This document records the performance, concurrency, transport-reliability, and
quality evidence for the experimental Qdrant dense-serving path in
**ML Research Radar**.

The slice does not authorize public Qdrant promotion. It establishes a
reproducible evidence base and hardens the experimental serving transport.

---

## 1. Scope

The benchmark compares two levels:

```text
backend-only
→ FileDenseBackend vs QdrantDenseBackend over pre-encoded vectors

end-to-end API
→ public file-dense /search
vs
→ /experimental/search/qdrant
```

The benchmark is read-only. It does not:

- create or recreate Qdrant collections;
- upload or mutate vectors;
- change canonical paper truth;
- change public search defaults;
- add fallback;
- promote Qdrant.

Active evidence scope:

```text
canonical documents = 60954
retrieval build_id = 20260504T164021Z
embedding model = sentence-transformers/all-MiniLM-L6-v2
embedding dimension = 384
collection = ml_radar_dense_benchmark_v1
points = 60954
distance = Cosine
profile = ef_256
Golden Set queries = 34
top_k values = [10, 20]
backend concurrency = [1, 2, 4, 8]
API concurrency = [1, 2, 4, 8]
```

---

## 2. Benchmark implementation

Implemented files:

```text
configs/qdrant_serving_performance_v1.yaml
scripts/evaluation/qdrant_serving_performance.py
scripts/evaluation/run_qdrant_serving_performance.py
scripts/validation/check_qdrant_serving_performance.py

tests/smoke/test_qdrant_serving_performance.py
tests/smoke/test_qdrant_serving_performance_validator.py
```

The benchmark records:

- model-load and query-encoding timings;
- backend construction and first-request timings;
- sequential latency and throughput;
- concurrent latency and throughput;
- fresh-process API startup and first request;
- warm API latency and throughput;
- encode, search, hydration, and total server timings;
- process and container resource summaries where available;
- exact result-quality comparisons;
- bounded exception chains and task context on failure.

Repeated measurement rows retain result digests instead of complete ranked ID
lists. Full IDs are retained once per quality comparison.

The strict validator checks:

- report schema and resolved preset;
- safety markers;
- collection/build/profile compatibility;
- explicit transport identity;
- zero source errors;
- exact comparison quality;
- complete backend and API scenarios;
- explicit resource capability reporting.

---

## 3. Initial REST result and discovered failure

The first full benchmark used one shared synchronous REST `QdrantClient` on
Windows with Docker Desktop.

Quality remained exact:

```text
comparison count = 681
mean overlap@k = 1.0
minimum overlap@k = 1.0
exact same order = 681
result-count mismatches = 0
duplicate-ID failures = 0
```

However, direct backend load at concurrency `8` produced transient transport
failures:

```text
first full REST run:
tasks = 680
successes = 678
errors = 2

diagnostic REST rerun:
tasks = 680
successes = 679
errors = 1
```

The diagnostic hardening preserved the concrete task and exception chain:

```text
backend = qdrant
concurrency = 8
round = 6
query_id = protein_language_models_001
top_k = 20

DenseBackendUnavailableError
→ qdrant_client.http.exceptions.ResponseHandlingException
→ httpx.ReadError
→ httpcore.ReadError
→ WinError 10038
```

Windows reported that an operation was attempted on an object that was no
longer a socket.

Qdrant remained healthy during the incident:

- collection validation stayed green;
- server-side requests returned successfully around the failure;
- the container did not restart;
- `RestartCount` remained zero;
- no OOM kill occurred.

The evidence therefore localized the failure to the client-side REST /
HTTPX / HTTPCore / Windows socket path under the tested direct concurrency.

The strict benchmark policy correctly rejected the REST run:

```text
max_error_count = 0
quality_ok = false
```

The policy was not weakened and retries were not added to hide the failure.

---

## 4. Transport hardening

The read-only Qdrant store now supports explicit transport configuration:

```text
grpc_port = 6334
prefer_grpc = true
transport = grpc
```

Core adapter behavior remains backward compatible:

```text
QdrantRetrievalStore default transport = REST
```

The experimental API and serving-performance benchmark explicitly choose gRPC.

The selected runtime chain is:

```text
ApiSettings
→ ApiRuntime
→ QdrantRetrievalStore
→ QdrantClient(prefer_grpc=True, grpc_port=6334)
→ QdrantDenseBackend
```

Public file search remains unchanged.

No retry framework, fallback path, circuit breaker, pool-size tuning, or
collection rebuild was introduced.

---

## 5. gRPC reliability evidence

Before the final end-to-end run, two independent backend-only full runs were
executed:

```text
backend_full_grpc_1:
concurrency 8 = 680 / 680 successful
errors = 0
quality_ok = true

backend_full_grpc_2:
concurrency 8 = 680 / 680 successful
errors = 0
quality_ok = true
```

The final full end-to-end run also passed:

```text
backend Qdrant concurrency 8:
680 / 680 successful
errors = 0

API Qdrant concurrency 8:
204 / 204 successful
errors = 0
```

This establishes that the observed REST socket failure was not reproduced by
the gRPC path in the current Windows + Docker Desktop environment and workload.

This is build- and environment-scoped evidence, not a universal guarantee for
all hosts, Qdrant versions, or future corpus sizes.

---

## 6. Final full benchmark result

Final report:

```text
preset = full
query_count = 34
qdrant_transport = grpc
error_count = 0
quality_ok = true
```

Strict validator:

```text
source_error_count = 0
source_comparison_count = 681
required_failed_count = 0
required_failed_checks = []
```

Safety markers:

```text
benchmark_only = true
production_default_changed = false
public_qdrant_promoted = false
fallback_used = false
```

### 6.1 Quality

```text
comparison_count_across_scenarios = 681
mean_overlap_at_k = 1.000
min_overlap_at_k = 1.000
exact_same_order_count = 681
result_count_mismatch_count = 0
duplicate_id_failure_count = 0
```

### 6.2 Encoding

```text
model_load_ms = 15177.284
first_encode_ms = 157.500
warm_encode_p50_ms = 6.483
warm_encode_p95_ms = 7.283
```

The model-load number is environment- and cache-sensitive and should not be
treated as a stable serving SLA.

---

## 7. Backend-only performance

### Sequential

| backend | requests | errors | p50 ms | p95 ms | max ms | throughput rps |
|---|---:|---:|---:|---:|---:|---:|
| file | 680 | 0 | 8.258 | 10.239 | 33.313 | 113.819 |
| Qdrant gRPC | 680 | 0 | 4.415 | 5.149 | 15.199 | 218.431 |

On the tested machine, Qdrant gRPC:

- reduced sequential backend p50 by about 46.5%;
- reduced sequential backend p95 by about 49.7%;
- delivered about 1.92 times the sequential throughput of file dense.

### Concurrency

| backend | concurrency | requests | errors | p50 ms | p95 ms | throughput rps |
|---|---:|---:|---:|---:|---:|---:|
| file | 1 | 680 | 0 | 8.173 | 9.024 | 116.629 |
| file | 2 | 680 | 0 | 10.942 | 13.580 | 170.568 |
| file | 4 | 680 | 0 | 16.153 | 27.682 | 228.871 |
| file | 8 | 680 | 0 | 26.329 | 46.950 | 276.089 |
| Qdrant gRPC | 1 | 680 | 0 | 4.473 | 5.276 | 214.095 |
| Qdrant gRPC | 2 | 680 | 0 | 5.284 | 6.368 | 359.716 |
| Qdrant gRPC | 4 | 680 | 0 | 6.914 | 11.477 | 524.608 |
| Qdrant gRPC | 8 | 680 | 0 | 16.078 | 31.037 | 451.630 |

Qdrant gRPC reached the highest measured throughput at concurrency `4`.
Throughput declined at `8`, while remaining error-free and still above the
file backend. This is a measured local saturation signal, not a correctness
failure.

---

## 8. API performance

### Fresh process

| target | startup ms | first request client ms | server total ms | server unattributed ms | client overhead ms |
|---|---:|---:|---:|---:|---:|
| file dense | 26800.815 | 216.106 | 194.828 | 0.499 | 21.278 |
| Qdrant gRPC | 25809.338 | 1014.653 | 1009.535 | 808.577 | 5.118 |

The first Qdrant request has substantial unattributed cold-start work, most
likely associated with lazy backend/channel creation and first-use
initialization. This is a known limitation of the experimental endpoint.

### Warm sequential

| target | requests | errors | p50 ms | p95 ms | max ms | throughput rps |
|---|---:|---:|---:|---:|---:|---:|
| file dense | 204 | 0 | 56.148 | 64.500 | 85.077 | 17.382 |
| Qdrant gRPC | 204 | 0 | 51.903 | 61.648 | 82.972 | 18.498 |

On the tested warm API path, Qdrant gRPC:

- reduced p50 by about 7.6%;
- reduced p95 by about 4.4%;
- increased throughput by about 6.4%.

### API concurrency

| target | concurrency | requests | errors | p50 ms | p95 ms | throughput rps |
|---|---:|---:|---:|---:|---:|---:|
| file dense | 1 | 204 | 0 | 61.654 | 77.255 | 15.536 |
| file dense | 2 | 204 | 0 | 107.195 | 140.105 | 15.271 |
| file dense | 4 | 204 | 0 | 211.862 | 280.505 | 18.198 |
| file dense | 8 | 204 | 0 | 429.470 | 536.722 | 18.422 |
| Qdrant gRPC | 1 | 204 | 0 | 54.785 | 73.130 | 17.436 |
| Qdrant gRPC | 2 | 204 | 0 | 97.340 | 125.393 | 19.583 |
| Qdrant gRPC | 4 | 204 | 0 | 194.778 | 246.263 | 20.305 |
| Qdrant gRPC | 8 | 204 | 0 | 408.457 | 487.822 | 19.267 |

The API path is dominated by work outside vector search, so the backend-level
advantage is attenuated at the endpoint boundary.

---

## 9. Stage timing interpretation

Warm Qdrant API sequential stage timings:

| stage | p50 ms | p95 ms | max ms |
|---|---:|---:|---:|
| encode | 11.590 | 17.172 | 22.929 |
| hydrate | 31.376 | 36.437 | 51.089 |
| Qdrant search | 5.216 | 5.968 | 12.619 |
| total | 48.475 | 57.014 | 77.422 |

Derived timings:

| field | p50 ms | p95 ms | max ms |
|---|---:|---:|---:|
| client overhead | 3.479 | 4.816 | 28.476 |
| known server stages | 48.270 | 56.820 | 77.154 |
| server unattributed | 0.193 | 0.218 | 0.379 |

Approximate warm p50 share:

```text
hydration ≈ 65%
encoding ≈ 24%
Qdrant search ≈ 11%
```

The primary warm-path bottleneck is therefore canonical hydration/document
lookup, not vector search.

Future latency work should first investigate hydration structure, lookup
layout, and response construction before attempting to optimize Qdrant search.

---

## 10. Integrated validation closure

The final integrated command covered:

```text
Golden Set strict validation
Discovery API integration and strict validation
topic clusters
topic projection
Streamlit static validation
Qdrant collection validation
34-query file/Qdrant comparison
Qdrant profile sweep
full serving-performance benchmark
strict serving-performance validator
experimental Qdrant API
Postgres smoke
full strict Definition of Done
```

Final results:

```text
Discovery integration = 34 passed, 4 expected DB-only skips
selected ef_256 = 34 / 34 exact
exact oracle = 34 / 34 exact
serving errors = 0
serving quality comparisons = 681 exact
DB total documents = 60954
canonical documents = 60954
canonical multisource documents = 9192
dod_passed = true
required_failed_count = 0
Discovery API regression passed
```

The profile sweep remained consistent:

```text
default = 33 / 34
ef_128 = 33 / 34
ef_256 = 34 / 34
ef_512 = 34 / 34
exact = 34 / 34
```

---

## 11. Architectural decision after this slice

The current decision remains conservative:

```text
public /search?mode=lexical = public lexical
public /search?mode=dense = file dense
public /search?mode=hybrid = file dense component

/experimental/search/qdrant = Qdrant gRPC
```

Additional rules:

```text
Qdrant remains optional
/health remains Qdrant-independent
hidden fallback remains prohibited
public response modes remain unchanged
similar papers remain unchanged
Discovery ranking remains unchanged
```

Serving performance and transport reliability are now sufficiently evidenced
for the experimental path.

They are not sufficient by themselves to authorize public promotion.

---

## 12. Remaining gates

### Controlled hybrid evaluation

Still required:

```text
lexical + FileDenseBackend
vs
lexical + QdrantDenseBackend
```

Keep common:

- encoder;
- lexical candidate generation;
- candidate counts;
- score normalization;
- merge;
- ranking;
- response schema;
- Golden Set.

Measure:

- exact candidate and final-result differences;
- query-level quality;
- latency;
- failure semantics;
- operational metadata.

### Public-exposure decision

Possible outcomes remain:

- keep Qdrant experimental;
- add explicit opt-in backend selection;
- choose the backend at deployment composition;
- postpone promotion until scale or product needs justify it.

No promotion is a valid outcome.

### Deployment-level reliability

Before production-like adoption, consider:

- explicit timeout failure injection;
- rollback drill;
- longer soak/restart evidence;
- deployed-network benchmark;
- metrics and tracing only if deployment complexity justifies them.

---

## 13. Reproduction commands

Set the file runtime:

```bat
set ML_RADAR_SEARCH_BACKEND=file
```

Run the benchmark:

```bat
python -m scripts.evaluation.run_qdrant_serving_performance ^
  --preset full
```

Strict validation:

```bat
python -m scripts.validation.check_qdrant_serving_performance --strict
```

Integrated milestone validation:

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

## 14. Definition of Done

- [x] Read-only benchmark configuration exists.
- [x] Backend-only file/Qdrant comparison exists.
- [x] Fresh and warm API measurement exists.
- [x] Sequential and concurrent scenarios exist.
- [x] Resource capability reporting is explicit.
- [x] Repeated records use compact result digests.
- [x] Full quality IDs are retained for comparisons.
- [x] Failure records preserve task context and exception chains.
- [x] Strict validator exists.
- [x] Regression runner integration is opt-in.
- [x] REST concurrency failure was reproduced and diagnosed.
- [x] Strict zero-error policy was retained.
- [x] Explicit gRPC transport support was implemented.
- [x] Two independent backend gRPC full runs passed.
- [x] Final full backend gRPC run passed.
- [x] Final full API gRPC run passed.
- [x] 681 comparisons were exact.
- [x] Strict serving-performance validation passed.
- [x] Integrated Discovery regression passed.
- [x] Full strict Definition of Done passed.
- [x] Public defaults remain unchanged.
- [x] Public Qdrant promotion was not performed.
- [x] Hidden fallback was not introduced.

---

## 15. Final conclusion

The performance slice produced a concrete engineering result rather than a
decorative benchmark:

1. it exposed a reproducible REST transport failure under direct concurrency;
2. it preserved enough diagnostic context to identify the Windows socket path;
3. it rejected the failing run instead of relaxing the gate;
4. it introduced explicit gRPC transport for the experimental path;
5. it demonstrated zero transport errors across repeated backend and complete
   end-to-end runs;
6. it preserved exact result parity;
7. it showed a meaningful backend-level performance advantage for Qdrant gRPC;
8. it identified hydration, not vector search, as the main warm API bottleneck.

The next retrieval slice should be controlled hybrid evaluation, followed by an
explicit public-promotion decision.
