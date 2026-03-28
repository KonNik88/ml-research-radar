# Merge Policy

## Purpose

This document defines how source-level normalized documents are merged into canonical paper entities.

The merge policy is the core quality mechanism of ML Research Radar. It controls:
- identity resolution,
- field-level source priorities,
- conflict resolution,
- and semantic normalization for important metadata fields.

---

## 1. Identity resolution

Canonical grouping is currently based on the following priority:

1. DOI
2. external DOI
3. arXiv id
4. external arXiv id
5. normalized title + year fallback

### Notes
- DOI is the strongest reconciliation key
- arXiv id is a secondary identity path
- title + year is fallback-only and should be treated conservatively
- arXiv version normalization remains a known technical debt area (`2412.19245` vs `2412.19245v1`)

---

## 2. Source priority philosophy

Different metadata families have different trusted sources.

The system does **not** assume one source is best for all fields.

Instead, source priority is field-dependent.

---

## 3. Field-level merge priorities

### 3.1 Backbone content fields
Preferred source:
1. arxiv
2. openalex_alignment
3. semantic_scholar_alignment
4. crossref_alignment

Applies mainly to:
- title
- abstract
- authors
- categories
- comment
- journal_ref
- pdf_url

Reason:
arXiv is currently the main content backbone and main manifestation source.

---

### 3.2 Semantic enrichment fields
Preferred source:
1. openalex_alignment
2. semantic_scholar_alignment
3. arxiv
4. crossref_alignment

Applies to:
- concepts
- keywords
- tags
- cited_by_count
- referenced_ids

Reason:
OpenAlex currently provides the richest semantic and citation-oriented metadata.

---

### 3.3 Bibliographic stabilization fields
Preferred source:
1. crossref_alignment
2. openalex_alignment
3. semantic_scholar_alignment
4. arxiv

Applies to:
- publisher
- publication_type
- references_count
- referenced_dois
- license

Reason:
Crossref is currently the strongest bibliographic authority among connected sources.

---

### 3.4 Artifact/code fields
Preferred source:
1. paperswithcode_alignment
2. arxiv
3. openalex_alignment
4. semantic_scholar_alignment
5. crossref_alignment

Applies to:
- repo_url
- code_links
- dataset_links
- model_links
- has_code_link
- has_dataset_link
- has_model_link

Reason:
Papers with Code is planned as the artifact enrichment layer.

---

## 4. Special semantic rules

### 4.1 publication_type
Rule:
- published bibliographic type should override generic preprint classification when reliable bibliographic evidence exists
- `article`, `conference-paper`, `book-chapter`, etc. should be preferred over `preprint` where appropriate

Current trusted sources:
- Crossref first
- OpenAlex second

---

### 4.2 open_access vs is_open_access

#### open_access
Meaning:
- whether an open manifestation exists anywhere

Typical example:
- arXiv version exists → `open_access = true`

#### is_open_access
Meaning:
- whether there is explicit bibliographic open-access evidence from trusted non-arXiv sources

Typical evidence:
- OpenAlex OA metadata
- reliable publisher-side OA metadata

This distinction is intentional.

---

### 4.3 license
Rule:
- real open licenses (e.g. `cc-by`) should be preferred over generic publisher/TDM policy URLs
- publisher text-mining policy URLs are not equivalent to content license labels

Crossref license data should be treated carefully and normalized when possible.

---

### 4.4 venue / journal / conference
Rule:
- venue-related fields require conservative normalization
- book series should not automatically become `journal`
- noisy `journal="ArXiv"` values should not override clearer DOI-based venue metadata
- conference series and journals must be separated where possible

This remains an active refinement area.

---

## 5. Multi-value merge behavior

For list-like fields, the policy is union + deduplication.

Applies to:
- categories
- concepts
- keywords
- tags
- referenced_ids
- referenced_dois
- code_links
- dataset_links
- model_links

Deduplication should be case-insensitive where applicable and URL-normalization-aware for links.

---

## 6. Provenance preservation

Canonical records must preserve source provenance:
- contributing source list
- source record ids
- source record urls
- fetched timestamps
- source update timestamps

This is required for auditability and future debugging.

---

## 7. Known technical debt

Current known technical debt areas:
- arXiv version normalization
- external_ids key harmonization (`doi` vs `DOI`, `arxiv` vs `ArXiv`)
- venue / journal / conference normalization
- license normalization
- source config lag behind operational pipeline
- future artifact merge policy for Papers with Code not yet implemented

---

## 8. Design principle

The merge layer is the core quality gate of the system.

The project should prefer:
- explicit source roles,
- conservative conflict resolution,
- provenance-preserving merge,
- and stable canonical paper entities

over aggressive field filling that introduces semantic noise.