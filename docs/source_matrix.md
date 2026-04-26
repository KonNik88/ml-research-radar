# Source Matrix

## Purpose

This document defines the current source landscape of ML Research Radar:

- which sources are used
- which sources are candidate sources
- how sources are connected
- what metadata they contribute
- what role they play during canonical reconciliation
- how much they are trusted for different metadata families
- which sources belong to the paper plane, artifact plane, or signal plane

The goal is to keep source behavior explicit and stable as the project grows.

ML Research Radar is a paper-centric canonical corpus platform, but not every source is a paper source.

The project now explicitly separates:

1. paper sources
2. artifact sources
3. signal sources

This separation prevents artifact repositories, models, datasets, or trend signals from being accidentally treated as bibliographic paper truth.

---

## 1. Source taxonomy v2

### 1.1 Paper sources

Paper sources provide paper-level metadata and may contribute to canonical paper entities.

They can contribute to:

- title
- abstract
- authors
- DOI
- arXiv id
- PMID
- venue
- journal
- conference
- publisher
- publication type
- publication date
- references
- citation counts
- taxonomy / topic metadata

Current stable paper sources:

- `arxiv`
- `openalex_alignment`
- `semantic_scholar_alignment`
- `crossref_alignment`

Candidate paper/domain sources after viability checks:

- `acl_anthology`
- `openreview`
- `pubmed`
- `biorxiv`
- `medrxiv`

### 1.2 Artifact sources

Artifact sources provide repositories, code, models, datasets, demos, project pages, and other non-paper research artifacts.

They must not be treated as paper-level truth sources.

They may contribute to:

- repository entities
- model entities
- dataset entities
- demo/project URLs
- artifact metadata
- possible paper-artifact links
- code/dataset/model convenience fields

Candidate artifact sources after viability checks:

- `github`
- `huggingface_hub`

Archived or blocked artifact source:

- `paperswithcode`

Papers with Code live integration is blocked because the upstream live path did not provide usable JSON.

Future Papers with Code use may only be reconsidered as offline historical backfill after a separate viability check.

### 1.3 Signal sources

Signal sources provide popularity, trending, discovery, ranking, or prioritization signals.

They must not directly modify canonical paper truth.

Possible future signal sources:

- Hugging Face Trending Papers
- GitHub stars/trending
- news/social/trend sources
- other discovery surfaces

Signal sources can influence ranking, alerts, or discovery, but they are not canonical bibliographic sources.

---

## 2. Current active source roles

| source | plane | mode | match basis | primary role | strong fields | weak / not trusted fields | status |
|---|---|---|---|---|---|---|---|
| `arxiv` | paper | backbone | arXiv id / DOI / title fallback | corpus backbone, preprint manifestation, main text source | title, abstract, authors, categories, arxiv_id, pdf_url, comment, journal_ref | publisher truth, venue truth, final publication type truth, citation graph | active |
| `openalex_alignment` | paper | alignment | DOI | semantic enrichment + citation metadata | concepts, keywords, cited_by_count, referenced_ids, venue, journal, publisher, OA hints | publication_type can be noisy, artifact links limited | active |
| `semantic_scholar_alignment` | paper | alignment | DOI / arXiv id | auxiliary bibliographic + citation support | external identifiers, cited_by_count, venue hints, title/author cross-check | journal can be noisy, reference coverage can be uneven, OA metadata limited | active |
| `crossref_alignment` | paper | alignment | DOI | bibliographic stabilizer + references enrichment | publisher, publication_type, references_count, referenced_dois, license, publication date | abstract often missing, semantic metadata weak, cited_by_count weak | active |

---

## 3. Candidate source roles after viability checks

| source | plane | access mode | primary role | expected contribution | status |
|---|---|---|---|---|---|
| `github` | artifact | REST API | repository/artifact enrichment | repositories, topics, stars, forks, licenses, repo metadata, possible paper links | viable candidate |
| `huggingface_hub` | artifact | Hub API / Python client | model/dataset/space enrichment | models, datasets, spaces, cards, tags, downloads, likes, possible paper links | viable candidate |
| `acl_anthology` | paper | bulk metadata / GitHub XML | NLP/domain paper source | NLP papers, venues, authors, abstracts where available, URLs, ACL ids | viable candidate |
| `openreview` | paper | API v2 / Python client | ML conference paper source | submissions, venues, reviews metadata later, OpenReview ids, titles, authors, abstracts | viable candidate |
| `pubmed` | paper | NCBI E-utilities | biomedical/domain paper source | PMID, DOI, biomedical titles/abstracts, publication metadata | viable candidate |
| `biorxiv` | paper | public API | biomedical preprint source | preprints, DOI, title, abstract, authors, category/date metadata | viable candidate |
| `medrxiv` | paper | public API | medical preprint source | preprints, DOI, title, abstract, authors, category/date metadata | viable candidate |
| `paperswithcode` | artifact | archived-only / blocked live | historical artifact source only if reconsidered | repo/code/dataset/model links from offline data only | blocked / archived |

---

## 4. Current operational paper pipeline

The current stable canonical paper build is based on:

1. `arxiv` as corpus backbone
2. `openalex_alignment` for DOI-aligned semantic enrichment
3. `semantic_scholar_alignment` for auxiliary bibliographic support
4. `crossref_alignment` for bibliographic and references enrichment

Current clean baseline:

- canonical corpus source of truth: `data/analytics/reconciled/canonical_documents.jsonl`
- canonical documents: 30008
- multi-source canonical documents: 5893
- active stable sources: 4
- retrieval artifacts built from canonical corpus
- Postgres materialized from canonical corpus
- DoD passed after DB export and validation

---

## 5. Source-specific notes

### `arxiv`

- Main backbone of the current corpus
- Provides the majority of current papers
- Primary source for abstract, categories, arXiv identifiers, PDF links, comments, and journal reference strings
- Represents preprint/open manifestation semantics
- Does not automatically define final bibliographic publication type

### `openalex_alignment`

- Current strongest semantic enrichment layer
- Main source for concepts, keywords, cited-by metadata, OpenAlex identifiers, and venue/publisher hints
- Useful for OA hints and graph-oriented identifiers
- Strong for semantic metadata, but field-level noise still requires conservative merge rules

### `semantic_scholar_alignment`

- Auxiliary bibliographic and citation layer
- Useful for DOI/arXiv/DBLP/CorpusId/MAG-style identifier support
- Helps recover citation/reference metadata and venue hints
- Should be treated as secondary support rather than primary bibliographic authority

### `crossref_alignment`

- Main bibliographic stabilization layer for DOI-covered subset
- Strongest current source for publisher, publication type, publication dates, references_count, referenced_dois, and license hints
- Important for future citation/reference graph construction
- License information still needs conservative normalization

### `github`

- Artifact source, not paper source
- Should produce repository entities and possible paper-artifact links
- Should not modify canonical paper title, authors, abstract, venue, publisher, citation counts, or publication type
- Good future source for repo metadata: owner, name, description, topics, license, stars, forks, archived status, timestamps

### `huggingface_hub`

- Artifact ecosystem source, not paper source
- Should produce model, dataset, and space entities
- May contribute model/dataset links, tags, downloads, likes, license, pipeline tags, card metadata
- Should not override paper bibliographic truth

### `acl_anthology`

- Candidate paper/domain source for NLP and computational linguistics
- Good candidate for deterministic/bulk metadata ingestion
- Should be integrated as candidate paper source first, then evaluated before stable reconcile integration

### `openreview`

- Candidate paper source for ML conference submissions and accepted papers
- API/client behavior may differ between venues and years
- Should first be implemented as candidate ingestion with clear venue/year scope
- Reviews and decisions are separate product layers and should not be mixed into basic paper truth prematurely

### `pubmed`

- Biomedical/domain paper source
- PMID-first identity with DOI where available
- Useful for biomedical expansion, not immediate ML core expansion

### `biorxiv` / `medrxiv`

- Biomedical/medical preprint sources
- Useful for domain expansion
- Should remain separate from the current ML/AI paper core until a domain expansion milestone is explicitly chosen

### `paperswithcode`

- Live integration is blocked
- The attempted live path did not provide usable JSON
- Not part of active registry/reconcile/export/audit path
- Future use only as possible offline historical backfill after separate viability check
- The key lesson is: viability first, integration later

---

## 6. Trust model by metadata family

| metadata family | preferred sources / plane |
|---|---|
| title / abstract / categories / comment / journal_ref / pdf manifestation | primarily `arxiv`, with conservative support from paper enrichment sources |
| concepts / keywords / cited_by_count / referenced_ids | primarily `openalex_alignment`, with support from `semantic_scholar_alignment` |
| external identifier support | `semantic_scholar_alignment`, `openalex_alignment`, `crossref_alignment`, source-specific paper identifiers |
| publisher / publication_type / references_count / referenced_dois / license | primarily `crossref_alignment`, with support from `openalex_alignment` |
| venue / journal / conference stabilization | `openalex_alignment`, `crossref_alignment`, with support from `semantic_scholar_alignment` |
| repository / code / dataset / model / demo links | artifact layer: internal extraction, `github`, `huggingface_hub`; not bibliographic truth |
| popularity / trending / discovery signals | signal layer only; not canonical truth |

---

## 7. Connection model

ML Research Radar is not based on the assumption that all sources cover the whole corpus.

Instead:

- `arxiv` provides the backbone corpus
- enrichment layers attach where matching is possible
- canonical reconciliation merges partial overlap into one paper entity
- the corpus is expected to contain both single-source and multi-source canonical records
- artifact entities can exist with or without linked papers
- paper-artifact links can be strong, weak, candidate-only, or absent

This is intentional and expected behavior.

---

## 8. Artifact layer connection model

The artifact layer is a second data plane.

It should have its own entities and links:

- artifact entities
- artifact observations
- paper-artifact links

Artifacts may link to canonical papers through `canonical_id`, but this is not required.

Examples:

- a GitHub repository may be linked to one paper
- a Hugging Face model may be linked to multiple papers
- a dataset may have no paper link initially
- a paper may have no artifacts
- a paper may have multiple candidate artifact links with different confidence scores

Artifact evidence must preserve provenance:

- where the URL was found
- which source or field contained it
- whether it came from structured metadata or text extraction
- confidence score
- extraction/enrichment stage

---

## 9. Current status summary

### Active stable paper build

- `arxiv`
- `openalex_alignment`
- `semantic_scholar_alignment`
- `crossref_alignment`

### Viable candidate artifact sources

- `github`
- `huggingface_hub`

### Viable candidate paper/domain sources

- `acl_anthology`
- `openreview`
- `pubmed`
- `biorxiv`
- `medrxiv`

### Blocked / archived

- `paperswithcode` live integration

---

## 10. Design principle

The source matrix exists to make source behavior explicit.

ML Research Radar prefers:

- stable source roles
- field-dependent trust
- partial-overlap enrichment
- conservative canonical merge
- separate paper and artifact data planes
- explicit source viability checks before integration

over the assumption that every source should cover every paper equally or that every external source should modify canonical paper truth.