# Scientific Entity Semantic Typer v0.3 — H2 Frozen Selective Override Policy

## Status

Development policy frozen for preparation of a new independent acceptance held-out.
This is not production approval and not independent acceptance evidence.

## Parent evidence

H1 (`scientific-entity-semantic-typer-candidate-v0.3-h1`) performed unconditional second-stage semantic retyping and was rejected on consumed development evidence because it introduced 83 regressions while correcting 51 errors.

The deterministic H1 revision analysis selected one bounded H2 policy from a predeclared margin sweep. The first stable three-point all-gate-pass plateau was `[0.05, 0.10, 0.15]`; the selection rule therefore froze the interior threshold `0.10`.

## Frozen H2 candidate

The semantic typer itself is unchanged from H1 and is pinned by its semantic fingerprint. The only revision is the post-inference policy:

```text
if baseline_type == method
and semantic_typer_type == model
and score_margin >= 0.10:
    final_type = model
else:
    final_type = baseline_type
```

The baseline type is a post-inference policy condition only. It is not supplied to the semantic typer as an inference feature.

## Development reproduction

Freeze materialization must reproduce the selected revision result exactly from the immutable H1 case comparison:

- overrides: 33
- corrected errors: 24
- introduced regressions: 9
- wrong-to-wrong changes: 0
- net corrected cases: +15
- regression rate: 0.026239
- same-span accuracy delta: +0.032051
- macro-F1 delta: +0.011061
- model -> method after H2: 41
- model -> method reduction: 0.369231

These values are development reproduction only. They are not a new evaluation and must not be interpreted as independent generalization evidence.

## Frozen lineage

The package fails closed unless all of the following remain exact:

- selected revision-analysis ID and selected policy;
- rejected H1 development evaluation and its case comparison;
- H1 prediction package bound to that evaluation;
- H1 semantic typer config hash and semantic fingerprint;
- H2 threshold, transition family, operator, and preserve-baseline behavior.

The frozen composite candidate has its own deterministic fingerprint combining the frozen H1 semantic typer identity with the H2 post-inference policy.

## Safety

This layer performs no new model inference, no model-threshold tuning, no policy-margin recalibration, no span mutation, no taxonomy change, no canonical mutation, no production selection, and no full-corpus build.

The previous 48-paper fresh-v0.2c sample remains consumed development evidence.

## Next

Prepare a new disjoint prediction-blind held-out for independent H2 acceptance. The H2 policy and its `0.10` margin threshold are frozen before that held-out is created or reviewed and may not be changed based on its results.
