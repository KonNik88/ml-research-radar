# Source Observation Materialization Identity Design v0.1

## Status

```text
design_status = accepted_candidate_design
implementation_status = not_started
migration_status = not_started
promotion_status = not_started
canonical_truth_mutation = forbidden
reconciliation_behavior_change = not_required
public_api_change = not_required
```

This document defines the candidate physical identity for normalized paper-source
observations in the PostgreSQL serving/materialization layer.

It is a design contract only. It does not modify PostgreSQL, canonical JSONL,
reconciliation, retrieval artifacts, Qdrant, graphs, artifact materialization,
API response schemas, or public-release policy.

---

## 1. Purpose

The current PostgreSQL paper materialization cannot represent every selected
normalized source observation because `source_documents.doc_id` is a global
primary key even though legacy `doc_id` values can be shared by observations
from different source families.

The purpose of this design is to strengthen the existing:

```text
source_documents
canonical_source_links
```

without creating a parallel source-observation data plane and without changing
canonical paper truth.

The selected design operationalizes the already validated deterministic:

```text
source_observation_id
```

as the physical source-observation identity in PostgreSQL.

---

## 2. Architectural boundaries

The following project invariants remain unchanged.

```text
data/analytics/reconciled/canonical_documents.jsonl = canonical paper truth
data/normalized/<source>/                            = source observations
PostgreSQL                                           = rebuildable serving layer
retrieval / Qdrant / graphs                          = derived layers
artifact layer                                       = separate evidence plane
```

This slice must not:

- modify canonical IDs or reconciliation keys;
- change reconciliation grouping or field-selection behavior;
- add `source_observation_id` to the public canonical contract;
- add `source_observation_id` to public API response schemas;
- rename artifact-layer `source_doc_id`;
- rebuild retrieval artifacts or Qdrant collections;
- change graph contracts or graph outputs;
- change Semantic Scholar redistribution policy;
- introduce a second source-observation store alongside `source_documents`.

---

## 3. Accepted audit baseline

The accepted Reconciliation Evidence Audit v0.1 baseline is:

```text
selected normalized source observations = 88,178
canonical provenance observations       = 88,037
non-contributing observations            = 141

PostgreSQL source_documents              = 70,244
PostgreSQL canonical_source_links        = 88,037
resolved canonical source links          = 70,145
NULL canonical source links              = 17,892
dangling non-NULL links                  = 0
```

The audit also established:

```text
source_observation_id conflicts                   = 0
source_observation_id cross-source collisions     = 0
legacy doc_id cross-source collision values       = 9,119
all 141 non-contributing observations explained   = true
parallel source-observation plane required         = false
```

The target is not to create links for all 88,178 observations.

The correct cardinalities are:

```text
source_documents        = all 88,178 selected observations
canonical_source_links  = only 88,037 contributing provenance observations
```

The 141 valid non-contributing observations must exist in `source_documents`
without receiving synthetic canonical links.

---

## 4. Current implementation and failure mode

### 4.1 Current schema

The current schema uses:

```sql
source_documents.doc_id TEXT PRIMARY KEY
```

and:

```sql
canonical_source_links.doc_id
    REFERENCES source_documents(doc_id)
    ON DELETE SET NULL
```

### 4.2 Current exporter

The current exporter inserts normalized observations with:

```sql
ON CONFLICT (doc_id) DO UPDATE
```

Canonical-source links are then resolved by querying `source_documents` using
`source` plus the first available legacy lookup field and returning `doc_id`.

### 4.3 Failure mechanism

Legacy `doc_id` is paper-oriented and can be identical across provider
observations describing the same paper.

Therefore:

```text
OpenAlex observation
Semantic Scholar observation
Crossref observation
```

can share one legacy `doc_id`.

With `doc_id` as the primary key, later source rows overwrite or reuse the same
physical row. Canonical provenance still contains separate source observations,
but PostgreSQL cannot resolve every link to the correct physical observation.

This is a physical materialization identity defect. It is not a canonical
reconciliation defect.

---

## 5. Existing source-observation identity contract

The accepted identity helper computes:

```text
source_observation_id = stable_hash(
    [
        "source_observation_v1",
        normalized_source,
        identity_basis,
        normalized_identity_value,
    ],
    length=32,
)
```

Identity-basis precedence is:

```text
source_record_id
→ source_id
→ source_record_url
→ source_api_url
→ legacy doc_id
→ canonical_url
```

The normalized source family is always part of the hash input.

Consequences:

- two providers cannot collapse only because they share legacy `doc_id`;
- equivalent provider-native identifier forms normalize to the same observation;
- identity is deterministic;
- identity can be built from current normalized rows and canonical provenance
  rows without changing `NormalizedDocument`;
- missing identity fails closed.

---

## 6. Design requirements

The candidate design must satisfy all of the following.

### 6.1 Identity requirements

- one selected normalized observation maps to one `source_observation_id`;
- `source_observation_id` is stable and deterministic;
- source family remains part of observation identity;
- legacy `doc_id` remains available but is not globally unique;
- source observations from different providers cannot overwrite each other.

### 6.2 Link requirements

- every canonical provenance row maps to exactly one materialized observation;
- `canonical_source_links.source_observation_id` is never NULL;
- every non-NULL observation link has referential integrity;
- duplicate `(canonical_id, source_observation_id)` pairs are rejected;
- non-contributing observations remain unlinked.

### 6.3 Compatibility requirements

- canonical JSONL remains unchanged;
- `canonical_documents.doc_ids` remains legacy paper-level diagnostic data;
- API source filtering through `canonical_source_links.source` remains valid;
- artifact-layer `source_doc_id` keeps its existing artifact evidence semantics;
- current `doc_id` values remain queryable for diagnostics;
- `--replace` continues to represent a full rebuild of paper materialization.

### 6.4 Operational requirements

- implementation is candidate-first;
- operational PostgreSQL is not altered in place during validation;
- rollback is achieved by discarding the candidate database;
- promotion requires explicit full-parity and DB/API regression evidence.

---

## 7. Options considered

### Option A — Keep `doc_id` as the primary key

```text
decision = rejected
```

Reason:

- known cross-source collisions remain;
- selected observations cannot reach full materialization parity;
- canonical links remain nullable;
- the option preserves the demonstrated defect.

### Option B — Composite primary key over source and provider fields

Example:

```text
(source, source_record_id)
```

```text
decision = rejected
```

Reason:

- provider identity fields are heterogeneous and nullable;
- identity-basis fallback would have to be duplicated in SQL;
- foreign keys would become wide and provider-dependent;
- the project already has a validated normalized identity abstraction.

### Option C — Surrogate database key plus unique `source_observation_id`

Example:

```text
id BIGSERIAL PRIMARY KEY
source_observation_id TEXT UNIQUE NOT NULL
```

```text
decision = acceptable_but_not_selected
```

This would work, but the surrogate key adds an unnecessary physical identity
when `source_observation_id` is already deterministic, compact, stable, and
validated.

A surrogate key may be reconsidered only if future storage/performance evidence
demonstrates a concrete need.

### Option D — `source_observation_id` as the primary key

```text
decision = selected
```

This is the smallest design that directly represents the project-level
source-observation identity and resolves the proven collision mechanism.

---

## 8. Selected target schema

The SQL below is normative design pseudocode. Exact column order and migration
syntax belong to the implementation slice.

### 8.1 `source_documents`

```sql
CREATE TABLE source_documents (
    source_observation_id TEXT PRIMARY KEY,

    doc_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    source_record_id TEXT,
    source_record_url TEXT,
    source_api_url TEXT,
    canonical_url TEXT,

    -- existing metadata columns remain unchanged
    ...
);
```

Normative semantics:

```text
source_observation_id = physical/project source-observation identity
doc_id                = legacy paper-oriented compatibility field
```

`source_documents.doc_id`:

- is required for the current normalized baseline;
- is non-unique;
- is not a foreign-key target;
- may be used for diagnostics and compatibility lookups;
- must never be used alone to identify a source observation.

No `identity_basis` or normalized identity-value columns are required in v0.1.
They remain deterministically recoverable from the preserved source identity
fields.

`source_documents` is an evidence/materialization table, not canonical truth.
Incomplete source metadata must remain representable:

- `source_id` may be NULL when another accepted identity basis is available;
- `title` may be NULL for an incomplete but identity-valid observation;
- missing bibliographic metadata must not cause an otherwise valid selected
  observation to disappear from materialization.

### 8.2 `canonical_source_links`

```sql
CREATE TABLE canonical_source_links (
    id BIGSERIAL PRIMARY KEY,

    canonical_id TEXT NOT NULL
        REFERENCES canonical_documents(canonical_id)
        ON DELETE CASCADE,

    source_observation_id TEXT NOT NULL
        REFERENCES source_documents(source_observation_id)
        ON DELETE RESTRICT,

    doc_id TEXT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    source_record_id TEXT,
    source_record_url TEXT,
    canonical_url TEXT,

    -- existing provenance columns remain unchanged
    ...,

    UNIQUE (canonical_id, source_observation_id)
);
```

Normative semantics:

- `source_observation_id` is the only source-row foreign key;
- link `doc_id` is an optional denormalized legacy diagnostic copy;
- link `doc_id` is nullable and is not a foreign key;
- `ON DELETE RESTRICT` prevents accidental deletion of a linked observation;
- full `--replace` rebuild remains free to truncate dependent paper tables in
  the established order.

### 8.3 Required indexes

```sql
CREATE INDEX idx_source_documents_doc_id
    ON source_documents (doc_id);

CREATE INDEX idx_source_documents_source_record_id
    ON source_documents (source, source_record_id);

CREATE INDEX idx_source_documents_source_record_url
    ON source_documents (source, source_record_url)
    WHERE source_record_url IS NOT NULL;

CREATE INDEX idx_canonical_source_links_canonical_id
    ON canonical_source_links (canonical_id);

CREATE INDEX idx_canonical_source_links_source_observation_id
    ON canonical_source_links (source_observation_id);

CREATE INDEX idx_canonical_source_links_source
    ON canonical_source_links (source);
```

The legacy:

```text
idx_canonical_source_links_doc_id
```

may remain temporarily only for compatibility diagnostics. It is not required
for referential integrity and must not be used as the primary link join.

---

## 9. Exporter contract

### 9.1 Source rows

For every selected normalized row, the exporter must:

1. build identity with
   `build_source_observation_identity_from_mapping`;
2. add `source_observation_id` to the database row;
3. insert into `source_documents`;
4. use:

```sql
ON CONFLICT (source_observation_id) DO UPDATE
```

The identity slice must not opportunistically redesign all existing source-field
upsert semantics. Broadening which metadata columns are updated is a separate
review unless required to preserve current behavior.

### 9.2 Canonical-source links

For every row in `canonical_documents.sources`, the exporter must:

1. build the same deterministic `source_observation_id` directly from the
   provenance row;
2. insert that value into `canonical_source_links`;
3. rely on the foreign key to fail closed when the observation was not
   materialized;
4. preserve legacy provenance fields, including `doc_id`, on the link row.

The legacy iterative:

```text
resolve_source_doc_id(...)
```

lookup is removed from the primary link path.

The exporter must not silently insert a NULL observation link.

### 9.3 Selected versus contributing rows

The exporter continues to load:

```text
source_documents
= all rows from the exact selected timestamped normalized snapshots
```

It continues to load:

```text
canonical_source_links
= only rows present in canonical provenance
```

It must not infer canonical links for the 141 non-contributing observations.

### 9.4 Replace behavior

`--replace` remains the accepted full materialization mode.

Because the paper-table truncate can cascade into dependent artifact links, the
existing operational rule remains:

```text
paper export --replace
→ paper materialization validation
→ artifact export
→ artifact validation
```

---

## 10. Consumer compatibility matrix

| Consumer | Current dependency | Candidate impact |
|---|---|---|
| `services/api/db.py` | filters canonical IDs by `canonical_source_links.source` | no public query change required |
| DB lexical/document endpoints | read `canonical_documents` | unaffected |
| artifact tables and API | use artifact `source_doc_id` and `canonical_id` | no rename or schema change in this slice |
| citation/reference graph | file-backed canonical IDs | unaffected |
| retrieval and Qdrant | canonical/retrieval artifacts | unaffected |
| `capture_refresh_baseline.py` | table counts | compatible; expected source count changes |
| `build_known_issues_snapshot.py` | reports legacy materialization caveat | update after parity promotion |
| materialization parity validator | currently supports legacy and candidate evidence | update primary joins to `source_observation_id`; retain legacy diagnostics |
| audit package builder | derives observation identity from source fields | compatible |
| public dataset exporter | canonical projection | unaffected |

No public API response field is added in v0.1.

A future private source-drilldown endpoint may expose
`source_observation_id`, but that is outside this implementation.

---

## 11. Candidate rebuild strategy

### 11.1 Selected strategy

```text
strategy = clean candidate database rebuild
in_place_alter_operational_db = false
```

PostgreSQL is a rebuildable serving layer. The current database has already
lost rows through key collisions, so an in-place migration cannot reconstruct
the missing observations from database state alone.

The candidate must be rebuilt from:

```text
canonical_documents.jsonl
+
exact selected timestamped normalized snapshots
```

### 11.2 Candidate sequence

1. create a separate candidate database or isolated equivalent;
2. apply candidate `01_schema.sql`;
3. apply candidate `02_indexes.sql`;
4. run paper export with `--replace`;
5. run materialization parity with `--require-full-parity`;
6. run DB smoke and API regression;
7. run artifact export because paper replace can cascade;
8. run artifact DB/API regression;
9. compare operational and candidate counts/contracts;
10. make an explicit promotion decision.

The implementation must not point the normal API runtime at the candidate
database before its gates pass.

### 11.3 Promotion

Promotion mechanics may use environment/config switching or a controlled
database replacement. The selected mechanism must preserve a rollback target.

Promotion is not implicit in a green exporter run.

---

## 12. Rollback and failure isolation

Before promotion:

```text
rollback = discard candidate database
operational database = unchanged
```

After promotion:

- preserve the previous operational database or a restorable backup;
- revert runtime DB configuration to the previous database if regression fails;
- do not roll back canonical JSONL because this slice never changes it;
- rebuild artifact materialization after any paper-table replace;
- retain validation reports for both candidate and promoted states.

No down-migration that attempts to collapse observations back into legacy
`doc_id` identity is required.

---

## 13. Acceptance gates

### 13.1 Static schema/export contract

The implementation must prove:

- `source_documents.source_observation_id` exists and is the primary key;
- `source_documents.doc_id` exists and is non-unique;
- `canonical_source_links.source_observation_id` is NOT NULL;
- the link has a foreign key to
  `source_documents(source_observation_id)`;
- `UNIQUE (canonical_id, source_observation_id)` exists;
- exporter conflict target is `source_observation_id`;
- exporter no longer resolves primary links through legacy `doc_id`;
- current source identity helper is reused, not reimplemented in SQL.

### 13.2 Full materialization parity

The required command is:

```bash
python -m scripts.validation.check_source_observation_materialization_parity \
  --require-full-parity
```

Expected candidate evidence:

```text
source_documents                             = 88,178
canonical_source_links                       = 88,037
resolved_links                               = 88,037
NULL links                                   = 0
dangling links                               = 0
selected observations missing from DB        = 0
unexpected observations in DB                = 0
canonical pairs missing from DB              = 0
DB pairs missing from canonical provenance   = 0
source_observation_id columns present        = true
full_parity_ok                               = true
required_failed_count                        = 0
```

### 13.3 Regression gates

Required implementation tests:

- source-row identity/upsert unit tests;
- canonical-link identity unit tests;
- cross-source shared-`doc_id` exporter regression;
- duplicate canonical-observation pair rejection;
- missing source observation fails closed;
- candidate schema constraint inspection;
- `--replace` materialization smoke;
- DB source-filter regression;
- `/documents` DB regression;
- DB lexical `/search` regression;
- artifact re-export and artifact API regression;
- canonical corpus fingerprint unchanged;
- retrieval manifest/build unchanged unless independently rebuilt.

### 13.4 Promotion gate

Promotion requires all of:

```text
full parity green
DB/API regressions green
artifact restoration/regressions green
canonical fingerprint unchanged
no unexpected schema consumers
explicit human promotion decision
rollback target preserved
```

---

## 14. Implementation file plan

The next implementation slice is expected to change:

```text
store/sql/01_schema.sql
store/sql/02_indexes.sql
scripts/export/export_postgres_v1.py
scripts/validation/check_source_observation_materialization_parity.py
tests/smoke/<new exporter/schema tests>
```

It may also update after successful promotion:

```text
scripts/validation/build_known_issues_snapshot.py
docs/refresh_contract_v1.md
docs/project_state_current_v0.1.md
docs/roadmap.md
```

The implementation must not change unrelated artifact, graph, retrieval, Qdrant,
ranking, cluster, or API response contracts.

---

## 15. Explicit decision

```text
parallel_source_observation_plane = not_needed

selected_source_identity =
    source_observation_id

source_documents_primary_key =
    source_observation_id

legacy_doc_id =
    preserved_non_unique_compatibility_field

canonical_source_links_foreign_key =
    source_observation_id

canonical_source_link_pair_uniqueness =
    canonical_id + source_observation_id

migration_strategy =
    candidate_database_rebuild

canonical_contract_change =
    not_required_initially

canonical_truth_mutation =
    forbidden

reconciliation_behavior_change =
    not_required

public_api_change =
    not_required

field_level_provenance =
    separate_future_slice

next_slice =
    source_observation_materialization_identity_implementation_v0.1
```
