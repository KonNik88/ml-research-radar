# Field-Level Canonical Provenance Evidence v0.1

## 1. Purpose

This document defines the first bounded implementation of field-level canonical
provenance evidence for ML Research Radar.

The layer answers, for each field of a sampled `CanonicalDocument`:

```text
which contributing source observations were available
which observations supplied the selected value or elements
which current reconciliation rule was applied
which normalization or derivation step was applied
whether recomputation matches the current canonical sample
```

The layer implements the previously accepted
`Field-Level Canonical Provenance Contract v0.1` without changing canonical
truth or reconciliation behavior.

---

## 2. Architectural status

```text
schema_version = field_level_canonical_provenance_evidence_v0.1
status = bounded_derived_explanatory_evidence
canonical_truth = false
may_be_used_as_reconcile_input = false
manual_review_required = true
publication_ready = false
```

Hard boundaries:

```text
canonical_documents.jsonl mutation = false
CanonicalDocument schema change = false
reconcile.py change = false
Postgres mutation = false
retrieval mutation = false
Qdrant mutation = false
graph mutation = false
API mutation = false
Streamlit mutation = false
provider API calls = false
publication action = false
```

The generated evidence describes current executable behavior. It does not
become a new selector, merge policy, paper identity, source of truth, or runtime
serving dependency.

---

## 3. Input contract

The builder consumes one bounded reconciliation audit package produced by:

```bat
python -m scripts.validation.build_reconciliation_audit_package ^
  --strict-reports ^
  --max-papers 18 ^
  --semantic-scholar-min 6 ^
  --keep-staging
```

Accepted input forms:

```text
reconciliation audit staging directory
or
reconciliation audit ZIP
```

Required files inside the audit package:

```text
manifest.json
data_slice/canonical_documents.sample.jsonl
data_slice/source_documents.sample.jsonl
data_slice/canonical_source_links.sample.jsonl
data_slice/unmatched_canonical_source_links.jsonl
```

The builder fails closed when:

```text
an audit source link is unmatched
one contributing source observation is absent
source_observation_id resolves to conflicting source rows
a canonical sample row has no contributing observations
contributing observations recompute into multiple reconciliation groups
audit link counts disagree with canonical provenance rows
strict mode finds any canonical/recomputed field mismatch
```

The full canonical corpus, complete source snapshots, Postgres dumps, PDFs,
full text, embeddings, retrieval artifacts, and graph outputs are not inputs.

---

## 4. Source-observation linkage

The authoritative bounded linkage is reconstructed from the ordered
`CanonicalDocument.sources` rows.

For every source link the builder recomputes:

```text
source_observation_id
= build_source_observation_identity_from_mapping(source_link)
```

The resulting ID must resolve to exactly one row in
`source_documents.sample.jsonl`.

This preserves the established identity boundary:

```text
source_observation_id = physical source-observation identity
doc_id = legacy diagnostic identifier, not globally unique
canonical_id = reconciled paper identity
```

The order of `CanonicalDocument.sources` is retained as the contributing
observation order. This matters for current order-sensitive rules such as
`ordered_first`, stable exact ties, and ordered union.

Non-contributing selected observations are not eligible for field evidence.

---

## 5. Recomputing the canonical sample

The builder does not call provider APIs and does not run a full corpus
reconciliation job.

For each bounded canonical paper it applies the same current selector helpers to
its already-established contributing observations:

```text
build_reconciliation_groups
build_canonical_id
choose_best_title
choose_best_abstract
choose_best_doi
choose_best_arxiv_id
choose_best_openalex_id
choose_preferred_string
choose_best_license
choose_best_publication_type
normalize_venue_fields
merge_unique_strings
merge_source_ids
merge_external_ids
choose_min/max helpers
boolean helpers
compute_metadata_completeness_score
build_source_links
```

The reconstructed values are assembled into a temporary in-memory
`CanonicalDocument` solely to normalize field types and compare against the
supplied canonical sample.

```text
mismatch -> report/fail in strict mode
mismatch -> never repair canonical data
```

`created_at` and `updated_record_at` are copied from the reference canonical row
for model validation, but their field records are explicitly marked as runtime
defaults and not source-reconstructable.

---

## 6. Evidence record schema

One record is emitted for every pair:

```text
canonical_id + field_name
```

There are 61 records for every canonical paper.

Example:

```json
{
  "schema_version": "field_level_canonical_provenance_evidence_v0.1",
  "record_id": "deterministic-32-character-hash",
  "canonical_id": "paper-id",
  "field_name": "abstract",
  "strategy_kind": "winner",
  "canonical_value": "selected abstract",
  "recomputed_value": "selected abstract",
  "comparison_status": "match",
  "reconstructability": "exact",
  "candidate_count": 3,
  "selected_source_observation_ids": ["observation-id"],
  "contributing_source_observation_ids": ["observation-id"],
  "candidates": [],
  "elements": [],
  "transformations": [],
  "selection_reason": "winner",
  "caveats": []
}
```

Deterministic record identity:

```text
record_id = stable_hash(
  JSON([schema_version, canonical_id, field_name]),
  length=32
)
```

The record ID is evidence identity, not paper identity.

---

## 7. Strategy evidence

### 7.1 Winner and ordered-first

Candidate rows may contain:

```text
source_observation_id
source
input_position
raw_value
normalized_value
source_priority
eligible
selected
```

Covered examples:

```text
title
abstract
doi
arxiv_id
openalex_id
pmid / pmcid / Semantic Scholar / DBLP / MAG IDs
landing_page_url
pdf_url
primary_category
repo_url
comment
journal_ref
publisher
language
```

### 7.2 Winner with normalization or quality rank

The evidence retains the source candidate and a transformation record for:

```text
license -> normalize_license_value
venue/journal/conference -> normalize_venue_fields
publication_type -> non-preprint semantic override + source priority
```

A pre-normalization winner may remain the selected source observation even when
the normalized canonical output becomes null, for example when a book-chapter
series title is cleared from `journal`.

A conference value derived from a selected venue records the venue-providing
observation.

### 7.3 Ordered union

For list-valued fields, `elements` records:

```text
value
normalized_key
first_source_observation_id
contributing_source_observation_ids
occurrence_count
```

The first-seen spelling is retained and comparison/deduplication is
case-insensitive, matching current `merge_unique_strings` behavior.

Reference identifiers use bibliographic source-priority ordering before union.

### 7.4 Aggregate minimum and maximum

For date/year and citation/reference counts, all equal selected values are
preserved as co-winners.

```text
published_at / publication_date / year -> minimum
updated_at / cited_by_count / references_count -> maximum
```

### 7.5 Boolean evidence

Boolean records identify source observations relevant to the field-specific
rule.

Important semantics:

```text
open_access = explicit manifestation-level evidence
is_open_access = non-arXiv bibliographic OA evidence
is_preprint = explicit non-preprint publication evidence can override preprint
citation_graph_available / is_review / is_survey / is_withdrawn = any-true rules
```

### 7.6 Derived flags

```text
has_code_link
= source flags OR merged code links OR repo_url presence

has_dataset_link
= source flags OR merged dataset links

has_model_link
= source flags OR merged model links
```

The transformation record stores the OR components.

### 7.7 Derived score

`metadata_completeness_score` records all contributing observations and the
current 12-component recomputation rule.

It is not selected as `max(source metadata_completeness_score)`.

### 7.8 Identity, maps, and row-level provenance

```text
canonical_id / reconciliation_key = identity-derived
source_ids / external_ids = first non-empty value per key
sources / source_count / unique_source_count = all contributing rows
```

### 7.9 Runtime defaults

```text
created_at
updated_record_at
```

Required record state:

```text
comparison_status = not_applicable
reconstructability = not_source_reconstructable
selected_source_observation_ids = []
contributing_source_observation_ids = []
candidates = []
```

---

## 8. Output package

Default root:

```text
artifacts/audit/field_level_canonical_provenance_evidence_v0.1/
```

One build creates:

```text
latest.json
field_level_canonical_provenance_evidence_v0.1_<run_ts>/
  field_evidence.jsonl
  paper_summary.jsonl
  data_quality_summary.json
  manifest.json
  README.md
  checksums.txt
field_level_canonical_provenance_evidence_v0.1_<run_ts>.zip
```

### `field_evidence.jsonl`

One deterministic record per canonical field.

### `paper_summary.jsonl`

One row per canonical paper with:

```text
contributing source observation IDs
field record count
match count
not-applicable count
mismatch count
```

### `data_quality_summary.json`

Contains package-wide counts, strategy counts, and bounded mismatch samples.

### `manifest.json`

Contains safety boundaries, input reference, physical counts, and build verdict.

### `checksums.txt`

SHA-256 values for every required content file.

`field_evidence.jsonl`, `paper_summary.jsonl`, and
`data_quality_summary.json` are deterministic for identical inputs. Manifest and
ZIP hashes may differ between runs because they include build timestamps and run
names.

---

## 9. Builder CLI

From the repository root in Anaconda Prompt:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

Using the retained audit staging directory:

```bat
python -m scripts.validation.build_field_level_canonical_provenance_evidence ^
  --audit-path artifacts/audit/reconciliation_evidence_package_v0.1/reconciliation_evidence_audit_v0.1_20260724T074909Z ^
  --strict
```

Using the audit ZIP:

```bat
python -m scripts.validation.build_field_level_canonical_provenance_evidence ^
  --audit-path artifacts/audit/reconciliation_evidence_package_v0.1/reconciliation_evidence_audit_v0.1_20260724T074909Z.zip ^
  --strict
```

`--audit-dir` is accepted as an alias for `--audit-path`.

Optional flags:

```text
--output-root <path>
--run-ts <YYYYMMDDTHHMMSSZ>
--no-zip
```

---

## 10. Independent validator

The validator does not trust builder counts without rereading physical files.

It checks:

```text
required files exist
JSON and JSONL parse correctly
schema versions are exact
record IDs are deterministic and unique
(canonical_id, field_name) keys are unique
strategies match FIELD_STRATEGIES
all papers have exactly all 61 fields
all evidence observation IDs belong to the paper's contributing set
selected observation IDs are field-contributing IDs
candidate_count matches physical eligible candidates
runtime defaults use the required semantics
all source-reconstructable canonical/recomputed values match
manifest counts match physical files
quality counts match physical files
checksums are complete and correct
all safety/mutation flags remain false
```

Default validation through `latest.json`:

```bat
python -m scripts.validation.check_field_level_canonical_provenance_evidence --strict
```

Explicit package directory or ZIP:

```bat
python -m scripts.validation.check_field_level_canonical_provenance_evidence ^
  --package-path artifacts/audit/field_level_canonical_provenance_evidence_v0.1/field_level_canonical_provenance_evidence_v0.1_<run_ts> ^
  --strict
```

Validation reports:

```text
artifacts/reports/validation/field_level_canonical_provenance_evidence_v01_latest.json
artifacts/reports/validation/field_level_canonical_provenance_evidence_v01_latest.md
artifacts/reports/validation/history/field_level_canonical_provenance_evidence_v01_<run_ts>.json
artifacts/reports/validation/history/field_level_canonical_provenance_evidence_v01_<run_ts>.md
```

---

## 11. Smoke tests

New tests:

```text
tests/smoke/test_build_field_level_canonical_provenance_evidence.py
tests/smoke/test_field_level_canonical_provenance_evidence.py
```

Builder tests cover:

```text
complete 61-field package
winner evidence
ordered union and case-insensitive deduplication
normalization to null
license quality selection
boolean override semantics
derived flags
runtime defaults
deterministic output
ZIP input
fail-closed unmatched links
fail-closed missing source observations
```

Validator tests cover:

```text
valid package
missing field records
duplicate record IDs
wrong strategy
foreign/non-contributing observation IDs
field-value mismatches
checksum tampering
invalid runtime-default semantics
manifest count drift
```

Run:

```bat
python -m pytest ^
  tests/smoke/test_build_field_level_canonical_provenance_evidence.py ^
  tests/smoke/test_field_level_canonical_provenance_evidence.py ^
  -q
```

---

## 12. Related regression checks

After the new tests are green:

```bat
python -m pytest ^
  tests/smoke/test_reconcile_smoke.py ^
  tests/smoke/test_field_level_canonical_provenance_contract.py ^
  tests/smoke/test_build_reconciliation_audit_package.py ^
  tests/smoke/test_source_observation_identity_contract.py ^
  tests/smoke/test_source_observation_non_contributing.py ^
  tests/smoke/test_build_field_level_canonical_provenance_evidence.py ^
  tests/smoke/test_field_level_canonical_provenance_evidence.py ^
  -q
```

Contract regression:

```bat
python -m scripts.validation.check_field_level_canonical_provenance_contract --strict
```

No database, retrieval, Qdrant, graph, API, or UI gate is required because this
slice does not mutate those layers.

---

## 13. Accepted real-sample baseline

The implementation was exercised against the current bounded reconciliation
audit package:

```text
reconciliation_evidence_audit_v0.1_20260724T074909Z
```

Accepted evidence:

```text
canonical papers = 12
contributing source observations = 33
canonical source links = 33
unmatched source links = 0
canonical fields per paper = 61
field evidence records = 732
runtime-default records = 24
source-reconstructable matches = 708
not-applicable runtime defaults = 24
required mismatches = 0
```

Independent validation baseline:

```text
checks = 34 / 34
paper_count = 12
field_record_count = 732
value_mismatch_count = 0
required_failed_count = 0
```

Local synthetic tests prepared with this package:

```text
16 passed
```

The warning originating from `datetime.utcnow()` is an existing deprecation
warning in `reconcile.py`; this slice does not change that file.

---

## 14. Definition of Done

The slice is complete when all conditions hold:

```text
new builder tests = green
new validator tests = green
real audit evidence build = green
independent strict validator = green
12 canonical papers represented
33 contributing observations resolved
732 field records produced
61/61 fields per paper
0 unmatched source links
0 foreign/non-contributing evidence IDs
0 required canonical/recomputed mismatches
contract validator remains green
reconcile.py unchanged
canonical_documents.jsonl unchanged
Postgres unchanged
retrieval/Qdrant/graphs unchanged
API/UI unchanged
publication state unchanged
```

---

## 15. Explicit decision

```text
Field-Level Canonical Provenance Evidence v0.1
= accepted as a bounded, derived, read-only explanatory layer
```

It explains current canonical field selection. It does not modify or replace it.
