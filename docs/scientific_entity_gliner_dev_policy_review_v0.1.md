# Scientific Entity GLiNER Dev Policy Review v0.1

## Status

```text
status = completed local dev-policy review
checkpoint_date = 2026-08-23
calibration_id = scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z
calibration_status = candidate
strict_validator = 53 / 53 required checks
selected_profile = balanced_f1
selected_trial_id = calibration-trial:1172aea9d875d59f3b39cc21488dec8f
selected_title_threshold = 0.55 inclusive
selected_abstract_threshold = 0.65 inclusive
selected_entity_type_thresholds = none
selected_dev_policy_frozen = true
production_extractor_selected = false
full_corpus_build_authorized = false
current_24_paper_dev_set_becomes_held_out = false
canonical_truth_mutated = false
```

This record closes the human review step after the bounded GLiNER threshold-policy
calibration. It freezes one **development-only** source-field threshold policy by
reference to an immutable calibration and trial identity. It does not promote a
production extractor, authorize a full-corpus build, reinterpret model scores as
probabilities, or turn the tuned 24-paper package into held-out evidence.

## Immutable evidence reviewed

```text
review_id = scientific-entity-manual-review-v0.1-20260821T131320262656Z
review documents = 24
reference mentions = 435
prediction_build_id = scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z
input predictions = 546
baseline_evaluation_id = scientific-entity-evaluation-v0.1-20260823T124036780234Z
calibration_id = scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z
calibration trials = 127
profile-eligible trials = 69
Pareto trials = 29
strict validation = 53 / 53 required checks
model inference during calibration = false
```

The calibration output remains local, immutable, and ignored by Git. The
repository records only aggregate evidence, exact identities, and the human
decision boundary.

## Profile review

| Profile | Title threshold | Abstract threshold | Predictions | Exact P | Exact R | Exact F1 | Relaxed F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 0.50 | 0.50 | 546 | 0.322344 | 0.404598 | 0.358817 | 0.397554 |
| Precision / F0.5 | 0.65 | 0.85 | 175 | 0.542857 | 0.218391 | 0.311476 | 0.324590 |
| **Balanced / F1** | **0.55** | **0.65** | **391** | **0.401535** | **0.360920** | **0.380146** | **0.404358** |
| Recall / F2 | 0.55 | 0.50 | 545 | 0.322936 | 0.404598 | 0.359184 | 0.397959 |

The balanced profile is selected as the single frozen dev policy. Relative to
the unfiltered GLiNER baseline it removes 155 predictions, materially improves
precision, retains most recall, improves exact F1 from `0.358817` to `0.380146`,
and improves relaxed F1 from `0.397554` to `0.404358`.

The precision profile is too aggressive for the general entity-evidence layer,
while the recall profile is effectively the original `0.50` policy and provides
negligible gain.

## Local robustness around the selected source-field policy

At fixed `abstract = 0.65`, the exact F1 surface is shallow across the lower
title thresholds:

| Title threshold | Predictions | Exact P | Exact R | Exact F1 |
|---:|---:|---:|---:|---:|
| 0.50 | 392 | 0.400510 | 0.360920 | 0.379686 |
| **0.55** | **391** | **0.401535** | **0.360920** | **0.380146** |
| 0.60 | 384 | 0.403646 | 0.356322 | 0.378511 |
| 0.65 | 380 | 0.405263 | 0.354023 | 0.377914 |

This supports the source-field conclusion more strongly than an exact claim
that `0.55` is uniquely optimal: the main stable signal is that abstracts need
a materially stricter threshold than titles. `0.55 / 0.65` is frozen because it
is the deterministic balanced-F1 winner under the declared search and tie-break
contract, not because the 24-paper sample proves that neighboring title
thresholds are universally inferior.

## Per-type effect of the frozen source-field policy

| Entity type | Baseline exact F1 | Frozen-policy exact F1 | Delta |
|---|---:|---:|---:|
| task | 0.271739 | 0.240601 | -0.031138 |
| method | 0.374269 | 0.376624 | +0.002355 |
| dataset | 0.372882 | 0.476191 | +0.103309 |
| metric | 0.377778 | 0.400000 | +0.022222 |
| model | 0.466102 | 0.521739 | +0.055637 |
| domain | 0.114286 | 0.131147 | +0.016861 |

The task degradation is explicitly retained as a caveat. Diagnostic type probes
show that task prefers an isolated `0.50` threshold, while dataset/model/domain
prefer stricter thresholds. Those probes are **not** combined into the frozen
policy: six type-specific parameters on 24 dev papers would be an unjustified
overfit risk. The v0.1 non-Cartesian safety boundary remains intact.

## Decision

```text
GLiNER candidate = retained
selected dev profile = balanced_f1
frozen dev policy = title >= 0.55 / abstract >= 0.65
entity-type overrides = none
policy identity = scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z + calibration-trial:1172aea9d875d59f3b39cc21488dec8f
production promotion = false
full-corpus extraction = false
same 24 papers as held-out evidence = forbidden
```

This is a **dev policy freeze**, not a production-quality acceptance decision.
The selected policy changes emitted mention semantics relative to the original
global `0.50` candidate and therefore must not rewrite the existing immutable
prediction build.

## Next safe slice

The next slice is to materialize the frozen source-field policy under a new
immutable candidate configuration/build identity and validate/evaluate it
without changing the old GLiNER build. After that candidate semantics are
frozen, prepare at least 32 new, disjoint, prediction-blind papers for held-out
evidence. The 32-paper gate is a minimum next check, not sufficient evidence for
a full-corpus or future multi-million-paper production claim.
