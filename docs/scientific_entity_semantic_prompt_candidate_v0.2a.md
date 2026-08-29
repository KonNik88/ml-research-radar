# Scientific Entity Semantic Prompt Candidate v0.2a

Status: **completed controlled development comparison / hard guardrail failed / candidate not accepted**

## Purpose

This slice freezes the first bounded Scientific Entity v0.2 improvement hypothesis
selected by the completed v0.1 held-out error analysis.

The v0.1 extractor already uses semantic GLiNER-facing labels. The v0.2a hypothesis
is therefore **not** “add semantic labels”; it is:

```text
existing semantic prompts
→ more discriminative semantic prompts
```

The goal is to reduce semantic class confusion while changing as little else as
possible.

## Evidence basis

The decision is grounded in:

```text
v0.1 held-out evaluation:
scientific-entity-evaluation-v0.1-20260827T113112815887Z

v0.1 held-out error analysis:
scientific-entity-heldout-error-analysis-v0.1-20260828T121239202063Z
```

Dominant observed confusions:

```text
model -> method = 55
method -> task = 28
method predicted-type sink = 94 / 176 type mismatches
```

Representative high-score errors included `Recurrent Neural Networks` as
`method`, and `domain adaptation` / `population-based training` as `task`.
This makes another global threshold retune a poor first intervention.

## Frozen prompt delta

| Canonical type | v0.1 prompt | v0.2a prompt |
|---|---|---|
| task | `machine learning task or research objective` | `machine learning task, prediction problem, or learning objective` |
| method | `machine learning method or algorithm` | `algorithm, training procedure, optimization method, or computational technique` |
| dataset | `dataset corpus or benchmark` | `named dataset, benchmark dataset, corpus, or data collection` |
| metric | `evaluation metric` | `quantitative metric, score, measured property, or efficiency measure` |
| model | `model architecture or named system` | `named machine learning or statistical model, neural network, or model architecture` |
| domain | `research or application domain` | `research field, scientific domain, application area, or data domain` |

The canonical output taxonomy remains unchanged:

```text
task / method / dataset / metric / model / domain
```

## Controlled-change contract

The candidate runtime remains pinned to the same:

```text
model = gliner-community/gliner_small-v2.5
revision = f227d3cd637bd4e6757ae143935316d062393341
model artifact SHA-256 = d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74
GLiNER = 0.2.28
raw inference threshold = 0.5
window size = 320 WordsSplitter tokens
window overlap = 64
flat_ner = false
multi_label = false
```

The first comparison also keeps the previously frozen source-field policy:

```text
title >= 0.55
abstract >= 0.65
entity-type overrides = none
```

No threshold recalibration is part of v0.2a’s first comparison.

## Development evidence boundary

The v0.2a development pool is:

```text
old DEV = 24 papers
consumed v0.1 held-out = 48 papers
combined development evidence = 72 papers
```

Report all three views separately:

```text
old_dev_24
consumed_v01_heldout_48
combined_dev_72
```

The 48-paper package remains independent evidence for the already-frozen v0.1
candidate, but its errors have now informed v0.2a design. It therefore **must not**
be called independent held-out evidence for v0.2.

Any future v0.2 acceptance requires a new disjoint prediction-blind held-out sample.

## Pre-frozen development decision gate

The consumed-v0.1-heldout-48 baseline is:

```text
exact F1 = 0.396882
relaxed F1 = 0.414868
type mismatches = 176
model -> method = 55
method -> task = 28
method sink = 94
```

Before candidate inference, v0.2a is defined as **promising development evidence**
only if all hard guardrails pass:

```text
overall exact F1 >= 0.386882
model -> method <= 44
method -> task <= 28
total type mismatches <= 176
method predicted-type sink <= 84
no predicted-type mismatch sink > 94
```

These are development gates, not production or independent-acceptance criteria.
Directional improvements in `metric` F1, `domain` F1, `task` recall, `model` F1,
and relaxed F1 are desirable but not individually required by this first gate.

## Identity and lineage

Prompt/config changes are extractor changes.

Therefore:

```text
new runtime config SHA required
new extractor identity required
new extractor fingerprint required
new build_id required
same span/type/source text -> same mention_id
new extractor fingerprint -> new evidence_id
immutable output directory
no overwrite
```

The existing v0.1 evidence is never rewritten.

## Safety boundary

This contract slice performs:

```text
no model inference
no threshold tuning
no canonical mutation
no reconcile input
no production selection
no full-corpus build
no publication
no medium-model comparison
no fine-tuning
no markup cleanup
```

## Next step

After this contract is validated, run exactly one bounded raw v0.2a inference over
the 72-paper development pool using the new runtime config. Then apply the unchanged
`0.55 / 0.65` policy and produce a controlled v0.1-vs-v0.2a comparison.

## Development package materialization before inference

The first executable v0.2a step does **not** create a new review or reuse the 48-paper
package as independent held-out evidence. It materializes one deterministic local
72-paper development package from the two already-consumed evidence sources:

```text
old_dev_24
+ consumed_v01_heldout_48
= combined_dev_72
```

The package builder follows the two source evaluation manifests, verifies their
canonical/reference hashes and frozen review lineage, requires zero canonical-id
overlap, and writes only:

```text
data/entities/scientific_entity_semantic_prompt_development/v0.2a/<package_id>/
├── canonical_documents.jsonl
├── split_membership.jsonl
├── manifest.json
├── README.md
└── checksums.txt
```

Important semantics:

```text
model inference = false
threshold tuning = false
canonical truth mutation = false
new annotation/review identity = false
independent v0.2 held-out evidence = false
```

The canonical-shaped rows are schema-validated but materialized from the original
source JSON payloads rather than re-serializing `CanonicalDocument` defaults. This
keeps the package byte-reproducible and prevents runtime default timestamps from
entering the development input.

### Real package runbook

```bat
set OLD_DEV_EVAL_ID=scientific-entity-evaluation-v0.1-20260823T124036780234Z
set OLD_DEV_EVAL_DIR=data\entities\scientific_entity_evaluation\v0.1\%OLD_DEV_EVAL_ID%

set CONSUMED_HELDOUT_EVAL_ID=scientific-entity-evaluation-v0.1-20260827T113112815887Z
set CONSUMED_HELDOUT_EVAL_DIR=data\entities\scientific_entity_evaluation\v0.1\%CONSUMED_HELDOUT_EVAL_ID%
```

Plan:

```bat
python -m scripts.entities.prepare_scientific_entity_semantic_prompt_development ^
  --old-dev-evaluation-dir %OLD_DEV_EVAL_DIR% ^
  --consumed-heldout-evaluation-dir %CONSUMED_HELDOUT_EVAL_DIR%
```

Freeze the emitted `package_id`, verify the target does not already exist, then execute:

```bat
set SEMANTIC_PROMPT_DEV_PACKAGE_ID=<package_id-from-plan>
set SEMANTIC_PROMPT_DEV_PACKAGE_DIR=data\entities\scientific_entity_semantic_prompt_development\v0.2a\%SEMANTIC_PROMPT_DEV_PACKAGE_ID%

python -m scripts.entities.prepare_scientific_entity_semantic_prompt_development ^
  --old-dev-evaluation-dir %OLD_DEV_EVAL_DIR% ^
  --consumed-heldout-evaluation-dir %CONSUMED_HELDOUT_EVAL_DIR% ^
  --package-id %SEMANTIC_PROMPT_DEV_PACKAGE_ID% ^
  --execute

python -m scripts.validation.check_scientific_entity_semantic_prompt_development ^
  --package-dir %SEMANTIC_PROMPT_DEV_PACKAGE_DIR% ^
  --strict
```

Required result:

```text
old_dev_document_count = 24
consumed_heldout_document_count = 48
combined_document_count = 72
source_split_overlap_count = 0
model_inference_executed = false
threshold_tuning_executed = false
next_slice = bounded_raw_candidate_inference_on_72_development_documents
```

### Raw v0.2a inference after the package is validated

Reuse the existing bounded GLiNER builder with the frozen v0.2a runtime config. No
parallel inference implementation is introduced.

Plan first:

```bat
python -m scripts.entities.build_scientific_entity_evidence_gliner ^
  --config configs\scientific_entity_gliner_semantic_prompt_candidate_v0.2a.yaml ^
  --input %SEMANTIC_PROMPT_DEV_PACKAGE_DIR%\canonical_documents.jsonl ^
  --status candidate ^
  --max-documents 72
```

Freeze the emitted raw `build_id`, then execute against the already-verified local model
cache without enabling downloads:

```bat
set SEMANTIC_PROMPT_RAW_BUILD_ID=<build-id-from-plan>
set SEMANTIC_PROMPT_RAW_BUILD_DIR=data\entities\scientific_entity_evidence\v0.1\%SEMANTIC_PROMPT_RAW_BUILD_ID%

python -m scripts.entities.build_scientific_entity_evidence_gliner ^
  --config configs\scientific_entity_gliner_semantic_prompt_candidate_v0.2a.yaml ^
  --input %SEMANTIC_PROMPT_DEV_PACKAGE_DIR%\canonical_documents.jsonl ^
  --build-id %SEMANTIC_PROMPT_RAW_BUILD_ID% ^
  --status candidate ^
  --max-documents 72 ^
  --execute
```

Then validate using the same v0.2a runtime config:

```bat
python -m scripts.validation.check_scientific_entity_gliner_build ^
  --build-dir %SEMANTIC_PROMPT_RAW_BUILD_DIR% ^
  --config configs\scientific_entity_gliner_semantic_prompt_candidate_v0.2a.yaml ^
  --strict ^
  --no-write-reports
```

The following slice will apply the unchanged `title >= 0.55 / abstract >= 0.65`
policy in a deterministic development comparison and report old-dev-24,
consumed-heldout-48, and combined-dev-72 views separately.

## Materialized v0.2a raw development evidence

The frozen 72-paper development package was materialized as:

```text
package_id = scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z
old_dev_document_count = 24
consumed_heldout_document_count = 48
combined_document_count = 72
source_split_overlap_count = 0
```

The semantic-prompt raw candidate was then run once with the pinned small-v2.5
model and materialized as:

```text
build_id = scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z
input_document_count = 72
raw_prediction_count = 1430
raw_threshold = 0.50
GLiNER build validator = 91 / 91 required checks
```

Controlled identity verification against the prior v0.1 raw held-out build:

```text
old_extractor_fingerprint = df5fec8a0036db042990f5fdd74dbfb2cb63f788fb967add567a726d29ecea1c
new_extractor_fingerprint = 3e890253263ca3e5d7fa06e9a731205b020ec1251123b8aa1926a696180e48c0
fingerprint_changed = true

old_runtime_config_sha256 = 1ff31b24dca7afb7388aafcd88dd13cefacb55f7f8f03ae1b35a04762813d427
new_runtime_config_sha256 = a51897e984a0d7d9189ec23373f0e8fc00f5887c2fed917d8eb6c0eb7145c2dd
runtime_config_sha_changed = true

same_model = true
same_model_revision = true
same_model_artifact = true
```

This confirms the intended controlled experiment: model weights and revision are
unchanged, while the prompt-bearing runtime config and extractor identity are new.

## Unchanged policy materialization

The next bounded slice is policy filtering only. It does **not** invoke GLiNER again.
It applies the same source-field policy frozen for v0.1:

```text
input threshold = 0.50
title >= 0.55
abstract >= 0.65
entity-type overrides = none
```

The policy-aware output receives a new extractor fingerprint/evidence identity while
preserving each selected `mention_id`, model score, and source span. The raw v0.2a
build remains immutable.

Plan:

```bat
python -m scripts.entities.build_scientific_entity_semantic_prompt_policy ^
  --parent-build-dir %SEMANTIC_PROMPT_RAW_BUILD_DIR% ^
  --development-package-dir %SEMANTIC_PROMPT_DEV_PACKAGE_DIR%
```

Freeze the emitted build id, verify the target does not exist, then execute and
validate:

```bat
set SEMANTIC_PROMPT_POLICY_BUILD_ID=<build-id-from-plan>
set SEMANTIC_PROMPT_POLICY_BUILD_DIR=data\entities\scientific_entity_semantic_prompt_policy\v0.2a\%SEMANTIC_PROMPT_POLICY_BUILD_ID%

python -m scripts.entities.build_scientific_entity_semantic_prompt_policy ^
  --parent-build-dir %SEMANTIC_PROMPT_RAW_BUILD_DIR% ^
  --development-package-dir %SEMANTIC_PROMPT_DEV_PACKAGE_DIR% ^
  --build-id %SEMANTIC_PROMPT_POLICY_BUILD_ID% ^
  --execute

python -m scripts.validation.check_scientific_entity_semantic_prompt_policy ^
  --build-dir %SEMANTIC_PROMPT_POLICY_BUILD_DIR% ^
  --parent-build-dir %SEMANTIC_PROMPT_RAW_BUILD_DIR% ^
  --development-package-dir %SEMANTIC_PROMPT_DEV_PACKAGE_DIR% ^
  --strict ^
  --no-write-reports
```

Only after this immutable policy build validates do we construct the controlled
`old_dev_24 / consumed_v01_heldout_48 / combined_dev_72` comparison artifact.

## Materialized unchanged-policy candidate evidence

The unchanged v0.1 source-field policy was materialized over the 72-paper v0.2a
raw build as:

```text
build_id = scientific-entity-semantic-prompt-policy-v0.2a-20260829T143901678616Z
parent_build_id = scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z
input_document_count = 72
input_prediction_count = 1430
selected_prediction_count = 977
rejected_prediction_count = 453
extractor_fingerprint_changed = true
title_threshold = 0.55
abstract_threshold = 0.65
model_inference_executed = false
threshold_tuning_executed = false
canonical_truth_mutated = false
full_corpus_build_authorized = false
strict_validator_required_failed_count = 0
```

This closes the policy materialization slice. The 977 selected predictions are now
the immutable candidate evidence used by the controlled comparison.

## Controlled comparison v0.2a

The next slice is read-only evaluation over three views of already-consumed development
evidence:

```text
old_dev_24
consumed_v01_heldout_48
combined_dev_72
```

The comparison reuses the existing scientific-entity evaluation matching semantics.
No new model inference and no threshold tuning occur.

The 48-paper view is the decision-gate view because its v0.1 baseline was frozen before
v0.2a prompt design. It is **development evidence for v0.2**, not an independent v0.2
held-out set.

Frozen hard guardrails:

```text
overall exact F1 >= 0.386882
model -> method <= 44
method -> task <= 28
total type mismatches <= 176
method semantic sink <= 84
any predicted-type mismatch sink <= 94
```

All hard guardrails must pass for v0.2a to be called promising for the next development
slice. Even a promising result is not production acceptance and does not authorize a
full-corpus build.

Plan:

```bat
python -m scripts.entities.compare_scientific_entity_semantic_prompt_candidate ^
  --development-package-dir %SEMANTIC_PROMPT_DEV_PACKAGE_DIR% ^
  --policy-build-dir %SEMANTIC_PROMPT_POLICY_BUILD_DIR% ^
  --parent-raw-build-dir %SEMANTIC_PROMPT_RAW_BUILD_DIR%
```

Freeze the emitted comparison id, verify the immutable target does not exist, then
execute and validate:

```bat
set SEMANTIC_PROMPT_COMPARISON_ID=<comparison-id-from-plan>
set SEMANTIC_PROMPT_COMPARISON_DIR=data\entities\scientific_entity_semantic_prompt_comparison\v0.2a\%SEMANTIC_PROMPT_COMPARISON_ID%

python -m scripts.entities.compare_scientific_entity_semantic_prompt_candidate ^
  --development-package-dir %SEMANTIC_PROMPT_DEV_PACKAGE_DIR% ^
  --policy-build-dir %SEMANTIC_PROMPT_POLICY_BUILD_DIR% ^
  --parent-raw-build-dir %SEMANTIC_PROMPT_RAW_BUILD_DIR% ^
  --comparison-id %SEMANTIC_PROMPT_COMPARISON_ID% ^
  --execute

python -m scripts.validation.check_scientific_entity_semantic_prompt_comparison ^
  --comparison-dir %SEMANTIC_PROMPT_COMPARISON_DIR% ^
  --development-package-dir %SEMANTIC_PROMPT_DEV_PACKAGE_DIR% ^
  --policy-build-dir %SEMANTIC_PROMPT_POLICY_BUILD_DIR% ^
  --parent-raw-build-dir %SEMANTIC_PROMPT_RAW_BUILD_DIR% ^
  --strict ^
  --no-write-reports
```

## Materialized controlled comparison and decision

The controlled comparison was materialized as:

```text
comparison_id = scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z
development_document_count = 72
reference_mention_count = 1316
candidate_prediction_count = 977
strict_validator_required_failed_count = 0
model_inference_executed = false
threshold_tuning_executed = false
canonical_truth_mutated = false
full_corpus_build_authorized = false
```

The split-level comparison is:

| Split | System | Exact P | Exact R | Exact F1 | Relaxed P | Relaxed R | Relaxed F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| old_dev_24 | v0.1 baseline | 0.322344 | 0.404598 | 0.358817 | 0.357143 | 0.448276 | 0.397554 |
| old_dev_24 | v0.2a | 0.449405 | 0.347126 | 0.391699 | 0.482143 | 0.372414 | 0.420234 |
| consumed_v01_heldout_48 | v0.1 baseline | 0.420584 | 0.375709 | 0.396882 | 0.439644 | 0.392736 | 0.414868 |
| consumed_v01_heldout_48 | v0.2a | 0.455538 | 0.331442 | 0.383706 | 0.488300 | 0.355278 | 0.411301 |
| combined_dev_72 | v0.1 baseline | 0.380345 | 0.385258 | 0.382786 | 0.405851 | 0.411094 | 0.408456 |
| combined_dev_72 | v0.2a | 0.453429 | 0.336626 | 0.386393 | 0.486182 | 0.360942 | 0.414304 |

The combined 72-paper view therefore moved in a precision-heavy direction:

```text
exact precision delta = +0.073084
exact recall delta = -0.048632
exact F1 delta = +0.003607

relaxed precision delta = +0.080331
relaxed recall delta = -0.050152
relaxed F1 delta = +0.005848
```

On the pre-frozen consumed-48 decision view:

```text
exact:
TP 331 -> 292
FP 456 -> 349
FN 550 -> 589
precision 0.420584 -> 0.455538
recall 0.375709 -> 0.331442
F1 0.396882 -> 0.383706

relaxed:
TP 346 -> 313
FP 441 -> 328
FN 535 -> 568
precision 0.439644 -> 0.488300
recall 0.392736 -> 0.355278
F1 0.414868 -> 0.411301
```

### Pre-frozen hard guardrails

| Guardrail | Threshold | Observed | Result |
|---|---:|---:|---|
| minimum overall exact F1 | `>= 0.386882` | `0.383706` | **FAIL** |
| maximum `model -> method` | `<= 44` | `31` | PASS |
| maximum `method -> task` | `<= 28` | `21` | PASS |
| maximum total type mismatches | `<= 176` | `125` | PASS |
| maximum method semantic sink | `<= 84` | `54` | PASS |
| maximum any predicted-type mismatch sink | `<= 94` | `54` | PASS |

Exactly one hard guardrail failed. Because the gate was frozen before inference,
the candidate is not reclassified post hoc:

```text
all_hard_guardrails_passed = false
candidate_promising_for_next_development_slice = false
candidate_accepted = false
production_extractor_selected = false
full_corpus_build_authorized = false
```

### Semantic-disambiguation signal

The semantic-prompt hypothesis nevertheless produced a strong intended typing effect
on the consumed-48 view:

```text
model -> method: 55 -> 31  (-24; -43.6%)
method -> task: 28 -> 21   (-7; -25.0%)
all type mismatches: 176 -> 125  (-51; -29.0%)
method semantic sink: 94 -> 54   (-40; -42.6%)
```

Per-type exact F1:

| Type | v0.1 | v0.2a | Delta |
|---|---:|---:|---:|
| task | 0.387097 | 0.366197 | -0.020900 |
| method | 0.410345 | 0.334038 | -0.076307 |
| dataset | 0.369230 | 0.352000 | -0.017230 |
| metric | 0.209877 | 0.197183 | -0.012694 |
| model | 0.513369 | 0.557545 | +0.044176 |
| domain | 0.293707 | 0.299065 | +0.005358 |

The desirable directional signals were mixed:

```text
metric exact F1: -0.012694
domain exact F1: +0.005358
task exact recall: -0.011428
model exact F1: +0.044176
overall relaxed F1: -0.003567
```

## Interpretation and next bounded hypothesis

v0.2a answers its controlled question:

> Do more discriminative prompts, with the old v0.1 source-field thresholds held
> fixed, produce a candidate that passes the pre-frozen development gate?

Answer: **no**.

The experiment also shows that semantic disambiguation improved substantially while
the unchanged-policy candidate became more precision-oriented and lost recall. That
pattern supports a new bounded hypothesis: the v0.1 `title 0.55 / abstract 0.65`
thresholds may no longer be appropriate for the changed v0.2a score distribution.

This is a hypothesis, not a post-hoc acceptance of v0.2a.

The next slice is therefore:

```text
Scientific Entity Semantic Prompt Threshold Calibration v0.2b

keep fixed:
- v0.2a prompts
- gliner-community/gliner_small-v2.5
- pinned model revision and artifact
- 320/64 adapter windowing
- six canonical output types
- evaluation/matching semantics

change:
- bounded source-field threshold policy only
```

Before threshold search, v0.2b must freeze:

- the calibration/search space;
- the optimization/selection rule;
- guardrails against trading away semantic-confusion gains;
- the exact development evidence inputs;
- the rule that these 72 papers remain development evidence only.

A fresh independent held-out set is **not** spent during v0.2b calibration. Any
future v0.2 acceptance still requires a new disjoint prediction-blind held-out sample.

No new model inference, medium-model experiment, fine-tuning, canonical cleanup,
full-corpus entity extraction, normalization, or production promotion is authorized
by the v0.2a result.
