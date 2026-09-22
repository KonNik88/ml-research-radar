# Scientific Entity v0.3 H2 — Independent Acceptance Gate

## Purpose

Preregister the independent acceptance criteria for the already frozen H2
selective semantic-typing intervention **before** human-reference results are
inspected and before any H2 inference is run on the new fresh held-out.

This slice freezes an evaluation contract only. It does not spend the held-out.

## Frozen candidate lineage

```text
candidate_id = scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method
candidate_fingerprint = 6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966
baseline_type = method
semantic_typer_type = model
score_margin >= 0.10
otherwise preserve baseline
```

The candidate policy and threshold remain immutable for this independent cycle.
Any policy or threshold revision defines a new candidate and requires another
new disjoint prediction-blind held-out.

## Frozen fresh-heldout lineage

```text
sample_id = scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z
review_id = scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z
papers = 48
annotation rows = 96
consumed evidence excluded = 120 documents
sample/consumed overlap = 0
```

At contract freeze the sample must still satisfy:

- prediction blind;
- human reference not frozen;
- H2 inference not executed;
- evaluation not executed;
- threshold tuning not executed;
- policy revision not executed.

## Reference adequacy

The v0.2 human-reference semantics are intentionally retained because the
six-type taxonomy and annotation guidelines did not change:

- all 96 title/abstract annotation rows completed;
- manual adjudication;
- prediction blind;
- zero unresolved uncertain mentions;
- at least 20 reference mentions for each of `task`, `method`, `dataset`,
  `metric`, `model`, and `domain`;
- entity surfaces must be exact slices of source text;
- duplicate typed spans are forbidden;
- automatic annotation and automatic approval are forbidden;
- candidate inference is forbidden until reference freeze completes.

## Hard independent H2 gates

H2 is evaluated as a bounded intervention relative to the frozen v0.2c
baseline on the **same new held-out**.

All hard gates must pass:

```text
reference adequacy                           = PASS
candidate fingerprint                       = exact frozen fingerprint
typer coverage                              >= 0.95
same-span accuracy delta                    >= +0.01
net corrected cases                         >= 5
regression rate                             <= 0.05
model->method reduction fraction            >= 0.10
macro-F1 delta                              >= 0.0
absolute exact F1                           >= 0.396882
```

`exact F1 >= 0.396882` is retained as a continuity safety floor from the earlier
independent Scientific Entity gate.

`relaxed F1 >= 0.414868` remains a desirable diagnostic, not a hard gate.

If a denominator required for a comparative hard metric does not exist, the
evaluator must fail closed with insufficient evidence rather than pass the gate
automatically.

## Historical semantic diagnostics

For continuity with v0.2c, independent evaluation must still compute:

```text
model->method count
method->task count
total type mismatch count
method semantic sink count
maximum predicted-type mismatch sink count
```

The historical caps (`43`, `25`, `150`, `74`, `74`) are diagnostics only for H2.
They are **not** hard H2 acceptance gates because they are raw counts originally
frozen for another disjoint sample.

Evaluation must also explicitly materialize:

- `corrected_errors`;
- `introduced_regressions`;
- `model_to_method_direct_corrections`;
- `model_to_method_wrong_to_wrong`.

This prevents a reduced confusion-cell count from being mistaken for genuine
error correction.

## Decision semantics

If every hard gate passes:

```text
accept_h2_as_independently_validated_bounded_semantic_typing_intervention
```

If any hard gate fails:

```text
reject_h2_independent_acceptance
```

Even a PASS does not select a production extractor and does not authorize a
full-corpus Scientific Entity build. Production/full-corpus authorization is a
separate later slice.

A failed held-out becomes consumed evidence and may not be reused to retune and
reaccept H2.

## What this slice does not do

It performs no:

- human-reference inspection;
- baseline inference;
- H2 inference;
- evaluation;
- acceptance decision;
- threshold tuning;
- policy revision;
- span mutation;
- taxonomy change;
- canonical truth mutation;
- production selection;
- full-corpus build.

## Next slice

After this contract validates, proceed to:

```text
H2 v0.3 Prediction-Blind Reference Freeze Tooling
```
