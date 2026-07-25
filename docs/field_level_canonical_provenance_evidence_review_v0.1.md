# Field-Level Canonical Provenance Evidence Review v0.1

## 1. Purpose

This document defines the bounded review and regression-hardening checkpoint for
Field-Level Canonical Provenance Evidence v0.1.

The preceding builder and validator established that one bounded audit sample
can be reconstructed without required field-value mismatches. This review slice
answers a narrower but stronger question:

```text
Do two independent executions over directory and ZIP representations of the
same reconciliation audit package produce exactly the same explanatory evidence,
and does that evidence remain tied to the accepted bounded audit baseline?
```

The review is intentionally file-first, read-only, and bounded.

It does not generate a full-corpus provenance dataset, modify reconciliation, or
promote evidence into a serving layer.

---

## 2. Architectural status

```text
status = read_only_determinism_and_regression_review
canonical_truth = false
may_be_used_as_reconcile_input = false
publication_ready = false
manual_review_required = true
```

The review operates over three existing derived artifacts:

```text
bounded reconciliation audit package
+ evidence run built from audit directory
+ evidence run built from audit ZIP
→ independent package validation
→ semantic determinism comparison
→ accepted-baseline regression checks
→ JSON / Markdown review report
```

The review report is derived validation evidence. It is not a paper entity, a
source observation, a canonical field, or a new truth layer.

---

## 3. Tracked files

This slice adds:

```text
scripts/validation/check_field_level_canonical_provenance_evidence_review.py
tests/smoke/test_field_level_canonical_provenance_evidence_review.py
docs/field_level_canonical_provenance_evidence_review_v0.1.md
```

No configuration file is required. The accepted bounded regression baseline is
small, explicit, and versioned directly in the review validator.

No separate comparison runner is required. Package validation, audit linkage,
semantic comparison, and accepted-baseline checks are intentionally combined in
one review validator to avoid duplicated comparison logic.

---

## 4. Inputs

### 4.1 Reconciliation audit package

Accepted input:

```text
reconciliation_evidence_audit_v0.1_20260724T074909Z
```

The validator accepts either the extracted directory or its ZIP archive.

Required audit files:

```text
manifest.json
data_slice/canonical_documents.sample.jsonl
data_slice/source_documents.sample.jsonl
data_slice/canonical_source_links.sample.jsonl
data_slice/unmatched_canonical_source_links.jsonl
```

Accepted audit-package identity:

```text
package_name = reconciliation_evidence_audit_v0.1_20260724T074909Z
canonical papers = 12
matched source documents = 33
canonical source links = 33
unmatched source links = 0
```

The review also fixes the accepted SHA-256 values of the four relevant audit
content files. This allows directory and ZIP representations to be checked
against the same semantic audit baseline without relying on the outer archive
filename.

### 4.2 Left evidence package

Accepted left run:

```text
field_level_canonical_provenance_evidence_v0.1_20260724T120609Z
```

This run was built from the extracted audit directory.

### 4.3 Right evidence package

Accepted right run:

```text
field_level_canonical_provenance_evidence_v0.1_20260724T120621Z
```

This run was built from the audit ZIP.

The review requires the pair to cover both input modes:

```text
{directory, zip}
```

The order of left and right is not semantically important, but both modes must
be represented in the accepted regression review.

---

## 5. Reuse of the existing package validator

Each evidence package is first checked independently through:

```text
scripts.validation.check_field_level_canonical_provenance_evidence.build_report
```

Therefore the review does not weaken or replace the existing 34-check package
validator.

Each run must independently preserve:

```text
required files
exact evidence schema
61/61 field coverage per paper
deterministic record IDs
strategy-to-field contract
contributing observation boundaries
runtime-default semantics
canonical/recomputed value equality
manifest and physical counts
checksums
read-only safety flags
```

A semantic comparison is attempted only as part of the same report; failure of
either individual package remains a required review failure.

---

## 6. Semantic files

The review treats these files as deterministic semantic outputs:

```text
field_evidence.jsonl
paper_summary.jsonl
data_quality_summary.json
```

For equal inputs, the review requires both:

```text
physical bytes are identical
SHA-256 digests are identical
```

Accepted SHA-256 values:

```text
field_evidence.jsonl
= d3a42644e51854226343e98f048856a16b2f9cd52289bb3dd6e5676f751077b0

paper_summary.jsonl
= dc3d3ab43d4bc3bf82c14593f0b274f8989efbd7bd79694c5a397f7b58d7356d

data_quality_summary.json
= 825d49a0f5b1b95be39a6bff77a000adc03842c8290c758716a202b04bb52236
```

The full evidence package ZIP is not expected to have the same checksum across
runs because these values legitimately differ:

```text
package_name
generated_at_utc
inputs.audit_path
inputs.audit_root
```

The review normalizes only these volatile manifest fields and requires the
remaining manifest semantics to match exactly.

---

## 7. Comparison contract

### 7.1 Paper identity

Both runs must contain exactly the same canonical paper IDs.

The paper ID set must also equal the physical canonical ID set from:

```text
data_slice/canonical_documents.sample.jsonl
```

### 7.2 Source-observation identity

The review recomputes every audit source row identity with:

```text
build_source_observation_identity_from_mapping
```

The resulting audit source-observation ID set must equal the union of
`contributing_source_observation_ids` in both evidence-run paper summaries.

This prevents evidence from silently dropping, replacing, or importing source
observations while still preserving superficially correct counts.

### 7.3 Field record identity

Both runs must contain exactly the same:

```text
(canonical_id, field_name) keys
record_id values
complete record objects
```

A change to an explanatory property such as `selection_reason` is therefore a
semantic difference even when the ordinary package validator still considers
the modified package structurally valid.

### 7.4 Field coverage

For each canonical paper:

```text
actual field set = all 61 FIELD_STRATEGIES fields
```

Arithmetic invariant:

```text
12 papers × 61 fields = 732 field evidence records
```

### 7.5 Strategy coverage

All 14 accepted strategy families must appear in each run:

```text
identity_derived
winner
winner_with_normalization
winner_with_quality_rank
ordered_first
ordered_union
aggregate_min
aggregate_max
boolean_evidence
derived_flag
derived_score
row_level_provenance
merged_identifier_map
runtime_default
```

Accepted strategy counters:

```text
aggregate_max = 36
aggregate_min = 36
boolean_evidence = 84
derived_flag = 36
derived_score = 12
identity_derived = 24
merged_identifier_map = 24
ordered_first = 120
ordered_union = 144
row_level_provenance = 36
runtime_default = 24
winner = 96
winner_with_normalization = 48
winner_with_quality_rank = 12
```

### 7.6 Comparison partition

For each run:

```text
comparison_match_count
+ comparison_not_applicable_count
+ comparison_mismatch_count
= field_evidence_record_count
```

Accepted values:

```text
source-reconstructable matches = 708
runtime-default not-applicable records = 24
required mismatches = 0
total = 732
```

### 7.7 Runtime defaults

The accepted canonical model has two runtime-default fields:

```text
created_at
updated_record_at
```

Required arithmetic:

```text
12 papers × 2 runtime-default fields = 24 runtime-default records
```

These records remain explicitly non-source-reconstructable and do not receive a
fabricated source winner.

---

## 8. Accepted-baseline mode

The general review logic can compare smaller synthetic packages without forcing
the production bounded counts.

The CLI flag:

```text
--require-accepted-baseline
```

adds exact regression checks for:

```text
accepted audit package name
accepted audit content SHA-256 values
accepted evidence semantic SHA-256 values
accepted paper/source/link/field counters
accepted strategy counters
```

This mode is required for the real project checkpoint.

It deliberately fails for synthetic one-paper fixtures, proving that the
baseline gate is separate from the generic semantic-comparison logic.

---

## 9. Negative-fixture coverage

The new smoke tests cover the following failure classes.

### 9.1 Semantic drift with a structurally valid package

A test changes only `selection_reason`, updates the package manifest and
checksums, and confirms:

```text
ordinary package validator = still green
review semantic comparison = fails
```

This proves that the review adds real regression protection rather than merely
running the existing validator twice.

### 9.2 Audit package identity drift

A test changes the audit package name recorded in one evidence manifest and
confirms that the review rejects the pair even though the individual evidence
package remains structurally valid.

### 9.3 Individual package contract failure

A test changes a field strategy and confirms that the existing package
validator failure propagates into the review verdict.

### 9.4 Audit source-observation drift

A test removes one source row from a copied audit package, updates its local
audit manifest, and confirms that the review detects:

```text
audit observation ID set != evidence observation ID set
audit counts != evidence manifest counts
```

### 9.5 Accepted baseline drift

A test runs accepted-baseline mode over a valid synthetic one-paper pair and
confirms rejection of non-accepted counts and SHA-256 values.

### 9.6 Archive handling

A test validates evidence ZIP + evidence ZIP + audit ZIP inputs to ensure the
review is not dependent on already extracted directories.

---

## 10. CLI

Run from the repository root in Anaconda Prompt.

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

Real accepted-baseline review:

```bat
python -m scripts.validation.check_field_level_canonical_provenance_evidence_review ^
  --left-package artifacts/audit/field_level_canonical_provenance_evidence_v0.1/field_level_canonical_provenance_evidence_v0.1_20260724T120609Z.zip ^
  --right-package artifacts/audit/field_level_canonical_provenance_evidence_v0.1/field_level_canonical_provenance_evidence_v0.1_20260724T120621Z.zip ^
  --audit-path artifacts/audit/reconciliation_evidence_package_v0.1/reconciliation_evidence_audit_v0.1_20260724T074909Z.zip ^
  --require-accepted-baseline ^
  --strict
```

The three package arguments may also point to extracted directories.

Optional flags:

```text
--sample-limit <int>
--output-dir <path>
--no-write
```

`--strict` returns a non-zero process exit code when any required check fails.

---

## 11. Reports

Generated reports are not tracked repository files.

```text
artifacts/reports/validation/
├── field_level_canonical_provenance_evidence_review_v01_latest.json
├── field_level_canonical_provenance_evidence_review_v01_latest.md
└── history/
    ├── field_level_canonical_provenance_evidence_review_v01_<run_ts>.json
    └── field_level_canonical_provenance_evidence_review_v01_<run_ts>.md
```

The report contains:

```text
individual package validation summaries
all review checks
semantic SHA-256 values
strategy counters
bounded counts
sample differences when present
read-only boundary verdict
```

---

## 12. Accepted real review result

Current accepted validation:

```text
checks = 58 / 58
paper_count = 12
canonical_field_count = 61
field_record_count = 732
contributing_source_observation_count = 33
strategy_family_count = 14
semantic_files_compared_count = 3
semantic_file_difference_count = 0
record_key_difference_count = 0
record_content_difference_count = 0
comparison_match_count = 708
runtime_default_record_count = 24
value_mismatch_count = 0
unmatched_source_link_count = 0
required_failed_count = 0
```

Accepted verdict:

```text
semantic_determinism_confirmed = true
directory_zip_input_parity_confirmed = true
accepted_bounded_baseline_confirmed = true
```

---

## 13. Smoke tests

New test:

```text
tests/smoke/test_field_level_canonical_provenance_evidence_review.py
```

Run only the review tests:

```bat
python -m pytest ^
  tests/smoke/test_field_level_canonical_provenance_evidence_review.py ^
  -q
```

Expected result:

```text
7 passed
```

Run the complete field-level evidence test block:

```bat
python -m pytest ^
  tests/smoke/test_build_field_level_canonical_provenance_evidence.py ^
  tests/smoke/test_field_level_canonical_provenance_evidence.py ^
  tests/smoke/test_field_level_canonical_provenance_evidence_review.py ^
  -q
```

Expected result:

```text
23 passed
```

The existing `datetime.utcnow()` deprecation warning comes from
`radar_core/normalize/reconcile.py`. This review slice does not change that file.

---

## 14. Related regression checks

After review tests and the real strict review are green:

```bat
python -m pytest ^
  tests/smoke/test_reconcile_smoke.py ^
  tests/smoke/test_field_level_canonical_provenance_contract.py ^
  tests/smoke/test_build_reconciliation_audit_package.py ^
  tests/smoke/test_source_observation_identity_contract.py ^
  tests/smoke/test_source_observation_non_contributing.py ^
  tests/smoke/test_build_field_level_canonical_provenance_evidence.py ^
  tests/smoke/test_field_level_canonical_provenance_evidence.py ^
  tests/smoke/test_field_level_canonical_provenance_evidence_review.py ^
  -q
```

Contract validator:

```bat
python -m scripts.validation.check_field_level_canonical_provenance_contract --strict
```

Evidence package validator remains independently runnable:

```bat
python -m scripts.validation.check_field_level_canonical_provenance_evidence --strict
```

No Postgres, Qdrant, retrieval, graph, API, or UI runtime is required for this
review slice.

---

## 15. Safety boundaries

The review validator declares and preserves:

```text
canonical_truth_mutated = false
reconcile_executed_by_review = false
postgres_mutated = false
retrieval_mutated = false
qdrant_mutated = false
graph_mutated = false
api_mutated = false
ui_mutated = false
publication_performed = false
```

The slice does not change:

```text
radar_core/normalize/reconcile.py
CanonicalDocument
NormalizedDocument
canonical_documents.jsonl
source-observation materialization
Postgres schema or data
retrieval artifacts
Qdrant collections
ranking
artifact policy
graph outputs
FastAPI
Streamlit
publication state
```

---

## 16. Definition of Done

The review slice is complete when all conditions hold:

```text
review smoke tests = green
full field-evidence test block = green
both evidence packages pass the independent package validator
audit package integrity checks = green
directory and ZIP input modes are both represented
semantic JSON/JSONL bytes are identical
semantic SHA-256 values are identical
normalized manifests are identical
paper ID sets are identical and match audit input
source-observation ID sets are identical and match audit input
record keys, IDs, and complete records are identical
all 61 fields are present for every paper
all 14 strategy families are present
accepted counters match exactly
accepted strategy counters match exactly
accepted semantic SHA-256 values match exactly
value mismatches = 0
unmatched source links = 0
required_failed_count = 0
reconcile.py unchanged
canonical corpus unchanged
Postgres/retrieval/Qdrant/graph/API/UI unchanged
publication state unchanged
```

---

## 17. Explicit decision

```text
Field-Level Canonical Provenance Evidence Review v0.1
= accepted as a bounded determinism and regression-hardening gate
```

The accepted evidence is deterministic across directory and ZIP input
representations of the same audit package.

This decision does not authorize:

```text
full-corpus evidence generation
Postgres provenance materialization
API or Streamlit provenance surfaces
reconciliation changes
canonical schema changes
publication
```

The next safe step is a small review checkpoint/living-doc synchronization, not
runtime or full-corpus promotion.
