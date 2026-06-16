# Source Matrix

## Purpose

This document defines the current source landscape of ML Research Radar:

- which sources are used
- which sources are candidate sources
- how sources are connected
- what metadata they contribute
- what role they play during canonical reconciliation
- how much they are trusted for different metadata families
- which sources belong to the paper plane, artifact plane, signal plane, or future full-text plane

ML Research Radar is a paper-centric canonical corpus platform, but not every source is a paper source.

The project explicitly separates:

1. paper sources
2. artifact sources
3. signal sources
4. future full-text/chunk sources

This separation prevents repositories, models, datasets, demos, reviews, trend signals, or full-text chunks from being accidentally treated as bibliographic paper truth.

---

## Operational onboarding process

This matrix defines source roles, planes, status, and trust semantics.

For the operational procedure used to add a new source safely, see:

```text
docs/source_onboarding_v1.md
```

The onboarding document defines the required gates:

1. source contract
2. viability check
3. real-data smoke
4. candidate normalized output or provider metadata snapshot
5. source/provider audit
6. candidate reconcile impact check, for paper sources
7. export / materialization checks
8. DoD / promotion decision

This matrix answers what each source is allowed to contribute. The onboarding contract answers how a new source becomes safe enough to integrate.

---

## 1. Source taxonomy v2

### 1.1 Paper sources

Paper sources provide paper-level metadata and may contribute to canonical paper entities after validation.

They can contribute to:

- title
- abstract
- authors
- DOI
- arXiv id
- PMID
- ACL id
- OpenReview id
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
- `acl_anthology`

Candidate paper/domain sources after viability checks:

- `openreview`
- `pubmed`
- `biorxiv`
- `medrxiv`

### 1.2 Artifact sources

Artifact sources provide repositories, code, models, datasets, demos, project pages, videos, and other non-paper research artifacts.

They must not be treated as paper-level truth sources.

They may contribute to:

- repository entities
- model entities
- dataset entities
- demo/project URLs
- artifact metadata
- possible paper-artifact links
- code/dataset/model convenience fields
- provider metadata such as stars, downloads, likes, tags, license, timestamps, status

Current operational artifact enrichment providers:

- `github`
- `huggingface_hub`

Other artifact providers extracted from URLs but not deeply enriched yet:

- `zenodo`
- `figshare`
- `youtube`
- `gitlab`
- `bitbucket`
- `codeberg`
- `kaggle`
- `generic`

Archived or blocked artifact source:

- `paperswithcode`

Papers with Code live integration is blocked because the upstream live path did not provide usable JSON. Future Papers with Code use may only be reconsidered as offline historical backfill after a separate viability check.

### 1.3 Signal sources

Signal sources provide popularity, trending, discovery, ranking, or prioritization signals.

They must not directly modify canonical paper truth.

Possible future signal sources:

- Hugging Face Trending Papers
- GitHub trending
- news/social/trend sources
- other discovery surfaces

Signal sources can influence ranking, alerts, or discovery only in explicit ranking/discovery layers.

---

## 2. Current active paper source roles

| source | plane | mode | match basis | primary role | strong fields | weak / not trusted fields | status |
|---|---|---|---|---|---|---|---|
| `arxiv` | paper | backbone | arXiv id / DOI / title fallback | corpus backbone, preprint manifestation, main text source | title, abstract, authors, categories, arxiv_id, pdf_url, comment, journal_ref | publisher truth, final venue truth, final publication type truth, citation graph | active |
| `openalex_alignment` | paper | alignment | DOI | semantic enrichment + citation metadata | concepts, keywords, cited_by_count, referenced_ids, venue, journal, publisher, OA hints | publication_type can be noisy, artifact links limited | active |
| `semantic_scholar_alignment` | paper | alignment | DOI / arXiv id | auxiliary bibliographic + citation support | external identifiers, cited_by_count, venue hints, title/author cross-check | journal can be noisy, reference coverage can be uneven, OA metadata limited | active |
| `crossref_alignment` | paper | alignment | DOI | bibliographic stabilizer + references enrichment | publisher, publication_type, references_count, referenced_dois, license, publication date | abstract often missing, semantic metadata weak, cited_by_count weak | active |
| `acl_anthology` | paper | domain source | ACL id / DOI / title-year fallback | NLP and computational-linguistics paper metadata | ACL id, title, authors, year, venue, landing page, PDF URL, DOI and abstract where available | citation metadata and broad cross-domain coverage are limited | active / promoted |

Current stable canonical paper build:

```text
canonical corpus source of truth = data/analytics/reconciled/canonical_documents.jsonl
canonical documents = 60954
multi-source canonical documents = 9192
active stable paper sources = 5
ACL-family canonical documents = 957
ACL-only canonical documents = 954
existing canonical papers enriched with ACL provenance = 3
DoD passed = true
```

---

## 3. Current operational artifact provider roles

| source | plane | access mode | primary role | expected contribution | status |
|---|---|---|---|---|---|
| `github` | artifact | REST API | repository/artifact enrichment | repositories, topics, stars, forks, licenses, repo metadata, status, possible paper links | operational enrichment provider |
| `huggingface_hub` | artifact | Hub API / optional Python client | model/dataset/space enrichment | models, datasets, spaces, cards, tags, downloads, likes, pipeline tags, license, status, possible paper links | operational enrichment provider |

### 3.1 GitHub

GitHub is an artifact source, not a paper source.

Allowed contributions:

- repository artifact entities
- repository metadata
- owner/name
- description
- topics
- license
- stars/forks
- archived/private/disabled status
- timestamps
- `metadata.github.*`

Not allowed:

- changing canonical paper title, authors, abstract, venue, publisher, citation counts, references, publication type or paper identity
- ranking papers by GitHub stars as canonical paper quality

Current accepted baseline:

```text
github_entities_count = 5953
metadata_rows_count = 5953
found_count = 5339
not_found_count = 614
forbidden_count = 0
rate_limited_count = 0
error_count = 0
ok = true
```

### 3.2 Hugging Face Hub

Hugging Face Hub is an artifact ecosystem source, not a paper source.

Allowed contributions:

- model artifact entities
- dataset artifact entities
- space artifact entities
- tags
- downloads
- likes
- license
- pipeline tag
- library name
- card metadata
- provider status
- `metadata.huggingface.*`

Not allowed:

- changing canonical paper title, authors, abstract, venue, publisher, citation counts, references, publication type or paper identity
- treating model/dataset/space popularity as canonical paper quality

Current accepted baseline:

```text
huggingface_entities_count = 100
metadata_rows_count = 100
found_count = 77
forbidden_count = 2
skipped_invalid_external_id_count = 21
rate_limited_count = 0
error_count = 0
ok = true
```

`forbidden` and `skipped_invalid_external_id` are diagnostic states. They do not invalidate the artifact layer.

---

## 4. Candidate source roles after viability checks

| source | plane | access mode | primary role | expected contribution | status |
|---|---|---|---|---|---|
| `openreview` | paper | API v2 / Python client | ML conference paper source | submissions, venues, OpenReview ids, titles, authors, abstracts | viable candidate |
| `pubmed` | paper | NCBI E-utilities | biomedical/domain paper source | PMID, DOI, biomedical titles/abstracts, publication metadata | viable candidate; later domain expansion |
| `biorxiv` | paper | public API | biomedical preprint source | preprints, DOI, title, abstract, authors, category/date metadata | viable candidate; later domain expansion |
| `medrxiv` | paper | public API | medical preprint source | preprints, DOI, title, abstract, authors, category/date metadata | viable candidate; later domain expansion |
| `paperswithcode` | artifact | archived-only / blocked live | historical artifact source only if reconsidered | repo/code/dataset/model links from offline data only | blocked / archived |

---

## 5. Source-specific notes

### `arxiv`

- Main backbone of the current corpus.
- Provides the majority of current papers.
- Primary source for abstract, categories, arXiv identifiers, PDF links, comments and journal reference strings.
- Represents preprint/open manifestation semantics.
- Does not automatically define final bibliographic publication type.

### `openalex_alignment`

- Current strongest semantic enrichment layer.
- Main source for concepts, keywords, cited-by metadata, OpenAlex identifiers and venue/publisher hints.
- Useful for OA hints and graph-oriented identifiers.
- Strong for semantic metadata, but field-level noise still requires conservative merge rules.

### `semantic_scholar_alignment`

- Auxiliary bibliographic and citation layer.
- Useful for DOI/arXiv/DBLP/CorpusId/MAG-style identifier support.
- Helps recover citation/reference metadata and venue hints.
- Should be treated as secondary support rather than primary bibliographic authority.

### `crossref_alignment`

- Main bibliographic stabilization layer for DOI-covered subset.
- Strongest current source for publisher, publication type, publication dates, references_count, referenced_dois and license hints.
- Important for future citation/reference graph construction.
- License information still needs conservative normalization.

### `github`

- Operational artifact enrichment provider.
- Uses extracted artifact entities as input.
- Writes provider metadata snapshots under `data/enriched/github_artifacts/`.
- Merges metadata into `artifact_entities.metadata.github` during artifact export.
- Optional in DoD and refresh pipeline because the GitHub API is a live external dependency.

### `huggingface_hub`

- Operational artifact enrichment provider for extracted model/dataset/space URLs.
- Uses extracted artifact entities as input.
- Writes provider metadata snapshots under `data/enriched/huggingface_artifacts/`.
- Merges metadata into `artifact_entities.metadata.huggingface` during artifact export.
- Optional in DoD and refresh pipeline because Hugging Face Hub is a live external dependency.

### `acl_anthology`

- Active promoted paper/domain source for NLP and computational linguistics.
- Integrated through deterministic bulk metadata ingestion and the standard candidate reconcile, audit and explicit promotion lifecycle.
- Current accepted checkpoint contains 957 ACL-family canonical documents: 954 ACL-only documents and 3 existing canonical papers enriched with ACL provenance.
- ACL remains part of the paper plane and does not bypass canonical reconciliation.

### `openreview`

- Candidate paper source for ML conference submissions and accepted papers.
- API/client behavior may differ between venues and years.
- Should first be implemented as candidate ingestion with clear venue/year scope.
- Reviews and decisions are separate product layers and should not be mixed into basic paper truth prematurely.

### `pubmed`

- Biomedical/domain paper source.
- PMID-first identity with DOI where available.
- Useful for biomedical expansion, not immediate ML core expansion.

### `biorxiv` / `medrxiv`

- Biomedical/medical preprint sources.
- Useful for domain expansion.
- Should remain separate from the current ML/AI paper core until a domain expansion milestone is explicitly chosen.

### `paperswithcode`

- Live integration is blocked.
- The attempted live path did not provide usable JSON.
- Not part of active registry/reconcile/export/audit path.
- Future use only as possible offline historical backfill after separate viability check.

---

## 6. Trust model by metadata family

| metadata family | preferred sources / plane |
|---|---|
| title / abstract / categories / comment / journal_ref / PDF manifestation | primarily `arxiv`, with conservative support from paper enrichment sources |
| concepts / keywords / cited_by_count / referenced_ids | primarily `openalex_alignment`, with support from `semantic_scholar_alignment` |
| external identifier support | `semantic_scholar_alignment`, `openalex_alignment`, `crossref_alignment`, source-specific paper identifiers |
| publisher / publication_type / references_count / referenced_dois / license | primarily `crossref_alignment`, with support from `openalex_alignment` |
| venue / journal / conference stabilization | `openalex_alignment`, `crossref_alignment`, with support from `semantic_scholar_alignment` |
| repository / code / dataset / model / demo links | artifact layer: internal extraction, GitHub enrichment, Hugging Face enrichment, provider URLs; not bibliographic truth |
| popularity / trending / discovery signals | signal layer only; not canonical truth |

---

## 7. Connection model

ML Research Radar is not based on the assumption that all sources cover the whole corpus.

Instead:

- `arxiv` provides the backbone corpus.
- enrichment layers attach where matching is possible.
- canonical reconciliation merges partial overlap into one paper entity.
- the corpus is expected to contain both single-source and multi-source canonical records.
- artifact entities can exist with or without linked papers.
- paper-artifact links can be strong, weak, candidate-only, or absent.

This is intentional and expected behavior.

---

## 8. Artifact layer connection model

The artifact layer is a second data plane.

It has its own entities and links:

- artifact entities
- artifact observations
- paper-artifact links
- provider enrichment snapshots

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
- `acl_anthology`

### Operational artifact enrichment providers

- `github`
- `huggingface_hub`

### Viable candidate paper/domain sources

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
- provider enrichment snapshots before DB/API exposure

The project does not assume that every source should cover every paper equally or that every external source should modify canonical paper truth.
