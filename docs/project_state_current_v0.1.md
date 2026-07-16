# ML Research Radar — Current State Checkpoint v0.1

## Document status

```text
document = consolidated current-state checkpoint
checkpoint_version = v0.1
checkpoint_date = 2026-07-08
scope = documentation / transfer / design-hardening baseline
canonical_truth = false
may_be_used_as_reconcile_input = false
mutates_canonical_documents = false
mutates_retrieval_artifacts = false
mutates_qdrant = false
mutates_postgres = false
mutates_api = false
mutates_ui = false
mutates_ranking = false
publishes_dataset = false
creates_runtime_graph = false
```

This document is a compact transfer and orientation checkpoint for **ML Research Radar**.
It records the current validated project model, accepted layer boundaries, current counters,
completed work, current API status surface, and recommended next slices.

It is not a new source of truth. The paper-level source of truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

All retrieval artifacts, Postgres tables, artifact evidence tables, graph outputs,
reports, API responses, UI state, and packages are derived/rebuildable layers.

---

## 1. Project identity

ML Research Radar is a paper-centric research-discovery platform for ML/AI research.

It is designed to:

- collect partially overlapping paper observations from multiple sources;
- reconcile them into canonical paper-level entities;
- preserve source provenance;
- build lexical/dense/hybrid retrieval artifacts;
- materialize optional Postgres serving tables;
- extract and validate implementation/evidence artifacts;
- enrich artifact metadata from providers such as GitHub and Hugging Face;
- build paper-level features, ranking profiles, paper detail views, similar-paper views, and topic-cluster views;
- expose a Discovery API and Streamlit UI over derived layers;
- build local derived graph lines for review/evidence analysis;
- protect every promotion/publication/runtime step through validation, reports, and manual-review gates.

It is not:

- an arXiv-only parser;
- a vector database wrapper;
- a RAG demo;
- a graph database project by default;
- a public dataset publication pipeline by default;
- a runtime graph API by default;
- a collection of unrelated scripts.

---

## 2. Non-negotiable architecture boundaries

### 2.1 Paper truth

```text
canonical_documents.jsonl = paper-level source of truth
```

Everything below is derived and rebuildable:

- retrieval artifacts;
- Qdrant collections;
- Postgres serving tables;
- artifact entities / observations / trusted links;
- provider metadata snapshots;
- paper features;
- ranking outputs;
- similar-paper outputs;
- topic clusters and projections;
- API responses;
- Streamlit UI state;
- graph outputs;
- graph packages;
- validation reports.

No derived layer may redefine paper identity or mutate canonical paper truth.

### 2.2 Identity separation

```text
source_doc_id / doc_id      = source-level observation identity
canonical_id                = reconciled paper-level identity
artifact_id                 = normalized external artifact identity
dense_index / Qdrant point  = retrieval-serving mapping in one build
graph node id               = typed derived graph identity
```

Paper identity priority:

```text
DOI
→ external DOI
→ arXiv ID
→ external arXiv ID
→ normalized title + year fallback
```

### 2.3 Provenance semantics

`canonical_documents.sources` is row-level provenance.

`source_count` is the number of source/provenance rows.

`unique_source_count` is the number of unique source families.

`source_ids` is a merged identifier map and must not be treated as strict provenance by itself.

Graph source-family evidence must derive from canonical provenance rows, not from `source_ids` alone.

---

## 3. Accepted current baseline

### 3.1 Canonical and retrieval baseline

```text
canonical_doc_count = 60,954
canonical_multisource_docs = 9,192
doi_count = 10,183
arxiv_backbone = 60,000
acl_family_docs = 957
acl_only_docs = 954
acl_enriched_existing_docs = 3
retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]
topic_clusters_count = 80
topic_assignments_count = 60,954
```

### 3.2 Artifact evidence baseline

Current accepted artifact-layer orientation:

```text
artifact_entities_db_count ≈ 7,333
artifact_entities_file_count ≈ 7,336
artifact_observations_db_count ≈ 38,246
paper_artifact_links_db_count ≈ 7,430
github_found_count ≈ 5,339
huggingface_found_count ≈ 77
```

Older slice-local numbers inside historical docs must not override the latest accepted checkpoint.
When in doubt, prefer the latest validation/export/read reports over historical narrative docs.

### 3.3 Qdrant baseline

```text
collection = ml_radar_dense_benchmark_v1
points_count = 60,954
vector_size = 384
distance = Cosine
selected profile = ef_256
transport = gRPC
public_qdrant_promotion = not performed
fallback = absent
```

Public `/search` dense/hybrid behavior remains file-backed.
Qdrant remains optional/experimental and is exposed through the experimental path only.

---

## 4. Implemented layers

## 4.1 Canonical corpus and merge policy

Completed:

- source normalization;
- source-level identity separation;
- paper-level reconciliation;
- conservative identity resolution;
- provenance-preserving merge;
- DOI/arXiv/title+year identity policy;
- arXiv backbone;
- OpenAlex, Semantic Scholar, Crossref, ACL alignment;
- canonical contract validation;
- controlled candidate promotion.

Important boundary:

```text
artifact/provider metadata never becomes paper truth
```

## 4.2 Retrieval layer

Implemented:

- compact BM25 lexical index;
- dense embeddings with `sentence-transformers/all-MiniLM-L6-v2`;
- lexical/dense/hybrid retrieval;
- backend-neutral hybrid score merge;
- retrieval artifacts save/load;
- retrieval manifest;
- retrieval artifact smoke tests;
- file dense exact backend;
- Qdrant dense backend abstraction;
- Qdrant parity helpers.

Reference dense semantics:

```text
scores = stored_embeddings @ normalized_float32_query
order = np.argsort(scores)[::-1]
```

Stored embeddings are used as persisted and are not silently re-normalized by parity/reference helpers.

## 4.3 API runtime layer

Implemented backend modes:

```text
file
db
```

File backend:

- public `/search?mode=lexical|dense|hybrid`;
- retrieval artifacts and embedding model;
- optional experimental Qdrant endpoint;
- Qdrant-independent health.

DB backend:

- document browse/filter;
- DB lexical search v1;
- artifact endpoints;
- document-artifact filters.

Intentional DB v1 limitation:

```text
DB backend supports lexical search only.
DB dense/hybrid search is intentionally rejected.
```

Qdrant failure contract:

```text
DenseBackendRequestError       -> 400 dense_backend_bad_request
DenseBackendUnavailableError   -> 503 dense_backend_unavailable
DenseBackendCompatibilityError -> 503 dense_backend_incompatible
DenseBackendResultError        -> 503 dense_backend_invalid_result
```

Qdrant failures must not make file runtime unhealthy.


Citation/reference graph API surface:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

Current graph API semantics:

```text
status_endpoint = implemented
outgoing_references_endpoint = implemented
disabled_by_default = true
feature_flag = ML_RADAR_CITATION_GRAPH_API_ENABLED
compatibility_probe = implemented
fixture_store = implemented_internal
incoming_citations_endpoint = implemented
external_reference_papers_endpoint = implemented
source_family_endpoint = implemented
top_referenced_papers_endpoint = implemented
top_external_references_endpoint = implemented
full_graph_runtime_loader = not implemented
graph_db_materialization = not implemented
streamlit_graph_status_panel = implemented
streamlit_graph_paper_workspace_panel = implemented
streamlit_graph_diagnostics_ui = implemented
streamlit_graph_external_reference_lookup_ui = implemented
graphrag = not implemented
publication_ready = false
manual_review_required = true
```

Boundary:

```text
The status endpoint is an API safety/status/compatibility surface.
When enabled, it may read local graph manifests/reports for compatibility status.
The outgoing references, incoming citations, external-reference-papers, source-families, top-referenced-papers, and top-external-references endpoints are the implemented narrow local-inspection endpoints.
It is read-only, feature-flagged, compatibility-gated, and backed by CitationGraphStore.
It may return resolved paper references and unresolved external_reference evidence.
Incoming citations are resolved internal links only; external-reference-papers is implemented as reverse lookup over unresolved external references; source-family diagnostics are implemented as reference-evidence-only summaries; top-referenced-papers is implemented as resolved-internal-reference-count diagnostics; top-external-references is implemented as unresolved-external-reference-count diagnostics.
A full graph runtime loader is not implemented.
The graph API does not change /search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, or publication state.
```

Internal citation/reference graph fixture store:

```text
services/api/citation_graph_store.py = implemented
fixture graph = tests/fixtures/citation_graph_v0_1/
public outgoing references route = implemented
public incoming citations route = implemented
public external-reference papers route = implemented
public source-families route = implemented
public top-referenced-papers route = implemented
public top-external-references route = implemented
full graph runtime loader = not implemented
```

Current store/API semantics:

```text
outgoing references include resolved and external references
incoming citations include only resolved paper_references_paper edges at the store layer
external_reference lookup returns referencing papers at the store layer
source-family diagnostics and top-reference summaries are bounded at the store layer
unknown ids return found=false at the store layer
unknown canonical_id returns canonical_id_not_found at the API layer
```

Boundary:

```text
fixture store is internal and read-only
outgoing references API is a narrow local-inspection traversal surface
incoming citations API is a narrow local-inspection traversal surface over resolved internal references only
external-reference papers API is a narrow local-inspection traversal surface over unresolved external_reference evidence
source-families API is a narrow local-inspection diagnostics surface over source-family reference evidence
store/API do not mutate graph artifacts, reports, packages, or latest pointers
store/API do not change /search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, or publication state
```

Latest graph API validation:

```text
test_api_citation_graph_references.py = 27 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py = 7 passed
manual live top-referenced-papers check = green for top-referenced-papers success path and limit guard, with resolved_internal_reference_count_only / not_global_citation_metric / not_publication_grade_ranking caveats
manual live top-external-references check = green for top-external-references success path and limit guard, with external_reference_is_unresolved / not_publication_grade_reference_entity / not_global_citation_metric / not_publication_grade_ranking caveats
```

## 4.4 Artifact evidence plane

Implemented artifact model:

```text
artifact_entities      = normalized external artifact identities
artifact_observations  = broad evidence rows
paper_artifact_links   = trusted serving links
```

Trusted link invariant:

```text
unique key = canonical_id + artifact_id + relation_type
```

Evidence multiplicity is preserved in metadata, not duplicated as multiple trusted links.

Shared trusted-link policy:

```text
policy_source = radar_core.artifacts.trusted_links
policy_version = artifact_trusted_links_policy_v1
```

Provider-specific trusted artifact types are trusted at `confidence >= 0.65`.
Generic links are trusted only when confidence is high, the source field is trusted, and the domain is not bibliographic/resolver/technical noise.

Legacy source-layer flag and trusted artifact evidence must remain separate:

```text
has_code_link ≠ has_trusted_code_artifact
```

## 4.5 GitHub and Hugging Face enrichment

GitHub/Hugging Face enrichment is artifact metadata enrichment, not paper-source enrichment.

GitHub date-filter semantics:

```text
pushed_*  -> metadata.github.pushed_at
updated_* -> artifact_entities.updated_at / materialized repository updated_at
```

Rows without the required provider metadata/date do not match provider-specific date filters.

## 4.6 Postgres serving layer

Postgres is a serving/materialization layer, not canonical truth.

Paper tables include:

```text
source_documents
canonical_documents
canonical_source_links
document_references
```

Artifact tables include:

```text
artifact_entities
artifact_observations
paper_artifact_links
```

Operational note:

```text
paper export with --replace may cascade to dependent artifact links;
full refresh should run artifact export after paper export.
```

## 4.7 Discovery layer

Implemented:

- paper features;
- ranking profiles;
- feature ranking filters/sorts;
- paper detail workspace;
- similar papers semantic and radar-adjusted modes;
- topic clusters;
- topic projection/map;
- Discovery API;
- Streamlit Discovery UI.

Known profile orientation:

```text
default_profile = recent_artifact_ready
required profiles include:
  - huggingface_ready
  - recent_artifact_ready
  - acl_radar
```

Discovery API is a product layer over derived features/evidence, not a source of truth.

---

## 5. Graph lines

There are two separate local derived graph lines.

Both are:

- local;
- derived;
- rebuildable;
- evidence/review artifacts;
- not canonical truth;
- not reconcile inputs;
- not DB replacements;
- not API/runtime features by default;
- not GraphRAG;
- not publication-ready without manual review.

## 5.1 Paper–Artifact Graph v0.1

Purpose:

```text
paper -> trusted artifact evidence graph
```

Node types:

```text
paper
artifact
provider
source_family
topic_cluster
```

Edge types:

```text
paper_has_artifact
artifact_from_provider
paper_observed_in_source_family
paper_assigned_to_topic_cluster
```

Accepted counters:

```text
nodes_count = 68,385
edges_count = 163,757
paper nodes = 60,954
artifact nodes = 7,336
provider nodes = 10
source_family nodes = 5
topic_cluster nodes = 80
paper_has_artifact edges = 7,430
artifact_from_provider edges = 7,336
paper_observed_in_source_family edges = 88,037
paper_assigned_to_topic_cluster edges = 60,954
trusted_links_used_count = 7,430
topic_edges_count = 60,954
```

Critical rule:

```text
paper_has_artifact edges derive from trusted paper_artifact_links semantics,
not directly from broad artifact_observations.
```

Completed line:

```text
contract
→ builder
→ output validator
→ inspection / QA
→ query CLI
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
→ analytics report
```

Manual review status:

```text
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

## 5.2 Citation / Reference Graph v0.1

Purpose:

```text
paper -> paper / paper -> external reference evidence graph
```

Input scope:

```text
referenced_dois
referenced_ids
referenced_arxiv_ids
```

Non-inputs:

```text
full text
PDF
HTML
raw bibliography strings
in-text citation context
```

Node types:

```text
paper
external_reference
source_family
```

Edge types:

```text
paper_references_paper
paper_references_external
paper_has_reference_source_family
```

Accepted counters:

```text
nodes_count = 529,295
edges_count = 745,516
paper nodes = 60,954
external_reference nodes = 468,336
source_family nodes = 5
paper_references_paper edges = 6,165
paper_references_external edges = 703,234
paper_has_reference_source_family edges = 36,117
resolved_reference_edges = 6,165
unresolved_reference_edges = 703,234
reference_resolution_ratio = 0.00869
```

Normalization rule:

```text
OpenAlex URL / ID references from referenced_ids -> reference_type = openalex_id
DOI references -> reference_type = doi only when DOI syntax matches
```

Completed line:

```text
contract
→ builder
→ output validator
→ inspection / QA
→ query CLI
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
→ analytics report
```

Manual review status:

```text
manual_review_required = true
manual_review_complete = true
approval_state = approved
category_status_counts = {passed: 18}
publication_ready = false
publication_block_reason = publication_action_not_in_scope
```

Manual-review validator semantics:

```text
pending categories block publication;
pending categories do not fail the validator;
summary.ok=true means structural/safety gate is valid,
not that human review is complete.
```

---

## 6. Regression, reports, and DoD

The project uses validation/report gates instead of implicit trust.

Refresh DoD can aggregate:

- canonical summary;
- retrieval manifest/checks;
- DB smoke;
- canonical contract;
- artifact quality/export/read reports;
- artifact API filters;
- GitHub/Hugging Face enrichment;
- paper features;
- similar papers;
- Discovery API;
- topic clusters/projection;
- Streamlit UI;
- golden queries;
- Citation Graph API regression report.

Optional gates remain opt-in unless the active slice requires them. The Citation Graph API regression gate is optional by default and becomes required only with `--require-citation-graph-api-regression`.

Artifact API filters are correctly modeled as an opt-in DB-backed regression gate, not as a mandatory requirement for every refresh.

---

## 7. Current safest development direction

The next work should remain narrow and sequential:

```text
one graph API endpoint at a time
no broad runtime / GraphRAG / graph DB / Qdrant promotion without separate accepted design
```

Recently completed safe slices after this checkpoint baseline:

1. **Graph Review Evidence Pack v0.1**
   - local review/evidence report over both graph lines;
   - no runtime/API/UI/DB/Qdrant/retrieval/ranking changes;
   - no publication.

2. **Citation / Reference Graph API Design v0.1**
   - design-only;
   - safe future query modes, caveats, failure semantics, and boundaries.

3. **Graph API Response Fixture Design v0.1**
   - expected response/error/caveat fixtures before endpoint implementation.

4. **Graph Runtime Stale-Version Compatibility Design v0.1**
   - fail-closed compatibility semantics for stale/unsafe graph outputs.

5. **Citation / Reference Graph API Implementation Plan v0.1**
   - implementation plan only;
   - staged rollout from status to store to one endpoint at a time.

6. **Citation Graph API Disabled Status Endpoint v0.1**
   - `GET /citation-graph/status`;
   - disabled by default;
   - no traversal endpoint yet.

7. **Citation Graph Status Compatibility Probe v0.1**
   - read-only compatibility/status probe through `/citation-graph/status`;
   - no graph runtime loader.

8. **Citation Graph Fixture Store v0.1**
   - internal read-only fixture-backed query core;
   - outgoing/incoming/external/source-family/top-reference semantics covered by fixture tests;
   - no full graph runtime loader.

9. **Citation Graph Outgoing References Endpoint v0.1**
   - first narrow traversal endpoint;
   - `GET /citation-graph/papers/{canonical_id}/references`;
   - disabled by default and compatibility-gated;
   - external-reference lookup, source-family, or top-reference endpoints not implemented.

10. **Citation Graph Incoming Citations Endpoint v0.1**
   - second narrow traversal endpoint;
   - `GET /citation-graph/papers/{canonical_id}/citations`;
   - incoming citations include only resolved internal `paper_references_paper` edges;
   - disabled by default and compatibility-gated.

11. **Citation Graph Incoming Citations Endpoint Docs Sync v0.1**
   - shared docs aligned with the implemented second traversal endpoint;
   - no-full-runtime-loader/no-external-source-top-endpoints boundary preserved.

12. **Citation Graph Traversal API Checkpoint v0.1**
   - docs/regression-hardening checkpoint over `status + references + citations`;
   - no new endpoint;
   - preserve current fail-closed behavior and caveats.

13. **Citation Graph External Reference Papers Endpoint v0.1**
   - third narrow traversal endpoint;
   - `GET /citation-graph/external-references/{reference_id}/papers`;
   - accepts external_reference node id, reference_key, or normalized value;
   - disabled by default and compatibility-gated.

14. **Citation Graph Source Families Endpoint v0.1**
   - fourth narrow diagnostics endpoint;
   - `GET /citation-graph/source-families`;
   - source-family reference-evidence diagnostics only;
   - not a source coverage metric.

15. **Citation Graph Source Families Endpoint Docs Sync v0.1**
   - shared docs aligned with the implemented fourth graph endpoint;
   - no-top-endpoints/no-full-runtime-loader boundary preserved.

16. **Citation Graph Traversal API Checkpoint v0.2**
   - completed docs/regression-hardening checkpoint over `status + references + citations + external-reference papers + source-families`;
   - no new endpoint;
   - preserve fail-closed behavior and caveats.

17. **Citation Graph Top Referenced Papers Endpoint v0.1**
   - fifth narrow diagnostics endpoint;
   - top resolved internal reference counts only;
   - not a global citation metric or publication-grade ranking.

18. **Citation Graph Top External References Endpoint v0.1**
   - sixth narrow diagnostics endpoint;
   - top unresolved external-reference counts only;
   - not a publication-grade reference-entity catalog.

19. **Citation Graph Traversal API Checkpoint v0.3**
   - completed docs/regression-hardening checkpoint over all seven implemented graph routes;
   - no new endpoint;
   - preferred next step after this is regression/DoD hardening.

20. **Citation Graph API Regression Check v0.1**
   - completed static regression validator over the accepted seven-route graph API block;
   - writes `citation_graph_api_regression_latest.json` / `.md` reports;
   - no endpoint, runtime loader, graph output, or publication behavior change.

21. **Citation Graph API Regression DoD Wiring v0.1**
   - completed opt-in DoD gate for the Citation Graph API regression report;
   - `--require-citation-graph-api-regression` makes the gate required;
   - default DoD remains unchanged unless the flag is passed.

22. **Graph API / Streamlit Productization Design v0.1**
   - completed design-only bridge from accepted graph API surfaces to future Streamlit UI slices;
   - confirms that Streamlit remains a thin API client;
   - confirms that Paper–Artifact evidence should use existing Artifact API surfaces before designing a dedicated graph API.

23. **Citation Graph Streamlit Status Panel v0.1**
   - completed first thin Streamlit graph evidence consumer;
   - consumes `/citation-graph/status` only.

24. **Citation Graph Paper Workspace Panel v0.1**
   - completed second thin Streamlit graph evidence consumer;
   - consumes selected-paper `/references` and `/citations` endpoints.

25. **Citation Graph Diagnostics UI v0.1**
   - completed third thin Streamlit graph evidence consumer;
   - consumes source-family and top-reference diagnostics.

26. **Citation Graph External Reference Lookup UI v0.1**
   - completed fourth thin Streamlit graph evidence consumer;
   - URL-quotes `reference_id` before calling the external-reference papers endpoint.

27. **Citation Graph UI Productization Checkpoint v0.1**
   - completed validator-light checkpoint;
   - freezes seven API routes and four Streamlit evidence consumers;
   - synchronized living docs, existing validators, terminology, and stale comments only.

28. **Citation Graph Store Cache & Reload Regression v0.1**
   - completed regression-hardening slice;
   - freezes bounded cache reuse, `/reload` invalidation, disabled-reload behavior, and graph-artifact no-mutation semantics.

29. **Citation Graph Failure Isolation & Error Recovery v0.1**
   - completed regression-hardening slice;
   - freezes graph-scoped missing/invalid/OSError mapping, health independence, cache non-poisoning, and repair/retry recovery semantics.

30. **Citation Graph Live Smoke & Known-Issues Hardening v0.1**
   - completed operator-facing validation/docs slice;
   - adds live HTTP evidence and documents accepted limitations without changing API/runtime behavior.

31. **Citation Graph Manual-Review Evidence Preparation v0.1**
   - current read-only review-support slice;
   - assembles evidence for all 18 existing pending categories without changing approval or publication state.

Recommended next slices:

1. **Manual Citation Graph Review Execution v0.1**
   - human-only follow-up using the prepared evidence; record explicit rationale for any status or approval change.

2. **Paper–Artifact Graph API Design v0.1, only if needed**
   - start only after proving that existing Artifact API surfaces cannot cover a concrete product requirement.

---


## 7.5 Citation Graph Streamlit Status Panel v0.1

Completed first UI code slice:

```text
Citation Graph Streamlit Status Panel v0.1
```

Scope:

```text
Streamlit consumes GET /citation-graph/status only.
The status panel is a thin API client surface.
It renders graph availability, disabled/unavailable states, local safety status, runtime loader state, and manual-review/publication caveats.
```

Boundary:

```text
no references/citations tables yet
no source-family/top-reference diagnostics UI yet
no external-reference lookup UI yet
no graph visualization
no direct graph file reads from Streamlit
no CitationGraphStore import from Streamlit
no NetworkX/Neo4j/GraphRAG
no full graph runtime loader
no graph DB materialization
no API endpoint change
no mutation of canonical truth, graph outputs, reports, packages, retrieval, Qdrant, DB, ranking, or publication state
```

---


## 7.1 Citation Graph Paper Workspace Panel v0.1 boundary

Current UI productization state:

```text
Citation Graph status panel = implemented
Citation Graph Paper workspace evidence panel = implemented
Citation Graph diagnostics UI = implemented
Citation Graph external-reference lookup UI = implemented
```

Paper workspace evidence panel semantics:

```text
selected paper -> outgoing references via /citation-graph/papers/{canonical_id}/references
selected paper -> incoming resolved citations via /citation-graph/papers/{canonical_id}/citations
metadata_reference_fields_only = true
not_a_complete_citation_index = true
manual_review_required = true
publication_ready = false
```

Boundary:

```text
no direct Streamlit reads from graph files
no CitationGraphStore import from Streamlit
no graph visualization
no NetworkX / Neo4j / GraphRAG
no graph DB materialization
no full graph runtime loader
no mutation of canonical truth, retrieval artifacts, Qdrant, Postgres, ranking, graph outputs, reports, packages, or publication state
```

## 8. Explicit non-goals for the immediate next slice

Do not do these without a separate accepted design:

- additional graph traversal endpoints beyond the implemented status/references/citations/external-reference-papers/source-families/top-referenced-papers/top-external-references block in this checkpoint;
- GraphRAG;
- Neo4j/NetworkX runtime;
- full runtime graph loader over production graph artifacts;
- DB materialization of graph as serving truth;
- Qdrant public promotion;
- hidden Qdrant fallback;
- publication/upload;
- replacing canonical truth with graph/artifact/DB metadata;
- changing public `/search` behavior;
- changing ranking formulas silently.

---

## 9. Suggested immediate plan

Current dialogue should close with a design-only productization checkpoint over
how the accepted graph API surfaces will be consumed by Streamlit.

Minimal documentation set:

```text
docs/api_reference.md
docs/roadmap.md
docs/project_state_current_v0.1.md
docs/refresh_contract_v1.md
docs/architecture.md
```

Suggested validation:

```text
git diff --check
python -m scripts.validation.check_citation_graph_api_regression --strict
```

Optional UI static confirmation before the first UI code slice:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Suggested commit message:

```text
docs: design graph api streamlit productization
```


## Citation Graph Traversal API Checkpoint v0.2

Status: **accepted docs-only local-inspection checkpoint**

This checkpoint freezes the current narrow citation/reference graph API surface as
a stable local-inspection block after the source-families endpoint and before any
top-reference endpoint work.

Implemented and checkpointed routes:

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
test_api_citation_graph_references.py = 19 passed
test_api_citation_graph_status.py = 6 passed
test_citation_graph_fixture_store.py = 7 passed
test_api_smoke.py with ML_RADAR_SEARCH_BACKEND=file = 7 passed
manual live API check = green for status, references, citations, external-reference papers, source-families, unknown ids, and limit guards
```

Boundary:

```text
checkpoint is docs/regression-hardening only
external-reference papers endpoint = implemented
source-family endpoint = implemented
top-reference endpoints = not implemented
top-reference endpoints = not implemented
full graph runtime loader = not implemented
graph DB materialization = not implemented
Streamlit graph UI = not implemented
GraphRAG = not implemented
/search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, and publication state = unchanged
```



## Citation Graph External Reference Papers Endpoint v0.1

Status: **implemented narrow local-inspection traversal endpoint**

Implemented route:

```text
GET /citation-graph/external-references/{reference_id}/papers
```

Semantics:

```text
external_reference -> papers that reference it
uses paper_references_external incoming edges
accepts external_reference node id, reference_key, or normalized value
slash-containing DOI values require URL encoding
external references remain unresolved metadata-derived evidence nodes
```

Manual live API check:

```text
GET /citation-graph/external-references/external_reference:1954a09282cc66f2/papers?limit=5&offset=0 -> 200, returned=4, total_estimate=4, caveats include external_reference_is_unresolved and not_publication_grade_reference_entity
GET /citation-graph/external-references/10.1080%2F14786440009463897/papers?limit=5&offset=0 -> 200, returned=4, total_estimate=4, normalized DOI lookup with slash works through URL encoding
GET /citation-graph/external-references/W2083798294/papers?limit=5&offset=0 -> 200, returned=1, OpenAlex normalized value lookup works
GET /citation-graph/external-references/not-a-real-reference/papers?limit=5 -> 404 external_reference_not_found
GET /citation-graph/external-references/external_reference:1954a09282cc66f2/papers?limit=101 -> 400 graph_result_limit_exceeded
```

Boundary:

```text
read-only local-inspection endpoint
feature-flagged and compatibility-gated
source-family endpoint = implemented
no top-reference endpoints
no full graph runtime loader
no graph DB materialization
no Streamlit graph UI
no GraphRAG
no /search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, or publication state change
```


## Citation Graph Source Families Endpoint v0.1

Status: **implemented narrow local-inspection diagnostics endpoint**

Implemented route:

```text
GET /citation-graph/source-families
```

Semantics:

```text
source_family -> reference evidence diagnostics
uses source_family nodes and paper_has_reference_source_family evidence
reports paper_count_with_reference_evidence, reference_edge_count, resolved_edge_count, and external_edge_count
diagnostics are reference-evidence-only and not source coverage metrics
```

Manual live API check:

```text
GET /citation-graph/source-families?limit=5&offset=0 -> 200, returned=5, total_estimate=5, caveats include source_family_reference_evidence_only and not_source_coverage_metric
GET /citation-graph/source-families?limit=101 -> 400 graph_result_limit_exceeded
```

Boundary:

```text
read-only local-inspection endpoint
feature-flagged and compatibility-gated
no top-reference endpoints
no full graph runtime loader
no graph DB materialization
no Streamlit graph UI
no GraphRAG
no /search, Discovery API, DB, Qdrant, ranking, canonical truth, graph output, package output, or publication state change
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


## Graph API / Streamlit Productization Design v0.1

Status: **completed design-only productization checkpoint**

Purpose:

```text
Close the design gap between the accepted Citation Graph API block and future
Streamlit UI consumption, without adding UI code or changing API/runtime behavior.
```

Productization rules:

```text
Streamlit remains a thin API client.
Streamlit consumes graph evidence through FastAPI only.
Streamlit must not read graph JSONL/package files directly.
Streamlit must not instantiate CitationGraphStore directly.
Streamlit must not introduce NetworkX, Neo4j, GraphRAG, or a full graph runtime loader.
Graph evidence must remain labeled as metadata-only, local-inspection evidence.
manual_review_required=true and publication_ready=false must remain visible.
```

Citation Graph UI rollout:

```text
1. Status panel: /citation-graph/status
2. Paper workspace evidence: /citation-graph/papers/{canonical_id}/references and /citations
3. Diagnostics: /citation-graph/source-families, /top-referenced-papers, /top-external-references
4. External reference lookup: /citation-graph/external-references/{reference_id}/papers
```

Paper–Artifact Graph productization rule:

```text
Use existing Artifact API surfaces first:
/artifacts
/artifacts/{artifact_id}
/artifacts/{artifact_id}/papers
/documents/{canonical_id}/artifacts

Do not create a dedicated Paper–Artifact Graph API unless a later design slice
identifies a concrete gap that existing Artifact API endpoints cannot cover.
```

Boundary:

```text
design-only
no Streamlit code change
no API endpoint change
no graph runtime loader
no graph DB materialization
no GraphRAG
no Qdrant promotion
no /search or ranking behavior change
no canonical truth mutation
no graph output/package/report rebuild
no publication
```


## Citation Graph External Reference Lookup UI v0.1

Status: **implemented UI-only local-inspection slice**

```text
Streamlit calls GET /citation-graph/external-references/{reference_id}/papers through FastAPI.
The UI URL-quotes reference_id before inserting it into the endpoint path.
The panel renders referencing-paper evidence rows and raw payloads for manual inspection.
```

Boundary:

```text
no API endpoint changes
no CitationGraphStore changes
no schema changes
no direct Streamlit reads from data/graphs/*
no graph visualization
no NetworkX/Neo4j/GraphRAG
no full graph runtime loader
no graph DB materialization
no canonical/retrieval/Qdrant/Postgres/ranking/publication change
```


## Citation Graph UI Productization Checkpoint v0.1

Status: **current validator-light checkpoint**

Accepted surface:

```text
Citation Graph API routes = 7
Citation Graph traversal/diagnostics routes = 6
streamlit_graph_evidence_panels = implemented
streamlit_graph_status_panel = implemented
streamlit_graph_paper_workspace_panel = implemented
streamlit_graph_diagnostics_ui = implemented
streamlit_graph_external_reference_lookup_ui = implemented
full_graph_runtime_loader = not implemented
full_graph_visualization_ui = not implemented
graph_db_materialization = not implemented
graphrag = not implemented
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

Runtime terminology:

```text
CitationGraphStore = narrow file-backed local-inspection store
full graph runtime subsystem = not implemented
runtime_loader_implemented = false
traversal_endpoints_implemented = false remains the broad full-runtime-surface marker
```

Scope:

```text
living docs synchronization
existing API/UI validator synchronization
status-only comments/docstrings cleanup
no endpoint or response-schema change
no graph rebuild or package rebuild
no canonical/retrieval/Qdrant/Postgres/ranking change
no manual-review approval
no publication
```

The next preferred direction after this checkpoint is review/regression
hardening, not additional graph endpoints or a graph database.


## Citation Graph Store Cache & Reload Regression v0.1

Completed hardening slice:

```text
citation_graph_store_cache = bounded_by_graph_root
citation_graph_store_cache_maxsize = 2
citation_graph_store_cache_clear_on_reload = implemented
graph_reload_rebuilds_artifacts = false
graph_reload_mutates_artifacts = false
reload_disabled_clears_graph_cache = false
```

The implementation already existed at the accepted `82717c8` baseline. This
slice adds explicit regression evidence rather than a new runtime capability.
The graph store remains a process-local, read-only local-inspection cache. A
successful `/reload` invalidates it before the existing API runtime and
Discovery reload sequence. The next graph access may re-read updated files from
the same root.

No canonical, retrieval, Qdrant, Postgres, ranking, UI, graph schema, endpoint,
manual-review, or publication behavior changes are included.


## Citation Graph Failure Isolation & Error Recovery v0.1

Completed hardening slice:

```text
citation_graph_failure_isolation = implemented
graph_store_oserror_maps_to_graph_artifacts_invalid = true
graph_store_failed_load_cached = false
graph_runtime_failure_affects_general_health = false
graph_runtime_recovery_requires_process_restart = false
```

The graph status probe and six traversal/diagnostics routes remain optional,
read-only, and feature-flagged. Missing artifacts fail closed with
`graph_artifacts_not_found`. Invalid JSON/JSONL, invalid store structure, and
ordinary graph-store `OSError` failures fail closed with
`graph_artifacts_invalid` rather than escaping to the generic `500` handler.

A failed store load is not cached. After local files are repaired, the next
request may recover without restarting the API process. A cached valid store is
stable until `/reload` clears it, after which current files are re-read.

General API readiness and serving remain independent of Citation Graph state.
No endpoint, schema, graph output, canonical, retrieval, Postgres, Qdrant,
ranking, UI, manual-review, or publication semantics are promoted or changed.


## Citation Graph Live Smoke & Known-Issues Hardening v0.1

Completed validation/docs slice:

```text
citation_graph_live_smoke = implemented_operator_facing_opt_in
citation_graph_live_smoke_dod_gate = not_required
citation_graph_live_smoke_auto_samples = graph_jsonl
citation_graph_known_issues = documented_v0.1
```

The validator calls an already running API and exercises general runtime, the
status endpoint, all six traversal/diagnostics routes, stable not-found errors,
and the result-limit guard. Real samples come from current graph JSONL, so the
check is not coupled to one hard-coded production paper.

The known-issues checkpoint records metadata-only reference coverage, unresolved
external-reference semantics, low resolution ratio, non-bibliometric top/source
diagnostics, whole-file local store loading, and manual-review/publication
blocks. These are current limitations and boundaries, not permission for broad
runtime expansion.

No production API, store, schema, canonical, retrieval, Postgres, Qdrant,
ranking, Streamlit, graph artifact, manual-review approval, or publication state
is changed.


## Citation Graph Manual-Review Evidence Preparation v0.1

Completed evidence-preparation checkpoint:

```text
citation_reference_graph_manual_review_evidence = implemented_read_only
categories_count = 18
automated_support_categories_count = 13
human_decision_categories_count = 5
evidence_ready_categories_count = 18 (expected)
evidence_validator_mutated_category_status = false
evidence_validator_mutated_approval_state = false
pre_review_manual_review_complete = false
publication_ready = false
```

The evidence layer reads accepted local reports, graph/package manifests, data
quality, README files, known issues, source roles, merge policy, live smoke, and
API regression evidence. It produces one category record for every existing
manual-review category and never changes the source checklist.

Interpretation:

```text
evidence_ready = material exists for human review
evidence_ready != passed
validator ok != approval
approval remained a separate explicit human action; publication remains separate
```

No graph JSONL rebuild/reprocessing, API/runtime change, canonical/retrieval/DB/
Qdrant/ranking/UI change, GraphRAG, graph DB, or publication is introduced.


## Manual Citation Graph Review Execution v0.1

Completed human review state prepared on the active branch:

```text
required_categories = 18
passed_categories = 18
approval_state = approved
manual_review_complete = true
publication_ready = false
publication_block_reason = publication_action_not_in_scope
reviewer_role = project_owner_maintainer
reviewed_at = 2026-07-16
```

The decision record accepts the graph for the project's non-commercial,
educational, portfolio, metadata-first purpose. Future public targets are
Kaggle, GitHub, and a Radar website with attribution and original-source links.
No PDF or full-text redistribution is part of the project.

This closes the Citation Graph manual-review gate but does not publish or promote
the package. The next project-level direction is a source-aware public metadata
dataset/Kaggle release policy rather than more graph runtime expansion by
default.

## Public Metadata Release Policy & Kaggle Packaging v0.1

Current implementation state:

```text
public_metadata_release_policy = implemented
policy_schema = public_metadata_release_policy_v1
policy_validation = implemented
source_policies = 5
field_policies = 34
source_aware_abstract_gate = implemented
kaggle_metadata_template = implemented_template_only
public_upload = not_performed
publication_ready = false
publication_block_reason = public_release_decision_not_completed
```

The existing 60,954-row metadata candidate remains a derived projection of
canonical truth. Its 34-column Parquet schema is unchanged. The local package
now includes a dataset card, provider attribution, generated field/source policy
artifacts, and an unresolved Kaggle metadata template. Final compilation-license
selection, owner slug replacement, and upload remain explicit future actions.

This slice does not change canonical reconciliation, Postgres, retrieval,
Qdrant, ranking, API, Streamlit, graph outputs, or runtime behavior.
