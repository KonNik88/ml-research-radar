# Article Source Architecture

## 1. Purpose

This document defines the current article-source architecture of ML
Research Radar.

Its goal is to fix the actual structure of the paper ingestion and
canonicalization system so that future work on full text, embeddings,
artifact linking, API features, orchestration, and product surfaces can
build on a stable foundation.

This is an architecture/state document, not a wish-list. It reflects the
current working system and the intended near-term direction.

------------------------------------------------------------------------

## 2. Core architectural principle

ML Research Radar is a **paper-centric canonical corpus platform**.

The central entity of the system is **not** a raw source record and
**not** a source API response.\
The central entity is a **canonical paper-level document** built from
one or more normalized source-level records.

------------------------------------------------------------------------

## 3. Source-of-truth model

### Canonical corpus

data/analytics/reconciled/canonical_documents.jsonl

### Postgres

Materialized serving layer (not source of truth)

### Retrieval artifacts

Derived layer (lexical + dense indexes)

------------------------------------------------------------------------

## 4. Active source core

-   arxiv
-   openalex_alignment
-   semantic_scholar_alignment
-   crossref_alignment

Experimental: - paperswithcode_alignment

------------------------------------------------------------------------

## 5. Roles of sources

arXiv → backbone corpus\
OpenAlex → semantic enrichment\
Semantic Scholar → auxiliary metadata\
Crossref → bibliographic stabilization

------------------------------------------------------------------------

## 6. Identity model

doc_id → source-level identity\
canonical_id → paper-level merged identity

Reconcile priority: 1. DOI 2. external DOI 3. arXiv id 4. external arXiv
id 5. title + year

------------------------------------------------------------------------

## 7. Merge semantics

Content → arXiv priority\
Semantic → OpenAlex\
Bibliographic → Crossref\
Auxiliary → Semantic Scholar

------------------------------------------------------------------------

## 8. Special rules

open_access ≠ is_open_access

publication_type must be corrected by stronger sources

------------------------------------------------------------------------

## 9. Provenance

source_ids → identifier map\
sources → provenance rows\
source_count → rows\
unique_source_count → source families

------------------------------------------------------------------------

## 10. Refresh model

selective → merge → reconcile → validate → promote → export → retrieval
→ audit

Promotion is always explicit.

------------------------------------------------------------------------

## 11. Serving split

File backend → retrieval (lexical + dense)\
DB backend → browse/filter/search v1

------------------------------------------------------------------------

## 12. Current state

docs ≈ 30008\
multisource ≈ 5893

------------------------------------------------------------------------

## 13. Direction

1.  stabilize article layer\
2.  add text layers\
3.  embeddings\
4.  retrieval/LLM\
5.  orchestration later
