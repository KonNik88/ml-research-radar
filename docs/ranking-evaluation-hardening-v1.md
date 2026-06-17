# Ranking Evaluation and Hardening v1

## Document status

```text
status: design contract
slice: Ranking Evaluation and Hardening v1
branch: retrieval/ranking-evaluation-hardening-v1
base checkpoint: main after Current-State and Evidence Sync v1
public behavior change: none in the contract commit
```

This document defines the first evidence-driven hardening slice for the
optional product ranking applied to free-form search results.

The purpose is not to make ranking more complex. The purpose is to explain,
measure, and classify the effect of the current heuristic ranking before any
default, formula, normalization, or model is changed.

---

## 1. Problem statement

The current file-backed search pipeline supports optional ranking after
retrieval and filtering:

```text
query
→ lexical / dense / hybrid retrieval
→ candidate hydration
→ filters
→ optional rank_results(...)
→ pagination
→ API response
```

Current ranking weights:

```text
retrieval = 0.60
recency = 0.20
source_support = 0.10
metadata_quality = 0.10
```

Existing controlled search-quality evidence shows that enabling the current
heuristic ranking lowered nDCG in multiple hybrid settings. At the same time,
the current report does not preserve enough candidate-level evidence to answer:

- which papers moved;
- which relevant papers moved up or down;
- which ranking component caused the change;
- whether a relevant paper crossed the top-k boundary;
- whether the effect depends on candidate-pool size;
- whether the result is a true quality change or only a tie/boundary effect.

The project must answer those questions before promoting a new ranking formula,
changing public defaults, or introducing a learned reranker.

---

## 2. Scope boundary

This slice evaluates only the optional ranking used by free-form file-backed
search.

Primary implementation:

```text
radar_core/ranking/scoring.py
services/api/search_service.py
configs/scoring.yaml
```

Primary existing evaluation surface:

```text
configs/search_quality_controlled_experiments_v1.yaml
scripts/evaluation/run_search_quality_controlled_experiments.py
scripts/validation/check_search_quality_controlled_experiments.py
```

Explicitly outside this slice:

```text
Discovery ranking profiles
DB-specific ranking
embedding-model replacement
hybrid-weight promotion
candidate-generation changes
Qdrant promotion
similar-paper ranking
cross-encoder implementation
learned sparse retrieval
Golden Set expansion
canonical-corpus changes
retrieval-artifact rebuild
```

The Discovery ranking stack remains separate:

```text
radar_core/ranking/feature_ranking.py
radar_core/ranking/profiles.py
configs/ranking_profiles_v1.yaml
```

It ranks precomputed paper features for product profiles and is not the same
contract as query-conditioned search reranking.

---

## 3. Current ranking semantics

### 3.1 Retrieval normalization

`rank_results(...)` min-max normalizes the selected retrieval score inside the
current candidate list:

```text
retrieval_score =
(raw_score - candidate_min)
/
(candidate_max - candidate_min)
```

When all candidate retrieval scores are equal, every normalized retrieval score
is `1.0`.

### 3.2 Recency

The current implementation derives `min_year` and `max_year` from the current
candidate list.

```text
recency_score =
(clipped_year - candidate_min_year)
/
(candidate_max_year - candidate_min_year)
```

Missing year receives `0.0`.

When all non-null years are equal, a present year receives `1.0`.

### 3.3 Source support

The current implementation derives `max_source_count` from the current
candidate list.

```text
source_support_score =
(clipped_source_count - 1)
/
(candidate_max_source_count - 1)
```

Missing or non-positive source count receives `0.0`.

When the candidate maximum is at most one, a positive source count receives
`1.0`.

### 3.4 Metadata quality

Metadata quality is currently computed from hardcoded field-presence weights in
`radar_core/ranking/scoring.py`.

Current implementation weights:

```text
title = 0.22
abstract = 0.20
authors = 0.14
year = 0.10
doi = 0.10
primary_category = 0.08
categories = 0.08
tags = 0.05
venue = 0.01
journal = 0.01
publisher = 0.01
```

The result is normalized by the sum of the weights and therefore lies in
`[0.0, 1.0]`.

### 3.5 Final score

```text
final_score =
retrieval_weight × retrieval_score
+ recency_weight × recency_score
+ source_support_weight × source_support_score
+ metadata_quality_weight × metadata_quality_score
```

Current sorting uses descending `final_score`.

Python's stable sort preserves input order for exact score ties, but there is no
explicit secondary product tie-breaker in this ranking contract.

---

## 4. Confirmed technical debt to measure, not silently fix

### 4.1 Candidate-pool-relative scores

Recency and source support depend on the composition of the current candidate
pool.

The same paper may receive different component scores when:

```text
candidate_k = 50
candidate_k = 100
candidate_k = 200
```

This behavior is a characterization target in v1. It is not changed in the
contract commit.

### 4.2 Config/code drift

`configs/scoring.yaml` contains:

```text
ranking.recency.min_year
ranking.recency.max_year
ranking.recency.fallback_score
ranking.source_support.max_source_count_for_normalization
ranking.source_support.fallback_score
ranking.metadata_quality.*
```

The current `rank_results(...)` path reads only the top-level ranking weights
through `services/api/search_service.py`.

The detailed recency, source-support, and metadata-quality sections are not
currently used by `radar_core/ranking/scoring.py`.

The hardcoded metadata weights also differ from the YAML metadata weights.

This slice must measure the current implementation first. It must not silently
switch semantics merely to make code and YAML look consistent.

### 4.3 Different DB formula

The DB-backed search path has separate ranking semantics. DB parity is not part
of this slice and no DB formula is changed here.

---

## 5. Evaluation question

Primary question:

```text
Which current ranking signals help query-conditioned retrieval quality,
which signals hurt it, and why?
```

Secondary questions:

1. Does the current ranking improve or reduce top-k relevance?
2. Which component causes the largest harmful movements?
3. Does candidate-pool size change the conclusion?
4. Are observed changes caused by true ranking effects, exact ties, or top-k
   boundary effects?
5. Is a simpler heuristic more robust than the current full formula?
6. Should heuristic ranking remain optional, be simplified, or be rejected in
   favor of a later learned-reranking study?

---

## 6. Fixed retrieval baseline

Ranking evaluation must hold retrieval constant.

```text
backend = file
mode = hybrid
lexical_weight = 0.55
dense_weight = 0.45
candidate_k = [50, 100]
search_top_k = 20
metric_k = [5, 10, 20]
Golden Set = current enabled explicit-label cases
```

This slice does not search over hybrid weights.

Lexical and dense retrieval should be computed once per query at the maximum
candidate depth and then sliced for smaller candidate pools, following the
existing controlled-experiment cache pattern.

---

## 7. Ranking profiles

The first matrix contains one unranked baseline and eight ranking profiles.

### 7.1 `unranked`

```text
apply_ranking = false
```

Preserves the hybrid retrieval order.

### 7.2 `current`

```text
retrieval = 0.60
recency = 0.20
source_support = 0.10
metadata_quality = 0.10
```

Reproduces the current public optional ranking formula.

### 7.3 `retrieval_only`

```text
retrieval = 1.00
recency = 0.00
source_support = 0.00
metadata_quality = 0.00
```

Contract invariant: it must preserve the unranked retrieval order except for
explicitly identified exact-score ties.

### 7.4 Single-component ablations

The removed component receives zero weight. Remaining current weights are
renormalized to sum to one.

```text
without_recency:
retrieval = 0.75
recency = 0.00
source_support = 0.125
metadata_quality = 0.125

without_source_support:
retrieval = 0.666667
recency = 0.222222
source_support = 0.00
metadata_quality = 0.111111

without_metadata_quality:
retrieval = 0.666667
recency = 0.222222
source_support = 0.111111
metadata_quality = 0.00
```

### 7.5 Retrieval plus one signal

The current relative importance of retrieval versus the selected signal is
preserved and renormalized.

```text
retrieval_plus_recency:
retrieval = 0.75
recency = 0.25
source_support = 0.00
metadata_quality = 0.00

retrieval_plus_source_support:
retrieval = 0.857143
recency = 0.00
source_support = 0.142857
metadata_quality = 0.00

retrieval_plus_metadata_quality:
retrieval = 0.857143
recency = 0.00
source_support = 0.00
metadata_quality = 0.142857
```

This is an ablation matrix, not an automatic promotion search.

---

## 8. Candidate-level evidence contract

For each query, candidate depth, and ranking profile, the report must preserve
the evaluated candidate list.

Required fields per candidate:

```text
canonical_id
title
relevant
rank_before
rank_after
rank_delta
retrieval_score_raw
retrieval_score_normalized
recency_score
source_support_score
metadata_quality_score
final_score
year
source_count
```

Definitions:

```text
rank_delta = rank_before - rank_after
positive rank_delta = paper moved upward
negative rank_delta = paper moved downward
```

For the unranked profile:

```text
rank_after = rank_before
rank_delta = 0
final_score = null
```

Relevant labels must come only from the existing Golden Set contract. Weak
pattern matches must not be represented as explicit relevance labels.

---

## 9. Query-level evidence contract

For every query/profile/candidate-depth run, preserve:

```text
query_id
query
candidate_k
profile_name
relevant_ids
result_ids_before
result_ids_after
metrics_before
metrics_after
metric_deltas
moved_candidate_count
relevant_moved_up_count
relevant_moved_down_count
relevant_added_to_top_k
relevant_removed_from_top_k
effect_classification
```

Metrics:

```text
Hit@k
Precision@k
Recall@k
MRR@k
nDCG@k
```

Required k values:

```text
5
10
20
```

---

## 10. Effect classifications

Each ranked comparison against `unranked` must receive one primary
classification.

### `ranking_helped`

At least one configured relevance metric improves and no protected metric
regresses beyond tolerance.

### `ranking_no_effect`

Result order and configured metrics are unchanged.

### `ranking_hurt_order`

A relevant paper moves downward or nDCG/MRR decreases, but the relevant set
inside the evaluated top-k is preserved.

### `ranking_removed_relevant_from_top_k`

At least one explicitly relevant paper present in the unranked top-k is absent
from the ranked top-k.

### `ranking_added_relevant_to_top_k`

At least one explicitly relevant paper absent from the unranked top-k enters the
ranked top-k.

### `tie_or_boundary_effect`

The change is explained by equal or near-equal scores under the configured
numeric tolerance, or by an ordering change exactly at the evaluated boundary,
without a material relevance-set loss.

### `insufficient_labels`

The query does not contain enough explicit relevance information to support a
strong quality interpretation.

A comparison may also store secondary flags, but exactly one primary
classification is required.

---

## 11. Aggregate evidence

The report must include per-profile and per-candidate-depth aggregates:

```text
query_count
error_count
mean metrics at k
metric deltas versus unranked
classification counts
queries helped
queries harmed
queries with relevant top-k loss
queries with relevant top-k gain
mean moved candidates
mean absolute rank delta
candidate-pool sensitivity summary
```

The aggregate report must not hide per-query evidence.

---

## 12. Candidate-pool sensitivity

For every profile, compare the same query at `candidate_k=50` and
`candidate_k=100`.

Required evidence:

```text
shared candidate IDs
component-score changes for shared IDs
final-score changes for shared IDs
order overlap
top-k set overlap
top-k order equality
metric deltas
```

This section characterizes the current candidate-relative normalization.

It does not yet replace it with fixed global bounds.

---

## 13. Determinism and tie semantics

The evaluator must run the scoring stage at least twice over the same cached
candidate inputs.

Required checks:

```text
same result IDs
same order
same component scores within tolerance
same final scores within tolerance
same classifications
```

Current tie semantics:

```text
descending final_score
stable input order for exact ties
```

A future explicit secondary tie-breaker would be a behavior-changing slice and
is not introduced silently here.

---

## 14. Report outputs

Planned evaluation outputs:

```text
artifacts/reports/evaluation/ranking_evaluation_latest.json
artifacts/reports/evaluation/ranking_evaluation_latest.md
artifacts/reports/evaluation/history/ranking_evaluation_<timestamp>.json
artifacts/reports/evaluation/history/ranking_evaluation_<timestamp>.md
```

Planned validation outputs:

```text
artifacts/reports/validation/ranking_evaluation_quality_latest.json
artifacts/reports/validation/ranking_evaluation_quality_latest.md
artifacts/reports/validation/history/ranking_evaluation_quality_<timestamp>.json
artifacts/reports/validation/history/ranking_evaluation_quality_<timestamp>.md
```

Generated reports remain operational evidence and are not automatically added
to Git.

---

## 15. Planned implementation reuse

Do not create a second retrieval implementation.

Reuse or extract shared logic from:

```text
scripts/evaluation/run_search_quality_controlled_experiments.py
```

Existing reusable concepts:

- file-runtime loading;
- Golden Set loading;
- lexical/dense query caching;
- hybrid candidate construction;
- `metrics_at_k`;
- compact query/result serialization;
- report writing conventions.

Ranking components must continue to use:

```text
radar_core/ranking/scoring.py
```

The evaluator may add diagnostic wrappers, but evaluation-only code must not
become a second production ranking formula.

---

## 16. Contract tests in the first commit

The contract commit adds focused tests that characterize the existing
implementation:

1. min-max normalization;
2. constant-score normalization;
3. recency boundaries;
4. source-support boundaries;
5. metadata-quality range and complete/empty cases;
6. `retrieval_only` preserves retrieval order;
7. weighted final-score composition;
8. exact ties preserve input order;
9. candidate-pool-relative recency/source behavior is reproducible.

These tests do not assert that the current candidate-relative behavior is
optimal. They lock the baseline so that later semantic changes are explicit.

---

## 17. Validator requirements

A strict validator must eventually require:

```text
expected schema version
all enabled Golden queries processed
all configured profiles processed
all candidate depths processed
zero runtime errors
finite component and final scores
candidate IDs unique per run
valid rank permutations
retrieval_only order invariant
deterministic repeated scoring
classification for every ranked comparison
aggregate metrics consistent with per-query metrics
candidate-pool sensitivity section present
recommendation/decision section present
```

No quality threshold should force a heuristic profile to win.

A valid outcome is that all heuristic profiles are rejected.

---

## 18. Decision policy

This slice may end with one of four decisions.

### A. Preserve current optional behavior

Use when evidence is mixed and no safer candidate is clearly better.

### B. Promote a simplified heuristic

Use only when the candidate improves aggregate and per-query evidence without
unacceptable relevant-paper loss.

### C. Change normalization in a follow-up slice

Use when candidate-pool-relative scaling is identified as the primary defect.
The follow-up must compare old and new semantics explicitly.

### D. Reject heuristic reranking

Use when non-retrieval signals consistently reduce query relevance. A later
cross-encoder or learned-reranking study may then be proposed as a separate
slice.

No public default changes inside the evaluation run itself.

---

## 19. Non-goals

Not part of Ranking Evaluation and Hardening v1:

```text
new embedding generation
hybrid-weight promotion
Qdrant backend promotion
DB ranking parity
Discovery-profile redesign
cross-encoder implementation
learning-to-rank training
personalization
new relevance labels
corpus expansion
canonical refresh
retrieval rebuild
UI redesign
```

---

## 20. Definition of Done

The slice is complete when:

```text
current ranked and unranked baselines are reproduced
all configured ablations are evaluated
candidate-level score decomposition is available
per-query movements are classified
candidate-pool sensitivity is measured
determinism is checked
strict validator is green
decision is explicit: preserve / simplify / follow-up normalization / reject
runtime defaults remain unchanged unless a separate evidence-backed promotion is approved
documentation and regression entry points are updated
```

The project must leave this slice knowing not merely whether ranking metrics
changed, but why they changed.
