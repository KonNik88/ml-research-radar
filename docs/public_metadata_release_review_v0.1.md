# Public Metadata Release Manual Review v0.1

## Document status

```text
status: completed human-owned manual review
approval_state: rejected
required_categories: 20
category_statuses: passed = 15, failed = 5
manual_review_complete: true
publication_ready: false
publication_block_reason: manual_release_rejected
publication action: not performed
canonical truth impact: none
```

This document defines the completed manual review for the local
`ml_research_radar_metadata` v0.1 candidate.

The technical candidate and evidence layer remain green. The human review rejects
public publication of the current candidate because redistribution of
Semantic Scholar-derived data in a downloadable public dataset is not
sufficiently resolved by the current source terms and package provenance.

---

## 1. Flow

```text
canonical checkpoint
→ source-aware public metadata package
→ config / policy / output / readiness validation
→ 20-category manual-review checklist
→ deterministic evidence preparation
→ human review execution
→ rejected publication decision
→ remediation before any future publication action
```

The current slice completes review and stops before publication.

---

## 2. Tracked contract

Config:

```text
configs/public_metadata_release_review.yaml
```

Validator:

```text
scripts/validation/check_public_metadata_release_review.py
```

Smoke tests:

```text
tests/smoke/test_public_metadata_release_review.py
```

Decision record:

```text
docs/public_metadata_release_review_decision_v0.1.md
```

Generated reports, not committed by default:

```text
artifacts/reports/validation/public_metadata_release_review_latest.json
artifacts/reports/validation/public_metadata_release_review_latest.md
artifacts/reports/validation/history/public_metadata_release_review_<timestamp>.json
artifacts/reports/validation/history/public_metadata_release_review_<timestamp>.md
```

---

## 3. Category outcomes

Passed categories: 15.

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

Failed categories: 5.

```text
Semantic Scholar policy evidence
final compilation license decision
provider terms review
dataset card and attribution wording
final manual release approval state
```

Detailed rationale is stored in the review config and decision record.

---

## 4. Blocking finding

Current official Semantic Scholar terms support attributed public displays and
non-commercial research/educational use, while also imposing restrictions that
make public downloadable redistribution insufficiently clear for the current
candidate.

The current export does not prove that all Semantic Scholar-derived values were
removed or independently sourced. Therefore:

```text
approval_state = rejected
publication_ready = false
publication_block_reason = manual_release_rejected
```

This is a provider-terms/publication-policy blocker, not a package-integrity
failure.

---

## 5. Compilation-license decision

No final compilation/release license is selected:

```text
compilation_license_decision = not_selected_due_semantic_scholar_redistribution_blocker
Kaggle license = other_template_only
```

`other` remains an unresolved template label. It does not authorize upload.

---

## 6. Publication-target decision

```text
preferred future target = Kaggle after remediation
optional mirror = GitHub Release after remediation
Hugging Face Datasets = deferred
```

Target selection passed as a planning decision, but no target may be used while
the review remains rejected.

---

## 7. Required remediation

A separate slice must complete one of these paths:

```text
A. obtain written Semantic Scholar/AI2 permission for the intended public downloadable redistribution
or
B. rebuild the public candidate without Semantic Scholar-derived data and prove the exclusion
```

Option B requires field/source provenance evidence, updated package wording,
regenerated checksums, fresh output validation, and a full rerun of all 20 review
categories.

---

## 8. State consistency

Accepted completed state:

```text
approval_state = rejected
category_status_counts = {failed: 5, passed: 15}
manual_review_complete = true
publication_ready = false
publication_block_reason = manual_release_rejected
```

Important:

```text
validator ok=true = recorded human decision is structurally valid
validator ok=true ≠ candidate approved
manual_review_complete=true ≠ publication allowed
publication action remains separate
```

---

## 9. Safety boundary

This review does not:

- rebuild `data.parquet`;
- rewrite package files;
- mutate canonical documents;
- mutate retrieval, Qdrant, Postgres, ranking, API, UI, or graph state;
- call Kaggle, Hugging Face, Semantic Scholar, or GitHub APIs;
- create a public release;
- make the package a reconciliation input.

---

## 10. Validation

```bat
python -m py_compile scripts/validation/check_public_metadata_release_review.py
python -m pytest tests/smoke/test_public_metadata_release_review.py -q
python -m scripts.validation.check_public_metadata_release_review --strict --check-paths
```

Expected result:

```text
ok = true
approval_state = rejected
required_category_count = 20
category_status_counts = {failed: 5, passed: 15}
manual_review_complete = true
publication_ready = false
publication_block_reason = manual_release_rejected
required_failed_count = 0
```
