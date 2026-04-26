# Merge Policy

## Purpose

This document defines how source-level normalized documents are merged into canonical paper entities.

The merge layer is the core quality gate of ML Research Radar.

It controls:

- identity resolution
- field-level source priorities
- conflict resolution
- semantic normalization for important metadata fields
- provenance preservation

The system is intentionally conservative.

It prefers explicit source roles and stable canonical paper entities over aggressive field filling that introduces semantic noise.

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

The system does not assume one source is best for all fields.

Instead, source priority is field-dependent.

This is intentional and central to canonical quality.

---

## 3. Current source families

## 3.1 Active stable paper sources

### Backbone source

- `arxiv`

### Semantic enrichment sources

- `openalex_alignment`
- `semantic_scholar_alignment`

### Bibliographic stabilization source

- `crossref_alignment`

## 3.2 Candidate paper/domain sources

Candidate paper/domain sources are viable but not yet part of the stable canonical merge path:

- `acl_anthology`
- `openreview`
- `pubmed`
- `biorxiv`
- `medrxiv`

They must first pass candidate ingestion, source quality audit, and reconcile impact checks before stable integration.

## 3.3 Artifact sources

Artifact sources are not paper truth sources.

Viable artifact candidates:

- `github`
- `huggingface_hub`

Blocked/archived artifact source:

- `paperswithcode`

Papers with Code live integration is blocked and must not be part of the active stable merge policy.

Future use may only be reconsidered as offline historical backfill after a separate viability check.

---

## 4. Field-level merge priorities

## 4.1 Backbone content fields

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

Implementation note:

The current code may prefer richer non-empty title/abstract candidates in some cases. This is acceptable as long as provenance is preserved and source-specific noise is controlled. If the project later wants strict source-priority selection for title/abstract, both implementation and smoke tests must be updated together.

---

## 4.2 Semantic enrichment fields

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

Semantic Scholar is useful as an auxiliary support layer.

---

## 4.3 Bibliographic stabilization fields

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

OpenAlex and Semantic Scholar provide useful support, but field-level noise must be handled conservatively.

---

## 4.4 Venue / journal / conference fields

Preferred source order:

1. `openalex_alignment`
2. `crossref_alignment`
3. `semantic_scholar_alignment`
4. `arxiv`

Applies mainly to:

- `venue`
- `journal`
- `conference`

Reason:

Venue metadata is distributed and noisy.

OpenAlex often provides useful venue normalization.

Crossref provides bibliographic container information.

Semantic Scholar can provide supporting hints.

arXiv should not override stronger DOI-based venue evidence with generic or preprint-only strings.

---

## 4.5 License and OA fields

Preferred source order:

1. `openalex_alignment`
2. `crossref_alignment`
3. `semantic_scholar_alignment`
4. `arxiv`

Applies mainly to:

- `license`
- `open_access`
- `is_open_access`

Important:

`open_access` and `is_open_access` are semantically different and must not be collapsed.

---

## 4.6 Artifact/code fields

Artifact/code evidence is no longer assigned to Papers with Code as an active preferred source.

Current preferred strategy:

1. existing structured fields from active paper sources
2. internal artifact extraction layer
3. dedicated artifact entities and paper-artifact links
4. GitHub / Hugging Face Hub enrichment in the artifact plane
5. possible offline historical Papers with Code backfill only if reconsidered later

Applies mainly to:

- `repo_url`
- `code_links`
- `dataset_links`
- `model_links`
- `has_code_link`
- `has_dataset_link`
- `has_model_link`

Important:

Artifact fields in `CanonicalDocument` are convenience/materialized fields.

They are not the primary artifact source of truth.

The primary artifact source of truth should live in the artifact layer:

- artifact entities
- artifact observations
- paper-artifact links

---

## 5. Special semantic rules

## 5.1 `publication_type`

Rule:

- reliable published bibliographic type should override generic preprint classification when trustworthy bibliographic evidence exists
- values such as `article`, `conference`, `conference-paper`, `book-chapter`, or equivalent normalized forms should be preferred over `preprint` when appropriate

Current trusted sources:

1. `crossref_alignment`
2. `openalex_alignment`
3. `semantic_scholar_alignment`

Notes:

- arXiv being present does not imply canonical `publication_type=preprint`
- manifestation-level preprint availability and bibliographic publication type must be separated
- unknown `is_preprint` values should be handled conservatively

---

## 5.2 `open_access` vs `is_open_access`

These two fields are intentionally distinct.

### `open_access`

Meaning:

- whether an open manifestation exists anywhere

Typical example:

- arXiv PDF exists → `open_access = true`

### `is_open_access`

Meaning:

- whether there is explicit bibliographic open-access evidence from trusted non-arXiv sources

Typical evidence:

- OpenAlex OA metadata
- reliable publisher-side OA metadata

Rule:

- do not collapse these two concepts into one
- preserve manifestation-level openness separately from bibliographic OA evidence
- API filters should be explicit about which concept is being used

---

## 5.3 `license`

Rule:

- real open licenses, for example `cc-by`, should be preferred over generic publisher or text-mining policy URLs
- publisher TDM policy URLs are not equivalent to content license labels
- Crossref license data must be treated conservatively and normalized when possible

---

## 5.4 `venue`, `journal`, `conference`

Rule:

- venue-related fields require conservative normalization
- book series should not automatically become `journal`
- noisy values such as `journal="ArXiv"` must not override clearer DOI-based bibliographic venue metadata
- conference names and journals should remain separated where possible
- `venue` can act as a display/container field, but `journal` and `conference` should remain semantically distinct where possible

This remains an active refinement area.

---

## 5.5 Artifact evidence

Artifact evidence is not bibliographic truth.

Artifact sources must not override:

- title
- abstract
- authors
- year
- venue
- journal
- conference
- publisher
- publication_type
- citation counts
- reference counts

Artifact sources may contribute:

- repo URL evidence
- code links
- dataset links
- model links
- demo links
- project page links
- artifact tags
- artifact entity metadata
- paper-artifact link evidence

In v1, artifact evidence should be stored in a separate artifact layer and linked to canonical papers through explicit paper-artifact links.

CanonicalDocument may contain materialized artifact convenience fields, but those fields are not the primary artifact source of truth.

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
- provenance should be preserved when deduplication occurs

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

## 8. Artifact provenance preservation

Artifact observations must preserve their own provenance.

At minimum, artifact observations should retain:

- raw URL
- normalized URL
- artifact type
- provider
- source layer
- source name
- source document id when available
- canonical id when available
- source field
- evidence text
- relation type
- confidence
- extraction/enrichment stage
- observed timestamp

This is required because artifact evidence can be weak, ambiguous, or external to a paper.

A repository or model link should not be treated as official unless evidence supports that interpretation.

---

## 9. Merge behavior by conflict type

## 9.1 Prefer non-empty values for:

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

Subject to field-specific source priority and normalization rules.

## 9.2 Prefer max value for:

- `cited_by_count`
- `references_count`
- `source_count`
- `unique_source_count`
- `metadata_completeness_score`

## 9.3 Preserve and union for:

- identifiers
- categories
- tags
- concepts
- keywords
- references
- artifact links
- provenance fields

---

## 10. Candidate source integration policy

New viable sources must not be added directly to stable reconcile.

Required flow:

1. source viability check
2. real-data smoke
3. candidate normalized snapshot
4. source quality report
5. candidate reconcile
6. canonical impact check
7. explicit promotion decision
8. stable registry/reconcile/export/audit integration only after validation

This applies to:

- `acl_anthology`
- `openreview`
- `pubmed`
- `biorxiv`
- `medrxiv`
- future sources

Artifact sources have a separate flow:

1. source viability check
2. artifact extraction/enrichment candidate
3. artifact quality report
4. artifact entity/link materialization
5. optional paper convenience-field materialization only after validation

---

## 11. Known technical debt

Current known technical debt areas:

- arXiv version normalization
- external id key harmonization (`doi` vs `DOI`, `arxiv` vs `ArXiv`)
- venue / journal / conference normalization
- license normalization
- source config lag behind operational pipeline
- OpenAlex and Semantic Scholar field-level noise
- stricter canonical handling for manifestation-level vs bibliographic-level fields
- title/abstract selection policy should be aligned between docs, code, and tests
- artifact layer is not yet implemented
- GitHub/Hugging Face enrichment is viable but not yet implemented
- Papers with Code live integration is blocked and must remain outside active stable merge
- `open_access` vs `is_open_access` API semantics need explicit handling

---

## 12. Design principle

The merge layer is the core quality gate of the paper corpus.

The project prefers:

- explicit source roles
- conservative conflict resolution
- provenance-preserving merge
- stable canonical paper entities
- separate paper and artifact data planes
- candidate-first integration for new sources

over aggressive field filling that introduces semantic noise.

Artifact evidence can enrich the product, but it must not destabilize paper identity.