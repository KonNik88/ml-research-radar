# Bounded Scientific Entity GLiNER Candidate Adapter v0.1

## Status

```text
status = immutable bounded candidate build validated; comparative evaluation pending
canonical truth mutation = false
full-corpus entity extraction = false
production extractor selected = false
candidate accepted = false
publication = false
```

Local runtime evidence:

```text
build_id = scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z
status = candidate
documents = 24
mentions = 546
model artifact verified = true
backbone config verified = true
backbone config injected = true
inference duration seconds = 2.095834
peak CUDA memory bytes = 419360768
independent build validation = 91 / 91 required checks
```

The immutable output is local and ignored by Git. These values establish that
the pinned adapter can execute and serialize valid evidence; they do not yet
measure extraction quality or select a production extractor.

This slice adds one bounded zero-shot candidate behind the existing Scientific
Entity Evidence Contract and Evaluation Harness. It does not replace the
literal v0.1 control, create another metric system, or authorize a full-corpus
run.

## Candidate decision

The frozen candidate is:

```text
model = gliner-community/gliner_small-v2.5
revision = f227d3cd637bd4e6757ae143935316d062393341
variant = fp16
artifact = model.fp16.safetensors
artifact bytes = 332065392
artifact SHA-256 = d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74
license = Apache-2.0
library = gliner==0.2.28
backbone config repository = microsoft/deberta-v3-small
backbone config revision = a36c739020e01763fe789b4b85e2df55d6180012
backbone config artifact = config.json
backbone config bytes = 578
backbone config SHA-256 = b0bb1caf90a50aa67d1085130508dfbf8646ac5a11928305e280b07a36e100ae
backbone config resolution = verified local config injection
initial threshold = 0.5
```

Why this candidate:

- it supports open-label span extraction without training a project-specific
  model before the evidence line is mature;
- its Apache-2.0 model license is compatible with bounded local evaluation;
- the small checkpoint fits the current RTX 2070 SUPER resource envelope;
- model, revision, FP16 artifact, auxiliary DeBERTa config, sizes, hashes,
  runtime and label prompts are frozen before looking at candidate results;
- it can emit exact offsets and uncalibrated model scores required by the
  existing evidence contract.

Primary references:

- [GLiNER model card](https://huggingface.co/gliner-community/gliner_small-v2.5)
- [GLiNER v0.2.28 release](https://github.com/urchade/GLiNER/releases/tag/v0.2.28)
- [official input-limit and windowing guidance](https://urchade.github.io/GLiNER/input_limits.html)

## Existing evidence reused

The first real comparison reuses the local development package:

```text
review_id = scientific-entity-manual-review-v0.1-20260821T131320262656Z
documents = 24
title/abstract rows = 48
reference mentions = 435
role = pilot/dev diagnostics only
```

The unchanged literal control remains:

```text
prediction_build_id = scientific-entity-literal-v0.1-20260822T114316573133Z
predictions = 30
exact F1 = 0.043012
relaxed F1 = 0.068818
```

No threshold, label wording or type policy may be tuned on the 24-paper
references and then described as held-out evidence. If the candidate is worth
freezing, a separate prediction-blind set of at least 32 documents is the next
quality slice.

## Contract mapping

| Contract type | Frozen GLiNER prompt |
|---|---|
| `task` | `machine learning task or research objective` |
| `method` | `machine learning method or algorithm` |
| `dataset` | `dataset corpus or benchmark` |
| `metric` | `evaluation metric` |
| `model` | `model architecture or named system` |
| `domain` | `research or application domain` |

The prompts are part of the semantic config fingerprint. Changing one creates a
different extractor fingerprint and requires a new candidate comparison.

`confidence_kind` is `model_score`. Scores are not calibrated probabilities;
`calibration_id` remains null.

## Long-input completeness

GLiNER stateless inference truncates inputs longer than `model.config.max_len`
to a prefix and does not return truncation metadata. The adapter therefore does
not call the model blindly on a long abstract.

The implemented policy is:

```text
public prepare_batch token maps
→ at most 320 splitter tokens per window
→ 64-token overlap
→ exact character offset shift back to source text
→ deduplicate (entity_type, char_start, char_end)
→ retain highest model score
```

The loaded model must report `model.config.max_len >= 320`, and overlap must be
at least `model.config.max_width - 1`. Any malformed label, score, offset,
surface, token map, artifact hash or truncation condition fails the build.

## Safety boundary

```text
default documents = 32
hard maximum documents = 100
input truncation = forbidden
current full canonical path = forbidden
allowed statuses = fixture, candidate
accepted status = forbidden
plan mode = default
project output write = explicit --execute only
model network download = explicit --allow-model-download only
overwrite = forbidden
mutable latest pointer = absent
provider inference API = absent
canonical/reconcile/publication use = forbidden
```

The adapter writes the same six-file immutable build layout as the literal
control, under a unique build ID:

```text
mentions.jsonl
manifest.json
schema.json
data_quality_summary.json
README.md
checksums.txt
```

## Auxiliary backbone configuration boundary

The first non-writing real plan resolved the pinned GLiNER snapshot and then
revealed a second runtime dependency: GLiNER `0.2.28` calls
`AutoConfig.from_pretrained("microsoft/deberta-v3-small")` while constructing
its encoder because the checkpoint does not embed `encoder_config`. A pinned
GLiNER weight file alone was therefore insufficient to prove offline
reproducibility.

The adapter now resolves the exact DeBERTa `config.json` revision explicitly,
checks its byte size and SHA-256, parses it as `deberta-v2`, and injects a fresh
`DebertaV2Config` built from those verified bytes only while GLiNER constructs
the model graph. The module-local resolver is protected by a lock, rejects any
other repository or resolver arguments, and is restored even if construction
fails. Candidate provenance records that the config was verified and injected;
the independent validator resolves the same cached revision offline and
rehashes it.

The diagnostic plan did not create a project build directory. Its generated
build ID must not be reused after this code/config hardening because the
extractor fingerprint has changed.

## Environment change

The environment preflight for `gliner==0.2.28` showed that the existing
`torch`, `transformers`, `huggingface_hub`, `numpy`, CUDA runtime and project
packages remain unchanged. Only these packages are added:

```text
gliner==0.2.28
onnxruntime==1.29.0
sentencepiece==0.2.2
flatbuffers==25.12.19
```

`onnxruntime` is the CPU runtime dependency pulled by GLiNER; it does not
replace PyTorch CUDA and the v0.1 adapter does not select the ONNX backend.

Before installation:

```bat
python -m pip freeze > D:\ML\ml_radar_before_gliner_20260822.txt
conda list --explicit > D:\ML\ml_radar_before_gliner_conda_20260822.txt
python -m pip check
```

Install the exact additive set:

```bat
python -m pip install gliner==0.2.28 onnxruntime==1.29.0 sentencepiece==0.2.2 flatbuffers==25.12.19
python -m pip check
```

Then confirm versions and existing smoke tests before downloading weights:

```bat
python -c "from importlib.metadata import version; print({p:version(p) for p in ['gliner','onnxruntime','sentencepiece','flatbuffers']})"
python -m pytest tests/smoke/test_scientific_entity_gliner_candidate_adapter.py tests/smoke/test_project_state_current_v02.py -q
python -m pytest tests/smoke -q
```

The before-install snapshots are recovery evidence. If pip unexpectedly changes
an existing dependency, stop before model download or project output creation.

## First real bounded run

Set the existing local pilot paths:

```bat
set REVIEW_ID=scientific-entity-manual-review-v0.1-20260821T131320262656Z
set PREPARED_DIR=data\entities\scientific_entity_manual_review\v0.1\prepared\%REVIEW_ID%
set SAMPLE_DOCUMENTS=%PREPARED_DIR%\canonical_documents.sample.jsonl
```

### 1. Explicit download plus non-writing plan

This call may mutate only the Hugging Face cache. It may download the pinned
GLiNER snapshot and the pinned DeBERTa `config.json`; it does not create a
project build directory because `--execute` is absent.

```bat
python -m scripts.entities.build_scientific_entity_evidence_gliner ^
  --input %SAMPLE_DOCUMENTS% ^
  --status candidate ^
  --max-documents 24 ^
  --allow-model-download
```

Record the printed `build_id`, inference duration, peak CUDA memory and mention
count. Both the model artifact and auxiliary backbone config are rehashed
before inference. The report must print
`model_artifact_verified=True`, `backbone_config_verified=True`, and
`backbone_config_injected=True`.

### 2. Local-only immutable execution

Use the exact build ID from the plan. Omit `--allow-model-download`; the second
call must succeed from the verified local cache.

```bat
set GLINER_BUILD_ID=<build-id-from-plan>
set GLINER_BUILD_DIR=data\entities\scientific_entity_evidence\v0.1\%GLINER_BUILD_ID%

python -m scripts.entities.build_scientific_entity_evidence_gliner ^
  --input %SAMPLE_DOCUMENTS% ^
  --status candidate ^
  --max-documents 24 ^
  --build-id %GLINER_BUILD_ID% ^
  --execute
```

An existing `%GLINER_BUILD_DIR%` causes `FileExistsError`; it is never replaced.

### 3. Independent validation

```bat
python -m scripts.validation.check_scientific_entity_gliner_build ^
  --build-dir %GLINER_BUILD_DIR% ^
  --strict ^
  --no-write-reports
```

For a candidate build the validator independently requires:

- exact six-file layout, LF and checksums;
- current contract/config/environment/code fingerprints;
- exact span, identity and confidence recomputation;
- pinned model metadata;
- locally cached artifact size and SHA-256;
- pinned DeBERTa config repository, revision, size and SHA-256;
- verified and injected backbone-config provenance from the build;
- independent offline rehash of the cached backbone config;
- no injected test backend;
- no canonical/reconcile/full-corpus/publication flags.

### 4. Existing evaluation harness

Use the completed review manifest/references and the candidate
`manifest.json`/`mentions.jsonl` with
`scripts.entities.evaluate_scientific_entity_evidence`. No new evaluator is
introduced. The resulting metrics are descriptive pilot/dev evidence.

## Acceptance boundary after the pilot

The real pilot can support one of three decisions:

1. reject GLiNER candidate and retain only the literal control;
2. revise/freeze a new candidate configuration, clearly marking the old dev
   comparison as tuning evidence;
3. freeze this configuration and create independent prediction-blind held-out
   evidence.

It cannot by itself authorize production selection, current-canonical
full-corpus extraction, API/UI integration, graph edges, RAG, or publication.
