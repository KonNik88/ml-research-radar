# Architecture

## Purpose

This document describes the current architecture of **ML Research Radar**.

ML Research Radar is a paper-centric canonical corpus and discovery platform for
ML/AI research. It is not a simple arXiv parser, not a local JSONL search demo,
not a vector-database wrapper, and not a RAG prototype.

The central entity is a stable **canonical paper entity** built from partially
overlapping source-level observations.

---

## Current checkpoint

```text
checkpoint = Retrieval Serving Checkpoint v1 / Search API Semantics Cleanup v1 / Citation Graph Traversal API Checkpoint v0.3 / Graph API Streamlit Productization Design v0.1 / Citation Graph Streamlit Status Panel v0.1 / Citation Graph Paper Workspace Panel v0.1 / Citation Graph Diagnostics UI v0.1 / Citation Graph External Reference Lookup UI v0.1 / Citation Graph UI Productization Checkpoint v0.1 / Citation Graph Store Cache & Reload Regression v0.1 / Citation Graph Failure Isolation & Error Recovery v0.1 / Citation Graph Live Smoke & Known-Issues Hardening v0.1 / Citation Graph Manual-Review Evidence Preparation v0.1 / Manual Citation Graph Review Execution v0.1 / Public Metadata Release Policy & Kaggle Packaging v0.1 / Public Metadata Release Manual-Review Evidence Preparation v0.1 / Manual Public Metadata Release Review Execution v0.1 / Source Observation Materialization Operational Promotion v0.1 / Field-Level Canonical Provenance Contract v0.1 / Field-Level Canonical Provenance Evidence Builder v0.1 / Field-Level Canonical Provenance Evidence Review & Regression Hardening v0.1 / Field-Level Canonical Provenance Evidence Checkpoint v0.1
public Qdrant promotion = not performed
public dense/hybrid backend = file
experimental Qdrant transport = gRPC
fallback = absent
```

Current stable baseline:

```text
canonical_documents = 60954
canonical_multisource_docs = 9192
doi_count = 10183
arXiv backbone = 60000
ACL-family docs = 957

source_documents_operational_count = 88178
canonical_source_links_operational_count = 88037
resolved_source_observation_links = 88037
non_contributing_source_observations = 141
null_source_observation_links = 0
dangling_source_observation_links = 0
rollback_db = ml_radar_pre_source_identity_v01_20260722t101620z

field_level_provenance_contract_fields = 61
field_level_provenance_contract_classified = 61
field_level_provenance_contract_validator_checks = 99 / 99
field_level_provenance_contract_smoke_tests = 8 passed

field_level_provenance_evidence_status = bounded_derived_explanatory_evidence
field_level_provenance_evidence_papers = 12
field_level_provenance_evidence_source_observations = 33
field_level_provenance_evidence_records = 732
field_level_provenance_evidence_matches = 708
field_level_provenance_evidence_runtime_defaults = 24
field_level_provenance_evidence_mismatches = 0
field_level_provenance_evidence_validator_checks = 34 / 34
field_level_provenance_evidence_smoke_tests = 16 passed
field_level_provenance_builder_regression = 45 passed

field_level_provenance_review_status = completed_read_only_hardening
field_level_provenance_review_validator_checks = 58 / 58
field_level_provenance_review_smoke_tests = 7 passed
field_level_provenance_evidence_block_tests = 23 passed
field_level_provenance_related_regression = 52 passed
field_level_provenance_review_strategy_families = 14
field_level_provenance_review_semantic_file_differences = 0
field_level_provenance_review_record_key_differences = 0
field_level_provenance_review_record_content_differences = 0

field_level_provenance_checkpoint_status = completed_read_only_final_checkpoint
field_level_provenance_checkpoint_validator_checks = 35 / 35
field_level_provenance_checkpoint_smoke_tests = 9 passed
field_level_provenance_checkpoint_required_failed_count = 0
field_level_provenance_line_complete = true
bounded_evidence_checkpoint_ready = true

retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]

paper_features_rows_count = 60954
topic_clusters_count = 80
topic_projection_rows_count = 2080

qdrant_collection = ml_radar_dense_benchmark_v1
qdrant_points_count = 60954
qdrant_vector_size = 384
qdrant_distance = Cosine
qdrant_selected_profile = ef_256

golden_queries_enabled = 34
golden_queries_explicit = 34
golden_queries_weak_pattern = 0
```

---

## Core flow

The current operational chain is:

```text
sources
→ raw/source records
→ normalized source-level documents
→ alignment / enrichment
→ reconcile / identity resolution
→ canonical paper corpus
→ Field-Level Canonical Provenance Contract / static validator
→ bounded Field-Level Canonical Provenance Evidence / independent validator
→ Field-Level Canonical Provenance Evidence semantic review / accepted-baseline pinning
→ Field-Level Canonical Provenance Evidence final bounded checkpoint
→ retrieval artifacts
→ deterministic source-observation identity materialization
→ Postgres materialized serving layer
→ artifact evidence/materialization layer
→ GitHub / Hugging Face enrichment
→ paper features
→ ranking / paper detail / similar papers
→ topic clusters / topic projection
→ Discovery API
→ Citation Graph status/references/citations/external-reference-papers/source-families/top-referenced-papers/top-external-references local-inspection API
→ Graph API / Streamlit productization design boundary
→ Citation Graph Streamlit status panel
→ Citation Graph Paper workspace evidence panel
→ Citation Graph diagnostics panel
→ Citation Graph external reference lookup panel
→ Citation Graph bounded store-cache / reload invalidation contract
→ Citation Graph failure isolation / repair-and-retry recovery contract
→ Citation Graph operator-facing live smoke / known-issues evidence
→ Citation Graph manual-review evidence preparation
→ Citation Graph human review decision record / checklist approval
→ Streamlit Discovery UI
→ validators / regression / strict DoD
```

---

## Main invariants

```text
canonical_documents.jsonl = paper-level truth
Postgres = rebuildable materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization plane
paper_features = derived discovery feature layer
ranking / detail / similar = derived discovery/product layer
topic clusters / projection = derived analytics/discovery layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin API client
Citation Graph API = read-only local-inspection evidence surface
Paper–Artifact evidence = Artifact API first, dedicated graph API only after separate design
Field-Level Canonical Provenance Contract = static derived governance over current reconcile semantics
Field-Level Canonical Provenance Evidence = bounded derived explanatory evidence, not canonical truth
Field-Level Canonical Provenance Evidence Review = read-only semantic determinism and drift-detection gate
Field-Level Canonical Provenance Evidence Checkpoint = final read-only fail-closed closure gate over the bounded provenance line
Qdrant = optional derived vector-serving implementation
```

Important boundary:

```text
No derived layer is allowed to mutate or redefine canonical truth.
```

Identity domains:

```text
source_observation_id
= deterministic operational source-observation row identity

doc_id
= legacy normalized-document id; not globally unique across sources

canonical_id
= reconciled paper-level identity

artifact_id
= normalized repository/model/dataset/demo identity

dense_index / Qdrant point_id
= serving mapping inside one retrieval generation
```

Paper identity priority:

```text
DOI
→ external DOI
→ arXiv ID
→ external arXiv ID
→ normalized title + year fallback
```

---

## 1. Source and normalization layer

Stable paper sources:

```text
arxiv
openalex_alignment
semantic_scholar_alignment
crossref_alignment
acl_anthology
```

Roles:

- `arxiv` is the backbone corpus.
- `openalex_alignment`, `semantic_scholar_alignment`, and `crossref_alignment`
  enrich identity, citation/reference, concept, venue, publisher, and DOI signals.
- `acl_anthology` is the first promoted domain-source expansion.
- GitHub and Hugging Face are artifact enrichment providers, not paper sources.
- Papers with Code live/source integration remains blocked/archived.

The normalized layer isolates downstream code from raw provider-specific formats.

---

## 2. Reconciliation and canonical corpus

The reconciliation layer creates paper-level canonical entities.

Responsibilities:

```text
identity resolution
source grouping
field-level fusion
conflict resolution
provenance preservation
canonical entity creation
```

Operational source of truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

A canonical URL is useful metadata but is not the sole identity rule.


### 2.1 Field-Level Canonical Provenance Contract v0.1

The project now has an explicit static contract over the current field-selection
behavior of `radar_core/normalize/reconcile.py`.

The contract classifies all 61 `CanonicalDocument` fields into:

```text
identity_derived
winner
winner_with_normalization
winner_with_quality_rank
ordered_first
ordered_union
aggregate_min
aggregate_max
boolean_evidence
derived_flag
derived_score
row_level_provenance
merged_identifier_map
runtime_default
```

It distinguishes:

```text
selected normalized observation
materialized observation
contributing observation
field candidate observation
field selected observation
field contributing observation
```

Accepted validation:

```text
canonical fields classified = 61 / 61
static validator = 99 / 99
contract smoke tests = 8 passed
related reconciliation regression = 38 passed
contract_matches_current_reconciliation = true
```

Architecture boundary:

```text
contract is documentation plus static validation
contract does not execute reconcile
contract does not mutate canonical_documents.jsonl
contract does not change CanonicalDocument
contract does not change Postgres, retrieval, Qdrant, ranking, graph, API, or UI
contract does not authorize a full-corpus evidence build
```

### 2.2 Field-Level Canonical Provenance Evidence Builder v0.1

The bounded evidence layer is now implemented over deterministic fixtures and
the selected reconciliation audit sample.

Tracked package:

```text
docs/field_level_canonical_provenance_evidence_v0.1.md
scripts/validation/build_field_level_canonical_provenance_evidence.py
scripts/validation/check_field_level_canonical_provenance_evidence.py
tests/smoke/test_build_field_level_canonical_provenance_evidence.py
tests/smoke/test_field_level_canonical_provenance_evidence.py
```

The builder consumes either the bounded audit staging directory or its ZIP and
emits one deterministic evidence record for every:

```text
canonical_id + field_name
```

Accepted bounded baseline:

```text
canonical papers = 12
contributing source observations = 33
canonical source links = 33
unmatched source links = 0
canonical fields per paper = 61
field evidence records = 732
source-reconstructable matches = 708
runtime-default records = 24
required mismatches = 0
independent validator = 34 / 34
new smoke tests = 16 passed
builder-slice related regression = 45 passed
```

Architectural role:

```text
field evidence explains current executable reconciliation semantics
field evidence does not become a selector or merge policy
field evidence record_id is derived evidence identity, not paper identity
canonical/recomputed mismatch is reported and never repaired
runtime-default fields are explicitly not source-reconstructable
```

Hard boundary:

```text
bounded and file-first
read-only and derived
canonical_truth = false
may_be_used_as_reconcile_input = false
no full-corpus materialization
no Postgres schema or serving table
no API or Streamlit provenance surface
no reconciliation, retrieval, Qdrant, ranking, graph, or publication change
```

Any full-corpus generation or product/runtime surface requires a separate
accepted design after the bounded evidence line checkpoint.

### 2.3 Field-Level Canonical Provenance Evidence Review & Regression Hardening v0.1

The bounded evidence line now has an independent semantic-review layer over two
accepted runs produced from different input forms:

```text
audit staging directory
→ evidence run 20260724T120609Z

the same audit ZIP
→ evidence run 20260724T120621Z
```

The review validator compares both runs, verifies their relationship to the
accepted audit package, and pins the accepted bounded baseline.

Accepted validation:

```text
review validator = 58 / 58
review smoke tests = 7 passed
field-level evidence block = 23 passed
related regression = 52 passed

canonical papers = 12
contributing source observations = 33
field evidence records = 732
strategy families = 14
semantic files compared = 3
semantic file differences = 0
record-key differences = 0
record-content differences = 0
value mismatches = 0
unmatched source links = 0
```

Accepted semantic SHA-256 values:

```text
field_evidence.jsonl
= d3a42644e51854226343e98f048856a16b2f9cd52289bb3dd6e5676f751077b0

paper_summary.jsonl
= dc3d3ab43d4bc3bf82c14593f0b274f8989efbd7bd79694c5a397f7b58d7356d

data_quality_summary.json
= 825d49a0f5b1b95be39a6bff77a000adc03842c8290c758716a202b04bb52236
```

Architectural interpretation:

```text
directory input and ZIP input are semantically identical
ordinary package integrity validation does not replace semantic-drift review
recomputed checksums cannot hide changed evidence content from the review gate
the accepted baseline remains bounded and audit-package-specific
```

Boundary:

```text
review is read-only
review does not rebuild evidence packages
review does not execute stable-corpus reconciliation
review does not mutate canonical truth or source observations
review does not change Postgres, retrieval, Qdrant, ranking, graph, API, or UI
review does not authorize full-corpus generation or publication
```

### 2.4 Field-Level Canonical Provenance Evidence Checkpoint v0.1

The final bounded checkpoint is implemented over the accepted contract,
evidence-validation, and semantic-review reports.

Tracked package:

```text
docs/field_level_canonical_provenance_evidence_checkpoint_v0.1.md
scripts/validation/check_field_level_canonical_provenance_evidence_checkpoint.py
tests/smoke/test_field_level_canonical_provenance_evidence_checkpoint.py
```

Accepted validation:

```text
contract = 99 / 99
evidence package validator = 34 / 34
semantic review = 58 / 58
final checkpoint = 35 / 35
checkpoint smoke tests = 9 passed
required_failed_count = 0
field_level_provenance_line_complete = true
bounded_evidence_checkpoint_ready = true
```

The checkpoint aggregates existing reports only. It fails closed on missing
reports, report/schema/status drift, field/count/hash drift, semantic
differences, mismatches, unmatched links, or changed safety flags.

Boundary:

```text
read-only and bounded
no evidence or review rebuild
no reconcile execution
no canonical/source-observation mutation
no full-corpus provenance materialization
no Postgres/retrieval/Qdrant/ranking/graph/API/UI change
no publication
```

The bounded field-level provenance line is closed. Any later full-corpus,
Postgres, API/UI, or publication expansion requires a separate accepted design.

---

## 3. Retrieval layer

Retrieval is a derived artifact layer built from canonical documents.

Public retrieval modes:

```text
lexical
dense
hybrid
```

Current implementation:

```text
lexical = file BM25 / lexical index
dense = exact file dense over normalized sentence-transformer embeddings
hybrid = lexical + exact file dense with min-max normalization and fixed weights
```

Active retrieval manifest:

```text
artifacts/retrieval/manifests/latest.json
```

Active dense artifacts:

```text
artifacts/retrieval/dense/embeddings_20260504T164021Z.npy
artifacts/retrieval/dense/ids_20260504T164021Z.json
artifacts/retrieval/dense/meta_20260504T164021Z.json
```

Exact file dense remains the reference implementation.

Reference semantics:

```python
query_vector = encoder.encode(
    [query],
    convert_to_numpy=True,
    normalize_embeddings=True,
)[0].astype(np.float32)

scores = stored_embeddings @ query_vector
order = np.argsort(scores)[::-1]
```

---

## 4. Hybrid merge

Hybrid retrieval uses shared score composition:

```text
lexical candidates
dense candidates
→ independent min-max normalization
→ union of canonical IDs
→ weighted hybrid score
→ score-based ordering
```

Current weights:

```text
lexical = 0.55
dense = 0.45
```

The shared hybrid kernel does not own retrieval, hydration, ranking, pagination,
or serialization.

---

## 5. Ranking layer

Free-form `/search` supports optional ranking:

```text
rank=false
→ default reference behavior

rank=true
→ explicit optional/experimental heuristic reranking
```

Accepted ranking evidence rejects promotion of the current heuristic reranking
formula:

```text
recommended_outcome = reject_heuristic_reranking
reference_behavior = unranked hybrid
public_behavior_change = false
```

Discovery ranking profiles are separate from free-form query reranking.

Free-form search ranking scope:

```text
radar_core/ranking/scoring.py
services/api/search_service.py
configs/scoring.yaml
```

Discovery profile ranking scope:

```text
radar_core/ranking/feature_ranking.py
radar_core/ranking/profiles.py
configs/ranking_profiles_v1.yaml
```

---

## 6. Postgres materialized serving layer

Postgres is a serving/materialization layer, not canonical truth.

Current DB-backed capabilities:

```text
GET /documents
GET /artifacts
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/papers
GET /documents/{canonical_id}/artifacts
GET /search?mode=lexical
```

Operational source-observation schema:

```text
source_documents.source_observation_id = PRIMARY KEY
source_documents.doc_id = non-unique legacy diagnostic
canonical_source_links.source_observation_id = authoritative FK
canonical_source_links.doc_id = nullable legacy diagnostic
UNIQUE(canonical_id, source_observation_id)
```

Current default operational state:

```text
ml_radar source_documents = 88,178
ml_radar canonical_source_links = 88,037
rollback DB = ml_radar_pre_source_identity_v01_20260722t101620z
```

DB backend does not currently support:

```text
/search?mode=dense
/search?mode=hybrid
```

This asymmetry is deliberate. Current DB search is a serving slice, not
retrieval-quality parity.

---

## 7. Artifact evidence and enrichment layer

Artifact evidence is separate from paper identity.

Current artifact/enrichment baseline:

```text
source_documents_operational_count = 88178
canonical_source_links_operational_count = 88037
source_observation_links_resolved = 88037
source_observation_links_null = 0
source_observation_links_dangling = 0

artifact_entities_db_count = 7333
artifact_observations_db_count = 38246
paper_artifact_links_db_count = 7430
github_found_count ≈ 5339
huggingface_found_count ≈ 77
```

Important semantics:

```text
GitHub stars/forks/language/license/status are artifact metadata.
Hugging Face downloads/likes/tags are artifact metadata.
Artifact metadata must not redefine canonical paper identity.
```

---

## 8. Discovery/product layer

Discovery API is a file-first product layer over validated derived artifacts.

It uses:

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

Product chain:

```text
ranking profile + query overrides
→ paper detail/card
→ similar papers
→ selected paper topic cluster
→ topic cluster navigation
→ topic map
→ artifact explorer
→ Streamlit UI
```

Discovery API does not redefine canonical truth.

---

## 9. Topic clusters and topic projection

Topic clusters and projections are derived analytics/discovery artifacts.

Current baseline:

```text
topic_clusters_count = 80
topic_assignments_count = 60954
topic_projection_algorithm = umap
topic_projection_rows_count = 2080
```

Cluster labels are heuristic navigation hints, not curated taxonomy.

Projection coordinates are stable only for a specific combination of:

```text
projection_build_id
cluster_build_id
retrieval_build_id
```

---

## 10. API backend architecture

The API supports two runtime backend modes:

```text
file
db
```

Controlled by:

```text
ML_RADAR_SEARCH_BACKEND
```

### File backend

Ready when:

```text
manifest is loaded
canonical documents are loaded
lexical artifacts are loaded
dense artifacts are loaded
embedding model is loaded
```

Supports:

```text
/search?mode=lexical
/search?mode=dense
/search?mode=hybrid
/experimental/search/qdrant
/discovery/*
```

`/experimental/search/qdrant` requires file runtime.

### DB backend

Ready when:

```text
DB store is loaded
DB connectivity is healthy
```

Supports browse/filter/artifact endpoints and DB lexical search.

Unsupported DB modes return structured `400 Bad Request`.

---

## 11. Qdrant layer

Qdrant is an optional derived vector-serving implementation.

Current collection:

```text
ml_radar_dense_benchmark_v1
```

Current healthy state:

```text
collection_exists = true
points_count = 60954
corpus_doc_count = 60954
vector_size = 384
distance = Cosine
status = green
optimizer_status = ok
transport = gRPC for experimental serving
profile = ef_256
```

Current Qdrant surfaces:

```text
scripts.validation.check_qdrant_collection
scripts.evaluation.compare_qdrant_file_dense
scripts.evaluation.run_qdrant_search_profile_sweep
scripts.evaluation.run_qdrant_serving_performance
scripts.evaluation.run_qdrant_hybrid_evaluation
scripts.validation.check_qdrant_file_dense_comparison
scripts.validation.check_qdrant_serving_performance
scripts.validation.check_qdrant_hybrid_evaluation
GET /experimental/search/qdrant
GET /runtime -> Qdrant diagnostics and operational state
Streamlit sidebar -> Qdrant runtime status
```

Transport roles:

```text
REST
→ compatibility-oriented parity/profile-sweep tooling

gRPC
→ production-like experimental serving, performance benchmark, and controlled hybrid evaluation
```

Critical boundaries:

```text
Qdrant is not canonical truth.
Qdrant is not required for /health readiness.
Qdrant does not change /search defaults.
Qdrant is not the production default backend.
Qdrant does not introduce fallback.
The public Qdrant search path remains /experimental/search/qdrant.
```

If Qdrant is unavailable:

```text
/health
→ still 200 OK if selected runtime backend is ready

/runtime
→ 200 OK with qdrant.ok=false and qdrant.error populated

/experimental/search/qdrant
→ structured 503

/search?mode=dense
→ file dense remains available
```

---

## 12. Dense backend abstraction

Current dense backend contract:

```text
DenseSearchBackend
├── FileDenseBackend
└── QdrantDenseBackend
```

Backends own only dense candidate generation:

```text
prepared normalized query vector
→ dense candidates
```

Backends do not own:

- query text validation;
- embedding model loading;
- query encoding;
- lexical retrieval;
- hybrid merge;
- canonical hydration;
- ranking;
- API serialization;
- fallback.

Typed dense backend errors:

```text
DenseBackendRequestError
DenseBackendUnavailableError
DenseBackendCompatibilityError
DenseBackendResultError
```

API mapping:

```text
DenseBackendRequestError       -> 400 dense_backend_bad_request
DenseBackendUnavailableError   -> 503 dense_backend_unavailable
DenseBackendCompatibilityError -> 503 dense_backend_incompatible
DenseBackendResultError        -> 503 dense_backend_invalid_result
```

---

## 13. Runtime observability

Runtime endpoint:

```text
GET /runtime
GET /runtime?refresh_qdrant=true
```

Qdrant diagnostics include:

- configured endpoint and transport;
- collection existence and compatibility;
- point count / corpus count comparison;
- vector size and distance;
- optimizer/status;
- selected search profile;
- diagnostics cache state;
- backend creation and compatibility state;
- request/success/failure counters;
- last status and timestamps;
- last failure category/stage/message;
- last timing map;
- requested/effective vector backend;
- `fallback_applied`.

`/runtime` may expose Qdrant unavailability without making `/health` unhealthy.

---

## 14. Streamlit UI

Streamlit is a thin client over FastAPI.

Current UI surfaces:

```text
Discovery ranking
Search
Experimental Qdrant dense search
Paper workspace
Topic clusters
Topic map
Artifact explorer
Sidebar API status
Sidebar Qdrant runtime status
Sidebar Citation graph status
```

The UI must not compute ranking, clustering, embeddings, or canonical merge
logic.

---

## 14.5 Citation/reference graph API checkpoint v0.3

The current graph API surface is deliberately narrow and local-inspection only:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

Checkpoint v0.3 interpretation:

```text
checkpoint v0.3 = docs/regression-hardening over the implemented seven-route graph API block
checkpoint v0.3 = not a new endpoint and not graph-runtime promotion
next preferred direction = regression / DoD hardening rather than more graph API expansion
```

Architectural role:

```text
status = compatibility/status surface over local graph artifacts and reports
references = outgoing reference evidence for one canonical paper
citations = incoming resolved internal citation evidence for one canonical paper
external-reference papers = papers referencing one unresolved external_reference
source-families = source-family reference-evidence diagnostics
top-referenced-papers = resolved internal incoming reference-count diagnostics
top-external-references = unresolved external-reference count diagnostics
```

Important boundaries:

```text
citation/reference graph output = derived local evidence
graph API = read-only, feature-flagged, compatibility-gated local-inspection surface
incoming citations = resolved internal paper_references_paper edges only
unresolved external_reference evidence is not counted as incoming canonical-paper citation
external-reference papers endpoint is implemented as reverse lookup over unresolved external evidence
source-families endpoint is implemented as reference-evidence-only diagnostics
top-referenced-papers endpoint is implemented as resolved-internal-count diagnostics
top-external-references endpoint is implemented as unresolved-external-reference-count diagnostics
full graph runtime loader = not implemented
graph DB materialization = not implemented
Streamlit graph status panel = implemented
Streamlit graph evidence panels = implemented
full graph visualization UI = not implemented
GraphRAG = not implemented
```

Productization terminology:

```text
streamlit_graph_evidence_panels = implemented
streamlit_graph_status_panel = implemented
streamlit_graph_paper_workspace_panel = implemented
streamlit_graph_diagnostics_ui = implemented
streamlit_graph_external_reference_lookup_ui = implemented
full_graph_runtime_loader = not implemented
full_graph_visualization_ui = not implemented
graph_db_materialization = not implemented
graphrag = not implemented
```

`CitationGraphStore` is the narrow file-backed local-inspection store used by
bounded read-only routes. It is not a promoted full graph runtime subsystem.
The status field `traversal_endpoints_implemented=false` remains a broad
full-runtime-surface compatibility marker; changing that field requires a
separate schema/compatibility slice.

The graph API must not mutate canonical truth, graph artifacts, validation
reports, Postgres, Qdrant, retrieval artifacts, ranking artifacts, Streamlit
state, package outputs, or publication state.




## 14.6 Graph API / Streamlit productization boundary

The four planned graph evidence consumers are implemented as thin API clients. The current step is a validator-light productization checkpoint over that accepted surface.

Accepted productization order:

```text
1. Citation Graph Streamlit Status Panel v0.1
   - call /citation-graph/status
   - show disabled/unavailable/safe-to-serve states and caveats
   - implemented as the first status-only UI code slice

2. Citation Graph Paper Workspace Panel v0.1
   - call /citation-graph/papers/{canonical_id}/references
   - call /citation-graph/papers/{canonical_id}/citations
   - render evidence tables for the selected paper

3. Citation Graph Diagnostics UI v0.1
   - call /citation-graph/source-families
   - call /citation-graph/top-referenced-papers
   - call /citation-graph/top-external-references
   - label counts as diagnostics, not global citation metrics

4. Citation Graph External Reference Lookup UI v0.1
   - call /citation-graph/external-references/{reference_id}/papers
   - handle URL/path encoding explicitly
```

Paper–Artifact Graph productization rule:

```text
Existing Artifact API surfaces are the first productization path:
/artifacts
/artifacts/{artifact_id}
/artifacts/{artifact_id}/papers
/documents/{canonical_id}/artifacts

A dedicated Paper–Artifact Graph API is deferred until a separate design slice
shows a concrete gap that these endpoints cannot cover.
```

Hard boundaries:

```text
Streamlit must not read data/graphs/* directly.
Streamlit must not import CitationGraphStore.
Streamlit must not compute graph metrics locally.
No NetworkX/Neo4j/GraphRAG runtime.
No full graph runtime loader.
No graph DB materialization.
No canonical/reconcile/search/ranking/Qdrant behavior change.
```


### 14.7 Citation Graph Paper workspace panel

The selected-paper Citation Graph UI remains a thin FastAPI client.

Implemented UI scope:

```text
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
render outgoing references and incoming resolved citations as Paper workspace evidence tables
```

Boundary:

```text
no direct reads from data/graphs/*
no CitationGraphStore import from Streamlit
no source-family/top-reference diagnostics UI
no external-reference lookup UI
no graph visualization
no NetworkX / Neo4j / GraphRAG
no full graph runtime loader
no graph DB materialization
no canonical/retrieval/Qdrant/Postgres/ranking/publication changes
```

## 15. Validation architecture

Validation is a first-class architecture layer.

Important validator families:

```text
canonical/provenance validators
retrieval artifact validators
Golden Set validators
ranking evidence validators
Qdrant collection/parity/profile/performance/hybrid validators
Discovery API validators
topic cluster/projection validators
Streamlit UI validators
Definition-of-Done checks
retrieval-serving checkpoint gate
source-observation materialization parity validator
source-observation operational-promotion validator
field-level canonical provenance contract validator
field-level canonical provenance evidence builder/validator
field-level canonical provenance evidence review validator
field-level canonical provenance evidence checkpoint validator
```

Lightweight retrieval-serving checkpoint:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint
```

Extended local checkpoint:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint ^
  --include-serving-performance-evidence ^
  --include-qdrant-collection-live ^
  --include-api-smoke
```

Generated reports under `artifacts/reports/...` are build/evidence artifacts and
are not canonical truth.

---

## 16. Deferred architecture work

Deferred, separate slices:

```text
public Qdrant promotion
ML_RADAR_VECTOR_BACKEND=file|qdrant design
Qdrant-backed public hybrid
Qdrant-backed similar-paper migration
filter pushdown into Qdrant
new embedding generation
retrieval rebuild
larger Golden Set expansion
dataset release
full text / RAG
orchestration / Airflow
distributed execution / Ray
event processing / Kafka
deployment / Kubernetes
observability stack
```

These should not be mixed into Search API Semantics Cleanup v1.

---

## 17. Current architectural interpretation

The accepted interpretation is:

```text
Public /search remains file-backed.
Qdrant is experimentally validated but not promoted.
Unranked hybrid remains the search relevance reference.
The retrieval-serving checkpoint gate is the lightweight regression guard.
Future promotion decisions must be explicit, evidence-backed, and reversible.
The source-observation promotion follows this rule: two checked dumps and the
70,244-row legacy database remain available for rollback.
Citation graph status/references/citations/external-reference-papers/source-families/top-referenced-papers/top-external-references are the checkpointed v0.3 narrow local-inspection API block, not a graph-runtime promotion.
Graph API / Streamlit productization starts as a design-only thin-client plan, not UI implementation.
```


## Citation Graph external reference lookup UI

```text
Citation Graph External Reference Lookup UI v0.1 = implemented UI-only local-inspection surface
```

The panel calls the existing `GET /citation-graph/external-references/{reference_id}/papers` endpoint through FastAPI and URL-quotes `reference_id` before placing it in the path. It renders referencing-paper evidence for unresolved external references.

Boundary:

```text
Streamlit remains a thin API client
no direct reads from data/graphs/*
no CitationGraphStore import from Streamlit
no API/store/schema changes
no graph visualization
no NetworkX/Neo4j/GraphRAG
no full graph runtime loader
no graph DB materialization
no canonical/retrieval/Qdrant/Postgres/ranking/publication change
```


## Citation Graph UI Productization Checkpoint v0.1

The accepted productization surface is now:

```text
7 read-only feature-flagged API routes
4 thin Streamlit evidence consumers
CitationGraphStore = narrow file-backed local-inspection store
full graph runtime subsystem = not implemented
full graph visualization UI = not implemented
```

This checkpoint changes documentation, validation markers, and stale comments
only. It does not change API responses, graph loading, canonical truth, retrieval,
Postgres, Qdrant, ranking, graph outputs, packages, manual-review state, or
publication state.


## Citation Graph store cache and reload lifecycle

The implemented local-inspection routes use a small process-local cache:

```text
citation_graph_store_cache = bounded_by_graph_root
citation_graph_store_cache_maxsize = 2
citation_graph_store_cache_clear_on_reload = implemented
```

The cache key is the configured graph-root string. Repeated reads of the same
root reuse one immutable, read-only `CitationGraphStore` instance. This avoids
re-reading the complete local nodes/edges files on every narrow inspection
request.

`POST /reload` invalidates the graph-store cache before reloading the main API
runtime and Discovery caches. The next graph traversal request loads the current
files from the configured root. This is cache invalidation, not a promoted graph
runtime subsystem:

```text
graph_reload_rebuilds_artifacts = false
graph_reload_mutates_artifacts = false
full_graph_runtime_loader = not implemented
graph_db_materialization = not implemented
graphrag = not implemented
```

When the reload endpoint is disabled, the request returns `404` before graph
cache invalidation. General API health remains governed by the normal API
runtime and does not depend on Citation Graph availability.


## Citation Graph failure isolation and recovery

The Citation Graph local-inspection surface is optional and failure-isolated:

```text
citation_graph_failure_isolation = implemented
graph_store_oserror_maps_to_graph_artifacts_invalid = true
graph_store_failed_load_cached = false
graph_runtime_failure_affects_general_health = false
graph_runtime_recovery_requires_process_restart = false
```

The status probe checks graph/package/report compatibility without becoming a
general runtime dependency. Each traversal route performs the compatibility gate
before loading the file-backed store. Missing files map to
`graph_artifacts_not_found`; invalid content and ordinary graph-store file I/O
errors map to `graph_artifacts_invalid`.

Only successful store construction enters the bounded cache. Therefore a failed
load cannot poison future reads: repairing the files is sufficient for the next
uncached request to recover. An already cached valid store remains immutable and
usable until `/reload` explicitly invalidates it.

This isolation preserves the architecture boundary:

```text
/health, /info, /runtime, /search, Discovery, Postgres, and Qdrant are graph-independent
no graph rebuild or graph mutation on failure/recovery
no full graph runtime subsystem
no graph DB / GraphRAG
```


## Citation Graph live smoke and known-issues evidence

```text
citation_graph_live_smoke = implemented_operator_facing_opt_in
citation_graph_live_smoke_dod_gate = not_required
citation_graph_live_smoke_auto_samples = graph_jsonl
citation_graph_known_issues = documented_v0.1
```

The live-smoke layer is validation evidence, not a runtime component. It uses
ordinary HTTP calls against an already running file-backed API with the Citation
Graph feature flag enabled. It selects one resolved paper-reference edge and one
unresolved external-reference edge from current graph JSONL, then exercises the
seven accepted graph routes plus general runtime and error-contract checks.

This preserves the architecture boundary:

```text
live smoke report = derived operator evidence
known-issues document = governance/operations evidence
API and CitationGraphStore = unchanged
manual_review_complete = false
publication_ready = false
full_graph_runtime_loader = not implemented
graph_db_materialization = not implemented
graphrag = not implemented
```

The validator is intentionally opt-in because it depends on a separately running
HTTP process and local graph artifacts. It is not added to the default refresh
Definition of Done.


## Citation Graph Manual-Review Evidence Preparation v0.1

The graph governance line includes a separate read-only evidence layer. At the preparation checkpoint it represented:

```text
manual-review checklist (18 pending categories)
+ accepted analytics / inspection / package / live API evidence
→ deterministic category evidence report
→ human review remains separate
```

Preparation split:

```text
automated_support_categories = 13
human_decision_categories = 5
evidence_ready does not mean passed
summary.ok does not mean approved
pre_review_approval_state = not_reviewed
pre_review_manual_review_complete = false
publication_ready = false
```

The subsequent human review execution records the current approved state below.

The validator does not reread the full graph output. It reuses accepted derived
reports and small README/manifest/governance inputs. This avoids duplicating the
analytics layer and preserves the graph as a derived evidence artifact.

Architecture boundary:

```text
evidence report = derived review support
evidence validator does not mutate manual-review config
canonical paper truth = unchanged
API/UI/runtime = unchanged
publication = separate explicit action
```


## Manual Citation Graph Review Execution v0.1

The graph governance path now separates automated evidence preparation from the
human-owned review decision:

```text
accepted graph/package/analytics/API evidence
→ read-only 18-category evidence report
→ explicit human reviewer decisions in manual-review config
→ tracked decision record
→ approved checklist
→ publication remains separate
```

Current reviewed state:

```text
category_status_counts = {passed: 18}
approval_state = approved
manual_review_complete = true
publication_ready = false
publication_block_reason = publication_action_not_in_scope
```

The approved scope is non-commercial educational/portfolio metadata discovery,
Kaggle/GitHub metadata or graph releases, and a future public Radar website with
provider attribution and links to originals. Radar does not redistribute PDFs
or full text. The decision changes governance state only; it does not promote the
graph to canonical truth or introduce a graph DB, full runtime loader, GraphRAG,
API schema change, or publication action.

## Public Metadata Release Policy & Kaggle Packaging v0.1

The dataset-release architecture now includes an explicit source-aware policy
between canonical truth and the local public candidate package:

```text
canonical_documents.jsonl
→ public_metadata_release_policy_v1
→ field-level include/link/null decisions
→ data.parquet + review/attribution artifacts
→ policy/output/review-readiness validators
→ explicit release decision remains separate
```

The table schema remains `dataset_release_schema_v1` with 34 columns. The
package contract is extended through `dataset_release_config_v2` and
`dataset_release_manifest_v2`.

New generated review artifacts:

```text
DATASET_CARD.md
ATTRIBUTION.md
field_release_policy.json
source_attribution.json
kaggle_metadata.template.json
```

The abstract field is fail-closed: arXiv-backed abstracts and ACL-backed
abstracts from 2016 onward are allowed; unsupported text provenance becomes
null. `pdf_url` remains an external link only. No PDF binary, full text, raw
provider payload, source snapshot, embedding vector, or publication action is
introduced.


## Public metadata manual-review evidence preparation v0.1

The dataset-release line now includes a read-only governance/evidence layer:

```text
canonical_documents.jsonl
→ source-aware public metadata package
→ config / policy / output / readiness validation
→ 20-category manual-review checklist
→ deterministic evidence preparation
→ separate human review execution
→ separate publication action
```

The checklist contains 15 categories with automated evidence support and 5
human-decision categories. At the evidence-preparation checkpoint all statuses
were `pending`; `manual_review_evidence_ready=true` meant only that review material
existed. The later execution records the human-owned passed statuses and approval.

The review/evidence validators are read-only. They do not rebuild the dataset,
mutate package files, canonical truth, retrieval, Qdrant, Postgres, ranking, API,
UI, or graph layers, and they do not call Kaggle/Hugging Face/GitHub publication
surfaces.

## Public Metadata manual-review execution boundary

The metadata-release governance line now includes a completed human review:

```text
policy and local package
→ technical review readiness
→ 20-category checklist
→ deterministic evidence preparation
→ human review execution
→ rejected publication decision
→ source-boundary remediation
→ fresh review before any publication action
```

Accepted state:

```text
approval_state = rejected
category_status_counts = {failed: 5, passed: 15}
manual_review_complete = true
publication_ready = false
publication_block_reason = manual_release_rejected
```

The blocker is confined to public redistribution governance for
Semantic Scholar-derived data. It does not invalidate canonical truth or package
integrity and does not change reconciliation, retrieval, Qdrant, Postgres, graph,
ranking, API, or UI behavior.

## Source Observation Materialization Operational Promotion v0.1

Status: **completed / operationally promoted / rollback retained**

Purpose:

```text
Promote the fully validated source-observation materialization candidate to the
default operational Postgres database without changing canonical paper truth.
```

Completed database-name transition:

```text
ml_radar
→ ml_radar_pre_source_identity_v01_20260722t101620z

ml_radar_source_identity_candidate_v01
→ ml_radar
```

Current operational schema:

```text
source_documents.source_observation_id = PRIMARY KEY
source_documents.doc_id = NOT NULL, non-unique legacy diagnostic
canonical_source_links.source_observation_id = NOT NULL
canonical_source_links.source_observation_id
  → source_documents(source_observation_id) ON DELETE RESTRICT
canonical_source_links.doc_id = nullable legacy diagnostic
UNIQUE(canonical_id, source_observation_id)
```

Accepted operational counters:

```text
canonical_documents = 60,954
source_documents = 88,178
canonical_source_links = 88,037
document_references = 709,662
artifact_entities = 7,333
artifact_observations = 38,246
paper_artifact_links = 7,430
non_contributing_source_observations = 141
null_links = 0
dangling_links = 0
missing_selected_observations = 0
```

Accepted validation evidence:

```text
promotion validator smoke tests = 10 passed
preflight = 24 / 24
backup-required preflight = 28 / 28
post-promotion = 29 / 29
DB smoke = green
artifact DB smoke = green
full source-observation parity = green
Artifact API strict filter gate = green
```

Backup and rollback evidence:

```text
operational dump SHA-256 = af40c266cf12f284b20ccad6f1877ff85c3c3b05d4ccc4a36fcd114a92e71303
candidate dump SHA-256 = 8f9e4ee2765a7eeb6f368adec263787402b0a030ff305bfcfcb634509e684b4f
rollback DB retained = true
rollback DB source_documents = 70,244
rollback DB deletion = not performed
```

Architectural interpretation:

```text
source_observation_id fixes physical source-row identity in the derived serving layer
doc_id remains useful legacy/diagnostic metadata but is not globally unique
canonical_documents.jsonl remains paper truth
reconciliation behavior and canonical IDs are unchanged
Postgres remains rebuildable and derived
```

The **Field-Level Canonical Provenance Contract v0.1**, bounded
**Field-Level Canonical Provenance Evidence Builder v0.1**, and
**Field-Level Canonical Provenance Evidence Review & Regression Hardening v0.1**
are implemented and green against the current reconciliation code and accepted
audit sample.

The review confirms semantic parity between directory- and ZIP-driven evidence
runs and detects drift even when an altered package has internally consistent
checksums. The final checkpoint is green at 35/35 with nine smoke tests, and
the bounded field-level provenance line is closed. Full-corpus generation,
Postgres materialization, API/UI exposure, publication, or any use as
reconciliation input remains unauthorized without a later separate accepted
design slice.
