# Public Metadata Release Manual Review Decision v0.1

## Decision status

```text
review: Manual Public Metadata Release Review Execution v0.1
reviewed_at: 2026-07-17
reviewer_role: project_owner_maintainer
dataset: ml_research_radar_metadata v0.1
approval_state: rejected
category_status_counts: passed = 15, failed = 5
manual_review_complete: true
publication_ready: false
publication_block_reason: manual_release_rejected
publication action: not performed
canonical truth impact: none
```

The project owner/maintainer completed the 20-category review against the
validated 60,954-row / 34-column local candidate, package artifacts, source-aware
policy, and latest strict reports.

The current candidate is **not approved for public upload**. The review found a
provider-terms blocker around redistribution of Semantic Scholar-derived data in
a downloadable Kaggle dataset.

---

## 1. Blocking finding

Official Semantic Scholar terms support non-commercial research/educational use,
attributed public displays, and compliance with the licenses accompanying S2
data. At the same time, the API/data terms include non-transferability and
restrictions on sharing or transferring obtained data.

The current package may contain selected identifiers, counts, links, venue hints,
or compact merged fields influenced by Semantic Scholar observations. Because
the public export does not prove that all S2-derived values have been removed,
the current downloadable package cannot be approved conservatively.

```text
blocking_source_family = semantic_scholar
blocking_use = downloadable public dataset redistribution
publication decision = rejected until remediation
```

Official references reviewed:

```text
https://www.semanticscholar.org/product/api/license
https://api.semanticscholar.org/license/
```

---

## 2. Required remediation

One of these paths must be completed in a separate slice:

### Option A — written permission

Obtain written permission or an expanded license from AI2/Semantic Scholar that
clearly permits redistribution of the selected S2-derived metadata in a public
downloadable dataset.

### Option B — source-exclusion rebuild

Exclude Semantic Scholar-derived data from the public candidate, rebuild the
public package, and prove this boundary through field/source provenance and validation.

Minimum evidence for Option B:

```text
Semantic Scholar-derived public fields removed or independently sourced
no S2-only values remain in public rows
source attribution and dataset card updated
field/source policy updated
candidate regenerated
checksums regenerated
all dataset-release validators green
all 20 review categories rerun
```

A simple removal of the `semantic_scholar` name from attribution is not
sufficient. The data contribution itself must be removed or independently
reconstructed.

---

## 3. Category outcomes

Passed categories:

```text
release identity and checkpoint
canonical truth and reconcile boundary
selected field policy coverage
source-aware abstract handling
bibliographic metadata contract
external identifiers and links
taxonomy, derived flags, and count metadata
excluded content boundary
source attribution coverage
arXiv policy evidence
OpenAlex policy evidence
Crossref policy evidence
ACL Anthology policy evidence
package manifest, checksums, and Kaggle template
publication target decision
```

Failed categories:

```text
Semantic Scholar policy evidence
final compilation license decision
provider terms review
dataset card and attribution wording
final manual release approval state
```

The package itself is technically coherent. Rejection is a publication-policy
decision, not a data-integrity failure.

---

## 4. Other provider findings

### arXiv

Accepted for the current metadata-first scope:

```text
descriptive metadata, including abstract metadata
attribution retained by project policy
PDF/e-print content linked only and not mirrored
```

Official reference:

```text
https://info.arxiv.org/help/api/tou.html
```

### OpenAlex

Accepted for the current metadata-first scope:

```text
OpenAlex dataset metadata under its recorded CC0 basis
raw provider payload excluded
publication content not redistributed
```

Official reference:

```text
https://help.openalex.org/hc/en-us/articles/24396686889751-About-us
```

### Crossref

Accepted with the existing abstract restriction:

```text
bibliographic facts, identifiers, references/count metadata
Crossref abstracts are not an independent public-abstract basis
raw API responses excluded
```

Official reference:

```text
https://www.crossref.org/documentation/retrieve-metadata/
```

### ACL Anthology

Accepted for the intended non-commercial educational/portfolio scope:

```text
metadata and original-source links
2016+ ACL-backed abstract text allowed by policy
pre-2016 ACL-backed abstract text fails closed to null
third-party material not assumed to share the ACL license
PDFs and full text not redistributed
```

Official reference:

```text
https://aclanthology.org/faq/copyright/
```

---

## 5. Compilation-license decision

No final compilation/release license is selected for the rejected candidate:

```text
compilation_license_decision = not_selected_due_semantic_scholar_redistribution_blocker
Kaggle license = other_template_only
```

`other` remains a safe unresolved template label. It is not a completed license
decision and does not authorize upload.

After remediation, a new review may consider custom attribution/non-commercial
terms that apply only to the Radar compilation and derived presentation while
preserving upstream rights. That choice is not approved by this decision.

---

## 6. Publication target

The target decision itself is recorded:

```text
preferred future target = Kaggle after remediation
optional mirror = GitHub Release after remediation
Hugging Face Datasets = deferred
```

Target selection does not override the rejected approval state.

---

## 7. Package wording

The current package correctly says it is a local candidate and not published.
However, a future public package must explicitly disclose the resolved Semantic
Scholar boundary. Current wording is insufficient for publication because it
does not state that S2-derived downloadable redistribution is blocked.

The reviewed package remains immutable evidence and still records:

```text
publication_status = not_published
final_compilation_license = pending_explicit_release_decision
Kaggle owner = __KAGGLE_OWNER__
Kaggle license = other
```

---

## 8. Safety and non-goals

This decision:

- does not redistribute PDFs;
- does not redistribute full text;
- does not include raw provider payloads or source snapshots;
- does not mutate `canonical_documents.jsonl`;
- does not make the package a reconciliation input;
- does not change retrieval, Qdrant, Postgres, API, UI, ranking, or graph state;
- does not call Kaggle, Hugging Face, Semantic Scholar, or GitHub APIs;
- does not create a public dataset or release;
- does not set `publication_ready=true`.

The publication action remains separate. No upload may proceed while
`approval_state=rejected`.
