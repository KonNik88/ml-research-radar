# API Reference

## Purpose

This document describes the current public API surface of ML Research Radar.

The API currently supports two backend modes:

```text
file
db
```

The two backends intentionally expose the same top-level API shape where possible, but they are not fully symmetric.

---

## Backend modes

## File backend

Role:

```text
retrieval-oriented runtime
```

Current characteristics:

- loads retrieval manifest
- loads canonical documents from JSONL
- loads lexical retrieval artifacts
- loads dense retrieval artifacts
- loads embedding model
- supports lexical search
- supports dense search
- supports hybrid search

Current primary endpoint:

```text
GET /search
```

Supported search modes:

```text
lexical
dense
hybrid
```

---

## DB backend

Role:

```text
materialized serving runtime over Postgres
```

Current characteristics:

- loads Postgres-backed runtime
- checks DB connectivity
- serves canonical documents from Postgres
- serves artifact entities and paper-artifact links from Postgres
- supports browse/filter access
- supports DB lexical search v1

Current DB-backed endpoints:

```text
GET /documents
GET /artifacts
GET /documents/{canonical_id}/artifacts
GET /search?mode=lexical
```

DB backend does not currently support:

```text
/search?mode=dense
/search?mode=hybrid
```

Unsupported modes return a structured error.

---

## Runtime configuration

The backend mode is controlled by:

```text
ML_RADAR_SEARCH_BACKEND
```

Example:

```bat
set ML_RADAR_SEARCH_BACKEND=db
```

Valid values:

```text
file
db
```

---

## Error response

Structured API errors use the following shape:

```json
{
  "error_code": "bad_request",
  "message": "human-readable error message",
  "details": null
}
```

Typical error codes:

```text
bad_request
validation_error
runtime_not_ready
file_not_found
internal_error
```

Some FastAPI-native errors, such as explicit `HTTPException(status_code=404)`, may return the standard FastAPI shape:

```json
{
  "detail": "Document not found: <canonical_id>"
}
```

---

# Endpoints

---

## `GET /health`

Backend-aware readiness check.

### Purpose

Returns whether the current runtime is ready and which components are active.

### Response fields

```text
status
backend_mode
ready
build_id
corpus_doc_count
embedding_model_name
checks
```

### Example response: DB backend

```json
{
  "status": "ok",
  "backend_mode": "db",
  "ready": true,
  "build_id": "db-runtime",
  "corpus_doc_count": 30008,
  "embedding_model_name": null,
  "checks": {
    "manifest_loaded": false,
    "documents_loaded": false,
    "lexical_artifacts_loaded": false,
    "dense_artifacts_loaded": false,
    "embedding_model_loaded": false,
    "db_store_loaded": true,
    "db_connected": true
  }
}
```

### Notes

File backend readiness depends on file retrieval artifacts.

DB backend readiness depends on Postgres store availability and DB connectivity.

---

## `GET /info`

Returns API-level information and current runtime information.

### Response fields

```text
api_title
api_version
backend_mode
build_id
corpus_doc_count
embedding_model_name
artifacts_root
loaded_components
```

---

## `GET /runtime`

Returns a detailed runtime snapshot.

### Response fields

```text
ready
backend_mode
build_id
corpus_doc_count
embedding_model_name
artifacts_root
loaded_components
db_connected
last_load_error
last_loaded_at
last_reload_at
model_reused
current_model_name
```

### File backend semantics

```text
build_id comes from retrieval manifest
embedding_model_name is populated
file retrieval components are loaded
db_connected = false
```

### DB backend semantics

```text
build_id = db-runtime
embedding_model_name = null
db_store is loaded
db_connected indicates DB reachability
file retrieval components are not loaded
```

---

## `POST /reload`

Reloads the current runtime.

### File backend reloads

```text
latest manifest
canonical documents
lexical artifacts
dense artifacts
embedding model
```

### DB backend reloads

```text
Postgres-backed runtime
DB store connectivity
document count snapshot
```

### Example response

```json
{
  "status": "reloaded",
  "backend_mode": "db",
  "message": "DB backend runtime reloaded successfully",
  "build_id": "db-runtime",
  "corpus_doc_count": 30008,
  "embedding_model_name": null,
  "model_reused": false,
  "last_reload_at": "2026-04-26T10:00:00+00:00"
}
```

---

# Search API

---

## `GET /search`

Main relevance-search endpoint.

### Query parameters

```text
query
mode
top_k
rank
year_from
year_to
category
source
publication_type
venue
open_access
has_code_link
offset
sort_by
```

### Parameter details

| parameter | type | default | notes |
|---|---:|---:|---|
| `query` | string | required | search query |
| `mode` | lexical / dense / hybrid | hybrid | DB backend supports lexical only |
| `top_k` | int | settings default | capped by max_top_k |
| `rank` | bool | false | apply ranking layer |
| `year_from` | int | null | lower year bound |
| `year_to` | int | null | upper year bound |
| `category` | string | null | category/concept/tag-like filter |
| `source` | string | null | source filter |
| `publication_type` | string | null | publication type filter |
| `venue` | string | null | venue/journal/conference/publisher filter |
| `open_access` | bool | null | open-access filter |
| `has_code_link` | bool | null | legacy canonical/source-layer code link flag |
| `offset` | int | 0 | pagination offset |
| `sort_by` | relevance / year_desc / year_asc | relevance | DB lexical search respects relevance/year sorting |

### File backend support

Supported modes:

```text
lexical
dense
hybrid
```

### DB backend support

Supported mode:

```text
lexical
```

Unsupported DB modes:

```text
dense
hybrid
```

These return `400 Bad Request`.

### Example

```http
GET /search?query=graph%20neural%20networks&mode=lexical&top_k=5
```

### Response shape

```json
{
  "query": "graph neural networks",
  "mode": "lexical",
  "top_k": 5,
  "rank_applied": false,
  "build_id": "db-runtime",
  "meta": {
    "build_id": "db-runtime",
    "result_count": 5,
    "rank_applied": false,
    "timing_ms": {
      "retrieve_ms": 3.1,
      "total_ms": 3.8
    },
    "debug_enabled": true,
    "applied_filters": {
      "year_from": null,
      "year_to": null,
      "category": null,
      "source": null,
      "publication_type": null,
      "venue": null,
      "open_access": null,
      "has_code_link": null
    },
    "retrieved_candidates_before_filters": 42,
    "retrieved_candidates_after_filters": 42,
    "offset": 0,
    "returned_count": 5,
    "sort_by": "relevance"
  },
  "results": [
    {
      "document": {
        "canonical_id": "...",
        "title": "...",
        "abstract": "...",
        "authors": [],
        "year": 2024,
        "doi": "...",
        "arxiv_id": null,
        "openalex_id": null,
        "primary_category": null,
        "categories": [],
        "concepts": [],
        "keywords": [],
        "tags": [],
        "venue": null,
        "journal": null,
        "conference": null,
        "publisher": null,
        "publication_type": null,
        "language": "en",
        "landing_page_url": null,
        "pdf_url": null,
        "repo_url": null,
        "open_access": null,
        "has_code_link": false,
        "code_links": [],
        "cited_by_count": null,
        "references_count": null,
        "source_count": 1,
        "unique_source_count": 1,
        "metadata_completeness_score": 0.7,
        "is_preprint": false,
        "is_review": false,
        "is_survey": false,
        "is_withdrawn": false
      },
      "retrieval": {
        "score": 35.0,
        "lexical_score": null,
        "dense_score": null,
        "hybrid_score": null
      },
      "ranking": null
    }
  ]
}
```

---

# Documents API

---

## `GET /documents`

Browse/filter endpoint for canonical documents stored in Postgres.

DB backend only.

### Purpose

Provides deterministic browse/filter access over canonical documents.

It is not a relevance-search endpoint.

For relevance search, use:

```text
GET /search
```

### Query parameters

```text
query
limit
offset
year_from
year_to
category
source
publication_type
venue
open_access
has_code_link
has_trusted_artifact
has_trusted_code_artifact
has_trusted_dataset_artifact
has_trusted_model_artifact
has_trusted_demo_artifact
artifact_provider
artifact_type
sort_by
```

### Parameter details

| parameter | type | default | notes |
|---|---:|---:|---|
| `query` | string | null | simple text query over title/abstract/venue/publisher |
| `limit` | int | 10 | max 100 |
| `offset` | int | 0 | pagination offset |
| `year_from` | int | null | lower year bound |
| `year_to` | int | null | upper year bound |
| `category` | string | null | matches `categories` JSONB |
| `source` | string | null | source family filter through canonical source links |
| `publication_type` | string | null | publication type |
| `venue` | string | null | normalized venue equality |
| `open_access` | bool | null | `is_open_access` DB field |
| `has_code_link` | bool | null | legacy canonical/source-layer code link flag |
| `has_trusted_artifact` | bool | null | any trusted artifact link |
| `has_trusted_code_artifact` | bool | null | trusted artifact relation `code` |
| `has_trusted_dataset_artifact` | bool | null | trusted artifact relation `dataset` |
| `has_trusted_model_artifact` | bool | null | trusted artifact relation `model` |
| `has_trusted_demo_artifact` | bool | null | trusted artifact relation `demo` |
| `artifact_provider` | string | null | trusted artifact provider filter |
| `artifact_type` | string | null | trusted artifact type filter |
| `sort_by` | year_desc / year_asc / title_asc | year_desc | deterministic ordering |

### Legacy vs trusted artifact filters

Legacy field:

```text
has_code_link
```

This uses canonical/source-layer fields.

Trusted artifact-layer filters:

```text
has_trusted_artifact
has_trusted_code_artifact
has_trusted_dataset_artifact
has_trusted_model_artifact
has_trusted_demo_artifact
artifact_provider
artifact_type
```

These use:

```text
paper_artifact_links
JOIN artifact_entities
```

Do not treat `has_code_link` and `has_trusted_code_artifact` as equivalent.

### Examples

Documents with any trusted artifact:

```http
GET /documents?has_trusted_artifact=true&limit=10
```

Documents with trusted code artifacts:

```http
GET /documents?has_trusted_code_artifact=true&limit=10
```

Documents with trusted GitHub artifacts:

```http
GET /documents?artifact_provider=github&limit=10
```

Documents with trusted GitHub code artifacts:

```http
GET /documents?has_trusted_code_artifact=true&artifact_provider=github&limit=10
```

Documents without trusted artifacts:

```http
GET /documents?has_trusted_artifact=false&limit=10
```

### Response shape

```json
{
  "total": 451,
  "offset": 0,
  "limit": 10,
  "sort_by": "year_desc",
  "results": [
    {
      "canonical_id": "...",
      "title": "...",
      "abstract": "...",
      "authors": [],
      "year": 2016,
      "doi": null,
      "arxiv_id": "...",
      "openalex_id": null,
      "primary_category": null,
      "categories": [],
      "concepts": [],
      "keywords": [],
      "tags": [],
      "venue": null,
      "journal": null,
      "conference": null,
      "publisher": null,
      "publication_type": "preprint",
      "language": "en",
      "landing_page_url": "...",
      "pdf_url": "...",
      "repo_url": null,
      "open_access": true,
      "has_code_link": false,
      "code_links": [],
      "cited_by_count": null,
      "references_count": null,
      "source_count": 1,
      "unique_source_count": 1,
      "metadata_completeness_score": 0.5833,
      "is_preprint": true,
      "is_review": false,
      "is_survey": false,
      "is_withdrawn": false
    }
  ]
}
```

---

# Artifacts API

---

## `GET /artifacts`

Browse/filter endpoint for artifact entities stored in Postgres.

DB backend only.

### Purpose

Provides deterministic browse/filter access over artifact entities and their trusted paper-link summary.

### Query parameters

```text
provider
artifact_type
relation_type
owner
min_confidence
has_paper_links
limit
offset
sort_by
```

### Parameter details

| parameter | type | default | notes |
|---|---:|---:|---|
| `provider` | string | null | e.g. github, figshare, zenodo |
| `artifact_type` | string | null | e.g. github_repository |
| `relation_type` | string | null | code, dataset, model, demo |
| `owner` | string | null | namespace/owner when available |
| `min_confidence` | float | null | trusted link confidence threshold |
| `has_paper_links` | bool | null | whether artifact participates in trusted links |
| `limit` | int | 20 | max 100 |
| `offset` | int | 0 | pagination offset |
| `sort_by` | linked_papers_desc / provider_asc / type_asc / owner_asc / last_seen_desc | linked_papers_desc | deterministic ordering |

### Examples

List artifacts:

```http
GET /artifacts?limit=20
```

GitHub artifacts:

```http
GET /artifacts?provider=github&limit=20
```

Code artifacts:

```http
GET /artifacts?relation_type=code&limit=20
```

Artifacts with trusted paper links:

```http
GET /artifacts?has_paper_links=true&limit=20
```

### Response shape

```json
{
  "total": 491,
  "offset": 0,
  "limit": 3,
  "sort_by": "linked_papers_desc",
  "results": [
    {
      "artifact_id": "...",
      "artifact_type": "github_repository",
      "provider": "github",
      "external_id": "owner/repo",
      "normalized_url": "https://github.com/owner/repo",
      "canonical_url": "https://github.com/owner/repo",
      "name": "repo",
      "owner": "owner",
      "title": null,
      "description": null,
      "license": null,
      "stars": null,
      "forks": null,
      "downloads": null,
      "likes": null,
      "topics": [],
      "tags": [],
      "metadata": {
        "first_extraction_stage": "internal_artifact_extraction_v1"
      },
      "first_seen_at": "2026-04-25T16:02:37.224899+00:00",
      "last_seen_at": "2026-04-25T16:02:37.224899+00:00",
      "fetched_at": null,
      "created_at": null,
      "updated_at": null,
      "linked_papers_count": 1,
      "relation_types": ["code"]
    }
  ]
}
```

---

## `GET /documents/{canonical_id}/artifacts`

Returns trusted artifacts linked to one canonical document.

DB backend only.

### Path parameters

```text
canonical_id
```

### Query parameters

```text
relation_type
provider
artifact_type
min_confidence
limit
offset
```

### Parameter details

| parameter | type | default | notes |
|---|---:|---:|---|
| `relation_type` | string | null | code, dataset, model, demo |
| `provider` | string | null | e.g. github |
| `artifact_type` | string | null | e.g. github_repository |
| `min_confidence` | float | null | link confidence threshold |
| `limit` | int | 100 | max 500 |
| `offset` | int | 0 | pagination offset |

### Examples

All artifacts for a document:

```http
GET /documents/0205aa895017eb983683114d12938f11/artifacts
```

Only dataset artifacts:

```http
GET /documents/0205aa895017eb983683114d12938f11/artifacts?relation_type=dataset
```

Only GitHub artifacts:

```http
GET /documents/<canonical_id>/artifacts?provider=github
```

### Response shape

```json
{
  "canonical_id": "0205aa895017eb983683114d12938f11",
  "total": 2,
  "results": [
    {
      "link_id": "...",
      "canonical_id": "0205aa895017eb983683114d12938f11",
      "artifact_id": "...",
      "relation_type": "dataset",
      "confidence": 1.0,
      "evidence_source": "canonical:canonical",
      "evidence_url": "https://figshare.com/articles/...",
      "source_field": "dataset_links",
      "source_doc_id": null,
      "metadata": {
        "observation_ids": ["..."],
        "evidence": [
          {
            "observation_id": "...",
            "source_layer": "canonical",
            "source_name": "canonical",
            "source_doc_id": null,
            "source_field": "dataset_links",
            "evidence_source": "canonical:canonical",
            "raw_url": "https://figshare.com/articles/...",
            "normalized_url": "https://figshare.com/articles/...",
            "confidence": 1.0,
            "provider": "figshare",
            "artifact_type": "figshare_artifact"
          }
        ],
        "provider": "figshare",
        "artifact_type": "figshare_artifact",
        "extraction_stage": "internal_artifact_extraction_v1"
      },
      "created_at": "2026-04-25T16:02:37.224899+00:00",
      "updated_at": "2026-04-25T16:02:37.224899+00:00",
      "artifact": {
        "artifact_id": "...",
        "artifact_type": "figshare_artifact",
        "provider": "figshare",
        "external_id": "https://figshare.com/articles/...",
        "normalized_url": "https://figshare.com/articles/...",
        "canonical_url": "https://figshare.com/articles/...",
        "name": "6475511",
        "owner": null,
        "title": null,
        "description": null,
        "license": null,
        "stars": null,
        "forks": null,
        "downloads": null,
        "likes": null,
        "topics": [],
        "tags": [],
        "metadata": {
          "first_extraction_stage": "internal_artifact_extraction_v1"
        },
        "first_seen_at": "2026-04-25T16:02:37.224899+00:00",
        "last_seen_at": "2026-04-25T16:02:37.224899+00:00",
        "fetched_at": null,
        "created_at": null,
        "updated_at": null,
        "linked_papers_count": null,
        "relation_types": []
      }
    }
  ]
}
```

### Missing document

If the canonical document does not exist, the endpoint returns:

```json
{
  "detail": "Document not found: <canonical_id>"
}
```

with status:

```text
404
```

---

# Current capability matrix

| Endpoint | file backend | db backend |
|---|---:|---:|
| `GET /health` | yes | yes |
| `GET /info` | yes | yes |
| `GET /runtime` | yes | yes |
| `POST /reload` | yes | yes |
| `GET /search?mode=lexical` | yes | yes |
| `GET /search?mode=dense` | yes | no |
| `GET /search?mode=hybrid` | yes | no |
| `GET /documents` | no | yes |
| `GET /artifacts` | no | yes |
| `GET /documents/{canonical_id}/artifacts` | no | yes |

---

# Current baseline values

Current DB-backed corpus baseline:

```text
canonical_documents = 30008
```

Current artifact baseline:

```text
artifact_entities = 491
artifact_observations = 1646
paper_artifact_links = 492
documents with trusted artifacts = 451
artifact entities participating in trusted links = 482
```

Current document artifact filter counts:

```text
has_trusted_artifact=true                  451
has_trusted_code_artifact=true             215
has_trusted_dataset_artifact=true          154
artifact_provider=github                   111
has_trusted_code_artifact=true + github    111
has_trusted_artifact=false                 29557
```

---

# API smoke tests

Run with DB backend:

```bat
set ML_RADAR_SEARCH_BACKEND=db
```

Runtime:

```bat
python -c "import os; os.environ['ML_RADAR_SEARCH_BACKEND']='db'; from fastapi.testclient import TestClient; from services.api.app import app; client=TestClient(app); client.__enter__(); r=client.get('/runtime'); print(r.status_code); print(r.json()); client.__exit__(None,None,None)"
```

Artifacts:

```bat
python -c "import os; os.environ['ML_RADAR_SEARCH_BACKEND']='db'; from fastapi.testclient import TestClient; from services.api.app import app; client=TestClient(app); client.__enter__(); r=client.get('/artifacts', params={'limit':3}); print(r.status_code); print(r.json()); client.__exit__(None,None,None)"
```

Document artifacts:

```bat
python -c "import os; os.environ['ML_RADAR_SEARCH_BACKEND']='db'; from fastapi.testclient import TestClient; from services.api.app import app; client=TestClient(app); client.__enter__(); r=client.get('/documents/0205aa895017eb983683114d12938f11/artifacts'); print(r.status_code); print(r.json()); client.__exit__(None,None,None)"
```

Documents with artifact filters:

```bat
python -c "import os; os.environ['ML_RADAR_SEARCH_BACKEND']='db'; from fastapi.testclient import TestClient; from services.api.app import app; client=TestClient(app); client.__enter__(); r=client.get('/documents', params={'has_trusted_artifact':'true','limit':3}); print(r.status_code); print(r.json()); client.__exit__(None,None,None)"
```

---

# Integration tests

Artifact API:

```bat
python -m pytest tests/integration/test_api_artifacts_db.py -q
```

Document artifact filters:

```bat
python -m pytest tests/integration/test_api_documents_artifact_filters_db.py -q
```

Recommended DB/API artifact regression:

```bat
python -m pytest tests/integration/test_api_artifacts_db.py -q
python -m pytest tests/integration/test_api_documents_artifact_filters_db.py -q
python -m scripts.update.check_refresh_definition_of_done --require-artifacts
```

---

# Design notes

The current API reflects the current architecture:

- canonical JSONL remains the paper source of truth
- Postgres is a materialized serving layer
- retrieval artifacts remain file-based
- artifact layer is a separate DB-backed evidence/materialization plane
- file and DB backends are intentionally asymmetric
- artifact API is DB-only in v1
- `has_code_link` remains a legacy canonical/source field
- trusted artifact filters operate through `paper_artifact_links`

---

# Next API directions

Near-term:

```text
document artifact filter hardening
API docs and examples
GitHub enrichment fields in artifact responses
```

Later:

```text
source coverage endpoints
artifact enrichment diagnostics endpoints
Qdrant/vector serving endpoints
full-text/chunk endpoints
RAG endpoints
watchlist/bookmark endpoints
dataset release endpoints
```