# Architecture

## Purpose

This document describes the current architecture of **ML Research Radar**.

ML Research Radar is a paper-centric canonical corpus and discovery platform for ML/AI research. The project is not a simple arXiv parser, not a local JSONL search demo, and not a RAG prototype. Its central entity is a stable **canonical paper entity** built from partially overlapping source-level observations.

---

## Current checkpoint

Current working checkpoint:

```text
Discovery Green Checkpoint — 2026-05 / Qdrant runtime visibility sync — 2026-06
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
qdrant_benchmark_collection = ml_radar_dense_benchmark_v1
qdrant_benchmark_uploaded_count = 60954
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
Qdrant = optional derived vector-serving benchmark / experimental layer
```

Important boundary:

```text
No derived layer is allowed to mutate canonical truth.
```

---

## 1. Source and normalization layer

Current stable paper sources:

```text
arxiv
openalex_alignment
semantic_scholar_alignment
crossref_alignment
acl_anthology
```

Roles:

- `arxiv` is the 60k backbone.
- `openalex_alignment`, `semantic_scholar_alignment`, and `crossref_alignment` enrich the backbone.
- `acl_anthology` is the first major source-expansion case.
- GitHub and Hugging Face are artifact enrichment providers, not paper sources.
- Papers with Code live/source integration remains blocked/archived; PWC-like signals are artifact candidates only unless policy changes.

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

Identity priority is currently:

```text
DOI
external DOI
arXiv id
external arXiv id
title + year fallback
```

The current operational paper source of truth is:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

---

## 3. Retrieval layer

Retrieval is a derived artifact layer built from canonical documents.

Current retrieval modes:

```text
lexical
dense
hybrid
```

Current implementation:

```text
lexical index over canonical text fields
dense embeddings with sentence-transformers/all-MiniLM-L6-v2
hybrid merge over lexical and dense candidates
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

Retrieval remains file-based in the current checkpoint.

---

## 4. Postgres materialized serving layer

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

This asymmetry is deliberate: current DB search is a serving slice, not retrieval-quality parity.

---

## 5. Artifact evidence and enrichment layer

Artifact evidence is a separate plane from paper identity.

Current artifact/enrichment baseline:

```text
artifact_entities_db_count = 7333
artifact_observations_db_count = 38246
paper_artifact_links_db_count = 7430
github_found_count ≈ 5339
huggingface_found_count ≈ 77
```

GitHub and Hugging Face metadata are artifact metadata, not canonical paper truth.

Important semantics:

```text
GitHub stars/forks/language/license/status must not be used as canonical identity signals.
Hugging Face forbidden/skipped_invalid_external_id states are diagnostics under current policy.
```

---

## 6. Discovery/product layer

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

Current product chain:

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

## 7. Topic clusters and topic projection

Topic clusters and projections are derived analytics/discovery artifacts.

Current baseline:

```text
topic_clusters_count = 80
topic_assignments_count = 60954
topic_projection_algorithm = umap
topic_projection_rows_count = 2080
```

Topic cluster labels are heuristic navigation hints, not curated taxonomy.

Projection coordinates are stable only for a specific combination of:

```text
projection_build_id
cluster_build_id
retrieval_build_id
```

---

## 8. API backend architecture

The API supports two backend modes:

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

Supports `/search` modes:

```text
lexical
dense
hybrid
```

### DB backend

Ready when:

```text
DB store is loaded
DB connectivity is healthy
```

Supports:

```text
documents/artifacts browsing
DB lexical search v1
```

The two backends are intentionally not fully symmetric.

---

## 9. Qdrant layer

Qdrant is currently an optional derived vector-serving benchmark / experimental layer.

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
```

Current Qdrant surfaces:

```text
scripts.validation.check_qdrant_collection
scripts.evaluation.compare_qdrant_file_dense
scripts.validation.check_qdrant_file_dense_comparison
GET /experimental/search/qdrant
GET /runtime -> qdrant diagnostics
Streamlit sidebar -> Qdrant runtime status
```

Critical boundaries:

```text
Qdrant is not canonical truth.
Qdrant is not required for /health readiness.
Qdrant does not change /search defaults.
Qdrant is not the production default backend.
The public Qdrant search path remains /experimental/search/qdrant.
```

If Qdrant is unavailable:

```text
/health still returns 200 OK if the selected runtime backend is ready.
/runtime still returns 200 OK with qdrant.ok=false and qdrant.error populated.
Streamlit remains usable and shows Qdrant unavailable.
```

---

## 10. Streamlit UI

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

The UI must not compute ranking, clustering, embeddings, or reconciliation locally.

Current UI validation:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Expected Qdrant UI check:

```text
qdrant_runtime_status_ui_snippets_present = true
required_failed_count = 0
```

---

## 11. Validation and DoD layer

The validation layer is first-class architecture, not a side utility.

Current validation families:

```text
canonical / provenance / postpass audit
retrieval checks
artifact quality
GitHub enrichment
Hugging Face enrichment
paper features
ranking profiles
similar papers
Discovery API
topic clusters
topic projection
Streamlit UI
Qdrant benchmark / serving POC / experimental API
strict DoD
```

Preferred engineering pattern:

```text
small focused script
→ explicit report
→ strict validator
→ optional DoD gate
→ docs/runbook update
```

---

## 12. Current scope boundaries

Included now:

```text
canonical paper corpus
file retrieval artifacts
Postgres materialized serving
artifact evidence layer
GitHub/HF artifact enrichment
paper features
Discovery API
Streamlit UI
topic clusters/projection
Qdrant experimental visibility and validation
```

Postponed:

```text
full-text ingestion
chunk-level retrieval
production Qdrant /search backend
RAG serving
Airflow orchestration
Kubernetes deployment
Kafka/event streaming
public production frontend
GraphRAG/product graph layer
```

---

## 13. Near-term direction

Near-term after current Qdrant visibility sync:

```text
docs/runtime runbook sync
Golden Set Expansion v2
small UI/topic label polish
cache diagnostics if needed
careful planning for Qdrant search promotion
```

Do not jump directly into Qdrant/RAG/Airflow until current docs, runbooks, and regression commands remain stable.

Final rule:

```text
Viability first, candidate integration second, stable integration last.
```
