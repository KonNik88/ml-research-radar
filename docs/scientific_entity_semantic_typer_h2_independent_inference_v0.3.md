# Scientific Entity Semantic Typer v0.3 — Frozen H2 Independent Inference

## Purpose

This slice runs the already-frozen H2 candidate on the new disjoint v0.3 held-out only after the prediction-blind human reference has been frozen and strictly validated.

The slice is inference-only. It does not evaluate against human labels and does not make an acceptance decision.

## Frozen candidate

Candidate:

`scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method`

Candidate fingerprint:

`6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966`

Frozen H2 rule:

- baseline type must be `method`;
- semantic typer must predict `model` without fallback;
- `score_margin >= 0.10`;
- then final type is `model`;
- otherwise preserve the baseline type.

No span repair, taxonomy change, threshold tuning, or policy revision is allowed.

## Held-out lineage

Sample:

`scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z`

Review:

`scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z`

Expected document count: `48`.

The human reference must already be frozen and must pass the strict H2 v0.3 reference validator before EXECUTE is permitted.

## Why inference cases are built from baseline predictions

The independent acceptance gate later includes full exact/relaxed extraction metrics as well as same-span typing metrics.

Therefore semantic-typer cases are built from every selected frozen baseline prediction span, not only spans that match the human reference. Using reference-matched spans at inference time would leak human labels into case selection and would prevent a valid full precision/recall/F1 comparison.

Human reference labels are not read into inference cases and are not model features.

## Inputs

The slice binds to:

- frozen independent acceptance-gate config;
- frozen v0.3 sample;
- frozen human reference evidence;
- frozen H2 candidate definition;
- parent H1 semantic-typer config;
- frozen v0.2c upstream GLiNER runtime config;
- frozen v0.2c baseline threshold policy.

The v0.2c upstream baseline is reconstructed on the 48 new documents using the frozen raw threshold and frozen title/abstract selection thresholds. The H1 semantic typer is then run on every selected baseline span, and the frozen H2 rule is applied.

## PLAN semantics

PLAN:

- validates all parent lineage and frozen reference evidence;
- chooses the future immutable inference ID/output path;
- does not load the model;
- does not run upstream inference;
- does not run semantic typing;
- does not write output;
- does not evaluate predictions.

Expected next slice after PLAN:

`execute_frozen_h2_independent_inference_once`

## EXECUTE semantics

EXECUTE is one-shot and immutable. Existing output directories are never overwritten.

It materializes:

- `upstream_raw_mentions.jsonl` — raw v0.2c predictions at the frozen input threshold;
- `baseline_mentions.jsonl` — the frozen v0.2c baseline threshold subset;
- `semantic_typer_cases.jsonl` — reference-free target-focused cases for all baseline spans;
- `semantic_typer_predictions.jsonl` — frozen parent semantic-typer outputs;
- `h2_predictions.jsonl` — final H2 decisions after the selective override rule;
- `summary.json`;
- `manifest.json`;
- `README.md`;
- `checksums.txt`.

The manifest records exact config/evidence lineage, counts, immutable file hashes, and fail-closed safety flags.

Expected next slice after EXECUTE:

`validate_h2_v03_independent_inference_evidence`

## Validation

The strict validator verifies, among other things:

- exact package layout and checksums;
- candidate/sample/review/config lineage;
- frozen reference precondition;
- reconstruction of baseline predictions from raw predictions using the frozen threshold policy;
- reconstruction of inference cases without human-reference labels;
- semantic prediction/case identity and coverage counts;
- exact reconstruction of H2 predictions from the frozen policy;
- no span mutation;
- exact summary reconstruction;
- evaluation and acceptance decision remain false.

After strict validation passes, the next slice is:

`run_h2_independent_comparative_evaluation`

## CLI

PLAN:

```bat
python -m scripts.entities.run_scientific_entity_semantic_typer_h2_independent_inference ^
  --sample-dir data\entities\scientific_entity_fresh_heldout_sample\v0.3\scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z ^
  --reference-dir data\entities\scientific_entity_semantic_typer_h2_reference\v0.3\scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z ^
  --development-package-dir data\entities\scientific_entity_semantic_prompt_development\v0.2a\scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z ^
  --previous-heldout-sample-dir data\entities\scientific_entity_fresh_heldout_sample\v0.2\scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z ^
  --frozen-candidate-dir data\entities\scientific_entity_semantic_typer_h2_frozen_candidate\v0.3\scientific-entity-semantic-typer-h2-frozen-candidate-v0.3-20260919T083718533083Z
```

EXECUTE uses the same arguments plus `--execute`.

Strict validation requires the generated `--inference-dir` plus the same lineage directories:

```bat
python -m scripts.validation.check_scientific_entity_semantic_typer_h2_independent_inference ^
  --inference-dir <generated inference directory> ^
  --sample-dir <sample directory> ^
  --reference-dir <frozen reference directory> ^
  --development-package-dir <v0.2a development package> ^
  --previous-heldout-sample-dir <v0.2 previous held-out sample> ^
  --frozen-candidate-dir <frozen H2 candidate directory> ^
  --strict
```

## Explicit non-goals

This slice does not:

- inspect human labels to construct model cases;
- calculate exact/relaxed F1;
- calculate same-span accuracy delta;
- tune the `0.10` threshold;
- revise H2 policy;
- make ACCEPT/REJECT decision;
- select a production extractor;
- authorize full-corpus extraction;
- mutate canonical paper truth.
