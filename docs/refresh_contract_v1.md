# Refresh Runbook v1

## Purpose

This runbook describes the current **manual safe refresh loop v1** for the active 4-source core:

- arXiv backbone
- OpenAlex alignment
- Semantic Scholar alignment
- Crossref alignment

It is the human-oriented operational companion to:

- `docs/refresh_contract_v1.md`
- `docs/experiment_safety_rules.md`
- `docs/provenance_semantics.md`

This document is intentionally practical and step-by-step.

---

## What this runbook is for

Use this runbook when you want to safely refresh the corpus and keep all core layers consistent:

- canonical corpus
- Postgres serving layer
- retrieval artifacts
- validation reports
- known issues snapshot

This runbook assumes the current architecture:

- **canonical JSONL** = source of truth
- **Postgres** = materialized serving layer
- **retrieval artifacts** = separate search layer

---

## Current operational scope

This runbook covers the currently stabilized refresh loop for the active 4-source core.

It does **not** yet cover:

- new external sources beyond the active 4
- full text ingestion
- repository linkage
- embeddings beyond current retrieval build flow
- Airflow orchestration
- Kubernetes / Kafka / broader MLOps automation

Those belong to later iterations.

---

## Current active source set

The refresh loop v1 currently works with:

1. `arxiv`
2. `openalex_alignment`
3. `semantic_scholar_alignment`
4. `crossref_alignment`

Important:

- arXiv is the backbone
- OpenAlex / Semantic Scholar / Crossref are enrichment layers
- reconcile must run against **full merged snapshots**, not selective mini-batches

---

## Core safety principle

Never run reconcile against latest selective alignment batches directly.

Correct pattern:

1. selective enrichment
2. merge selective into full alignment snapshots
3. reconcile using explicit full merged inputs
4. validate candidate
5. promote candidate
6. export / rebuild / validate / DoD

This is the central safety rule of refresh v1.

---

## Preconditions

Before starting a refresh run, confirm:

- project environment is active
- Docker / Postgres is running if DB export will be included
- current latest canonical exists
- current retrieval manifest exists
- current validation reports exist
- latest known issues snapshot exists
- backups are allowed to be created in canonical/retrieval paths

---

## Recommended preflight

Activate environment and go to project root.

Example:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

If DB export is part of the run, ensure Docker services are up.

Example:

```bat
cd /d D:\ML\ML_Research_Radar\infra\docker
docker compose up -d
docker ps
cd /d D:\ML\ML_Research_Radar
```

Recommended quick sanity checks:

```bat
python -m scripts.export.test_db_read
python -m scripts.validation.run_retrieval_checks
python -m scripts.validation.run_postpass_audit
python -m scripts.validation.build_known_issues_snapshot
```

---

## Main manual refresh flow

### Option A — preferred thin orchestration wrapper

Use:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --arxiv-input data\normalized\arxiv\documents.20260404T161108Z.jsonl --execute
```

This wrapper currently performs:

1. `reconcile_candidate`
2. `candidate_provenance_audit`
3. `promote_candidate`
4. `export_postgres`
5. `rebuild_retrieval`
6. `retrieval_checks`
7. `postpass_audit`
8. `known_issues`
9. `dod_check`

This is the preferred current manual operational path.

---

### Option B — step-by-step manual execution

Use this if debugging or isolating a step.

#### 1. Build candidate canonical

```bat
python -m scripts.update.run_incremental_reconcile_stage --arxiv-input data\normalized\arxiv\documents.20260404T161108Z.jsonl --output-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl --execute
```

Expected:
- candidate file created
- reconcile input mode = `merged_full_inputs`
- candidate counts remain sane

#### 2. Audit candidate provenance

```bat
python -m scripts.validation.check_canonical_provenance_consistency --canonical-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl
```

Expected:
- `docs_with_error = 0`

Warnings/info may still exist and are not automatically blockers.

#### 3. Promote candidate to latest

```bat
python -m scripts.update.promote_canonical_candidate --candidate-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl --execute
```

Expected:
- backup created
- promotion performed
- postcheck match = true

#### 4. Export canonical to Postgres

```bat
python -m scripts.export.export_postgres_v1
```

Expected:
- source docs inserted/updated
- canonical export completes successfully

#### 5. Rebuild retrieval artifacts

```bat
python -m scripts.retrieval.build_indexes
```

Expected:
- new retrieval build id
- corpus doc count matches canonical latest

#### 6. Run retrieval checks

```bat
python -m scripts.validation.run_retrieval_checks
```

Expected:
- latest retrieval checks report updated
- build id matches retrieval manifest latest

#### 7. Run post-pass audit

```bat
python -m scripts.validation.run_postpass_audit
```

Expected:
- total docs matches canonical
- multi_source_docs matches canonical summary

#### 8. Refresh known issues snapshot

```bat
python -m scripts.validation.build_known_issues_snapshot
```

Expected:
- operational truth updated
- retrieval build id updated

#### 9. Run strict DoD check

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues
```

Expected:
- `dod_passed = True`
- `required_failed_count = 0`

---

## Expected success criteria

A refresh run v1 is considered successful when all of the following hold:

- candidate reconcile succeeds
- provenance audit reports `docs_with_error = 0`
- promotion succeeds
- export to Postgres succeeds
- retrieval rebuild succeeds
- retrieval checks updated successfully
- postpass audit updated successfully
- known issues snapshot updated successfully
- strict DoD check passes

---

## Current expected healthy values

At the current stabilized state, expected values are approximately:

- canonical docs: `30008`
- multisource docs: `5893`

These values may change after a future real refresh, but during current validation runs they should remain internally consistent across:

- canonical
- retrieval manifest
- retrieval checks
- postpass audit
- Postgres
- known issues operational truth

---

## What counts as a blocker

Stop the run and investigate if any of these occur:

- reconcile runs in unsafe mode instead of `merged_full_inputs`
- candidate counts collapse unexpectedly
- multisource docs collapse unexpectedly
- provenance audit reports real structural errors
- promotion fails
- export fails
- retrieval build fails
- DoD strict check fails

---

## What does not automatically count as a blocker

The following are not automatic blockers under current semantics:

- `doc_ids_shorter_than_sources`
- repeated source families in `sources`
- `arxiv_id` present without arXiv provenance row
- `source_ids` containing more families than `sources`

These are interpretation-level signals and must be understood through `docs/provenance_semantics.md`.

---

## Key supporting files

### Contracts and docs

- `docs/refresh_contract_v1.md`
- `docs/experiment_safety_rules.md`
- `docs/provenance_semantics.md`

### Core update scripts

- `scripts/update/run_incremental_reconcile_stage.py`
- `scripts/update/promote_canonical_candidate.py`
- `scripts/update/check_refresh_definition_of_done.py`
- `scripts/update/run_refresh_pipeline_v1.py`

### Validation scripts

- `scripts/validation/check_canonical_provenance_consistency.py`
- `scripts/validation/run_retrieval_checks.py`
- `scripts/validation/run_postpass_audit.py`
- `scripts/validation/build_known_issues_snapshot.py`

---

## Important output locations

### Canonical layer

- latest canonical:
  `data/analytics/reconciled/canonical_documents.jsonl`

- candidate canonical:
  timestamped files under:
  `data/analytics/reconciled/`

### Retrieval layer

- manifest latest:
  `artifacts/retrieval/manifests/latest.json`

### Validation reports

- retrieval checks:
  `artifacts/reports/validation/retrieval_checks_latest.json`

- postpass audit:
  `artifacts/reports/validation/postpass_audit_summary_latest.json`

- known issues:
  `artifacts/reports/validation/known_issues_snapshot_latest.json`

### Update reports

- reconcile stage:
  `artifacts/reports/update/run_incremental_reconcile_stage_latest.json`

- promotion:
  `artifacts/reports/update/promote_canonical_candidate_latest.json`

- DoD:
  `artifacts/reports/update/check_refresh_definition_of_done_latest.json`

- wrapper:
  `artifacts/reports/update/run_refresh_pipeline_v1_latest.json`

---

## Recommended working style

Keep the system modular.

Do not collapse all logic into one large script.

Preferred pattern:

- small focused scripts
- one thin wrapper
- explicit reports
- explicit backups
- explicit validation
- explicit DoD

This makes later Airflow orchestration much safer.

---

## Next steps after refresh v1 milestone

Once refresh v1 is stable and repeatable, the next major directions may include:

- onboarding additional sources
- full text ingestion
- repository linkage
- richer embeddings / vector layer
- Airflow DAG implementation
- product/API/UI expansion
- later MLOps automation

These should be built on top of the current proven refresh loop, not instead of it.

---

## Final note

Refresh v1 is considered complete only when the strict DoD path is green:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues
```

That is the final operational truth check for this runbook version.
