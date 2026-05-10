# API Reference

## Purpose

This document describes the current public API surface of **ML Research Radar**.

ML Research Radar is a paper-centric canonical corpus platform for ML/AI research. The API is built over several distinct layers:

```text
canonical JSONL truth
→ retrieval artifacts
→ Postgres materialized serving layer
→ artifact evidence/materialization layer
→ paper features
→ discovery API
```

The key invariant is:

```text
canonical_documents.jsonl = paper-level truth
Postgres = materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization layer
paper_features / ranking / detail / similar = derived discovery layer
```

---

## Current stable baseline

Current green corpus baseline:

```text
canonical_documents = 60954
canonical_multisource_docs = 9192
arXiv backbone = 60000
ACL-family docs = 957
ACL-only docs = 954
ACL-enriched existing docs = 3
```

Current retrieval build:

```text
build_id = 20260504T164021Z
corpus_doc_count = 60954
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]
```

Current retrieval manifest:

```text
artifacts/retrieval/manifests/latest.json
```

Current dense artifacts:

```text
artifacts/retrieval/dense/embeddings_20260504T164021Z.npy
artifacts/retrieval/dense/ids_20260504T164021Z.json
artifacts/retrieval/dense/meta_20260504T164021Z.json
```

Current artifact/enrichment baseline, approximate:

```text
artifact_entities ≈ 7333–7336
artifact_observations ≈ 38246
paper_artifact_links ≈ 7430
GitHub enrichment = green
Hugging Face enrichment = green
artifact export DB = green
```

Current product/discovery chain:

```text
ranking profile + query overrides
→ paper detail/card
→ similar papers
→ Discovery API
→ validators
→ strict DoD
```

---

## Backend modes

The API supports two runtime backend modes:

```text
file
db
```

The two backends intentionally expose the same top-level API shape where possible, but they are not fully symmetric.

The backend mode is controlled by:

```text
ML_RADAR_SEARCH_BACKEND
```

Example on Windows CMD:

```bat
set ML_RADAR_SEARCH_BACKEND=file
```

or:

```bat
set ML_RADAR_SEARCH_BACKEND=db
```

Valid values:

```text
file
db
```

---

## File backend

Role:

```text
retrieval-oriented runtime
```

Current characteristics:

- loads retrieval manifest;
- loads canonical documents from JSONL;
- loads lexical retrieval artifacts;
- loads dense retrieval artifacts;
- loads embedding model;
- supports lexical search;
- supports dense search;
- supports hybrid search.

Primary endpoint:

```text
GET /search
```

Supported search modes:

```text
lexical
dense
hybrid
```

Notes:

- file backend is the current full retrieval path;
- dense and hybrid search are not mirrored in Postgres DB backend v1;
- Discovery API is file-first, but it is implemented as a separate product service rather than as a direct extension of `/search`.

---

## DB backend

Role:

```text
materialized serving runtime over Postgres
```

Current characteristics:

- loads Postgres-backed runtime;
- checks DB connectivity;
- serves canonical documents from Postgres;
- serves artifact entities and paper-artifact links from Postgres;
- supports browse/filter access;
- supports DB lexical search v1.

DB-backed endpoints:

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

Unsupported DB modes return a structured `400 Bad Request` error.

---

## Discovery API runtime semantics

Discovery API is exposed under:

```text
/discovery/*
```

Discovery API is a product/discovery layer over file-first derived artifacts:

```text
configs/ranking_profiles_v1.yaml
data/features/paper_features_latest.jsonl
data/analytics/reconciled/canonical_documents.jsonl
data/enriched/artifact_links/*
data/enriched/github_artifacts/*
data/enriched/huggingface_artifacts/*
artifacts/retrieval/manifests/latest.json
artifacts/retrieval/dense/*
```

Discovery API does **not** redefine canonical truth. It materializes user-facing discovery workflows over already validated derived layers.

Discovery API is separate from `SearchRuntime`:

```text
/search backend=file|db remains retrieval/search runtime
/discovery/* uses a separate file-first DiscoveryService
```

Current DiscoveryService cache behavior:

- ranking profiles are cached process-locally;
- paper feature rows are cached process-locally;
- feature/canonical lookup maps are cached process-locally;
- dense bundle, normalized embeddings and dense id index are cached process-locally for similar-paper API calls;
- cache is runtime-only and is not a truth layer;
- `POST /reload` reloads the main API runtime; DiscoveryService exposes its own internal reload behavior where used by API code.

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

Some explicit FastAPI `HTTPException` responses may return the native FastAPI shape:

```json
{
  "detail": "Document not found: <canonical_id>"
}
```

Examples:

```text
unknown ranking profile -> 404
unknown canonical_id in detail endpoint -> 404
invalid top_k / invalid query params -> 400 or 422 depending on validation path
invalid discovery ranking sort_by -> 422
invalid discovery ranking year range -> 400
unsupported DB search mode -> 400
```

---

# Runtime endpoints

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
  "corpus_doc_count": 60954,
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
  "corpus_doc_count": 60954,
  "embedding_model_name": null,
  "model_reused": false,
  "last_reload_at": "2026-05-09T16:00:00+00:00"
}
```

---

# Search API

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
| `top_k` | int | settings default | capped by `max_top_k` |
| `rank` | bool | false | apply ranking layer where supported |
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

# Discovery API

Discovery API exposes the current product workflow:

```text
ranking profile + query overrides
→ paper detail/card
→ similar papers
```

It is intentionally separated from `/search`, `/documents`, and `/artifacts`:

```text
/search      = query retrieval
/documents   = DB/materialized corpus browsing
/artifacts   = artifact evidence browsing
/discovery/* = product/research-radar workflow
```

Current Discovery API endpoints:

```text
GET /discovery/profiles
GET /discovery/ranking/{profile_name}
GET /discovery/papers/{canonical_id}
GET /discovery/papers/{canonical_id}/similar
```

Current quality gate:

```bat
python -m scripts.validation.check_discovery_api --strict
```

Current strict DoD with Discovery API gate:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api
```

---

## `GET /discovery/profiles`

Lists configured ranking/discovery profiles.

### Purpose

Returns the product-level ranking profiles used by the radar workflow.

Profiles are defined in:

```text
configs/ranking_profiles_v1.yaml
```

Current profiles:

```text
acl_artifact_ready
acl_radar
high_confidence_radar
huggingface_ready
recent_artifact_ready
recent_code_radar
recent_dataset_ready
recent_model_ready
recent_transformer_radar
```

Current default profile:

```text
recent_artifact_ready
```

### Example

```http
GET /discovery/profiles
```

### Response shape

```json
{
  "schema_version": "ranking_profiles_v1",
  "default_profile": "recent_artifact_ready",
  "profile_count": 9,
  "profiles": [
    {
      "name": "huggingface_ready",
      "description": "Papers with Hugging Face artifacts, ranked by implementation readiness.",
      "sort_by": "implementation_readiness_score",
      "top_k": 50,
      "descending": true,
      "filters": {
        "has_hf": true
      }
    }
  ]
}
```

---

## `GET /discovery/ranking/{profile_name}`

Returns ranked papers for a configured discovery profile, optionally refined with query-level overrides.

### Purpose

Provides a product-ready ranked feed over `paper_features_latest.jsonl`.

This is not free-form retrieval. It is profile-based radar ranking with controlled query overrides.

### Path parameters

```text
profile_name
```

### Query parameters

| parameter | type | default | notes |
|---|---:|---:|---|
| `top_k` | int | profile default | capped by API settings, currently `max_top_k = 100` |
| `min_year` | int | profile/default null | lower year bound |
| `max_year` | int | profile/default null | upper year bound |
| `query_title` | string | profile/default null | case-insensitive substring match over title |
| `source_family` | string | profile/default null | source family filter, e.g. `arxiv`, `acl_anthology` |
| `has_code` | bool | profile/default false | requires code artifact signal |
| `has_dataset` | bool | profile/default false | requires dataset artifact signal |
| `has_model` | bool | profile/default false | requires model artifact signal |
| `has_demo` | bool | profile/default false | requires demo artifact signal |
| `has_github` | bool | profile/default false | requires found GitHub repository signal |
| `has_hf` | bool | profile/default false | requires Hugging Face signal |
| `has_acl` | bool | profile/default false | requires ACL source signal |
| `has_doi` | bool | profile/default false | requires DOI signal |
| `sort_by` | ranking sort field | profile default | overrides profile sorting |
| `descending` | bool | profile default | overrides sort direction |

Supported `sort_by` values:

```text
radar_score
implementation_readiness_score
source_confidence_score
citation_signal_score
recency_score
year
github_stars_max
github_stars_sum
github_forks_max
github_forks_sum
trusted_artifact_links_count
trusted_code_links_count
trusted_dataset_links_count
trusted_model_links_count
trusted_demo_links_count
hf_downloads_max
hf_likes_max
```

### Override semantics

Profile filters are used as the base preset. Query parameters are explicit overrides or additions.

```text
profile.filters = base profile filters
query params = explicit overrides/additions
response.filters = effective filters after overrides
response.sort_by = effective sort field
response.descending = effective sort direction
```

Boolean override policy:

```text
not provided = keep profile default
true = explicit true override
false = explicit false override
```

This means that even an override that weakens a profile constraint is allowed:

```http
GET /discovery/ranking/huggingface_ready?top_k=5&has_hf=false
```

In that case:

```text
profile.filters.has_hf = true
filters.has_hf = false
```

### Examples

Recent artifact-ready papers from 2025 onward:

```http
GET /discovery/ranking/recent_artifact_ready?top_k=20&min_year=2025
```

Hugging Face-ready papers with title containing `speech`:

```http
GET /discovery/ranking/huggingface_ready?top_k=20&query_title=speech
```

Recent artifact-ready code papers from 2025 onward:

```http
GET /discovery/ranking/recent_artifact_ready?top_k=5&min_year=2025&has_code=true
```

Override a base profile filter:

```http
GET /discovery/ranking/huggingface_ready?top_k=5&has_hf=false
```

Override sorting:

```http
GET /discovery/ranking/recent_code_radar?top_k=20&sort_by=implementation_readiness_score
```

### Response shape

```json
{
  "mode": "ranking",
  "profile": {
    "name": "huggingface_ready",
    "description": "Papers with Hugging Face artifacts, ranked by implementation readiness.",
    "sort_by": "implementation_readiness_score",
    "top_k": 50,
    "descending": true,
    "filters": {
      "has_hf": true
    },
    "loaded": true,
    "profiles_path": "configs/ranking_profiles_v1.yaml"
  },
  "sort_by": "implementation_readiness_score",
  "descending": true,
  "top_k": 5,
  "input_rows_count": 60954,
  "filtered_rows_count": 85,
  "returned_rows_count": 5,
  "features_path": "data/features/paper_features_latest.jsonl",
  "filters": {
    "has_hf": true,
    "min_year": null,
    "max_year": null,
    "query_title": null,
    "source_family": null
  },
  "results": [
    {
      "rank": 1,
      "canonical_id": "bd3c9332f17370fa801e6ac9542f125a",
      "title": "FlashLabs Chroma 1.0: A Real-Time End-to-End Spoken Dialogue Model with Personalized Voice Cloning",
      "year": 2026,
      "radar_score": 0.658838,
      "implementation_readiness_score": 0.768109,
      "source_confidence_score": 0.45,
      "citation_signal_score": 0.0,
      "trusted_artifact_links_count": 2,
      "has_code_artifact": true,
      "hf_found_count": 1,
      "github_found_repo_count": 1
    }
  ]
}
```

### Missing profile

Unknown profile names return:

```text
404
```

### Invalid parameters

Invalid `sort_by` values return FastAPI validation error:

```text
422
```

Invalid cross-field year range returns bad request:

```text
400
```

Example invalid year range:

```http
GET /discovery/ranking/recent_artifact_ready?min_year=2026&max_year=2025
```

---

## `GET /discovery/papers/{canonical_id}`

Returns a full paper detail/card payload.

### Purpose

Builds a paper detail view by combining:

```text
canonical document
paper features
trusted artifact links
artifact entities
GitHub metadata
Hugging Face metadata
source evidence
identifiers
scores
```

### Path parameters

```text
canonical_id
```

### Query parameters

| parameter | type | default | notes |
|---|---:|---:|---|
| `view` | full | full | only `full` is supported in v1 |

`compact` view is postponed.

### Example

```http
GET /discovery/papers/bd3c9332f17370fa801e6ac9542f125a
```

### Response shape

```json
{
  "canonical_id": "bd3c9332f17370fa801e6ac9542f125a",
  "found": true,
  "inputs": {
    "canonical_path": "data/analytics/reconciled/canonical_documents.jsonl",
    "features_path": "data/features/paper_features_latest.jsonl"
  },
  "detail": {
    "canonical_id": "bd3c9332f17370fa801e6ac9542f125a",
    "found": true,
    "canonical_found": true,
    "features_found": true,
    "title": "FlashLabs Chroma 1.0: A Real-Time End-to-End Spoken Dialogue Model with Personalized Voice Cloning",
    "year": 2026,
    "scores": {
      "radar_score": 0.658838,
      "implementation_readiness_score": 0.768109,
      "source_confidence_score": 0.45,
      "citation_signal_score": 0.0
    },
    "artifacts": [
      {
        "relation_type": "code",
        "artifact": {
          "provider": "github",
          "artifact_type": "github_repository"
        }
      },
      {
        "relation_type": "model",
        "artifact": {
          "provider": "huggingface",
          "artifact_type": "huggingface_model"
        }
      }
    ],
    "source_evidence": {},
    "identifiers": {}
  }
}
```

### Missing paper

If the canonical paper does not exist, the endpoint returns:

```text
404
```

---

## `GET /discovery/papers/{canonical_id}/similar`

Returns semantic nearest-neighbor papers for a target paper.

### Purpose

Finds similar papers over the current dense retrieval embeddings and enriches results with paper features/canonical metadata.

Default mode:

```text
rank_by=semantic
```

Supported ranking modes:

```text
semantic
radar_adjusted
```

Semantics:

```text
semantic = pure dense cosine similarity
radar_adjusted = semantic similarity + radar_score + implementation_readiness_score
```

Current `radar_adjusted` formula:

```text
0.85 * semantic_similarity_norm
+ 0.10 * radar_score
+ 0.05 * implementation_readiness_score
```

### Path parameters

```text
canonical_id
```

### Query parameters

| parameter | type | default | notes |
|---|---:|---:|---|
| `top_k` | int | 20 | capped by API settings |
| `rank_by` | semantic / radar_adjusted | semantic | result ranking mode |
| `min_similarity` | float | null | optional cosine threshold |

### Examples

Semantic nearest papers:

```http
GET /discovery/papers/bd3c9332f17370fa801e6ac9542f125a/similar?top_k=20
```

Radar-adjusted similar papers:

```http
GET /discovery/papers/bd3c9332f17370fa801e6ac9542f125a/similar?top_k=20&rank_by=radar_adjusted
```

### Response shape

```json
{
  "mode": "similar_papers",
  "target_canonical_id": "bd3c9332f17370fa801e6ac9542f125a",
  "target_found": true,
  "target": {
    "canonical_id": "bd3c9332f17370fa801e6ac9542f125a",
    "title": "FlashLabs Chroma 1.0: A Real-Time End-to-End Spoken Dialogue Model with Personalized Voice Cloning",
    "year": 2026,
    "radar_score": 0.658838,
    "implementation_readiness_score": 0.768109
  },
  "rank_by": "semantic",
  "top_k": 20,
  "min_similarity": null,
  "input_rows_count": 60954,
  "returned_rows_count": 20,
  "dense_artifacts": {
    "manifest_path": "artifacts/retrieval/manifests/latest.json",
    "embedding_path": "artifacts/retrieval/dense/embeddings_20260504T164021Z.npy",
    "ids_path": "artifacts/retrieval/dense/ids_20260504T164021Z.json",
    "meta_path": "artifacts/retrieval/dense/meta_20260504T164021Z.json",
    "embedding_shape": [60954, 384],
    "ids_count": 60954
  },
  "results": [
    {
      "canonical_id": "...",
      "dense_index": 123,
      "title": "StreamVC: Real-Time Low-Latency Voice Conversion",
      "year": 2024,
      "semantic_similarity": 0.7124,
      "semantic_similarity_norm": 0.8562,
      "radar_adjusted_similarity": 0.7548,
      "rank_score": 0.7124,
      "radar_score": 0.27,
      "implementation_readiness_score": 0.0,
      "trusted_artifact_links_count": 0
    }
  ]
}
```

### Runtime/cache note

Discovery API caches the dense runtime in process:

```text
dense bundle
normalized embeddings
dense id index
features lookup map
canonical lookup map
```

This accelerates repeated `/similar` calls within the same API process. It does not alter retrieval artifacts and is not a truth layer.

---

# Documents API

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

For profile-based product discovery, use:

```text
GET /discovery/ranking/{profile_name}
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

---

# Artifacts API

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
min_stars
max_stars
language
license
archived
github_status
has_github_metadata
limit
offset
sort_by
```

### Parameter details

| parameter | type | default | notes |
|---|---:|---:|---|
| `provider` | string | null | e.g. github, huggingface, figshare, zenodo |
| `artifact_type` | string | null | e.g. github_repository, huggingface_model |
| `relation_type` | string | null | code, dataset, model, demo |
| `owner` | string | null | namespace/owner when available |
| `min_confidence` | float | null | trusted link confidence threshold |
| `has_paper_links` | bool | null | whether artifact participates in trusted links |
| `min_stars` | int | null | minimum GitHub stars; applies to materialized artifact metadata |
| `max_stars` | int | null | maximum GitHub stars; applies to materialized artifact metadata |
| `language` | string | null | GitHub repository language, case-insensitive; uses `metadata.github.language` |
| `license` | string | null | artifact/GitHub license, case-insensitive; uses `artifact_entities.license` |
| `archived` | bool | null | GitHub archived flag; matches only explicit `metadata.github.archived` rows |
| `github_status` | found / not_found / forbidden / rate_limited / error / skipped_invalid_external_id | null | GitHub enrichment status from `metadata.github.status` |
| `has_github_metadata` | bool | null | whether `artifact_entities.metadata` contains a `github` object |
| `limit` | int | 20 | max 100 |
| `offset` | int | 0 | pagination offset |
| `sort_by` | linked_papers_desc / provider_asc / type_asc / owner_asc / last_seen_desc / stars_desc / forks_desc | linked_papers_desc | deterministic ordering |

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

GitHub repositories with at least 100 stars, Python as primary language, sorted by stars:

```http
GET /artifacts?provider=github&min_stars=100&language=Python&sort_by=stars_desc&limit=20
```

GitHub repositories by enrichment status:

```http
GET /artifacts?provider=github&github_status=found&limit=20
GET /artifacts?provider=github&github_status=not_found&limit=20
```

Non-archived GitHub repositories with explicit GitHub metadata:

```http
GET /artifacts?provider=github&archived=false&has_github_metadata=true&limit=20
```

GitHub artifacts sorted by forks:

```http
GET /artifacts?provider=github&has_github_metadata=true&sort_by=forks_desc&limit=20
```

### GitHub artifact metadata semantics

GitHub Artifact Enrichment v1 enriches GitHub repository artifacts and exposes metadata through existing artifact endpoints.

Relevant endpoints:

```text
GET /artifacts?provider=github
GET /documents/{canonical_id}/artifacts
GET /discovery/papers/{canonical_id}
```

Example enriched fields:

```text
stars
forks
license
topics
fetched_at
metadata.github.status
metadata.github.language
metadata.github.watchers
metadata.github.open_issues
metadata.github.default_branch
metadata.github.archived
metadata.github.pushed_at
metadata.github.github_api_url
```

Semantics:

- GitHub metadata is artifact metadata, not paper truth.
- GitHub stars/forks/language/license/status must not be used as canonical paper identity signals.
- `has_code_link` remains the legacy canonical/source-layer field.
- `has_trusted_code_artifact` remains the trusted artifact-layer filter.
- `not_found` GitHub repositories are preserved as historical artifact evidence.
- `archived=false` matches only rows with explicit GitHub metadata; non-GitHub artifacts are not treated as non-archived.
- `has_github_metadata=false` means `metadata` does not contain a `github` object; for diagnostics, prefer `provider=github&has_github_metadata=false`.
- GitHub enrichment is optional and not required for base artifact API operation.

### Hugging Face artifact metadata semantics

Hugging Face Artifact Enrichment v1 enriches Hugging Face model/dataset/space artifacts and exposes metadata in artifact entities and paper detail cards.

Semantics:

- Hugging Face is an artifact enrichment provider, not a paper source.
- `forbidden` rows are provider/access states and remain diagnostic.
- `skipped_invalid_external_id` rows are recognized extraction/noise states and remain diagnostic.
- These states do not fail the strict gate unless policy changes later.
- Provider-specific HF API filters remain postponed.

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
| `provider` | string | null | e.g. github, huggingface, figshare, zenodo |
| `artifact_type` | string | null | e.g. github_repository, huggingface_model |
| `min_confidence` | float | null | link confidence threshold |
| `limit` | int | 100 | max 500 |
| `offset` | int | 0 | pagination offset |

### Examples

All artifacts for a document:

```http
GET /documents/<canonical_id>/artifacts
```

Only dataset artifacts:

```http
GET /documents/<canonical_id>/artifacts?relation_type=dataset
```

Only GitHub artifacts:

```http
GET /documents/<canonical_id>/artifacts?provider=github
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

| Endpoint | file backend | db backend | notes |
|---|---:|---:|---|
| `GET /health` | yes | yes | runtime readiness |
| `GET /info` | yes | yes | runtime/API info |
| `GET /runtime` | yes | yes | detailed runtime state |
| `POST /reload` | yes | yes | reload current backend runtime |
| `GET /search?mode=lexical` | yes | yes | DB supports lexical only |
| `GET /search?mode=dense` | yes | no | use file backend |
| `GET /search?mode=hybrid` | yes | no | use file backend |
| `GET /documents` | no | yes | Postgres materialized serving layer |
| `GET /artifacts` | no | yes | artifact DB layer |
| `GET /documents/{canonical_id}/artifacts` | no | yes | artifact DB layer |
| `GET /discovery/profiles` | yes | yes* | file-first DiscoveryService; app startup still follows backend mode |
| `GET /discovery/ranking/{profile_name}` | yes | yes* | file-first DiscoveryService; supports profile + query overrides |
| `GET /discovery/papers/{canonical_id}` | yes | yes* | file-first DiscoveryService |
| `GET /discovery/papers/{canonical_id}/similar` | yes | yes* | file-first DiscoveryService with dense runtime cache |

`yes*` means the endpoint itself is served by file-first DiscoveryService. The enclosing app runtime still starts according to `ML_RADAR_SEARCH_BACKEND`.

---

# Validation and smoke commands

## File/API discovery checks

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_discovery.py -q
python -m scripts.validation.check_discovery_api --strict
```

The Discovery API quality gate checks both the base ranking endpoint and the v1.1 ranking override smoke:

```http
GET /discovery/ranking/recent_artifact_ready?top_k=5&min_year=2025&has_code=true
```

Required v1.1 checks include:

```text
discovery_api_ranking_overrides_endpoint_ok
discovery_api_ranking_overrides_results_non_empty
discovery_api_ranking_overrides_min_year_filter_echoed
discovery_api_ranking_overrides_has_code_filter_echoed
discovery_api_ranking_overrides_results_match_filters
```

## Similar papers checks

```bat
python -m scripts.retrieval.find_similar_papers --from-latest-detail --top-k 20
python -m scripts.validation.check_similar_papers_report --strict
```

## DB backend checks

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m scripts.export.test_db_read
python -m pytest tests/integration/test_api_db_smoke.py -q
python -m pytest tests/integration/test_api_search_db_backend.py -q
python -m pytest tests/integration/test_api_search_filters_db.py -q
python -m pytest tests/integration/test_api_artifacts_db.py -q
python -m pytest tests/integration/test_api_documents_artifact_filters_db.py -q
python -m pytest tests/integration/test_api_artifacts_github_filters_db.py -q
python -m pytest tests/integration/test_api_github_enrichment_db.py -q
```

## Discovery API regression

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.run_discovery_api_regression
```

Full variant with DB smoke and strict DoD:

```bat
python -m scripts.validation.run_discovery_api_regression --include-db-smoke --include-dod
```

## Full strict DoD

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api
```

Expected result:

```text
dod_passed=True
required_failed_count=0
```

---

# Design notes

The current API reflects the project architecture:

- canonical JSONL remains the paper source of truth;
- Postgres is a materialized serving layer;
- retrieval artifacts remain file-based derived artifacts;
- artifact layer is a separate DB-backed evidence/materialization plane;
- feature/ranking/detail/similar layers are derived discovery/product layers;
- file and DB backends are intentionally asymmetric;
- artifact API is DB-only in v1;
- Discovery API is file-first;
- Discovery ranking uses profiles as base presets and query parameters as explicit overrides;
- `has_code_link` remains a legacy canonical/source field;
- trusted artifact filters operate through `paper_artifact_links`;
- GitHub/HF enrichment is artifact metadata, not paper truth;
- process-local caches are runtime accelerators, not truth layers.

---

# Next API directions

Near-term:

```text
Discovery UI v0.1:
  thin Streamlit client over /discovery/*
  profile selector
  ranking query overrides
  paper cards
  paper detail
  similar papers panel
```

Possible follow-up Discovery API ergonomics:

```text
compact paper detail view
smaller artifact metadata view
endpoint examples for UI
better latency diagnostics
explicit DiscoveryService cache stats
lighter discovery validator startup path if needed
```

Later:

```text
Qdrant/vector serving endpoints
DB/materialized paper_features table
cached paper detail endpoint
source coverage endpoints
artifact enrichment diagnostics endpoints
full-text/chunk endpoints
RAG endpoints
watchlist/bookmark endpoints
dataset release endpoints
```
