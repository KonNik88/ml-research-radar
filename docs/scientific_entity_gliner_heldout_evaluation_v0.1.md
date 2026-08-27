# Scientific Entity GLiNER Held-Out Evaluation v0.1

## Status

```text
checkpoint = completed bounded held-out generalization gate
heldout_review_id = scientific-entity-heldout-review-v0.1-20260827T092900455472Z
heldout_evaluation_id = scientific-entity-evaluation-v0.1-20260827T113112815887Z
bounded_working_extractor_accepted = true
production_extractor_selected = false
full_corpus_build_authorized = false
canonical_truth_mutated = false
next_authorized_slice = structured held-out error analysis / extractor v0.2 design
```

This checkpoint closes the first independent held-out evaluation for the frozen
Scientific Entity GLiNER policy. It is a bounded model-development decision,
not a production promotion and not authorization for a full-corpus entity run.

## Frozen candidate under test

The held-out run uses the same pinned GLiNER candidate and the same policy that
were selected on the earlier 24-paper development evidence:

```text
model = gliner-community/gliner_small-v2.5
policy origin calibration = scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z
selected trial = calibration-trial:1172aea9d875d59f3b39cc21488dec8f
title threshold = 0.55 inclusive
abstract threshold = 0.65 inclusive
entity-type overrides = none
```

No threshold tuning, label/prompt change, or model selection was performed on
the held-out sample.

## Held-out evidence

The held-out sample is disjoint from the 24-paper development package and was
annotated prediction-blind before the model was run:

```text
held-out papers = 48
annotation rows = 96
reference mentions = 881
uncertain reference mentions = 0
dev overlap = 0
prediction blind = true
reference package validator = 4444 / 4444 required checks
```

Reference support by type:

| Type | References |
|---|---:|
| task | 175 |
| method | 303 |
| dataset | 56 |
| metric | 94 |
| model | 185 |
| domain | 68 |

All six types exceed the evaluation harness minimum of 20 reference mentions.

## Held-out prediction materialization

The one held-out GLiNER inference produced an immutable raw build:

```text
raw build id = scientific-entity-gliner-small-v2.5-v0.1-20260827T111030652864Z
documents = 48
raw predictions = 1145
raw build validator = 91 / 91 required checks
```

The already-frozen source-field policy was then applied without model inference
or tuning:

```text
held-out policy build id = scientific-entity-gliner-small-v2.5-heldout-frozen-policy-v0.1-20260827T112658493807Z
input predictions = 1145
selected predictions = 787
rejected predictions = 358
model inference during policy materialization = false
threshold tuning = false
held-out references mutated = false
policy build validator = 4762 / 4762 required checks
```

## Independent held-out evaluation

Evaluation:

```text
evaluation id = scientific-entity-evaluation-v0.1-20260827T113112815887Z
documents = 48
references = 881
predictions = 787
evaluation validator = 69 / 69 required checks
```

Overall micro metrics:

| Matching | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Exact | 331 | 456 | 550 | 0.420584 | 0.375709 | 0.396882 |
| Relaxed | 346 | 441 | 535 | 0.439644 | 0.392736 | 0.414868 |

Development-policy reproduction for comparison:

| Matching | Dev F1 | Held-out F1 | Delta |
|---|---:|---:|---:|
| Exact | 0.380146 | 0.396882 | +0.016736 |
| Relaxed | 0.404358 | 0.414868 | +0.010510 |

The held-out result shows no observed generalization collapse. The frozen
source-field policy transfers to the new disjoint evidence and remains a viable
bounded baseline.

## Source-field metrics

| Field | Exact P | Exact R | Exact F1 | Relaxed F1 |
|---|---:|---:|---:|---:|
| title | 0.467391 | 0.390909 | 0.425742 | 0.435644 |
| abstract | 0.414388 | 0.373541 | 0.392906 | 0.412005 |

The held-out title result is weaker than the earlier dev title result, while the
abstract result is stronger. The overall policy remains viable, but field-level
behavior is not treated as fully stable.

## Per-type held-out metrics

| Type | Exact P | Exact R | Exact F1 | Relaxed F1 | Interpretation |
|---|---:|---:|---:|---:|---|
| model | 0.507937 | 0.518919 | 0.513369 | 0.529412 | strongest current type |
| method | 0.429603 | 0.392739 | 0.410345 | 0.431035 | usable bounded baseline |
| task | 0.519231 | 0.308571 | 0.387097 | 0.408602 | precision-oriented; recall-limited |
| dataset | 0.324324 | 0.428571 | 0.369230 | 0.369230 | recall reasonable; precision weak |
| domain | 0.280000 | 0.308824 | 0.293707 | 0.307692 | weak |
| metric | 0.250000 | 0.180851 | 0.209877 | 0.234568 | weakest current type |

The extractor is therefore not accepted as an equally mature six-type
production system. `metric` and `domain` need targeted investigation; `task`
is notably recall-limited.

## Error structure

The evaluation emits 808 structural error records:

```text
false_negative = 352
false_positive = 258
type_mismatch = 176
boundary_mismatch = 22
```

Boundary errors are a small minority; the dominant residual problems are
missing entities, extra entities, and semantic typing.

The largest type-confusion pairs are:

```text
model -> method = 55
method -> task = 28
domain -> method = 14
method -> metric = 11
task -> method = 11
dataset -> method = 9
```

`method` is the predicted destination for 94 of 176 type mismatches, so it acts
as a semantic sink for ambiguous scientific mentions. The strongest single
confusion remains `model -> method`, consistent with the earlier dev pilot.

## Decision

Accepted decision:

```text
heldout_generalization_gate = passed
candidate_decision = accept_as_bounded_working_extractor_v0.1
production_extractor_selected = false
full_corpus_build_authorized = false
normalization_linking_over_all_six_types_authorized = false
```

The v0.1 extractor is now a stable bounded baseline for model-development and
error-analysis work. The independent held-out evidence is sufficient to show
that the dev policy did not collapse, but it also exposes material per-type
weaknesses that should be addressed before large-scale entity materialization
or product integration.

## Next authorized slice

The next slice is structured held-out error analysis, not threshold retuning and
not full-corpus extraction:

```text
frozen v0.1 baseline
-> structured review of type confusions / FP / FN
-> choose one bounded v0.2 hypothesis
-> new candidate identity and evidence
-> future new disjoint held-out sample for v0.2 acceptance
```

Priority diagnostic families:

1. `model -> method` semantic confusion;
2. `method -> task` semantic confusion;
3. low `metric` precision and recall;
4. weak `domain` extraction / possible document-level framing;
5. `task` recall.

Possible v0.2 hypotheses may include improved GLiNER label descriptions,
deterministic type-specific postfilters, a separate metric extraction component,
or a second-stage type/rejection classifier. No one of these is selected by
this checkpoint.

Because these 48 papers are now used for error analysis, they remain valid
held-out evidence for the v0.1 decision but must be treated as development
/error-analysis evidence for any v0.2 candidate designed from their errors.
