# API Reference

## Purpose

This document describes the current public API surface of ML Research Radar.

The API currently supports two backend modes:

- `file` backend — retrieval-oriented runtime using local retrieval artifacts
- `db` backend — storage-backed runtime using Postgres for browse/filter and lexical search v1

The two backends intentionally expose the same top-level API shape where possible, but they are **not fully symmetric** in current capabilities.

---

## Backend Modes

### File backend

Current characteristics:

- uses retrieval artifacts from local files
- loads canonical corpus from JSONL
- supports:
  - lexical search
  - dense search
  - hybrid search

### DB backend

Current characteristics:

- uses Postgres as materialized serving layer
- supports:
  - `/documents` browse/filter access
  - `/search` with `mode=lexical` only

Not supported in DB backend v1:

- `mode=dense`
- `mode=hybrid`

These unsupported modes return `400 Bad Request`.

---

## Error Response

All structured API errors use the following shape:

```json
{
  "error_code": "bad_request",
  "message": "human-readable error message",
  "details": null
}

---

## Typical error codes:

- bad_request
- validation_error
- runtime_not_ready
- file_not_found
- internal_error

---

## Endpoints

GET /health
Backend-aware readiness check.
Purpose
Returns whether the current runtime is ready and which components are active.
Response shape

```json
{
  "status": "ok",
  "backend_mode": "db",
  "ready": true,
  "build_id": "db-runtime",
  "corpus_doc_count": 1000,
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

## Notes

 -In `file` mode, readiness is based on loaded manifest, documents, lexical artifacts, dense artifacts, and embedding model
- In `db` mode, readiness is based on DB store availability and DB connectivity

---

GET /info
Returns API-level information plus current backend/runtime information.

Response fields
- api_title
- api_version
- backend_mode
- build_id
- corpus_doc_count
- embedding_model_name
- artifacts_root
- loaded_components

---

GET /runtime

Returns a detailed runtime snapshot.

Response fields
- ready
- backend_mode
- build_id
- corpus_doc_count
- embedding_model_name
- artifacts_root
- loaded_components
- db_connected
- last_load_error
- last_loaded_at
- last_reload_at
- model_reused
- current_model_name

Semantics
File backend
--build_id comes from retrieval manifest
- embedding_model_name is populated
- file retrieval components are marked in loaded_components
- db_connected = false
DB backend
- build_id = "db-runtime"
- embedding_model_name = null
- file retrieval components are not loaded
- db_connected indicates DB reachability

---

POST /reload

Reloads the current runtime.

Behavior
File backend

Reloads:

- latest manifest
- canonical documents
- lexical artifacts
- dense artifacts
- embedding model
- DB backend

Reloads:

- Postgres-backed runtime
- DB store connectivity and document count snapshot

Response shape
```json
{
  "status": "reloaded",
  "backend_mode": "db",
  "message": "DB backend runtime reloaded successfully",
  "build_id": "db-runtime",
  "corpus_doc_count": 1000,
  "embedding_model_name": null,
  "model_reused": false,
  "last_reload_at": "2026-03-28T12:00:00+00:00"
}

---

GET /search

Main relevance-search endpoint.

Query parameters
- query — required search query
- mode — lexical | dense | hybrid
- top_k — number of results
- rank — whether ranking layer should be applied
- year_from
- year_to
- category
- source
- publication_type
- venue
- open_access
- has_code_link
- offset
- sort_by — relevance | year_desc | year_asc

---

File backend support

Supported modes:

- lexical
- dense
- hybrid

Retrieval is artifact-based.

DB backend support

Supported modes:

- lexical

Unsupported modes:

- dense
- hybrid

These return 400 Bad Request with a descriptive error message.

DB lexical search v1

Current DB search v1 behavior:

- SQL candidate generation
- title / abstract / authors text matching
- optional filters
- simple ranking for rank=true
- same top-level response schema as /search

This is a serving slice, not parity with file-based hybrid retrieval.

---

Search Response
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

---

GET /documents

Browse/filter endpoint available in DB-backed runtime.

Purpose

Provides deterministic browse/filter access over canonical documents stored in Postgres.

Query parameters
- query
- limit
- offset
- year_from
- year_to
- category
- source
- publication_type
- venue
- open_access
- has_code_link
- sort_by — year_desc | year_asc | title_asc

Response shape
```json
{
  "total": 1000,
  "offset": 0,
  "limit": 10,
  "sort_by": "year_desc",
  "results": [
    {
      "canonical_id": "...",
      "title": "...",
      "abstract": "...",
      "authors": [],
      "year": 2024,
      "doi": "...",
      "categories": [],
      "concepts": [],
      "keywords": [],
      "tags": []
    }
  ]
}

Notes
- /documents is not a relevance-search endpoint
- /documents is intended for browse/filter scenarios
- /documents is currently DB-only

---

Current Capability Matrix
| endpoint | file backend | db backend |
|---|---|---:|
| `/health` | yes | yes |
| `/info` | yes | yes |
| `/runtime` | yes | yes |
| `/reload` | yes | yes |
| `/info` | yes | yes |
| `/search?mode=lexical` | yes | yes |
| `/search?mode=dense` | yes | no |
| `/search?mode=hybrid` | yes | no |
| `/documents` | no | yes |

---

Design Notes

The current API reflects the current architecture:

- JSONL canonical corpus remains the source of truth
- Postgres is the current materialized serving layer
- retrieval artifacts remain file-based
- dual-backend support is intentionally asymmetric during this phase

## `docs/architecture.md`

```md
# Architecture

## Purpose

This document describes the current architecture of ML Research Radar.

ML Research Radar is a paper-centric canonical corpus platform for machine learning research papers. It is designed to build a stable canonical paper corpus from multiple partially overlapping sources, enrich it with metadata, support retrieval and search, and prepare the system for future analytics, graph features, vector search, and product layers.

---

## 1. System Overview

The current project is organized around the following core flow:

`sources → ingest → normalized documents → alignment/enrichment → reconcile → canonical corpus → retrieval artifacts → API/runtime`

This is the real current architecture, not just a planned direction.

---

## 2. Core Design Principle

The center of the system is the **canonical paper entity**.

The system is intentionally designed around:

- source-level normalized records
- canonical reconciliation
- source-aware merge
- provenance preservation
- backend-aware serving

The project does **not** treat raw source records as final search entities.

---

## 3. Main Layers

## 3.1 Source / ingest layer

Each external source is normalized into a unified source-level paper contract.

Current sources:

- `arxiv`
- `openalex_alignment`
- `semantic_scholar_alignment`
- `crossref_alignment`
- `paperswithcode_alignment` (planned / experimental)

### Current source roles

- `arxiv` = backbone corpus source
- `openalex_alignment` = semantic enrichment
- `semantic_scholar_alignment` = auxiliary bibliographic/citation support
- `crossref_alignment` = bibliographic stabilizer and references enrichment
- `paperswithcode_alignment` = planned artifact enrichment

---

## 3.2 Normalized document layer

All source-specific inputs are transformed into a unified source-level paper contract.

This layer isolates downstream components from raw source API differences.

Key responsibilities:

- source normalization
- stable source-level identity
- source field harmonization
- stage/provenance tracking

---

## 3.3 Reconciliation layer

The reconciliation layer creates canonical paper entities.

This is the core quality gate of the project.

Responsibilities:

- identity resolution
- source grouping
- field-level fusion
- conflict resolution
- provenance preservation
- canonical entity creation

Identity priority is currently:

1. DOI
2. external DOI
3. arXiv id
4. external arXiv id
5. title + year fallback

The system uses field-dependent source trust rather than assuming one source is best for all fields.

---

## 3.4 Canonical corpus

The canonical corpus is the paper-level merged output of reconciliation.

Canonical documents contain:

- merged identifiers
- merged paper metadata
- merged semantic/bibliographic/artifact fields
- source provenance
- source counts
- quality signals
- graph-ready reference fields

This is the main corpus used for retrieval and serving.

---

## 3.5 Retrieval layer

Retrieval is currently a separate artifact-based layer built on top of the canonical corpus.

Current retrieval modes:

- lexical retrieval
- dense retrieval
- hybrid retrieval

Current retrieval implementation:

- lexical index built over canonical corpus text fields
- dense embeddings using `sentence-transformers/all-MiniLM-L6-v2`
- hybrid merge over lexical and dense outputs

Current retrieval is **file-based**, not DB-native.

---

## 3.6 Ranking layer

Ranking exists as a distinct layer on top of retrieval.

Current ranking signals include:

- retrieval score
- recency
- source support
- metadata quality

Ranking is currently applied after retrieval and remains separate from storage.

---

## 3.7 Audit / diagnostics / evaluation layer

The project includes a dedicated quality-control layer.

Current capabilities include:

- canonical corpus audit
- source corpus audit
- source-to-canonical comparison
- audit comparison across runs
- overlap diagnostics
- source-specific metadata diagnostics
- retrieval evaluation
- bootstrap evaluation set generation

This layer is a first-class part of the system, not a side utility.

---

## 4. Source of Truth and Serving Model

## 4.1 Source of truth

The canonical JSONL corpus remains the current source of truth.

This means:

- ingest / normalize / reconcile produce canonical JSONL outputs
- retrieval artifacts are built from canonical JSONL
- Postgres is populated from canonical outputs

## 4.2 Materialized serving layer

Postgres currently acts as a **materialized serving layer**.

This means:

- Postgres is used for serving and query access
- Postgres is not yet the canonical authoring/source-of-truth layer
- export from canonical outputs to Postgres is part of the serving pipeline

---

## 5. Current API Backend Architecture

The current API supports two backend modes.

## 5.1 File backend

Role:
- retrieval-oriented serving

Capabilities:
- loads retrieval manifest
- loads canonical documents from file
- loads lexical artifacts
- loads dense artifacts
- loads embedding model
- supports `/search` with:
  - `lexical`
  - `dense`
  - `hybrid`

## 5.2 DB backend

Role:
- storage-backed serving slice

Capabilities:
- loads Postgres-backed runtime
- supports `/documents`
- supports `/search` with `mode=lexical` only
- rejects `dense` and `hybrid` in current DB search v1

---

## 6. Important Architectural Clarification

The two backends are intentionally **not fully symmetric**.

Current meaning:

- `file backend` = retrieval-oriented backend
- `db backend` = browse/filter + lexical search v1

This is a transition phase in the architecture and is expected.

It is better to think of current DB search as a new serving slice with API contract parity, not retrieval quality parity.

---

## 7. Current Runtime Readiness Model

### File backend is considered ready when:
- manifest is loaded
- canonical documents are loaded
- lexical artifacts are loaded
- dense artifacts are loaded
- embedding model is loaded

### DB backend is considered ready when:
- DB store is loaded
- DB connectivity is healthy

---

## 8. Storage Overview

Current storage layers:

### File-based layers
- raw source artifacts
- normalized source documents
- canonical reconciled corpus
- retrieval artifacts
- run manifests
- local source-level change detection index

### DB-based layers
- `canonical_documents`
- `source_documents`
- `canonical_source_links`
- `document_references`
- `export_runs`

---

## 9. Current Scope Boundaries

Included in the current architecture:

- paper entities
- canonical paper reconciliation
- retrieval artifacts
- Postgres-backed serving
- evaluation and audit utilities

Explicitly postponed:

- GitHub/repository entity layer
- vector DB serving path
- dense DB-native serving
- hybrid DB-native serving
- full-text extraction pipeline
- chunk-level storage
- NER/entity extraction layer
- LLM summaries / RAG serving
- full graph product layer

---

## 10. Near-Term Architectural Direction

The next major stage after current cleanup is:

### medium-scale corpus expansion

Planned order:

1. expand arXiv backbone
2. run aligned enrichment
3. rebuild canonical corpus
4. export to Postgres
5. rebuild retrieval artifacts
6. run audit / evaluation / performance checks

Only after this stage should the system move toward:

- SQL search hardening
- vector serving integration
- Qdrant-backed retrieval path
- richer graph/product features

---

## 11. Design Summary

ML Research Radar is currently:

- a paper-centric canonical corpus platform
- with source-aware normalization and reconciliation
- with retrieval as a distinct artifact layer
- with JSONL as source of truth
- with Postgres as materialized serving layer
- with intentionally asymmetric dual-backend API serving

This architecture is deliberate and appropriate for the current project stage.

