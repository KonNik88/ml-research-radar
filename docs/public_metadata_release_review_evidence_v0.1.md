# Public Metadata Release Manual-Review Evidence v0.1

## Document status

```text
status: implemented local read-only evidence-preparation layer
required_categories: 20
automated_support_categories: 15
human_decision_categories: 5
automated approval: false
manual_review_complete: false
publication_ready: false
publication action: not performed
canonical truth impact: none
```

This document defines the deterministic evidence layer supporting the public
metadata release checklist.

Evidence readiness is not category approval. The report maps package files,
validation reports, tracked policy/docs, and accepted checkpoint counters to all
20 categories while leaving every category status `pending`.

---

## 1. Tracked contract

Config:

```text
configs/public_metadata_release_review_evidence.yaml
```

Validator:

```text
scripts/validation/check_public_metadata_release_review_evidence.py
```

Smoke tests:

```text
tests/smoke/test_public_metadata_release_review_evidence.py
```

Generated reports, not committed by default:

```text
artifacts/reports/validation/public_metadata_release_review_evidence_latest.json
artifacts/reports/validation/public_metadata_release_review_evidence_latest.md
artifacts/reports/validation/history/public_metadata_release_review_evidence_<timestamp>.json
artifacts/reports/validation/history/public_metadata_release_review_evidence_<timestamp>.md
```

---

## 2. Evidence inputs

The evidence report reads existing artifacts only:

```text
manual-review config and latest manual-review report
dataset release config and public metadata policy
config / policy / output / review-readiness reports
manifest, schema, data-quality summary
field release policy and source attribution JSON
README, DATASET_CARD, ATTRIBUTION
Kaggle metadata template and checksums
source matrix, provenance semantics, and merge policy docs
```

It does not read or rewrite canonical JSONL and does not require a Parquet
rebuild.

---

## 3. Accepted checkpoint evidence

Expected current package markers:

```text
dataset_name = ml_research_radar_metadata
version = v0.1
row_count = 60954
column_count = 34
duplicate_canonical_id_count = 0
public_policy_id = ml_research_radar_public_metadata_release_v0.1
abstract_excluded_by_policy_count = 0
source_policy_coverage = 5/5
publication_status = not_published
Kaggle metadata = template_only
```

The evidence layer verifies field-policy coverage, fail-closed abstract handling,
source attribution, package integrity, excluded-content boundaries, and
publication-action separation.

---

## 4. Automated support versus human decision

Automated support categories:

```text
release identity
canonical boundary
field policy coverage
abstract handling
bibliographic fields
identifiers and links
taxonomy / flags / counts
excluded content
source attribution
five source-specific policy categories
package integrity and Kaggle template
```

Human decision categories:

```text
final compilation license
provider terms and intended use
dataset-card / attribution wording
publication target
final approval or rejection
```

For human categories, `evidence_ready=true` means the material required for the
decision exists. It does not make the decision.

---

## 5. Report semantics

Expected evidence-preparation verdict:

```text
manual_review_evidence_ready = true
evidence_ready_category_count = 20
automated_support_category_count = 15
human_decision_category_count = 5
category_status_counts = {pending: 20}
manual_review_complete = false
publication_ready = false
publication_block_reason = public_release_decision_not_completed
automated_category_approval = false
automated_manual_approval = false
```

Important:

```text
evidence_ready = review material exists
category_status = still pending
ok = evidence layer is structurally green
ok ≠ approval
ok ≠ publication permission
```

---

## 6. Validation sequence

Run the existing release validators first, then the review/evidence validators:

```bat
python -m scripts.validation.check_dataset_release_config --strict --check-paths
python -m scripts.validation.check_public_metadata_release_policy --strict --check-paths
python -m scripts.validation.check_dataset_release_output --strict
python -m scripts.validation.check_dataset_release_review_readiness --strict
python -m scripts.validation.check_public_metadata_release_review --strict --check-paths
python -m scripts.validation.check_public_metadata_release_review_evidence --strict --check-paths
```

Smoke tests:

```bat
python -m pytest tests/smoke/test_public_metadata_release_review.py -q
python -m pytest tests/smoke/test_public_metadata_release_review_evidence.py -q
```

---

## 7. Next action

The next slice, if chosen, is a separate human-owned execution step:

```text
Manual Public Metadata Release Review Execution v0.1
```

That slice may record reviewer identity/role, rationale, category outcomes,
final compilation-license decision, publication-target decision, and approval or
rejection. Actual upload must remain another explicit action.
