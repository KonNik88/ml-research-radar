# Qdrant Search Promotion Plan v1

## Document status

```text
version: v1
status: design proposal / promotion gate definition
implementation status: not started
runtime behavior change: none
public API change: none
```

This document defines the controlled path for evolving Qdrant from the current experimental vector-serving boundary into a possible implementation backend for dense retrieval in ML Research Radar.

The document is intentionally design-first. It does **not** authorize changing the default behavior of `GET /search`, adding a new public search mode, introducing hidden fallback, or making Qdrant part of core service readiness.

---

## 1. Purpose

The purpose of this plan is to prevent an implementation detail from leaking prematurely into the public search contract.

The central distinction is:

```text
mode = retrieval strategy
vector_backend = implementation backend for the dense component
```

Examples of retrieval strategies:

```text
lexical
dense
hybrid
```

Examples of dense vector backends:

```text
file
qdrant
```

Therefore, the project should not immediately grow public modes such as:

```text
dense_qdrant
hybrid_qdrant
hybrid_ranked_qdrant
```

Qdrant should first become a well-defined internal backend implementation with explicit compatibility, quality, observability, and failure semantics.

---

## 2. Project architecture context

ML Research Radar is a paper-centric canonical corpus and discovery platform.

The relevant architecture is:

```text
canonical paper corpus
→ retrieval artifacts
→ retrieval runtime
→ search service
→ public Search API
```

Additional derived layers include:

```text
Postgres materialized serving
artifact evidence
paper features
ranking and discovery
similar papers
topic clusters and projections
Discovery API
Streamlit UI
```

Qdrant belongs to the derived retrieval-serving plane. It is not a canonical data source and is not allowed to mutate paper truth.

Main invariants:

```text
canonical_documents.jsonl = paper-level truth
Postgres = rebuildable materialized serving layer
retrieval artifacts = derived retrieval layer
Qdrant = optional derived vector-serving layer
paper_features = derived discovery feature layer
Discovery API = product layer over validated derived artifacts
Streamlit UI = thin API client
```

Critical boundary:

```text
No Qdrant operation may mutate canonical truth.
```

---

## 3. Current stable baseline

Current retrieval baseline:

```text
canonical corpus documents: 60954
retrieval build_id: 20260504T164021Z
embedding model: sentence-transformers/all-MiniLM-L6-v2
embedding dimension: 384
dense embeddings shape: [60954, 384]
```

Current Qdrant baseline:

```text
collection: ml_radar_dense_benchmark_v1
points_count: 60954
vector_size: 384
distance: Cosine
collection status: green
optimizer status: ok
```

Current Qdrant boundary:

```text
GET /experimental/search/qdrant
```

Current public search behavior:

```text
GET /search?mode=lexical
GET /search?mode=dense
GET /search?mode=hybrid
```

Ranking is a separate option over retrieval behavior. In API terms, the current ranked hybrid path is:

```text
GET /search?mode=hybrid&rank=true
```

`hybrid_ranked` may be used as an evaluation label, but it is not a separate public search mode.

Current parity evidence:

```text
enabled golden queries: 22
top_k: 20
mean overlap ratio at k: 1.0
minimum overlap ratio at k: 1.0
exact same order: 22 / 22
comparison errors: 0
```

This is a strong technical parity signal for the current build and query set. It is **not** sufficient evidence for production promotion or general search-quality superiority.

---

## 4. Current decision

The current architectural decision is:

1. Do not add public `mode=dense_qdrant`.
2. Do not silently switch `mode=dense` through `ML_RADAR_VECTOR_BACKEND=qdrant`.
3. Keep `GET /experimental/search/qdrant` as the explicit Qdrant boundary.
4. Design an internal `DenseSearchBackend` abstraction.
5. Keep file-based dense retrieval as the reference implementation.
6. Introduce Qdrant as an experimental/evaluation implementation first.
7. Reconsider public exposure only after expanded golden relevance labels, parity checks, latency analysis, failure tests, and regression gates.

Recommended future structure:

```text
DenseSearchBackend
├── FileDenseBackend
└── QdrantDenseBackend
```

This structure is a target design, not authorization to change `/search` behavior now.

---

## 5. Why public `mode=dense_qdrant` is postponed

A public `dense_qdrant` mode would be easy to expose and easy to test, but it would mix two distinct concepts:

```text
dense = retrieval strategy
qdrant = implementation backend
```

The likely mode surface would quickly become inconsistent:

```text
dense
dense_qdrant
hybrid
hybrid_qdrant
hybrid + rank
hybrid_qdrant + rank
```

This creates several problems:

- backend implementation leaks into the public strategy enum;
- future backends would require additional public modes;
- clients become coupled to storage technology;
- OpenAPI and validation enums expand without product-level value;
- removing or replacing a backend becomes a public compatibility issue;
- search evaluation labels and public API modes become easy to confuse.

The project therefore treats `dense_qdrant` as an experimental label only, not as the preferred long-term public API design.

---

## 6. Why a hidden backend switch is postponed

A config-driven backend selector is architecturally cleaner than backend-specific public modes:

```text
ML_RADAR_VECTOR_BACKEND=file|qdrant
```

However, switching this behavior silently would be unsafe before promotion gates exist.

The same request:

```text
GET /search?mode=dense
```

could change in:

- result ordering;
- numerical score details;
- latency;
- availability;
- timeout behavior;
- error semantics;
- filter support;
- runtime dependencies.

Such a change is acceptable only when it is:

- deliberate;
- observable;
- reversible;
- regression-tested;
- compatible with the current retrieval build;
- explicit in response metadata and runtime diagnostics.

Until then, file dense remains the effective backend for the public dense and hybrid paths.

---

## 7. Proposed internal responsibility boundary

The dense backend abstraction should represent **candidate retrieval only**.

It should not own:

- query text validation;
- embedding model loading;
- query encoding;
- canonical document hydration;
- response schema construction;
- product ranking;
- API fallback policy;
- Streamlit rendering.

Recommended flow:

```text
query text
→ common query validation
→ common query encoder
→ query vector
→ DenseSearchBackend.search(...)
→ canonical_id + score candidates
→ common hydration
→ optional common ranking
→ Search API response
```

This boundary is important because parity comparisons must measure backend retrieval rather than differences in encoding or hydration code.

The query encoder should remain common to both backends for a given retrieval build.

---

## 8. Proposed interface

Suggested location:

```text
radar_core/retrieval/dense_backend.py
```

The exact Python type system may use `Protocol`, an abstract base class, or another minimal interface. A protocol-style design is preferred unless shared implementation state requires an abstract base class.

Illustrative interface:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class DenseSearchRequest:
    query_vector: Sequence[float]
    top_k: int
    filters: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DenseSearchCandidate:
    canonical_id: str
    score: float
    backend_rank: int
    backend_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DenseSearchBackendInfo:
    backend_name: str
    build_id: str | None
    ready: bool
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DenseSearchBackendResult:
    candidates: list[DenseSearchCandidate]
    backend: DenseSearchBackendInfo
    timing_ms: Mapping[str, float] = field(default_factory=dict)


class DenseSearchBackend(Protocol):
    def search(self, request: DenseSearchRequest) -> DenseSearchBackendResult:
        ...

    def info(self) -> DenseSearchBackendInfo:
        ...
```

This is an architectural sketch. Names and exact types may change during implementation review.

---

## 9. Common result contract

The common backend result should expose backend-neutral fields:

```text
canonical_id
score
backend_rank
```

Backend-specific details may be placed under diagnostics metadata:

```text
point_id
dense_index
collection_name
native timing
native payload subset
```

Common search-service code must not depend on Qdrant-specific fields to hydrate documents or construct the normal search response.

The canonical identifier remains the join key between retrieval candidates and the canonical runtime.

Rules:

- every returned candidate must have a non-empty `canonical_id`;
- candidate ranks must be positive and deterministic for the returned order;
- scores must be finite numbers;
- duplicate canonical IDs in one result are invalid;
- returned count must not exceed `top_k`;
- unsupported filters must fail explicitly, not be silently ignored;
- backend metadata must never become canonical truth.

---

## 10. FileDenseBackend role

`FileDenseBackend` remains the reference implementation.

Its expected inputs are the current retrieval artifacts:

```text
dense embeddings
dense ids
retrieval manifest
```

Reference semantics:

- use the same query embedding model declared by the retrieval manifest;
- use the current exact file-based similarity implementation;
- preserve current public `/search?mode=dense` behavior;
- preserve the dense component used by `/search?mode=hybrid`;
- act as the parity oracle for Qdrant comparisons;
- remain available during all initial Qdrant promotion stages;
- not be removed as part of the first abstraction PR.

The abstraction must initially wrap or delegate to current file-dense behavior without rewriting its numerical logic unnecessarily.

A pure refactor is preferred over a simultaneous algorithm change.

---

## 11. QdrantDenseBackend role

`QdrantDenseBackend` is initially an experimental/evaluation implementation.

Expected responsibilities:

- query an existing compatible Qdrant collection;
- return canonical IDs and scores;
- expose collection/build diagnostics;
- validate collection compatibility before serving;
- fail explicitly when Qdrant is unavailable or incompatible;
- avoid collection creation, recreation, or upload in normal request handling;
- avoid canonical document hydration inside the backend;
- avoid implicit fallback to file dense.

Collection mutation belongs to benchmark/build tooling, not to the read-only serving backend.

Initial consumers may include:

```text
GET /experimental/search/qdrant
compare_qdrant_file_dense.py
Qdrant benchmark validators
future backend contract tests
```

Initial non-consumers:

```text
GET /search?mode=dense
GET /search?mode=hybrid
similar-paper production path
Discovery ranking paths
```

---

## 12. Build compatibility contract

A Qdrant collection is compatible with a file retrieval runtime only when the required build properties match.

Required compatibility signals:

```text
collection name is configured
collection exists
collection points_count == manifest corpus_doc_count
collection vector_size == dense embedding dimension
payload canonical_id is present
payload build_id matches retrieval build_id
payload dense_index is valid when used
query encoder model matches manifest embedding model
```

Current expected values:

```text
build_id: 20260504T164021Z
corpus_doc_count: 60954
vector_size: 384
collection_name: ml_radar_dense_benchmark_v1
```

`indexed_vectors_count` should remain visible as an operational diagnostic. It should not become a blocking compatibility gate until its expected lifecycle and Qdrant optimizer semantics are formally defined for this project.

A mismatch must not be hidden through fallback.

---

## 13. Filter semantics

The first backend interface may reserve a `filters` field, but implementation behavior must remain explicit.

Rules:

- a backend must declare whether it supports filters;
- unsupported filters must produce a structured error;
- a backend must not silently ignore filters;
- file and Qdrant filter semantics must be compared before filters are exposed publicly;
- Qdrant payload filtering must not create semantics that the reference file backend cannot reproduce unless this difference is explicitly documented as a capability difference.

Initial implementation may set:

```text
filters supported: false
```

for both dense backends, preserving current behavior.

---

## 14. Failure and fallback policy

### 14.1 Experimental endpoint

For:

```text
GET /experimental/search/qdrant
```

Qdrant failure must be explicit.

Examples:

```text
Qdrant unavailable
collection missing
collection/build mismatch
vector size mismatch
query failure
timeout
invalid result payload
```

No fallback to file dense should occur on the explicit experimental endpoint.

### 14.2 Future public backend selection

If Qdrant is later exposed through a public backend selector, the initial behavior should also be explicit failure:

```text
requested vector_backend=qdrant
Qdrant unavailable
→ 503-style structured error
```

The exact project error code should be finalized during API implementation. A candidate semantic name is:

```text
vector_backend_unavailable
```

### 14.3 Future optional fallback

Fallback may be introduced only as an explicit policy, for example:

```text
ML_RADAR_VECTOR_FALLBACK=file
```

or a future request option such as:

```text
fallback=file
```

If fallback is enabled, response metadata must disclose it.

Required metadata:

```json
{
  "requested_vector_backend": "qdrant",
  "effective_vector_backend": "file",
  "fallback_applied": true,
  "fallback_reason": "qdrant_unavailable"
}
```

Hidden fallback is prohibited because it makes evaluations and incident analysis unreliable.

---

## 15. Observability contract

If multiple vector backends are ever used by `/search`, the response must make the effective execution path visible.

Proposed response metadata:

```json
{
  "retrieval_backend": "file_runtime",
  "requested_vector_backend": "qdrant",
  "effective_vector_backend": "qdrant",
  "collection_name": "ml_radar_dense_benchmark_v1",
  "retrieval_build_id": "20260504T164021Z",
  "fallback_applied": false,
  "fallback_reason": null,
  "qdrant_ok": true
}
```

For the current public file-dense path, equivalent metadata may eventually report:

```json
{
  "retrieval_backend": "file_runtime",
  "requested_vector_backend": "file",
  "effective_vector_backend": "file",
  "retrieval_build_id": "20260504T164021Z",
  "fallback_applied": false
}
```

The first internal abstraction PR does not need to expand the public response schema. Public metadata changes belong to a later controlled exposure PR.

---

## 16. Runtime diagnostics

`GET /runtime` should remain the primary operational visibility surface for optional Qdrant readiness.

Expected Qdrant diagnostics include:

```text
configured
ok
collection_exists
collection_name
points_count
expected_corpus_doc_count
points_match_corpus
vector_size
expected_vector_size
build_id
expected_build_id
build_matches_runtime
status
optimizer_status
error
```

Runtime diagnostics should distinguish:

```text
core retrieval runtime readiness
optional Qdrant readiness
```

Qdrant diagnostic failure must not make the core file runtime unready.

---

## 17. Health semantics

Qdrant remains optional during all phases covered by this plan.

Therefore:

```text
GET /health
```

must not depend on Qdrant readiness while file retrieval remains the public reference implementation.

Expected behavior:

```text
file runtime ready + Qdrant unavailable
→ /health remains ready
→ /runtime.qdrant reports failure details
→ /experimental/search/qdrant fails explicitly
```

Only a future deployment that explicitly requires Qdrant as its selected production vector backend may define a separate readiness policy. Such a change requires a new design decision and must not be inferred from this document.

---

## 18. Latency interpretation

Current direct comparison evidence shows that file dense is faster for the current local 60k corpus:

```text
Qdrant mean query latency: approximately 23.8 ms
Qdrant p50: approximately 17.7 ms
file dense mean query latency: approximately 4.6 ms
file dense p50: approximately 4.6 ms
```

The experimental API may show much higher total latency because it includes additional stages:

```text
query encoding
Qdrant request
result hydration
FastAPI/TestClient overhead
cold model/runtime effects
```

Promotion must therefore use stage-level timings:

```text
validation_ms
encode_ms
backend_search_ms
hydrate_ms
rank_ms
total_ms
```

Latency gates must distinguish:

- warm and cold runs;
- direct backend comparison and full API latency;
- local development and deployed network conditions;
- p50, p95, and maximum latency;
- small current corpus and expected future corpus scale.

Qdrant does not need to beat local NumPy retrieval at 60k documents to be architecturally useful. Its potential value is serving isolation, persistence, filtering, scalability, concurrency, operational tooling, and future corpus growth. These benefits must still be demonstrated rather than assumed.

---

## 19. Quality and parity gates

Before Qdrant can influence public `/search`, all required gates must pass on a fresh compatible build.

### 19.1 Collection integrity gates

Required:

```text
collection exists
points_count == corpus_doc_count
vector_size == embedding dimension
payload canonical_id coverage == 100%
payload build_id matches retrieval build
error_count == 0
strict collection validator passes
```

### 19.2 Dense parity gates

Initial candidate thresholds:

```text
mean overlap@20 >= 0.99
minimum overlap@20 >= 0.95
error_count == 0
all enabled queries return results
order differences are reported and inspectable
```

The current 22-query comparison exceeds these thresholds, but the query set is not large enough for promotion.

### 19.3 Golden relevance gates

Required before public promotion:

- expand beyond the current 22 enabled queries;
- increase explicit canonical relevance labels;
- reduce reliance on weak title-pattern relevance;
- include ambiguous modern queries;
- include broad, mid-specific, and edge-diagnostic groups;
- include bio-ML, agents, RAG, diffusion, SSM, tabular, recommender, audio, and scientific-ML groups;
- inspect per-query regressions, not only aggregate metrics.

### 19.4 Search-quality gates

Required:

```text
retrieval evaluation validator passes
search quality experiment validator passes
controlled experiment validator passes
no unexplained regression in Recall@K
no unexplained regression in MRR@K
no unexplained regression in nDCG@K
no increase in empty-result rate
query-group regressions are reviewed
```

### 19.5 API gates

Required:

```text
experimental endpoint returns hydrated documents
result_count <= top_k
all results have rank/document/score
build_id is visible
collection_name is visible
vector backend is visible
structured errors are stable
```

### 19.6 Regression gates

Required before merge of any public exposure:

```text
file backend API smoke passes
Discovery API tests pass
Discovery API strict validator passes
topic cluster validator passes when relevant
topic projection validator passes when relevant
Streamlit static validator passes
DB artifact/search tests pass when touched
strict DoD passes for milestone-level changes
```

---

## 20. Golden set expansion dependency

Public Qdrant promotion is blocked on a stronger golden set.

The current query set is useful for smoke, parity, and regression detection. It is not a complete representation of real product search behavior.

Suggested expansion areas:

```text
large language model agents
agent tool use
retrieval-augmented generation
GraphRAG
diffusion models
diffusion transformers
Mamba and state space models
protein language models
tabular transformers
recommender-system ranking
self-supervised vision
audio and speech generation
scientific machine learning
model compression
prompt tuning
multimodal learning
artifact-ready/code-focused discovery
```

Labeling priority:

```text
explicit canonical IDs
→ graded relevance where useful
→ weak patterns only as diagnostic support
```

Golden set expansion should be completed and validated before a backend affects public search behavior.

---

## 21. Test strategy for the abstraction PR

The first code PR after this design document should be a behavior-preserving internal refactor.

Required tests:

### 21.1 Backend contract tests

Run the same contract against both implementations:

```text
returns no more than top_k
returns unique canonical IDs
returns finite scores
returns positive ordered ranks
returns stable backend identity
rejects invalid vector shape
rejects invalid top_k
rejects unsupported filters
```

### 21.2 File reference tests

Verify that wrapping current file dense logic does not change:

```text
canonical result IDs
result order
scores within tolerance
public /search response shape
public /search error behavior
```

### 21.3 Qdrant tests

Verify:

```text
collection compatibility checks
explicit unavailable behavior
missing collection behavior
build mismatch behavior
vector-size mismatch behavior
invalid payload behavior
experimental endpoint success
no implicit fallback
```

### 21.4 No-public-change tests

Explicitly assert:

```text
/search?mode=dense still uses file dense
/search?mode=hybrid still uses the file dense component
public mode enum remains lexical|dense|hybrid
/health remains independent of Qdrant
/experimental/search/qdrant remains available when Qdrant is ready
```

---

## 22. Proposed implementation phases

### Phase 0 — current state

```text
file dense serves public dense/hybrid search
Qdrant has an explicit experimental endpoint
Qdrant parity and benchmark tooling exist
runtime/UI show Qdrant diagnostics
```

### Phase 1 — design documentation

Deliverables:

```text
docs/qdrant-search-promotion-plan-v1.md
roadmap reference if appropriate
no runtime change
no API change
```

### Phase 2 — internal abstraction

Deliverables:

```text
DenseSearchBackend protocol
DenseSearchRequest
DenseSearchCandidate
DenseSearchBackendResult
FileDenseBackend
QdrantDenseBackend
backend contract tests
```

Restrictions:

```text
/search remains file-backed
Qdrant remains experimental
no public vector_backend parameter
no hidden fallback
```

### Phase 3 — evaluation-path adoption

Use the new abstraction in:

```text
experimental Qdrant endpoint
Qdrant/file parity comparison
Qdrant benchmark read path
backend contract tests
```

The purpose is to remove duplicated candidate-retrieval semantics without changing product behavior.

### Phase 4 — golden set and regression hardening

Deliverables:

```text
expanded golden set
more explicit relevance labels
fresh retrieval evaluation
fresh controlled experiments
fresh Qdrant parity report
latency report with stage timings
failure-injection checks
```

### Phase 5 — controlled public exposure decision

Possible outcomes:

```text
keep Qdrant experimental
expose vector_backend=qdrant as opt-in
select Qdrant through deployment config with explicit metadata
postpone promotion until corpus or deployment scale changes
```

This phase requires a separate implementation decision.

### Phase 6 — optional fallback

Fallback may be added only after explicit backend selection is stable and observable.

This is not part of the first promotion implementation.

---

## 23. Future public API direction

If Qdrant is eventually exposed through `/search`, the preferred scalable API concept is:

```text
GET /search?mode=dense&vector_backend=file
GET /search?mode=dense&vector_backend=qdrant
GET /search?mode=hybrid&vector_backend=qdrant
```

This is preferable to backend-specific mode names because:

```text
mode describes retrieval strategy
vector_backend describes dense implementation
rank remains a separate ranking option
```

However, a public `vector_backend` parameter is postponed until promotion gates pass.

Before public exposure, `vector_backend` may exist only as an internal dependency selection concept.

---

## 24. Hybrid retrieval semantics

Hybrid search contains at least two distinct components:

```text
lexical candidate generation
dense candidate generation
```

A future Qdrant-backed hybrid path should replace only the dense candidate backend unless the hybrid design is intentionally redesigned.

Expected conceptual flow:

```text
lexical candidates from current lexical backend
+
dense candidates from selected DenseSearchBackend
→ common hybrid merge
→ optional common ranking
```

The hybrid merge implementation, weights, normalization, ranking option, and public response shape should remain common.

A Qdrant abstraction PR must not duplicate hybrid merge logic inside `QdrantDenseBackend`.

---

## 25. Similar papers and Discovery scope

The first backend abstraction is scoped to query-to-paper dense candidate retrieval.

It does not automatically change:

```text
similar papers
paper detail
ranking profiles
topic clusters
topic projection
artifact discovery
Discovery API
```

Similar-paper Qdrant integration, if desired, must be evaluated separately because its input is typically a paper vector rather than an encoded text query and its regression contract is different.

Discovery remains a product layer over validated derived artifacts, not part of the backend selector itself.

---

## 26. Report and artifact policy

The project must preserve experiment safety rules.

Rules:

- do not write experimental outputs over accepted `latest` artifacts;
- do not recreate Qdrant collections inside request handling;
- use timestamped outputs for experiments;
- promote reports to `latest` only after validation;
- do not commit `artifacts/reports/**/history/*` as part of routine PRs;
- commit generated `latest` reports only when the repository intentionally tracks them and the PR is an explicit baseline update;
- avoid broad `git add .` after report-generating commands;
- inspect `git status` and `git diff` before commit.

The file dense artifacts remain the reference state for the current retrieval build.

---

## 27. Validation commands

Current validation commands relevant to this plan include:

```bash
python -m scripts.validation.check_qdrant_collection --strict
python -m scripts.evaluation.compare_qdrant_file_dense
python -m scripts.validation.check_qdrant_file_dense_comparison --strict
python -m scripts.validation.check_qdrant_api_experimental --strict
python -m scripts.validation.check_golden_queries --strict
python -m scripts.evaluation.run_retrieval_eval
python -m scripts.validation.check_retrieval_eval --strict
python -m scripts.evaluation.run_search_quality_experiments
python -m scripts.validation.check_search_quality_experiments --strict
python -m scripts.evaluation.run_search_quality_controlled_experiments
python -m scripts.validation.check_search_quality_controlled_experiments --strict
python -m scripts.validation.check_discovery_api --strict
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Integrated runner example:

```bash
python -m scripts.validation.run_discovery_api_regression \
  --include-qdrant-serving-poc \
  --include-qdrant-api \
  --include-retrieval-eval \
  --include-search-quality-experiments \
  --include-controlled-search-quality-experiments
```

On Windows `cmd.exe`, use `^` instead of `\` for line continuation, or run the command on one line.

Heavy collection recreation/upload benchmarking should be run intentionally:

```bash
python -m scripts.evaluation.run_qdrant_retrieval_benchmark
python -m scripts.validation.check_qdrant_retrieval_benchmark --strict
```

It is not required for every small refactor if a compatible collection already exists and the lightweight serving checks are sufficient.

---

## 28. Promotion checklist

Qdrant may influence public `/search` only when all required items are complete.

### Architecture

- [ ] `DenseSearchBackend` responsibility is documented and implemented.
- [ ] Query encoding is common and outside backend implementations.
- [ ] Hydration is common and outside backend implementations.
- [ ] Hybrid merge is common and outside backend implementations.
- [ ] File dense remains the reference implementation.
- [ ] Qdrant read path does not create or mutate collections.

### Compatibility

- [ ] Qdrant build ID matches retrieval runtime build ID.
- [ ] Point count matches corpus document count.
- [ ] Vector dimension matches embedding dimension.
- [ ] Payload canonical IDs are complete and valid.
- [ ] Collection mismatch fails explicitly.

### Quality

- [ ] Golden set is expanded beyond the current 22 queries.
- [ ] Explicit canonical relevance coverage is increased.
- [ ] Collection validator passes.
- [ ] File/Qdrant parity validator passes.
- [ ] Retrieval evaluation validator passes.
- [ ] Search-quality validator passes.
- [ ] Controlled-experiment validator passes.
- [ ] Query-level regressions are reviewed.

### Reliability

- [ ] Qdrant unavailable behavior is tested.
- [ ] Timeout behavior is tested.
- [ ] Missing collection behavior is tested.
- [ ] Build mismatch behavior is tested.
- [ ] No implicit fallback exists.
- [ ] Rollback to file dense is documented.

### Observability

- [ ] Runtime reports requested/effective vector backend.
- [ ] Runtime reports collection name and build compatibility.
- [ ] Response metadata reports effective backend when public exposure exists.
- [ ] Fallback metadata is explicit if fallback is ever enabled.
- [ ] Stage-level latency is recorded.

### Regression

- [ ] File `/search` behavior remains covered.
- [ ] API smoke tests pass.
- [ ] Discovery tests pass.
- [ ] Streamlit validator passes.
- [ ] DB tests pass when shared code is touched.
- [ ] Strict DoD passes for milestone-level promotion.

---

## 29. Rollout and rollback principles

Any future public exposure must be reversible without rebuilding canonical data.

Preferred rollout sequence:

```text
internal abstraction
→ experimental adoption
→ opt-in controlled exposure
→ monitored comparison
→ explicit promotion decision
```

Rollback target:

```text
FileDenseBackend
```

Rollback must not require:

- canonical corpus changes;
- retrieval artifact rebuild;
- Postgres rebuild;
- UI data migration.

If Qdrant-backed search produces regressions, the effective vector backend should be switched back to file while preserving diagnostics and reports for investigation.

---

## 30. Recommended PR sequence

### PR 1 — design document

```text
branch: docs/qdrant-search-promotion-plan-v1
```

Expected changes:

```text
docs/qdrant-search-promotion-plan-v1.md
optional small roadmap reference
```

No runtime or public API change.

### PR 2 — baseline refresh, if needed

Run and inspect:

```text
Qdrant collection quality
Qdrant/file dense comparison
experimental Qdrant API quality
Discovery regression
Streamlit static validation
```

Generated reports are committed only if this is an intentional tracked-baseline PR.

### PR 3 — golden set expansion

Expected changes:

```text
golden query definitions
explicit/graded relevance labels
candidate-labeling outputs when appropriate
validation reports
```

No public backend change.

### PR 4 — internal dense backend abstraction

Expected changes may include:

```text
radar_core/retrieval/dense_backend.py
FileDenseBackend
QdrantDenseBackend
backend contract tests
experimental endpoint integration
parity-tool integration
```

Restrictions:

```text
/search remains file-backed
public mode enum remains unchanged
/health remains Qdrant-independent
```

### PR 5 — controlled evaluation

Evaluate:

```text
file vs Qdrant dense
hybrid with file dense vs hybrid with Qdrant dense
latency stages
failure semantics
concurrency if relevant
expanded golden set quality
```

### PR 6 — public exposure decision

Possible decision outcomes:

```text
keep experimental only
expose opt-in vector_backend parameter
use deployment config with explicit response metadata
postpone until scale changes
```

No promotion is also a valid evidence-based decision.

---

## 31. Non-goals

This plan does not include:

- changing canonical reconciliation;
- adding new paper sources;
- changing paper feature scoring;
- making ranking fully config-driven;
- replacing lexical retrieval;
- redesigning Postgres search;
- moving artifact APIs out of DB serving;
- adding chunk-level retrieval;
- implementing RAG;
- changing topic clustering;
- changing topic projection;
- changing similar-paper serving;
- declaring Qdrant faster or better based on current 22-query evidence;
- making Qdrant required for `/health`;
- silently changing `/search` behavior.

These may be separate future initiatives, but they must not be mixed into the first Qdrant backend abstraction PR.

---

## 32. Acceptance criteria for this design stage

This document is accepted when the project agrees on the following statements:

1. Public search modes remain `lexical`, `dense`, and `hybrid`.
2. Ranked hybrid remains `mode=hybrid&rank=true`, not a new public mode.
3. File dense remains the public and reference backend for now.
4. Qdrant remains accessible through the explicit experimental endpoint.
5. Backend abstraction is designed around candidate retrieval only.
6. Query encoding and hydration remain shared outside backend implementations.
7. No hidden fallback is allowed.
8. Qdrant public exposure is blocked on stronger quality and relevance gates.
9. Future public exposure should prefer a distinct `vector_backend` concept over backend-specific search modes.
10. Any promotion must remain observable, reversible, and compatible with the active retrieval build.

---

## 33. Final recommendation

Recommended path:

```text
1. Keep current public /search behavior unchanged.
2. Keep /experimental/search/qdrant as the explicit Qdrant boundary.
3. Keep FileDenseBackend as the reference implementation.
4. Design and then implement DenseSearchBackend as an internal abstraction.
5. Use QdrantDenseBackend first only in experimental and evaluation paths.
6. Expand the golden set and strengthen explicit relevance labels.
7. Re-run parity, quality, latency, failure, API, UI, and regression gates.
8. Only then decide whether Qdrant should be exposed through vector_backend,
   selected through deployment configuration with explicit metadata,
   or remain experimental.
```

The project should optimize for controlled, explainable, testable evolution rather than for introducing a vector database into the public path as quickly as possible.
