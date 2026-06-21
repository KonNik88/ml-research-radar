# API Reference

## Purpose

This document describes the current public API surface of **ML Research Radar**.

ML Research Radar is a paper-centric canonical corpus and discovery platform for
ML/AI research.

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
Qdrant = optional derived vector-serving implementation
artifact DB = derived evidence/materialization layer
paper_features / ranking / detail / similar / topic clusters = derived discovery layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin API client
```

---

## Current stable baseline

Current checkpoint:

```text
Retrieval Serving Checkpoint v1 / Search API Semantics Cleanup v1
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
dense_vectors_normalized = true
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

github_found_count ≈ 5339
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
```

Current Golden Set baseline:

```text
golden_queries_enabled_count = 34
golden_queries_explicit_count = 34
golden_queries_weak_pattern_count = 0
```

Current Qdrant baseline:

```text
collection = ml_radar_dense_benchmark_v1
points_count = 60954
vector_size = 384
distance = Cosine
transport = grpc
selected_profile = ef_256
exact = false
hnsw_ef = 256
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

The two backends intentionally expose the same top-level app where possible, but
they are not fully symmetric.

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
- supports exact file dense search;
- supports file-backed hybrid search;
- supports explicit experimental Qdrant dense search;
- supports Discovery API file-first derived artifacts.

Primary endpoint:

```text
GET /search
```

Supported public search modes:

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

DB-backed endpoints include:

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
/experimental/search/qdrant
```

Unsupported DB search modes return structured `400 Bad Request`.

---

## Public vs experimental search semantics

Public search:

```text
GET /search?mode=lexical
→ file lexical retrieval in file runtime
→ DB lexical retrieval in db runtime

GET /search?mode=dense
→ exact file dense retrieval
→ file runtime only

GET /search?mode=hybrid
→ file lexical + exact file dense hybrid retrieval
→ file runtime only
```

Experimental Qdrant search:

```text
GET /experimental/search/qdrant
→ Qdrant dense search over the same retrieval build
→ file runtime only
```

Important guarantees:

```text
Qdrant is optional.
Qdrant is not canonical truth.
Qdrant is not required for /health readiness.
Qdrant does not change /search behavior.
Qdrant does not introduce fallback.
Qdrant is not the public dense/hybrid default.
```

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

Common error codes:

```text
bad_request
validation_error
runtime_not_ready
file_not_found
internal_error
dense_backend_bad_request
dense_backend_unavailable
dense_backend_incompatible
dense_backend_invalid_result
```

Some FastAPI `HTTPException` responses may use the native FastAPI shape:

```json
{
  "detail": "Document not found: <canonical_id>"
}
```

Typical examples:

```text
invalid top_k / invalid query params -> 400 or 422
invalid mode enum -> 422
unsupported DB search mode -> 400
runtime not loaded -> 503 runtime_not_ready
Qdrant unavailable -> 503 dense_backend_unavailable
Qdrant incompatible collection/build -> 503 dense_backend_incompatible
Qdrant invalid result or hydration miss -> 503 dense_backend_invalid_result
unknown ranking profile -> 404
unknown canonical_id in detail endpoint -> 404
invalid discovery ranking sort_by -> 422
invalid discovery ranking year range -> 400
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

Notes:

- In `file` mode, readiness is based on loaded manifest, documents, lexical
  artifacts, dense artifacts, and embedding model.
- In `db` mode, readiness is based on DB store availability and DB connectivity.
- Qdrant is not required for `/health` readiness.

If file runtime is ready but Qdrant is unavailable:

```text
GET /health
→ 200 OK
→ ready=true
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

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `refresh_qdrant` | bool | false | force a fresh live Qdrant diagnostics probe instead of using the bounded runtime cache |

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
qdrant
last_load_error
last_loaded_at
last_reload_at
model_reused
current_model_name
```

### Qdrant diagnostics

`/runtime` includes an optional `qdrant` diagnostics block.

Fields:

```text
configured
ok

host
port
grpc_port
prefer_grpc
transport
collection_name
timeout_sec
check_compatibility

collection_exists
points_count
expected_corpus_doc_count
points_match_corpus

vector_size
distance
status
optimizer_status
error

probe_cached
probe_checked_at
probe_cache_age_sec
probe_ttl_sec

profile_name
exact
hnsw_ef
build_id

backend_created
compatibility_checked
compatibility_ok

request_count
success_count
failure_count

last_status
last_request_at
last_success_at
last_failure_at

last_failure_category
last_failure_stage
last_failure_message

last_result_count
last_timing_ms

requested_vector_backend
effective_vector_backend
fallback_applied
```

Semantics:

- Qdrant diagnostics are informational.
- Qdrant remains optional.
- Qdrant is not canonical truth.
- Qdrant is not required for `/health`.
- Qdrant diagnostics do not change `/search` backend semantics.
- If Qdrant is unavailable, `/runtime` still returns `200 OK`,
  `qdrant.ok=false`, and `qdrant.error` contains diagnostic information.
- `GET /runtime` may use a bounded diagnostics cache.
- `GET /runtime?refresh_qdrant=true` forces a fresh live probe.
- `fallback_applied` must remain `false`.

---

## `POST /reload`

Reloads the current runtime.

File backend reloads:

```text
latest retrieval manifest
canonical documents
lexical artifacts
dense artifacts
embedding model
experimental Qdrant backend cache reset
Qdrant runtime observability counters reset
Discovery caches
```

DB backend reloads:

```text
Postgres-backed runtime
DB store connectivity
document count snapshot
Discovery caches
```

Response fields:

```text
status
backend_mode
message
build_id
corpus_doc_count
embedding_model_name
model_reused
last_reload_at
```

---

# Search API

## `GET /search`

Main free-form relevance-search endpoint.

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `query` | string | required | search query |
| `mode` | lexical / dense / hybrid | hybrid | DB backend supports lexical only |
| `top_k` | int | settings default | capped by `max_top_k` |
| `rank` | bool | false | explicit optional heuristic reranking where supported |
| `year_from` | int | null | lower year bound |
| `year_to` | int | null | upper year bound |
| `category` | string | null | category/concept/keyword/tag filter |
| `source` | string | null | source filter |
| `publication_type` | string | null | publication type filter |
| `venue` | string | null | venue/journal/conference/publisher filter |
| `open_access` | bool | null | open-access filter |
| `has_code_link` | bool | null | legacy canonical/source-layer code link flag |
| `offset` | int | 0 | pagination offset |
| `sort_by` | relevance / year_desc / year_asc | relevance | DB lexical respects relevance/year sorting |

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

Examples:

```http
GET /search?query=graph%20neural%20networks&mode=lexical&top_k=5
GET /search?query=graph%20neural%20networks&mode=dense&top_k=5
GET /search?query=graph%20neural%20networks&mode=hybrid&top_k=5
GET /search?query=graph%20neural%20networks&mode=hybrid&top_k=5&rank=true
```

### Search ranking semantics

Current accepted semantics:

```text
rank=false
→ default and current reference behavior

rank=true
→ explicit optional/experimental heuristic reranking
```

Accepted ranking evidence concluded:

```text
recommended_outcome = reject_heuristic_reranking
reference_behavior = unranked hybrid
public_behavior_change = false
```

Therefore:

- the current heuristic ranking is not promoted as a default relevance strategy;
- `rank=true` is still available for explicit inspection/diagnostics;
- future reranking must be evaluated in a separate evidence-backed slice.

### Candidate-depth semantics

For file search, the service retrieves a larger internal candidate pool before
filtering, ranking, pagination, and truncation:

```text
candidate_k = min(
    max(top_k + offset, top_k * 5, 50),
    corpus_size
)
```

For hybrid retrieval, this applies per component before merge/deduplication.

### Search response shape

```json
{
  "query": "graph neural networks",
  "mode": "hybrid",
  "top_k": 5,
  "rank_applied": false,
  "build_id": "20260504T164021Z",
  "meta": {
    "build_id": "20260504T164021Z",
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
        "score": null,
        "lexical_score": 0.4,
        "dense_score": 0.7,
        "hybrid_score": 0.535
      },
      "ranking": null
    }
  ]
}
```

When `rank=true`, each result may include:

```json
"ranking": {
  "final_score": 0.82,
  "retrieval_score": 0.75,
  "recency_score": 0.9,
  "source_support_score": 0.3,
  "metadata_quality_score": 0.8
}
```

---

# Experimental Qdrant Search API

## `GET /experimental/search/qdrant`

Explicit experimental Qdrant dense-search endpoint.

This endpoint:

- requires file backend runtime;
- uses the current embedding model;
- uses the current retrieval build;
- uses `QdrantDenseBackend`;
- uses the configured Qdrant profile;
- searches the configured Qdrant collection;
- hydrates against the active file runtime;
- returns `mode=dense_qdrant`;
- fails explicitly on backend, compatibility, or result errors;
- does not fall back to file dense retrieval.

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `query` | string | required | search query |
| `top_k` | int | settings default | capped by `max_top_k` |

Example:

```http
GET /experimental/search/qdrant?query=protein%20language%20models&top_k=5
```

Response fields include:

```text
query
mode
top_k
build_id
collection_name
profile_name
exact
hnsw_ef
meta
results
```

Each result includes:

```text
rank
document
score
point_id
dense_index
payload
```

Failure semantics:

```text
invalid request
→ 400 dense_backend_bad_request

Qdrant unavailable
→ 503 dense_backend_unavailable

collection/build/vector incompatibility
→ 503 dense_backend_incompatible

invalid backend result or hydration miss
→ 503 dense_backend_invalid_result
```

Health isolation:

```text
Qdrant failure does not make /health unhealthy.
Qdrant failure does not change public /search behavior.
Qdrant failure does not trigger fallback.
```

---

# Documents API

The documents API is DB-backed and requires `ML_RADAR_SEARCH_BACKEND=db`.

## `GET /documents`

Browse/filter canonical documents from Postgres.

Common query parameters:

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

Supported sort examples:

```text
year_desc
year_asc
title_asc
```

Response fields:

```text
total
offset
limit
sort_by
results[]
```

Each result uses the same `SearchResultDocument` shape as `/search`.

---

# Artifacts API

The artifacts API is DB-backed and requires `ML_RADAR_SEARCH_BACKEND=db`.

## `GET /artifacts`

Lists artifact entities.

Common query parameters:

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

Supported `github_status` values:

```text
found
not_found
forbidden
rate_limited
error
skipped_invalid_external_id
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
pushed_desc
updated_desc
```

GitHub date filter semantics:

```text
pushed_after / pushed_before
→ filter by metadata.github.pushed_at

updated_after / updated_before
→ filter by materialized GitHub repository updated_at
```

Date filter values are parsed by PostgreSQL as timestamps. Recommended request
format is ISO-8601, for example:

```text
2024-01-01T00:00:00Z
```

Rows without the relevant GitHub date metadata do not match the corresponding
date filter. These fields remain artifact metadata only: they do not change
canonical paper truth, paper ranking, retrieval behavior, Qdrant behavior, or
Streamlit response schemas.

Example queries:

```http
GET /artifacts?provider=github&pushed_after=2024-01-01T00:00:00Z&sort_by=pushed_desc&limit=5
GET /artifacts?provider=github&pushed_before=2024-01-01T00:00:00Z&limit=5
GET /artifacts?provider=github&updated_after=2024-01-01T00:00:00Z&sort_by=updated_desc&limit=5
GET /artifacts?provider=github&updated_before=2024-01-01T00:00:00Z&limit=5
```

## `GET /artifacts/{artifact_id}`

Returns one artifact entity by normalized artifact ID.

## `GET /artifacts/{artifact_id}/papers`

Returns trusted paper links for one artifact.

## `GET /documents/{canonical_id}/artifacts`

Returns trusted artifacts linked to one canonical paper.

Artifact metadata is a separate evidence/materialization layer. It does not
overwrite canonical paper identity or bibliography.

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

Current profiles include:

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

---

## `GET /discovery/ranking/{profile_name}`

Returns ranked papers for a configured discovery profile, optionally refined
with query-level overrides.

This is profile-based radar ranking over `paper_features_latest.jsonl`, not
free-form retrieval.

Common query parameters:

```text
top_k
min_year
max_year
query_title
source_family
has_code
has_dataset
has_model
has_demo
has_github
has_hf
has_acl
has_doi
sort_by
descending
```

Supported sort fields include:

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

Invalid profile returns `404`.

Invalid `sort_by` returns `422`.

Invalid `min_year > max_year` returns `400`.

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

```text
view=full
```

Missing paper returns `404`.

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

Query parameters:

```text
top_k
rank_by
min_similarity
```

This contract starts from a paper embedding and is intentionally separate from
text-query `/search`.

---

## `GET /discovery/papers/{canonical_id}/cluster`

Returns the latest topic-cluster assignment for one paper.

Response content includes:

```text
canonical_id
cluster_id
cluster_build_id
retrieval_build_id
rank_within_cluster
distance_to_centroid
similarity_to_centroid
cluster label candidates
cluster summary
```

Missing paper or assignment returns `404`.

---

## `GET /discovery/clusters`

Lists current topic clusters from the latest topic-cluster artifact.

Common query parameters:

```text
limit
sort_by
min_size
```

Current checked sort examples:

```text
size_desc
cluster_id_asc
mean_radar_desc
artifact_ready_desc
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

Common query parameters:

```text
top_k
min_year
max_year
has_code
has_github
min_radar_score
min_implementation_readiness_score
min_citation_signal_score
sort_by
```

Current checked sort modes:

```text
rank
similarity_desc
radar_score
implementation_readiness_score
citation_signal_score
year_desc
```

Missing cluster returns `404`.

---

## `GET /discovery/clusters/map`

Returns topic-map projection points from the latest projection artifact.

The endpoint reads existing projection artifacts and does not compute UMAP/PCA
at request time.

Current projection baseline:

```text
projection_algorithm = umap
projection_rows_count = 2080
centroid_count = 80
representative_count = 800
sampled_count = 1200
```

Common query parameters:

```text
include_papers
limit
cluster_id
```

---

# Validation entry points

## Retrieval-serving checkpoint

Default lightweight gate:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint
```

Default required checks:

```text
ranking_evidence_regression
qdrant_hybrid_evidence
```

Extended local gate:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint ^
  --include-serving-performance-evidence ^
  --include-qdrant-collection-live ^
  --include-api-smoke
```

Optional flags:

```text
--include-serving-performance-evidence
--require-serving-performance-evidence
--include-qdrant-collection-live
--require-qdrant-collection-live
--include-api-smoke
--skip-qdrant-hybrid-evidence
--dry-run
```

The wrapper composes existing accepted validators. It does not rerun heavy
benchmark/evaluation jobs by default.

Generated outputs:

```text
artifacts/reports/validation/retrieval_serving_checkpoint_latest.json
artifacts/reports/validation/retrieval_serving_checkpoint_latest.md
artifacts/reports/validation/history/retrieval_serving_checkpoint_<timestamp>.json
artifacts/reports/validation/history/retrieval_serving_checkpoint_<timestamp>.md
```

Generated reports should not be committed unless a separate artifact-retention
policy explicitly says otherwise.

## Ranking evidence regression

```bat
python -m scripts.validation.check_ranking_evidence_regression ^
  --config-path configs
anking_evaluation_v1.yaml ^
  --report-path artifacts
eports\evaluation
anking_evaluation_latest.json ^
  --retrieval-manifest-path artifacts
etrieval\manifests\latest.json
```

Accepted green output:

```text
strict=True
evaluation_build_id=20260504T164021Z
manifest_build_id=20260504T164021Z
recommended_outcome=reject_heuristic_reranking
required_failed_count=0
```

## Qdrant collection live check

```bat
python -m scripts.validation.check_qdrant_collection --strict
```

Requires running Qdrant.

## Qdrant hybrid evaluation evidence check

```bat
python -m scripts.validation.check_qdrant_hybrid_evaluation --strict
```

Validates existing Qdrant hybrid evidence report.

## Discovery API check

```bat
python -m scripts.validation.check_discovery_api --strict
```

## Artifact API filter regression

DB-backed artifact API filter checks require a running Postgres serving layer
and DB backend mode:

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m pytest tests/integration/test_api_artifacts_db.py tests/integration/test_api_artifacts_github_filters_db.py tests/integration/test_api_artifacts_github_date_filters_db.py tests/integration/test_api_documents_artifact_filters_db.py tests/integration/test_api_github_enrichment_db.py -q
```

Expected current green baseline:

```text
35 passed
```

---

# Current API safety summary

```text
No public /search behavior change in this cleanup.
No Qdrant promotion.
No fallback.
No retrieval rebuild.
No ranking formula change.
No generated report commit.
```

The API documentation should remain synchronized with the accepted retrieval,
Qdrant, runtime, and ranking evidence checkpoints.
