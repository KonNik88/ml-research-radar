# Artifact API Ownership v1

## Document status

```text
status: active ownership note
scope: DB-backed Artifact API and document-artifact filters
canonical truth impact: none
runtime behavior change: none
```

This document records how the current Artifact API surface is wired after the
GitHub enriched filters, GitHub date filters, standalone validation report, and
DoD gate slices.

It is not a new product feature and it does not change API behavior. Its purpose
is to make the current implementation easier to review, maintain, and extend.

---

## 1. Ownership boundary

The Artifact API layer is a Postgres-backed serving/materialization layer.

```text
canonical_documents.jsonl = paper-level truth
Postgres artifact tables = derived evidence/materialization plane
GitHub / Hugging Face metadata = artifact metadata, not paper truth
Artifact API = DB-backed inspection/filter surface
```

Artifact metadata must not silently change:

- canonical paper identity;
- canonical paper fields;
- retrieval artifacts;
- Qdrant behavior;
- ranking formula;
- Discovery API scoring semantics;
- Streamlit response schemas.

---

## 2. Relevant files

### API boundary

```text
services/api/app.py
services/api/schemas.py
services/api/runtime.py
services/api/settings.py
```

### DB/materialization boundary

```text
services/api/db.py
store/sql/03_artifact_layer.sql
store/sql/04_fix_paper_artifact_links_unique.sql
```

### Validation and tests

```text
tests/integration/test_api_artifacts_db.py
tests/integration/test_api_artifacts_github_filters_db.py
tests/integration/test_api_artifacts_github_date_filters_db.py
tests/integration/test_api_documents_artifact_filters_db.py
scripts/validation/check_artifact_api_filters.py
scripts/update/check_refresh_definition_of_done.py
```

### Context-only files for this ownership slice

```text
services/api/search_service.py
services/api/discovery_service.py
services/api/logging.py
```

These files are useful for architectural context, but the current Artifact API
filter ownership surface is primarily `app.py` + `db.py` + response schemas +
validation/tests.

---

## 3. Endpoint map

### `GET /artifacts`

Owner in API layer:

```text
services/api/app.py::list_artifacts
```

Owner in DB layer:

```text
services/api/db.py::PostgresDocumentStore.list_artifacts
services/api/db.py::PostgresDocumentStore.count_artifacts
services/api/db.py::PostgresDocumentStore._build_artifact_where
services/api/db.py::PostgresDocumentStore._build_artifact_order_by
services/api/db.py::PostgresDocumentStore._normalize_artifact_row
```

Response schema:

```text
services/api/schemas.py::ArtifactListResponse
services/api/schemas.py::ArtifactEntityResponse
```

Current query parameters:

```text
provider
artifact_type
relation_type
owner
min_confidence
has_paper_links
min_stars
max_stars
language
license
archived
github_status
has_github_metadata
pushed_after
pushed_before
updated_after
updated_before
limit
offset
sort_by
```

Supported sort modes:

```text
linked_papers_desc
provider_asc
type_asc
owner_asc
last_seen_desc
stars_desc
forks_desc
pushed_desc
updated_desc
```

API-level validation:

```text
min_stars <= max_stars
pushed_after <= pushed_before
updated_after <= updated_before
FastAPI Literal validation for github_status and sort_by
```

DB-level semantics:

```text
provider              -> ae.provider
artifact_type         -> ae.artifact_type
owner                 -> ae.owner, case-insensitive exact match
relation_type         -> EXISTS paper_artifact_links for relation_type
min_confidence        -> EXISTS paper_artifact_links with confidence >= threshold
has_paper_links=true  -> EXISTS paper_artifact_links
has_paper_links=false -> NOT EXISTS paper_artifact_links
min_stars/max_stars   -> ae.stars numeric comparison; NULL values do not match
language              -> metadata.github.language, case-insensitive exact match
license               -> ae.license, case-insensitive exact match
archived              -> metadata.github.archived, requires metadata.github
status                -> metadata.github.status
has_github_metadata   -> presence/absence of metadata.github
pushed_*              -> metadata.github.pushed_at cast to timestamptz
updated_*             -> ae.updated_at materialized repository updated_at
```

Important date distinction:

```text
pushed_*  = metadata.github.pushed_at
updated_* = artifact_entities.updated_at materialized GitHub repository updated_at
```

Rows without the relevant GitHub metadata/date do not match the corresponding
GitHub metadata/date filter.

---

### `GET /artifacts/{artifact_id}`

Owner in API layer:

```text
services/api/app.py::get_artifact_detail
```

Owner in DB layer:

```text
services/api/db.py::PostgresDocumentStore.get_artifact_by_id
services/api/db.py::PostgresDocumentStore._normalize_artifact_row
```

Response schema:

```text
services/api/schemas.py::ArtifactDetailResponse
services/api/schemas.py::ArtifactEntityResponse
```

Semantics:

```text
artifact_id must exist in artifact_entities
missing artifact_id returns 404
linked_papers_count and relation_types are derived from paper_artifact_links
```

---

### `GET /artifacts/{artifact_id}/papers`

Owner in API layer:

```text
services/api/app.py::get_artifact_papers
```

Owner in DB layer:

```text
services/api/db.py::PostgresDocumentStore.get_artifact_by_id
services/api/db.py::PostgresDocumentStore.list_artifact_papers
services/api/db.py::PostgresDocumentStore.count_artifact_papers
services/api/db.py::PostgresDocumentStore._normalize_artifact_paper_link_row
```

Response schema:

```text
services/api/schemas.py::ArtifactLinkedPapersResponse
services/api/schemas.py::ArtifactLinkedPaperRow
services/api/schemas.py::SearchResultDocument
```

Query parameters:

```text
relation_type
min_confidence
limit
offset
sort_by = confidence_desc | year_desc | title_asc
```

Semantics:

```text
artifact must exist before linked papers are listed
paper rows are hydrated from canonical_documents
paper payload is normalized into SearchResultDocument shape
```

---

### `GET /documents`

Document list has two kinds of artifact-related filters.

Legacy source/canonical flag:

```text
has_code_link
```

Artifact evidence-plane filters:

```text
has_trusted_artifact
has_trusted_code_artifact
has_trusted_dataset_artifact
has_trusted_model_artifact
has_trusted_demo_artifact
artifact_provider
artifact_type
```

Owner in API layer:

```text
services/api/app.py::list_documents
```

Owner in DB layer:

```text
services/api/db.py::PostgresDocumentStore.search_documents
services/api/db.py::PostgresDocumentStore.count_documents
services/api/db.py::PostgresDocumentStore._build_document_where
services/api/db.py::PostgresDocumentStore._append_document_artifact_filters
services/api/db.py::PostgresDocumentStore._document_artifact_exists_clause
```

Semantics:

```text
has_trusted_artifact=true
  -> EXISTS any paper_artifact_links row, optionally scoped by provider/type

has_trusted_artifact=false
  -> NOT EXISTS any paper_artifact_links row

has_trusted_<relation>_artifact=true
  -> EXISTS paper_artifact_links row with relation_type=<relation>

has_trusted_<relation>_artifact=false
  -> NOT EXISTS paper_artifact_links row with relation_type=<relation>

artifact_provider / artifact_type without relation flags
  -> EXISTS artifact link scoped by provider/type
```

Important separation:

```text
has_code_link is legacy canonical/source-layer signal
has_trusted_code_artifact is artifact evidence-plane signal
```

They must not be treated as synonyms.

---

### `GET /documents/{canonical_id}/artifacts`

Owner in API layer:

```text
services/api/app.py::get_document_artifacts
```

Owner in DB layer:

```text
services/api/db.py::PostgresDocumentStore.get_document_by_id
services/api/db.py::PostgresDocumentStore.get_document_artifacts
services/api/db.py::PostgresDocumentStore.count_document_artifacts
services/api/db.py::PostgresDocumentStore._normalize_document_artifact_link_row
```

Response schema:

```text
services/api/schemas.py::DocumentArtifactsResponse
services/api/schemas.py::PaperArtifactLinkResponse
services/api/schemas.py::ArtifactEntityResponse
```

Query parameters:

```text
relation_type
provider
artifact_type
min_confidence
limit
offset
```

Semantics:

```text
canonical_id must exist in canonical_documents
missing canonical_id returns 404
each returned row links one paper_artifact_links row to one artifact_entities row
artifact payload is nested inside the link row
```

---

## 4. Response-shape ownership

Artifact response fields are centralized in `ArtifactEntityResponse`:

```text
artifact_id
artifact_type
provider
external_id
normalized_url
canonical_url
name
owner
title
description
license
stars
forks
downloads
likes
topics
tags
metadata
first_seen_at
last_seen_at
fetched_at
created_at
updated_at
linked_papers_count
relation_types
```

Normalization responsibilities in `db.py`:

```text
JSON-like fields are decoded where needed:
  topics
  tags
  metadata
  relation_types

Datetime-like fields are serialized to ISO strings:
  first_seen_at
  last_seen_at
  fetched_at
  created_at
  updated_at
```

---

## 5. Test coverage map

### `tests/integration/test_api_artifacts_db.py`

Covers:

```text
/runtime DB readiness for artifact tests
/artifacts list smoke
provider=github
relation_type=code
has_paper_links=true
/documents/{canonical_id}/artifacts
relation_type=dataset on document artifacts
missing document -> 404
```

### `tests/integration/test_api_artifacts_github_filters_db.py`

Covers:

```text
min_stars
max_stars
language case-insensitive
license case-insensitive
github_status=found
github_status=not_found
archived=false
has_github_metadata=true
has_github_metadata=false
stars_desc
forks_desc
min_stars > max_stars -> 400
invalid sort_by -> 422
```

### `tests/integration/test_api_artifacts_github_date_filters_db.py`

Covers:

```text
pushed_after with pushed_desc
updated_before with updated_desc
pushed_after > pushed_before -> 400
updated_after > updated_before -> 400
```

### `tests/integration/test_api_documents_artifact_filters_db.py`

Covers:

```text
has_trusted_artifact=true
has_trusted_code_artifact=true
has_trusted_dataset_artifact=true
artifact_provider=github
artifact_type=github_repository
combined has_trusted_code_artifact=true + artifact_provider=github
has_trusted_artifact=false
legacy has_code_link still works separately
```

---

## 6. Validation report ownership

Standalone validator:

```text
scripts/validation/check_artifact_api_filters.py
```

Command:

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m scripts.validation.check_artifact_api_filters --strict
```

Report paths:

```text
artifacts/reports/validation/artifact_api_filters_check_latest.json
artifacts/reports/validation/artifact_api_filters_check_latest.md
artifacts/reports/validation/history/artifact_api_filters_check_<timestamp>.json
artifacts/reports/validation/history/artifact_api_filters_check_<timestamp>.md
```

Validator properties:

```text
uses FastAPI TestClient
forces DB backend mode before importing app
calls no external artifact provider APIs
mutates no canonical/retrieval/DB data
writes only validation reports
```

Validator check groups:

```text
runtime DB readiness
provider=github artifacts
github metadata presence
github_status=found
stars/forks sorting
min_stars filter
language filter
archived=false filter
pushed date filter/sort
updated date filter/sort
invalid date range errors
artifact detail
artifact linked papers
documents with trusted artifacts
documents filtered by artifact_provider=github
document artifacts endpoint scoped by provider
```

DoD integration:

```bat
python -m scripts.update.check_refresh_definition_of_done ^
  --require-artifacts ^
  --require-github-enrichment ^
  --require-artifact-api-filters
```

DoD must read the latest report. It must not run the Artifact API validator
itself.

---

## 7. Invariants

### Artifact truth boundary

```text
artifact_entities / paper_artifact_links are not canonical paper truth
GitHub/Hugging Face metadata is artifact metadata only
Artifact API filters must not alter canonical_documents.jsonl
```

### Runtime boundary

```text
Artifact API is DB-backed
ML_RADAR_SEARCH_BACKEND=db is required for Artifact API filter validation
DB backend does not support dense/hybrid /search
Qdrant is irrelevant for Artifact API correctness
```

### Date metadata boundary

```text
pushed_at lives under metadata.github.pushed_at
updated_at is materialized as artifact_entities.updated_at
rows missing relevant GitHub metadata/date do not match date filters
```

### Document-artifact boundary

```text
has_code_link is legacy canonical/source-layer signal
has_trusted_code_artifact is artifact evidence-plane signal
artifact_provider/artifact_type filters operate through paper_artifact_links + artifact_entities
```

### Validation boundary

```text
integration tests verify endpoint-level behavior
check_artifact_api_filters.py verifies reportable operational behavior
check_refresh_definition_of_done.py aggregates the latest report as optional/required gate
```

---

## 8. Known extension points

### Safe future additions

```text
new artifact sort modes
new provider metadata filters
new provider-specific validation blocks
more document-artifact relation filters
small API docs sync
DoD optional/required gates for new validation reports
```

### Changes requiring more care

```text
changing response schemas
changing artifact_id normalization
changing relation_type taxonomy
changing canonical document fields based on artifact metadata
using artifact metadata in ranking formulas
promoting Artifact API signals into Discovery ranking profiles
adding live external provider calls to request path
```

### Likely next product-level slice, if desired later

```text
Discovery/API/UI exposure of artifact freshness signals
```

But this should be a separate product/evaluation slice, not part of Artifact API
ownership documentation.

---

## 9. Standard validation commands

Artifact API regression tests:

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m pytest tests/integration/test_api_artifacts_db.py tests/integration/test_api_artifacts_github_filters_db.py tests/integration/test_api_artifacts_github_date_filters_db.py tests/integration/test_api_documents_artifact_filters_db.py tests/integration/test_api_github_enrichment_db.py -q
```

Standalone Artifact API filter validator:

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m scripts.validation.check_artifact_api_filters --strict
```

DoD with Artifact API filters gate:

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m scripts.update.check_refresh_definition_of_done ^
  --require-artifacts ^
  --require-github-enrichment ^
  --require-artifact-api-filters
```

Expected green state:

```text
ok = true
required_failed_count = 0
dod_passed = true
```

---

## 10. Operational note

This ownership document should be updated when one of the following changes:

```text
/artifacts query parameters
/artifacts sort modes
/documents artifact filters
artifact response shape
artifact DB SQL semantics
Artifact API validation report checks
DoD flags related to artifacts
```

It does not need to change for unrelated Discovery API, Qdrant, retrieval,
dataset-release, or Streamlit-only UI changes.
