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

## 1.4 Field-level canonical provenance evidence

The bounded evidence layer materializes explanatory records for selected audit
samples without adding fields to `Document` or `CanonicalDocument`.

One evidence record represents:

```text
canonical_id + field_name
```

Key evidence identities and references:

```text
record_id
= deterministic derived evidence identity

canonical_id
= existing paper identity

source_observation_id
= contributing source-observation identity referenced by candidates,
  selected/co-winning observations, and element-level contributors
```

The evidence record may contain:

```text
canonical_value
recomputed_value
comparison_status
strategy_kind
candidate_count
selected_source_observation_ids
contributing_source_observation_ids
candidates
elements
transformations
selection_reason
caveats
```

This is not another semantic paper entity level. It is bounded, derived,
read-only explanatory output and must not be used as a reconciliation input.

## 1.5 Field-level canonical provenance evidence review

The review layer is not another data entity. It is a read-only validation
contract over two bounded evidence packages plus the accepted reconciliation
audit package.

It compares:

```text
semantic file hashes
paper and field key sets
record content
strategy-family coverage
accepted counts
audit package identity
package safety flags
```

The review report may identify semantic drift even when a modified package has
fresh internally consistent checksums. It never changes an evidence record,
canonical document, or source observation.

---


## 1.6 Field-level canonical provenance evidence checkpoint

The checkpoint is not another entity, data contract, or materialized record
type. It is a fail-closed read-only validation report over the accepted:

```text
field-level contract
bounded evidence package validation
semantic review
```

Accepted checkpoint state:

```text
checkpoint validator = 35 / 35
checkpoint smoke tests = 9 passed
required_failed_count = 0
field_level_provenance_line_complete = true
bounded_evidence_checkpoint_ready = true
```

The checkpoint preserves all existing identity domains:

```text
canonical_id = paper identity
source_observation_id = source-row identity
record_id = derived field-evidence identity
```

It adds no field to `Document` or `CanonicalDocument`, creates no Postgres
entity, and cannot be used as a reconcile input or serving truth.

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

## 11.8 Field-level contract, bounded evidence, and review boundary

Accepted contract:

```text
docs/field_level_canonical_provenance_contract_v0.1.md
```

Implemented bounded evidence package:

```text
docs/field_level_canonical_provenance_evidence_v0.1.md
scripts/validation/build_field_level_canonical_provenance_evidence.py
scripts/validation/check_field_level_canonical_provenance_evidence.py
```

Validation checkpoint:

```text
CanonicalDocument fields = 61
classified fields = 61
contract validator = 99 / 99
contract smoke tests = 8 passed

bounded canonical papers = 12
contributing source observations = 33
canonical source links = 33
unmatched source links = 0
field evidence records = 732
source-reconstructable matches = 708
runtime-default records = 24
required value mismatches = 0
evidence validator = 34 / 34
evidence smoke tests = 16 passed
builder-slice related regression = 45 passed

review validator = 58 / 58
review smoke tests = 7 passed
field-level evidence block = 23 passed
current related regression = 52 passed
strategy families = 14
semantic file differences = 0
record-key differences = 0
record-content differences = 0

checkpoint validator = 35 / 35
checkpoint smoke tests = 9 passed
checkpoint required_failed_count = 0
field_level_provenance_line_complete = true
bounded_evidence_checkpoint_ready = true
```

Review baseline:

```text
field_evidence.jsonl sha256
= d3a42644e51854226343e98f048856a16b2f9cd52289bb3dd6e5676f751077b0

paper_summary.jsonl sha256
= dc3d3ab43d4bc3bf82c14593f0b274f8989efbd7bd79694c5a397f7b58d7356d

data_quality_summary.json sha256
= 825d49a0f5b1b95be39a6bff77a000adc03842c8290c758716a202b04bb52236
```

Evidence semantics:

```text
61 records are emitted per sampled canonical paper
record_id is deterministic derived evidence identity
canonical_id remains paper identity
source_observation_id remains source-row identity
selected IDs must belong to the contributing observation set
union/map evidence is element/key level
equal minima/maxima may preserve multiple co-winners
created_at and updated_record_at are runtime-default records
canonical/recomputed mismatch is diagnostic and never repairs canonical truth
```

The contract, bounded evidence, semantic review, and final checkpoint do not:

```text
change reconcile selectors
add provenance fields to CanonicalDocument
mutate canonical_documents.jsonl
add Postgres provenance tables
add API or Streamlit provenance surfaces
authorize full-corpus provenance generation
become reconcile inputs or serving truth
allow package checksums to substitute for semantic-drift comparison
```

---

# 12. Current scope boundaries

## Included now
- paper entities
- source-level normalized documents
- deterministic source-observation materialization identity
- canonical merged paper entities
- static Field-Level Canonical Provenance Contract v0.1
- bounded Field-Level Canonical Provenance Evidence v0.1
- Field-Level Canonical Provenance Evidence Review & Regression Hardening v0.1
- Field-Level Canonical Provenance Evidence Checkpoint v0.1
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

The **Field-Level Canonical Provenance Contract v0.1**, bounded
**Field-Level Canonical Provenance Evidence v0.1**,
**Field-Level Canonical Provenance Evidence Review & Regression Hardening v0.1**,
and **Field-Level Canonical Provenance Evidence Checkpoint v0.1** are
implemented and green:

```text
canonical fields classified = 61 / 61
contract validator = 99 / 99
contract smoke tests = 8 passed

bounded papers = 12
contributing source observations = 33
field records = 732
source-reconstructable matches = 708
runtime-default records = 24
value mismatches = 0
evidence validator = 34 / 34
evidence smoke tests = 16 passed

review validator = 58 / 58
review smoke tests = 7 passed
field-level evidence block = 23 passed
related regression = 52 passed
strategy families = 14
semantic file differences = 0
record-key differences = 0
record-content differences = 0

checkpoint validator = 35 / 35
checkpoint smoke tests = 9 passed
required_failed_count = 0
field_level_provenance_line_complete = true
bounded_evidence_checkpoint_ready = true
```

The bounded evidence output explains the current merge but does not redefine
`CanonicalDocument`, modify reconcile, or add a serving truth. The review layer
pins semantic parity between accepted directory- and ZIP-driven runs, and the
final checkpoint closes the bounded line. Any later full-corpus, Postgres,
API/UI, publication, or reconcile-input provenance design requires a separate
accepted architecture slice.
