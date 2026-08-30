# Scientific Entity Semantic Prompt Raw-Floor Controlled Comparison v0.2c

Status: **completed / controlled development comparison validated / candidate ready for development freeze**

This layer closes the consumed-development evidence line for the selected v0.2c
policy before any new independent held-out sample is spent.

Frozen candidate lineage:

```text
candidate = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
raw build = scientific-entity-gliner-small-v2.5-v0.1-20260830T100756992945Z
calibration = scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z
selected trial = calibration-trial:adcd020d8bce5af1ff157f4303e0b171
policy build = scientific-entity-semantic-prompt-raw-floor-policy-v0.2c-20260830T105318817514Z
policy = title >= 0.45 / abstract >= 0.625
selected predictions = 1077
```

The comparison evaluates the materialized policy with the unchanged v0.1 evaluator
on three consumed development views:

```text
old_dev_24
consumed_v01_heldout_48
combined_dev_72
```

The 48-paper view remains **consumed development evidence for v0.2**. It is not an
independent v0.2 acceptance held-out set.

## Hard invariants

The materialized policy evaluation must reproduce the selected calibration trial:

```text
combined-72 exact F1 = 0.403677
consumed-48 exact F1 = 0.400000
consumed-48 relaxed F1 = 0.422642
model -> method = 32
method -> task = 25
total type mismatches = 140
method semantic sink = 58
```

It must also retain the pre-frozen development guardrails:

```text
consumed-48 exact F1 >= 0.396882
combined-72 exact F1 >= 0.398654
model -> method <= 43
method -> task <= 25
total type mismatches <= 150
method semantic sink <= 74
max predicted-type mismatch sink <= 74
```

No gate may be relaxed after observing comparison results.

## Historical progression artifact

`progression.json` is grounded in two immutable historical inputs rather than
hard-coded narrative recollection:

```text
v0.2a comparison = scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z
v0.2b calibration = scientific-entity-semantic-prompt-threshold-calibration-v0.2b-20260830T093225845167Z
```

It records the consumed-48 and combined-72 progression across:

```text
v0.1 frozen baseline
v0.2a semantic prompts with inherited thresholds
v0.2b threshold-calibrated policy
v0.2c raw-floor selected policy
```

## Decision boundary

If calibration reproduction and all frozen hard guardrails pass, the comparison may
mark the candidate as ready for **development freeze** only.

The next slice is then:

```text
freeze v0.2c development candidate
prepare a new disjoint prediction-blind held-out sample
```

This layer does not itself:

```text
run model inference
perform threshold tuning
consume a fresh held-out set
mutate canonical truth
select a production extractor
authorize a full-corpus build
```


## Materialized controlled comparison

```text
comparison_id = scientific-entity-semantic-prompt-raw-floor-comparison-v0.2c-20260830T110628936475Z
development documents = 72
reference mentions = 1316
candidate predictions = 1077
old-dev-24 exact F1 = 0.410959
consumed-48 exact F1 = 0.400000
consumed-48 relaxed F1 = 0.422642
combined-72 exact F1 = 0.403677
model -> method = 32
method -> task = 25
total type mismatches = 140
method semantic sink = 58
calibration_reproduction_passed = true
all_hard_guardrails_passed = true
candidate_ready_for_development_freeze = true
strict validation = 45 / 45
```

This closes consumed development evidence only. It is not independent acceptance. The frozen v0.2c candidate keeps the v0.2a prompts and pinned small-v2.5 model, uses raw inference floor `0.40`, `title >= 0.45`, `abstract >= 0.625`, and no entity-type overrides. The next authorized slice is a new disjoint prediction-blind v0.2 held-out gate. No production extractor is selected and no full-corpus build is authorized.
