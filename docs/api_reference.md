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
→ local graph evidence/review artifacts
→ Citation Graph status/compatibility surface
→ Citation Graph outgoing references endpoint
→ Citation Graph incoming citations endpoint
→ Citation Graph traversal API checkpoint
→ internal Citation Graph fixture store/query core
→ Discovery API
→ Graph API / Streamlit productization design
→ Citation Graph Streamlit status panel
→ Citation Graph Paper workspace panel
→ Citation Graph Diagnostics UI panel
→ Citation Graph External Reference Lookup UI panel
→ Streamlit Discovery UI
→ Runtime Service Contract v0.1
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
runtime_services_v0.1 = unified service/capability status over current backend mode
Citation / Reference Graph status API = disabled-by-default status/compatibility safety surface
Citation / Reference Graph outgoing references API = first narrow read-only traversal endpoint
Citation / Reference Graph fixture store = internal read-only query core for fixture-backed semantics
Citation / Reference Graph traversal/runtime API = partially implemented for outgoing references, incoming citations, external-reference papers, source-family diagnostics, top-referenced-papers diagnostics, and top-external-references diagnostics only; full-runtime surfaces are not implemented
```

---

## Current stable baseline

Current checkpoint:

```text
Retrieval Serving Checkpoint v1 / Search API Semantics Cleanup v1
Citation Graph API Disabled Status Endpoint v0.1
Citation Graph Status Compatibility Probe v0.1
Citation Graph Fixture Store v0.1
Citation Graph Traversal API Checkpoint v0.1
Citation Graph Source Families Endpoint v0.1
Citation Graph Traversal API Checkpoint v0.2
Citation Graph Top Referenced Papers Endpoint v0.1
Citation Graph Top External References Endpoint v0.1
Citation Graph Traversal API Checkpoint v0.3
Citation Graph API Regression Check v0.1
Citation Graph API Regression DoD Wiring v0.1
Graph API / Streamlit Productization Design v0.1
Citation Graph Streamlit Status Panel v0.1
Citation Graph Paper Workspace Panel v0.1
Citation Graph Diagnostics UI v0.1
Citation Graph External Reference Lookup UI v0.1
Citation Graph UI Productization Checkpoint v0.1
Citation Graph Store Cache & Reload Regression v0.1
Citation Graph Failure Isolation & Error Recovery v0.1
Citation Graph Live Smoke & Known-Issues Hardening v0.1
Runtime Service Contract v0.1
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
service_status
last_load_error
last_loaded_at
last_reload_at
model_reused
current_model_name
```

### Service status

`/runtime` includes a machine-readable `service_status` block using
`runtime_services_v0.1`.

The block summarizes required and optional runtime services for the active
backend mode without probing additional resources beyond the runtime snapshot.

Top-level fields:

```text
schema_version
overall_status
backend_mode
services
counts
caveats
```

Expected service keys:

```text
api_runtime
file_retrieval_runtime
postgres_document_runtime
search_lexical
search_dense
search_hybrid
artifact_api
workspace_collections
qdrant_experimental
citation_graph
```

Semantics:

- `overall_status=ready` means health-blocking services for the selected backend
  mode are available.
- Optional services may be `unavailable`, `not_configured`, `unsupported`, or
  `unknown` without making `/health` fail.
- Qdrant remains optional and experimental.
- Citation graph remains optional, disabled by default, and caveated as derived
  local-inspection evidence.
- Workspace availability remains endpoint-local unless DB runtime has already
  proven shared PostgreSQL connectivity.
- Streamlit feature actions use `service_status.services[*]` as the capability
  decision source for mode-specific and optional endpoints instead of inferring
  availability from endpoint errors.

See `docs/runtime_service_contract_v0.1.md`.

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


# Citation / Reference Graph API

## Current implementation status

The API now exposes a deliberately narrow citation/reference graph surface:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

Current v0.1 semantics:

```text
status_endpoint = implemented
compatibility_probe = implemented
read_only = true
disabled_by_default = true
feature_flag = ML_RADAR_CITATION_GRAPH_API_ENABLED
fixture_store = implemented_internal
outgoing_references_endpoint = implemented
incoming_citations_endpoint = implemented
external_reference_papers_endpoint = implemented
source_family_endpoint = implemented
top_referenced_papers_endpoint = implemented
top_external_references_endpoint = implemented
full_graph_runtime_loader = not implemented
graph_db_materialization = not implemented
streamlit_graph_evidence_panels = implemented
full_graph_visualization_ui = not implemented
streamlit_graph_status_panel = implemented
streamlit_graph_paper_workspace_panel = implemented
streamlit_graph_diagnostics_ui = implemented
streamlit_graph_external_reference_lookup_ui = implemented
graphrag = not implemented
publication_ready = false
manual_review_required = true
```

Productization checkpoint markers:

```text
Citation Graph UI Productization Checkpoint v0.1
streamlit_graph_evidence_panels = implemented
streamlit_graph_status_panel = implemented
streamlit_graph_paper_workspace_panel = implemented
streamlit_graph_diagnostics_ui = implemented
streamlit_graph_external_reference_lookup_ui = implemented
full_graph_visualization_ui = not implemented
```

`CitationGraphStore` remains a narrow file-backed local-inspection store. The
status payload intentionally keeps `runtime_loader_implemented=false` because a
promoted full graph runtime subsystem does not exist. It also keeps
`traversal_endpoints_implemented=false` as the broad full-runtime-surface marker;
the six bounded traversal/diagnostics routes are nevertheless implemented and
checkpointed. Any change to those status fields requires a separate response-
compatibility/schema slice.

The status endpoint remains the safety/status/compatibility surface. The
references endpoint returns outgoing references for one canonical paper. The
citations endpoint returns incoming resolved internal paper citations for one
canonical paper. The external-reference papers endpoint returns canonical papers
that reference one unresolved `external_reference` node. The source-families
endpoint returns source-family reference-evidence diagnostics. The top-referenced-papers
endpoint returns bounded diagnostics over resolved internal reference counts. The
top-external-references endpoint returns bounded diagnostics over unresolved
external reference counts. All traversal routes are
read-only, feature-flagged, compatibility-gated, and backed by `CitationGraphStore`
over the configured local graph root.

These routes must not be interpreted as graph publication, GraphRAG, graph DB
materialization, a complete citation index, or promotion of the graph as
canonical truth.

The rollout so far is:

```text
1. GET /citation-graph/status
2. read-only compatibility probe
3. internal fixture-backed CitationGraphStore
4. GET /citation-graph/papers/{canonical_id}/references
5. GET /citation-graph/papers/{canonical_id}/citations
6. GET /citation-graph/external-references/{reference_id}/papers
7. GET /citation-graph/source-families
8. GET /citation-graph/top-referenced-papers
9. GET /citation-graph/top-external-references
```

No full runtime graph loader,
graph DB materialization, Streamlit graph UI, GraphRAG, publication step,
`/search` change, Qdrant change, ranking change, or canonical truth change is
implemented by this API surface.


## Graph API / Streamlit productization contract

The accepted Citation Graph API block is ready to be consumed by future
Streamlit UI slices, but this contract does not add new endpoints or UI code.

Streamlit consumption rules:

```text
Streamlit is a thin API client.
Streamlit must call FastAPI endpoints for graph evidence.
Streamlit must not read graph JSONL/package/report files directly.
Streamlit must not import CitationGraphStore.
Streamlit must not introduce NetworkX, Neo4j, GraphRAG, or a full graph runtime loader.
```

Planned Citation Graph UI surfaces:

```text
Status panel:
  GET /citation-graph/status

Selected paper evidence panel:
  GET /citation-graph/papers/{canonical_id}/references
  GET /citation-graph/papers/{canonical_id}/citations

Diagnostics panel:
  GET /citation-graph/source-families
  GET /citation-graph/top-referenced-papers
  GET /citation-graph/top-external-references

External reference lookup:
  GET /citation-graph/external-references/{reference_id}/papers
```

Required UI caveats:

```text
metadata_reference_fields_only
not_a_complete_citation_index
manual_review_required
publication_ready_false
not_global_citation_metric for top-reference diagnostics
not_publication_grade_ranking for top-reference diagnostics
not_publication_grade_reference_entity for top external references
```

Paper–Artifact evidence rule:

```text
Use existing Artifact API endpoints first:
GET /artifacts
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/papers
GET /documents/{canonical_id}/artifacts

Do not add a dedicated Paper–Artifact Graph API unless a later design slice
identifies a concrete gap that these Artifact API endpoints cannot cover.
```

## Streamlit Citation Graph status panel

Current Streamlit implementation:

```text
Citation Graph Streamlit Status Panel v0.1 = implemented status-only UI slice
```

UI behavior:

```text
Streamlit calls GET /citation-graph/status through FastAPI.
The panel renders runtime_enabled, available, safe_to_serve_locally, and runtime_loader_implemented.
The panel exposes graph/status details and caveats.
The response is stored in citation_graph_status_payload session state.
```

Boundary:

```text
no direct reads from data/graphs/*
no CitationGraphStore import from Streamlit
no references/citations table UI in this slice
no source-family/top-reference diagnostics UI in this slice
no external-reference lookup UI in this slice
no graph visualization
no NetworkX/Neo4j/GraphRAG
no full graph runtime loader
no graph DB materialization
```


## Streamlit Citation Graph Paper workspace panel

Current Streamlit implementation:

```text
Citation Graph Paper Workspace Panel v0.1 = implemented selected-paper evidence UI slice
```

UI behavior:

```text
Streamlit calls GET /citation-graph/papers/{canonical_id}/references through FastAPI.
Streamlit calls GET /citation-graph/papers/{canonical_id}/citations through FastAPI.
The Paper workspace renders outgoing references and incoming resolved citations as evidence tables.
The response payloads are stored in selected_paper_citation_references_payload and selected_paper_citation_citations_payload session state.
```

Boundary:

```text
no direct reads from data/graphs/*
no CitationGraphStore import from Streamlit
no source-family/top-reference diagnostics UI in this slice
no external-reference lookup UI in this slice
no graph visualization
no NetworkX/Neo4j/GraphRAG
no full graph runtime loader
no graph DB materialization
```

## Streamlit Citation Graph diagnostics panel

Current Streamlit implementation:

```text
Citation Graph Diagnostics UI v0.1 = implemented diagnostics-table UI slice
```

UI behavior:

```text
Streamlit calls GET /citation-graph/source-families through FastAPI.
Streamlit calls GET /citation-graph/top-referenced-papers through FastAPI.
Streamlit calls GET /citation-graph/top-external-references through FastAPI.
The diagnostics panel renders source-family reference diagnostics, top resolved-internal referenced papers, and top unresolved external references as explicitly non-publication-grade diagnostic tables.
The response payloads are stored in citation_graph_source_families_payload, citation_graph_top_referenced_papers_payload, and citation_graph_top_external_references_payload session state.
```

Boundary:

```text
no direct reads from data/graphs/*
no CitationGraphStore import from Streamlit
no external-reference lookup UI in this slice
no graph visualization
no NetworkX/Neo4j/GraphRAG
no full graph runtime loader
no graph DB materialization
no endpoint/API schema changes
no canonical/retrieval/Qdrant/Postgres/ranking/publication change
```


## Streamlit Citation Graph external reference lookup panel

Current Streamlit implementation:

```text
Citation Graph External Reference Lookup UI v0.1 = implemented external-reference lookup UI slice
```

UI behavior:

```text
Streamlit calls GET /citation-graph/external-references/{reference_id}/papers through FastAPI.
The reference_id input is URL-quoted before being inserted into the path.
The panel renders papers that reference one unresolved external_reference node.
The response payload is stored in citation_graph_external_reference_lookup_payload session state.
```

Boundary:

```text
no direct reads from data/graphs/*
no CitationGraphStore import from Streamlit
no graph visualization
no NetworkX/Neo4j/GraphRAG
no full graph runtime loader
no graph DB materialization
no endpoint/API schema changes
no canonical/retrieval/Qdrant/Postgres/ranking/publication change
```

## Configuration

The citation graph API is controlled by:

```bat
set ML_RADAR_CITATION_GRAPH_API_ENABLED=false
```

Default behavior:

```text
ML_RADAR_CITATION_GRAPH_API_ENABLED=false
→ /citation-graph/status reports runtime_enabled=false
→ /citation-graph/papers/{canonical_id}/references fails closed
→ /citation-graph/papers/{canonical_id}/citations fails closed
→ /citation-graph/external-references/{reference_id}/papers fails closed
→ /citation-graph/source-families fails closed
→ /citation-graph/top-referenced-papers fails closed
→ /citation-graph/top-external-references fails closed
→ error_code=graph_runtime_not_enabled
```

Explicit local-inspection behavior:

```bat
set ML_RADAR_CITATION_GRAPH_API_ENABLED=true
```

When enabled, graph-facing routes perform a read-only compatibility probe over
the configured graph root and validation reports before serving local graph
evidence. If the graph is missing, unsafe, stale, incompatible, or configured for
unsupported public exposure, graph routes fail closed with a graph-specific
error code.

Relevant settings:

```text
ML_RADAR_CITATION_GRAPH_API_ENABLED
ML_RADAR_CITATION_GRAPH_EXPOSURE_MODE
ML_RADAR_CITATION_GRAPH_ROOT
ML_RADAR_CITATION_GRAPH_REPORTS_ROOT
ML_RADAR_CITATION_GRAPH_VERSION
ML_RADAR_CITATION_GRAPH_DEFAULT_LIMIT
ML_RADAR_CITATION_GRAPH_MAX_LIMIT
ML_RADAR_CITATION_GRAPH_REQUIRE_REVIEW_FOR_PUBLIC
```

## `GET /citation-graph/status`

Returns the current citation/reference graph API status and compatibility
summary.

Current expected behavior:

- when disabled, returns disabled/unavailable status;
- when enabled, probes local graph artifact/report compatibility read-only;
- returns no traversal items;
- does not mutate canonical documents;
- does not mutate graph outputs, packages, reports, or latest pointers;
- does not mutate Postgres;
- does not change `/search`;
- does not change Discovery API behavior;
- works independently of Qdrant;
- preserves manual-review and publication caveats.

A compatible local-inspection status means:

```text
runtime_enabled = true
available = true
safe_to_serve_locally = true
compatibility_probe_implemented = true
runtime_loader_implemented = false
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

`manual_review_complete=false` does not make local status compatibility fail. It
remains a caveat and publication blocker.

Compatibility/status payloads may still report
`traversal_endpoints_implemented=false` as a broad full-runtime-surface marker.
That field does not mean the narrow `/references`, `/citations`,
`/external-references/{reference_id}/papers`, `/source-families`,
`/top-referenced-papers`, and `/top-external-references` routes are absent; it
means the full traversal/runtime
surface remains incomplete.

## `GET /citation-graph/papers/{canonical_id}/references`

Returns outgoing reference evidence for a canonical paper from the local
citation/reference graph.

Path parameters:

| parameter | type | notes |
|---|---:|---|
| `canonical_id` | string | canonical paper id or paper node id accepted by the store |

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | `ML_RADAR_CITATION_GRAPH_DEFAULT_LIMIT` | must be `>= 1` and `<= ML_RADAR_CITATION_GRAPH_MAX_LIMIT` |
| `offset` | int | 0 | must be `>= 0` |

Successful response shape:

```text
graph
query
items
page
caveats
```

Returned items may include both:

```text
paper_references_paper      -> resolved canonical-paper reference
paper_references_external   -> unresolved external_reference evidence
```

The endpoint preserves these caveats:

```text
metadata_reference_fields_only
not_a_complete_citation_index
manual_review_required
publication_ready_false
unresolved_references_preserved_as_external_reference_nodes
```

Current endpoint behavior:

```text
disabled feature flag -> 503 graph_runtime_not_enabled
missing/incompatible graph -> 503 graph_artifacts_* / graph_*_mismatch
unknown canonical_id -> 404 canonical_id_not_found
limit above max -> 400 graph_result_limit_exceeded
success -> 200 graph/query/items/page/caveats envelope
```

This endpoint is intentionally narrow. It does not implement incoming citation
semantics; those belong to the paired `/citations` endpoint. It also does not
implement source-family diagnostics, top-reference rankings, full runtime graph
loading, graph DB materialization, Streamlit graph UI, GraphRAG, publication, or
any `/search` behavior change.

## `GET /citation-graph/papers/{canonical_id}/citations`

Returns incoming citation evidence for a canonical paper from the local
citation/reference graph.

Path parameters:

| parameter | type | notes |
|---|---:|---|
| `canonical_id` | string | canonical paper id or paper node id accepted by the store |

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | `ML_RADAR_CITATION_GRAPH_DEFAULT_LIMIT` | must be `>= 1` and `<= ML_RADAR_CITATION_GRAPH_MAX_LIMIT` |
| `offset` | int | 0 | must be `>= 0` |

Successful response shape:

```text
graph
query
items
page
caveats
```

Returned items include only resolved internal paper-reference edges:

```text
paper_references_paper -> source canonical paper references the target canonical paper
```

Unresolved `paper_references_external` evidence is not counted as an incoming
canonical-paper citation.

The endpoint preserves these caveats:

```text
metadata_reference_fields_only
not_a_complete_citation_index
manual_review_required
publication_ready_false
resolved_internal_references_only
```

Current endpoint behavior:

```text
disabled feature flag -> 503 graph_runtime_not_enabled
missing/incompatible graph -> 503 graph_artifacts_* / graph_*_mismatch
unknown canonical_id -> 404 canonical_id_not_found
limit above max -> 400 graph_result_limit_exceeded
success -> 200 graph/query/items/page/caveats envelope
```

This endpoint is intentionally narrow. It does not implement source-family
diagnostics, top-reference rankings, full runtime graph loading, graph DB
materialization, Streamlit graph UI, GraphRAG, publication, or any `/search`
behavior change.

## `GET /citation-graph/external-references/{reference_id}/papers`

Returns canonical papers that reference one unresolved external reference from
the local citation/reference graph.

Path parameters:

| parameter | type | notes |
|---|---:|---|
| `reference_id` | string/path | external reference node id, reference key, or normalized value accepted by the store |

The route uses a path-style parameter because DOI-like normalized values may
contain `/`. Clients should URL-encode slash-containing values, for example:

```text
10.1080/14786440009463897 -> 10.1080%2F14786440009463897
```

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | `ML_RADAR_CITATION_GRAPH_DEFAULT_LIMIT` | must be `>= 1` and `<= ML_RADAR_CITATION_GRAPH_MAX_LIMIT` |
| `offset` | int | 0 | must be `>= 0` |

Lookup supports:

```text
external_reference node id
reference_key
normalized_value
```

Successful response shape:

```text
graph
query
items
page
caveats
```

Returned items are papers that have `paper_references_external` edges pointing to
the selected unresolved external reference. Typical item fields:

```text
edge_id
source_canonical_id
source_title
source_year
external_reference_id
reference_type
normalized_reference
source_families
evidence_count
```

The endpoint preserves these caveats:

```text
metadata_reference_fields_only
not_a_complete_citation_index
manual_review_required
publication_ready_false
external_reference_is_unresolved
not_publication_grade_reference_entity
```

Current endpoint behavior:

```text
disabled feature flag -> 503 graph_runtime_not_enabled
missing/incompatible graph -> 503 graph_artifacts_* / graph_*_mismatch
unknown external reference -> 404 external_reference_not_found
limit above max -> 400 graph_result_limit_exceeded
success -> 200 graph/query/items/page/caveats envelope
```

This endpoint is intentionally narrow. It does not resolve the external reference
into a canonical paper, does not expose top external-reference rankings, does not
publish a reference entity catalog, and does not make external references
publication-grade bibliographic entities.

## `GET /citation-graph/source-families`

Returns source-family reference-evidence diagnostics from the local
citation/reference graph.

This endpoint is a compact summary over `source_family` nodes and
`paper_has_reference_source_family` evidence. It is intended for local
inspection and QA, not for publication-grade source coverage measurement.

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | `ML_RADAR_CITATION_GRAPH_DEFAULT_LIMIT` | must be `>= 1` and `<= ML_RADAR_CITATION_GRAPH_MAX_LIMIT` |
| `offset` | int | 0 | must be `>= 0` |

Successful response shape:

```text
graph
query
items
page
caveats
```

Returned items contain bounded diagnostics per source family:

```text
source_family
paper_count_with_reference_evidence
reference_edge_count
resolved_edge_count
external_edge_count
```

The endpoint preserves these caveats:

```text
metadata_reference_fields_only
not_a_complete_citation_index
manual_review_required
publication_ready_false
source_family_reference_evidence_only
not_source_coverage_metric
```

Current endpoint behavior:

```text
disabled feature flag -> 503 graph_runtime_not_enabled
missing/incompatible graph -> 503 graph_artifacts_* / graph_*_mismatch
limit above max -> 400 graph_result_limit_exceeded
success -> 200 graph/query/items/page/caveats envelope
```

This endpoint is intentionally narrow. It does not expose source-family papers,
does not implement source coverage analytics, does not expose top-external-reference
rankings, does not load a full runtime graph, and does not change canonical
truth, `/search`, Qdrant, ranking, DB, Discovery API, Streamlit, graph package
outputs, or publication state.

## `GET /citation-graph/top-referenced-papers`

Returns bounded diagnostics for canonical papers with the highest resolved
internal incoming reference counts in the local citation/reference graph.

This endpoint is intended for local inspection and QA. It is not a global
citation metric, not a publication-grade ranking, and not a replacement for
provider citation counts such as `cited_by_count`.

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | `ML_RADAR_CITATION_GRAPH_DEFAULT_LIMIT` | must be `>= 1` and `<= ML_RADAR_CITATION_GRAPH_MAX_LIMIT` |
| `offset` | int | 0 | must be `>= 0` |

Successful response shape:

```text
graph
query
items
page
caveats
```

Returned items contain resolved internal reference-count diagnostics:

```text
canonical_id
title
year
incoming_resolved_reference_count
source_families
```

The endpoint preserves these caveats:

```text
metadata_reference_fields_only
not_a_complete_citation_index
manual_review_required
publication_ready_false
resolved_internal_reference_count_only
not_global_citation_metric
not_publication_grade_ranking
```

Current endpoint behavior:

```text
disabled feature flag -> 503 graph_runtime_not_enabled
missing/incompatible graph -> 503 graph_artifacts_* / graph_*_mismatch
limit above max -> 400 graph_result_limit_exceeded
success -> 200 graph/query/items/page/caveats envelope
```

This endpoint is intentionally narrow. It counts only resolved internal
`paper_references_paper` edges in the local v0.1 graph. It does not count
unresolved `external_reference` evidence; that evidence is exposed only through
the separate `/citation-graph/top-external-references` diagnostics endpoint. It
does not implement global bibliometrics, does not load a full runtime graph, and
does not change canonical truth, `/search`, Qdrant, ranking, DB, Discovery API,
Streamlit, graph package outputs, or publication state.


## `GET /citation-graph/top-external-references`

Returns bounded diagnostics for unresolved external references with the highest
referencing paper counts in the local citation/reference graph.

This endpoint is intended for local inspection and QA. It is not a global
citation metric, not a publication-grade reference-entity catalog, not a
bibliographic authority file, and not a replacement for provider-level citation
or reference indexes.

Query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | `ML_RADAR_CITATION_GRAPH_DEFAULT_LIMIT` | must be `>= 1` and `<= ML_RADAR_CITATION_GRAPH_MAX_LIMIT` |
| `offset` | int | 0 | must be `>= 0` |

Successful response shape:

```text
graph
query
items
page
caveats
```

Returned items contain unresolved external-reference diagnostics:

```text
external_reference_id
reference_type
normalized_reference
referencing_paper_count
source_families
```

The endpoint preserves these caveats:

```text
metadata_reference_fields_only
not_a_complete_citation_index
manual_review_required
publication_ready_false
external_reference_is_unresolved
not_publication_grade_reference_entity
not_global_citation_metric
not_publication_grade_ranking
```

Current endpoint behavior:

```text
disabled feature flag -> 503 graph_runtime_not_enabled
missing/incompatible graph -> 503 graph_artifacts_* / graph_*_mismatch
limit above max -> 400 graph_result_limit_exceeded
success -> 200 graph/query/items/page/caveats envelope
```

This endpoint is intentionally narrow. It counts only unresolved
`paper_references_external` edges in the local v0.1 graph. It does not resolve
external references into canonical papers, does not make external references
publication-grade bibliographic entities, does not implement global
bibliometrics, does not load a full runtime graph, and does not change canonical
truth, `/search`, Qdrant, ranking, DB, Discovery API, Streamlit, graph package
outputs, or publication state.

## Compatibility failure states

Graph-facing routes fail closed when local graph evidence is missing, unsafe,
stale, or incompatible.

Common graph error codes:

```text
graph_runtime_not_enabled
graph_artifacts_not_found
graph_artifacts_invalid
graph_artifacts_unsafe
graph_version_unsupported
graph_canonical_baseline_mismatch
graph_package_stale
graph_manual_review_incomplete
graph_result_limit_exceeded
canonical_id_not_found
external_reference_not_found
```

Representative interpretations:

```text
feature flag disabled
→ graph_runtime_not_enabled

required graph root / manifest / report missing
→ graph_artifacts_not_found

invalid JSON, malformed counters, or report not ok
→ graph_artifacts_invalid

unsafe manifest/report flag
→ graph_artifacts_unsafe

unsupported graph version
→ graph_version_unsupported

canonical corpus count mismatch
→ graph_canonical_baseline_mismatch

package/report staleness or checksum mismatch
→ graph_package_stale

public exposure requested while manual review is incomplete
→ graph_manual_review_incomplete

requested page limit exceeds configured graph max limit
→ graph_result_limit_exceeded

paper is not present in the local citation graph
→ canonical_id_not_found

external reference is not present in the local citation graph
→ external_reference_not_found
```

These graph errors are endpoint-local. They must not make `/health` unhealthy
when the normal file or DB runtime is otherwise ready.

## Manual live API validation

Manual live API validation after the traversal API checkpoint v0.3 merge:

```text
ML_RADAR_SEARCH_BACKEND=file
ML_RADAR_CITATION_GRAPH_API_ENABLED=true
GET /citation-graph/status -> available=true, safe_to_serve_locally=true, compatibility.ok=true, error_code=null
GET /citation-graph/papers/0bad150e917742a07cf30555c15a5ee6/references?limit=5&offset=0 -> 200, returned=5, total_estimate=81, unresolved external references preserved
GET /citation-graph/papers/11c222e89f686cb704be7834c50dd3aa/citations?limit=5&offset=0 -> 200, returned=5, total_estimate=23, only paper_references_paper items, resolved_internal_references_only caveat
GET /citation-graph/external-references/external_reference:1954a09282cc66f2/papers?limit=5&offset=0 -> 200, returned=4, total_estimate=4, caveats include external_reference_is_unresolved and not_publication_grade_reference_entity
GET /citation-graph/external-references/10.1080%2F14786440009463897/papers?limit=5&offset=0 -> 200, returned=4, total_estimate=4, normalized DOI lookup with slash works through URL encoding
GET /citation-graph/external-references/W2083798294/papers?limit=5&offset=0 -> 200, returned=1, OpenAlex normalized value lookup works
GET /citation-graph/external-references/not-a-real-reference/papers?limit=5 -> 404 external_reference_not_found
GET /citation-graph/external-references/external_reference:1954a09282cc66f2/papers?limit=101 -> 400 graph_result_limit_exceeded
GET /citation-graph/source-families?limit=5&offset=0 -> 200, returned=5, total_estimate=5, caveats include source_family_reference_evidence_only and not_source_coverage_metric
GET /citation-graph/source-families?limit=101 -> 400 graph_result_limit_exceeded
GET /citation-graph/top-referenced-papers?limit=5&offset=0 -> 200, returned=5, total_estimate=1770, caveats include resolved_internal_reference_count_only, not_global_citation_metric, and not_publication_grade_ranking
GET /citation-graph/top-referenced-papers?limit=101 -> 400 graph_result_limit_exceeded
GET /citation-graph/top-external-references?limit=5&offset=0 -> 200, returned=5, total_estimate=468336, caveats include external_reference_is_unresolved, not_publication_grade_reference_entity, not_global_citation_metric, and not_publication_grade_ranking
GET /citation-graph/top-external-references?limit=101 -> 400 graph_result_limit_exceeded
```

## Citation Graph Traversal API Checkpoint v0.1

Status: **accepted docs-only local-inspection checkpoint**

This checkpoint freezes the first narrow citation/reference graph API block as a
stable local-inspection baseline.

Checkpointed routes:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
```

Checkpointed behavior:

```text
status endpoint = compatibility/status surface
outgoing references endpoint = resolved paper references + unresolved external_reference evidence
incoming citations endpoint = resolved internal paper_references_paper edges only
response envelope = graph/query/items/page/caveats
disabled feature flag = fail closed with graph_runtime_not_enabled
unknown canonical_id = canonical_id_not_found
limit above max = graph_result_limit_exceeded
missing/incompatible graph artifacts = graph_artifacts_* / graph_*_mismatch
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

Checkpoint validation evidence:

```text
test_api_citation_graph_references.py = 9 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py with ML_RADAR_SEARCH_BACKEND=file = 7 passed
manual live API check = green for status, references, citations, unknown ids, and limit guards
```

## Citation Graph External Reference Papers Endpoint v0.1

Status: **implemented narrow local-inspection traversal endpoint**

This slice adds the third narrow traversal endpoint:

```text
GET /citation-graph/external-references/{reference_id}/papers
```

Semantics:

```text
external_reference -> papers that reference it
uses paper_references_external incoming edges
accepts external_reference node id, reference_key, or normalized_value
slash-containing DOI values require URL encoding
```

Validation evidence:

```text
test_api_citation_graph_references.py = 15 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py with ML_RADAR_SEARCH_BACKEND=file = 7 passed
manual live API check = green for external_reference id, normalized DOI, normalized OpenAlex value, unknown id, and limit guard
```

Boundary:

```text
external-reference papers endpoint is read-only
external-reference papers endpoint is feature-flagged and compatibility-gated
external references remain unresolved evidence nodes
source-family endpoint = implemented
top-referenced-papers endpoint = implemented
top-external-references endpoint = implemented
full graph runtime loader = not implemented
graph DB materialization = not implemented
Streamlit graph UI = not implemented
GraphRAG = not implemented
/search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, and publication state = unchanged
```

## Citation Graph Source Families Endpoint v0.1

Status: **implemented narrow local-inspection diagnostics endpoint**

This slice adds the fourth narrow traversal/diagnostic endpoint:

```text
GET /citation-graph/source-families
```

Semantics:

```text
source_family -> reference evidence diagnostics
uses paper_has_reference_source_family evidence and per-paper outgoing reference edges
reports paper_count_with_reference_evidence, reference_edge_count, resolved_edge_count, external_edge_count
does not represent publication-grade source coverage
```

Validation evidence:

```text
test_api_citation_graph_references.py = 19 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py with ML_RADAR_SEARCH_BACKEND=file = 7 passed
manual live API check = green for source-families success and limit guard
```

Boundary:

```text
source-families endpoint is read-only
source-families endpoint is feature-flagged and compatibility-gated
source-family diagnostics are reference-evidence-only
source-family diagnostics are not source coverage metrics
top-referenced-papers endpoint = implemented
top-external-references endpoint = implemented
full graph runtime loader = not implemented
graph DB materialization = not implemented
Streamlit graph UI = not implemented
GraphRAG = not implemented
/search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, and publication state = unchanged
```

## Citation Graph Traversal API Checkpoint v0.2

Status: **accepted docs-only local-inspection checkpoint**

This checkpoint freezes the current narrow citation/reference graph API block
after the implemented source-families endpoint and before any top-reference
endpoint work.

Checkpointed routes:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
```

Checkpointed behavior:

```text
status endpoint = compatibility/status surface
outgoing references endpoint = resolved paper references + unresolved external_reference evidence
incoming citations endpoint = resolved internal paper_references_paper edges only
external-reference papers endpoint = papers referencing unresolved external_reference evidence
source-families endpoint = reference-evidence-only diagnostics, not source coverage
response envelope = graph/query/items/page/caveats
disabled feature flag = fail closed with graph_runtime_not_enabled
unknown canonical_id = canonical_id_not_found
unknown external reference = external_reference_not_found
limit above max = graph_result_limit_exceeded
missing/incompatible graph artifacts = graph_artifacts_* / graph_*_mismatch
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

Checkpoint validation evidence:

```text
test_api_citation_graph_references.py = 19 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py with ML_RADAR_SEARCH_BACKEND=file = 7 passed
manual live API check = green for status, references, citations, external-reference papers, source-families, unknown ids, and limit guards
```

Boundary:

```text
checkpoint is docs/regression-hardening only
no new endpoint
top-reference endpoints = not implemented
full graph runtime loader = not implemented
graph DB materialization = not implemented
Streamlit graph UI = not implemented
GraphRAG = not implemented
/search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, and publication state = unchanged
```


## Citation Graph Traversal API Checkpoint v0.3

Status: **accepted docs-only local-inspection checkpoint**

This checkpoint freezes the current narrow citation/reference graph API block
after the implemented top-referenced-papers and top-external-references
diagnostic endpoints. It is a docs/regression-hardening checkpoint, not a new
endpoint slice and not a graph-runtime promotion.

Checkpointed routes:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

Checkpointed behavior:

```text
status endpoint = compatibility/status surface
outgoing references endpoint = resolved paper references + unresolved external_reference evidence
incoming citations endpoint = resolved internal paper_references_paper edges only
external-reference papers endpoint = papers referencing unresolved external_reference evidence
source-families endpoint = reference-evidence-only diagnostics, not source coverage
top-referenced-papers endpoint = resolved internal incoming reference-count diagnostics only
top-external-references endpoint = unresolved external-reference referencing-paper-count diagnostics only
response envelope = graph/query/items/page/caveats
disabled feature flag = fail closed with graph_runtime_not_enabled
unknown canonical_id = canonical_id_not_found
unknown external reference = external_reference_not_found
limit above max = graph_result_limit_exceeded
missing/incompatible graph artifacts = graph_artifacts_* / graph_*_mismatch
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

Checkpoint validation evidence:

```text
test_api_citation_graph_references.py = 27 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py with ML_RADAR_SEARCH_BACKEND=file = 7 passed
manual live API check = green for status, references, citations, external-reference papers, source-families, top-referenced-papers, top-external-references, unknown ids, and limit guards
```

Boundary:

```text
checkpoint is docs/regression-hardening only
no new endpoint
all seven current graph API routes are implemented and checkpointed
full graph runtime loader = not implemented
graph DB materialization = not implemented
Streamlit graph UI = not implemented
GraphRAG = not implemented
no additional traversal/filtering endpoints without a separate accepted design
/search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, and publication state = unchanged
```

## Current non-goals

```text
no source-family papers endpoint
no additional graph traversal/filtering endpoints without a separate accepted design
no full graph runtime loader over production nodes/edges
no graph DB serving layer
no Streamlit graph surface
no GraphRAG
no Qdrant dependency
no public graph publication
no use as reconcile input
```

Implementation files touched by the status, compatibility-probe, fixture-store,
outgoing-references, incoming-citations, external-reference-papers, and source-families endpoint
slices:

```text
services/api/citation_graph_service.py
services/api/citation_graph_store.py
services/api/settings.py
services/api/schemas.py
services/api/app.py
tests/integration/test_api_citation_graph_status.py
tests/integration/test_api_citation_graph_references.py
tests/smoke/test_citation_graph_fixture_store.py
tests/fixtures/citation_graph_v0_1/
```

Recommended validation:

```bat
python -m py_compile services/api/settings.py services/api/schemas.py services/api/citation_graph_service.py services/api/citation_graph_store.py services/api/app.py tests/integration/test_api_citation_graph_references.py tests/integration/test_api_citation_graph_status.py

set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_citation_graph_references.py -q
python -m pytest tests/integration/test_api_citation_graph_status.py -q
python -m pytest tests/smoke/test_citation_graph_fixture_store.py -q
python -m pytest tests/integration/test_api_smoke.py -q
```

## Boundary

```text
read-only local-inspection API only
no graph rebuild
no graph package rebuild
no validation report writes
no canonical truth mutation
no Postgres mutation
no retrieval/Qdrant/ranking behavior change
no Streamlit graph UI
no GraphRAG
no publication
```


# Citation / Reference Graph Fixture Store

## Current implementation status

The project includes an internal fixture-backed citation/reference graph store:

```text
services/api/citation_graph_store.py
tests/fixtures/citation_graph_v0_1/
tests/smoke/test_citation_graph_fixture_store.py
```

This store is a read-only query core for hardening graph traversal semantics.
The outgoing-references endpoint now uses the same store semantics through a
feature-flagged and compatibility-gated route. The store itself remains
read-only and must not mutate graph artifacts or become canonical truth.

Implemented internal methods:

```text
CitationGraphStore.load(...)
graph_summary()
outgoing_references(canonical_id)
incoming_citations(canonical_id)
external_reference_papers(reference_id)
source_family_diagnostics()
top_referenced_papers()
top_external_references()
```

Fixture-backed semantics:

```text
outgoing references may include resolved paper references and unresolved external references
incoming citations include only resolved paper_references_paper edges
external_reference lookup accepts node id, reference key, or normalized value in the store layer
source-family diagnostics are bounded
limit/offset are validated
unknown paper/reference ids return found=false at the store layer
```

Boundary:

```text
fixture store is internal and read-only
fixture store is not canonical truth
fixture store is not a graph DB runtime
fixture store does not mutate graph outputs, reports, packages, or latest pointers
fixture store does not change /search, /health, /runtime, Discovery API, DB, Qdrant, Streamlit, or ranking
fixture store does not implement GraphRAG
fixture store does not publish anything
```

Validation:

```bat
python -m py_compile services/api/citation_graph_store.py tests/smoke/test_citation_graph_fixture_store.py
python -m pytest tests/smoke/test_citation_graph_fixture_store.py -q
python -m pytest tests/integration/test_api_citation_graph_status.py -q
```

Accepted local result:

```text
test_citation_graph_fixture_store.py = 7 passed
test_api_citation_graph_status.py = 6 passed
```

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
POST /discovery/papers/compare
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

## `POST /discovery/papers/compare`

Returns one deterministic batch comparison for two to five unique canonical
papers.

Request:

```json
{
  "canonical_ids": [
    "paper-id-a",
    "paper-id-b"
  ]
}
```

The response preserves request order and composes:

```text
canonical metadata and identifiers
categories / concepts / keywords
source and provenance evidence
Radar scores
trusted artifacts
GitHub / Hugging Face signals
canonical and feature-level citation evidence
optional read-only citation graph evidence
topic-cluster context
exact pairwise semantic similarity from the active dense build
shared / left-only / right-only comparison dimensions
```

Validation:

```text
fewer than 2 IDs -> 422
more than 5 IDs -> 422
duplicate or blank IDs -> 422
unknown canonical ID -> 404 with missing_canonical_ids
```

Optional derived layers are failure-isolated. Missing dense, cluster, artifact
detail or citation graph artifacts are reported through `capabilities` and
`warnings`; canonical metadata comparison remains available.

This endpoint does not use Qdrant, workspace PostgreSQL, a graph database, an
LLM or RAG. It does not persist comparison state or mutate any source layer.

Full contract:

```text
docs/paper_comparison_workspace_v0.1.md
```

Final bounded regression:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.run_paper_comparison_regression
```

Live HTTP merge gate, with the API already running on
`http://127.0.0.1:8000`:

```bat
python -m scripts.validation.check_paper_comparison_live_smoke --strict
```

The live validator resolves five real sample papers from
`GET /discovery/ranking/recent_artifact_ready`, checks deterministic two- and
five-paper responses, validates `422`/`404` boundaries, and confirms general
runtime health before and after comparison calls. It does not require
workspace PostgreSQL or Qdrant.

Generated regression/live-smoke reports are local operational evidence under:

```text
artifacts/reports/validation/paper_comparison_regression_latest.json
artifacts/reports/validation/paper_comparison_live_smoke_latest.json
```

They are not committed and do not become canonical, retrieval, DB, graph or
publication state.

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

## Artifact API filters validation report

DB-backed artifact API filter validation requires a running Postgres serving layer
and DB backend mode:

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m scripts.validation.check_artifact_api_filters --strict
```

The validator exercises the existing Artifact/Documents API surface and writes
JSON/Markdown reports:

```text
artifacts/reports/validation/artifact_api_filters_check_latest.json
artifacts/reports/validation/artifact_api_filters_check_latest.md
artifacts/reports/validation/history/artifact_api_filters_check_<timestamp>.json
artifacts/reports/validation/history/artifact_api_filters_check_<timestamp>.md
```

Covered checks include:

```text
/runtime DB readiness
/artifacts?provider=github
/artifacts?has_github_metadata=true
/artifacts?github_status=found
stars_desc / forks_desc sort modes
min_stars
language
archived=false
pushed_desc / pushed_after
updated_desc / updated_before
invalid pushed/updated date ranges -> 400
/artifacts/{artifact_id}
/artifacts/{artifact_id}/papers
/documents?has_trusted_artifact=true
/documents?artifact_provider=github
/documents/{canonical_id}/artifacts?provider=github
```

Expected current green output:

```text
ok=True
required_failed_count=0
```

The refresh Definition of Done aggregator can require this latest report with:

```bat
python -m scripts.update.check_refresh_definition_of_done ^
  --require-artifacts ^
  --require-github-enrichment ^
  --require-artifact-api-filters
```

Important semantics:

```text
check_refresh_definition_of_done does not run the Artifact API validator itself.
It only reads artifacts/reports/validation/artifact_api_filters_check_latest.json.
Without --require-artifact-api-filters, this report is diagnostic/optional.
With --require-artifact-api-filters, it becomes a required DoD gate.
Generated reports are not committed.
```

## Artifact API filter regression tests

DB-backed artifact API filter tests require a running Postgres serving layer
and DB backend mode:

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m pytest tests/integration/test_api_artifacts_db.py tests/integration/test_api_artifacts_github_filters_db.py tests/integration/test_api_artifacts_github_date_filters_db.py tests/integration/test_api_documents_artifact_filters_db.py tests/integration/test_api_github_enrichment_db.py tests/integration/test_artifact_api_filters_validation.py -q
```

Expected current green baseline:

```text
36 passed
```

---

# Current API safety summary

```text
No public /search behavior change in this checkpoint.
Citation graph status endpoint is implemented.
Citation graph outgoing references endpoint is implemented.
Citation graph incoming citations endpoint is implemented.
Citation graph external-reference, source-family, top-referenced-papers, and top-external-references endpoints are implemented as narrow diagnostics/traversal surfaces.
Citation graph API is disabled by default.
Graph API / Streamlit productization is design-only in this checkpoint.
No full graph runtime loader.
No Qdrant promotion.
No fallback.
No retrieval rebuild.
No ranking formula change.
Artifact API filters validation is report-only.
DoD reads the latest Artifact API filters report only when required.
No generated report commit.
```

The API documentation should remain synchronized with the accepted retrieval,
Qdrant, runtime, ranking, and citation graph traversal checkpoint evidence.


## Citation Graph UI Productization Checkpoint v0.1

This validator-light checkpoint freezes the current product surface:

```text
API routes = 7
traversal/diagnostics routes = 6
Streamlit evidence consumers = 4
API access only = required
direct graph-file access from Streamlit = forbidden
CitationGraphStore import from Streamlit = forbidden
full graph visualization UI = not implemented
full graph runtime subsystem = not implemented
```

No endpoint, response schema, store-query, canonical, retrieval, Postgres,
Qdrant, ranking, graph-output, package, manual-review, or publication behavior is
changed by this checkpoint.


## Citation Graph Store Cache & Reload Regression v0.1

This checkpoint does not add an endpoint. It freezes the existing relationship
between the Citation Graph local-inspection store and `POST /reload`.

```text
citation_graph_store_cache = bounded_by_graph_root
citation_graph_store_cache_maxsize = 2
citation_graph_store_cache_clear_on_reload = implemented
graph_reload_rebuilds_artifacts = false
graph_reload_mutates_artifacts = false
```

Operational semantics:

1. The first traversal request for a configured graph root loads the read-only
   `CitationGraphStore` from local files.
2. Repeated requests for the same root reuse the cached store instance.
3. Replacing files under that root does not affect the already cached instance
   until cache invalidation.
4. A successful `POST /reload` clears the graph-store cache, reloads the main
   API runtime, and reloads Discovery caches.
5. The next graph request reads the current files from the configured root.
6. Reload never rebuilds or writes Citation Graph artifacts.
7. When `enable_reload_endpoint=false`, `POST /reload` returns `404` and does
   not clear the graph-store cache.

This lifecycle does not change the seven-route Citation Graph API contract,
feature-flag defaults, compatibility gates, manual-review state, publication
state, or the meaning of `runtime_loader_implemented=false`.


## Citation Graph Failure Isolation & Error Recovery v0.1

This checkpoint hardens file-loading failure behavior for the six existing
Citation Graph traversal/diagnostics routes.

```text
citation_graph_failure_isolation = implemented
graph_store_oserror_maps_to_graph_artifacts_invalid = true
graph_store_failed_load_cached = false
graph_runtime_failure_affects_general_health = false
graph_runtime_recovery_requires_process_restart = false
```

Error mapping:

```text
missing required graph artifact or race-to-missing file
→ 503 graph_artifacts_not_found

invalid JSON/JSONL, invalid store structure, or graph-store OSError
→ 503 graph_artifacts_invalid
```

The status endpoint continues to return `200` with its diagnostic `error_code`.
Traversal routes return graph-scoped `503` responses. These failures do not
change readiness or behavior of `/health`, `/info`, `/runtime`, `/search`,
Discovery API, DB serving, or Qdrant diagnostics.

`functools.lru_cache` caches successful store objects only. A failed
`CitationGraphStore.load(...)` attempt does not create a cache entry. Once the
files are repaired, a later request can recover without a process restart. A
successfully cached store remains stable until `/reload` clears the cache.

This checkpoint adds no route, query method, schema, graph rebuild, graph-file
write, full graph runtime loader, graph DB, GraphRAG, or publication behavior.


## Citation Graph Live Smoke & Known-Issues Hardening v0.1

This checkpoint adds no API route and changes no response model. It adds an
operator-facing live HTTP validator over the existing local-inspection surface.

```text
citation_graph_live_smoke = implemented_operator_facing_opt_in
citation_graph_live_smoke_dod_gate = not_required
citation_graph_live_smoke_auto_samples = graph_jsonl
citation_graph_known_issues = documented_v0.1
```

The validator requires an already running API process configured with:

```text
ML_RADAR_SEARCH_BACKEND=file
ML_RADAR_CITATION_GRAPH_API_ENABLED=true
```

It calls:

```text
GET /health
GET /info
GET /runtime
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

It also verifies the stable `canonical_id_not_found`,
`external_reference_not_found`, and `graph_result_limit_exceeded` contracts and
confirms that general runtime health remains ready after graph calls. Sample IDs
are selected from the configured graph JSONL rather than hard-coded.

Reports:

```text
artifacts/reports/validation/citation_graph_live_smoke_latest.json
artifacts/reports/validation/citation_graph_live_smoke_latest.md
artifacts/reports/validation/history/citation_graph_live_smoke_<timestamp>.json
artifacts/reports/validation/history/citation_graph_live_smoke_<timestamp>.md
```

The live report is operational evidence and is not a default DoD gate. Current
limitations are documented in `docs/citation_graph_known_issues_v0.1.md`. A green
report does not mean manual review is complete and does not make the graph
publication-ready.
