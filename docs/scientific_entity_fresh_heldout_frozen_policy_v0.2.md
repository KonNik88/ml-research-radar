# Scientific Entity Fresh Held-Out Frozen Policy v0.2

## Purpose

Apply the already-frozen v0.2c threshold policy to the already-materialized fresh-heldout raw predictions.

This slice is deliberately deterministic and non-evaluative:

```text
raw parent = 48 documents / 1257 raw mentions
policy origin = development-only v0.2c calibration
input floor = 0.40
title threshold = 0.45
abstract threshold = 0.625
entity-type overrides = none
```

The layer does **not** run GLiNER, tune thresholds, compare predictions with held-out references, compute quality metrics, or make an acceptance decision.

## Frozen lineage

```text
candidate = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
raw build = scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z
raw mentions = 1257
raw extractor fingerprint = e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13
sample = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z
review = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z
frozen references = 944
policy calibration = scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z
selected trial = calibration-trial:adcd020d8bce5af1ff157f4303e0b171
```

The tracked development policy config is pinned by semantic SHA-256:

```text
9ad8d4f6728e49e04ed4bdc4cec6f4d2a23db82d55af71b4f71f33dabf84f62c
```

## Identity semantics

Policy application preserves the scientific mention identity:

```text
mention_id = preserved
confidence_score = preserved
evidence_id = recomputed
extractor_fingerprint = policy-aware and differs from raw parent
```

This keeps the semantic source span/type identity stable while making the applied policy part of evidence provenance.

## Output

The immutable/rebuildable policy artifact is written under:

```text
data/entities/scientific_entity_fresh_heldout_policy/v0.2/
scientific-entity-gliner-small-v2.5-fresh-v0.2c-policy-20260901T130232963026Z/
```

It contains:

```text
mentions.jsonl
manifest.json
derivation_manifest.json
evidence_lineage.jsonl
data_quality_summary.json
schema.json
README.md
checksums.txt
```

The generated artifact is local derived evidence and is not canonical truth.

## Safe workflow

1. Run PLAN. It validates raw inference lineage and the frozen development policy, computes deterministic selected/rejected counts in memory, and writes nothing.
2. If PLAN is green, run `--execute` once.
3. Run the independent strict policy validator.
4. Stop before any comparison with the 944 frozen references.

## Execution result

The frozen policy was applied exactly once and independently validated.

```text
status = frozen policy applied and strictly validated
build_id = scientific-entity-gliner-small-v2.5-fresh-v0.2c-policy-20260901T130232963026Z

input predictions = 1257
selected predictions = 773
rejected predictions = 484

fresh policy config SHA-256 = 9375fc73ce5ff8cf757891bca2f2ca5461b9e140439ef5c589aa3888d5064abb
development policy semantic SHA-256 = 9ad8d4f6728e49e04ed4bdc4cec6f4d2a23db82d55af71b4f71f33dabf84f62c

title threshold = 0.45
abstract threshold = 0.625
entity-type overrides = none

raw inference validation failures = 0
strict policy validator = 37 / 37
required failures = 0

new model inference executed = false
threshold tuning executed = false
reference comparison executed = false
evaluation executed = false
acceptance decision made = false
canonical truth mutated = false
production extractor selected = false
full corpus authorized = false
```

The `773 / 484` split is only the deterministic result of the pre-frozen policy.
It is not a quality metric and does not imply acceptance or rejection.

## Safety boundary

```text
new model inference = false
threshold tuning = false
prompt changes = false
model changes = false
sampling changes = false
reference comparison = false
evaluation = false
acceptance decision = false
canonical mutation = false
production extractor selected = false
full corpus authorized = false
```

## Next slice

Strict validation is complete. The next bounded slice is:

```text
evaluate_frozen_v02c_policy_once
```

That next slice may compare the frozen selected predictions against the frozen human references and apply the acceptance gate that was frozen before the fresh held-out was sampled.
