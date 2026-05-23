# Retrieval Evaluation Layer

This document describes the retrieval evaluation layer in **ML Research Radar**.

The goal of this layer is to measure retrieval quality over the canonical paper corpus instead of judging search results only by manual inspection.

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

Retrieval evaluation is a derived validation/evaluation layer over the retrieval artifacts and canonical corpus. It does not modify canonical data, Postgres, artifacts, paper features, topic clusters, API, or UI.

Current retrieval build used by this layer:

```text
build_id = 20260504T164021Z
corpus_doc_count = 60954
embedding_model = sentence-transformers/all-MiniLM-L6-v2
backend_mode = file
```

## 2. Related scripts

There are three related but different scripts.

### 2.1 `scripts/validation/run_retrieval_checks.py`

This is the older smoke/inspection script.

It runs a curated query set through retrieval modes and writes human-readable top results.

Use it to quickly check that retrieval runtime works:

```bash
python -m scripts.validation.run_retrieval_checks --top-k 5 --backend-mode file
```

It answers:

```text
Does retrieval run?
Does the manifest load?
Do lexical/dense/hybrid modes return results?
What do the top results look like?
```

It does not provide a strict quality benchmark.

### 2.2 `scripts/evaluation/run_retrieval_eval.py`

This is the metric-based retrieval evaluation runner.

It runs golden queries from:

```text
data/eval/retrieval/golden_queries.jsonl
```

using settings from:

```text
configs/retrieval_eval_v1.yaml
```

It evaluates multiple modes:

```text
lexical
dense
hybrid
hybrid_ranked
```

and computes:

```text
Hit@K
Recall@K
Precision@K
MRR@K
nDCG@K
empty result rate
latency p50/p95
mode comparison diagnostics
query-level diagnostics
```

Run it with:

```bash
python -m scripts.evaluation.run_retrieval_eval
```

Outputs:

```text
artifacts/reports/evaluation/retrieval_eval_latest.json
artifacts/reports/evaluation/retrieval_eval_latest.md
artifacts/reports/evaluation/history/retrieval_eval_<timestamp>.json
artifacts/reports/evaluation/history/retrieval_eval_<timestamp>.md
```

### 2.3 `scripts/validation/check_retrieval_eval.py`

This is the strict validator for the latest retrieval evaluation report.

Run it with:

```bash
python -m scripts.validation.check_retrieval_eval --strict
```

It validates:

```text
report exists
schema_version is correct
enabled cases were executed
all expected modes are present
all cases have all expected modes
no runtime errors occurred
metrics are finite
comparison diagnostics are present
empty result rate is within threshold
hybrid quality thresholds are met
```

Outputs:

```text
artifacts/reports/validation/retrieval_eval_quality_latest.json
artifacts/reports/validation/retrieval_eval_quality_latest.md
artifacts/reports/validation/history/retrieval_eval_quality_<timestamp>.json
artifacts/reports/validation/history/retrieval_eval_quality_<timestamp>.md
```

## 3. Configuration

Main config:

```text
configs/retrieval_eval_v1.yaml
```

Typical structure:

```yaml
schema_version: retrieval_eval_v1

defaults:
  backend_mode: file
  modes:
    - lexical
    - dense
    - hybrid
    - hybrid_ranked
  top_k_values:
    - 5
    - 10
    - 20
  primary_k: 10

paths:
  golden_queries_path: data/eval/retrieval/golden_queries.jsonl
  output_dir: artifacts/reports/evaluation

thresholds:
  min_enabled_cases: 10
  require_all_modes_present: true
  require_metrics_finite: true

  max_empty_result_rate: 0.05
  min_hybrid_hit_at_10: 0.60
  min_hybrid_mrr_at_10: 0.25
  min_hybrid_recall_at_10: 0.40
```

The thresholds are intentionally soft for the current baseline. They are strict enough to catch broken retrieval evaluation runs, but not strict enough to pretend that the current golden set is final.

## 4. Golden queries

Golden queries live in:

```text
data/eval/retrieval/golden_queries.jsonl
```

Each line is one JSON object.

Example:

```json
{
  "query_id": "protein_language_models_001",
  "enabled": true,
  "group": "bio_ml",
  "query": "protein language models",
  "intent": "Find papers about protein language models, ESM-like models, or sequence representation learning for proteins.",
  "expected": {
    "canonical_ids": [
      "5009ba530555744107c75b246dd1c890",
      "de60bb2379efe45c0162964334120830"
    ],
    "strict_canonical_relevance": true,
    "title_substrings": ["protein"],
    "must_have_any_terms": ["protein", "esm", "sequence", "language model"]
  },
  "graded_relevance": [
    {
      "canonical_id": "5009ba530555744107c75b246dd1c890",
      "grade": 3,
      "note": "Direct protein language model paper with structural knowledge."
    }
  ]
}
```

### 4.1 Weak relevance

If a case does not define explicit canonical IDs, the evaluator can use weak matching:

```text
title_substrings
title_any_substrings
must_have_any_terms
```

Weak relevance is useful for initial smoke-like cases, but it is not a strong retrieval benchmark.

### 4.2 Strict canonical relevance

For labeled cases, use:

```json
"strict_canonical_relevance": true
```

When this is enabled and `canonical_ids` / `graded_relevance` are present, only explicitly labeled canonical IDs are counted as relevant.

This prevents weak title/term matching from making metrics too optimistic.

### 4.3 Graded relevance

`graded_relevance` supports nDCG-style evaluation.

Suggested grade convention:

```text
3 = highly relevant / direct match
2 = relevant but broader or secondary
1 = weakly relevant
0 = not relevant
```

## 5. Running the layer

Recommended sequence:

```bash
set ML_RADAR_SEARCH_BACKEND=file

python -m scripts.validation.run_retrieval_checks --top-k 5 --backend-mode file
python -m scripts.evaluation.run_retrieval_eval
python -m scripts.validation.check_retrieval_eval --strict
```

The evaluation runner does not require a live FastAPI server. It loads the file backend directly through the existing API runtime/search service.

## 6. Regression runner integration

Retrieval Eval can be included in the Discovery API regression runner:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval
```

This runs the normal Discovery API regression checks plus:

```text
run_retrieval_eval
check_retrieval_eval
```

Current behavior:

```text
Retrieval Eval is optional in regression runner.
Retrieval Eval is not yet a DoD gate.
```

This is intentional. The evaluation layer is still stabilizing and the golden set will continue to improve.

## 7. Reading the report

Main report:

```text
artifacts/reports/evaluation/retrieval_eval_latest.md
```

### 7.1 Mode summary

The mode summary compares aggregate quality and latency:

```text
Hit@K
Recall@K
MRR@K
nDCG@K
empty result rate
p50 latency
p95 latency
```

Example interpretation:

```text
dense can be much faster than lexical/hybrid
hybrid can recover some lexical failures
hybrid_ranked can improve recall in some cases
lexical can still be best on exact terminology-heavy queries
```

### 7.2 Mode comparison diagnostics

This section is designed to avoid manual table inspection.

It includes:

```text
overall mode ranking
pairwise deltas
diagnostic signals
failed modes
query-level mode comparison
```

Important signals include:

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

### 7.3 Failed modes

A failed mode means that a mode returned no relevant result for a query at primary K.

For example:

```text
lexical failed on diffusion_models_001
dense recovered this lexical failure
```

This is useful for deciding whether the retrieval stack should be improved with stronger dense search, hybrid tuning, field weighting, reranking, or vector serving.

## 8. Current state

The current Retrieval Eval layer has reached:

```text
Retrieval Eval v1   -> baseline metric evaluation layer
Retrieval Eval v1.1 -> strict canonical relevance + stronger golden queries
Retrieval Eval v1.2 -> optional regression runner integration
Retrieval Eval v1.3 -> mode comparison diagnostics
```

Current report shows that the modes now differ meaningfully:

```text
dense is fastest and strongest by nDCG@10
hybrid_ranked is strongest by recall@10
lexical has one known failure in the current golden set
hybrid improves over lexical overall
dense and hybrid are tied on some aggregate metrics
```

## 9. What this layer is not

Retrieval Eval is not:

```text
a new source of paper truth
a replacement for canonical_documents.jsonl
a Postgres materialization
a UI layer
a RAG layer
a production monitoring layer
```

It is a quality measurement layer for retrieval.

## 10. Future improvements

Planned next improvements:

```text
add more canonical_id-labeled queries
add more graded relevance
increase coverage across query groups
add search quality experiments
compare hybrid weights
compare ranked vs unranked hybrid
evaluate candidate pool sizes
evaluate stronger scientific embedding models
consider reranker experiments
eventually add a DoD flag after the eval set stabilizes
```

Possible future command after stabilization:

```bash
python -m scripts.update.check_refresh_definition_of_done --require-retrieval-eval
```

This DoD gate should not be added until the golden set and thresholds are stable.

## 11. Git policy

Commit these files when changed:

```text
configs/retrieval_eval_v1.yaml
data/eval/retrieval/golden_queries.jsonl
scripts/evaluation/run_retrieval_eval.py
scripts/validation/check_retrieval_eval.py
scripts/validation/run_discovery_api_regression.py
docs/retrieval_eval.md
```

Usually do not commit generated reports:

```text
artifacts/reports/evaluation/*
artifacts/reports/validation/retrieval_eval_quality_*
artifacts/reports/retrieval/*
```

unless selected reports are intentionally versioned.

## 12. Minimal command checklist

Fast smoke:

```bash
python -m scripts.validation.run_retrieval_checks --top-k 5 --backend-mode file
```

Eval:

```bash
python -m scripts.evaluation.run_retrieval_eval
python -m scripts.validation.check_retrieval_eval --strict
```

Regression with eval:

```bash
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval
```

Compile checks:

```bash
python -m py_compile scripts/evaluation/run_retrieval_eval.py
python -m py_compile scripts/validation/check_retrieval_eval.py
python -m py_compile scripts/validation/run_discovery_api_regression.py
```
