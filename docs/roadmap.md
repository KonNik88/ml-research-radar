# Roadmap

## Purpose

This roadmap describes the current implementation stage of ML Research Radar and the next planned stages.

The roadmap is intentionally incremental. The project prefers closing stable vertical slices over expanding feature surface too early.

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

Status:
- done

---

## 1.2 Retrieval foundation
Completed:

- lexical retrieval
- dense retrieval
- hybrid retrieval
- retrieval artifacts build pipeline
- ranking layer
- retrieval evaluation utilities

Status:
- done

---

## 1.3 Audit / diagnostics / evaluation layer
Completed:

- corpus audit
- source corpus audit
- overlap diagnostics
- source-to-canonical comparison
- source metadata diagnostics
- multisource inspection
- bootstrap eval set
- evaluation run scripts

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

## 2. Current System State

The project is currently at this point:

- canonical corpus is stable enough for iterative growth
- retrieval works in file backend
- DB serving works for browse/filter and lexical search v1
- tests are green in both backend modes
- documentation matches current architecture closely enough
- the next logical stage is controlled corpus expansion

---

## 3. Next Stage

## 3.1 Medium-scale corpus expansion
Next major goal:

build a significantly larger but still manageable working corpus.

Target direction:
- approximately 10k–50k canonical papers
- incremental growth, not immediate maximal crawl

Planned order:

1. expand arXiv backbone
2. run aligned enrichment over DOI-covered subset
3. rebuild canonical corpus
4. export refreshed corpus to Postgres
5. rebuild retrieval artifacts
6. run audit / evaluation / performance checks

Status:
- next

---

## 4. After Medium-Scale Corpus

## 4.1 Search hardening
Planned:

- improve SQL search quality
- possibly add stronger text indexing
- reduce gap between DB lexical search and file retrieval ergonomics

Status:
- planned

### Possible directions
- trigram improvements
- `tsvector` / GIN
- more explicit lexical scoring

---

## 4.2 Vector serving integration
Planned:

- integrate vector-serving path
- move toward serving-time dense retrieval
- prepare for future hybrid serving

Status:
- planned

### Possible directions
- Qdrant-backed serving
- hybrid SQL + vector candidate generation
- serving-time dense search

---

## 4.3 Reference / provenance endpoints
Planned:

- `/documents/{id}/sources`
- `/documents/{id}/references`
- source drilldown / merge inspection utilities

Status:
- planned

---

## 5. Later Product Layers

These are intentionally postponed until medium-scale corpus and serving foundations are stronger.

## 5.1 Full-text and chunking
Planned:
- full-text extraction
- chunk storage
- chunk-level retrieval

## 5.2 Structured extraction
Planned:
- NER / entity extraction
- richer paper metadata derivation
- structured research signals

## 5.3 LLM / RAG layer
Planned:
- summaries
- retrieval-augmented question answering
- citation-aware generation

## 5.4 Graph / analytics layer
Planned:
- reference graph
- topic graph
- trend analytics
- related-paper surfaces

## 5.5 Artifact / repository layer
Planned:
- repository entities
- repo-to-paper linkage
- code/dataset/model surfaces as first-class product features

---

## 6. Explicit Non-Goals for the Current Stage

Not part of the immediate next step:

- full-text pipeline
- DB-native dense search parity
- DB-native hybrid parity
- GitHub entity layer
- LLM summaries
- RAG serving
- large-scale graph product layer

The project should not expand into these areas before medium-scale corpus validation.

---

## 7. Guiding Principle

The roadmap is intentionally staged:

1. stabilize core
2. stabilize serving
3. expand corpus
4. harden search
5. add vector serving
6. add richer product layers

This ordering is deliberate and should be preserved.