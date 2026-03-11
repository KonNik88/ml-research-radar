# ML Research Radar — Data Contracts

## Purpose

This document defines the planned data model for research papers in ML Research Radar.

The goal is to support:

- search and retrieval
- ranking
- metadata filtering
- analytics
- similarity search
- clustering
- graph construction
- future citation graph features
- future implementation finder and code linkage

The project uses a two-level paper model:

1. **Document** — source-level normalized record  
2. **CanonicalDocument** — reconciled merged paper entity

At the current stage, the project expands the **paper metadata layer first**, using arXiv as the main source for the first implementation wave.

GitHub repositories and other external sources will be added later as separate entities.

---

# Field Registry

## Identity fields

| Field | Purpose | Source-level (`Document`) | Canonical (`CanonicalDocument`) | Phase | Status |
|---|---|---:|---:|---|---|
| source | source name | yes | no | B1 | planned |
| source_record_id | original id in source | yes | no | B1 | planned |
| doi | stable paper id | yes | yes | B1 | planned |
| arxiv_id | arXiv identifier | yes | yes | B1 | planned |
| openalex_id | OpenAlex identifier | yes | yes | B2 | planned |
| canonical_id | internal merged id | no | yes | existing | implemented |
| source_ids | map of source → source id | no | yes | B1 | planned |

---

## Core content fields

| Field | Purpose | Document | CanonicalDocument | Phase | Status |
|---|---|---:|---:|---|---|
| title | main title | yes | yes | existing | implemented |
| abstract | abstract text | yes | yes | existing | implemented |
| authors | author names | yes | yes | existing | implemented |
| publication_year | basic year field | yes | yes | B1 | planned |
| publication_date | normalized publication date | yes | yes | B1 | planned |
| updated_date | last update date | yes | yes | B1 | planned |

---

## Taxonomy and topic fields

| Field | Purpose | Document | CanonicalDocument | Phase | Status |
|---|---|---:|---:|---|---|
| primary_category | main category | yes | yes | existing/B1 normalize | partial |
| categories | category list | yes | yes | existing | implemented |
| concepts | richer source concepts/topics | yes | yes | B1 | planned |
| keywords | extracted/available keywords | yes | yes | B1 | planned |
| tags | normalized tags | yes | yes | B1 | planned |

---

## Links and accessibility fields

| Field | Purpose | Document | CanonicalDocument | Phase | Status |
|---|---|---:|---:|---|---|
| landing_page_url | source page url | yes | yes | B1 | planned |
| pdf_url | direct pdf link | yes | yes | B1 | planned |
| license | document license | yes | yes | B1 | planned |
| open_access | OA flag | yes | yes | B1 | planned |

---

## Citation / graph-ready fields

| Field | Purpose | Document | CanonicalDocument | Phase | Status |
|---|---|---:|---:|---|---|
| cited_by_count | citation count | yes | yes | B1 | planned |
| references_count | number of references | yes | yes | B1 | planned |
| referenced_ids | referenced work ids | yes | yes | B1 | planned |
| referenced_dois | referenced DOIs | yes | yes | B3 | planned |
| referenced_arxiv_ids | referenced arXiv ids | yes | yes | B3 | planned |
| citation_graph_available | graph-ready marker | yes | yes | B3 | planned |

---

## Code / assets fields

| Field | Purpose | Document | CanonicalDocument | Phase | Status |
|---|---|---:|---:|---|---|
| has_code_link | whether code link exists | yes | yes | B1 | planned |
| code_links | list of code links | yes | yes | B1 | planned |
| dataset_links | dataset references | yes | yes | B3 | planned |
| model_links | model/demo links | yes | yes | B3 | planned |

---

## Publication info fields

| Field | Purpose | Document | CanonicalDocument | Phase | Status |
|---|---|---:|---:|---|---|
| venue | normalized venue name | yes | yes | B2 | planned |
| journal | journal name | yes | yes | B2 | planned |
| conference | conference name | yes | yes | B2 | planned |
| publisher | publisher | yes | yes | B2 | planned |
| publication_type | article / preprint / proceedings etc. | yes | yes | B2 | planned |

---

## Provenance and quality fields

| Field | Purpose | Document | CanonicalDocument | Phase | Status |
|---|---|---:|---:|---|---|
| source_count | number of merged sources | no | yes | existing | implemented |
| sources | merged source provenance | no | yes | existing/B1 expand | partial |
| ingested_at | ingestion timestamp | yes | no | B1 | planned |
| source_updated_at | source update timestamp | yes | yes | B2 | planned |
| raw_source_name | raw source alias | yes | no | B2 | planned |
| metadata_completeness_score | completeness heuristic | yes | yes | B3 | planned |

---

# Phase Plan

## Phase B1 — Core paper metadata expansion

Fields:

- source
- source_record_id
- doi
- arxiv_id
- source_ids
- title
- abstract
- authors
- publication_year
- publication_date
- updated_date
- primary_category
- categories
- concepts
- keywords
- tags
- landing_page_url
- pdf_url
- license
- open_access
- cited_by_count
- references_count
- referenced_ids
- has_code_link
- code_links
- source_count
- sources

Goal:

- expand paper contracts
- implement arXiv-side extraction for available fields
- extend reconcile rules
- preserve backward compatibility with retrieval/API where possible

---

## Phase B2 — Publication and provenance enrichment

Fields:

- openalex_id
- venue
- journal
- conference
- publisher
- publication_type
- source_updated_at
- raw_source_name

Goal:

- improve publication analytics
- improve filtering
- prepare for richer cross-source reconciliation

---

## Phase B3 — Graph/product/quality enrichment

Fields:

- referenced_dois
- referenced_arxiv_ids
- citation_graph_available
- dataset_links
- model_links
- metadata_completeness_score

Goal:

- make corpus graph-ready
- support future analytics/widgets/product features

---

# Reconciliation Principles

## Identity priority

1. DOI
2. arXiv id
3. future fallback strategies (not in current phase)

## Merge rules

### Prefer non-empty values for:
- title
- abstract
- publication_date
- pdf_url
- landing_page_url

### Union + deduplicate for:
- authors
- categories
- concepts
- keywords
- tags
- referenced_ids
- code_links
- sources

### Prefer max value for:
- cited_by_count
- references_count

### Preserve provenance always:
- source_count
- sources
- source_ids

---

# Notes

- GitHub repositories are intentionally excluded from the current phase.
- Repository ingestion will be introduced later as a separate entity layer.
- The current target corpus size after paper metadata expansion is approximately **1000–2000 canonical documents**.