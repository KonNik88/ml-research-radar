# Source Matrix

## Purpose

This document defines the current source landscape of ML Research Radar:
- which sources are used,
- how they are connected,
- what metadata they contribute,
- and what role they play during canonical reconciliation.

The goal is to keep source behavior explicit and stable as the project grows.

---

## Source roles

| source | mode | match basis | primary role | strong fields | weak / not trusted fields | status |
|---|---|---|---|---|---|---|
| arxiv | backbone | arxiv_id / DOI / title | corpus backbone, preprint manifestation, core text source | title, abstract, authors, categories, arxiv_id, pdf_url, comment, journal_ref | publisher, venue truth, publication_type truth, citation graph | active |
| openalex_alignment | alignment | DOI | semantic enrichment + citation metadata | concepts, keywords, cited_by_count, referenced_ids, venue, journal, publisher, OA hints | publication_type can be noisy, repo/code links limited | active |
| semantic_scholar_alignment | alignment | DOI / arxiv_id | auxiliary bibliographic + citation support | external_ids, cited_by_count, venue hints, title/author cross-check | journal can be noisy, references coverage weak, OA limited | active |
| crossref_alignment | alignment | DOI | bibliographic stabilizer + references enrichment | publisher, publication_type, references_count, referenced_dois, license | abstract often missing, semantic metadata weak, cited_by_count weak | active |
| paperswithcode_alignment | alignment | DOI / arxiv_id | artifact enrichment | repo_url, code_links, dataset_links, model_links, tasks, benchmark-related metadata | publisher, venue, publication_type, citation counts | planned |

---

## Current operational pipeline

Current canonical build is based on:

1. `arxiv` as corpus backbone
2. `openalex_alignment` for DOI-aligned semantic enrichment
3. `semantic_scholar_alignment` for auxiliary bibliographic support
4. `crossref_alignment` for bibliographic and references enrichment

Planned next addition:
5. `paperswithcode_alignment` for code and artifact enrichment

---

## Source-specific notes

### arxiv
- Main corpus backbone
- Provides the majority of current documents
- Primary source for abstract, categories, arXiv identifiers, and PDF links
- Often represents preprint manifestation rather than final published manifestation

### openalex_alignment
- Current strongest semantic enrichment layer
- Main source for concepts, keywords, and cited-by metadata
- Also contributes venue/journal/publisher metadata for DOI-covered subset

### semantic_scholar_alignment
- Useful as supporting bibliographic and citation layer
- Helps recover extra identifiers such as DBLP / CorpusId / arXiv links
- Should be treated as secondary support rather than primary metadata authority

### crossref_alignment
- Main bibliographic stabilization layer for DOI-covered subset
- Best source for publication_type, publisher, references_count, referenced_dois, and some license information
- Important for future citation/reference graph construction

### paperswithcode_alignment
- Planned artifact enrichment source
- Will be used to enrich canonical papers with repository links, code resources, datasets, and model-related artifacts
- Will not be treated as authoritative source for bibliographic fields

---

## Trust model by metadata family

| metadata family | preferred sources |
|---|---|
| title / abstract / categories / comment / journal_ref | arxiv |
| concepts / keywords / cited_by_count / referenced_ids | openalex_alignment |
| external identifiers support | semantic_scholar_alignment, openalex_alignment |
| publisher / publication_type / references_count / referenced_dois / license | crossref_alignment |
| repo / code / dataset / model links | paperswithcode_alignment |

---

## Design principle

ML Research Radar is not based on the assumption that all sources cover the whole corpus.

Instead:
- `arxiv` provides the backbone corpus,
- enrichment layers attach where matching is possible,
- canonical reconciliation merges partial overlap into one paper entity.

This is intentional and expected behavior.