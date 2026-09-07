# Scientific Entity Fresh Held-Out Frozen Policy v0.2

## Purpose

This slice applies the already-frozen v0.2c source-field threshold policy to the already-materialized fresh-heldout raw predictions. It is a deterministic derived-evidence transformation, not a new inference or calibration run.

## Frozen inputs

```text
candidate = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
raw build = scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z
raw predictions = 1257
raw extractor fingerprint = e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13
raw runtime config SHA-256 = b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6

frozen development policy config SHA-256 = 9ad8d4f6728e49e04ed4bdc4cec6f4d2a23db82d55af71b4f71f33dabf84f62c
calibration = scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z
selected trial = calibration-trial:adcd020d8bce5af1ff157f4303e0b171

title threshold = 0.45
abstract threshold = 0.625
entity-type overrides = none
```

The fresh held-out remains the immutable 48-paper sample with 944 frozen reference mentions. References are revalidated as lineage evidence through the raw-inference validator, but reference labels are **not used for filtering**.

The original development policy contract intentionally remains `fresh_heldout_consumption_allowed=false`. This new wrapper does not alter that historical contract; it is the explicit independent-gate authorization to reuse only the already-frozen threshold semantics on the now-frozen fresh held-out.

## PLAN semantics

PLAN is intentionally non-filtering. It validates:

- exact frozen policy config semantic SHA and selected-trial identity;
- exact raw inference lineage and green strict raw validation;
- raw count `1257`;
- exact raw extractor fingerprint;
- exact sample/review lineage;
- absence/presence of the one-shot output directory.

PLAN may read raw evidence as part of the existing strict raw-build validator, but it does **not** invoke policy filtering or compute a selected count. Therefore the selected prediction count first becomes visible only on EXECUTE.

## EXECUTE semantics

EXECUTE performs no model call. It uses the existing `filter_predictions` semantics with inclusive thresholds:

```text
title:    score >= 0.45
abstract: score >= 0.625
```

For selected mentions:

- `mention_id` is preserved;
- confidence score/kind are preserved;
- `evidence_id` is recomputed from the policy-aware extractor fingerprint;
- parent evidence linkage is recorded.

The output is immutable and one-shot:

```text
data/entities/scientific_entity_fresh_heldout_frozen_policy/v0.2/
scientific-entity-semantic-prompt-raw-floor-policy-fresh-v0.2c-20260901T130232963026Z/
```

## Executed policy materialization

The frozen policy was applied exactly once to the immutable fresh-heldout raw build.

```text
build_id = scientific-entity-semantic-prompt-raw-floor-policy-fresh-v0.2c-20260901T130232963026Z
raw prediction count = 1257
selected prediction count = 773
rejected prediction count = 484

title threshold = 0.45
abstract threshold = 0.625
entity-type overrides = none

policy extractor fingerprint = 77af105871b227daa0d8c9e5501839addf229004795490a63bebe4f02672cf52

model inference executed by policy = false
policy applied = true
threshold tuning executed = false
reference labels used for filtering = false
evaluation executed = false
acceptance decision made = false
canonical truth mutated = false
production extractor selected = false
full-corpus build authorized = false
```

Strict independent policy validation passed:

```text
total checks = 46
required failures = 0
next = evaluate_frozen_v02c_on_fresh_heldout_once
```

The selected count is descriptive materialization output only. It is not itself a
quality result and must not be used to tune thresholds before independent evaluation.

## Safety boundary

```text
model inference = false
threshold tuning = false
reference labels used for filtering = false
evaluation = false
acceptance decision = false
canonical mutation = false
production selection = false
full-corpus authorization = false
```

## Next slice

Strict policy-build validation is complete. The next bounded slice is:

```text
next = evaluate_frozen_v02c_on_fresh_heldout_once
```

Only that later evaluation slice may compare selected predictions with the 944 frozen references and apply the pre-frozen acceptance gate.
