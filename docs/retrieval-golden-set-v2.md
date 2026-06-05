# Retrieval Golden Set v2

## Status

Completed.

This document records the second expansion campaign for the ML Research Radar retrieval golden set. The slice expands and strengthens retrieval evaluation coverage without changing search behavior, retrieval defaults, the canonical corpus, or the Qdrant serving boundary.

## Baseline before the campaign

Before this campaign:

- retrieval build: `20260504T164021Z`;
- corpus size: `60,954`;
- enabled golden queries: `22`;
- explicit canonical-labeled queries: `15`;
- weak-pattern-only queries: `7`;
- evaluated modes: `lexical`, `dense`, `hybrid`, and the evaluation label `hybrid_ranked`;
- public API equivalent of `hybrid_ranked`: `mode=hybrid&rank=true`;
- Qdrant/file-dense top-20 parity was exact on the original 22-query set.

The original parity result was an engineering signal only and was not treated as sufficient evidence for public Qdrant promotion.

## Final result

After the campaign:

- enabled golden queries: `34`;
- explicit canonical-labeled queries: `34`;
- weak-pattern-only queries: `0`;
- upgraded existing weak-pattern cases: `7`;
- new query intents added: `12`;
- duplicate `query_id` values: `0`;
- every enabled row uses `strict_canonical_relevance: true`;
- every accepted `canonical_id` has a matching graded-relevance entry;
- grades used: `2` and `3`.

The campaign therefore changed the evaluation set from:

```text
22 enabled
15 explicit
7 weak-pattern-only
```

to:

```text
34 enabled
34 explicit
0 weak-pattern-only
```

## Goals

The campaign completed the following goals:

1. Replaced all seven weak-pattern-only cases with human-reviewed canonical relevance labels.
2. Added twelve new query intents spanning underrepresented ML areas.
3. Increased the number and diversity of explicit relevance judgments before any `DenseSearchBackend` promotion work.
4. Preserved file dense as the reference backend.
5. Re-ran retrieval, search-quality, controlled-experiment, and Qdrant parity gates on the expanded set.

## Non-goals

This slice did not:

- change `/search` behavior;
- add a public `vector_backend` parameter;
- add `mode=dense_qdrant`;
- switch file dense to Qdrant;
- change canonical truth;
- rebuild retrieval artifacts;
- rebuild the Qdrant collection;
- tune production scoring weights;
- alter `/health` readiness semantics.

## Files

### Campaign config

`configs/golden_labeling_expansion_v2.yaml`

The campaign config uses `schema_version: golden_labeling_v1` because the exporter and validator schema did not change. The campaign-specific file name preserves the completed v1 campaign config.

### Golden evaluation truth

`data/eval/retrieval/golden_queries.jsonl`

This is the only final golden-truth file. Temporary intermediate JSONL files used during manual review are not part of the PR.

### Human-review exporter

`scripts/evaluation/export_golden_labeling_review.py`

This helper hydrates candidate rows from the canonical corpus and exports review-ready JSON, Markdown, and CSV containing:

- abstracts;
- authors;
- categories and concepts;
- DOI and arXiv identifiers;
- venue information;
- landing-page and PDF links;
- retrieval rank summaries;
- empty review-grade and review-note fields.

The helper prevents relevance labeling from being based only on titles and retrieval ranks.

## Campaign composition

The campaign contained nineteen query intents:

- seven upgrades of existing weak-pattern-only rows;
- twelve new query intents.

### Existing weak cases upgraded

- `vision_language_models_001`
- `reinforcement_learning_from_human_feedback_001`
- `efficient_transformers_001`
- `large_language_model_agents_001`
- `self_supervised_learning_001`
- `neural_ordinary_differential_equations_001`
- `explainable_ai_shap_001`

### New query intents added

- `parameter_efficient_fine_tuning_001`
- `long_context_language_models_001`
- `mixture_of_experts_language_models_001`
- `llm_quantization_001`
- `code_generation_language_models_001`
- `graph_transformers_001`
- `time_series_transformers_001`
- `neural_recommender_systems_001`
- `physics_informed_neural_networks_001`
- `language_model_alignment_001`
- `federated_learning_privacy_001`
- `causal_machine_learning_001`

## Relevance policy

The campaign used strict human-reviewed canonical relevance.

### Grade 3

The paper directly addresses the query intent and the topic is central to its contribution.

### Grade 2

The paper is clearly relevant and useful for the query, but the topic is narrower, applied, or not the sole central contribution.

### Excluded candidates

Marginal, keyword-overlapping, task-mismatched, or weakly related candidates were excluded rather than padded into the positive set.

### Canonical relevance contract

For every accepted paper:

- its `canonical_id` appears in `expected.canonical_ids`;
- one matching item appears in `graded_relevance`;
- `expected.strict_canonical_relevance` is `true`;
- the graded-relevance item contains a concise rationale.

## Completed workflow

### Candidate export

```cmd
python -m scripts.evaluation.export_golden_labeling_candidates --config-path configs/golden_labeling_expansion_v2.yaml
```

Result:

- enabled queries: `19`;
- candidate rows: `570`;
- unique candidate canonical IDs: `563`;
- mode errors: `0`.

### Candidate-export validation

```cmd
python -m scripts.validation.check_golden_labeling_candidates --config-path configs/golden_labeling_expansion_v2.yaml --strict
```

Result:

- `required_failed_count=0`.

### Review export

```cmd
python -m scripts.evaluation.export_golden_labeling_review --strict
```

Result:

- query count: `19`;
- candidate rows: `570`;
- canonical rows found: `563`;
- missing canonical rows: `0`.

### Golden-query validation

```cmd
python -m scripts.validation.check_golden_queries --strict
```

Result:

- rows: `34`;
- enabled cases: `34`;
- explicit canonical-labeled enabled cases: `34`;
- weak-pattern enabled cases: `0`;
- `required_failed_count=0`.

## Evaluation results

### Retrieval evaluation

```cmd
python -m scripts.evaluation.run_retrieval_eval
python -m scripts.validation.check_retrieval_eval --strict
```

Result:

- enabled cases: `34`;
- retrieval build: `20260504T164021Z`;
- corpus size: `60,954`;
- strict validation passed;
- `required_failed_count=0`.

### Search-quality experiments

```cmd
python -m scripts.evaluation.run_search_quality_experiments
python -m scripts.validation.check_search_quality_experiments --strict
```

Result:

- modes evaluated: `4`;
- Pareto-frontier modes: `2`;
- group-level mode recommendations: `27`;
- recommendations: `9`;
- strict validation passed;
- `required_failed_count=0`.

### Controlled search-quality experiments

```cmd
python -m scripts.evaluation.run_search_quality_controlled_experiments
python -m scripts.validation.check_search_quality_controlled_experiments --strict
```

Result:

- enabled cases: `34`;
- variants: `32`;
- total query-variant runs: `1,088`;
- errors: `0`;
- maximum `candidate_k`: `200`;
- cached queries: `34`;
- Pareto-frontier variants: `6`;
- recommendations: `6`;
- strict validation passed;
- `required_failed_count=0`.

## Qdrant/file-dense parity

Commands:

```cmd
python -m scripts.evaluation.compare_qdrant_file_dense
python -m scripts.validation.check_qdrant_file_dense_comparison --strict
```

Result:

- enabled queries: `34`;
- compared queries: `34`;
- errors: `0`;
- mean overlap ratio at top 20: `0.998529`;
- minimum overlap ratio at top 20: `0.95`;
- strict validation passed;
- `required_failed_count=0`.

### Observed mismatch

Exactly one expanded query was not an exact top-20 match:

```text
query_id: mixture_of_experts_language_models_001
query: mixture of experts language models
overlap: 19 / 20
overlap ratio: 0.95
```

Qdrant-only canonical ID:

```text
0608d3a69d12ff457ce5cade497afd42
```

File-dense-only canonical ID:

```text
989404213cfbfc6e1d2c5386acf475fa
```

This does not block the Golden Set v2 PR because:

- the comparison completed with zero errors;
- the strict validator passed;
- the configured minimum overlap threshold was met;
- the mismatch affects one result at the top-20 boundary for one query;
- file dense remains the reference backend;
- no public Qdrant promotion is part of this slice.

The mismatch is a concrete input for the next parity-hardening checkpoint. It should be inspected for score proximity, numeric precision, deterministic tie handling, and top-k boundary behavior before internal backend abstraction work is promoted further.

## Acceptance criteria

All campaign acceptance criteria were met:

- at least 32 enabled queries: passed (`34`);
- at least 30 explicit canonical-labeled enabled queries: passed (`34`);
- no more than 4 weak-pattern-only enabled queries: passed (`0`);
- no duplicate `query_id`: passed;
- every explicit row has `strict_canonical_relevance: true`: passed;
- every accepted canonical ID has matching graded relevance: passed;
- every new or upgraded query has at least 3 defensible positive papers: passed;
- `check_golden_queries --strict`: passed;
- retrieval evaluation validator: passed;
- search-quality experiments validator: passed;
- controlled experiments validator: passed;
- controlled experiments completed with zero errors: passed;
- Qdrant/file-dense comparison completed with zero errors: passed;
- query-level mismatch was inspected and documented: passed.

## Commit boundaries

The PR should contain only intentional source files:

- `configs/golden_labeling_expansion_v2.yaml`;
- `data/eval/retrieval/golden_queries.jsonl`;
- `docs/retrieval-golden-set-v2.md`;
- `scripts/evaluation/export_golden_labeling_review.py`.

Generated files under `artifacts/reports/` remain ignored and are not part of the PR.

Temporary intermediate files are not part of the PR:

- `data/eval/retrieval/golden_queries_after_weak_upgrades_v2.jsonl`;
- `data/eval/retrieval/golden_queries_expansion_v2_final.jsonl`;
- `data/eval/retrieval/golden_weak_upgrades_review_v2.md`;
- any temporary summary or review files copied into tracked directories.

## Next step after merge

The next planned slice is a narrow Qdrant/file-dense parity-hardening checkpoint focused on:

- score-difference visibility;
- top-k boundary behavior;
- deterministic ordering under near-equal scores;
- payload and `dense_index` consistency;
- collection/build compatibility;
- repeated-run determinism.

Only after deciding whether parity hardening requires code changes should the project start the internal `DenseSearchBackend` abstraction.

Public search behavior remains unchanged.
