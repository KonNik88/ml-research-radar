# Public Metadata Release Manual Review v0.1

## Document status

```text
status: implemented local manual-review governance gate
approval_state: not_reviewed
required_categories: 20
category_statuses: pending = 20
manual_review_complete: false
publication_ready: false
publication_block_reason: public_release_decision_not_completed
publication action: not performed
canonical truth impact: none
```

This document defines the manual-review checklist for the local
`ml_research_radar_metadata` v0.1 candidate.

The checklist is a governance layer above the already-green config, policy,
export, output, and review-readiness reports. It does not rebuild the candidate,
change field values, choose a license, approve publication, or call a publishing
API.

---

## 1. Flow

```text
canonical checkpoint
→ source-aware public metadata package
→ config / policy / output / readiness validation
→ manual-review checklist
→ evidence preparation
→ separate human review execution
→ separate publication action, if approved
```

The current slice stops at checklist and evidence preparation.

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

Generated reports, not committed by default:

```text
artifacts/reports/validation/public_metadata_release_review_latest.json
artifacts/reports/validation/public_metadata_release_review_latest.md
artifacts/reports/validation/history/public_metadata_release_review_<timestamp>.json
artifacts/reports/validation/history/public_metadata_release_review_<timestamp>.md
```

---

## 3. Category contract

The gate contains 20 required categories:

```text
1. release identity and checkpoint
2. canonical truth and reconcile boundary
3. selected field policy coverage
4. source-aware abstract handling
5. bibliographic metadata contract
6. external identifiers and links
7. taxonomy, derived flags, and count metadata
8. excluded content boundary
9. source attribution coverage
10. arXiv policy evidence
11. OpenAlex policy evidence
12. Crossref policy evidence
13. Semantic Scholar policy evidence
14. ACL Anthology policy evidence
15. package manifest, checksums, and Kaggle template
16. final compilation license decision
17. provider terms review
18. dataset card and attribution wording
19. publication target decision
20. final manual release approval state
```

The first 15 categories receive automated evidence support. The final 5 require
explicit human judgment.

---

## 4. Pending-state semantics

Current state:

```text
approval_state = not_reviewed
required category status = pending
manual_review_complete = false
publication_ready = false
publication_block_reason = public_release_decision_not_completed
```

Important:

```text
pending categories block publication
pending categories do not fail the validator
validator ok=true means the gate is structurally valid
validator ok=true does not mean human review is complete
```

A future human-review execution slice may change category statuses and the
approval state. Evidence preparation must not do so.

---

## 5. Approval-state consistency

Supported states are intentionally explicit:

```text
not_reviewed
→ all required categories pending
→ manual_review_complete = false
→ publication_ready = false
→ publication_block_reason = public_release_decision_not_completed

approved
→ all required categories passed
→ manual_review_complete = true
→ publication_ready = false
→ publication_block_reason = publication_action_not_in_scope

rejected
→ at least one required category failed
→ manual_review_complete = true
→ publication_ready = false
→ publication_block_reason = manual_release_rejected
```

Even an approved manual review does not itself publish the dataset.

---

## 6. Safety boundary

This gate must not:

- rebuild `data.parquet`;
- rewrite package files;
- mutate canonical documents;
- mutate retrieval, Qdrant, Postgres, ranking, API, or UI state;
- call Kaggle or Hugging Face APIs;
- create a GitHub Release;
- select a final compilation license automatically;
- approve categories automatically;
- become a reconciliation input.

---

## 7. Validation

```bat
python -m py_compile scripts/validation/check_public_metadata_release_review.py
python -m pytest tests/smoke/test_public_metadata_release_review.py -q
python -m scripts.validation.check_public_metadata_release_review --strict --check-paths
```

Expected evidence-preparation state:

```text
ok = true
approval_state = not_reviewed
required_category_count = 20
category_status_counts = {pending: 20}
manual_review_complete = false
publication_ready = false
required_failed_count = 0
```
