# Discovery UI / Paper Workspace Ownership v1

## Document status

```text
status: active ownership note
scope: Streamlit Discovery UI, Paper workspace, Artifact Explorer, topic navigation and validation boundaries
canonical truth impact: none
runtime behavior change: none
api behavior change: none
```

This document records how the current Streamlit UI is wired after the Discovery
API, Qdrant runtime visibility, Artifact Explorer, Paper Workspace, Artifact API
filters validation, Artifact Explorer GitHub date filters UI sync, DoD gate,
and discovery regression runner slices.

It is not a product feature and it does not change application behavior. Its
purpose is to make the current UI implementation easier to review, validate and
extend without confusing UI state with canonical truth or API ownership.

---

## 1. Ownership boundary

The Streamlit application is a thin client over FastAPI.

```text
canonical_documents.jsonl = paper-level truth
Postgres = materialized serving layer
retrieval artifacts = derived retrieval layer
Qdrant = optional derived vector-serving implementation
artifact DB = derived evidence/materialization layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin API client
```

The UI must not become a second business-logic layer.

The UI may:

- collect user inputs;
- build API query parameters;
- call FastAPI endpoints;
- render tables, cards, charts and JSON payloads;
- preserve temporary navigation state in `st.session_state`;
- expose operational hints when the current API backend does not support a tab.

The UI must not:

- mutate canonical paper truth;
- recompute ranking, retrieval, clustering or artifact evidence locally;
- silently reinterpret API response schemas;
- hide backend-mode limitations;
- make live external provider calls;
- change Qdrant, retrieval or DB state;
- treat session state as persisted user data.

---

## 2. Relevant files

### UI implementation

```text
services/ui/app.py
```

Primary responsibilities:

```text
API helpers
session state defaults
sidebar status/runtime panel
Discovery ranking tab
Search tab
Experimental Qdrant search block
Paper workspace
Topic clusters tab
Topic map tab
Artifact explorer
shared render helpers
```

### API validation context

```text
scripts/validation/check_discovery_api.py
scripts/validation/check_streamlit_discovery_ui.py
scripts/validation/run_discovery_api_regression.py
scripts/update/check_refresh_definition_of_done.py
```

### Documentation context

```text
docs/api_reference.md
docs/refresh_contract_v1.md
docs/artifact_api_ownership_v1.md
```

`docs/artifact_api_ownership_v1.md` remains the authoritative ownership note for
DB-backed Artifact API semantics. This document owns only how the Streamlit UI
uses that surface.

---

## 3. Top-level UI map

The current app exposes six top-level tabs:

```text
Discovery ranking
Search
Paper workspace
Topic clusters
Topic map
Artifact explorer
```

The tab layout is created in `services/ui/app.py::main`.

High-level purpose:

| UI surface | Primary purpose | Primary API surface | Backend expectation |
|---|---|---|---|
| Discovery ranking | Profile-based radar ranking | `/discovery/ranking/{profile}` | file-first discovery runtime |
| Search | Free-form corpus search | `/search` | file for lexical/dense/hybrid, db for lexical only |
| Experimental Qdrant block | Explicit Qdrant dense smoke | `/experimental/search/qdrant` | file runtime + Qdrant collection |
| Paper workspace | Paper-centric inspection hub | `/discovery/papers/*`, `/artifacts/*` | mixed: discovery file-first, artifact detail DB-backed |
| Topic clusters | Cluster list/detail navigation | `/discovery/clusters/*` | file-first discovery runtime |
| Topic map | 2D topic projection navigation | `/discovery/clusters/map` | file-first discovery runtime |
| Artifact explorer | DB-backed artifact evidence browser | `/artifacts`, `/artifacts/{id}`, `/artifacts/{id}/papers` | DB backend |

---

## 4. API helper ownership

The UI uses small wrapper functions around `requests` and `st.cache_data`.

Core helpers:

```text
api_get
api_post
fetch_health
fetch_info
fetch_runtime
trigger_reload
clear_api_caches
```

Search and Discovery helpers:

```text
fetch_search
fetch_qdrant_experimental_search
fetch_profiles
fetch_ranking
fetch_paper_detail
fetch_similar_papers
fetch_paper_topic_cluster
fetch_topic_clusters
fetch_topic_cluster_map
fetch_topic_cluster_detail
```

Artifact helpers:

```text
fetch_artifacts
fetch_artifact_detail
fetch_artifact_linked_papers
```

Rules:

```text
UI helpers should remain transport/render helpers.
Endpoint semantics belong to FastAPI and service/DB layers.
Request failures should be shown to the user without fabricating fallback data.
Cache clearing should happen through clear_api_caches() / sidebar Refresh / Reload.
```

---

## 5. Session-state model

The UI uses `st.session_state` as temporary local navigation state.

Major state groups:

```text
connection/runtime:
  api_base_url

Discovery ranking:
  profile_name
  top_k
  query_title
  source_family
  min_year / max_year
  boolean artifact/source filters
  sort_by / descending
  ranking_payload
  selected_canonical_id

Search:
  search_query
  search_mode
  search_top_k
  search_rank
  search filters
  search_payload

Experimental Qdrant search:
  qdrant_search_query
  qdrant_search_top_k
  qdrant_search_payload

Paper workspace:
  selected_paper_canonical_id
  selected_paper_detail_payload
  selected_paper_similar_payload
  selected_paper_cluster_payload
  selected_paper_selected_artifact_id
  selected_paper_artifact_detail_payload
  selected_paper_artifact_linked_papers_payload

Topic clusters/map:
  cluster_payload
  selected_cluster_id
  cluster_detail_* filters
  topic_map_payload
  topic_map_selected_cluster_id

Artifact explorer:
  artifact_payload
  artifact filters
  selected_artifact_id
  artifact_detail_payload
  artifact_linked_papers_payload
```

Important boundaries:

```text
Session state is not persistence.
Session state is not feedback storage.
Session state is not user personalization.
Session state should not replace API/backend state.
```

---

## 6. Paper navigation model

The paper navigation model is intentionally paper-centric.

Primary selected paper key:

```text
selected_paper_canonical_id
```

Selection helpers:

```text
select_paper
select_paper_from_ui
render_open_paper_workspace_button
clear_selected_paper
reset_selected_paper_payloads
reset_selected_paper_artifact_navigation
```

Papers can be opened into Paper workspace from:

```text
Discovery ranking result cards
Search result cards
Experimental Qdrant result cards
Similar papers
Topic cluster papers
Topic map cluster detail papers
Artifact linked papers
Manual canonical_id input
```

When the selected paper changes, paper-specific payloads must be reset so that
old detail/similar/cluster/artifact payloads are not accidentally shown for the
new paper.

---

## 7. Discovery ranking tab

UI owner:

```text
services/ui/app.py::render_sidebar
services/ui/app.py::build_ranking_params
services/ui/app.py::render_ranking
services/ui/app.py::render_result_card
```

API endpoint:

```text
GET /discovery/ranking/{profile_name}
```

Current UI controls:

```text
profile_name
top_k
query_title
source_family
min_year / max_year
has_code / has_dataset / has_model / has_demo
has_github / has_hf / has_acl / has_doi
sort_by
descending
```

Rendering responsibilities:

```text
show effective profile and filters
show result table
show result cards
show radar/source/implementation/citation/recency metrics
provide navigation into Paper workspace
show raw ranking JSON for inspection
```

Business logic boundary:

```text
Profile definitions, scoring and filtering are API-owned.
The UI only sends overrides and renders the returned payload.
```

---

## 8. Search tab

UI owner:

```text
services/ui/app.py::render_search_tab
services/ui/app.py::build_search_params
services/ui/app.py::render_search_results
```

API endpoint:

```text
GET /search
```

Current UI controls:

```text
query
mode = lexical | dense | hybrid
top_k
rank
sort_by = relevance | year_desc | year_asc
offset
open_access
has_code_link
year_from / year_to
category
source
publication_type
venue
```

Backend boundary:

```text
file backend supports lexical / dense / hybrid
DB backend supports lexical only
```

The UI must keep that distinction visible. If the user selects dense/hybrid
against DB backend, the API should reject the request and the UI should show the
error instead of emulating retrieval locally.

Legacy artifact boundary:

```text
has_code_link is a legacy canonical/source-layer signal
trusted artifact filters live in DB-backed document/artifact APIs
```

---

## 9. Experimental Qdrant UI block

UI owner:

```text
services/ui/app.py::render_qdrant_experimental_search_block
services/ui/app.py::build_qdrant_experimental_search_params
services/ui/app.py::render_qdrant_search_results
services/ui/app.py::render_qdrant_runtime_status
```

API endpoints:

```text
GET /runtime
GET /experimental/search/qdrant
```

UI semantics:

```text
Qdrant block is explicitly experimental.
It does not change /search.
It does not imply Qdrant is production dense backend.
It does not apply fallback.
It depends on file runtime and a populated Qdrant collection.
```

Sidebar runtime panel should show Qdrant as optional diagnostics:

```text
Qdrant: OK / unavailable
collection
points / expected corpus count
points_match_corpus
vector size
distance
diagnostic error expander
runtime details expander
```

---

## 10. Paper workspace

UI owner:

```text
services/ui/app.py::render_paper_workspace
services/ui/app.py::render_paper_detail
services/ui/app.py::render_similar_papers_payload
services/ui/app.py::render_paper_topic_cluster_payload
services/ui/app.py::render_selected_paper_artifacts
```

Primary API endpoints:

```text
GET /discovery/papers/{canonical_id}
GET /discovery/papers/{canonical_id}/similar
GET /discovery/papers/{canonical_id}/cluster
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/papers
```

Workspace tabs:

```text
Selected paper detail
Selected paper similar papers
Selected paper topic cluster
Selected paper artifacts
```

Paper detail subtabs:

```text
Overview
Artifacts
Links
Source evidence
Raw detail
```

Paper workspace is the current UI bridge between paper-centric Discovery API
and artifact evidence. The artifact rows shown in paper detail come from the
paper detail payload. Opening an artifact detail or linked-papers list uses the
DB-backed Artifact API.

Important boundary:

```text
Paper workspace can navigate between paper and artifact surfaces.
It must not merge artifact metadata back into canonical paper truth.
```

---

## 11. Selected paper artifacts

UI owner:

```text
services/ui/app.py::extract_artifact_rows
services/ui/app.py::render_selected_paper_artifacts
services/ui/app.py::build_selected_paper_artifact_linked_papers_params
services/ui/app.py::render_artifact_detail_panel
services/ui/app.py::render_artifact_linked_papers
```

Flow:

```text
Load selected paper detail
→ extract artifact rows from paper detail payload
→ select artifact_id
→ optionally load artifact detail
→ optionally load other papers linked to this artifact
→ optionally open those papers in Paper workspace
```

Current linked-paper controls:

```text
limit
offset
relation_type
min_confidence
sort_by = confidence_desc | year_desc | title_asc
```

This creates a paper ↔ artifact ↔ paper navigation loop while keeping all
artifact semantics API/DB-owned.

---

## 12. Topic clusters tab

UI owner:

```text
services/ui/app.py::render_topic_clusters
services/ui/app.py::render_topic_cluster_detail
services/ui/app.py::build_cluster_detail_params
```

API endpoints:

```text
GET /discovery/clusters
GET /discovery/clusters/{cluster_id}
GET /discovery/papers/{canonical_id}/cluster
```

Current cluster list sort modes:

```text
size_desc
cluster_id_asc
mean_radar_desc
artifact_ready_desc
```

Current cluster paper sort modes:

```text
rank
similarity_desc
radar_score
implementation_readiness_score
citation_signal_score
year_desc
```

Current cluster detail filters:

```text
min_year / max_year
has_code / has_dataset / has_model / has_demo
has_github / has_hf / has_acl / has_doi
min_radar_score
min_implementation_readiness_score
min_citation_signal_score
```

Boundary:

```text
The UI calls precomputed cluster artifacts through the API.
The UI does not run clustering locally.
Cluster labels are heuristic navigation aids, not curated taxonomy.
```

---

## 13. Topic map tab

UI owner:

```text
services/ui/app.py::render_topic_map
services/ui/app.py::render_topic_map_metrics
services/ui/app.py::topic_map_point_row
services/ui/app.py::render_topic_cluster_detail
```

API endpoint:

```text
GET /discovery/clusters/map
```

Current controls:

```text
include_papers
max_points
selected mapped cluster
mapped cluster paper sort_by
```

Rendering:

```text
Plotly scatter if available
Streamlit scatter fallback
centroid table / points table
cluster detail from selected centroid
```

Boundary:

```text
The topic map reads existing projection artifacts.
The UI does not compute UMAP/PCA at request time.
```

---

## 14. Artifact Explorer

UI owner:

```text
services/ui/app.py::render_artifact_explorer
services/ui/app.py::build_artifact_params
services/ui/app.py::artifact_row_to_table
services/ui/app.py::render_artifact_card
services/ui/app.py::render_artifact_detail_panel
services/ui/app.py::render_artifact_linked_papers
```

API endpoints:

```text
GET /artifacts
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/papers
```

Current UI filters:

```text
limit
offset
provider
artifact_type
relation_type
owner
min_confidence
min_stars
max_stars
language
license
has_paper_links
archived
has_github_metadata
github_status
pushed_after
pushed_before
updated_after
updated_before
sort_by
```

GitHub date/freshness filters are UI pass-through controls:

```text
pushed_after / pushed_before -> Artifact API pushed_at filtering over metadata.github.pushed_at
updated_after / updated_before -> Artifact API updated_at filtering over materialized artifact_entities.updated_at
```

The UI does not parse, normalize or validate these date strings locally.
Recommended input format is ISO-8601, for example `2024-01-01T00:00:00Z`.
Date format and invalid range errors are API-owned and should be displayed by the
UI through normal request error handling.

Current UI sort modes:

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

Current linked-paper controls:

```text
limit
offset
relation_type
min_confidence
sort_by = confidence_desc | year_desc | title_asc
```

Backend boundary:

```text
Artifact Explorer is DB-backed.
It requires API startup with ML_RADAR_SEARCH_BACKEND=db and Postgres available.
```

Artifact boundary:

```text
Artifact Explorer inspects materialized artifact evidence.
It does not define canonical paper identity.
It does not define paper ranking semantics.
```

---

## 15. Current UI/API drift candidates and polish backlog

### 15.1 Resolved: Artifact GitHub date filters are exposed in UI

The `Artifact Explorer GitHub Date Filters UI v1` slice closes the previous
UI/API drift where the Artifact API already supported GitHub date filters and
sort modes, but Streamlit did not expose them.

The Artifact Explorer now exposes these `GET /artifacts` parameters:

```text
pushed_after
pushed_before
updated_after
updated_before
```

The Artifact Explorer now also exposes these sort modes:

```text
pushed_desc
updated_desc
```

Implementation ownership:

```text
services/ui/app.py
  ARTIFACT_SORT_OPTIONS includes pushed_desc / updated_desc
  init_ui_state() defines artifact_pushed_after / artifact_pushed_before
  init_ui_state() defines artifact_updated_after / artifact_updated_before
  render_artifact_explorer() exposes four text inputs
  build_artifact_params() forwards non-empty date strings to GET /artifacts

scripts/validation/check_streamlit_discovery_ui.py
  ARTIFACT_EXPLORER_UI_SNIPPETS includes the new sort modes, state keys and API params
```

Semantics remain API-owned:

```text
pushed_* filters target metadata.github.pushed_at
updated_* filters target materialized artifact_entities.updated_at
UI does not parse or normalize dates locally
UI shows API validation errors through normal request error handling
```

This was intentionally a UI/API sync only. It did not change:

```text
Artifact API behavior
DB schema
canonical truth
retrieval artifacts
Qdrant behavior
ranking behavior
artifact enrichment fetchers
live GitHub dependency
```

### 15.2 Artifact freshness display can be improved later

The Artifact API can return GitHub metadata. The UI currently shows core fields
such as stars, forks, language, license and status. A later UI polish slice may
surface pushed/updated timestamps in artifact tables/cards/detail panels, but
that should stay separate from the filter-control slice.

### 15.3 Backend-mode guidance can be made more explicit later

The UI spans file-first Discovery/Qdrant surfaces and DB-backed Artifact API
surfaces. The sidebar shows backend mode, and Artifact Explorer shows a DB
backend hint on failure. A later UX slice may add stronger per-tab backend
badges or preflight warnings, but this should not change API behavior.

---

## 16. Validation ownership

### Static Streamlit UI validator

Validator:

```text
scripts/validation/check_streamlit_discovery_ui.py
```

Default command:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Default validator properties:

```text
checks app path exists
runs py_compile on services/ui/app.py
checks streamlit and requests imports
checks required UI snippets
checks discovery endpoint strings
checks search tab snippets
checks Qdrant experimental UI snippets
checks Qdrant runtime status snippets
checks topic cluster/map snippets
checks cluster detail filter snippets
checks Artifact Explorer snippets, including GitHub date filter controls
checks artifact-linked paper navigation snippets
checks Paper workspace snippets
checks Paper workspace artifact snippets
checks no deprecated use_container_width
checks legacy search endpoint absence
writes latest/history UI quality reports
```

Report paths:

```text
artifacts/reports/ui/streamlit_discovery_ui_quality_latest.json
artifacts/reports/ui/streamlit_discovery_ui_quality_latest.md
artifacts/reports/ui/history/streamlit_discovery_ui_quality_<timestamp>.json
artifacts/reports/ui/history/streamlit_discovery_ui_quality_<timestamp>.md
```

### Optional live UI/API validator path

Command:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict --check-api
```

This checks live API reachability and selected endpoint behavior. Use it only
when the relevant API runtime is intentionally running.

### Discovery API validator

Validator:

```text
scripts/validation/check_discovery_api.py
```

Default command:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.check_discovery_api --strict
```

Primary coverage:

```text
/discovery/profiles
/discovery/ranking/{profile}
ranking overrides
/discovery/clusters
/discovery/clusters/map
/discovery/clusters/{cluster_id}
/discovery/papers/{canonical_id}
/discovery/papers/{canonical_id}/similar
/discovery/papers/{canonical_id}/cluster
```

DB-mode artifact smoke is available when the validator is run with DB backend.

---

## 17. Regression and DoD integration

Discovery regression runner:

```bat
python -m scripts.validation.run_discovery_api_regression --skip-similar-rebuild
```

Artifact API filters + DoD variant:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-artifact-api-filters ^
  --include-dod
```

Streamlit UI gate in strict DoD:

```bat
python -m scripts.update.check_refresh_definition_of_done ^
  --require-streamlit-discovery-ui
```

Full current strict DoD may include:

```bat
python -m scripts.update.check_refresh_definition_of_done ^
  --require-known-issues ^
  --require-artifacts ^
  --require-artifact-api-filters ^
  --require-github-enrichment ^
  --require-huggingface-enrichment ^
  --require-paper-features ^
  --require-similar-papers ^
  --require-discovery-api ^
  --require-topic-clusters ^
  --require-topic-projection ^
  --require-streamlit-discovery-ui ^
  --require-golden-queries
```

Expected green state:

```text
streamlit_discovery_ui_quality_ok = true
streamlit_discovery_ui_required_failed_count_zero = true
dod_passed = true
required_failed_count = 0
```

---

## 18. Standard local validation commands

Static UI check:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Discovery API check:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.check_discovery_api --strict
```

Artifact API filters check, when Artifact Explorer behavior is in scope:

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m scripts.validation.check_artifact_api_filters --strict
```

For the Artifact Explorer GitHub date filters UI sync, this check should cover
`pushed_desc`, `updated_desc`, date filter pass-through behavior, and invalid
pushed/updated range rejection at the API layer.

Discovery regression with Artifact API filters report + DoD:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-artifact-api-filters ^
  --include-dod
```

---

## 19. Safe extension points

Safe UI-only extensions:

```text
add controls for already-supported API query parameters
add table/card columns for already-returned response fields
add per-tab help text and backend-mode hints
add static validator snippets for new controls
add docs sync for UI ownership
```

Changes requiring API/validation review:

```text
new API query parameters
new response fields that UI depends on as required
new endpoint calls from UI
new live API validation requirements
changes to paper/artifact navigation semantics
changes to backend-mode expectations
changes to session-state key names used by validators
```

Changes that should not be done inside a UI-only slice:

```text
ranking formula changes
retrieval behavior changes
Qdrant promotion/default changes
canonical schema changes
artifact DB schema changes
external provider calls from Streamlit
persistent user personalization / bookmarks / feedback storage
```

---

## 20. Operational note

This ownership document should be updated when one of the following changes:

```text
new top-level UI tab
new Paper workspace subtab
new Streamlit API endpoint call
new Artifact Explorer filter/sort control
new topic cluster/map control
new Qdrant UI/runtime status behavior
new Streamlit validation snippet group
new DoD gate related to Streamlit UI
```

It does not need to change for unrelated canonical refreshes, retrieval rebuilds,
artifact enrichment runs, Qdrant benchmark runs, dataset export slices, or API
changes that are not exposed through Streamlit UI.
