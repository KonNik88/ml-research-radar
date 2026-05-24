# Search Quality Findings After Golden Set Expansion

This document summarizes the search-quality findings after expanding the retrieval golden query set from 12 to 18 enabled queries.

The purpose of this note is to capture the current evidence before making any production search-default changes.

## 1. Context

ML Research Radar now has a layered retrieval evaluation stack:

```text
Retrieval Eval
→ metric-based evaluation over golden queries

Search Quality Experiments
→ mode-level quality/latency analysis over retrieval_eval_latest.json

Controlled Search Quality Experiments
→ evaluation-only sweeps over hybrid weights, candidate_k, and rank mode

Golden Labeling Helper
→ candidate export workflow for expanding golden_queries.jsonl
```

The golden set was expanded with the first wave of manually selected queries:

```text
rag_evaluation_001
graph_rag_001
diffusion_transformers_001
tabular_deep_learning_001
self_supervised_vision_001
audio_language_models_001
```

The total enabled query count changed from:

```text
12 → 18
```

The updated evaluation stack passed:

```text
run_retrieval_eval
check_retrieval_eval --strict

run_search_quality_experiments
check_search_quality_experiments --strict

run_search_quality_controlled_experiments
check_search_quality_controlled_experiments --strict
```

Observed green-state:

```text
golden_queries.jsonl rows = 18
duplicates = []
retrieval_eval enabled_cases_count = 18
controlled variants_count = 32
controlled runs_count = 576
controlled error_count = 0
controlled cache_queries = 18
strict validators required_failed_count = 0
```

## 2. Why the expansion matters

Before the expansion, the benchmark was useful but small.

After adding six new queries, the benchmark became more diverse:

```text
RAG evaluation
GraphRAG / knowledge-graph RAG
Diffusion transformers
Tabular deep learning
Self-supervised visual representation learning
Audio / speech language models
```

This makes the benchmark less likely to overfit to the original 12 queries.

The expanded set is still not final, but it is a better evidence base than the earlier 12-query set.

## 3. Main controlled experiment result

After expansion to 18 enabled queries, the best controlled quality variant is:

```text
hybrid__lexical_040_dense_060__k200__unranked
```

Settings:

```text
lexical_weight = 0.40
dense_weight   = 0.60
candidate_k    = 200
rank           = false
```

Observed metrics:

```text
Recall@10  = 0.832
MRR@10     = 1.000
nDCG@10    = 0.878
Composite  = 0.884
```

The nearest practical competitor remains very close:

```text
hybrid__lexical_040_dense_060__k50__unranked
```

Observed metrics:

```text
Recall@10  = 0.826
MRR@10     = 1.000
nDCG@10    = 0.877
Composite  = 0.881
```

Interpretation:

```text
The best quality region remains lexical=0.40 / dense=0.60.
candidate_k=200 is now slightly best by quality.
candidate_k=50 remains very close and may still be practical.
rank=false remains preferable.
```

## 4. Comparison with the earlier 12-query result

Before expansion, the best controlled quality variant was:

```text
hybrid lexical=0.40 / dense=0.60
candidate_k=50
rank=false
```

After expansion, the best controlled quality variant became:

```text
hybrid lexical=0.40 / dense=0.60
candidate_k=200
rank=false
```

Important: this is not a contradiction.

The stable part is:

```text
lexical=0.40 / dense=0.60
rank=false
```

The candidate pool preference moved from `50` to `200`, but `k=50` remains very close.

This suggests:

```text
The dense-heavy hybrid weighting is robust.
The optimal candidate_k is less settled.
```

## 5. What happened to absolute metrics

The absolute best composite score decreased after expansion.

Earlier, on 12 queries:

```text
best composite ≈ 0.963
```

After expansion, on 18 queries:

```text
best composite ≈ 0.884
```

This is expected.

The new queries are more diverse and less trivial. The decrease should not be interpreted as a regression in retrieval runtime. It indicates that the benchmark became harder.

## 6. Dense-only baseline

Dense-only remains the strongest latency and quality-per-second baseline.

Observed after expansion:

```text
baseline__dense__k200__unranked
Recall@10  = 0.759
MRR@10     = 0.972
nDCG@10    = 0.821
Composite  = 0.826
p50 latency ≈ 59.545 ms
quality/sec ≈ 13.875959
```

For comparison:

```text
baseline__lexical__k200__unranked
Recall@10  = 0.743
MRR@10     = 0.944
nDCG@10    = 0.779
Composite  = 0.798
p50 latency ≈ 1652.590 ms
```

Hybrid variants have stronger quality but much higher estimated query latency:

```text
hybrid estimated p50 latency ≈ 1745–1751 ms
```

Interpretation:

```text
dense-only = speed / quality-per-second baseline
hybrid 0.40/0.60 = quality baseline
lexical-only = still useful on some exact-term queries, but not the best global mode
```

## 7. Ranking findings

The controlled sweep confirms that `rank=true` should not become the default.

Observed rank effects:

```text
ranking lowered nDCG in 15 hybrid settings
ranking improved recall or composite quality in only 1 hybrid setting
```

Interpretation:

```text
ranked hybrid remains experimental
ranked hybrid may be useful for specific profiles or query families
ranked hybrid should not become the global default
```

## 8. Candidate_k findings

After expansion, the best global quality variant uses:

```text
candidate_k = 200
```

But:

```text
candidate_k = 50
```

is nearly tied and has slightly lower estimated/eval wall timing.

Current evidence:

```text
k=200 best by composite
k=50 very close
k=100 weaker than both in the current sweep
```

Interpretation:

```text
candidate_k is not fully settled
candidate_k should remain part of future controlled experiments
do not hard-change candidate_k defaults yet
```

Suggested next focused sweep:

```text
candidate_k = 25
candidate_k = 50
candidate_k = 75
candidate_k = 100
candidate_k = 150
candidate_k = 200
```

but only after more labeled queries are added.

## 9. Query-level observations

The best variant differs by query.

Examples from the expanded run:

```text
diffusion_models_001
→ dense baseline wins

efficient_transformers_001
→ lexical baseline wins

explainable_ai_shap_001
→ lexical baseline wins

protein_language_models_001
→ dense baseline wins

rag_evaluation_001
→ hybrid 0.40/0.60 k=200 unranked wins

graph_rag_001
→ lexical-heavy hybrid wins

tabular_deep_learning_001
→ dense-heavy ranked hybrid wins

audio_language_models_001
→ 0.60/0.40 k=200 unranked wins
```

Interpretation:

```text
There is no single universally best retrieval behavior for every query family.
A future query/profile-aware strategy may eventually be useful.
For now, global defaults should remain conservative.
```

## 10. Current decision

Do not change production `/search` defaults yet.

Reason:

```text
The new evidence is stronger, but the golden set is still only 18 queries.
The best weighting region is stable, but candidate_k is not fully settled.
Ranked hybrid clearly should not become default.
Dense-only is still much better for latency.
```

Current recommended project stance:

```text
Keep production defaults unchanged for now.
Keep dense-only as latency baseline.
Keep hybrid 0.40/0.60 rank=false as the leading quality candidate.
Continue expanding and strengthening the golden set.
```

## 11. When to consider changing defaults

A production default proposal becomes reasonable after:

```text
1. Golden set reaches roughly 25–30 enabled queries.
2. Most new queries have explicit canonical_id labels.
3. Most important queries include graded_relevance.
4. The 0.40/0.60 rank=false region remains best or near-best.
5. Candidate_k choice is validated on a focused sweep.
6. Per-group regressions are inspected.
```

A future proposal document could compare:

```text
current default:
  lexical_weight = 0.55
  dense_weight   = 0.45
  candidate_k    = current effective pool
  rank           = false

candidate default:
  lexical_weight = 0.40
  dense_weight   = 0.60
  candidate_k    = 50 or 200
  rank           = false
```

## 12. Recommended next steps

Recommended next project steps:

```text
1. Commit the expanded golden_queries.jsonl.
2. Keep temporary helper files out of git.
3. Add a second wave of golden queries only after manual review.
4. Improve existing weak/empty labeled queries.
5. Add group-level summaries to controlled experiments.
6. Add per-query regression/failure notes.
7. Re-run the full evaluation stack.
```

Second-wave candidates that need more manual filtering:

```text
scientific_reranking_001
multimodal_retrieval_001
protein_structure_prediction_001
llm_agents_tools_001
```

Potential near-term enhancement to controlled experiments:

```text
group-level metrics
per-query win/loss analysis
candidate_k focused sweep
score-normalization comparison
```

## 13. Git policy

Commit:

```text
data/eval/retrieval/golden_queries.jsonl
docs/search_quality_findings_after_golden_expansion.md
```

Do not commit temporary helper files:

```text
data/eval/retrieval/golden_queries_additions_first_wave.jsonl
data/eval/retrieval/golden_queries_suggested_merged.jsonl
data/eval/retrieval/golden_queries.before_first_wave.bak
data/eval/retrieval/golden_queries_first_wave_package.zip
```

Do not commit generated reports unless intentionally versioning selected reports:

```text
artifacts/reports/evaluation/*
artifacts/reports/validation/*
```

## 14. Minimal validation checklist

After editing `golden_queries.jsonl`:

```bash
python -c "import json; from pathlib import Path; p=Path('data/eval/retrieval/golden_queries.jsonl'); rows=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]; ids=[r['query_id'] for r in rows]; dup=sorted({x for x in ids if ids.count(x)>1}); print('rows=', len(rows)); print('duplicates=', dup); assert not dup"
```

Then:

```bash
python -m scripts.evaluation.run_retrieval_eval
python -m scripts.validation.check_retrieval_eval --strict

python -m scripts.evaluation.run_search_quality_experiments
python -m scripts.validation.check_search_quality_experiments --strict

python -m scripts.evaluation.run_search_quality_controlled_experiments
python -m scripts.validation.check_search_quality_controlled_experiments --strict
```

Expected state after the first expansion:

```text
enabled_cases_count = 18
controlled runs_count = 576
controlled error_count = 0
required_failed_count = 0
```
