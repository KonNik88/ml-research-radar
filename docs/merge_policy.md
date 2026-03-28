# Merge Policy

## Purpose

This document defines how source-level normalized documents are merged into canonical paper entities.

The merge layer is the core quality gate of ML Research Radar. It controls:

- identity resolution
- field-level source priorities
- conflict resolution
- semantic normalization for important metadata fields
- provenance preservation

The system is intentionally conservative: it prefers explicit source roles and stable canonical paper entities over aggressive field filling that introduces semantic noise.

---

## 1. Identity resolution

Canonical grouping currently follows this priority:

1. DOI
2. external DOI
3. arXiv id
4. external arXiv id
5. normalized title + year fallback

### Notes

- DOI is the strongest reconciliation key
- arXiv id is the secondary identity path
- title + year is fallback-only and should be treated conservatively
- arXiv version normalization remains a known technical debt area (`2412.19245` vs `2412.19245v1`)
- `doc_id` is source-level identity
- `canonical_id` is paper-level identity
- external/public-facing document identity should always be canonical-level

---

## 2. Source priority philosophy

Different metadata families have different trusted sources.

The system does **not** assume one source is best for all fields.

Instead, source priority is field-dependent.

This is intentional and central to canonical quality.

---

## 3. Current source families

### 3.1 Backbone source
- `arxiv`

### 3.2 Semantic enrichment sources
- `openalex_alignment`
- `semantic_scholar_alignment`

### 3.3 Bibliographic stabilization source
- `crossref_alignment`

### 3.4 Planned artifact/code enrichment source
- `paperswithcode_alignment`

---

## 4. Field-level merge priorities

### 4.1 Backbone content fields

Preferred source order:

1. `arxiv`
2. `openalex_alignment`
3. `semantic_scholar_alignment`
4. `crossref_alignment`

Applies mainly to:

- `title`
- `abstract`
- `authors`
- `primary_category`
- `categories`
- `comment`
- `journal_ref`
- `pdf_url`
- `landing_page_url`

Reason:

`arxiv` is currently the backbone manifestation source and main text source.

---

### 4.2 Semantic enrichment fields

Preferred source order:

1. `openalex_alignment`
2. `semantic_scholar_alignment`
3. `arxiv`
4. `crossref_alignment`

Applies mainly to:

- `concepts`
- `keywords`
- `tags`
- `cited_by_count`
- `referenced_ids`
- `open_access` hints
- semantic venue/topic metadata

Reason:

OpenAlex currently provides the richest semantic and citation-oriented metadata.

---

### 4.3 Bibliographic stabilization fields

Preferred source order:

1. `crossref_alignment`
2. `openalex_alignment`
3. `semantic_scholar_alignment`
4. `arxiv`

Applies mainly to:

- `publisher`
- `publication_type`
- `references_count`
- `referenced_dois`
- `license`
- bibliographic publication date normalization

Reason:

Crossref is currently the strongest bibliographic authority among connected sources.

---

### 4.4 Artifact/code fields

Preferred source order:

1. `paperswithcode_alignment`
2. `arxiv`
3. `openalex_alignment`
4. `semantic_scholar_alignment`
5. `crossref_alignment`

Applies mainly to:

- `repo_url`
- `code_links`
- `dataset_links`
- `model_links`
- `has_code_link`
- `has_dataset_link`
- `has_model_link`

Reason:

Papers with Code is planned as the dedicated artifact enrichment layer.

---

## 5. Special semantic rules

### 5.1 `publication_type`

Rule:

- reliable published bibliographic type should override generic preprint classification when trustworthy bibliographic evidence exists
- values such as `article`, `conference-paper`, `book-chapter` should be preferred over `preprint` when appropriate

Current trusted sources:

1. `crossref_alignment`
2. `openalex_alignment`

Notes:

- arXiv being present does **not** imply canonical `publication_type=preprint`
- manifestation-level preprint availability and bibliographic publication type must be separated

---

### 5.2 `open_access` vs `is_open_access`

These two fields are intentionally distinct.

#### `open_access`
Meaning:
- whether an open manifestation exists anywhere

Typical example:
- arXiv PDF exists → `open_access = true`

#### `is_open_access`
Meaning:
- whether there is explicit bibliographic open-access evidence from trusted non-arXiv sources

Typical evidence:
- OpenAlex OA metadata
- reliable publisher-side OA metadata

Rule:

- do not collapse these two concepts into one
- preserve manifestation-level openness separately from bibliographic OA evidence

---

### 5.3 `license`

Rule:

- real open licenses (for example `cc-by`) should be preferred over generic publisher or text-mining policy URLs
- publisher TDM policy URLs are not equivalent to content license labels

Crossref license data must be treated conservatively and normalized when possible.

---

### 5.4 `venue`, `journal`, `conference`

Rule:

- venue-related fields require conservative normalization
- book series should not automatically become `journal`
- noisy values such as `journal="ArXiv"` must not override clearer DOI-based bibliographic venue metadata
- conference names and journals should remain separated where possible

This remains an active refinement area.

---

## 6. Multi-value merge behavior

For list-like fields, the policy is:

**union + deduplication**

Applies to:

- `authors`
- `categories`
- `concepts`
- `keywords`
- `tags`
- `referenced_ids`
- `referenced_dois`
- `referenced_arxiv_ids`
- `code_links`
- `dataset_links`
- `model_links`

Deduplication rules:

- case-insensitive where appropriate
- normalization-aware for identifiers
- URL-normalization-aware for links

---

## 7. Provenance preservation

Canonical records must preserve source provenance.

At minimum, canonical records should retain:

- contributing source list
- source record ids
- source record urls
- canonical/source urls
- fetched timestamps
- source update timestamps
- source API urls where available
- raw source name

This is required for:

- auditability
- future debugging
- source drilldown
- merge inspection
- future `/documents/{id}/sources` style endpoints

---

## 8. Merge behavior by conflict type

### Prefer non-empty values for:
- `title`
- `abstract`
- `pdf_url`
- `landing_page_url`
- `publisher`
- `publication_type`
- `venue`
- `journal`
- `conference`
- `license`

### Prefer max value for:
- `cited_by_count`
- `references_count`
- `source_count`
- `unique_source_count`
- `metadata_completeness_score`

### Preserve and union for:
- identifiers
- categories/tags/concepts/keywords
- references
- artifact links
- provenance fields

---

## 9. Known technical debt

Current known technical debt areas:

- arXiv version normalization
- external id key harmonization (`doi` vs `DOI`, `arxiv` vs `ArXiv`)
- venue / journal / conference normalization
- license normalization
- source config lag behind operational pipeline
- future artifact merge policy for Papers with Code not yet implemented
- some source-level field noise in Semantic Scholar and OpenAlex metadata
- stricter canonical handling for manifestation-level vs bibliographic-level fields

---

## 10. Design principle

The merge layer is the core quality gate of the system.

The project prefers:

- explicit source roles
- conservative conflict resolution
- provenance-preserving merge
- stable canonical paper entities

over aggressive field filling that introduces semantic noise.