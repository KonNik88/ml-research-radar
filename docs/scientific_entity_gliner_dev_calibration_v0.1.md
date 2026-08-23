# Bounded Scientific Entity GLiNER Dev Calibration v0.1

## Status

```text
implementation = complete
tracked fixture = deterministic and green
real 24-paper candidate execution = complete
real calibration id = scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z
real calibration strict validation = 53 / 53 required checks
dev policy review = complete / balanced_f1 selected
dev policy review record = docs/scientific_entity_gliner_dev_policy_review_v0.1.md
production extractor selected = false
full-corpus entity build authorized = false
current 24-paper package becomes held-out evidence = false
canonical truth mutated = false
```

This layer performs bounded threshold-policy development over one already-built,
immutable GLiNER prediction set. It does not load GLiNER, run inference, download
a model or tokenizer, call a provider API, or change any source text, reference
annotation, prediction row, canonical document, retrieval artifact, database, or
public API.

The word *calibration* here means **development-time threshold-policy search**.
It does not mean probabilistic calibration. Input mentions retain:

```text
confidence_kind = model_score
calibration_id = null
```

No output may reinterpret `confidence_score` as a probability of correctness.

---

## Why this slice exists

The first frozen 24-paper GLiNER run produced:

```text
predictions = 546
references = 435
exact precision = 0.322344
exact recall = 0.404598
exact F1 = 0.358817
relaxed precision = 0.357143
relaxed recall = 0.448276
relaxed F1 = 0.397554
```

The candidate has useful recall but emits many false positives and type
confusions. The cheapest next control is to reuse the existing scores and test
bounded deterministic thresholds before changing prompts, rerunning a model,
or adding a second classifier.

This order preserves a clean evidence chain:

```text
frozen GLiNER prediction build
→ frozen baseline evaluation
→ deterministic threshold-policy trials
→ one explicitly reviewed dev policy
→ new immutable candidate build if semantics change
→ new disjoint prediction-blind review
```

---

## Inputs

The real local candidate run reuses these immutable inputs:

```text
review_id = scientific-entity-manual-review-v0.1-20260821T131320262656Z
review documents = 24
reference mentions = 435

prediction_build_id = scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z
prediction mentions = 546
input score floor = 0.50 inclusive

baseline_evaluation_id = scientific-entity-evaluation-v0.1-20260823T124036780234Z
baseline exact F1 = 0.358817
baseline relaxed F1 = 0.397554
```

The builder validates raw SHA-256 identities for the documents, review
manifest, references, prediction manifest, predictions, prediction quality
summary, baseline evaluation manifest, and baseline metrics. It also recomputes
the unfiltered baseline metrics before running any threshold trial.

The tracked fixture is synthetic. It exists only to prove contract behavior,
search determinism, immutability, and validation without committing real paper
text or local manual-review evidence.

---

## Search space

The v0.1 search is declared in
`configs/scientific_entity_gliner_dev_calibration_v0.1.yaml` and contains
exactly 127 trials:

| Stage | Policy | Trial count |
|---|---|---:|
| Baseline | global `0.50` | 1 |
| Global | `0.55` through `0.95`, step `0.05` | 9 |
| Source pair | title `0.50`–`0.80` × abstract `0.50`–`0.90` | 63 |
| Type probes | 6 types × `0.50`–`0.90` over the balanced source-pair base | 54 |
| Total | bounded declared search | 127 |

Threshold comparison is inclusive:

```text
retain prediction when confidence_score >= effective_threshold
```

Effective-threshold precedence is:

```text
entity-type override
→ source-field override
→ default threshold
```

The type-probe stage is diagnostic only. v0.1 intentionally forbids:

```text
full source_field × entity_type Cartesian policy search
combined per-type policy selection
automatic promotion from the best dev metric
```

This prevents a 24-document dev sample from silently producing a highly
parameterized policy that looks precise only because it overfits the sample.

Prompt variants and generic/cross-sentence rejection rules are not searched in
this fixed-prediction slice. Either change affects extraction semantics and must
receive a new config hash, extractor fingerprint, immutable prediction build,
and evaluation. A second-stage classifier remains deferred until threshold,
prompt, and deterministic-filter controls leave a measured bottleneck.

---

## Metrics and recommendations

Every trial reuses the existing exact/relaxed one-to-one matching contract and
records:

```text
micro exact and relaxed metrics
title and abstract metrics
all six per-type metrics
selected/rejected prediction counts
selected counts by field and type
F0.5 and F2 derived from exact and relaxed precision/recall
```

Profile selection is limited to baseline, global, and source-pair trials that
still emit at least one prediction for every contract type. The profiles are:

| Profile | Primary objective | Interpretation |
|---|---|---|
| `precision_oriented_f0_5` | exact F0.5 | precision-weighted dev option |
| `balanced_f1` | exact F1 | balanced dev option |
| `recall_oriented_f2` | exact F2 | recall-weighted dev option |

Ties are resolved deterministically by:

```text
primary objective descending
→ exact precision descending
→ exact recall descending
→ relaxed F1 descending
→ policy complexity ascending
→ trial_id ascending
```

The exact-precision/exact-recall Pareto frontier is emitted separately. Type
probes identify the best isolated threshold for each type and its exact per-type
F1 delta from the balanced source-pair base, but they cannot be combined or
selected as a profile in v0.1.

All recommendations are descriptive dev evidence. The three profile names do
not imply three accepted candidates, and they may legitimately point to the
same trial.

---

## Immutable output

Execution writes a new directory only:

```text
data/entities/scientific_entity_gliner_calibration/v0.1/<calibration_id>/
├── manifest.json
├── trials.jsonl
├── pareto_frontier.json
├── recommended_profiles.json
├── diagnostics.json
├── README.md
└── checksums.txt
```

There is no mutable `latest` pointer. Existing directories cannot be
overwritten. Plan mode is the default and writes no calibration directory.

The manifest explicitly records:

```text
confidence_scores_reinterpreted_as_probabilities = false
calibration_id_written_to_mentions = false
current_dev_set_becomes_held_out = false
metrics_are_descriptive_only = true
production_extractor_selected = false
canonical_truth_mutated = false
may_be_used_as_reconcile_input = false
model_inference_executed = false
model_downloaded = false
provider_api_called = false
full_corpus_build_authorized = false
publication_ready = false
```

---

## Local candidate run

Use the already validated local review, GLiNER build, and baseline evaluation.
In Anaconda Prompt:

```bat
set REVIEW_ID=scientific-entity-manual-review-v0.1-20260821T131320262656Z
set PREPARED_DIR=data\entities\scientific_entity_manual_review\v0.1\prepared\%REVIEW_ID%
set COMPLETED_DIR=data\entities\scientific_entity_manual_review\v0.1\completed\%REVIEW_ID%
set GLINER_BUILD_ID=scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z
set GLINER_BUILD_DIR=data\entities\scientific_entity_evidence\v0.1\%GLINER_BUILD_ID%
set BASELINE_EVALUATION_ID=scientific-entity-evaluation-v0.1-20260823T124036780234Z
set BASELINE_EVALUATION_DIR=data\entities\scientific_entity_evaluation\v0.1\%BASELINE_EVALUATION_ID%
```

First run plan mode:

```bat
python -m scripts.entities.calibrate_scientific_entity_gliner ^
  --documents %PREPARED_DIR%\canonical_documents.sample.jsonl ^
  --review-manifest %COMPLETED_DIR%\review_manifest.json ^
  --reference-mentions %COMPLETED_DIR%\reference_mentions.jsonl ^
  --prediction-build-dir %GLINER_BUILD_DIR% ^
  --baseline-evaluation-dir %BASELINE_EVALUATION_DIR% ^
  --status candidate ^
  --max-documents 24
```

Copy the emitted `calibration_id`, confirm its target directory does not exist,
then execute the identical request with that explicit identity:

```bat
set CALIBRATION_ID=<calibration_id from plan>
set CALIBRATION_DIR=data\entities\scientific_entity_gliner_calibration\v0.1\%CALIBRATION_ID%

python -c "from pathlib import Path; p=Path(r'%CALIBRATION_DIR%'); print('exists=',p.exists(),'path=',p.resolve())"

python -m scripts.entities.calibrate_scientific_entity_gliner ^
  --documents %PREPARED_DIR%\canonical_documents.sample.jsonl ^
  --review-manifest %COMPLETED_DIR%\review_manifest.json ^
  --reference-mentions %COMPLETED_DIR%\reference_mentions.jsonl ^
  --prediction-build-dir %GLINER_BUILD_DIR% ^
  --baseline-evaluation-dir %BASELINE_EVALUATION_DIR% ^
  --status candidate ^
  --max-documents 24 ^
  --calibration-id %CALIBRATION_ID% ^
  --execute
```

Validate the immutable result:

```bat
python -m scripts.validation.check_scientific_entity_gliner_calibration ^
  --calibration-dir %CALIBRATION_DIR% ^
  --strict ^
  --no-write-reports
```

The validator reloads every input, checks every raw hash and contract, verifies
LF/checksums, and rebuilds all 127 trials, profiles, Pareto output, diagnostics,
manifest, README, and checksum file in a temporary directory. Every emitted
byte must match.

To inspect the three recommendations:

```bat
python -c "import json; from pathlib import Path; p=Path(r'%CALIBRATION_DIR%\recommended_profiles.json'); print(json.dumps(json.loads(p.read_text(encoding='utf-8')),ensure_ascii=False,indent=2))"
```

To inspect type probes and the Pareto frontier:

```bat
python -c "import json; from pathlib import Path; d=Path(r'%CALIBRATION_DIR%'); print(json.dumps({'pareto':json.loads((d/'pareto_frontier.json').read_text(encoding='utf-8')),'diagnostics':json.loads((d/'diagnostics.json').read_text(encoding='utf-8'))},ensure_ascii=False,indent=2))"
```

---

## Real candidate execution and dev-policy decision

The local candidate execution completed with:

```text
calibration_id = scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z
status = candidate
documents = 24
references = 435
input predictions = 546
trials = 127
profile-eligible trials = 69
Pareto trials = 29
strict validator = 53 / 53 required checks
model inference = false
```

Human review selected the balanced exact-F1 source-field policy:

```text
selected_trial_id = calibration-trial:1172aea9d875d59f3b39cc21488dec8f
title threshold = 0.55 inclusive
abstract threshold = 0.65 inclusive
entity-type overrides = none
selected predictions = 391
exact precision = 0.401535
exact recall = 0.360920
exact F1 = 0.380146
relaxed precision = 0.427110
relaxed recall = 0.383908
relaxed F1 = 0.404358
```

The full decision rationale, Pareto interpretation, local threshold robustness,
per-type caveats, and freeze boundary are recorded in
[`scientific_entity_gliner_dev_policy_review_v0.1.md`](scientific_entity_gliner_dev_policy_review_v0.1.md).

---

## Acceptance boundary and next step

The calibration execution and human dev-policy review are complete. The frozen
policy is development-only and does not promote a production extractor.

The next safe sequence is:

1. preserve the original 546-mention prediction build unchanged;
2. materialize the frozen `title >= 0.55 / abstract >= 0.65` semantics under a
   new immutable candidate configuration/build identity;
3. validate and evaluate that derived candidate without reusing an old identity;
4. only after candidate semantics are frozen, prepare at least 32 new, disjoint,
   prediction-blind papers;
5. grow later stratified evidence before any full-corpus or future
   multi-million-paper production claim.

The current 24-paper review has informed tuning. It remains permanently dev
evidence and cannot later be relabeled as held-out evidence. Type probes remain
diagnostic only; no combined per-type policy is selected.
