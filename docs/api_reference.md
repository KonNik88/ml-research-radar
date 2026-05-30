# API Reference

## Purpose

This document describes the current public API surface of **ML Research Radar**.

ML Research Radar is a paper-centric canonical corpus and discovery platform for ML/AI research.

The API is built over distinct layers:

```text
canonical JSONL truth
→ retrieval artifacts
→ Postgres materialized serving layer
→ artifact evidence/materialization layer
→ GitHub / Hugging Face artifact enrichment
→ paper features
→ ranking / paper detail / similar papers
→ topic clusters / projection
→ Discovery API
→ Streamlit Discovery UI
```

Main invariant:

```text
canonical_documents.jsonl = paper-level truth
Postgres = materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization layer
paper_features / ranking / detail / similar / topic clusters = derived discovery layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin API client
```

---

## Current stable baseline

Current checkpoint:

```text
Discovery Green Checkpoint — 2026-05
```

Current canonical baseline:

```text
canonical_documents = 60954
canonical_multisource_docs = 9192
doi_count = 10183
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

Current artifact/enrichment baseline:

```text
artifact_entities_db_count = 7333
artifact_observations_db_count = 38246
paper_artifact_links_db_count = 7430

github_entities_count ≈ 5953
github_found_count ≈ 5339

huggingface_entities_count ≈ 100
huggingface_found_count ≈ 77
```

Current feature/discovery baseline:

```text
paper_features_rows_count = 60954
ranking_profiles_count = 9
topic_clusters_count = 80
topic_assignments_count = 60954
topic_projection_algorithm = umap
topic_projection_rows_count = 2080
strict_dod_required_checks = 132
strict_dod_required_failed_count = 0
strict_dod_passed = true

golden_queries_enabled_count = 22
golden_queries_explicit_count = 15
golden_queries_weak_pattern_count = 7
qdrant_benchmark_collection = ml_radar_dense_benchmark_v1
qdrant_benchmark_uploaded_count = 60954
```

Current product/discovery chain:

```text
ranking profile + query overrides
→ paper detail/card
→ similar papers
→ topic cluster navigation
→ topic map
→ artifact explorer
→ Discovery API
→ Streamlit UI
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

Backend mode is controlled by:

```text
ML_RADAR_SEARCH_BACKEND
```

Windows examples:

```bat
set ML_RADAR_SEARCH_BACKEND=file
```

```bat
set ML_RADAR_SEARCH_BACKEND=db
```

The two backends intentionally expose the same top-level app where possible, but they are not fully symmetric.

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

---

## DB backend

Role:

```text
materialized serving runtime over Postgres
```

Current characteristics:

- checks DB connectivity;
- serves canonical documents from Postgres;
- serves artifact entities from Postgres;
- serves trusted paper-artifact links from Postgres;
- supports browse/filter access;
- supports DB lexical search v1.

DB-backed endpoints:

```text
GET /documents
GET /artifacts
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/papers
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

Discovery API is a product/discovery layer over validated file-first artifacts:

```text
configs/ranking_profiles_v1.yaml
data/features/paper_features_latest.jsonl
data/analytics/reconciled/canonical_documents.jsonl
data/enriched/artifact_links/*
data/enriched/github_artifacts/*
data/enriched/huggingface_artifacts/*
artifacts/retrieval/manifests/latest.json
artifacts/retrieval/dense/*
artifacts/clusters/topic/latest.json
artifacts/clusters/topic/runs/<cluster_build_id>/*
```

Discovery API does not redefine canonical truth. It materializes user-facing discovery workflows over already validated derived layers.

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
- topic cluster latest pointer, summaries, labels, assignments and projection/map artifacts may be cached process-locally;
- cache is runtime-only and is not a truth layer.

---

## Error response

Structured API errors use this shape:

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

Some FastAPI `HTTPException` responses may use the native FastAPI shape:

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
unknown cluster_id -> 404
unknown artifact_id -> 404
```

---

# Runtime endpoints

## `GET /health`

Backend-aware readiness check.

Response fields:

```text
status
backend_mode
ready
build_id
corpus_doc_count
embedding_model_name
checks
```

DB backend example:

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

---

## `GET /info`

Returns API-level and runtime information.

Response fields:

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

Response fields:

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

---

## `POST /reload`

Reloads the current runtime.

File backend reloads:

```text
latest manifest
canonical documents
lexical artifacts
dense artifacts
embedding model
```

DB backend reloads:

```text
Postgres-backed runtime
DB store connectivity
document count snapshot
```

---

# Search API

## `GET /search`

Main relevance-search endpoint.

Query parameters:

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

Parameter summary:

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

File backend modes:

```text
lexical
dense
hybrid
```

DB backend mode:

```text
lexical
```

Example:

```http
GET /search?query=graph%20neural%20networks&mode=lexical&top_k=5
```

---

# Discovery API

Discovery API exposes the product workflow:

```text
ranking profile + query overrides
→ paper detail/card
→ similar papers
→ paper topic cluster
→ topic cluster list/detail/map
```

Current Discovery API endpoints:

```text
GET /discovery/profiles
GET /discovery/ranking/{profile_name}
GET /discovery/papers/{canonical_id}
GET /discovery/papers/{canonical_id}/similar
GET /discovery/papers/{canonical_id}/cluster
GET /discovery/clusters
GET /discovery/clusters/{cluster_id}
GET /discovery/clusters/map
```

Current quality gate:

```bat
python -m scripts.validation.check_discovery_api --strict
```

---

## `GET /discovery/profiles`

Lists configured ranking/discovery profiles.

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

Default profile:

```text
recent_artifact_ready
```

Example:

```http
GET /discovery/profiles
```

Response shape:

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

This is profile-based radar ranking over `paper_features_latest.jsonl`, not free-form retrieval.

Path parameter:

```text
profile_name
```

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `top_k` | int | profile default | capped by API settings, current API cap is 100 |
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

Override semantics:

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

Examples:

```http
GET /discovery/ranking/recent_artifact_ready?top_k=20&min_year=2025
GET /discovery/ranking/huggingface_ready?top_k=20&query_title=speech
GET /discovery/ranking/recent_artifact_ready?top_k=5&min_year=2025&has_code=true
GET /discovery/ranking/huggingface_ready?top_k=5&has_hf=false
GET /discovery/ranking/recent_code_radar?top_k=20&sort_by=implementation_readiness_score
```

Invalid profile:

```text
404
```

Invalid `sort_by`:

```text
422
```

Invalid `min_year > max_year`:

```text
400
```

---

## `GET /discovery/papers/{canonical_id}`

Returns a full paper detail/card payload.

Combines:

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

Path parameter:

```text
canonical_id
```

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `view` | full | full | only `full` is supported in v1 |

Example:

```http
GET /discovery/papers/bd3c9332f17370fa801e6ac9542f125a
```

Missing paper:

```text
404
```

---

## `GET /discovery/papers/{canonical_id}/similar`

Returns semantic nearest-neighbor papers for a target paper.

Supported ranking modes:

```text
semantic
radar_adjusted
```

Current `radar_adjusted` formula:

```text
0.85 * semantic_similarity_norm
+ 0.10 * radar_score
+ 0.05 * implementation_readiness_score
```

Path parameter:

```text
canonical_id
```

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `top_k` | int | 20 | capped by API settings |
| `rank_by` | semantic / radar_adjusted | semantic | result ranking mode |
| `min_similarity` | float | null | optional cosine threshold |

Examples:

```http
GET /discovery/papers/bd3c9332f17370fa801e6ac9542f125a/similar?top_k=20
GET /discovery/papers/bd3c9332f17370fa801e6ac9542f125a/similar?top_k=20&rank_by=radar_adjusted
```

Runtime/cache note:

```text
Discovery API caches the dense bundle, normalized embeddings, dense id index, features map and canonical map process-locally.
The cache accelerates repeated calls and is not a truth layer.
```

---

## `GET /discovery/papers/{canonical_id}/cluster`

Returns the latest topic-cluster assignment for one paper.

Purpose:

```text
connect paper detail/similar workflows to the corpus-level topic landscape
```

Example:

```http
GET /discovery/papers/bd3c9332f17370fa801e6ac9542f125a/cluster
```

Response content:

```text
canonical_id
assignment
cluster_id
cluster_build_id
retrieval_build_id
rank_within_cluster
distance_to_centroid
similarity_to_centroid
cluster label candidates
cluster summary
```

Missing paper or assignment:

```text
404
```

---

## `GET /discovery/clusters`

Lists current topic clusters from the latest topic-cluster artifact.

Purpose:

```text
corpus-level topic/navigation surface over validated topic clustering layer
```

Inputs:

```text
artifacts/clusters/topic/latest.json
artifacts/clusters/topic/runs/<cluster_build_id>/summary.json
artifacts/clusters/topic/runs/<cluster_build_id>/label_candidates.json
```

Current stable query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | service default | number of clusters to return |
| `sort_by` | string | implementation-supported | e.g. size/artifact-ready/score style sorting where enabled |
| `min_size` | int | null | optional cluster size filter where enabled |

Stable smoke example:

```http
GET /discovery/clusters?limit=5
```

Current quality smoke also checks an artifact-ready variant:

```http
GET /discovery/clusters?limit=1&sort_by=artifact_ready_desc&min_size=1
```

Response content:

```text
mode
cluster_build_id
retrieval_build_id
cluster_count
returned_count
results[]
```

Each cluster row may include:

```text
cluster_id
size
label_candidates
artifact_ready_count
code_artifact_count
dataset_artifact_count
model_artifact_count
demo_artifact_count
mean_radar_score
mean_implementation_readiness_score
mean_source_confidence_score
mean_citation_signal_score
top_source_families
representative_papers
```

Semantics:

```text
cluster_id is stable only inside a specific cluster_build_id/config/input corpus
label_candidates are heuristic hints, not curated taxonomy
representative_papers are inspection/navigation aids, not canonical labels
```

---

## `GET /discovery/clusters/{cluster_id}`

Returns detail for one topic cluster.

Purpose:

```text
cluster-level view for UI/API clients:
summary + label candidates + representative papers + limited papers from cluster
```

Path parameter:

```text
cluster_id
```

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `top_k` | int | service default | number of papers to return from the cluster |
| `min_year` | int | null | optional lower year bound where enabled |
| `max_year` | int | null | optional upper year bound where enabled |
| `has_code` | bool | null | optional code-artifact filter where enabled |
| `has_github` | bool | null | optional GitHub filter where enabled |
| `min_radar_score` | float | null | optional score filter where enabled |
| `min_implementation_readiness_score` | float | null | optional score filter where enabled |
| `min_citation_signal_score` | float | null | optional score filter where enabled |
| `sort_by` | string | rank | supported sort modes listed below |

Current checked sort modes:

```text
rank
similarity_desc
radar_score
implementation_readiness_score
citation_signal_score
year_desc
```

Examples:

```http
GET /discovery/clusters/41?top_k=5
GET /discovery/clusters/41?top_k=5&sort_by=similarity_desc
GET /discovery/clusters/39?top_k=5&min_year=2020&has_code=true&sort_by=radar_score
```

Response content:

```text
mode
cluster_id
cluster_build_id
retrieval_build_id
found
total_papers
returned_papers_count
summary
papers[]
effective filters where applicable
```

Missing cluster:

```text
404
```

---

## `GET /discovery/clusters/map`

Returns topic-map projection points from the latest projection artifact.

Purpose:

```text
serve precomputed corpus-level topic projection to UI/API clients
```

This endpoint reads existing projection artifacts. It does not compute UMAP/PCA at request time.

Inputs:

```text
artifacts/clusters/topic/latest.json
artifacts/clusters/topic/runs/<cluster_build_id>/projection_2d.jsonl
artifacts/clusters/topic/runs/<cluster_build_id>/projection_summary.json
```

Current projection baseline:

```text
projection_algorithm = umap
projection_build_id = 20260515T154038Z
cluster_build_id = 20260511T151842Z
retrieval_build_id = 20260504T164021Z
rows_count = 2080
centroid_count = 80
representative_count = 800
sampled_count = 1200
```

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `include_papers` | bool | false | false returns centroids only; true can include paper points |
| `max_points` | int | service default/cap | caps returned point count for UI performance |

Examples:

```http
GET /discovery/clusters/map
GET /discovery/clusters/map?include_papers=true&max_points=500
```

Default behavior:

```text
include_papers=false returns cluster centroid points only
```

Response content:

```text
mode
cluster_build_id
retrieval_build_id
projection_build_id
projection_algorithm
counts
returned_count
points[]
```

Each point includes:

```text
x
y
cluster_id
point_type
cluster_build_id
retrieval_build_id
```

Paper points may also include:

```text
canonical_id
title
year
is_representative
is_sampled
radar_score
implementation_readiness_score
```

Semantics:

```text
projection is a derived visualization artifact
projection does not change canonical truth
coordinates are stable only for a specific projection_build_id / cluster_build_id / retrieval_build_id
```

---

# Documents API

## `GET /documents`

Browse/filter endpoint for canonical documents stored in Postgres.

DB backend only.

Purpose:

```text
deterministic browse/filter access over canonical documents
```

It is not the primary relevance-search endpoint. Use:

```text
GET /search
```

for relevance search and:

```text
GET /discovery/ranking/{profile_name}
```

for profile-based discovery.

Query parameters:

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

Trusted artifact filters use:

```text
paper_artifact_links
JOIN artifact_entities
```

Do not treat `has_code_link` and `has_trusted_code_artifact` as equivalent.

---

# Artifacts API

## `GET /artifacts`

Browse/filter endpoint for artifact entities stored in Postgres.

DB backend only.

Query parameters:

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

Supported sort examples:

```text
linked_papers_desc
provider_asc
type_asc
owner_asc
last_seen_desc
stars_desc
forks_desc
```

Examples:

```http
GET /artifacts?limit=20
GET /artifacts?provider=github&limit=20
GET /artifacts?relation_type=code&limit=20
GET /artifacts?has_paper_links=true&limit=20
GET /artifacts?provider=github&min_stars=100&language=Python&sort_by=stars_desc&limit=20
GET /artifacts?provider=github&github_status=found&limit=20
GET /artifacts?provider=github&archived=false&has_github_metadata=true&limit=20
```

---

## `GET /artifacts/{artifact_id}`

Returns detail for one artifact entity.

DB backend only.

Purpose:

```text
show artifact metadata, provider-specific enrichment metadata and paper-link summary
```

Path parameter:

```text
artifact_id
```

Example:

```http
GET /artifacts/7e51675b8ad752fbf617dced0315d3bd
```

Typical response content:

```text
artifact_id
provider
artifact_type
canonical_url
normalized_url
owner
name
external_id
license
metadata
github metadata where present
huggingface metadata where present
paper link summary
```

Missing artifact:

```text
404
```

---

## `GET /artifacts/{artifact_id}/papers`

Returns papers linked to one artifact.

DB backend only.

Purpose:

```text
navigate from an artifact to canonical papers that cite/link it
```

Path parameter:

```text
artifact_id
```

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | service default | max rows |
| `offset` | int | 0 | pagination offset |
| `relation_type` | string | null | code/dataset/model/demo |
| `min_confidence` | float | null | trusted link confidence threshold |
| `sort_by` | string | confidence_desc | sorting mode where enabled |

Examples:

```http
GET /artifacts/7e51675b8ad752fbf617dced0315d3bd/papers
GET /artifacts/7e51675b8ad752fbf617dced0315d3bd/papers?relation_type=code&sort_by=confidence_desc
```

Typical response content:

```text
artifact
total
returned_count
results[]
```

Each linked paper row may include:

```text
canonical_id
title
year
relation_type
confidence
source_fields
radar_score
implementation_readiness_score
```

Missing artifact:

```text
404
```

---

## `GET /documents/{canonical_id}/artifacts`

Returns trusted artifacts linked to one canonical document.

DB backend only.

Path parameter:

```text
canonical_id
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

Examples:

```http
GET /documents/<canonical_id>/artifacts
GET /documents/<canonical_id>/artifacts?relation_type=dataset
GET /documents/<canonical_id>/artifacts?provider=github
```

Missing document:

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

# Provider metadata semantics

## GitHub artifact metadata

GitHub Artifact Enrichment v1 enriches GitHub repository artifacts.

Relevant endpoints:

```text
GET /artifacts?provider=github
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/papers
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
- `not_found` repositories are preserved as historical artifact evidence.
- `archived=false` matches only rows with explicit GitHub metadata.
- GitHub enrichment is optional and not required for base artifact API operation.

## Hugging Face artifact metadata

Hugging Face Artifact Enrichment v1 enriches Hugging Face model/dataset/space artifacts.

Semantics:

- Hugging Face is an artifact enrichment provider, not a paper source.
- `forbidden` rows are provider/access states and remain diagnostic.
- `skipped_invalid_external_id` rows are recognized extraction/noise states and remain diagnostic.
- These states do not fail the strict gate unless policy changes later.
- Provider-specific HF API filters remain postponed until there is a clear product need.

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
| `GET /artifacts/{artifact_id}` | no | yes | artifact DB layer |
| `GET /artifacts/{artifact_id}/papers` | no | yes | artifact DB layer |
| `GET /documents/{canonical_id}/artifacts` | no | yes | artifact DB layer |
| `GET /discovery/profiles` | yes | yes* | file-first DiscoveryService |
| `GET /discovery/ranking/{profile_name}` | yes | yes* | file-first DiscoveryService |
| `GET /discovery/papers/{canonical_id}` | yes | yes* | file-first DiscoveryService |
| `GET /discovery/papers/{canonical_id}/similar` | yes | yes* | file-first DiscoveryService with dense cache |
| `GET /discovery/papers/{canonical_id}/cluster` | yes | yes* | file-first DiscoveryService over topic artifacts |
| `GET /discovery/clusters` | yes | yes* | file-first DiscoveryService over topic artifacts |
| `GET /discovery/clusters/{cluster_id}` | yes | yes* | file-first DiscoveryService over topic artifacts |
| `GET /discovery/clusters/map` | yes | yes* | file-first DiscoveryService over projection artifact |

`yes*` means the endpoint itself is served by file-first DiscoveryService. The enclosing app runtime still starts according to `ML_RADAR_SEARCH_BACKEND`.

---

# Validation and smoke commands

## File/API discovery checks

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_discovery.py -q
python -m scripts.validation.check_discovery_api --strict
```

Discovery quality currently checks:

```text
profiles
ranking
ranking overrides
paper detail
similar semantic
similar radar-adjusted
paper topic cluster
topic clusters
topic cluster detail
topic cluster detail filters/sorts
topic cluster map
topic cluster map with paper points
```

## Streamlit UI checks

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Optional live API check:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict --check-api
```

## Topic cluster/projection checks

```bat
python -m scripts.validation.check_topic_clusters --strict
python -m scripts.validation.check_topic_projection --strict
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

## Qdrant vector-serving benchmark

Qdrant is currently validated as an evaluation-only vector-serving benchmark layer. It is not yet a production `/search` backend and does not change file/db runtime defaults.

```bat
python -m scripts.evaluation.run_qdrant_retrieval_benchmark
python -m scripts.validation.check_qdrant_retrieval_benchmark --strict
```

Current-green benchmark state:

```text
collection_name = ml_radar_dense_benchmark_v1
uploaded_count = 60954
collection_points_count = 60954
enabled_queries_count = 22
query_count = 22
error_count = 0
required_failed_count = 0
```

The benchmark reads current dense artifacts from the retrieval manifest, creates a Qdrant collection, uploads paper vectors, runs enabled golden queries, and compares Qdrant dense retrieval with current file-dense retrieval.

## Qdrant serving POC checks

Qdrant serving POC checks validate an existing Qdrant collection without recreating it or uploading vectors. They are intended as a lightweight validation layer after the benchmark collection already exists.

```bat
python -m scripts.validation.check_qdrant_collection --strict
python -m scripts.evaluation.compare_qdrant_file_dense
python -m scripts.validation.check_qdrant_file_dense_comparison --strict
```

Current-green POC state:

```text
collection_name = ml_radar_dense_benchmark_v1
collection_exists = true
points_count = 60954
corpus_doc_count = 60954
enabled_queries_count = 22
query_count = 22
error_count = 0
mean_overlap_ratio_at_k = 1.0
min_overlap_ratio_at_k = 1.0
required_failed_count = 0
```

The POC layer uses `radar_core/retrieval/qdrant_store.py` as a read-only Qdrant adapter. It validates collection health and compares Qdrant dense search with current file-dense search. It is not a public API backend yet and does not introduce `/search?mode=dense_qdrant`.

## Experimental Qdrant API endpoint

The experimental Qdrant API endpoint exposes Qdrant dense retrieval through a separate endpoint without changing the stable `/search` contract.

```text
GET /experimental/search/qdrant?query=protein+language+models&top_k=5
```

Expected response contract:

```text
mode = dense_qdrant
collection_name = ml_radar_dense_benchmark_v1
results[].document.canonical_id
results[].document.title
results[].retrieval.score
results[].retrieval.dense_score
results[].rank
```

Validation command:

```bash
python -m scripts.validation.check_qdrant_api_experimental --strict
```

Expected strict result:

```text
status_code = 200
mode = dense_qdrant
collection_name = ml_radar_dense_benchmark_v1
result_count > 0
required_failed_count = 0
```

Important boundaries:

- `/search` remains unchanged and still supports only `lexical`, `dense`, and `hybrid`.
- `SearchRuntime` and `ML_RADAR_SEARCH_BACKEND` are not changed.
- Qdrant is not the production default backend.
- The endpoint requires file runtime, the current embedding model, a running Qdrant container, and an existing benchmark collection.
- The endpoint is intentionally placed under `/experimental/*` until the Qdrant serving path is promoted.


## Discovery API regression

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.run_discovery_api_regression
```

Common variants:

```bat
python -m scripts.validation.run_discovery_api_regression --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments --include-controlled-search-quality-experiments
python -m scripts.validation.run_discovery_api_regression --include-qdrant-benchmark --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-qdrant-benchmark --include-retrieval-eval --include-search-quality-experiments --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-qdrant-serving-poc --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-qdrant-api --include-qdrant-serving-poc --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-qdrant-benchmark --include-qdrant-serving-poc --include-qdrant-api --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-db-smoke --include-dod
python -m scripts.validation.run_discovery_api_regression --include-live-ui-check
```

Supported runner flags:

```text
--skip-similar-rebuild
--similar-top-k
--include-retrieval-eval
--include-search-quality-experiments
--include-controlled-search-quality-experiments
--include-qdrant-benchmark
--include-qdrant-serving-poc
--include-qdrant-api
--include-db-smoke
--include-dod
--include-live-ui-check
```

## Full strict DoD

Current checkpoint DoD includes:

```text
known issues
artifacts
GitHub enrichment
Hugging Face enrichment
paper features
similar papers
Discovery API
topic clusters
topic projection
Streamlit Discovery UI
```

Current full strict DoD command should include all active required gates supported by the current project codebase:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api --require-topic-clusters --require-topic-projection --require-streamlit-discovery-ui --require-golden-queries
```

Expected:

```text
dod_passed = true
required_failed_count = 0
```

If local `--help` does not show these gates, sync the DoD script before treating local docs as current.

---

# Design notes

The current API reflects project architecture:

- canonical JSONL remains paper source of truth;
- Postgres is a materialized serving layer;
- retrieval artifacts are file-based derived artifacts;
- artifact layer is a separate DB-backed evidence/materialization plane;
- feature/ranking/detail/similar/topic-cluster layers are derived discovery/product layers;
- file and DB backends are intentionally asymmetric;
- artifact API is DB-only in v1;
- Discovery API is file-first;
- Discovery ranking uses profiles as base presets and query parameters as explicit overrides;
- Discovery topic-cluster endpoints serve existing validated artifacts and do not compute clustering at request time;
- Discovery topic-map endpoint serves precomputed projection artifacts and does not compute UMAP at request time;
- `has_code_link` remains a legacy canonical/source field;
- trusted artifact filters operate through `paper_artifact_links`;
- GitHub/HF enrichment is artifact metadata, not paper truth;
- process-local caches are runtime accelerators, not truth layers.
- Qdrant benchmark is evaluation-only in the current checkpoint and is not yet a production search backend.

---

# Next API directions

Near-term:

```text
docs / runbook / API reference sync with current checkpoint
small API/UI polish only after docs sync
more explicit cache diagnostics if needed
cluster map UX improvements
artifact explorer UX improvements
Golden Set Expansion v2 support in evaluation docs
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

Non-goal right now:

```text
do not start Qdrant/RAG/Airflow until current checkpoint docs and regression commands are stable
```
