# Scientific Entity Fresh Held-Out Frozen Inference v0.2 — Artifact-Loss Recovery

## Incident

The frozen v0.2c candidate was successfully executed once on the immutable
48-document fresh held-out.

Observed facts printed by the successful execution:

```text
raw_mention_count = 1257
extractor_fingerprint = e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13
model_artifact_verified = true
backbone_config_verified = true
runtime_device_name = NVIDIA GeForce RTX 2070 SUPER
inference_duration_seconds = 10.334789
peak_cuda_memory_bytes = 418029568
```

Strict post-build validation then passed `22 / 22`.

A faulty smoke test subsequently targeted the real fixed output directory and
deleted the successful local raw artifact during cleanup.

This is a **test-isolation defect**, not a model/inference failure.

## Safety interpretation

The original inference occurrence remains part of provenance and must not be
rewritten as though it never happened.

A recovery run is permitted only to rematerialize the deleted local artifact
under the exact frozen conditions:

- same v0.2c runtime config and SHA;
- same model/revision/artifact;
- same 48-document fresh sample;
- same frozen 944-reference package;
- no prompt changes;
- no threshold changes;
- no model changes;
- no sample changes;
- no policy application;
- no evaluation;
- no acceptance decision.

No fresh-heldout metrics were observed between the original run and recovery.

Because the original raw artifact was deleted before its file checksums were
preserved separately, **byte identity with the deleted artifact cannot be
proved**. Recovery therefore checks only the facts that were actually recorded
before deletion: raw mention count `1257` and the exact extractor fingerprint.

## Test hotfix

All smoke tests that create, detect, validate, or delete a fixed build now root
their writable paths under pytest `tmp_path`.

Tests must never create or delete:

```text
data/entities/scientific_entity_evidence/v0.1/
scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z
```

## Recovery workflow

First run recovery PLAN. PLAN must not invoke the model.

Then, and only if PLAN is green, execute the documented recovery exactly once.
The recovery script writes a separate local audit package before and after the
rerun under:

```text
data/entities/scientific_entity_fresh_heldout_frozen_inference_recovery/v0.2/
scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z/
```

If the recovered raw mention count or extractor fingerprint differs from the
recorded original facts, stop before policy application or evaluation.

## Recovery outcome

Recovery was executed once under the exact frozen contract after the test-isolation
hotfix was in place.

```text
recovery phase complete = true
recovery reason = faulty_smoke_test_deleted_successful_one_shot_raw_artifact
original one-shot execution observed = true
original artifact available before recovery = false
byte identity with deleted artifact verifiable = false

candidate = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
runtime config SHA-256 = b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6
sample = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z
review = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z
frozen references = 944
build = scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z

original raw mentions = 1257
recovered raw mentions = 1257
raw mention count match = true

original extractor fingerprint = e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13
recovered extractor fingerprint = e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13
extractor fingerprint match = true

recovery match passed = true
policy applied = false
evaluation executed = false
acceptance decision made = false
```

After recovery, the ordinary strict frozen-inference validator again passed:

```text
input documents = 48
raw mentions = 1257
reference mentions = 944
reference validation failures = 0
raw-build validation failures = 0
strict validator = 22 / 22
required failures = 0
next = apply_frozen_v02c_policy_once
```

The recovered artifact is therefore the current local raw evidence materialization.
The incident does not authorize any additional model run. Future tests are isolated
from the repository evidence path and the recovery path itself is one-shot/fail-closed.

