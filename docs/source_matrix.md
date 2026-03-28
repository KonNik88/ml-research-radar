# Source Matrix

## Purpose

This document defines the current source landscape of ML Research Radar:

- which sources are used
- how they are connected
- what metadata they contribute
- what role they play during canonical reconciliation
- how much they are trusted for different metadata families

The goal is to keep source behavior explicit and stable as the project grows.

---

## 1. Current source roles

| source | mode | match basis | primary role | strong fields | weak / not trusted fields | status |
|---|---|---|---|---|---|---|
| `arxiv` | backbone | arXiv id / DOI / title fallback | corpus backbone, preprint manifestation, main text source | title, abstract, authors, categories, arxiv_id, pdf_url, comment, journal_ref | publisher truth, venue truth, publication_type truth, citation graph | active |
| `openalex_alignment` | alignment | DOI | semantic enrichment + citation metadata | concepts, keywords, cited_by_count, referenced_ids, venue, journal, publisher, OA hints | publication_type can be noisy, code/artifact links limited | active |
| `semantic_scholar_alignment` | alignment | DOI / arXiv id | auxiliary bibliographic + citation support | external identifiers, cited_by_count, venue hints, title/author cross-check | journal can be noisy, references coverage weak, OA limited | active |
| `crossref_alignment` | alignment | DOI | bibliographic stabilizer + references enrichment | publisher, publication_type, references_count, referenced_dois, license | abstract often missing, semantic metadata weak, cited_by_count weak | active |
| `paperswithcode_alignment` | alignment | DOI / arXiv id | artifact enrichment | repo_url, code_links, dataset_links, model_links, tasks, benchmark-style metadata | publisher, venue, publication_type, citation counts | planned / experimental |

---

## 2. Current operational pipeline

The current canonical build is based on:

1. `arxiv` as corpus backbone
2. `openalex_alignment` for DOI-aligned semantic enrichment
3. `semantic_scholar_alignment` for auxiliary bibliographic support
4. `crossref_alignment` for bibliographic and references enrichment

Planned next addition:

5. `paperswithcode_alignment` for code and artifact enrichment

---

## 3. Source-specific notes

### `arxiv`
- Main backbone of the current corpus
- Provides the majority of current papers
- Primary source for abstract, categories, arXiv identifiers, and PDF links
- Typically represents a preprint manifestation rather than final bibliographic manifestation

### `openalex_alignment`
- Current strongest semantic enrichment layer
- Main source for concepts, keywords, and cited-by metadata
- Also contributes venue/journal/publisher metadata for DOI-covered subset
- Useful for OA hints and graph-oriented identifiers

### `semantic_scholar_alignment`
- Useful as supporting bibliographic and citation layer
- Helps recover extra identifiers such as DBLP / CorpusId / arXiv links
- Should be treated as secondary support rather than primary metadata authority

### `crossref_alignment`
- Main bibliographic stabilization layer for DOI-covered subset
- Best current source for `publication_type`, `publisher`, `references_count`, `referenced_dois`, and part of license information
- Important for future citation/reference graph construction

### `paperswithcode_alignment`
- Planned artifact enrichment layer
- Intended to enrich canonical papers with repository links, code resources, datasets, and model-related artifacts
- Must not be treated as authoritative source for bibliographic fields

---

## 4. Trust model by metadata family

| metadata family | preferred sources |
|---|---|
| title / abstract / categories / comment / journal_ref / pdf manifestation | `arxiv` |
| concepts / keywords / cited_by_count / referenced_ids | `openalex_alignment` |
| external identifier support | `semantic_scholar_alignment`, `openalex_alignment` |
| publisher / publication_type / references_count / referenced_dois / license | `crossref_alignment` |
| repo / code / dataset / model links | `paperswithcode_alignment` |
| venue/journal/conference stabilization | `crossref_alignment`, `openalex_alignment`, with support from `semantic_scholar_alignment` |

---

## 5. Connection model

ML Research Radar is not based on the assumption that all sources cover the whole corpus.

Instead:

- `arxiv` provides the backbone corpus
- enrichment layers attach where matching is possible
- canonical reconciliation merges partial overlap into one paper entity
- the corpus is expected to contain both single-source and multisource canonical records

This is intentional and expected behavior.

---

## 6. Current status summary

### Currently in active canonical build
- `arxiv`
- `openalex_alignment`
- `semantic_scholar_alignment`
- `crossref_alignment`

### Not yet part of stable core
- `paperswithcode_alignment`

### Explicitly postponed
- GitHub / repository entity layer as a separate non-paper entity system

---

## 7. Design principle

The source matrix exists to make source behavior explicit.

ML Research Radar prefers:

- stable source roles
- field-dependent trust
- partial-overlap enrichment
- conservative canonical merge

over the assumption that every source should cover every paper equally.