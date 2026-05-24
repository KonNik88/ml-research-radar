# Search Quality Controlled Experiments

This document describes the **Search Quality Controlled Experiments** layer in ML Research Radar.

This layer runs controlled, evaluation-only experiments over retrieval settings such as hybrid weights, candidate pool size, and ranking mode. It is designed to help decide how to improve search quality without changing production API behavior prematurely.

## 1. Position in the project architecture

ML Research Radar is a paper-centric canonical corpus platform for ML/AI research discovery.

The main architectural invariant remains:

```text
canonical_documents.jsonl = paper-level truth
Postgres = rebuildable materialized serving layer
retrieval artifacts = derived retrieval layer
artifact layer = evidence/materialization plane
paper_features/ranking/detail/similar/topic clusters = derived discovery layers
FastAPI = serving/product API
Streamlit = thin client over FastAPI
```

Controlled Search Quality Experiments is a derived evaluation layer over the retrieval runtime and golden query set.

It does not modify:

```text
canonical_documents.jsonl
Postgres
retrieval artifacts
artifact evidence layer
paper features
topic clusters
Discovery API defaults
Streamlit UI
Definition of Done
```

It is intentionally evaluation-only.

## 2. Why this layer exists

Earlier project layers answer different questions:

```text
run_retrieval_checks.py
→ Does retrieval run and return plausible results?

run_retrieval_eval.py
→ How do lexical / dense / hybrid / hybrid_ranked perform on golden queries?

run_search_quality_experiments.py
→ Given the latest retrieval eval report, which current retrieval mode has the best quality/latency tradeoff?

run_search_quality_controlled_experiments.py
→ What happens if we systematically vary hybrid weights, candidate_k, and rank mode?
```

Controlled experiments are the first layer where we deliberately change retrieval parameters for evaluation purposes.

The goal is to avoid changing production defaults based on intuition.

## 3. Related files

Main config:

```text
configs/search_quality_controlled_experiments_v1.yaml
```

Main runner:

```text
scripts/evaluation/run_search_quality_controlled_experiments.py
```

Validator:

```text
scripts/validation/check_search_quality_controlled_experiments.py
```

Regression runner integration:

```text
scripts/validation/run_discovery_api_regression.py
```

Generated reports:

```text
artifacts/reports/evaluation/search_quality_controlled_experiments_latest.json
artifacts/reports/evaluation/search_quality_controlled_experiments_latest.md
artifacts/reports/evaluation/history/search_quality_controlled_experiments_<timestamp>.json
artifacts/reports/evaluation/history/search_quality_controlled_experiments_<timestamp>.md
```

Validation reports:

```text
artifacts/reports/validation/search_quality_controlled_experiments_quality_latest.json
artifacts/reports/validation/search_quality_controlled_experiments_quality_latest.md
artifacts/reports/validation/history/search_quality_controlled_experiments_quality_<timestamp>.json
artifacts/reports/validation/history/search_quality_controlled_experiments_quality_<timestamp>.md
```

## 4. What is being controlled

The current controlled experiment grid varies:

```text
hybrid lexical/dense weights
candidate_k
rank mode
```

Current weight grid:

```text
0.75 lexical / 0.25 dense
0.60 lexical / 0.40 dense
0.55 lexical / 0.45 dense  baseline
0.40 lexical / 0.60 dense
0.25 lexical / 0.75 dense
```

Current candidate pool grid:

```text
candidate_k = 50
candidate_k = 100
candidate_k = 200
```

Current rank modes:

```text
rank = false
rank = true
```

Baselines included:

```text
lexical
dense
```

Current full grid:

```text
2 baselines + 5 hybrid weights × 3 candidate_k values × 2 rank modes = 32 variants
12 enabled golden queries × 32 variants = 384 runs
```

## 5. Why production defaults are not changed yet

The current production/API default behavior remains unchanged.

This is intentional.

Even though controlled experiments show that some variants outperform the current default on the current golden set, the golden set is still small and partly evolving.

The current principle is:

```text
measure first
experiment second
stabilize evidence third
change production defaults only after enough evidence
```

Do not immediately change `/search` defaults based only on one controlled experiment run.

## 6. Current default and current best controlled variant

The current effective baseline hybrid setting is:

```text
lexical_weight = 0.55
dense_weight = 0.45
candidate_k = 100 for top_k=20
```

The current best controlled quality variant from the latest successful run is:

```text
hybrid lexical=0.40 / dense=0.60
candidate_k=50
rank=false
```

Current observed metrics:

```text
Recall@10 ≈ 0.950
nDCG@10   ≈ 0.957
Composite ≈ 0.963
```

This suggests that the current default `0.55 / 0.45` is probably not optimal for quality on the current golden set.

However, this is still an experimental result, not a production decision.

## 7. Dense-only baseline

Dense-only retrieval remains the strongest latency / quality-per-second baseline.

Current observation:

```text
dense p50 latency ≈ 58 ms
lexical p50 latency ≈ 1550 ms
hybrid estimated p50 latency ≈ 1640 ms
```

Dense-only is much faster because it avoids the current expensive lexical/BM25 path.

Current interpretation:

```text
dense = serving-speed baseline
hybrid 0.40/0.60 k=50 unranked = quality baseline
lexical = still useful for exact terminology-heavy queries
```

Do not remove lexical search blindly, because lexical still wins on several query-level cases.

## 8. Candidate pool findings

The current candidate_k sweep suggests:

```text
candidate_k=50 performs best for the current hybrid quality winner
candidate_k=100 does not improve the best variant
candidate_k=200 does not improve the best variant
```

Current interpretation:

```text
larger candidate pools may introduce extra noise into the top-10 ranking
smaller candidate pools can be better when hybrid score already retrieves enough relevant candidates
```

This is an important result because bigger candidate pools are not automatically better.

## 9. Ranking findings

The current `rank=true` mode should not be made default.

Latest controlled experiments show:

```text
rank=true lowers nDCG in many hybrid settings
rank=true does not consistently improve recall
rank=true can add latency
```

Current recommendation:

```text
Do not make ranked hybrid the default.
Keep ranked hybrid as an experimental / profile-specific option.
Inspect query-level failures before changing ranking weights.
```

## 10. Estimated query latency vs eval wall latency

The v1.1 runner introduced caching, so the report distinguishes two timing concepts.

### 10.1 `estimated_query_latency_ms`

This approximates what a real query would cost if the variant were run independently.

For hybrid variants, it includes:

```text
cached lexical retrieval timing
+ cached dense retrieval timing
+ per-variant hybrid merge timing
+ optional rank timing
```

This is the timing to use for comparing variants.

### 10.2 `eval_wall_latency_ms`

This is the actual wall time of the experiment runner after cached lexical/dense retrieval has already been computed.

This is useful for understanding the speed of the experiment runner itself, but it should not be interpreted as production latency.

## 11. Caching design

v1.0 was correct but inefficient: the same query embedding was recomputed for many variants.

v1.1 added query-level caching.

For each query, the runner now computes once:

```text
lexical top max_candidate_k
dense top max_candidate_k
```

Then it reuses these cached candidates for all:

```text
hybrid weights
candidate_k slices
rank modes
```

Current cache behavior:

```text
12 enabled queries -> 12 dense embedding calls
```

instead of repeatedly embedding the same query for every variant.

This makes the experiment layer scalable enough to support candidate_k sweeps and future larger grids.

## 12. How the runner works

High-level flow:

```text
load config
load golden queries
load file backend runtime
build experiment variants
for each query:
    compute lexical top max_candidate_k
    compute dense top max_candidate_k
    cache both lists
    for each variant:
        slice candidates by candidate_k
        compute hybrid scores if needed
        optionally apply ranking
        compute Hit@K / Recall@K / MRR@K / nDCG@K
summarize variants
build rankings
build Pareto frontier
build rank effects
build weight effects
build query winners
build recommendations
write JSON/Markdown reports
```

The runner uses existing project logic where possible:

```text
golden query loading and metrics from run_retrieval_eval.py
ranking through existing rank_results
file runtime through services.api.runtime
dense search through current search service helper
lexical search through current lexical artifacts
```

It does not change API defaults.

## 13. Quality composite

The controlled report uses the same composite logic as Search Quality Experiments:

```text
quality_composite =
  0.40 * Recall@K
+ 0.40 * nDCG@K
+ 0.20 * MRR@K
```

Current default:

```text
primary_k = 10
```

The composite is not universal truth. It is a decision-support metric.

## 14. Pareto frontier

The Pareto frontier contains variants that are not dominated by another variant.

A variant is dominated if another variant has:

```text
quality_composite >= current quality
estimated_query_latency_p50_ms <= current latency
```

and at least one of these is strictly better.

Current interpretation:

```text
dense is the practical serving-speed baseline
best hybrid is the quality baseline
```

## 15. Running the layer

Recommended direct commands:

```bash
set ML_RADAR_SEARCH_BACKEND=file

python -m scripts.evaluation.run_search_quality_controlled_experiments
python -m scripts.validation.check_search_quality_controlled_experiments --strict
```

Expected successful output:

```text
[OK] schema_version=search_quality_controlled_experiments_v1
[OK] backend_mode=file
[OK] build_id=20260504T164021Z
[OK] corpus_doc_count=60954
[OK] enabled_cases_count=12
[OK] variants_count=32
[OK] runs_count=384
[OK] error_count=0
[OK] max_candidate_k=200
[OK] cache_queries=12
[OK] required_failed_count=0
```

## 16. Regression runner integration

Controlled experiments can be included in Discovery API regression:

```bash
python -m scripts.validation.run_discovery_api_regression --include-controlled-search-quality-experiments
```

Full fresh regression with all current optional evaluation layers:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments --include-controlled-search-quality-experiments
```

Fast version without similar rebuild:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments --include-controlled-search-quality-experiments --skip-similar-rebuild
```

Current behavior:

```text
Controlled Search Quality Experiments is optional in regression runner.
Controlled Search Quality Experiments is not a DoD gate.
```

This is intentional.

## 17. Validation

Validator:

```bash
python -m scripts.validation.check_search_quality_controlled_experiments --strict
```

It checks:

```text
report exists
schema_version is correct
runtime is ready
minimum enabled cases is met
minimum variants count is met
minimum hybrid variants count is met
runs_count matches enabled_cases_count × variants_count
no runtime errors
variants are present
variant_summary is present
rankings are present
weight_effects are present
query_winners are present
baseline lexical is present
baseline dense is present
rank_effects are present
Pareto frontier is present
recommendations are present
metrics are finite
```

Successful strict result:

```text
required_failed_count=0
```

## 18. What this layer is not

Controlled Search Quality Experiments is not:

```text
a production retrieval mode
a public API feature
a UI feature
a replacement for Retrieval Eval
a replacement for Search Quality Experiments
a source of paper truth
a DoD gate
```

It is an internal evaluation and decision-support layer.

## 19. Current project state

Current closed slice:

```text
Controlled Search Quality Experiments v1.0
→ baseline controlled runner

Controlled Search Quality Experiments v1.1
→ caching + candidate_k sweep

Controlled Search Quality Experiments v1.2
→ optional regression runner integration
```

Current strong findings:

```text
best quality variant:
  hybrid lexical=0.40 / dense=0.60, candidate_k=50, rank=false

dense:
  best latency / quality-per-second baseline

candidate_k:
  50 currently beats 100/200 for the best hybrid setting

rank:
  mostly hurts nDCG and should not be made default

production default:
  should not be changed yet without more evidence
```

## 20. Recommended next steps

Recommended next steps after this layer:

```text
1. Expand and strengthen golden query set.
2. Add more canonical_id-labeled queries.
3. Add more graded relevance examples.
4. Re-run controlled experiments.
5. Check whether 0.40/0.60 k=50 remains best.
6. Only then consider a production default proposal.
```

Possible next experiment improvements:

```text
add query group breakdown
add per-query failure analysis
compare candidate_k=25 / 50 / 75 / 100
test dense-heavy weights around 0.35/0.65 and 0.45/0.55
test score normalization alternatives
test stronger scientific embedding models
test reranker experiments
test Qdrant/pgvector serving after quality decisions are clearer
```

## 21. Git policy

Commit these files when changed:

```text
configs/search_quality_controlled_experiments_v1.yaml
scripts/evaluation/run_search_quality_controlled_experiments.py
scripts/validation/check_search_quality_controlled_experiments.py
scripts/validation/run_discovery_api_regression.py
docs/search_quality_controlled_experiments.md
```

Usually do not commit generated reports:

```text
artifacts/reports/evaluation/search_quality_controlled_experiments_*
artifacts/reports/validation/search_quality_controlled_experiments_quality_*
```

unless selected reports are intentionally versioned.

## 22. Minimal command checklist

Compile:

```bash
python -m py_compile scripts/evaluation/run_search_quality_controlled_experiments.py
python -m py_compile scripts/validation/check_search_quality_controlled_experiments.py
python -m py_compile scripts/validation/run_discovery_api_regression.py
```

Run controlled experiments:

```bash
python -m scripts.evaluation.run_search_quality_controlled_experiments
python -m scripts.validation.check_search_quality_controlled_experiments --strict
```

Run full regression with all optional eval layers:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments --include-controlled-search-quality-experiments
```
