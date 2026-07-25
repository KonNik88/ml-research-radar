# Field-Level Canonical Provenance Evidence Checkpoint v0.1

Status: implemented read-only final line checkpoint
Slice: `checkpoint/field-level-canonical-provenance-evidence-v01`
Input: accepted contract, bounded evidence validation, and semantic review reports
Output status: generated validation reports, not committed by default

## 1. Purpose

Field-Level Canonical Provenance Evidence Checkpoint v0.1 is the final bounded checkpoint for the completed field-level canonical provenance evidence line.

It answers one operational question:

```text
Is the bounded field-level canonical provenance line internally complete,
semantically deterministic, fail-closed, and safe to treat as a closed checkpoint?
```

This slice does not add a new evidence builder or change reconciliation. It aggregates the already accepted reports into one final read-only verdict.

## 2. Position in the provenance line

The completed bounded line is:

```text
field-level provenance contract
→ bounded evidence builder
→ evidence package validator
→ semantic determinism and regression review
→ final checkpoint
```

The checkpoint intentionally comes after the semantic review. It consumes existing reports only.

## 3. Tracked files

```text
docs/field_level_canonical_provenance_evidence_checkpoint_v0.1.md
scripts/validation/check_field_level_canonical_provenance_evidence_checkpoint.py
tests/smoke/test_field_level_canonical_provenance_evidence_checkpoint.py
```

The slice may also synchronize the living project documents:

```text
docs/architecture.md
docs/data_contracts.md
docs/project_state_current_v0.1.md
docs/provenance_semantics.md
docs/roadmap.md
```

## 4. Generated reports

Generated reports are local validation artifacts and are not committed by default:

```text
artifacts/reports/validation/
├── field_level_canonical_provenance_evidence_checkpoint_v01_latest.json
├── field_level_canonical_provenance_evidence_checkpoint_v01_latest.md
└── history/
    ├── field_level_canonical_provenance_evidence_checkpoint_v01_<timestamp>.json
    └── field_level_canonical_provenance_evidence_checkpoint_v01_<timestamp>.md
```

## 5. Inputs

The checkpoint reads exactly three existing latest reports:

```text
artifacts/reports/validation/field_level_canonical_provenance_contract_v01_latest.json
artifacts/reports/validation/field_level_canonical_provenance_evidence_v01_latest.json
artifacts/reports/validation/field_level_canonical_provenance_evidence_review_v01_latest.json
```

The validator does not rebuild those reports and does not repair missing or inconsistent inputs.

## 6. Accepted contract baseline

Required identity:

```text
report_name=field_level_canonical_provenance_contract_v01
schema_version=field_level_canonical_provenance_contract_v0.1
status=read_only_static_contract_validation
```

Accepted counters:

```text
checks=99 / 99
canonical fields=61
classified fields=61
assembly fields=59
strategy kinds=14
failed checks=0
required failed count=0
```

Accepted verdict:

```text
ok=true
contract_matches_current_reconciliation=true
canonical_contract_change_required=false
reconciliation_behavior_change_required=false
postgres_change_required=false
runtime_change_required=false
```

## 7. Accepted evidence validation baseline

Required identity:

```text
report_name=field_level_canonical_provenance_evidence_check_v01
schema_version=field_level_canonical_provenance_evidence_v0.1
status=read_only_package_validation
```

Accepted counters:

```text
checks=34 / 34
canonical papers=12
canonical fields=61
field evidence records=732
value mismatches=0
checksum mismatches=0
duplicate record ids=0
duplicate record keys=0
field coverage failures=0
foreign observation ids=0
required failed count=0
```

Accepted verdict:

```text
ok=true
evidence_package_valid=true
canonical_truth_mutated=false
postgres_mutated=false
provider_api_called=false
```

## 8. Accepted semantic review baseline

Required identity:

```text
report_name=field_level_canonical_provenance_evidence_review_v01
schema_version=field_level_canonical_provenance_evidence_review_v0.1
status=read_only_determinism_and_regression_review
```

Accepted counters:

```text
checks=58 / 58
canonical papers=12
contributing source observations=33
canonical fields=61
field evidence records=732
source-reconstructable matches=708
runtime-default records=24
strategy families=14
semantic files compared=3
semantic file differences=0
record-key differences=0
record-content differences=0
value mismatches=0
unmatched source links=0
required failed count=0
```

Accepted verdict:

```text
ok=true
accepted_bounded_baseline_confirmed=true
directory_zip_input_parity_confirmed=true
semantic_determinism_confirmed=true
```

## 9. Accepted semantic SHA-256

```text
field_evidence.jsonl
d3a42644e51854226343e98f048856a16b2f9cd52289bb3dd6e5676f751077b0

paper_summary.jsonl
dc3d3ab43d4bc3bf82c14593f0b274f8989efbd7bd79694c5a397f7b58d7356d

data_quality_summary.json
825d49a0f5b1b95be39a6bff77a000adc03842c8290c758716a202b04bb52236
```

Both reviewed evidence runs must match all three accepted semantic hashes.

## 10. Strategy-family baseline

The accepted evidence covers 14 strategy families:

```text
aggregate_max=36
aggregate_min=36
boolean_evidence=84
derived_flag=36
derived_score=12
identity_derived=24
merged_identifier_map=24
ordered_first=120
ordered_union=144
row_level_provenance=36
runtime_default=24
winner=96
winner_with_normalization=48
winner_with_quality_rank=12
```

The left and right reviewed runs must match these counters exactly.

## 11. Cross-report invariants

The checkpoint validates the entire chain, not three reports independently.

Required cross-report invariants:

```text
canonical_field_count = 61 in contract, evidence, and review
paper_count = 12 in evidence and review
field_record_count = 732 in evidence and review
strategy taxonomy = 14 families in contract and review
value_mismatch_count = 0 in evidence and review
12 × 61 = 732
708 + 24 = 732
```

## 12. Fail-closed behavior

Checkpoint readiness becomes false when any required invariant fails.

Examples:

```text
missing or unreadable input report
report_name drift
schema_version drift
status drift
any source report check becomes false
required_failed_count > 0
61-field contract drift
12-paper bounded baseline drift
732-record baseline drift
strategy-family drift
semantic SHA-256 drift
semantic file difference > 0
record-key or record-content difference > 0
value mismatch > 0
unmatched source link > 0
any mutation/publication safety flag becomes true
```

The checkpoint does not silently accept a recomputed or internally consistent replacement baseline.

## 13. Validator

Validator path:

```text
scripts/validation/check_field_level_canonical_provenance_evidence_checkpoint.py
```

Standard command:

```bat
python -m scripts.validation.check_field_level_canonical_provenance_evidence_checkpoint --strict
```

Read-only command without writing reports:

```bat
python -m scripts.validation.check_field_level_canonical_provenance_evidence_checkpoint --strict --no-write
```

Expected accepted result:

```text
report_name=field_level_canonical_provenance_evidence_checkpoint_v01
checks_count=35
passed_checks_count=35
canonical_field_count=61
paper_count=12
field_record_count=732
strategy_family_count=14
semantic_file_difference_count=0
value_mismatch_count=0
required_failed_count=0
field_level_provenance_line_complete=true
```

## 14. Smoke tests

Smoke test path:

```text
tests/smoke/test_field_level_canonical_provenance_evidence_checkpoint.py
```

Commands:

```bat
python -m py_compile scripts/validation/check_field_level_canonical_provenance_evidence_checkpoint.py
python -m pytest tests/smoke/test_field_level_canonical_provenance_evidence_checkpoint.py -q
python -m scripts.validation.check_field_level_canonical_provenance_evidence_checkpoint --strict
```

The smoke suite covers:

```text
accepted complete baseline passes
report identity drift fails
required source-report check failure propagates
canonical field-count drift fails
evidence counter drift fails
semantic drift fails
safety boundary drift fails
missing report fails
CLI --strict --no-write passes the accepted fixture
```

## 15. Architectural boundaries

This checkpoint is read-only and bounded.

It does not:

```text
rebuild the evidence package
re-run the evidence review
execute reconciliation
change merge policy
change CanonicalDocument
mutate canonical_documents.jsonl
materialize full-corpus field provenance
change Postgres or DB schema
change retrieval artifacts
change Qdrant
change ranking
change graph artifacts
change API
change Streamlit UI
call provider APIs
publish a dataset
publish evidence
create a runtime provenance API
```

The checkpoint remains:

```text
derived explanatory evidence
not canonical truth
not a reconcile input
not a database source
not a retrieval source
not a runtime product surface
not publication-ready by itself
```

## 16. Completion verdict

The checkpoint emits:

```text
field_level_provenance_line_complete=true
bounded_evidence_checkpoint_ready=true
required_failed_count=0
```

only when the complete accepted contract → evidence → semantic review chain is green.

After this checkpoint, the bounded field-level provenance evidence line is closed. A later full-corpus materialization, Postgres model, API/UI surface, publication path, or reconciliation change requires a separate architecture decision and a separate slice.

## 17. Git hygiene

Commit tracked source files and synchronized living documentation only.

Do not commit generated reports under:

```text
artifacts/reports/validation/
```

Do not commit bounded audit/evidence package output unless a separate artifact-retention policy explicitly requires it.
