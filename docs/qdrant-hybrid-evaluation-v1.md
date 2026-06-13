# Qdrant Hybrid Evaluation v1

## Document status

```text
checkpoint: Qdrant Hybrid Evaluation v1
status: implemented / validated on feature branch, pending PR merge
date: 2026-06-13
feature branch: retrieval/qdrant-hybrid-evaluation-v1
base main checkpoint: 6358164
previous checkpoint: Qdrant Serving Performance v1 merged in PR #19

public /search backend change: none
public dense/hybrid backend: file
experimental Qdrant transport: gRPC
fallback: absent
canonical data changed: no
retrieval build changed: no
Qdrant collection mutated: no
```

This checkpoint records the controlled comparison between the existing
file-backed hybrid search and the same hybrid strategy with only the dense
candidate component replaced by `QdrantDenseBackend`.

It is an evaluation and evidence slice. It does not promote Qdrant to public
`/search` and does not change public API semantics.

---

## 1. Goal

The slice answers one narrow question:

```text
Does replacing only the dense component of the existing hybrid strategy with
Qdrant preserve query-level behavior when the encoder, lexical branch,
candidate budgets, normalization, merge, ranking, metrics, and Golden Set are
held constant?
```

The required comparison is:

```text
lexical candidates + FileDenseBackend
vs
lexical candidates + QdrantDenseBackend
```

Everything after dense candidate generation is shared.

---

## 2. Non-goals

This slice does not include:

- public backend selection;
- public `vector_backend` parameter;
- switching `/search?mode=dense` to Qdrant;
- switching `/search?mode=hybrid` to Qdrant;
- backend-specific public modes;
- hidden or explicit fallback;
- similar-paper migration;
- DB-native dense or hybrid;
- new embeddings;
- retrieval artifact rebuild;
- canonical corpus changes;
- Qdrant collection rebuild or upload;
- retry, circuit breaker, or telemetry platform work.

---

## 3. Preconditions

Active retrieval state:

```text
canonical corpus documents = 60954
retrieval build_id = 20260504T164021Z
embedding model = sentence-transformers/all-MiniLM-L6-v2
embedding dimension = 384
dense vectors normalized = true
```

Active Qdrant state:

```text
collection = ml_radar_dense_benchmark_v1
points_count = 60954
vector_size = 384
distance = Cosine
transport = gRPC
grpc_port = 6334
profile = ef_256
exact = false
hnsw_ef = 256
```

Golden Set:

```text
enabled queries = 34
explicit canonical-labeled queries = 34
weak-pattern-only enabled queries = 0
```

The selected profile had already passed dense parity at the earlier evaluation
depth:

```text
ef_256 = 34 / 34 exact order
exact oracle = 34 / 34 exact order
```

---

## 4. Architecture and invariants

The architecture remains:

```text
query text
→ common normalization
→ common encoder
→ prepared normalized query vector
→ shared lexical retrieval
→ selected DenseSearchBackend
→ shared hybrid merge
→ strict evaluation hydration
→ optional shared ranking
→ common Golden Set metrics
```

Only this node changes:

```text
DenseSearchBackend
├── FileDenseBackend
└── QdrantDenseBackend
```

Backends continue to own only dense candidate generation.

They do not own:

- query encoding;
- lexical retrieval;
- hybrid normalization;
- hybrid score composition;
- canonical hydration;
- product ranking;
- pagination;
- API response serialization;
- fallback policy.

---

## 5. Shared hybrid merge extraction

Before the paired evaluation, duplicated hybrid score composition was extracted
into:

```text
radar_core/retrieval/hybrid_merge.py
```

The shared kernel owns:

```text
lexical and dense score maps
→ independent min-max normalization
→ union of canonical IDs
→ weighted score composition
→ current score-based ordering
```

It does not own retrieval, hydration, ranking, pagination, or serialization.

Callers migrated to the shared kernel:

```text
services/api/search_service.py
scripts/evaluation/run_search_quality_controlled_experiments.py
```

Characterization tests proved that the extraction preserved:

- public and controlled merge equivalence;
- public candidate-budget policy;
- raw lexical, dense, and hybrid scores;
- existing hydration behavior;
- existing ordering semantics;
- retrieval-evaluation and controlled-experiment quality behavior.

No new tie-breaker was introduced.

---

## 6. Implementation

New configuration:

```text
configs/qdrant_hybrid_evaluation_v1.yaml
```

Pure evaluation helpers:

```text
scripts/evaluation/qdrant_hybrid_evaluation.py
```

Responsibilities:

- config validation;
- public candidate-depth resolution;
- scenario matrix construction;
- query-vector fingerprinting;
- lexical-input digests;
- typed dense-candidate adaptation;
- strict hydration;
- shared scoring-contract validation;
- ranked-ID comparison;
- metric deltas;
- determinism summaries;
- difference classification;
- paired scenario execution.

Composition runner:

```text
scripts/evaluation/run_qdrant_hybrid_evaluation.py
```

Strict evidence validator:

```text
scripts/validation/check_qdrant_hybrid_evaluation.py
```

Regression integration:

```text
scripts/validation/run_discovery_api_regression.py
--include-qdrant-hybrid-evaluation
```

Tests:

```text
tests/smoke/test_hybrid_merge_contract.py
tests/smoke/test_qdrant_hybrid_evaluation.py
tests/smoke/test_run_qdrant_hybrid_evaluation.py
tests/smoke/test_qdrant_hybrid_evaluation_validator.py
tests/smoke/test_qdrant_regression_runner.py
```

---

## 7. Evaluation matrix

The full matrix contains four scenarios per query:

```text
top_k=10, candidate_k=50, rank=false
top_k=10, candidate_k=50, rank=true
top_k=20, candidate_k=100, rank=false
top_k=20, candidate_k=100, rank=true
```

Candidate budgets follow the current public policy:

```text
candidate_k = min(
    max(top_k + offset, top_k * 5, 50),
    corpus_size,
)
```

Fixed settings:

```text
offset = 0
sort_by = relevance
normalization = minmax
lexical_weight = 0.55
dense_weight = 0.45
```

Determinism policy:

```text
normal scenario repeats = 2
non-exact scenario repeats = 5
```

Total coverage:

```text
34 queries × 4 scenarios = 136 scenarios
```

---

## 8. Paired execution contract

For each query:

```text
1. encode the query once;
2. fingerprint the prepared vector;
3. execute lexical retrieval once at maximum candidate depth;
4. reuse the same lexical inputs for both branches;
5. send the same DenseSearchRequest to both dense backends;
6. adapt typed dense candidates to common score rows;
7. run the shared hybrid merge;
8. hydrate every result strictly;
9. optionally run the same rank_results() implementation;
10. truncate to final top_k;
11. calculate the same Golden Set metrics;
12. compare dense and final ranked IDs;
13. repeat non-exact scenarios five times;
14. classify every difference.
```

Strict evaluation hydration intentionally differs from legacy public silent-skip
behavior: any missing canonical document fails the scenario explicitly.

---

## 9. Safety contract

The config and report require:

```text
evaluation_only = true
production_default_changed = false
public_qdrant_promoted = false
fallback_used = false
canonical_data_changed = false
retrieval_build_changed = false
qdrant_collection_mutated = false
```

Additional invariants:

- runtime backend mode must be `file`;
- Qdrant transport must match the configured gRPC contract;
- Qdrant profile must match `ef_256`;
- file and Qdrant build IDs must match the active retrieval build;
- result IDs must be unique;
- scores and timings must be finite;
- query-vector fingerprints must be identical across scenarios for a query;
- lexical evidence must be identical for scenarios with the same candidate depth;
- fallback is forbidden;
- every difference must be classified;
- blocking classifications are forbidden;
- deterministic results are required.

---

## 10. Focused test evidence

```text
test_qdrant_hybrid_evaluation.py = 34 passed
test_run_qdrant_hybrid_evaluation.py = 10 passed
test_qdrant_hybrid_evaluation_validator.py = 8 passed
test_hybrid_merge_contract.py = 13 passed
test_dense_backend_contract.py = 19 passed
test_qdrant_regression_runner.py = 9 passed
```

Focused total:

```text
93 passed
```

The runner and validator also passed one-query smoke behavior:

```text
non-strict validator accepts structurally complete smoke evidence
strict validator rejects incomplete Golden Set coverage
```

---

## 11. Full-run result

Execution:

```text
selected_queries = 34
expected_scenarios = 136
successful_scenarios = 136
error_count = 0
quality_ok = true
```

Strict validation:

```text
schema_version = qdrant_hybrid_evaluation_quality_v1
input_schema_version = qdrant_hybrid_evaluation_v1
strict = true
selected_query_count = 34
expected_scenario_count = 136
required_failed_count = 0
```

Safety and integrity:

```text
fallback = 0
blocking classifications = 0
determinism failures = 0
mapping failures = 0
hydration failures = 0
build mismatches = 0
non-finite scores = 0
```

---

## 12. Parity and quality summary

Classifications:

```text
exact_match = 132
dense_candidate_difference_no_final_effect = 2
same_set_different_order = 2
```

Dense parity:

```text
mean overlap = 0.999412
minimum overlap = 0.98
exact dense order = 132 / 136
```

Final hybrid parity:

```text
mean overlap = 1.0
minimum overlap = 1.0
identical final result sets = 136 / 136
exact final order = 134 / 136
```

Metric deltas use:

```text
Qdrant metric - File metric
```

Observed deltas:

```text
Hit       = 0 for all scenarios
Precision = 0 for all scenarios
Recall    = 0 for all scenarios
MRR       = 0 for all scenarios
nDCG min  = 0
nDCG mean = 0.000017
nDCG max  = +0.002368
```

There is no measured quality regression.

---

## 13. Non-exact scenario analysis

All four non-exact scenarios occur only at:

```text
top_k = 20
candidate_k = 100
```

### 13.1 diffusion_models_001

Dense difference:

```text
file-only:
rank 68 → 1ef322e76542d583db3bc8aca69f3462
rank 96 → 1772186b99cc6378b3241749b14ac203

Qdrant-only:
rank 99  → 0b6c04b96de650db2b91388f8a9a180d
rank 100 → f366284e8cc6706016c080ded174511d
```

Unranked final result:

```text
final overlap = 1.0
final set = identical
final order = rank-9/rank-10 swap
metric deltas = 0
repeat_count = 5
deterministic = true
```

Ranked final result:

```text
final overlap = 1.0
final order = identical
metric deltas = 0
repeat_count = 5
deterministic = true
```

### 13.2 rag_evaluation_001

Dense difference:

```text
file-only:
rank 63 → dc3086252c9a1d1ed6903f0372b392a9
rank 78 → 29a5dbff0b29fb56c838f53339a8be1e

Qdrant-only:
rank 99  → 0883488608931bb0aeaf0e5ed8af1514
rank 100 → ff9d45fa527d6233fdb0dac928afbeff
```

Unranked final result:

```text
final overlap = 1.0
final order = identical
metric deltas = 0
repeat_count = 5
deterministic = true
```

Ranked final result:

```text
final overlap = 1.0
final set = identical
final order = rank-9/rank-10 swap
Hit/Precision/Recall/MRR deltas = 0
nDCG delta = +0.002368 for Qdrant
repeat_count = 5
deterministic = true
```

---

## 14. Interpretation

The evidence supports this classification:

```text
stable, non-blocking approximate-search or score-boundary differences at
candidate depth 100, with no final-set loss and no measured quality regression
```

The evidence does not support these defect classes:

- mapping defect;
- build mismatch;
- hydration defect;
- duplicate candidate defect;
- non-finite score;
- fallback;
- nondeterministic result.

The differences are not limited to file ranks 99-100: the omitted file
candidates include ranks 63, 68, 78, and 96. Therefore the precise statement is
not “only a last-rank swap.” The correct statement is that the approximate
dense top-100 sets differ by two IDs for two queries, while the complete final
hybrid top-20 set remains unchanged.

An optional exact Qdrant top-100 diagnostic may further distinguish HNSW recall
from score-order boundary effects. It is not required for this checkpoint.

---

## 15. Regression integration

New opt-in flag:

```text
--include-qdrant-hybrid-evaluation
```

It adds two ordered steps:

```text
run_qdrant_hybrid_evaluation
→ check_qdrant_hybrid_evaluation --strict
```

Both steps run with:

```text
ML_RADAR_SEARCH_BACKEND=file
```

The default Discovery regression remains unchanged.

Integrated run result:

```text
Golden Set strict validator = green
Discovery API integration = 34 passed, 4 expected DB-only skips
Discovery API strict validator = green
topic cluster validator = green
topic projection validator = green
Streamlit static validator = green
Qdrant hybrid evaluation = 136 / 136 successful
Qdrant hybrid strict validator = required_failed_count 0
Discovery API regression passed
```

---

## 16. Generated reports

Evaluation:

```text
artifacts/reports/evaluation/qdrant_hybrid_evaluation_latest.json
artifacts/reports/evaluation/qdrant_hybrid_evaluation_latest.md
artifacts/reports/evaluation/history/qdrant_hybrid_evaluation_<timestamp>.json
artifacts/reports/evaluation/history/qdrant_hybrid_evaluation_<timestamp>.md
```

Validation:

```text
artifacts/reports/validation/qdrant_hybrid_evaluation_quality_latest.json
artifacts/reports/validation/qdrant_hybrid_evaluation_quality_latest.md
artifacts/reports/validation/history/qdrant_hybrid_evaluation_quality_<timestamp>.json
artifacts/reports/validation/history/qdrant_hybrid_evaluation_quality_<timestamp>.md
```

`artifacts/` remains ignored in the active workflow. Reports are operational
evidence and are not routine commit candidates.

---

## 17. Reproduction commands

Focused tests:

```bat
python -m pytest ^
  tests/smoke/test_qdrant_hybrid_evaluation.py ^
  tests/smoke/test_run_qdrant_hybrid_evaluation.py ^
  tests/smoke/test_qdrant_hybrid_evaluation_validator.py ^
  tests/smoke/test_hybrid_merge_contract.py ^
  tests/smoke/test_dense_backend_contract.py ^
  tests/smoke/test_qdrant_regression_runner.py ^
  -q
```

Full evaluation:

```bat
set ML_RADAR_SEARCH_BACKEND=file

python -m scripts.evaluation.run_qdrant_hybrid_evaluation
python -m scripts.validation.check_qdrant_hybrid_evaluation --strict
```

Integrated regression:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-qdrant-hybrid-evaluation
```

---

## 18. PR boundary

This PR includes:

- shared hybrid merge extraction;
- characterization and regression protection;
- evaluation config and pure helpers;
- paired scenario executor;
- strict evidence validator;
- full 34-query evaluation;
- opt-in integrated regression;
- checkpoint and planning documentation.

This PR does not include public promotion.

Public state after merge remains:

```text
/search?mode=dense  → FileDenseBackend
/search?mode=hybrid → FileDenseBackend as dense component
/experimental/search/qdrant → QdrantDenseBackend over gRPC
/health → Qdrant-independent
fallback → absent
```

---

## 19. Decision and next step

Checkpoint verdict:

```text
GREEN
```

The controlled hybrid evidence is sufficient to close this slice.

Recommended next step:

```text
explicit public/deployment backend-selection design and decision
```

Possible outcomes:

- keep Qdrant experimental;
- expose an explicit opt-in selector;
- select Qdrant at deployment composition;
- postpone promotion.

No promotion is required merely because the technical evidence is positive.

Any future exposure must remain explicit, observable, reversible, build-scoped,
and free of hidden fallback.
