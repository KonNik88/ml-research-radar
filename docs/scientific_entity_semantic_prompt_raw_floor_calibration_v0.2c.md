# Scientific Entity Semantic Prompt Raw-Floor Calibration v0.2c

Status: **completed / immutable calibration validated / development hard gates passed**

This slice evaluates the already-materialized v0.2c raw GLiNER evidence at score floor
`0.40`. It performs no model inference.

Frozen search:

```text
title = 0.400 / 0.425 / 0.450 / 0.475 / 0.500
abstract = 0.625 fixed
trials = 5
```

The semantic guardrails and hard decision gates are inherited unchanged from the
pre-frozen v0.2c design contract.

A diagnostic control trial is `title=0.50 / abstract=0.625`.

The original calibration tooling assumed that lowering the GLiNER inference threshold
would return the old raw prediction set unchanged plus only lower-score evidence. A
read-only lineage diagnostic showed that this stronger assumption is not valid at the
threshold boundary: the v0.2c `0.40` run preserves all `1430 / 1430` v0.2a mention IDs
with identical scores, but also returns one new title mention at score exactly `0.50`:

```text
surface_text = Transfer Learning
entity_type = method
title = CactusNets: Layer Applicability as a Metric for Transfer Learning
```

Therefore exact v0.2b metric reproduction is diagnostic rather than a hard invariant.
The hard lineage invariant is preservation of every baseline mention identity and score.

The materialized v0.2b control reference remains:

```text
combined-72 exact F1 = 0.398654
consumed-48 exact F1 = 0.396453
model -> method = 32
method -> task = 25
total type mismatches = 138
method semantic sink = 57
```

Calibration fails closed only if baseline raw evidence is lost or a baseline score
changes. New evidence at or above the old `0.50` floor is allowed, counted explicitly,
and evaluated as part of the controlled effect of changing the inference threshold.

The calibration artifact records:

```text
baseline_raw_evidence_preserved
baseline_raw_missing_count
baseline_raw_score_changed_count
new_at_or_above_baseline_floor_count
new_selected_by_v02b_control_count
v02b_control_metrics_reproduced
v02b_control_selected_prediction_delta
```

For the already-observed raw builds, the expected lineage diagnostic before scoring is:

```text
baseline raw mentions = 1430
candidate raw mentions = 1762
baseline mentions missing = 0
baseline scores changed = 0
new mentions >= 0.50 = 1
new mentions selected by 0.50 / 0.625 control = 1
```

The selected trial is chosen only among semantic-safe trials by:

1. combined-72 exact F1 descending;
2. combined-72 relaxed F1 descending;
3. combined-72 exact recall descending;
4. title threshold descending;
5. trial ID ascending.

Hard gates:

```text
consumed-48 exact F1 >= 0.396882
combined-72 exact F1 >= 0.398654
semantic guardrails = PASS
```

Desirable signal:

```text
consumed-48 relaxed F1 >= 0.419252
```

If the selected promising title threshold is still exactly `0.40`, the artifact
records that the new raw input floor may remain binding and does not authorize a
fresh held-out sample automatically.

Safety boundary:

```text
model inference during calibration = false
prompt changes = false
fresh held-out consumption = false
canonical mutation = false
production selection = false
full-corpus authorization = false
```


## Materialized calibration result

```text
calibration_id = scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z
raw predictions = 1762
trials = 5
eligible = 4
selected trial = calibration-trial:adcd020d8bce5af1ff157f4303e0b171
title = 0.45
abstract = 0.625
combined exact F1 = 0.403677
consumed-48 exact F1 = 0.400000
consumed-48 relaxed F1 = 0.422642
model -> method = 32
method -> task = 25
total type mismatches = 140
method sink = 58
all_hard_gates_passed = true
candidate_promising_for_future_freeze = true
selected_title_at_candidate_raw_floor = false
strict validation = 61 / 61
```

Baseline raw evidence was preserved with zero missing mentions and zero score changes. The frozen development gates passed without post-hoc relaxation.
