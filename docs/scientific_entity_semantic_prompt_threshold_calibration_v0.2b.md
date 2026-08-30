# Scientific Entity Semantic Prompt Threshold Calibration v0.2b

Status: **completed bounded calibration / hard gate failed / raw-floor extension selected as next hypothesis**

## Purpose

v0.2a materially improved semantic type disambiguation but did not pass its
pre-frozen development gate under the inherited v0.1 source-field thresholds.
On the consumed 48-paper development view:

```text
model -> method: 55 -> 31
method -> task: 28 -> 21
type mismatches: 176 -> 125
method semantic sink: 94 -> 54

precision: 0.420584 -> 0.455538
recall:    0.375709 -> 0.331442
exact F1:  0.396882 -> 0.383706
```

The evidence suggests a precision/recall calibration problem rather than a need
to immediately change the model or prompts again. v0.2b therefore tests one
bounded hypothesis:

> Keep the v0.2a semantic prompts and pinned small-v2.5 runtime fixed, and
> recalibrate only title/abstract thresholds over the already-materialized raw
> v0.2a predictions.

This is development-time threshold-policy search. It is not probabilistic
calibration, does not reinterpret `model_score` as correctness probability, and
does not run GLiNER.

## Frozen lineage

```text
candidate_id = scientific-entity-semantic-prompt-candidate-v0.2a

development_package_id =
scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z

raw_build_id =
scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z

raw_extractor_fingerprint =
3e890253263ca3e5d7fa06e9a731205b020ec1251123b8aa1926a696180e48c0

v0.2a comparison_id =
scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z

documents = 72
references = 1316
raw predictions = 1430
raw input score floor = 0.50 inclusive
```

The 72 papers are development evidence only:

```text
24 old DEV
+
48 consumed v0.1 held-out
=
72 v0.2 development papers
```

No fresh independent v0.2 held-out evidence is consumed by this slice.

## Search space

Only source-field thresholds are searched:

```text
title:
0.50, 0.525, 0.55, 0.575, 0.60

abstract:
0.50, 0.525, 0.55, 0.575, 0.60, 0.625, 0.65

5 x 7 = 35 trials
```

The inherited v0.2a policy `title=0.55 / abstract=0.65` is inside the grid and
acts as an explicit control trial.

Thresholds below `0.50` are forbidden because the existing raw v0.2a build was
materialized with an inclusive `0.50` input floor. If the selected policy lands
on either `0.50` boundary, the artifact records `raw_input_floor_may_be_binding`
instead of extrapolating below available evidence.

Entity-type overrides are forbidden in v0.2b.

## Semantic-safe eligibility

A trial may participate in policy selection only if the consumed-48 diagnostics
retain at least a substantial share of the v0.2a semantic-disambiguation gain:

```text
model -> method <= 43
method -> task <= 25
total type mismatches <= 150
method semantic sink <= 74
maximum any predicted-type mismatch sink <= 74
```

An ineligible trial cannot win by F1 alone.

## Deterministic selection

Among eligible trials:

```text
1. maximize combined_dev_72 exact F1
2. maximize combined_dev_72 relaxed F1
3. maximize combined_dev_72 exact recall
4. prefer larger title + abstract threshold sum
5. prefer larger title threshold
6. prefer larger abstract threshold
7. trial_id ascending
```

The final strictness tie-break prevents a lower threshold from winning when all
quality metrics are exactly tied.

## Development decision gate

The selected trial is not automatically accepted.

Hard requirements are:

```text
consumed-48 exact F1 >= 0.396882
combined-72 exact F1 >= 0.386393
all semantic guardrails pass
```

The consumed-48 relaxed F1 `>= 0.414868` is tracked as a desirable signal rather
than a hard requirement.

If all hard gates pass, the next slice may materialize the selected v0.2b policy
and run a controlled comparison before freezing a candidate. If they fail, the
threshold hypothesis is rejected rather than tuning indefinitely.

## Safety boundary

```text
model inference = forbidden
model/tokenizer download = forbidden
prompt changes = forbidden
model changes = forbidden
entity-type threshold overrides = forbidden
canonical mutation = forbidden
reconcile input = forbidden
provider API calls = forbidden
fresh held-out consumption = forbidden
production selection = false
full-corpus build = false
publication = false
```

Future independent v0.2 acceptance still requires a new disjoint,
prediction-blind held-out sample after a promising candidate is frozen.

## Immutable output

Execution writes one immutable directory:

```text
data/entities/scientific_entity_semantic_prompt_threshold_calibration/v0.2b/<calibration_id>/
├── manifest.json
├── trials.jsonl
├── selected_policy.json
├── diagnostics.json
├── README.md
└── checksums.txt
```

Plan mode runs the bounded deterministic threshold search but writes no artifact.
The independent validator recomputes the full artifact byte-for-byte from the
frozen inputs.


## Materialized calibration result

The bounded search was executed and materialized as:

```text
calibration_id =
scientific-entity-semantic-prompt-threshold-calibration-v0.2b-20260830T093225845167Z

documents = 72
references = 1316
raw predictions = 1430

trials = 35
semantic-safe eligible trials = 10

selected trial =
calibration-trial:05df528b9ef88cd383ce1c8f02e3b23e

selected title threshold = 0.50
selected abstract threshold = 0.625

selected combined-72 exact F1 = 0.398654
selected consumed-48 exact F1 = 0.396453

selected model -> method = 32
selected method -> task = 25
selected total type mismatches = 138
selected method semantic sink = 57

all_hard_gates_passed = false
candidate_promising_for_future_freeze = false
raw_input_floor_may_be_binding = true

strict validator = 53 / 53
```

No model inference, prompt changes, fresh-held-out consumption, canonical mutation,
or full-corpus authorization occurred during calibration.

## Hard-gate decision

The selected trial passed the combined-development and semantic-safety gates:

```text
combined-72 exact F1:
observed = 0.398654
required >= 0.386393
PASS

semantic guardrails:
PASS
```

It missed the consumed-48 exact-F1 gate:

```text
observed = 0.396453
required >= 0.396882
difference = -0.000429
FAIL
```

The desirable consumed-48 relaxed-F1 signal passed:

```text
observed = 0.419252
required >= 0.414868
PASS
```

The frozen decision therefore remains:

```text
candidate accepted = false
candidate_promising_for_future_freeze = false
production_extractor_selected = false
full_corpus_build_authorized = false
```

The consumed-48 exact-F1 threshold is not relaxed after seeing the result.

## Eligible-trial landscape

The ten semantic-safe eligible trials were:

| Title | Abstract | Combined exact F1 | Consumed-48 exact F1 | Combined exact recall | model->method | method->task | Type mismatches | Method sink |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.500 | 0.625 | 0.398654 | 0.396453 | 0.360182 | 32 | 25 | 138 | 57 |
| 0.525 | 0.625 | 0.396290 | 0.393651 | 0.357143 | 32 | 25 | 138 | 57 |
| 0.550 | 0.625 | 0.394759 | 0.392357 | 0.354863 | 32 | 25 | 136 | 57 |
| 0.600 | 0.625 | 0.394581 | 0.391832 | 0.354103 | 32 | 25 | 135 | 57 |
| 0.575 | 0.625 | 0.394247 | 0.391582 | 0.354103 | 32 | 25 | 135 | 57 |
| 0.500 | 0.650 | 0.390455 | 0.387982 | 0.341945 | 31 | 21 | 127 | 54 |
| 0.525 | 0.650 | 0.387995 | 0.385069 | 0.338906 | 31 | 21 | 127 | 54 |
| 0.550 | 0.650 | 0.386393 | 0.383706 | 0.336626 | 31 | 21 | 125 | 54 |
| 0.600 | 0.650 | 0.386195 | 0.383147 | 0.335866 | 31 | 21 | 124 | 54 |
| 0.575 | 0.650 | 0.385857 | 0.382894 | 0.335866 | 31 | 21 | 124 | 54 |

At fixed `abstract=0.625`, reducing the title threshold improves recall and F1
throughout the observed grid while the key semantic-confusion counts remain stable:

```text
title 0.600 -> 0.575 -> 0.550 -> 0.525 -> 0.500
consumed-48 F1:
0.391832 -> 0.391582 -> 0.392357 -> 0.393651 -> 0.396453

model -> method = 32 throughout
method -> task = 25 throughout
method sink = 57 throughout
```

The best eligible title threshold is therefore exactly the lowest title threshold
observable in the existing raw evidence: `0.50`.

## Why abstract lowering is not the next hypothesis

The `title=0.50` family shows a different trade-off when the abstract threshold
is lowered:

| Abstract | Eligible | Combined exact F1 | Consumed-48 exact F1 | Combined recall | model->method | method->task | Type mismatches | Method sink |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| 0.500 | no | 0.396941 | 0.402846 | 0.414134 | 33 | 36 | 173 | 60 |
| 0.525 | no | 0.399850 | 0.405618 | 0.405015 | 33 | 35 | 169 | 61 |
| 0.550 | no | 0.402617 | 0.409430 | 0.397416 | 33 | 33 | 163 | 60 |
| 0.575 | no | 0.399208 | 0.403561 | 0.382979 | 33 | 32 | 158 | 59 |
| 0.600 | no | 0.400654 | 0.401227 | 0.372340 | 32 | 28 | 146 | 58 |
| 0.625 | yes | 0.398654 | 0.396453 | 0.360182 | 32 | 25 | 138 | 57 |
| 0.650 | yes | 0.390455 | 0.387982 | 0.341945 | 31 | 21 | 127 | 54 |

Lower abstract thresholds can recover the consumed-48 F1 gate, but they do so by
violating the pre-frozen semantic-safe eligibility rule, especially the
`method -> task <= 25` guardrail. The guardrail is not weakened post hoc.

This separates two effects:

```text
lower abstract threshold:
recall/F1 up
semantic confusion also up
not selected

lower title threshold at abstract=0.625:
recall/F1 up
observed semantic counts stable
selected policy reaches raw title floor
```

## Decision and next bounded hypothesis

v0.2b answers its controlled question:

> Can source-field threshold recalibration, within the already-available raw
> v0.2a evidence floor of 0.50, recover the required quality while preserving
> semantic-disambiguation gains?

Answer: **no** under the pre-frozen hard gate.

However, the search does not support the broader claim that the threshold/raw-score
hypothesis is exhausted. The deterministic optimum lands on the minimum observable
title threshold, and the title-threshold trajectory improves F1 without observed
semantic-count regression.

The next bounded hypothesis is therefore:

```text
Scientific Entity Semantic Prompt Raw-Floor Extension v0.2c
```

v0.2c should keep fixed:

```text
- v0.2a semantic prompts
- gliner-community/gliner_small-v2.5
- pinned revision and model artifact
- 320/64 adapter windowing
- six canonical entity types
- 72-paper consumed development evidence
- reference mentions and evaluation/matching semantics
- semantic-safety guardrails
```

and change only the evidence boundary required to test lower title thresholds:

```text
raw inference score floor < 0.50
```

The v0.2c contract must be frozen before inference. It should specify the lower raw
floor, bounded title-threshold search, any diagnostic abstract controls, selection
rule, and hard decision criteria before new predictions are generated.

A fresh independent held-out sample remains reserved for a later frozen promising
v0.2 candidate.

No medium-model experiment, fine-tuning, canonical cleanup, full-corpus extraction,
or production promotion is authorized by v0.2b.
