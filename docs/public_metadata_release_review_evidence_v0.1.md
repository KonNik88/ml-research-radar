# Public Metadata Release Manual-Review Evidence v0.1

## Document status

```text
status: completed read-only evidence validation for human-rejected review
required_categories: 20
evidence_ready_categories: 20
automated_support_categories: 15
human_decision_categories: 5
category_statuses: passed = 15, failed = 5
automated approval: false
manual_review_complete: true
publication_ready: false
publication_block_reason: manual_release_rejected
publication action: not performed
canonical truth impact: none
```

This document defines the deterministic evidence layer supporting the completed
public metadata release review.

The evidence validator mirrors `passed` and `failed` statuses from the
human-owned review config. It does not infer, perform, or mutate approval.

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

Decision record input:

```text
docs/public_metadata_release_review_decision_v0.1.md
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
completed manual-review config and latest manual-review report
decision record
dataset release config and public metadata policy
config / policy / output / review-readiness reports
manifest, schema, data-quality summary
field release policy and source attribution JSON
README, DATASET_CARD, ATTRIBUTION
Kaggle metadata template and checksums
source matrix, provenance semantics, and merge policy docs
```

It does not rebuild the dataset or rewrite the reviewed package.

---

## 3. Accepted checkpoint evidence

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
approval_state = rejected
category_status_counts = {failed: 5, passed: 15}
```

The technical evidence is complete even though the human publication decision is
negative.

---

## 4. Automated support versus human decision

Automated evidence support covers 15 categories. Five categories require human
judgment.

```text
automated_support = evidence calculation only
category_status = human-owned review state
automated_decision = null
```

One automated-support category, `semantic_scholar_policy_evidence`, is marked
failed by the human review because evidence availability does not equal acceptable
redistribution rights.

---

## 5. Report semantics

Expected completed-review evidence verdict:

```text
manual_review_evidence_ready = true
evidence_ready_category_count = 20
automated_support_category_count = 15
human_decision_category_count = 5
category_status_counts = {failed: 5, passed: 15}
manual_review_complete = true
publication_ready = false
publication_block_reason = manual_release_rejected
automated_category_approval = false
automated_manual_approval = false
```

A green evidence report confirms that the recorded rejection is backed by
consistent evidence. It does not convert rejection into approval.

---

## 6. Validation sequence

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

The next safe slice is:

```text
Semantic Scholar Public Release Boundary Remediation v0.1
```

It must either document written redistribution permission or produce a validated
public candidate with Semantic Scholar-derived data excluded. Publication remains
out of scope until a fresh manual review approves the remediated candidate.
