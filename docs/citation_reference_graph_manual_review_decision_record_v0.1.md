# Citation / Reference Graph Manual Review Decision Record v0.1

## Status

```text
review = completed
approval_state = approved
manual_review_complete = true
publication_ready = false
publication_block_reason = publication_action_not_in_scope
reviewed_at = 2026-07-16
reviewer_role = project_owner_maintainer
```

This record documents the human review of the 18-category Citation / Reference
Graph v0.1 checklist. It is a governance record, not graph truth, paper truth, a
reconcile input, a package rebuild, or a publication action.

## Intended project use

The reviewed project scope is:

```text
non-commercial educational and portfolio use
public ML Research Radar discovery website
versioned Kaggle metadata/graph datasets
versioned GitHub releases
transparent attribution to upstream providers
links to original publication pages and repositories
```

The project does not redistribute PDFs and does not redistribute full text.
Article content remains at the original source. Radar publishes metadata,
identifiers, links, provenance, graph relations, and derived Radar features.

## Human decision

All 18 required categories are accepted as `passed` for the intended scope.
The checklist approval means that the reviewed local graph/package candidate has
an explicit and acceptable metadata-only, attribution-preserving use policy.

It does not mean:

```text
the package has been uploaded
Kaggle publication has occurred
GitHub release publication has occurred
all upstream data has one uniform license
the graph is a complete citation index
the graph is canonical truth
the graph is publication-ready automatically
```

A future publication action remains separate and must generate its own dataset
card, attribution statement, release manifest, checksums, and target-specific
validation evidence.

## Source/provider review

The review used the current official provider terms available on 2026-07-16.
This is an engineering/governance review for the declared non-commercial,
metadata-first scope; it is not legal advice.

| Source family | Reviewed basis | Decision for Radar scope |
|---|---|---|
| arXiv | Descriptive metadata is available under CC0. arXiv permits retrieving, storing, transforming, and sharing descriptive metadata, encourages discovery/search/citation-graph services, and recommends linking users to original arXiv pages. | Accepted. Metadata, identifiers, abstracts supplied as descriptive metadata, classifications, and links may be used. PDFs/source files are not redistributed. |
| OpenAlex | The complete OpenAlex dataset is released under CC0 and is intended for reuse. | Accepted. OpenAlex identifiers and reference metadata may be included with attribution/citation as good practice. |
| Crossref | Bibliographic metadata, including references, is described as factual and reusable without restriction; Crossref-generated data is CC0. Abstracts retain publisher/author copyright. | Accepted for Citation Graph v0.1 because the graph package uses identifiers/reference metadata and does not redistribute Crossref abstracts or full text. |
| Semantic Scholar | API use is permitted for compatible third-party software to access/display S2 Data. S2 Data and underlying third-party content remain governed by their accompanying licenses, which may include CC BY-NC or ODC-BY. | Accepted for the declared non-commercial, attribution-preserving metadata scope. Future public releases must retain Semantic Scholar attribution and must not claim a uniform CC0 license for all S2-derived fields. |
| ACL Anthology | ACL materials before 2016 use CC BY-NC-SA 3.0; materials from 2016 onward use CC BY 4.0. Third-party materials hosted by ACL may have separate rights. | Accepted for non-commercial educational/portfolio use with attribution. Radar does not redistribute ACL PDFs/full text; third-party content is not republished. |

Official references reviewed:

- arXiv API Terms of Use: `https://info.arxiv.org/help/api/tou.html`
- OpenAlex developer overview: `https://developers.openalex.org/`
- Crossref metadata retrieval/licensing: `https://www.crossref.org/documentation/retrieve-metadata/`
- Semantic Scholar API License Agreement: `https://www.semanticscholar.org/product/api/license`
- ACL Anthology copyright FAQ: `https://aclanthology.org/faq/copyright/`

## Public-release guardrails

Every future public dataset or graph release must preserve these rules:

```text
metadata / identifiers / links / provenance / derived Radar features only
no PDF redistribution
no full-text redistribution
source attribution is mandatory
source-specific terms remain applicable
no claim that all upstream fields are owned by Radar
no claim that all mixed-source content is uniformly CC0
unknown or incompatible field provenance -> omit from public export
publication action remains separate from manual-review approval
```

The internal canonical corpus may remain richer than a public dataset
projection. Public Kaggle/GitHub exports must be generated through a dedicated
source-aware release policy rather than by copying the internal canonical file
verbatim.

## Category decisions

| Category | Status | Decision summary |
|---|---|---|
| `license_redistribution` | `passed` | Intended non-commercial metadata-only distribution with attribution is accepted; PDFs/full text are excluded. |
| `source_provider_terms` | `passed` | Current official terms for arXiv, OpenAlex, Crossref, Semantic Scholar, and ACL were reviewed and translated into source-aware release conditions. |
| `reference_metadata_caveats` | `passed` | Metadata-only and incomplete-citation-index caveats are explicit. |
| `explicit_reference_fields_only` | `passed` | Edges derive only from accepted explicit canonical reference fields. |
| `unresolved_external_reference_caveats` | `passed` | External nodes are unresolved evidence, not resolved publication entities. |
| `low_resolution_ratio_caveat` | `passed` | `0.00869` is an accepted v0.1 coverage limitation. |
| `openalex_normalization_review` | `passed` | OpenAlex references remain typed as `openalex_id`. |
| `doi_reference_policy_review` | `passed` | DOI resolution remains conservative and identity-safe. |
| `source_family_reference_distribution_review` | `passed` | Distribution is provenance evidence, not total provider coverage. |
| `top_internal_referenced_papers_review` | `passed` | Counts are bounded internal diagnostics, not global citation metrics. |
| `top_external_references_review` | `passed` | Counts are unresolved-reference diagnostics, not publication-grade rankings. |
| `full_text_not_parsed_caveat` | `passed` | No full text, PDFs, HTML bodies, or in-text contexts are parsed or redistributed. |
| `bibliography_not_parsed_caveat` | `passed` | No bibliography sections or raw reference strings are parsed. |
| `package_manifest_checksum_review` | `passed` | Package checksum evidence is green. |
| `readme_clarity` | `passed` | README boundaries and caveats are sufficiently clear for the reviewed local candidate. |
| `known_limitations` | `passed` | Known limitations remain visible and mandatory. |
| `publication_target_decision` | `passed` | Future targets are Kaggle, GitHub, and a public Radar website; no publication is performed here. |
| `manual_approval_state` | `passed` | The project owner/maintainer approved the completed checklist. |

## Final verdict

```text
required_categories = 18
passed_categories = 18
failed_categories = 0
pending_categories = 0
approval_state = approved
manual_review_complete = true
publication_ready = false
publication_block_reason = publication_action_not_in_scope
```

The Citation / Reference Graph v0.1 manual-review line is complete. Publication,
upload, public dataset licensing, and target-specific packaging remain explicit
future slices.
