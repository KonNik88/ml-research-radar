# ML Research Radar — Data Contracts

## Purpose

This document defines the current data model for research papers in ML Research Radar.

The goal is to support:

- search and retrieval
- ranking
- metadata filtering
- analytics
- similarity search
- clustering
- graph construction
- citation/reference graph preparation
- future code/artifact linkage
- future product features built on canonical paper entities

The project uses a two-level semantic paper model plus an operational materialization identity:

1. **Document** — source-level normalized record
2. **CanonicalDocument** — reconciled merged paper entity
3. **source_observation_id** — deterministic physical identity for one selected source observation in Postgres

At the current stage, the project expands the **paper metadata layer first**, using arXiv as the current backbone source.

GitHub repositories and other external artifacts are modeled separately in the artifact evidence plane (`artifact_entities`, `artifact_observations`, `paper_artifact_links`). They are not `Document` or `CanonicalDocument` rows and must not redefine paper identity.

---

# 1. Model overview

## 1.1 `Document`
A normalized source-level paper record.

Represents:
- one source manifestation
- one normalized source record
- source-specific metadata after normalization
- source-level identity and provenance

## 1.1.1 Operational source-observation materialization

The semantic `Document` contract is materialized into Postgres with an explicit
`source_observation_id`.

```text
source_observation_id = deterministic physical row identity
doc_id = legacy normalized-document identifier
```

`source_observation_id` is not a third paper entity level. It is an operational
identity used to preserve every selected source observation without changing the
paper-level canonical model.

## 1.2 `CanonicalDocument`
A merged paper entity created by reconciliation.

Represents:
- one paper-level canonical entity
- merged identifiers
- merged metadata
- source provenance
- paper-level flags and quality signals
- current serving/retrieval corpus unit

## 1.3 Field-level canonical provenance contract

The project now has an explicit static contract for the selection semantics of
all 61 `CanonicalDocument` fields.

It describes:

```text
field candidates
selected scalar winners or co-winners
element-level union contributors
aggregate and boolean evidence
post-selection normalization
derived scores and flags
runtime-default fields
```

This contract is derived governance metadata. It is not a new entity level, does
not modify `CanonicalDocument`, and is not a reconcile input.

---

# 2. Identity fields

| Field | Purpose | Document | CanonicalDocument | Current Status |
|---|---|---:|---:|---|
| `source` | source name | yes | no | implemented |
| `source_record_id` | original id in source | yes | no | implemented |
| `source_record_url` | source page / record url | yes | no | implemented |
| `source_api_url` | API endpoint url | yes | no | implemented |
| `source_observation_id` | deterministic operational identity of one selected source observation | materialized | no | implemented operationally |
| `doc_id` | normalized-document id; legacy diagnostic, not globally unique across sources | yes | no | implemented |
| `doi` | stable bibliographic paper id | yes | yes | implemented |
| `arxiv_id` | arXiv identifier | yes | yes | implemented |
| `openalex_id` | OpenAlex identifier | yes | yes | implemented |
| `semantic_scholar_id` | Semantic Scholar identifier | yes | yes | implemented |
| `dblp_id` | DBLP identifier | yes | yes | implemented |
| `pmid` | PubMed identifier | yes | yes | implemented where available |
| `pmcid` | PubMed Central identifier | yes | yes | implemented where available |
| `canonical_id` | internal merged canonical id | no | yes | implemented |
| `canonical_url` | normalized canonical URL / manifestation URL | yes | no | implemented |
| `source_ids` | source → source id map | yes | yes | implemented |
| `external_ids` | richer external identifier map | yes | yes | implemented |

---

## 2.1 Operational identity constraints

Current Postgres materialization contract:

```text
source_documents.source_observation_id = PRIMARY KEY
source_documents.doc_id = NOT NULL, non-unique
canonical_source_links.source_observation_id = NOT NULL
canonical_source_links.source_observation_id
  → source_documents(source_observation_id) ON DELETE RESTRICT
canonical_source_links.doc_id = nullable
UNIQUE(canonical_id, source_observation_id)
```

The authoritative canonical-to-source link is `source_observation_id`. `doc_id`
is retained for backward-compatible diagnostics and must not be used to collapse
observations across source families.

---

# 3. Core content fields

| Field | Purpose | Document | CanonicalDocument | Current Status |
|---|---|---:|---:|---|
| `title` | main title | yes | yes | implemented |
| `abstract` | abstract text | yes | yes | implemented |
| `authors` | author names | yes | yes | implemented |
| `document_type` | source-level entity type | yes | no | implemented |
| `year` | normalized publication year | yes | yes | implemented |
| `published_at` | normalized publication timestamp | yes | yes | implemented |
| `publication_date` | normalized publication date field | yes | yes | implemented |
| `updated_source_at` | source update timestamp | yes | no | implemented |
| `updated_at` / `updated_record_at` | pipeline / canonical update timestamp | yes | yes | implemented |
| `created_at` | creation timestamp | yes | yes | implemented |

---

# 4. Taxonomy and topic fields

| Field | Purpose | Document | CanonicalDocument | Current Status |
|---|---|---:|---:|---|
| `primary_category` | main category | yes | yes | implemented |
| `categories` | category list | yes | yes | implemented |
| `concepts` | richer topic concepts | yes | yes | implemented |
| `keywords` | available / extracted keywords | yes | yes | implemented |
| `tags` | normalized topic/tag surface | yes | yes | implemented |

---

# 5. Links and accessibility fields

| Field | Purpose | Document | CanonicalDocument | Current Status |
|---|---|---:|---:|---|
| `landing_page_url` | main source page | yes | yes | implemented |
| `pdf_url` | direct PDF link | yes | yes | implemented |
| `repo_url` | primary repo link | yes | yes | implemented where available |
| `license` | document/content license | yes | yes | implemented |
| `open_access` | open manifestation availability | yes | yes | implemented |
| `is_open_access` | bibliographic OA evidence | yes | yes | implemented |
| `has_pdf` | PDF availability flag | yes | yes | implemented |

---

# 6. Citation / graph-ready fields

| Field | Purpose | Document | CanonicalDocument | Current Status |
|---|---|---:|---:|---|
| `cited_by_count` | citation count | yes | yes | implemented |
| `references_count` | number of references | yes | yes | implemented |
| `referenced_ids` | referenced work ids | yes | yes | implemented |
| `referenced_dois` | referenced DOIs | yes | yes | implemented |
| `referenced_arxiv_ids` | referenced arXiv ids | yes | yes | implemented |
| `citation_graph_available` | graph-ready marker | yes | yes | implemented |

---

# 7. Code / asset fields

| Field | Purpose | Document | CanonicalDocument | Current Status |
|---|---|---:|---:|---|
| `has_code_link` | whether code link exists | yes | yes | implemented |
| `code_links` | code links | yes | yes | implemented |
| `dataset_links` | dataset links | yes | yes | implemented |
| `model_links` | model/demo links | yes | yes | implemented |
| `has_dataset_link` | dataset flag | yes | yes | implemented |
| `has_model_link` | model flag | yes | yes | implemented |

---

# 8. Publication info fields

| Field | Purpose | Document | CanonicalDocument | Current Status |
|---|---|---:|---:|---|
| `venue` | normalized venue | yes | yes | implemented |
| `journal` | journal name | yes | yes | implemented |
| `conference` | conference name | yes | yes | implemented |
| `publisher` | publisher | yes | yes | implemented |
| `publication_type` | article / preprint / book-chapter etc. | yes | yes | implemented |
| `journal_ref` | source journal reference text | yes | yes | implemented |
| `comment` | source comment text | yes | yes | implemented |
| `language` | language | yes | yes | implemented |

---

# 9. Provenance and quality fields

| Field | Purpose | Document | CanonicalDocument | Current Status |
|---|---|---:|---:|---|
| `source_count` | number of merged source records | no | yes | implemented |
| `unique_source_count` | unique contributing source count | no | yes | implemented |
| `sources` | canonical provenance entries | no | yes | implemented |
| `doc_ids` | contributing source-level ids | no | yes | implemented |
| `ingested_at` | ingestion timestamp | yes | no | implemented |
| `raw_artifact_path` | raw artifact reference | yes | no | implemented |
| `raw_source_name` | raw source alias | yes | no | implemented |
| `metadata_completeness_score` | completeness heuristic | yes | yes | implemented |
| `pipeline_version` | pipeline version | yes | no | implemented |
| `stages` | stage status trail | yes | no | implemented |
| `reconciliation_key` | grouping key used for canonical merge | no | yes | implemented |

---

# 10. Current serving/storage notes

## 10.1 Source of truth
The canonical JSONL corpus remains the current source of truth.

## 10.2 Serving layer
Postgres currently acts as a materialized serving layer.

Current operational source-observation state:

```text
operational_db = ml_radar
source_documents = 88,178
canonical_source_links = 88,037
resolved_links = 88,037
non_contributing_selected_observations = 141
null_links = 0
dangling_links = 0
missing_selected_observations = 0
```

The previous 70,244-row legacy materialization is retained only as the rollback
database `ml_radar_pre_source_identity_v01_20260722t101620z`.

## 10.3 Retrieval layer
Retrieval artifacts remain file-based:

- lexical index
- dense embeddings
- hybrid retrieval logic

## 10.4 Current serving asymmetry
Current API backends are intentionally asymmetric:

- **file backend** = retrieval-oriented
- **db backend** = browse/filter + lexical search v1

This is the current transition state and is expected.

---

# 11. Reconciliation principles

## 11.1 Identity and grouping

Current grouping remains conservative:

```text
compatible DOI
→ arXiv base identity
→ normalized title + year fallback
```

Input identity preference is:

```text
direct DOI
→ external DOI
→ direct arXiv ID
→ external arXiv ID
→ normalized title + year
```

DOI conflict protection:

```text
one DOI associated with multiple explicit arXiv base IDs
→ split by arXiv base
→ isolate DOI-only rows as doi_conflict::<doi>
```

`canonical_id` remains the stable hash of `reconciliation_key`.

## 11.2 Scalar winner and ordered-first fields

Current executable rules include:

```text
title
= longest non-empty title; OpenAlex wins equal-length ties

abstract
= longest non-empty abstract; OpenAlex wins equal-length ties

doi
= first direct DOI in contributing observation order;
  otherwise first external DOI

arxiv_id
= arXiv-source direct ID;
  otherwise first direct arXiv ID;
  otherwise first external arXiv ID

openalex_id
= first direct OpenAlex ID;
  otherwise first external OpenAlex ID

pmid / pmcid / semantic_scholar_id / dblp_id / mag_id
= first non-empty value in contributing observation order

landing_page_url / pdf_url / primary_category
= first eligible value in contributing observation order

repo_url
= artifact-source priority followed by URL-length tie-break

license
= normalized license quality rank followed by source priority
```

`ordered_first` fields are deterministic relative to the ordered contributing
observation list. They must not be documented as universally source-priority
selected when the implementation uses input order.

## 11.3 Dates and numeric aggregates

```text
published_at
= minimum eligible timestamp

publication_date
= minimum eligible date

year
= minimum accepted year

updated_at
= maximum source updated_source_at value;
  naive timestamps are coerced to UTC

cited_by_count
= maximum eligible integer

references_count
= maximum eligible integer
```

When equal minima or maxima exist, field-level provenance may contain multiple
co-winning observations.

## 11.4 Ordered unions and merged maps

Deterministic ordered union with deduplication is used for:

```text
authors
categories
concepts
keywords
tags
referenced_ids
referenced_dois
referenced_arxiv_ids
code_links
dataset_links
model_links
doc_ids
```

Reference unions first apply the accepted bibliographic source ordering.

Merged identifier maps:

```text
source_ids
external_ids
```

preserve the first non-empty value for each identifier key. Their provenance is
therefore key-level, not one scalar winner for the whole map.

## 11.5 Publication metadata and normalization

```text
comment / journal_ref
= preferred string using comment source priority, length, and final value tie-break

venue / journal / conference
= preferred string selection followed by normalize_venue_fields

publisher
= preferred string using bibliographic source priority

publication_type
= preferred source value with non-preprint semantic override

language
= preferred string using default source priority
```

The final canonical value may differ from the selected source string when
normalization clears, copies, or derives a venue/journal/conference field.

## 11.6 Boolean evidence and derived fields

```text
open_access
= explicit true evidence;
  otherwise explicit false evidence;
  otherwise null

is_open_access
= non-arXiv bibliographic true/false evidence only

citation_graph_available / is_review / is_survey / is_withdrawn
= any positive evidence

is_preprint
= published/non-preprint override;
  otherwise explicit flags;
  otherwise publication-type inference

has_code_link
= explicit flag OR merged code_links OR repo_url

has_dataset_link
= explicit flag OR merged dataset_links

has_model_link
= explicit flag OR merged model_links
```

## 11.7 Row-level provenance, scores, and defaults

```text
sources
= one SourceLink per contributing normalized observation, preserving order

source_count
= len(contributing observations)

unique_source_count
= number of distinct non-empty source families

metadata_completeness_score
= recomputed heuristic over twelve merged canonical-field checks

created_at / updated_record_at
= CanonicalDocument construction-time defaults
```

`metadata_completeness_score` is not selected by maximum source value.
`created_at` and `updated_record_at` have no source observation winner.

## 11.8 Field-level evidence boundary

The accepted contract is:

```text
docs/field_level_canonical_provenance_contract_v0.1.md
```

Validation checkpoint:

```text
CanonicalDocument fields = 61
classified fields = 61
contract validator = 99 / 99
contract smoke tests = 8 passed
related reconciliation regression = 38 passed
contract_matches_current_reconciliation = true
```

The contract does not:

```text
change reconcile selectors
add provenance fields to CanonicalDocument
mutate canonical_documents.jsonl
add Postgres provenance tables
add API or Streamlit provenance surfaces
authorize full-corpus provenance generation
```

---

# 12. Current scope boundaries

## Included now
- paper entities
- source-level normalized documents
- deterministic source-observation materialization identity
- canonical merged paper entities
- static Field-Level Canonical Provenance Contract v0.1
- retrieval and serving metadata
- separate artifact entities, observations, and trusted paper-artifact links

## Explicitly postponed
- promotion of artifact metadata into canonical paper truth
- dedicated Paper–Artifact Graph API unless existing Artifact API surfaces prove insufficient
- chunk-level full-text entities
- NER/entity extraction layer
- LLM summaries and RAG-specific chunk contracts

---

# 13. Design principle

ML Research Radar is centered on stable canonical paper entities.

The data contract prioritizes:

- clear identity boundaries
- source-aware normalization
- provenance-preserving merge
- search/retrieval compatibility
- future graph/artifact extensibility

over a flat one-record-per-source design.

# 14. Current operational checkpoint

```text
Source Observation Materialization Operational Promotion v0.1 = completed
operational database = ml_radar
source_observation_id primary-key materialization = active
legacy rollback database retained = true
canonical corpus changed = false
retrieval artifacts changed = false
Qdrant changed = false
Artifact API contract changed = false
```

The **Field-Level Canonical Provenance Contract v0.1** is now implemented and
green:

```text
canonical fields classified = 61 / 61
validator = 99 / 99
smoke tests = 8 passed
related regression = 38 passed
```

The next separate slice is **Field-Level Canonical Provenance Evidence Builder
v0.1**. It may emit bounded derived evidence for synthetic fixtures and selected
audit samples, but it must not redefine `CanonicalDocument`, modify reconcile,
or add a new serving truth.
