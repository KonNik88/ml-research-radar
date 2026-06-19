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
checkpoint = Retrieval Serving Checkpoint v1 / Search API Semantics Cleanup v1
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
→ retrieval artifacts
→ Postgres materialized serving layer
→ artifact evidence/materialization layer
→ GitHub / Hugging Face enrichment
→ paper features
→ ranking / paper detail / similar papers
→ topic clusters / topic projection
→ Discovery API
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
Qdrant = optional derived vector-serving implementation
```

Important boundary:

```text
No derived layer is allowed to mutate or redefine canonical truth.
```

Identity domains:

```text
source_doc_id / doc_id
= source-level observation identity

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
```

The UI must not compute ranking, clustering, embeddings, or canonical merge
logic.

---

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
```
