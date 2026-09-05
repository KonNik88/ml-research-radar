# Scientific Entity Fresh v0.2 Frozen Raw Inference

## Status

```text
status = one-shot raw inference executed and strictly validated
reference evidence = frozen and strictly validated
fresh held-out = 48 documents
frozen references = 944
candidate = v0.2c
model inference on fresh held-out = executed exactly once
raw mentions = 1257
policy application = not executed
evaluation = not executed
acceptance decision = not made
```

## Purpose

This slice opens the fresh independent held-out to the already-frozen v0.2c
candidate exactly once. It does not create a new extractor path. Execution
reuses `build_scientific_entity_evidence_gliner.build_gliner_candidate` with
its existing GLiNER adapter, provenance, model-artifact verification, windowing,
mention identity, immutable output, and independent build validator.

## Critical PLAN boundary

The legacy GLiNER builder performs inference even when its own `execute=False`.
That behavior is correct for its original bounded-development role but is not a
safe PLAN for an independent held-out.

Therefore this wrapper defines a new outer PLAN that performs only:

- frozen contract validation;
- semantic SHA verification of the exact v0.2c runtime config;
- strict revalidation of the already-frozen fresh reference evidence;
- exact sample/review/reference-count lineage checks;
- exact 48-paper sample-input existence check;
- one-shot output absence check.

The outer PLAN never calls GLiNER and never reveals candidate predictions.

## Frozen candidate

```text
candidate_id = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
runtime config SHA-256 = b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6
model = gliner-community/gliner_small-v2.5
revision = f227d3cd637bd4e6757ae143935316d062393341
artifact SHA-256 = d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74
raw inference floor = 0.40
window = 320 tokens
overlap = 64 tokens
source fields = title + abstract
entity types = task/method/dataset/metric/model/domain
```

Future policy thresholds are already frozen but are deliberately not applied in
this slice:

```text
title = 0.45
abstract = 0.625
entity-type overrides = none
```

## Frozen independent evidence

```text
sample_id = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z
review_id = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z
documents = 48
references = 944
uncertain references = 0
task = 150
method = 279
dataset = 66
metric = 86
model = 280
domain = 83
```

Before EXECUTE the reference package must pass its existing strict validator
with zero required failures.

## One-shot execution identity

```text
build_id = scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z
input = <fresh sample>/canonical_documents.sample.jsonl
max_documents = 48
status = candidate
output root = data/entities/scientific_entity_evidence/v0.1
```

The build ID is fixed. The output directory is immutable. A second `--execute`
with the same contract fails closed if the build directory already exists.

## Executed one-shot raw build

```text
build_id = scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z
candidate_id = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
runtime config SHA-256 = b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6
input documents = 48
raw mentions = 1257
extractor fingerprint = e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13

model artifact verified = true
backbone config verified = true
runtime device = NVIDIA GeForce RTX 2070 SUPER
inference duration seconds = 10.334789
peak CUDA memory bytes = 418029568

reference validation failures = 0
raw-build validation failures = 0
strict combined validator = 22 / 22
required failures = 0

model inference executed = true
policy applied = false
evaluation executed = false
acceptance decision made = false
canonical truth mutated = false
production extractor selected = false
full-corpus build authorized = false
```

The fixed build directory now exists, so the one-shot contract is consumed.
A second execution with the same build identity must fail closed.

## Artifact-loss incident and documented recovery

After the successful original one-shot execution and a green `22 / 22` strict
validation, a smoke test with an incorrectly non-isolated cleanup path targeted
the real fixed build directory and deleted the local raw artifact.

The original model execution remains part of provenance. It is not rewritten as
though it never occurred.

Before any policy application or evaluation:

1. the faulty tests were moved to pytest `tmp_path` so they can never create or
   delete the repository-held one-shot artifact;
2. a dedicated recovery workflow recorded the already-observed original run
   facts before rematerialization;
3. the exact frozen v0.2c candidate was rematerialized once under the same
   runtime config, model revision/artifact, 48-document sample, and 944-reference
   package;
4. the recovered build reproduced both recorded observable invariants.

```text
recovery reason = faulty_smoke_test_deleted_successful_one_shot_raw_artifact
original raw mentions = 1257
recovered raw mentions = 1257
raw mention count match = true

original extractor fingerprint = e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13
recovered extractor fingerprint = e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13
extractor fingerprint match = true
recovery match passed = true

byte identity with deleted original artifact verifiable = false
policy applied = false
evaluation executed = false
acceptance decision made = false
```

Byte-for-byte identity with the deleted original artifact cannot be claimed
because its independent file checksums were not preserved before deletion.
The recovery evidence therefore states only what is actually supported:
identical frozen lineage plus identical recorded raw mention count and extractor
fingerprint.

After recovery, the ordinary strict validator again passed `22 / 22` with zero
required failures. No fresh-heldout quality metric was inspected and no prompt,
threshold, model, sample, or taxonomy change occurred between the original run
and recovery.

The detailed incident record is
[`scientific_entity_fresh_heldout_frozen_inference_recovery_v0.2.md`](scientific_entity_fresh_heldout_frozen_inference_recovery_v0.2.md).

## Validation

After execution, the combined validator requires both:

1. strict fresh-reference evidence validation; and
2. the existing independent GLiNER raw-build validator.

It additionally confirms the exact build ID, exact 48-paper sample input,
frozen runtime config SHA/model provenance, raw floor `0.40`, `320/64` adapter,
and absence of policy/evaluation/acceptance operations in this slice.

## Safety

This slice does not:

- change prompts, thresholds, model, sample, or entity taxonomy;
- apply title/abstract policy thresholds;
- compute exact or relaxed F1;
- inspect semantic confusion counts;
- make an acceptance decision;
- mutate canonical truth;
- select a production extractor;
- authorize a full-corpus build.

Strict raw-build validation is complete:

```text
next = apply_frozen_v02c_policy_once
title threshold = 0.45
abstract threshold = 0.625
entity-type overrides = none
new model inference = forbidden
threshold calibration/tuning = forbidden
```

The next slice is deterministic policy materialization only; it does not rerun
GLiNER and it does not yet compute held-out quality metrics.
