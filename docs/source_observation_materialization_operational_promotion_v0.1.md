# Source Observation Materialization Operational Promotion v0.1

```text
contract_status = implementation_candidate
promotion_status = not_started
canonical_truth_mutation = forbidden
reconciliation_behavior_change = forbidden
public_api_change = not_required
database_mutation_by_validator = forbidden
```

## 1. Purpose

This contract defines the bounded operational promotion of the already validated
`source_observation_id` PostgreSQL materialization into the default local serving
database.

The implementation and candidate rebuild are already complete. This slice does
not redesign source identity and does not rebuild canonical truth. It promotes a
validated rebuildable serving database while preserving an immediate rollback
path.

```text
validated candidate database
→ logical backup evidence
→ controlled database-name swap
→ default-runtime validation
→ retained rollback database
```

## 2. Architectural boundaries

The following boundaries remain unchanged:

```text
data/analytics/reconciled/canonical_documents.jsonl
= paper-level canonical truth

Postgres
= rebuildable materialized serving layer

source_observation_id
= authoritative physical identity of one normalized source observation

doc_id
= legacy non-unique compatibility / diagnostic field

canonical_id
= reconciled paper-level identity
```

This promotion must not:

- run reconcile;
- modify `canonical_documents.jsonl`;
- rebuild retrieval artifacts;
- rebuild or promote Qdrant;
- modify ranking, features, graph outputs, API schemas, or Streamlit behavior;
- rename artifact-layer `source_doc_id` fields;
- perform an in-place ALTER of the legacy operational paper tables;
- delete the previous operational database during this slice.

## 3. Accepted pre-promotion baseline

### 3.1 Repository

```text
main merge commit = da2440f
implementation commit = 59dc438
working branch = ops/source-observation-materialization-promotion-v01
```

### 3.2 Canonical truth fingerprint

```text
canonical path = data/analytics/reconciled/canonical_documents.jsonl
SHA-256 = 6282e3e78a604490d0626a243e1e93a1c8e2a012b6558739a88448cf19970fc7
```

The fingerprint must remain unchanged before and after promotion.

### 3.3 Legacy operational database

```text
database = ml_radar
owner = ml_radar
schema phase = legacy materialization

canonical_documents    = 60,954
source_documents       = 70,244
canonical_source_links = 88,037
document_references    = 709,662
artifact_entities      = 7,333
artifact_observations  = 38,246
paper_artifact_links   = 7,430
```

Legacy schema markers:

```text
source_documents.source_observation_id = absent
canonical_source_links.source_observation_id = absent
source_documents.doc_id = NOT NULL legacy key
```

### 3.4 Validated candidate database

```text
database = ml_radar_source_identity_candidate_v01
owner = ml_radar
schema phase = source_observation_id materialization

canonical_documents    = 60,954
source_documents       = 88,178
canonical_source_links = 88,037
document_references    = 709,662
artifact_entities      = 7,333
artifact_observations  = 38,246
paper_artifact_links   = 7,430
```

Candidate identity evidence:

```text
unique source_observation_id = 88,178
NULL authoritative links = 0
dangling authoritative links = 0
selected observations missing from DB = 0
shared cross-source legacy doc_id values = 9,119
full_parity_ok = true
```

The 141 selected observations that do not contribute a canonical provenance row
remain preserved in `source_documents`; they must not create artificial
`canonical_source_links` rows.

## 4. Operational names

Before the actual promotion, define one UTC promotion timestamp:

```text
<PROMOTION_TS> = YYYYMMDDTHHMMSSZ, rendered in lowercase inside database names
```

Names:

```text
operational database = ml_radar
candidate database = ml_radar_source_identity_candidate_v01
legacy archive database = ml_radar_pre_source_identity_v01_<promotion_ts>
failed candidate database = ml_radar_source_identity_failed_v01_<promotion_ts>
```

Backup files, stored locally and never committed:

```text
backups/postgres/ml_radar_pre_source_identity_v01_<PROMOTION_TS>.dump
backups/postgres/ml_radar_source_identity_candidate_v01_<PROMOTION_TS>.dump

backups/postgres/ml_radar_pre_source_identity_v01_<PROMOTION_TS>.list.txt
backups/postgres/ml_radar_source_identity_candidate_v01_<PROMOTION_TS>.list.txt
```

## 5. Environment semantics

The API configuration is read from `services/api/settings.py`, which loads the
root `.env` with prefix `ML_RADAR_`.

Accepted root `.env` values remain:

```text
ML_RADAR_SEARCH_BACKEND=db
ML_RADAR_POSTGRES_HOST=127.0.0.1
ML_RADAR_POSTGRES_PORT=15432
ML_RADAR_POSTGRES_DBNAME=ml_radar
ML_RADAR_POSTGRES_USER=ml_radar
```

The `.env` database name must not change during promotion. The candidate receives
the stable operational name `ml_radar`, so normal API/runtime startup selects it
without a DB-name override.

Before promotion, shell overrides such as `ML_RADAR_DB_NAME` or
`ML_RADAR_POSTGRES_DBNAME` must be absent unless a specific validation command
sets them deliberately.

## 6. Read-only promotion validator

Tracked validator:

```text
scripts/validation/check_source_observation_materialization_promotion.py
```

Supported phases:

```text
--phase preflight
--phase post-promotion
```

The validator may:

- inspect PostgreSQL catalog metadata;
- connect read-only for `SELECT` queries;
- count rows and integrity gaps;
- inspect schema columns, PK/FK/unique constraints;
- hash the canonical JSONL file;
- inspect backup/list evidence files;
- inspect available disk space;
- write JSON/Markdown validation reports.

The validator must never execute:

```text
ALTER DATABASE
DROP DATABASE
CREATE DATABASE
TRUNCATE
INSERT
UPDATE
DELETE
pg_terminate_backend
pg_cancel_backend
```

## 7. Preflight gates

A strict preflight is green only when:

```text
canonical SHA-256 matches accepted fingerprint
operational ml_radar exists and is owned by ml_radar
candidate database exists and is owned by ml_radar
planned archive database does not already exist
active external connections to both databases = 0
free space at backup root >= configured minimum

operational database has the accepted legacy schema/counts
candidate database has the accepted source_observation_id schema/counts
candidate source_observation_id values are unique
candidate authoritative NULL links = 0
candidate authoritative dangling links = 0
candidate artifact dangling links = 0
```

The first preflight may run before dumps. Immediately before database mutation,
run it again with:

```text
--require-backups
```

That mode additionally requires both non-empty custom-format dumps and both
non-empty `pg_restore --list` outputs.

## 8. Backup procedure

Create the local backup directory:

```bat
if not exist backups\postgres mkdir backups\postgres
```

Choose one UTC timestamp and reuse it for every filename/database name in the
promotion attempt.

Operational backup:

```bat
docker exec ml_radar_postgres pg_dump ^
  -U ml_radar ^
  -d ml_radar ^
  -Fc ^
  -f /tmp/ml_radar_pre_source_identity_v01_<PROMOTION_TS>.dump

docker cp ml_radar_postgres:/tmp/ml_radar_pre_source_identity_v01_<PROMOTION_TS>.dump backups\postgres\ml_radar_pre_source_identity_v01_<PROMOTION_TS>.dump
```

Candidate backup:

```bat
docker exec ml_radar_postgres pg_dump ^
  -U ml_radar ^
  -d ml_radar_source_identity_candidate_v01 ^
  -Fc ^
  -f /tmp/ml_radar_source_identity_candidate_v01_<PROMOTION_TS>.dump

docker cp ml_radar_postgres:/tmp/ml_radar_source_identity_candidate_v01_<PROMOTION_TS>.dump backups\postgres\ml_radar_source_identity_candidate_v01_<PROMOTION_TS>.dump
```

Validate both dumps and save readable evidence:

```bat
docker exec -i ml_radar_postgres pg_restore --list < backups\postgres\ml_radar_pre_source_identity_v01_<PROMOTION_TS>.dump > backups\postgres\ml_radar_pre_source_identity_v01_<PROMOTION_TS>.list.txt

docker exec -i ml_radar_postgres pg_restore --list < backups\postgres\ml_radar_source_identity_candidate_v01_<PROMOTION_TS>.dump > backups\postgres\ml_radar_source_identity_candidate_v01_<PROMOTION_TS>.list.txt
```

A dump is not accepted merely because the file exists. Its paired list output
must also be non-empty.

Container `/tmp` copies may be removed only after the host files and list outputs
are verified.

## 9. Controlled database-name swap

Promotion is local and intentionally brief. Stop local API/Streamlit processes
first. Confirm zero external connections again.

From database `postgres`, terminate any unexpected remaining sessions only after
reviewing them explicitly. The read-only validator itself does not terminate
sessions.

Rename legacy operational database first:

```bat
docker exec ml_radar_postgres psql -v ON_ERROR_STOP=1 -U ml_radar -d postgres -c "ALTER DATABASE ml_radar RENAME TO ml_radar_pre_source_identity_v01_<promotion_ts>;"
```

Then rename candidate to the stable operational name:

```bat
docker exec ml_radar_postgres psql -v ON_ERROR_STOP=1 -U ml_radar -d postgres -c "ALTER DATABASE ml_radar_source_identity_candidate_v01 RENAME TO ml_radar;"
```

`ALTER DATABASE ... RENAME` is not treated as an atomic two-statement
transaction. If the second command fails, immediately restore the first name:

```bat
docker exec ml_radar_postgres psql -v ON_ERROR_STOP=1 -U ml_radar -d postgres -c "ALTER DATABASE ml_radar_pre_source_identity_v01_<promotion_ts> RENAME TO ml_radar;"
```

Do not improvise table-level fixes during this state.

## 10. Post-promotion gates

The post-promotion validator must be run with the exact archive and backup paths.
It requires:

```text
ml_radar = target source_observation_id schema
legacy archive DB = present and unchanged
original candidate database name = absent
canonical SHA-256 = unchanged
backup/list evidence = present and non-empty
active external connections = 0 during inspection
```

Then run the existing product gates without DB-name overrides:

```bat
python -m scripts.export.test_db_read
python -m scripts.export.test_artifact_db_read

python -m scripts.validation.check_source_observation_materialization_parity ^
  --dbname ml_radar ^
  --require-full-parity ^
  --output-dir artifacts/reports/validation/source_identity_operational_v01

python -m scripts.validation.check_artifact_api_filters --strict
```

Expected paper/materialization result:

```text
source_documents = 88,178
canonical_source_links = 88,037
resolved_links = 88,037
NULL authoritative links = 0
dangling authoritative links = 0
selected observations missing from DB = 0
full_parity_ok = true
```

Expected artifact result:

```text
artifact_entities = 7,333
artifact_observations = 38,246
paper_artifact_links = 7,430
dangling artifact links = 0
```

Expected API result:

```text
backend_mode = db
runtime_ready = true
runtime_db_connected = true
required_failed_count = 0
```

## 11. Rollback

Rollback is required when any blocking post-promotion gate fails.

Preserve the failed promoted candidate for diagnosis:

```bat
docker exec ml_radar_postgres psql -v ON_ERROR_STOP=1 -U ml_radar -d postgres -c "ALTER DATABASE ml_radar RENAME TO ml_radar_source_identity_failed_v01_<promotion_ts>;"
```

Restore the legacy operational name:

```bat
docker exec ml_radar_postgres psql -v ON_ERROR_STOP=1 -U ml_radar -d postgres -c "ALTER DATABASE ml_radar_pre_source_identity_v01_<promotion_ts> RENAME TO ml_radar;"
```

Then rerun legacy operational DB smoke. Do not delete either the failed candidate
or backup files inside the rollback action.

If rename-based rollback is impossible, restore the accepted operational dump
into a newly created `ml_radar` database as a separate recovery procedure. Do
not overwrite a database blindly.

## 12. Retention and cleanup

A green promotion does not authorize immediate deletion.

Retain:

```text
ml_radar_pre_source_identity_v01_<promotion_ts>
operational dump
candidate dump
both pg_restore list files
promotion reports
```

Cleanup requires a later explicit decision after the new operational DB has
survived normal startup, API usage, refresh validation, and at least one separate
working session.

## 13. Tracked file plan

First implementation package:

```text
docs/source_observation_materialization_operational_promotion_v0.1.md
scripts/validation/check_source_observation_materialization_promotion.py
tests/smoke/test_source_observation_materialization_promotion.py
.gitignore
```

After successful operational promotion, synchronize:

```text
docs/project_state_current_v0.1.md
docs/roadmap.md
docs/refresh_contract_v1.md
docs/architecture.md
docs/data_contracts.md
docs/provenance_semantics.md
```

## 14. Definition of Done

```text
preflight validator strict = green
operational and candidate dumps = present
pg_restore list evidence = present
controlled database rename = completed
post-promotion validator strict = green
source materialization full parity = green
artifact DB smoke = green
artifact API strict gate = green
canonical SHA-256 = unchanged
legacy operational DB = retained
rollback procedure = documented and immediately available
shared docs = synchronized
```

## 15. Explicit decision

```text
selected_promotion_strategy = validated_candidate_database_name_swap
in_place_schema_migration = rejected
canonical_rebuild = not_required
canonical_truth_mutation = forbidden
legacy_database_immediate_deletion = forbidden
validator_database_mutation = forbidden
next_slice_after_promotion = field_level_canonical_provenance_contract_v0.1
```
