# Scientific Entity Evaluation Harness v0.1

## 1. Purpose and status

```text
status = implemented bounded evaluation harness
layer_kind = derived_bounded_quality_evidence
canonical_truth_changed = false
runtime_behavior_changed = false
production_extractor_selected = false
full_corpus_build_authorized = false
publication_ready = false
```

This slice evaluates scientific-entity mention evidence against an explicit
reviewed reference set. It sits downstream of the Scientific Entity Evidence
Contract and Bounded Scientific Entity Extractor Baseline.

The harness answers a narrow question:

```text
Given one immutable canonical-shaped sample, one completed reference review,
and one immutable extractor-evidence build, what exact and relaxed mention
quality can be reproduced and independently validated?
```

It does not answer which production model should be selected and cannot
authorize full-corpus extraction.

---

## 2. Architectural position

```text
canonical_documents.jsonl = paper truth

bounded canonical-shaped sample
  + completed reference mentions
  + extractor prediction evidence
  + immutable manifests and hashes
        ↓
Scientific Entity Evaluation Harness
        ↓
descriptive metrics + matches + structural errors
```

Evaluation output is derived and rebuildable. It is not:

- canonical paper metadata;
- a reconciliation input;
- normalized global entity identity;
- a serving or product database;
- a model-promotion decision;
- a public dataset.

---

## 3. Executable components

```text
configs/scientific_entity_evaluation_v0.1.yaml
radar_core/contracts/scientific_entity_evaluation.py
radar_core/entities/scientific_entity_evaluation.py
scripts/entities/evaluate_scientific_entity_evidence.py
scripts/validation/check_scientific_entity_evaluation.py
```

The machine-readable policy owns matching, metric, safety, layout, fixture, and
validation boundaries. Pydantic contracts own reference, review, match, error,
metric, and evaluation-manifest schemas.

---

## 4. Inputs

The evaluator requires five immutable inputs:

```text
canonical_documents.jsonl
review_manifest.json
reference_mentions.jsonl
prediction_build/manifest.json
prediction_build/mentions.jsonl
```

The reference and prediction manifests must point to the same raw-byte
canonical input SHA-256 and document count. Every mention must use the same
canonical ID, source field, and source-text SHA-256 as that input.

Allowed source fields remain:

```text
title
abstract
```

Allowed entity types remain:

```text
task
method
dataset
metric
model
domain
```

---

## 5. Reference mention identity

A reference mention reuses the extractor-independent `mention_id` defined by
the Scientific Entity Evidence Contract:

```text
mention_id = hash(
  canonical_id,
  source_field,
  source_text_sha256,
  char_start,
  char_end,
  entity_type
)
```

The review-specific identity is:

```text
reference_id = hash(
  review_id,
  mention_id,
  annotation_method,
  annotation_pass
)
```

Reference identity does not contain an extractor fingerprint. The same exact
reviewed mention can therefore be compared with multiple extractor builds.

Supported annotation methods:

```text
synthetic_fixture
manual_independent
manual_adjudicated
```

Manual reference annotation in v0.1 must be prediction blind. Prediction-
assisted correction may be useful for diagnostics later, but it cannot silently
replace an independent recall reference.

---

## 6. Exact matching

An exact true positive requires equality of:

```text
canonical_id
source_field
source_text_sha256
entity_type
char_start
char_end
```

Exact matching is one-to-one. Duplicate reference IDs and duplicate prediction
evidence IDs fail closed before scoring.

---

## 7. Relaxed matching

Relaxed matching is intended to expose boundary quality without erasing type or
text-version errors.

Required equality:

```text
canonical_id
source_field
source_text_sha256
entity_type
```

Span criterion:

```text
character IoU = intersection_length / union_length
minimum character IoU = 0.5
```

Assignment policy:

```text
exact pairs are locked first
remaining candidates are sorted by:
  descending character IoU
  ascending boundary distance
  reference_id
  prediction evidence_id
each reference and prediction may be used once
```

The policy name is:

```text
deterministic_greedy_iou_desc_v0.1
```

It is deliberately explicit. Changing the threshold or assignment policy
changes evaluation semantics and requires a config fingerprint change.

---

## 8. Metrics

The harness reports exact and relaxed values for:

- micro precision, recall, and F1;
- every entity type;
- `title` and `abstract` separately;
- TP, FP, FN, reference support, and prediction support.

Undefined ratios are serialized as `null`, not silently converted to zero.
Scores are rounded to six decimal places after their denominators are fixed.

Data-sufficiency markers are also emitted:

```text
minimum documents = 32
minimum reference mentions per type = 20
```

Those markers do not create an automatic promotion gate. In v0.1:

```text
promotion_sample_sufficient = false
metrics_are_descriptive_only = true
```

This remains true even when raw counts happen to exceed the configured minima.
A later human decision must define production acceptance.

---

## 9. Automatic structural error evidence

The evaluator emits only categories that can be derived reproducibly from spans
and types:

```text
boundary_mismatch
type_mismatch
false_positive
false_negative
```

`boundary_mismatch` includes a relaxed-only match and an overlapping same-type
pair below the relaxed threshold. `type_mismatch` requires overlapping spans on
the same text identity with different entity types.

The evaluator does not pretend to infer semantic causes such as generic terms,
alias failures, or annotation uncertainty. Those remain optional manual labels:

```text
false_positive_generic_term
false_positive_lexical_ambiguity
missed_entity
wrong_entity_type
boundary_too_narrow
boundary_too_wide
alias_or_acronym_miss
dataset_model_ambiguity
task_domain_ambiguity
annotation_uncertainty
```

---

## 10. Plan and execute semantics

Safe plan:

```bash
python -m scripts.entities.evaluate_scientific_entity_evidence
```

Plan mode loads and validates all inputs, computes matching and metrics in
memory, resolves the intended output path, and writes nothing.

Tracked-fixture execution:

```bash
python -m scripts.entities.evaluate_scientific_entity_evidence \
  --evaluation-id scientific-entity-evaluation-fixture-v0.1 \
  --execute
```

Candidate execution will require explicit local paths and `--status candidate`.
The review manifest must have `reviewed_candidate` status and the prediction
manifest must have `candidate` status.

There is no `--force`. Existing evaluation directories are never overwritten.
Writes are staged in a new sibling temporary directory and atomically renamed.

---

## 11. Immutable output layout

```text
data/entities/scientific_entity_evaluation/v0.1/<evaluation_id>/
  manifest.json
  metrics.json
  per_type_metrics.json
  matches.jsonl
  errors.jsonl
  README.md
  checksums.txt
```

All generated text is UTF-8 without BOM, uses LF, and ends with LF. The checksum
file pins every other required file by raw-byte SHA-256.

The manifest pins:

- evaluation configuration SHA-256;
- canonical input path, SHA-256, and count;
- review manifest/reference paths, hashes, IDs, and counts;
- prediction manifest/mention paths, hashes, build ID, and extractor fingerprint;
- exact matching policy;
- output hashes and counts;
- all fail-closed safety flags.

Generated output remains ignored by Git.

---

## 12. Independent validation

Strict validation:

```bash
python -m scripts.validation.check_scientific_entity_evaluation \
  --evaluation-dir data/entities/scientific_entity_evaluation/v0.1/<evaluation_id> \
  --strict
```

The validator does not call the evaluator matching function. It independently:

- parses every contract;
- verifies the exact file layout and LF policy;
- verifies checksums and manifest output hashes;
- reloads canonical, review, and prediction inputs;
- recomputes source spans, mention/reference/evidence IDs, and input hashes;
- recomputes exact and relaxed one-to-one pairing;
- recomputes structural errors;
- recomputes micro, source-field, and per-type metrics;
- verifies all safety flags.

Reports are written to generated latest/history locations under:

```text
artifacts/reports/validation/
```

They are validation evidence, not source truth.

---

## 13. Deterministic synthetic fixture

Fixture root:

```text
tests/fixtures/scientific_entity_evaluation_v0_1/
```

The fixture contains four synthetic canonical-shaped documents, 18 reference
mentions, and 17 prediction mentions. It deliberately includes:

- 14 exact matches;
- one relaxed-only boundary match;
- one exact-span type mismatch;
- one unmatched false positive;
- two unmatched false negatives;
- overlapping references;
- same-span multiple entity types;
- all six entity types;
- both source fields.

Expected micro evidence:

```text
exact:   TP=14 FP=3 FN=4 precision=0.823529 recall=0.777778 F1=0.800000
relaxed: TP=15 FP=2 FN=3 precision=0.882353 recall=0.833333 F1=0.857143
```

The synthetic numbers validate the harness. They are not claims about real
corpus quality.

---

## 14. Safety limits

```text
default max documents = 32
hard max documents = 100
hard max reference mentions = 5000
hard max prediction mentions = 5000
truncation = forbidden
current canonical path = forbidden as direct evaluator input
model/tokenizer download = forbidden
provider API access = forbidden
canonical mutation = forbidden
reconcile-input use = forbidden
full-corpus authorization = false
redistribution = forbidden
publication = forbidden
```

The current canonical path is deliberately not accepted as a shortcut. A later
review-sample slice must create a bounded, manifest-pinned local sample first.

---

## 15. Acceptance gates

The harness is accepted only when:

```text
config and contracts = green
reference identity and span validation = green
fixture plan writes nothing
fixture execute creates exact seven-file layout
fixture expected metrics = exact match
one-to-one exact/relaxed matching = green
independent strict validator = green
metric corruption after internally consistent rehash = rejected
duplicate match after internally consistent rehash = rejected
missing error after internally consistent rehash = rejected
CRLF output = rejected
existing output overwrite = rejected
existing Evidence Contract and Baseline tests = green
project current-state tests = green
full smoke suite = green
```

Acceptance authorizes bounded manual-review evidence preparation only.

---

## 16. Explicit non-goals

This slice does not:

```text
create or publish a real-paper gold dataset
select or download a production NER model
benchmark model latency or memory
calibrate model confidence
normalize aliases or create global entity_id values
link entities to external knowledge bases
run extraction over 61,075 papers
materialize Postgres entity tables
add Discovery filters or paper-entity graph edges
modify canonical documents
authorize public redistribution
```

---

## 17. Authorized follow-on

The next bounded slice is:

```text
Bounded Scientific Entity Manual Review Evidence v0.1
```

It should create a local reproducible sample with separate uniform and
type-enriched strata, preserve raw real-paper text outside Git, perform
prediction-blind reference annotation, and feed the completed candidate review
into this evaluation harness.

Only after real bounded review evidence exists may the project design a
candidate extractor benchmark and evaluate model license, quality, latency,
memory, determinism, and provenance.
