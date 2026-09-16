# Scientific Entity Semantic Typer v0.3 — H1 Failure / Revision Analysis

## Status

Development-only deterministic revision analysis over the already-consumed H1 development evaluation.
No new model inference is executed.

## Parent result

H1 (`scientific-entity-semantic-typer-candidate-v0.3-h1`) was rejected on the frozen same-span development package:

- 474 total development cases;
- 468 primary-metric eligible cases;
- 51 corrected baseline errors;
- 83 introduced regressions;
- net corrected cases = -32;
- strong reduction of the `model -> method` confusion was not sufficient to offset global regressions.

## Bounded H2 policy family

The revision analysis considers exactly one policy family:

1. preserve the frozen v0.2c baseline type by default;
2. allow an override only when the baseline type is `method`;
3. require the already-frozen H1 second-stage typer to predict `model`;
4. require the H1 `score_margin` to meet a calibrated threshold;
5. otherwise preserve the baseline type.

The baseline type is used only as a post-inference policy condition. It was not supplied to H1 as a model feature.

## Threshold calibration

The analysis uses the frozen grid `0.00, 0.05, ..., 0.90` on consumed development evidence only.
It does **not** select the threshold that maximizes F1.

A threshold is selectable only when it is the lowest interior point of a three-point contiguous plateau where the previous, current, and next grid thresholds all satisfy the already-frozen H1 development gates.

This rule is intended to avoid selecting an isolated attractive threshold after inspection.

## Reused development gates

- typer coverage >= 0.95;
- same-span accuracy delta >= +0.01;
- net corrected cases >= 5;
- regression rate <= 0.05;
- `model -> method` reduction >= 10%;
- macro-F1 drop <= 0.

## Outputs

- `manifest.json` — immutable lineage and safety flags;
- `summary.json` — selected/not-selected result and calibrated policy metrics;
- `margin_sweep.json` — all predeclared threshold rows;
- `transition_breakdown.json` — H1 correction/regression/wrong-to-wrong transitions;
- `selected_policy.json` — one bounded H2 policy if stable selection succeeds;
- `policy_case_outcomes.jsonl` — deterministic replay of the selected policy on primary development cases;
- `checksums.txt` — immutable output checksums.

## Safety

This analysis:

- performs no new model inference;
- does not tune the GLiNER inference threshold;
- may calibrate only the H2 post-inference margin threshold on already-consumed development evidence;
- does not mutate spans, taxonomy, canonical truth, production state, or full-corpus state;
- is not independent acceptance;
- requires a new disjoint prediction-blind held-out for any future H2 acceptance decision.

## Next

If a stable H2 policy is selected, materialize/freeze that policy and verify deterministic replay without rerunning H1 inference. Then prepare a new disjoint prediction-blind held-out for independent acceptance.
