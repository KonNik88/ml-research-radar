# Scientific Entity Semantic Prompt Raw-Floor Selected Policy v0.2c

Status: **completed / immutable selected-policy build validated**

This layer materializes the selected development policy from the completed v0.2c
raw-floor calibration. It does not run GLiNER and does not tune thresholds.

Frozen lineage:

```text
candidate = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
raw build = scientific-entity-gliner-small-v2.5-v0.1-20260830T100756992945Z
raw predictions = 1762
calibration = scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z
selected trial = calibration-trial:adcd020d8bce5af1ff157f4303e0b171
```

Frozen selected policy:

```text
input raw floor = 0.40
title >= 0.45
abstract >= 0.625
entity-type overrides = none
```

The calibration must remain:

```text
all_hard_gates_passed = true
candidate_promising_for_future_freeze = true
selected_title_at_candidate_raw_floor = false
```

The selected calibration trial must remain semantic-safe and must retain the
materialized development metrics:

```text
combined-72 exact F1 = 0.403677
consumed-48 exact F1 = 0.400000
consumed-48 relaxed F1 = 0.422642
model -> method = 32
method -> task = 25
total type mismatches = 140
method semantic sink = 58
```

Materialization filters the immutable raw build only. For every selected mention:

```text
mention_id = preserved
evidence_id = recomputed under the policy-aware extractor fingerprint
confidence_kind = preserved
confidence_score = preserved
```

The materialized prediction count must exactly equal the selected calibration
trial's `selected_prediction_count`.

Safety boundary:

```text
model inference = false
threshold tuning = false
fresh held-out consumption = false
canonical truth mutation = false
reconcile input = false
production extractor selection = false
full-corpus authorization = false
publication = false
```

After strict validation, the next slice is a controlled `24 / 48 / 72`
development comparison of this exact immutable policy build. A new disjoint
prediction-blind held-out set remains reserved until the development candidate is
fully frozen.


## Materialized selected-policy result

```text
build_id = scientific-entity-semantic-prompt-raw-floor-policy-v0.2c-20260830T105318817514Z
parent raw build = scientific-entity-gliner-small-v2.5-v0.1-20260830T100756992945Z
calibration = scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z
selected trial = calibration-trial:adcd020d8bce5af1ff157f4303e0b171
input predictions = 1762
selected predictions = 1077
rejected predictions = 685
title = 0.45
abstract = 0.625
extractor_fingerprint_changed = true
strict validation = 48 / 48
```

No inference or threshold tuning occurred during materialization.
