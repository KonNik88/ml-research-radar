# Scientific Entity Evidence Contract v0.1

## 1. Purpose and status

This document defines the first executable contract for scientific-entity
mention evidence in ML Research Radar.

```text
status = contract_only
layer = derived_mention_evidence
canonical_truth_changed = false
model_selected = false
model_weights_downloaded = false
full_corpus_output_generated = false
```

The contract prepares a future extraction layer for six entity families:

```text
task
method
dataset
metric
model
domain
```

It defines identity, span, provenance, confidence, build-compatibility, output,
and validation semantics before any extractor is promoted.

The executable model is:

```text
radar_core/contracts/scientific_entity_evidence.py
```

The machine-readable policy is:

```text
configs/scientific_entity_evidence.yaml
```

---

## 2. Architectural boundaries

The project invariant remains:

```text
canonical_documents.jsonl = paper truth
scientific entity evidence = rebuildable derived evidence
```

Scientific entity evidence must never become a second paper truth or a
reconciliation input.

```text
canonical_id = paper identity
mention_id = exact typed span identity
evidence_id = extractor-specific observation identity
future entity_id = normalized/linked entity identity, not defined in v0.1
```

Hard boundaries:

```text
may_be_used_as_reconcile_input = false
may_add_fields_to_canonical_document = false
may_mutate_canonical_corpus = false
may_generate_full_corpus_output = false
may_download_model_weights = false
may_select_production_model = false
may_change_postgres_schema = false
may_change_retrieval_behavior = false
may_change_qdrant_behavior = false
may_change_graph_behavior = false
may_change_api_behavior = false
may_change_streamlit_behavior = false
may_publish_output = false
```

This contract does not reinterpret existing `concepts`, `keywords`, artifact
links, topic clusters, or graph nodes as accepted extracted entities.

---

## 3. Layer placement and staged semantics

The accepted conceptual sequence is:

```text
canonical title / abstract
→ typed mention extraction
→ mention evidence validation
→ mention normalization
→ optional entity linking
→ paper–entity evidence
→ accepted product and graph consumers
```

v0.1 stops at the validated mention-evidence contract. It intentionally does
not define a canonical scientific-entity registry.

The distinction matters:

```text
"BERT" at title[0:4] as model
= mention evidence

"BERT" normalized to one global entity node
= future normalization/linking decision
```

Classic BIO/IOB tags are an extractor representation, not the storage
contract. Any future token-level extractor must convert its output into exact
character spans before evidence is accepted.

---

## 4. Identity domains

### 4.1 Canonical paper identity

`canonical_id` is copied from the exact canonical paper used as input.

It is not generated or repaired by the entity layer.

### 4.2 Mention identity

`mention_id` identifies an exact entity type and exact span in one version of a
canonical text field.

Identity payload:

```text
namespace = scientific_entity_mention_v0.1
parts =
  canonical_id
  source_field
  source_text_sha256
  char_start
  char_end
  entity_type
hash = sha256(canonical JSON payload)[:32]
format = mention:<32 lowercase hex characters>
```

The extractor is deliberately absent from `mention_id`.

Consequences:

```text
same paper + same field text + same span + same type
→ same mention_id across extractors

same span + different contextual type
→ different mention_id

changed source text
→ changed source_text_sha256
→ changed mention_id

unrelated paper changed elsewhere in corpus
→ mention_id remains stable
```

The global canonical-corpus fingerprint is not part of `mention_id`; otherwise
an unrelated refresh would churn every entity mention ID.

### 4.3 Extraction-evidence identity

`evidence_id` identifies one extractor/config observation of one mention.

```text
namespace = scientific_entity_extraction_evidence_v0.1
parts = mention_id + extractor_fingerprint
hash = sha256(canonical JSON payload)[:32]
format = evidence:<32 lowercase hex characters>
```

An extractor, configuration, or runtime-environment change must change
`extractor_fingerprint` and therefore `evidence_id`, while leaving a
semantically identical `mention_id` unchanged.

Repeated output with the same `evidence_id` but different semantic record
content inside one build is a determinism conflict and must fail closed. A
different `build_id` alone does not redefine mention or evidence identity.

### 4.4 Future normalized entity identity

`mention_id` and `evidence_id` are not global entity identifiers.

Entity normalization and linking require a separate contract because aliases,
versions, datasets, benchmark suites, model families, and contextual ambiguity
cannot be resolved safely from string normalization alone.

---

## 5. Scientific entity taxonomy

| Type | Definition | Positive examples | Common exclusions |
|---|---|---|---|
| `task` | Research objective, prediction problem, or evaluation task. | image classification, machine translation, named entity recognition | generic “task”, an application domain without a concrete objective |
| `method` | Algorithmic technique, procedure, or methodological approach. | contrastive learning, beam search, knowledge distillation | generic “approach”, a named model used as a system instance |
| `dataset` | Named or contextually identifiable dataset, corpus, or benchmark data resource. | ImageNet, SQuAD, GLUE data | generic “data”, an evaluation metric, a task name without data-resource meaning |
| `metric` | Named evaluation measure. | F1 score, BLEU, mean average precision | a bare numeric result, generic “accuracy” when it does not denote the measure |
| `model` | Named model, architecture, system, or checkpoint used as a model instance. | BERT, ResNet-50, GPT-4 | generic “model”, a general training technique |
| `domain` | Research or application area in which the work is situated. | medical imaging, computational biology, autonomous driving | a concrete task when the phrase denotes an objective rather than an area |

Taxonomy policies:

```text
exact_contextual_type_required = true
overlapping_mentions_allowed = true
same_span_multiple_types_allowed = true
ambiguous_mentions_may_be_omitted = true
generic_terms_without_specific_referent_excluded = true
```

`model` versus `method`, `task` versus `domain`, and `dataset` versus
`benchmark` must be decided from context. The contract does not force false
mutual exclusivity: the same character span may have multiple typed mention
records when an accepted annotation policy justifies it.

---

## 6. Source text and span semantics

v0.1 accepts only canonical:

```text
title
abstract
```

Provider `concepts`, `keywords`, `categories`, and `tags` may later serve as
weak supervision or comparison evidence, but they are not span sources in this
contract.

Offset semantics:

```text
offset_unit = Unicode code point
offset_base = 0
offset_interval = [char_start, char_end)
source_text = exact JSON-decoded canonical field string
normalization_before_offsets = forbidden
```

For every accepted mention:

```python
surface_text == source_text[char_start:char_end]
source_text_sha256 == sha256(source_text.encode("utf-8")).hexdigest()
0 <= char_start < char_end <= len(source_text)
```

Offsets are not UTF-8 byte offsets, UTF-16 code units, token offsets, sentence
offsets, or offsets into lowercased/trimmed/Unicode-normalized text.

This exact policy is required for cross-platform reproducibility and for later
UI highlighting.

An absent canonical abstract produces no abstract mention records. Empty or
whitespace-only spans are forbidden.

---

## 7. Extractor provenance

Each build records one complete extractor descriptor:

| Field | Required | Meaning |
|---|---:|---|
| `schema_version` | yes | `scientific_entity_extractor_descriptor_v0.1` |
| `name` | yes | stable extractor family name |
| `version` | yes | extractor implementation/release version |
| `kind` | yes | rule, statistical model, language model, human annotation, or import |
| `code_revision` | yes | Git revision or immutable code reference |
| `config_sha256` | yes | exact extraction/configuration fingerprint |
| `environment_sha256` | yes | dependency lock/runtime environment fingerprint |
| `model_name` | model only | model identifier |
| `model_revision` | model only | immutable model revision |
| `model_artifact_sha256` | model only | local model artifact fingerprint |
| `model_license` | model only | reviewed model license identifier/text |

Allowed extractor kinds:

```text
rule_based
statistical_model
language_model
human_annotation
imported
```

For model-based extractors all four model-provenance fields are mandatory.
Recording only a mutable model name such as `latest` is insufficient.

`extractor_fingerprint` is the full SHA-256 of the descriptor serialized as
canonical JSON with sorted keys, compact separators, and explicit nulls.

The current contract fixture uses `human_annotation`. This does not select a
production extraction method.

---

## 8. Mention evidence record

Future `mentions.jsonl` contains one JSON object per extraction-evidence record.

| Field | Type | Contract |
|---|---|---|
| `schema_version` | string | exactly `scientific_entity_mention_evidence_v0.1` |
| `evidence_id` | string | deterministic extractor-specific evidence identity |
| `mention_id` | string | deterministic extractor-independent typed span identity |
| `build_id` | string | immutable build directory / manifest identity |
| `canonical_id` | string | existing paper identity |
| `entity_type` | enum | one of the six accepted types |
| `source_field` | enum | `title` or `abstract` |
| `source_text_sha256` | SHA-256 | exact source-field text fingerprint |
| `char_start` | integer | inclusive zero-based Unicode code-point offset |
| `char_end` | integer | exclusive Unicode code-point offset |
| `surface_text` | string | exact source slice |
| `extractor_fingerprint` | SHA-256 | descriptor fingerprint from manifest |
| `confidence_kind` | enum | explicit score semantics |
| `confidence_score` | number/null | normalized score in `[0, 1]`, not automatically a probability |
| `calibration_id` | string/null | required only for calibrated probability |

Extra fields are forbidden in v0.1. Contract evolution must be explicit via a
new schema version.

The record intentionally omits:

```text
normalized_entity_name
global_entity_id
knowledge_base_id
paper_entity_edge
```

Those belong to future normalization/linking layers.

---

## 9. Confidence semantics

Allowed values:

| Kind | Score | Interpretation |
|---|---|---|
| `not_available` | must be null | no numeric confidence is claimed |
| `rule_score` | required, `[0,1]` | normalized rule evidence strength, not probability |
| `model_score` | required, `[0,1]` | model-specific normalized score, not probability |
| `calibrated_probability` | required, `[0,1]` | calibrated probability tied to `calibration_id` |

Policies:

```text
model_score_is_not_probability = true
rule_score_is_not_probability = true
calibrated_probability_requires_calibration_id = true
thresholds_belong_to_extractor_config = true
```

The contract forbids silently labelling a softmax/logit-derived score as a
calibrated probability.

---

## 10. Build manifest and canonical compatibility

Every future output build must contain `manifest.json` validated by
`ScientificEntityEvidenceManifest`.

Required canonical input evidence:

```text
canonical corpus path
canonical corpus SHA-256
canonical document count
CanonicalDocument contract name
```

Required build evidence:

```text
build_id
status = fixture | candidate | accepted
generated_at_utc with UTC offset +00:00
extractor descriptor and fingerprint
offset semantics
declared source fields
declared entity types
mentions.jsonl SHA-256 and record count
safety flags
```

The contract deliberately does not hardcode the current corpus count. The
project-state checkpoint records `61,075`, but each future entity build must pin
the exact canonical file it actually consumed.

Compatibility rules:

```text
manifest canonical SHA-256 mismatch = incompatible build
record source_text_sha256 mismatch = stale or corrupt mention
record build_id mismatch = incompatible record
record extractor fingerprint mismatch = incompatible record
undeclared source field or entity type = incompatible record
mixed canonical inputs in one build = forbidden
```

A newer canonical refresh does not automatically invalidate every unchanged
`mention_id`, but it does make the old build manifest non-current until an
explicit compatibility/rebuild decision is made.

---

## 11. Future immutable output layout

Expected root:

```text
data/entities/scientific_entity_evidence/v0.1/<build_id>/
```

Expected files:

```text
mentions.jsonl
manifest.json
schema.json
data_quality_summary.json
README.md
checksums.txt
```

Policy:

```text
build directory = immutable
mutable latest pointer = not required
generated output committed to Git = false by default
generated output ignore rule = /data/entities/
contract slice generates output = false
encoding = UTF-8
line ending = LF
record key order = executable contract field order
source field order = title, abstract
record sort = canonical_id, source field order, char_start, char_end,
              entity_type, evidence_id
```

`schema.json` will be generated from the accepted executable Pydantic contract
by a future builder. It must not become a competing handwritten schema.

`status = accepted` means that an internal derived-evidence build passed its
own gates. It does not mean `publication_ready = true` and does not authorize
upload or redistribution.

---

## 12. Deterministic synthetic fixture

The contract includes a synthetic fixture covering all six entity types.

```text
tests/fixtures/scientific_entity_evidence_v0_1/canonical_documents.jsonl
tests/fixtures/scientific_entity_evidence_v0_1/extractor.json
tests/fixtures/scientific_entity_evidence_v0_1/manifest.json
tests/fixtures/scientific_entity_evidence_v0_1/mentions.jsonl
```

Fixture requirements:

```text
synthetic data only
synthetic paper rows validate against CanonicalDocument
all six entity types represented
title and abstract spans represented
exact span reconstruction passes
source text hashes pass
mention and evidence IDs pass
extractor fingerprint passes
manifest count and file hashes pass
duplicate identity conflicts absent
```

The fixture validates the contract, not extractor quality.

---

## 13. Validation requirements

Validator entrypoint:

```bat
python -m scripts.validation.check_scientific_entity_evidence_contract --strict
```

The validator must check:

```text
config schema/status/taxonomy
executable Pydantic models and enums
documented identity and safety markers
exact source-field and span semantics
extractor provenance requirements
confidence semantics
manifest/canonical compatibility fields
future-layout-only output policy
synthetic fixture integrity
identity determinism and collision absence
```

Reports:

```text
artifacts/reports/validation/scientific_entity_evidence_contract_latest.json
artifacts/reports/validation/scientific_entity_evidence_contract_latest.md
artifacts/reports/validation/history/scientific_entity_evidence_contract_<timestamp>.json
artifacts/reports/validation/history/scientific_entity_evidence_contract_<timestamp>.md
```

Reports are generated evidence, not source truth, and are not committed by
default.

Strict validation fails when any required check fails.

---

## 14. Fail-closed conditions

The following are required failures:

```text
unknown entity type or source field
invalid or out-of-range span
surface/source-slice mismatch
source text hash mismatch
mention ID mismatch
evidence ID mismatch
extractor fingerprint mismatch
missing model provenance for a model-based extractor
unlabelled confidence semantics
calibrated probability without calibration evidence
duplicate ID with conflicting content
fixture manifest/file count or hash mismatch
unsafe contract flag
full-corpus output claimed by the contract-only slice
```

Overlapping spans and same-span multi-type records are not failures by
themselves.

---

## 15. Explicit non-goals

This slice does not:

```text
choose spaCy, SciSpacy, GLiNER, DyGIE++, a transformer, or an LLM
download any model or tokenizer
benchmark extraction quality
create a gold corpus beyond contract fixtures
process the 61,075-paper corpus
normalize aliases into global entities
link entities to external knowledge bases
add paper–entity graph edges
add Postgres tables
add Discovery API/UI facets
change canonical, retrieval, Qdrant, graph, ranking, or publication state
```

Model/library selection before a reviewed evaluation harness would harden an
unmeasured implementation choice and is therefore deferred.

---

## 16. Next bounded slice

The next slice after this contract is:

```text
Bounded Scientific Entity Extractor Baseline v0.1
```

That slice should:

```text
consume only synthetic and small curated paper fixtures
use the accepted mention/manifest models
provide a deterministic adapter boundary
emit candidate evidence only
avoid full-corpus generation
avoid production model claims
prepare exact/relaxed span evaluation
```

Only after bounded review/evaluation may the project select a model and design
an accepted full derived entity build.

---

## 17. Acceptance decision

Scientific Entity Evidence Contract v0.1 is accepted when:

```text
config validator = green
executable contract tests = green
synthetic fixture validation = green
required_failed_count = 0
canonical/reconcile/runtime/publication boundaries = preserved
```

Acceptance authorizes the bounded extractor-baseline slice only. It does not
authorize model promotion, full-corpus processing, entity linking, runtime
integration, or publication.
