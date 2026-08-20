# Bounded Scientific Entity Extractor Baseline v0.1

## 1. Status and purpose

```text
status = bounded deterministic reference implementation
contract = Scientific Entity Evidence Contract v0.1
extractor_kind = rule_based
output_status = fixture | candidate
production_model_selected = false
full_corpus_authorized = false
canonical_truth_changed = false
runtime_behavior_changed = false
publication_changed = false
```

This slice is the first executable producer of Scientific Entity Evidence v0.1.
Its purpose is to prove the adapter, identity, provenance, serialization,
bounded-build, and independent-validation paths before the project compares or
promotes any statistical or language model.

The literal matcher is deliberately a reference/control implementation. It is
not presented as a competitive NER system, a corpus-quality claim, or a model
selection decision.

---

## 2. Architectural boundary

The existing project invariant remains unchanged:

```text
canonical_documents.jsonl = paper truth

bounded literal extraction
→ exact typed mention evidence
→ immutable local build directory
→ independent build validation
→ later review/evaluation
```

The baseline may read exact canonical-shaped `title` and `abstract` strings.
It may not:

```text
modify canonical documents
be used as a reconciliation input
emit accepted status
process the current 61,075-paper canonical path
truncate an oversized input silently
download a model or tokenizer
call a provider API
write Postgres, retrieval, Qdrant, graph, API, or UI state
publish output
```

Generated local output remains under ignored `/data/entities/`.

---

## 3. Tracked implementation

```text
configs/scientific_entity_extractor_baseline_v0.1.yaml
radar_core/entities/scientific_entity_baseline.py
scripts/entities/build_scientific_entity_evidence_baseline.py
scripts/validation/check_scientific_entity_evidence_build.py
tests/fixtures/scientific_entity_extractor_baseline_v0_1/*
tests/smoke/test_scientific_entity_extractor_baseline.py
tests/smoke/test_scientific_entity_evidence_build.py
```

The accepted evidence contract remains in:

```text
radar_core/contracts/scientific_entity_evidence.py
configs/scientific_entity_evidence.yaml
docs/scientific_entity_evidence_contract_v0.1.md
```

The baseline consumes those models and identity functions. It does not create a
parallel mention schema.

---

## 4. Adapter boundary

Future extractors must be replaceable behind one small interface:

```python
extract(
    canonical_id,
    source_field,
    source_text,
) -> Sequence[MentionCandidate]
```

`MentionCandidate` contains only:

```text
entity_type
char_start
char_end
```

The builder, rather than the extractor adapter, owns:

```text
exact surface slicing
source_text_sha256
mention_id
evidence_id
build_id attachment
confidence representation
record ordering
manifest construction
serialization
```

This separation prevents a future spaCy, transformer, GLiNER, LLM, or imported
annotation adapter from redefining storage identity or build safety.

---

## 5. Literal reference matcher

The v0.1 matcher uses tracked literal rules for all six contract types:

```text
task
method
dataset
metric
model
domain
```

Rule semantics are explicit:

```text
literal term
entity type
case sensitivity
boundary mode = unicode_word | none
```

Default matching is case-sensitive with Unicode word boundaries. A rule may
explicitly opt into case-insensitive matching. Matches are made against the
original source string, and offsets always refer to that string.

The matcher:

```text
does not normalize source text
does not tokenize source text
preserves overlapping spans
preserves the same span under multiple entity types
rejects embedded substring matches under unicode_word boundaries
deduplicates identical typed spans deterministically
returns candidates in deterministic span/type order
```

The tracked lexicon exists to exercise the contract and tests. Editing it is an
extractor-configuration change and therefore changes `config_sha256`,
`extractor_fingerprint`, and `evidence_id`.

It does not change `mention_id` when the exact paper, source text, type, and span
remain the same.

---

## 6. Provenance

Every build creates one `ScientificEntityExtractorDescriptor`.

```text
name = stable literal baseline family
version = 0.1.0
kind = rule_based
code_revision = normalized source-bundle SHA-256
config_sha256 = SHA-256 of canonical semantic config JSON
environment_sha256 = SHA-256 of normalized dependency-lock text
model provenance fields = null
```

Cross-platform fingerprint policy is intentional:

- YAML configuration is parsed and serialized to canonical semantic JSON before
  hashing, so formatting and CRLF/LF differences do not redefine the extractor.
- tracked code files and the environment lock are normalized to LF for their
  logical-content fingerprints;
- canonical input and generated files retain raw-byte SHA-256 because their
  manifests/checksums describe exact files.

The code revision bundle covers the evidence contract, literal extractor, and
builder source. A change to any of them changes the extractor fingerprint.

---

## 7. Bounded input policy

Default safety limits:

```text
default_max_documents = 32
hard_max_documents = 100
truncation_allowed = false
current canonical path allowed = false
```

The builder reads at most `max_documents + 1` records before failing. It never
converts an oversized input into an undocumented first-N sample.

The safe default input is the tracked synthetic fixture. A separately prepared,
small local curated JSONL may be supplied with `--status candidate`, provided it
is within the hard bound. Such a sample remains local/untracked unless a later
license and review decision explicitly changes that policy.

`fixture` status is reserved for the tracked synthetic fixture. The builder
cannot emit `accepted` status.

---

## 8. CLI and mutation semantics

Safe plan:

```bash
python -m scripts.entities.build_scientific_entity_evidence_baseline
```

The command validates input/config, runs extraction in memory, computes
provenance and planned output paths, and writes nothing.

Tracked-fixture execution:

```bash
python -m scripts.entities.build_scientific_entity_evidence_baseline \
  --build-id scientific-entity-literal-fixture-v0.1 \
  --execute
```

Local curated candidate execution:

```bash
python -m scripts.entities.build_scientific_entity_evidence_baseline \
  --input path/to/local_curated_canonical_documents.jsonl \
  --status candidate \
  --max-documents 32 \
  --build-id scientific-entity-literal-candidate-v0.1 \
  --execute
```

There is no `--force`. If the target build directory already exists, execution
fails without changing it.

Writes are staged in a new sibling temporary directory and renamed only after
all files and checksums have been produced.

---

## 9. Immutable output layout

```text
data/entities/scientific_entity_evidence/v0.1/<build_id>/
├── mentions.jsonl
├── manifest.json
├── schema.json
├── data_quality_summary.json
├── README.md
└── checksums.txt
```

Serialization:

```text
encoding = UTF-8 without BOM
line ending = LF
JSONL offsets = zero-based Unicode code points
span interval = half-open [char_start, char_end)
record order = canonical_id, source field, start, end, type, evidence_id
mutable latest pointer = absent
```

`checksums.txt` pins every other file in the directory. The manifest separately
pins the exact canonical input path/hash/count and `mentions.jsonl` hash/count.

---

## 10. Data-quality summary

The build records:

```text
input and configured limit counts
processed source-text count
documents with and without mentions
blank/null/empty source-field counters
mention count by entity type
mention count by source field
overlap-pair count
same-span multi-type group count
confidence kind
truncation flag
canonical/reconcile/publication/model/API/full-corpus safety flags
```

These are descriptive build counters. They are not precision, recall, F1,
calibration, or production-quality evidence.

---

## 11. Independent build validator

Validation command:

```bash
python -m scripts.validation.check_scientific_entity_evidence_build \
  --build-dir data/entities/scientific_entity_evidence/v0.1/<build_id> \
  --strict
```

For mutation-free validation without latest/history reports:

```bash
python -m scripts.validation.check_scientific_entity_evidence_build \
  --build-dir data/entities/scientific_entity_evidence/v0.1/<build_id> \
  --strict \
  --no-write-reports
```

The validator imports the executable evidence/config contracts but does not
import the builder implementation. It independently checks:

```text
exact output layout
UTF-8/LF serialization
all file checksums
manifest and mention schemas
input path/hash/count and boundedness
config/environment/code provenance and current source-bundle match
exact span/source/hash consistency
mention_id and evidence_id recomputation
record ordering and ID uniqueness
not_available confidence semantics
data-quality counter recomputation
README and safety markers
fixture/candidate-only status
```

Default report locations:

```text
artifacts/reports/validation/scientific_entity_evidence_build_latest.json
artifacts/reports/validation/scientific_entity_evidence_build_latest.md
artifacts/reports/validation/history/scientific_entity_evidence_build_<ts>.json
artifacts/reports/validation/history/scientific_entity_evidence_build_<ts>.md
```

Reports are validation evidence only and are ignored generated artifacts.

---

## 12. Synthetic fixture coverage

The tracked fixture covers:

```text
all six entity types
title and abstract
Unicode code-point offsets
case-sensitive and explicit case-insensitive rules
hyphen-delimited word boundaries
embedded-substring false positives
null abstract
documents without mentions
deterministic expected semantic spans
```

Additional smoke tests cover overlapping mentions, same-span multiple types,
identity response to config/text changes, hard caps, no-overwrite behavior,
plan-only behavior, deterministic repeated output, LF enforcement, corruption,
and independent validator failures.

No external corpus text, model artifact, tokenizer, or provider response is
committed.

---

## 13. Reference fixture evidence

```text
synthetic canonical-shaped documents = 4
expected exact mention spans = 17
entity type coverage = 6 / 6
source field coverage = title + abstract
independent build checks = 89
baseline-specific smoke tests = 36
```

The full repository smoke-suite count is recorded only after the branch is run
in the project environment. The numbers above describe this bounded slice, not
model quality.

---

## 14. Acceptance gates

The slice is accepted only when:

```text
baseline config and adapter tests = green
plan mode writes nothing
fixture execute creates exact six-file layout
independent strict validator = green
expected semantic spans = exact match
deterministic repeat = byte-identical with fixed build metadata
hard-cap/current-canonical/accepted-status/overwrite gates = green
CRLF and corrupt-output regressions = rejected
existing Scientific Entity Evidence Contract tests = green
project current-state tests = green
full smoke suite = green
```

Acceptance authorizes review/evaluation work only. It does not authorize
full-corpus extraction or a production model.

---

## 15. Explicit non-goals

This slice does not:

```text
benchmark model quality
select or download spaCy, SciSpacy, GLiNER, DyGIE++, transformers, or an LLM
claim literal rules are contextual NER
create a gold corpus from redistributable third-party paper text
normalize aliases
assign global entity_id values
link Wikidata, OpenAlex concepts, Papers with Code, or another KB
materialize Postgres entities
add Discovery filters
add paper–entity graph edges
run over 61,075 papers
publish entity evidence
```

---

## 16. Implemented evaluation follow-on and next bounded slice

The evaluation follow-on is now implemented as:

```text
Scientific Entity Evaluation Harness v0.1
```

It provides deterministic exact/relaxed one-to-one matching, micro/per-type/
source-field metrics, structural error evidence, immutable output, and an
independent validator. Its tracked fixture validates evaluation semantics only.

The next bounded slice is:

```text
Bounded Scientific Entity Manual Review Evidence v0.1
```

That slice should define a small local curated review set and evaluate this
baseline with explicit evidence such as:

```text
exact-span precision / recall / F1
relaxed-overlap precision / recall / F1
per-type metrics
boundary and type confusion analysis
abstention / no-mention behavior
runtime and resource measurements
license and model provenance review
```

Only an evidence-backed decision after real bounded review may propose a
candidate model benchmark, production extractor, or separately reviewed full
derived build.
