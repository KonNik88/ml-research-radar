# Roadmap

## Purpose

This roadmap describes the current implementation stage of ML Research Radar and the next planned stages.

The roadmap is intentionally incremental.

The project prefers closing stable vertical slices over expanding feature surface too early.

---

## 1. Completed / Current Stage

## 1.1 Canonical paper corpus foundation

Completed:

- source normalization layer
- canonical reconciliation layer
- paper-centric canonical corpus
- provenance-preserving merge
- arXiv backbone corpus
- aligned enrichment from:
  - OpenAlex
  - Semantic Scholar
  - Crossref
- conservative paper identity resolution
- source-level vs canonical-level identity separation

Status:

- done

Current stable paper sources:

- `arxiv`
- `openalex_alignment`
- `semantic_scholar_alignment`
- `crossref_alignment`

Current operational source of truth:

- `data/analytics/reconciled/canonical_documents.jsonl`

---

## 1.2 Retrieval foundation

Completed:

- lexical retrieval
- dense retrieval
- hybrid retrieval
- retrieval artifacts build pipeline
- ranking layer
- retrieval evaluation utilities
- retrieval validation checks
- file-backend retrieval runtime

Status:

- done

Current retrieval build:

- corpus document count: 30008
- embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- retrieval artifacts are derived from the canonical paper corpus

---

## 1.3 Audit / diagnostics / evaluation layer

Completed:

- corpus audit
- source corpus audit
- overlap diagnostics
- source-to-canonical comparison
- source metadata diagnostics
- multisource inspection
- retrieval checks
- postpass audit
- known issues snapshot
- refresh Definition of Done
- provenance consistency checks

Status:

- done

---

## 1.4 Storage-backed core v1

Completed:

- Postgres infrastructure
- Qdrant infrastructure placeholder
- SQL schema for canonical serving tables
- export to Postgres
- Postgres document store
- DB-backed `/documents`
- dual-backend runtime foundation

Status:

- done

Important principle:

Postgres is a materialized serving layer.

The canonical JSONL corpus remains the operational source of truth.

---

## 1.5 DB-backed `/search` v1

Completed:

- DB backend `/search`
- lexical search only in DB backend v1
- explicit rejection of `dense` / `hybrid` in DB backend
- integration tests for DB search path
- preservation of existing file retrieval path

Status:

- done

Important principle:

File backend is retrieval-first.

DB backend is browse/filter + lexical search v1.

Dense/hybrid parity in DB backend is not required at this stage.

---

## 1.6 Backend-aware cleanup

Completed:

- backend-aware runtime snapshot
- backend-aware health semantics
- backend-aware reload semantics
- file-only vs db-only integration test split
- API/runtime contract cleanup
- documentation sync for current backend model

Status:

- done

---

## 1.7 Papers with Code rollback and source viability gate

Completed:

- Papers with Code live integration was evaluated and blocked
- PWC-specific active integration was removed from stable source paths
- active stable source core returned to four paper sources
- source viability checklist introduced
- source viability config introduced
- source viability validation script introduced
- candidate sources checked before integration work

Status:

- done

Current viability outcome:

- `github`: viable artifact source candidate
- `huggingface_hub`: viable artifact source candidate
- `acl_anthology`: viable paper source candidate
- `openreview`: viable paper source candidate
- `pubmed`: viable paper/domain source candidate
- `biorxiv`: viable paper/domain source candidate
- `medrxiv`: viable paper/domain source candidate
- `paperswithcode`: blocked / archived live source

Key lesson:

Viability first, integration later.

---

## 1.8 Green four-source baseline

Completed:

- reconcile after PWC rollback
- retrieval checks
- postpass audit
- known issues snapshot
- Postgres export
- DB smoke
- refresh Definition of Done

Status:

- done

Current baseline:

- canonical documents: 30008
- multi-source canonical documents: 5893
- active stable paper sources: 4
- DB export validated
- DoD passed

---

## 2. Current System State

The project is currently at this point:

- canonical paper corpus is stable enough for iterative growth
- retrieval works in file backend
- DB serving works for browse/filter and lexical search v1
- tests are green in both backend modes
- validation and DoD are operational
- source viability gate exists
- Papers with Code live source is blocked/archived
- the next logical stage is a separate artifact/entity layer, not another paper-truth source

---

## 3. Next Stage: Artifact Layer v1

## 3.1 Goal

The next major goal is to add a second data plane for research artifacts:

- repositories
- code
- models
- datasets
- demos
- project pages
- external artifact URLs

This layer must be separate from the canonical paper corpus.

The canonical paper corpus remains the source of truth for paper-level entities.

Artifacts can be connected to papers, but they do not have to be.

---

## 3.2 Why this comes next

The original source plan included GitHub because code and repositories are important product features.

However, GitHub is not a paper source.

After the Papers with Code live integration failed, the correct next step is not to force another artifact source into the paper reconcile layer.

The correct next step is:

1. build an artifact layer
2. extract artifact URLs from existing paper/source metadata
3. materialize artifact candidates separately
4. validate coverage
5. only then enrich artifact entities through GitHub / Hugging Face APIs

---

## 3.3 Artifact Layer v1 scope

Planned:

- internal artifact URL extraction from existing canonical/source documents
- URL normalization
- artifact classification
- candidate artifact link JSONL
- artifact quality report
- separate SQL schema for artifact entities and paper-artifact links

Initial artifact types:

- GitHub repository
- GitLab repository
- Bitbucket repository
- Codeberg repository
- Hugging Face model
- Hugging Face dataset
- Hugging Face Space
- Kaggle dataset
- Zenodo artifact
- Figshare artifact
- generic code URL
- generic dataset URL
- generic model URL
- generic artifact URL

Status:

- next

---

## 3.4 Artifact Layer v1 non-goals

Not part of v1:

- GitHub API enrichment
- Hugging Face API enrichment
- automatic canonical paper updates
- treating repositories as paper sources
- merging artifact entities into canonical paper identity
- ranking by stars/downloads
- artifact search UI
- artifact graph product layer

---

## 3.5 Artifact Layer v1 expected outputs

Expected files:

- `docs/artifact_layer_v1.md`
- `configs/artifact_extraction.yaml`
- `store/sql/03_artifact_layer.sql`
- `scripts/enrich/extract_artifact_links.py`
- `scripts/validation/check_artifact_links_quality.py`

Expected data artifacts:

- `data/enriched/artifact_links/artifact_links.<timestamp>.jsonl`
- `data/enriched/artifact_links/artifact_entities.<timestamp>.jsonl`
- `artifacts/reports/validation/artifact_links_quality_latest.json`
- `artifacts/reports/validation/artifact_links_quality_latest.md`

---

## 4. After Artifact Layer v1

## 4.1 GitHub enrichment

Planned:

- enrich extracted GitHub repository URLs
- fetch repository metadata through GitHub API
- preserve repository entities separately
- link repositories to papers only when evidence exists

Possible fields:

- owner
- repository name
- description
- topics
- stars
- forks
- license
- default branch
- created_at
- updated_at
- pushed_at
- archived flag
- disabled flag

Status:

- planned

---

## 4.2 Hugging Face Hub enrichment

Planned:

- enrich extracted Hugging Face model/dataset/space URLs
- fetch Hub metadata through API or Python client
- preserve models/datasets/spaces as artifact entities

Possible fields:

- model id
- dataset id
- space id
- tags
- downloads
- likes
- pipeline tag
- license
- library name
- card metadata

Status:

- planned

---

## 4.3 First new paper source: ACL Anthology

Planned:

- ingest ACL Anthology metadata as candidate paper source
- parse bulk XML metadata
- normalize into `NormalizedDocument`
- run source quality audit
- run candidate reconcile impact check
- integrate into stable paper pipeline only after validation

Reason:

ACL Anthology is a good first new paper source because it is:

- structured
- domain-relevant for NLP/ML
- bulk-friendly
- relatively low API risk

Status:

- planned

---

## 4.4 OpenReview candidate source

Planned:

- ingest OpenReview papers by explicit venue/year scope
- start with selected ML venues
- use API v2 / Python client where appropriate
- preserve OpenReview identifiers
- avoid mixing reviews/decisions into core paper truth prematurely

Status:

- planned

---

## 4.5 Biomedical/domain sources

Planned later:

- PubMed
- bioRxiv
- medRxiv

Purpose:

- biomedical/domain expansion
- possible ML-for-biology / ML-for-medicine coverage
- separate domain-specific corpus slices

Status:

- later

---

## 5. Medium-Scale Corpus Expansion

Medium-scale corpus expansion remains important, but it should follow the artifact layer foundation.

Target direction:

- significantly larger but still manageable working corpus
- approximately 50k+ canonical papers for the next growth stage
- recent-balanced ML/AI slice
- incremental growth, not immediate maximal crawl

Possible target slice:

- years: 2020–2026
- categories:
  - `cs.LG`
  - `cs.AI`
  - `cs.CL`
  - `cs.CV`
  - `stat.ML`
  - `cs.IR`
  - `cs.NE`
  - `cs.RO`
  - `eess.AS`
  - `eess.IV`

Planned order:

1. define target corpus slice
2. expand arXiv backbone
3. run aligned enrichment over DOI-covered subset
4. rebuild canonical corpus
5. export refreshed corpus to Postgres
6. rebuild retrieval artifacts
7. run audit / evaluation / performance checks
8. compare retrieval quality against current baseline

Status:

- planned

---

## 6. Search Hardening

Planned:

- improve SQL search quality
- improve retrieval validation queries
- reduce gap between DB lexical search and file retrieval ergonomics
- handle modern ML query failures
- improve ambiguous query diagnostics

Possible directions:

- trigram improvements
- `tsvector` / GIN
- more explicit lexical scoring
- query groups:
  - modern ML
  - ambiguous terms
  - historical topics
  - metadata-heavy queries
  - regression guards
- reranking experiments

Status:

- planned

---

## 7. Vector Serving Integration

Planned:

- integrate vector-serving path
- move toward serving-time dense retrieval
- prepare for future hybrid serving

Possible directions:

- Qdrant-backed serving
- hybrid SQL + vector candidate generation
- serving-time dense search
- DB metadata filters + vector candidates + ranker

Status:

- planned

Important principle:

Dense/hybrid serving should likely be implemented through a vector-serving layer, not by forcing dense retrieval into the current Postgres DB backend.

---

## 8. Reference / Provenance Endpoints

Planned:

- `/documents/{id}/sources`
- `/documents/{id}/references`
- source drilldown
- merge inspection utilities
- paper-artifact link drilldown later

Status:

- planned

---

## 9. Later Product Layers

These are intentionally postponed until corpus, artifact, and serving foundations are stronger.

## 9.1 Full-text and chunking

Planned:

- full-text extraction
- chunk storage
- chunk-level retrieval

## 9.2 Structured extraction

Planned:

- NER / entity extraction
- richer paper metadata derivation
- structured research signals

## 9.3 LLM / RAG layer

Planned:

- summaries
- retrieval-augmented question answering
- citation-aware generation

## 9.4 Graph / analytics layer

Planned:

- reference graph
- artifact graph
- topic graph
- trend analytics
- related-paper surfaces

## 9.5 Product surfaces

Planned:

- search UI
- topic dashboards
- paper pages
- artifact pages
- repository/model/dataset pages
- trend/radar views

---

## 10. Explicit Non-Goals for the Current Stage

Not part of the immediate next step:

- full-text pipeline
- DB-native dense search parity
- DB-native hybrid parity
- LLM summaries
- RAG serving
- large-scale graph product layer
- automatic integration of all viable sources
- GitHub/Hugging Face as paper sources
- artifact evidence modifying canonical paper identity

The current next stage is artifact layer v1.

---

## 11. Guiding Principle

The roadmap is intentionally staged:

1. stabilize canonical paper core
2. stabilize serving and validation
3. add source viability gate
4. add separate artifact/entity data plane
5. enrich artifacts through APIs
6. add new paper/domain sources carefully
7. expand corpus
8. harden search
9. add vector serving
10. add richer product layers

This ordering is deliberate and should be preserved.

The key engineering rule is:

Viability first, candidate integration second, stable integration last.