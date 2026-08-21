# Bounded Scientific Entity Manual Review Evidence v0.1

## Status

```text
implementation_status = preparation/finalization tooling implemented
acceptance_scope = deterministic synthetic fixture and end-to-end integration
real_paper_review_prepared = false
real_paper_review_complete = false
real_quality_claim_available = false
prediction_blind = true
production_extractor_selected = false
full_corpus_build_authorized = false
canonical_truth_changed = false
redistribution_authorized = false
publication_ready = false
```

This slice closes the tooling gap between the accepted Scientific Entity
Evaluation Harness v0.1 and a future real-paper candidate benchmark. It creates
a bounded, deterministic sample from canonical title/abstract text, prepares a
prediction-blind annotation package, converts completed human annotations into
extractor-independent reference mentions, and validates the entire chain
independently.

The tracked fixture proves the workflow. It does **not** provide empirical
quality evidence for the real 61,075-paper corpus. Real-paper sample text,
working annotations, and completed review packages remain local generated data
under ignored `data/entities/` paths and must not be committed.

---

## Why this layer exists

The synthetic evaluation harness proves metric and matching semantics, but its
numbers cannot answer whether an extractor is useful on real papers. A real
benchmark must first have reference annotations whose creation was not
influenced by the extractor predictions being evaluated.

The accepted sequence is therefore:

```text
current canonical paper truth
→ deterministic bounded sample
→ prediction-blind title/abstract annotation
→ extractor-independent reference mentions
→ existing bounded extractor candidate
→ existing evaluation harness
→ descriptive quality evidence
→ separate human acceptance decision
```

No step in this line mutates canonical paper truth or becomes a reconciliation
input.

---

## Tracked implementation

```text
configs/scientific_entity_manual_review_evidence_v0.1.yaml
docs/scientific_entity_manual_review_evidence_v0.1.md
radar_core/contracts/scientific_entity_manual_review.py
radar_core/entities/scientific_entity_manual_review.py
scripts/entities/build_scientific_entity_manual_review_evidence.py
scripts/validation/check_scientific_entity_manual_review_evidence.py
tests/fixtures/scientific_entity_manual_review_evidence_v0_1/*
tests/smoke/test_scientific_entity_manual_review_contract.py
tests/smoke/test_scientific_entity_manual_review_builder.py
tests/smoke/test_scientific_entity_manual_review_validation.py
```

The builder owns package creation. The validator independently reloads the
source input and recomputes selection, identity, spans, counts, hashes, and
safety fields; it does not trust builder summaries.

---

## Sampling contract

The candidate sample contains 24 distinct papers:

| Stratum | Target | Purpose |
|---|---:|---|
| Uniform | 12 | Estimate behavior on a small unbiased canonical slice |
| Type-enriched: task | 2 | Increase the chance of task evidence |
| Type-enriched: method | 2 | Increase the chance of method evidence |
| Type-enriched: dataset | 2 | Increase the chance of dataset evidence |
| Type-enriched: metric | 2 | Increase the chance of metric evidence |
| Type-enriched: model | 2 | Increase the chance of model evidence |
| Type-enriched: domain | 2 | Increase the chance of domain evidence |

The uniform and type-enriched strata must always be reported separately. The
enriched stratum is deliberately biased and must not be presented as an
unbiased corpus-level quality estimate.

Selection is deterministic:

```text
algorithm = deterministic_hash_uniform_and_type_enriched_v0.1
seed = ml-research-radar-scientific-entity-manual-review-v0.1
eligibility = non-empty canonical title and abstract
enrichment matching = Unicode word, case-insensitive
selection score = SHA-256(seed + stratum + type + canonical_id)
duplicates across strata = forbidden
truncation = forbidden
```

Type-enrichment terms are sampling cues only. Their presence does not create a
reference annotation and is never treated as ground truth.

Hard safety limits:

```text
default maximum scanned source documents = 100,000
hard maximum scanned source documents = 250,000
hard maximum selected documents = 32
hard maximum annotation rows = 64
hard maximum reference mentions = 5,000
```

Candidate mode accepts only the configured current canonical path:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

The manifest pins its raw SHA-256, document count, semantic configuration hash,
code revision/fingerprint, dependency environment, sample hash, assignments,
and annotation template.

---

## Prediction-blind review contract

The prepared annotation template contains canonical identity, sampling stratum,
source field, exact source text, and source-text hash. It contains no extractor
name, prediction span, score, confidence, evaluation result, or suggested
mention.

The reviewer must:

1. copy `annotation_template.jsonl` to a separate local working file;
2. avoid opening any prediction build until annotation is complete;
3. inspect every selected `title` and `abstract` row;
4. set `annotation_complete=true` even when the row has no mentions;
5. record every accepted mention with type, half-open Unicode offsets, and the
   exact source slice;
6. use `uncertain=true` and a reviewer note when a decision needs later
   adjudication;
7. finalize only after every expected row is complete.

The schema is fail-closed and rejects extra keys. This prevents predictions or
model metadata from being silently added to the blind annotation file.

---

## Annotation guidelines v0.1

All spans use zero-based Unicode code-point offsets with a half-open interval
`[char_start, char_end)`. `source_text[char_start:char_end]` must equal
`surface_text` exactly.

General rules:

- annotate the smallest complete phrase that identifies the scientific entity;
- exclude leading determiners and trailing punctuation unless they are part of
  an official name;
- preserve the exact casing and spelling from the source text;
- annotate a long form and its acronym separately when they occupy separate
  spans and each is independently meaningful;
- a span may receive different contextual types only when the sentence truly
  supports both readings; duplicate records for the same type and span are
  forbidden;
- do not infer entities that are absent from the exact title/abstract text;
- generic words such as “model”, “method”, “dataset”, “task”, or “score” are not
  sufficient on their own unless the context makes them a specific entity;
- sampling cues are not pre-annotations.

Type guidance:

| Type | Include | Exclude |
|---|---|---|
| `task` | A named problem or capability being solved, such as `named entity recognition` or `machine translation` | A broad field, an implementation technique, or a generic use of “task” |
| `method` | An algorithm, training strategy, inference procedure, or technical approach, such as `contrastive learning` | A named model instance, a domain, or generic “our approach” |
| `dataset` | A named corpus, benchmark dataset, or evaluation resource, such as `CIFAR-10` | Generic “training data” unless it is the name of a defined resource |
| `metric` | A named quantitative evaluation measure, including necessary qualifiers, such as `macro F1 score` | A raw result value without a named measure, or generic “performance” |
| `model` | A named architecture, system, or model variant, such as `BERT` | A generic algorithmic technique better represented as `method` |
| `domain` | A research or application area, such as `medical imaging` | A concrete prediction task within that area |

Ambiguous cases should be marked uncertain rather than resolved from memory or
from a model prediction.

---

## Immutable local packages

Preparation writes a new review-ID directory with exactly seven files:

```text
canonical_documents.sample.jsonl
sample_assignments.jsonl
annotation_template.jsonl
manifest.json
data_quality_summary.json
README.md
checksums.txt
```

Finalization writes a separate immutable directory with exactly seven files:

```text
completed_annotations.jsonl
review_manifest.json
reference_mentions.jsonl
completion_manifest.json
annotation_audit_summary.json
README.md
checksums.txt
```

`completed_annotations.jsonl` is a validated, LF-normalized copy of the human
working file. Keeping it inside the ignored immutable package makes completion
evidence self-contained and prevents later edits to the working file from
silently changing validation input.

Both commands are plan-only by default. Writes require `--execute`; an existing
directory is never overwritten and there is no mutable `latest` pointer.

Prepared evidence explicitly states:

```text
prediction_blind = true
review_complete = false
selection_terms_are_reference_annotations = false
```

Completed evidence explicitly states:

```text
review_status = reviewed_candidate
prediction_blind = true
review_complete = true
evaluation_harness_ready = true
automatic_review_approval = false
production_extractor_selected = false
full_corpus_build_authorized = false
publication_ready = false
```

`evaluation_harness_ready=true` means only that the files satisfy the input
contract of the existing harness. It is not an extractor acceptance decision.

---

## Fixture acceptance evidence

The tracked synthetic fixture exercises the complete preparation/finalization
workflow:

```text
fixture source documents = 8
fixture uniform documents = 2
fixture type-enriched documents = 6
fixture annotation rows = 16
fixture reference mentions = 6
independent prepared-package checks = 61 / 61
independent completed-package checks = 118 / 118
new direct smoke test functions = 40
```

The fixture was also integrated locally with the existing literal baseline and
evaluation harness:

```text
prediction documents = 8
prediction mentions = 6
reference mentions = 6
exact matches = 6
evaluation structural errors = 0
evidence-build validator = 89 / 89
evaluation validator = 69 / 69
```

These synthetic values demonstrate compatibility and validator independence.
They are not real-paper precision/recall estimates.

---

## Operator workflow

### 1. Verify the synthetic workflow

Plan mode is safe and writes nothing:

```bat
python -m scripts.entities.build_scientific_entity_manual_review_evidence prepare
```

Use a fresh temporary output root for an executable fixture rehearsal:

```bat
python -m scripts.entities.build_scientific_entity_manual_review_evidence prepare ^
  --output-root data/entities/scientific_entity_manual_review/v0.1/rehearsal/prepared ^
  --execute
```

Copy the printed prepared directory and finalize the tracked completed fixture
annotations with a fresh completed root:

```bat
python -m scripts.entities.build_scientific_entity_manual_review_evidence finalize ^
  --prepared-dir <PREPARED_DIR> ^
  --annotations tests/fixtures/scientific_entity_manual_review_evidence_v0_1/completed_annotations.jsonl ^
  --annotator-id synthetic-fixture ^
  --output-root data/entities/scientific_entity_manual_review/v0.1/rehearsal/completed ^
  --execute
```

Validate both immutable packages:

```bat
python -m scripts.validation.check_scientific_entity_manual_review_evidence ^
  --prepared-dir <PREPARED_DIR> ^
  --completed-dir <COMPLETED_DIR> ^
  --strict ^
  --no-write-reports
```

### 2. Prepare the real bounded sample

First inspect the plan:

```bat
python -m scripts.entities.build_scientific_entity_manual_review_evidence prepare ^
  --status candidate ^
  --input data/analytics/reconciled/canonical_documents.jsonl
```

Record the generated `review_id`, then execute that exact ID once:

```bat
python -m scripts.entities.build_scientific_entity_manual_review_evidence prepare ^
  --status candidate ^
  --input data/analytics/reconciled/canonical_documents.jsonl ^
  --review-id <REVIEW_ID> ^
  --execute
```

Treat the source canonical file, semantic config, core dependency lock, and
review code as frozen until finalization and validation finish. The manifests
pin all four. If a canonical refresh or relevant code/config change occurs
during annotation, validation fails closed; prepare a fresh review ID and do
not silently reuse the stale package.

Validate the prepared package before annotation:

```bat
python -m scripts.validation.check_scientific_entity_manual_review_evidence ^
  --prepared-dir <PREPARED_DIR> ^
  --strict ^
  --no-write-reports
```

### 3. Annotate locally and finalize

Copy `annotation_template.jsonl` outside the immutable prepared directory,
complete all rows according to this document, and keep predictions closed.
Then run finalize in plan mode, inspect the report, and repeat with `--execute`:

```bat
python -m scripts.entities.build_scientific_entity_manual_review_evidence finalize ^
  --prepared-dir <PREPARED_DIR> ^
  --annotations <COMPLETED_ANNOTATIONS_JSONL> ^
  --annotator-id <LOCAL_ANNOTATOR_ID>
```

```bat
python -m scripts.entities.build_scientific_entity_manual_review_evidence finalize ^
  --prepared-dir <PREPARED_DIR> ^
  --annotations <COMPLETED_ANNOTATIONS_JSONL> ^
  --annotator-id <LOCAL_ANNOTATOR_ID> ^
  --execute
```

Run the independent validator again with both directories. Do not continue to
predictions or evaluation unless it reports `required_failed_count=0`.

### 4. Run the existing baseline and evaluation harness

Use `canonical_documents.sample.jsonl` as the bounded prediction input. Create
a fresh immutable prediction build, validate it, then pass:

```text
documents = canonical_documents.sample.jsonl
review manifest = completed/review_manifest.json
reference mentions = completed/reference_mentions.jsonl
prediction manifest = prediction/manifest.json
prediction mentions = prediction/mentions.jsonl
status = candidate
```

to `scripts.entities.evaluate_scientific_entity_evidence`. Run its independent
validator before interpreting any metric. Exact and relaxed metrics must be
reported for the uniform and type-enriched evidence context; no aggregate from
this small biased sample is a corpus-level quality claim.

---

## Acceptance gates for the real review run

The next operational checkpoint requires all of the following:

- candidate input path is the current canonical latest file;
- source and sample hashes are pinned and independently verified;
- exactly 12 uniform and 12 type-enriched documents are selected;
- all 48 title/abstract rows are explicitly complete;
- prediction-blind schema contains no prediction/model fields;
- every reference span matches the exact source slice;
- prepared and completed package validators are green;
- baseline prediction build and existing evaluation validator are green;
- metrics and errors are reviewed separately by type, source field, and sample
  stratum context;
- real review evidence is recorded as descriptive, not accepted-model proof;
- no raw real-paper text or local annotator identity is committed.

Only a later candidate-benchmark slice may define comparison and promotion
thresholds.

---

## Non-goals and safety boundary

```text
no automatic annotation
no automatic review approval
no model or tokenizer download
no provider API access
no production extractor selection
no full-corpus entity extraction
no canonical or reconcile mutation
no Postgres/retrieval/Qdrant/graph/API/UI integration
no redistribution or publication
no committed real-paper review text
```

Dataset publication remains paused pending explicit redistribution guidance.

---

## Next slice

The immediate next action is **Bounded Real-Paper Scientific Entity Manual
Review Execution v0.1**: run this accepted tooling against the current canonical
file, annotate the 24-paper sample prediction-blind, validate the completed
evidence, and run the existing baseline/evaluation harness.

Only after that real descriptive evidence is reviewed should the project open a
separate **Candidate Scientific Entity Extractor Benchmark v0.1** slice. New
models, full-corpus extraction, normalization/linking, and product integration
remain deferred.
