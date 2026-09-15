# Scientific Entity Semantic Typer Candidate v0.3

## Status

Development infrastructure for one bounded v0.3 hypothesis.

Candidate ID:

```text
scientific-entity-semantic-typer-candidate-v0.3-h1
```

Hypothesis:

```text
target_focused_second_stage_semantic_typing_over_frozen_spans
```

The parent Scientific Entity v0.2c independent acceptance decision remains rejected.
This v0.3 work is development-only and does not alter that decision.

## Why this slice exists

The completed typing root-cause review classified all 166 fresh-v0.2c type
mismatches. The dominant actionable signal is semantic typing on already-correct
spans rather than span discovery itself:

- 131 / 166 type mismatches use the same reference and prediction span;
- same-span reviewed failures are dominated by clear semantic mistyping and
  taxonomy-boundary ambiguity;
- the method predicted-type sink remains the principal systematic failure mode;
- annotation/reference issues are a small minority and must not be treated as
  ordinary supervised gold in the primary development metric. Six such issues are
  same-span and are excluded from the primary v0.3-H1 metric; the seventh reviewed
  reference issue is different-span and therefore outside this candidate package.

The first v0.3 hypothesis therefore freezes the upstream span and asks a separate
semantic stage to retype it.

## Candidate mechanism

The candidate reuses the exact pinned GLiNER small-v2.5 runtime already present in
v0.2c. It does **not** introduce a new model download in this infrastructure slice.

For each frozen source span, the future bounded inference step will build a target-
focused synthetic input:

```text
Target entity: <exact surface>
Context: <left context>[TARGET]<right context>
```

The six canonical types are supplied as explicit discriminative semantic prompts.
Inference is multi-label with a raw threshold of 0.0 so that the second stage can
observe exact-target type scores rather than reuse the upstream single-label choice.
Only predictions with offsets exactly equal to the synthetic target surface are
eligible for type selection. The highest exact-target score wins, with canonical
entity-type order as the deterministic tie breaker.

The upstream v0.2c predicted type and confidence are deliberately **not** supplied
as model features. Root-cause labels are also never model features.

If the target surface is not scorable at all, the candidate preserves the upstream
baseline type and records an explicit fallback. This is an operational fail-closed
fallback, not a semantic input feature. Coverage is therefore a mandatory candidate
metric.

## Development evidence

The prepare phase consumes only the already-consumed fresh-v0.2c evaluation:

```text
scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z
```

It does not rematch references and predictions. Instead it reuses the immutable
base evaluator outputs:

- `matches.jsonl`: exact same-span + same-type baseline-correct cases;
- `errors.jsonl`: same-span `type_mismatch` baseline-wrong cases.

This creates a development set containing both correction targets and regression
guardrails. Evaluating only the known 166 errors would be invalid because a typer
could fix errors while breaking already-correct predictions.

The completed root-cause review is joined only for offline diagnostics and for
excluding reviewed `annotation_reference_issue` cases from the primary metric.
Those labels are never inference features.

## Frozen boundaries

This slice does not change:

- source spans;
- upstream candidate generation;
- v0.2c thresholds;
- v0.2c semantic-prompt extraction behavior;
- the six-type taxonomy;
- canonical paper truth;
- reconciliation;
- production/full-corpus state.

Different-span compound/nested failures remain outside this hypothesis and belong
to a future span-handling slice.

## Development gate frozen before inference

The config freezes candidate-development guardrails before model results are seen:

```text
minimum typer coverage = 0.95
minimum same-span accuracy delta = +0.01
minimum net corrected cases = 5
maximum regression rate = 0.05
minimum model->method reduction fraction = 0.10
maximum macro-F1 drop = 0.0
```

These are development gates only. Passing them would justify freezing the single
candidate for a **new disjoint prediction-blind held-out**. It would not authorize
production or full-corpus extraction.

## Artifacts in this implementation slice

Tracked implementation:

```text
configs/scientific_entity_semantic_typer_candidate_v0.3.yaml
radar_core/contracts/scientific_entity_semantic_typer_candidate.py
radar_core/entities/scientific_entity_semantic_typer.py
radar_core/entities/scientific_entity_semantic_typer_development.py
scripts/entities/make_scientific_entity_semantic_typer_development.py
scripts/validation/check_scientific_entity_semantic_typer_development.py
tests/smoke/test_scientific_entity_semantic_typer_candidate.py
docs/scientific_entity_semantic_typer_candidate_v0.3.md
```

The immutable prepare artifact contains:

```text
manifest.json
development_cases.jsonl
summary.json
README.md
checksums.txt
```

Prepare performs no model inference and no threshold tuning.

## Expected operational sequence

After merging this infrastructure:

1. PLAN the development materialization against the frozen fresh-v0.2c evaluation,
   completed root-cause review, and typing diagnostics.
2. EXECUTE the development materialization once.
3. Run the strict independent package validator.
4. Only then implement/run the bounded candidate inference over the immutable
   `development_cases.jsonl`.
5. Compare candidate vs frozen v0.2c baseline with correction/regression metrics.
6. Freeze, reject, or revise the candidate from consumed development evidence.
7. If frozen, build a new disjoint prediction-blind held-out for independent
   acceptance.

## Safety

This layer is derived and rebuildable. It is not canonical paper truth, not a
reconcile input, not publication ready, and not a full-corpus authorization.
