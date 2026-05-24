# Search Quality Experiments Layer

This document describes the **Search Quality Experiments** layer in ML Research Radar.

This layer analyzes retrieval evaluation results and turns them into practical search-quality decisions: which retrieval mode is faster, which mode is stronger by recall, which mode has the best quality/latency tradeoff, and which modes should be carried forward into controlled experiments.

## 1. Position in the project architecture

ML Research Radar is a paper-centric canonical corpus platform for ML/AI research discovery.

The core invariant remains:

```text
canonical_documents.jsonl = paper-level truth
Postgres = rebuildable materialized serving layer
retrieval artifacts = derived retrieval layer
artifact layer = evidence/materialization plane
paper_features/ranking/detail/similar/topic clusters = derived discovery layers
FastAPI = serving/product API
Streamlit = thin client over FastAPI
```

Search Quality Experiments is a derived analysis layer over the Retrieval Evaluation report.

It does not modify:

```text
canonical_documents.jsonl
Postgres
retrieval artifacts
artifact evidence layer
paper features
topic clusters
Discovery API
Streamlit UI
```

It reads an existing Retrieval Eval report and produces an experiment-oriented summary.

Current input report:

```text
artifacts/reports/evaluation/retrieval_eval_latest.json
```

Current output reports:

```text
artifacts/reports/evaluation/search_quality_experiments_latest.json
artifacts/reports/evaluation/search_quality_experiments_latest.md
artifacts/reports/evaluation/history/search_quality_experiments_<timestamp>.json
artifacts/reports/evaluation/history/search_quality_experiments_<timestamp>.md
```

Validation reports:

```text
artifacts/reports/validation/search_quality_experiments_quality_latest.json
artifacts/reports/validation/search_quality_experiments_quality_latest.md
artifacts/reports/validation/history/search_quality_experiments_quality_<timestamp>.json
artifacts/reports/validation/history/search_quality_experiments_quality_<timestamp>.md
```

## 2. Relationship to Retrieval Eval

Retrieval Eval answers:

```text
How good is each retrieval mode on the golden query set?
```

Search Quality Experiments answers:

```text
Given the retrieval eval metrics, what should we do next?
```

Retrieval Eval runs search.

Search Quality Experiments does **not** run search. It analyzes:

```text
retrieval_eval_latest.json
```

This makes Search Quality Experiments fast, reproducible, and safe.

## 3. Related files

Main config:

```text
configs/search_quality_experiments_v1.yaml
```

Main runner:

```text
scripts/evaluation/run_search_quality_experiments.py
```

Validator:

```text
scripts/validation/check_search_quality_experiments.py
```

Optional regression runner integration:

```text
scripts/validation/run_discovery_api_regression.py
```

Input dependency:

```text
artifacts/reports/evaluation/retrieval_eval_latest.json
```

## 4. Configuration

Main config:

```text
configs/search_quality_experiments_v1.yaml
```

Typical structure:

```yaml
schema_version: search_quality_experiments_v1

paths:
  retrieval_eval_report_path: artifacts/reports/evaluation/retrieval_eval_latest.json
  output_dir: artifacts/reports/evaluation
  validation_output_dir: artifacts/reports/validation

analysis:
  primary_k: 10
  modes:
    - lexical
    - dense
    - hybrid
    - hybrid_ranked

  quality_composite_weights:
    recall: 0.40
    ndcg: 0.40
    mrr: 0.20

  comparison_pairs:
    - left: hybrid
      right: lexical
    - left: hybrid
      right: dense
    - left: hybrid_ranked
      right: hybrid
    - left: dense
      right: lexical

thresholds:
  min_modes_count: 4
  min_queries_count: 10
  require_pareto_frontier_non_empty: true
  require_recommendations_non_empty: true
  require_query_diagnostics: true
```

## 5. Quality composite

Search Quality Experiments computes a simple quality composite score:

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

This is not meant to be a universal search-quality truth. It is a decision-support metric.

Interpretation:

```text
Recall@K = whether the mode retrieves enough labeled relevant papers
nDCG@K   = whether relevant papers are ranked well
MRR@K    = whether the first relevant paper appears early
```

## 6. Quality per second

The layer also computes:

```text
quality_per_second_p50 = quality_composite / (p50_latency_ms / 1000)
```

This helps compare quality/latency tradeoffs.

A mode with slightly lower quality but much lower latency can be preferable for serving experiments.

## 7. Pareto frontier

The Pareto frontier contains modes that are not dominated by another mode.

A mode is dominated if another mode has:

```text
quality_composite >= current quality
latency_p50_ms <= current latency
```

and at least one of those is strictly better.

Current interpretation from the latest successful run:

```text
dense and hybrid_ranked are the main Pareto candidates
```

Typical meaning:

```text
dense = best quality/latency serving baseline
hybrid_ranked = best recall-oriented quality baseline
```

## 8. Pairwise summary

The report compares important mode pairs:

```text
hybrid vs lexical
hybrid vs dense
hybrid_ranked vs hybrid
dense vs lexical
```

For each pair it reports deltas for:

```text
Hit@K
Recall@K
MRR@K
nDCG@K
quality_composite
latency_p50_ms
```

This makes it easier to answer questions like:

```text
Does hybrid actually beat lexical?
Does hybrid beat dense enough to justify latency?
Does hybrid_ranked improve recall?
Does hybrid_ranked hurt nDCG?
Does dense recover lexical failures?
```

## 9. Query signal summary

The report aggregates query-level diagnostic signals from Retrieval Eval.

Important signals:

```text
dense_recovers_lexical_failure
dense_recall_gt_lexical
lexical_recall_gt_dense
hybrid_recall_gt_lexical
hybrid_recall_gt_dense
hybrid_recall_lt_dense
hybrid_ranked_improves_recall
hybrid_ranked_lowers_ndcg
```

These signals help choose controlled experiments.

For example:

```text
dense_recovers_lexical_failure
```

means dense retrieval found relevant papers when lexical failed.

```text
lexical_recall_gt_dense
```

means lexical still carries useful exact-term signal and should not be blindly removed.

```text
hybrid_ranked_lowers_ndcg
```

means ranking may improve recall while hurting rank quality on some cases.

## 10. Current findings

Based on the current Retrieval Eval and Search Quality reports:

```text
dense is the fastest mode by p50 latency
dense has the best quality-per-second tradeoff
dense is strongest by nDCG@10
hybrid_ranked is strongest by Recall@10
hybrid improves over lexical overall
lexical still wins on several query cases
lexical has one known failure case
dense recovers at least one lexical failure
hybrid_ranked improves recall on at least one case
hybrid_ranked can lower nDCG on some cases
```

Current important recommendation:

```text
Do not replace lexical blindly.
Do not make hybrid_ranked the default everywhere without more experiments.
Keep dense retrieval as a required component of production-quality search.
Use dense as the first latency-sensitive baseline.
Use hybrid_ranked as the recall-oriented quality baseline.
```

## 11. Running the layer

Recommended sequence:

```bash
set ML_RADAR_SEARCH_BACKEND=file

python -m scripts.evaluation.run_retrieval_eval
python -m scripts.validation.check_retrieval_eval --strict

python -m scripts.evaluation.run_search_quality_experiments
python -m scripts.validation.check_search_quality_experiments --strict
```

Search Quality Experiments assumes that `retrieval_eval_latest.json` exists and is up to date.

If you want a fresh analysis, always run Retrieval Eval first.

## 12. Regression runner integration

Search Quality Experiments can be included in the Discovery API regression runner:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments
```

Recommended fresh full check:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments
```

Fast version without similar rebuild:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments --skip-similar-rebuild
```

Current behavior:

```text
Search Quality Experiments is optional in regression runner.
Search Quality Experiments is not a DoD gate.
```

This is intentional. The layer is useful for decision support, but it should not block the full refresh DoD until the experiment definitions and thresholds are stable.

## 13. Validation

Run:

```bash
python -m scripts.validation.check_search_quality_experiments --strict
```

The validator checks:

```text
report exists
schema_version is correct
input report is retrieval_eval_v1
minimum query count is satisfied
mode table is present
minimum mode count is satisfied
rankings are present
pairwise summary is present
query signal summary is present
Pareto frontier is present
recommendations are present
metrics are finite
```

Expected successful output:

```text
[OK] schema_version=search_quality_experiments_v1
[OK] strict=True
[OK] required_failed_count=0
```

## 14. What this layer is not

Search Quality Experiments is not:

```text
a new retrieval algorithm
a replacement for Retrieval Eval
a replacement for canonical truth
a runtime serving layer
a vector database
a reranker
a DoD gate
```

It is an experiment-analysis and decision-support layer.

## 15. Future controlled experiments

The next logical stage is controlled experiments over retrieval behavior.

Candidate directions:

```text
hybrid weight sweep
ranked vs unranked hybrid
candidate pool size sweep
dense-only serving baseline
field-aware lexical scoring
query normalization experiments
scientific embedding model comparison
reranker experiments
Qdrant/pgvector serving experiments
```

Suggested order:

```text
1. hybrid weights
2. candidate pool size
3. ranked vs unranked hybrid diagnostics
4. stronger embedding model comparison
5. vector serving / Qdrant / pgvector
```

The reason for this order:

```text
first measure
then experiment
then choose serving technology
```

## 16. Git policy

Commit these files when changed:

```text
configs/search_quality_experiments_v1.yaml
scripts/evaluation/run_search_quality_experiments.py
scripts/validation/check_search_quality_experiments.py
scripts/validation/run_discovery_api_regression.py
docs/search_quality_experiments.md
```

Usually do not commit generated reports:

```text
artifacts/reports/evaluation/search_quality_experiments_*
artifacts/reports/validation/search_quality_experiments_quality_*
```

unless selected reports are intentionally versioned.

## 17. Minimal command checklist

Run fresh Retrieval Eval:

```bash
python -m scripts.evaluation.run_retrieval_eval
python -m scripts.validation.check_retrieval_eval --strict
```

Run Search Quality Experiments:

```bash
python -m scripts.evaluation.run_search_quality_experiments
python -m scripts.validation.check_search_quality_experiments --strict
```

Run regression with both optional layers:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments
```

Compile checks:

```bash
python -m py_compile scripts/evaluation/run_search_quality_experiments.py
python -m py_compile scripts/validation/check_search_quality_experiments.py
python -m py_compile scripts/validation/run_discovery_api_regression.py
```
