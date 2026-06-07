# Qdrant Search Promotion Plan v1

## Document status

```text
version: v1
status: active promotion-gate and implementation-tracking document
last updated: 2026-06-07

internal DenseSearchBackend abstraction: implemented / green
experimental API adoption: implemented / green
evaluation tooling adoption: implemented / green

public /search backend change: none
public API change: none
Qdrant required for /health: no
public promotion decision: not made
```

This document defines the controlled path for evolving Qdrant from an experimental vector-serving implementation into a possible dense candidate backend for public search.

It records both:

1. the internal abstraction that is now implemented; and
2. the remaining gates that must pass before Qdrant may influence public `/search`.

This document does not authorize hidden switching, hidden fallback, backend-specific public modes, or Qdrant-dependent general readiness.

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

The project therefore does not add public modes such as:

```text
dense_qdrant
hybrid_qdrant
hybrid_ranked_qdrant
```

`dense_qdrant` remains an experimental endpoint label, not a public strategy enum.

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

`ef_256` is build- and evaluation-scoped. It must be re-evaluated after material changes to the corpus, embedding model, Qdrant version/configuration, index, or Golden Set.

---

## 4. Current architectural decision

1. File dense remains the public and reference implementation.
2. Qdrant remains optional.
3. `/experimental/search/qdrant` remains the explicit serving boundary.
4. Public `/search` modes remain `lexical|dense|hybrid`.
5. Public dense and hybrid remain file-backed.
6. No hidden fallback exists.
7. The internal abstraction is implemented and proven in experimental/evaluation paths.
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

## 6. Actual responsibility boundary

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
- full descending sort preserves current reference behavior;
- IDs, dimensions, finite values, and result invariants are validated;
- `FileDenseBackend` requires normalized retrieval artifacts.

`parity.py` imports the backend kernel and provides legacy report adapters and diagnostic logic. Runtime backend code does not depend on evaluation/parity code.

Scale optimization is not part of this abstraction milestone.

---

## 8. Qdrant profile-aware store

`QdrantRetrievalStore.search_vector()` now supports:

```text
exact: bool
hnsw_ef: int | None
```

It uses explicit Qdrant `SearchParams` when a non-default profile is requested.

Default calls preserve prior default Qdrant behavior.

The store remains:

- read-only;
- collection-creation free;
- upload free;
- canonical-truth agnostic;
- responsible only for low-level Qdrant access and normalization.

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

API composition and evaluation scripts construct the profile.

### Lifecycle compatibility checks

Checked once per backend instance:

```text
collection exists
points_count matches corpus count
vector_size matches retrieval build
distance matches expected distance
```

Compatibility state is cached.

Runtime reload creates a new backend and therefore invalidates the old compatibility cache.

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

Reason:

- no shared supported filter semantics currently exist for file and Qdrant backends;
- speculative capability would expand the contract without a real consumer;
- silently ignored filters are unacceptable.

Future filter support requires:

- a concrete product use case;
- explicit capability semantics;
- equivalent or documented backend behavior;
- validation and regression tests;
- a separate interface change.

---

## 11. Experimental API adoption

`GET /experimental/search/qdrant` now uses:

```text
common query encoder
→ runtime-owned lazy QdrantDenseBackend
→ backend-neutral candidates
→ common canonical document hydration
→ existing experimental response schema
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
- does not include Qdrant in core file-runtime readiness.

---

## 12. Evaluation tooling adoption

The following consumers use the common abstraction:

```text
scripts/evaluation/compare_qdrant_file_dense.py
scripts/evaluation/run_qdrant_search_profile_sweep.py
```

Removed duplication includes:

- local `SearchParams` creation;
- direct `query_points/search` branching;
- raw result normalization;
- local rank construction.

`parity.py` provides explicit adapters:

```text
file backend result → legacy file report rows
Qdrant backend result → legacy Qdrant report rows
```

Preserved without schema changes:

- comparison report versions;
- profile-sweep report version;
- mapping audit;
- mismatch details;
- determinism checks;
- classification;
- latency summaries;
- validators.

The collection build/upload benchmark remains outside this read-only backend abstraction.

---

## 13. Current adoption boundary

Current consumers:

```text
FileDenseBackend:
- exact comparison reference
- profile-sweep reference
- contract tests

QdrantDenseBackend:
- experimental API
- selected ef_256 comparison
- exact diagnostic comparison
- default/ef_128/ef_256/ef_512/exact sweep
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

Failures are explicit:

- Qdrant unavailable;
- collection missing;
- incompatible count;
- incompatible vector size;
- distance mismatch;
- query failure;
- invalid payload;
- build mismatch;
- mapping mismatch;
- invalid result score.

The experimental endpoint never silently serves file dense.

### Future public selection

A future explicit Qdrant request should initially fail explicitly when unavailable.

Candidate future semantic:

```text
vector_backend_unavailable
```

The exact public error contract requires a separate API decision.

### Optional future fallback

Fallback may exist only as an explicit, observable policy.

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

Current health rule:

```text
file runtime ready + Qdrant unavailable
→ /health remains ready
```

Qdrant remains optional.

Operational diagnostics belong in `/runtime` and logs.

A future promotion should expose:

- requested backend;
- effective backend;
- collection name;
- profile;
- build compatibility;
- fallback status;
- Qdrant availability;
- stage-level latency.

Public response-schema expansion is not part of the internal abstraction PR.

---

## 16. Validation evidence

Feature-branch tests:

```text
backend/parity/regression smoke = 69 passed
retrieval smoke = 4 passed
retrieval artifact smoke = 5 passed
API smoke = 6 passed
API errors = 3 passed
API reload = 3 passed
Discovery integration = 34 passed, 4 expected DB-only skips
```

Strict validators passed:

- Qdrant collection;
- experimental Qdrant API;
- 34-query file/Qdrant comparison;
- 34-query profile sweep;
- Golden Set;
- Discovery API;
- topic clusters;
- topic projection;
- Streamlit static validation;
- integrated Discovery regression.

Full comparison:

```text
selected profile = ef_256
selected full match = true
exact full match = true
errors = 0
blocking classifications = 0
```

Full profile sweep:

```text
default = 33/34
ef_128 = 33/34
ef_256 = 34/34
ef_512 = 34/34
exact = 34/34
errors = 0
strict required failures = 0
```

---

## 17. Memory and test-process observation

A combined heavy pytest process caused a transient system memory failure.

The same test files passed when run as separate Python processes.

Observed runtime lifecycle:

```text
initial file runtime load:
embedding model loaded from scratch

runtime reload:
embedding model reused

Qdrant backend before reload:
same cached instance

Qdrant backend after reload:
new instance
```

This indicates:

- model reuse during runtime reload works;
- Qdrant backend cache invalidation works;
- the incident is most likely test-process memory accumulation rather than backend correctness.

Until test infrastructure is hardened:

- run heavy integration groups separately;
- run comparison and sweep in separate processes;
- monitor RAM/commit/VRAM during future diagnosis.

This is technical debt, not a public-promotion gate by itself unless production-like load reproduces it.

---

## 18. Remaining promotion gates

Internal abstraction is complete. Public promotion is still blocked on the following evidence.

### Reliability

- timeout failure injection;
- unavailable Qdrant;
- collection missing;
- incompatible build/count/dimension;
- invalid payload and mapping;
- restart/reconnect behavior;
- deployment rollback procedure.

### Observability

- requested/effective backend metadata;
- stage-level latency;
- backend/profile runtime diagnostics;
- explicit fallback metadata if fallback is ever introduced.

### Performance

- warm/cold latency;
- p50/p95/max;
- concurrent requests;
- local and deployed conditions;
- resource use;
- behavior after corpus growth.

### Hybrid evaluation

- common lexical component;
- file vs Qdrant dense component;
- unchanged merge/ranking;
- query-level quality;
- latency;
- failure semantics.

### Product decision

Decide whether Qdrant provides enough value in:

- serving isolation;
- persistence;
- filtering;
- concurrency;
- scalability;
- deployment topology;
- operational tooling.

It does not need to beat local NumPy at 60k documents, but value must be demonstrated.

---

## 19. Future public API direction

If public selection is approved, preferred semantics are:

```text
/search?mode=dense&vector_backend=file
/search?mode=dense&vector_backend=qdrant
/search?mode=hybrid&vector_backend=qdrant
```

This is preferable to backend-specific modes.

Before adding this:

- define default and opt-in behavior;
- add response metadata;
- add structured errors;
- add OpenAPI enums;
- add rollback;
- add no-fallback or explicit-fallback policy;
- pass all promotion gates.

A deployment-level selector with explicit metadata may be preferable to a request parameter. That decision remains open.

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
- result enrichment differs;
- evaluation contract differs.

No automatic migration follows from the text-query backend abstraction.

Discovery remains unchanged until a separate evaluated slice is approved.

---

## 22. Report and artifact policy

Generated reports are operational evidence.

Current repository workflow ignores `artifacts/`.

Therefore:

- report generation does not normally create commit candidates;
- no `git restore` is needed for ignored, untracked reports;
- `git status` remains the source of truth;
- do not use broad `git add .`;
- commit tracked generated baselines only under an explicit future policy.

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
  tests/smoke/test_qdrant_regression_runner.py ^
  -q
```

Heavy API groups should run separately:

```bat
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

Integrated regression:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-qdrant-api
```

---

## 24. Implementation phase status

### Phase 0 — experimental baseline

Status: **complete**

- explicit Qdrant endpoint;
- collection validator;
- comparison tooling;
- runtime diagnostics.

### Phase 1 — design and Golden Set hardening

Status: **complete**

- promotion plan;
- 34-query fully explicit Golden Set;
- parity diagnosis;
- selected `ef_256`;
- exact oracle.

### Phase 2 — internal abstraction

Status: **complete / green**

- protocol and contracts;
- exact file kernel;
- FileDenseBackend;
- profile-aware Qdrant store;
- QdrantDenseBackend;
- typed errors;
- contract tests.

### Phase 3 — experimental and evaluation adoption

Status: **complete / green**

- experimental API;
- comparison;
- profile sweep;
- legacy report adapters;
- strict validators.

### Phase 4 — reliability, observability, performance, hybrid evidence

Status: **next**

### Phase 5 — controlled public exposure decision

Status: **not started**

Possible outcomes:

- remain experimental;
- opt-in public backend;
- deployment-level selection;
- postpone.

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
- [x] Dense index and optional dense-ID mapping checked.
- [x] Collection mismatch fails explicitly.
- [ ] Compatibility behavior tested in deployment failure injection.

### Quality

- [x] Golden Set expanded to 34 explicit canonical-labeled queries.
- [x] Collection validator passes.
- [x] File/Qdrant comparison validator passes.
- [x] Profile sweep validator passes.
- [x] `ef_256` and exact match 34/34.
- [ ] Controlled hybrid comparison completed.
- [ ] Performance/concurrency evidence completed.
- [ ] Public-exposure query-level review completed.

### Reliability

- [x] Missing collection behavior covered by backend tests.
- [x] Count/dimension/distance mismatch covered.
- [x] Invalid payload/mapping covered.
- [x] No implicit fallback exists.
- [ ] Timeout and reconnect behavior tested.
- [ ] Production-like restart behavior tested.
- [ ] Rollback procedure documented and exercised.

### Observability

- [x] Experimental endpoint exposes collection and build.
- [x] Backend info exposes profile and compatibility diagnostics.
- [x] Backend search timing is recorded.
- [ ] Public requested/effective backend metadata designed.
- [ ] Fallback metadata designed if fallback is approved.
- [ ] Production metrics and tracing implemented.

### Regression

- [x] Public file search tests pass.
- [x] API smoke/error/reload tests pass.
- [x] Discovery integration passes.
- [x] Discovery strict regression passes.
- [x] Topic validators pass.
- [x] Streamlit static validator passes.
- [ ] Milestone-level strict DoD rerun if required by merge policy.

---

## 26. Rollout and rollback

Preferred sequence:

```text
internal abstraction
→ experimental adoption
→ reliability/performance evidence
→ controlled opt-in
→ monitored decision
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

The current abstraction PR includes:

- backend contracts;
- FileDenseBackend;
- QdrantDenseBackend;
- explicit Qdrant profiles;
- runtime composition;
- experimental endpoint adoption;
- comparison migration;
- profile-sweep migration;
- tests;
- checkpoint documentation.

It does not include:

- public backend selection;
- public response metadata;
- hybrid Qdrant serving;
- similar-paper migration;
- fallback;
- new embeddings;
- source or canonical changes.

---

## 28. Final recommendation

Merge the internal abstraction after final review and documentation.

Then proceed with:

```text
failure injection
→ observability design
→ warm/cold and concurrency evidence
→ controlled hybrid evaluation
→ explicit promotion decision
```

Do not promote Qdrant merely because parity is green.

The correct question is whether Qdrant produces enough operational and scaling value to justify a public or deployment-level backend choice while remaining observable, reversible, and compatible with the active retrieval build.
