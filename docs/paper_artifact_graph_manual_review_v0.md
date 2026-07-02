# Paper-Artifact Graph Manual Review Checklist v0.1

## Purpose

This slice adds a read-only manual-review gate for the local Paper-Artifact Graph v0.1 package.

It exists after the graph line checkpoint:

```text
contract -> builder -> output validator -> inspection -> query CLI -> release candidate -> package -> line checkpoint -> manual review checklist
```

The checklist answers:

```text
What must a human review before the Paper-Artifact Graph v0.1 package can be published, shared externally, or exposed through a public runtime/API/UI surface?
```

## Status

```text
status = local_manual_review_gate
manual_review_required = true
manual_review_complete = false by default
publication_ready = false
publication_block_reason = manual_review_not_completed by default
```

## Key v0.1 semantics

Pending manual-review categories are a normal default state.

```text
pending categories block publication
pending categories do not fail the validator
```

Therefore, the default expected validator result is:

```text
summary.ok = true
summary.required_failed_count = 0
verdict.manual_review_required = true
verdict.manual_review_complete = false
verdict.publication_ready = false
verdict.publication_block_reason = manual_review_not_completed
```

`summary.ok=true` means the manual-review gate is structurally valid and publication is correctly blocked. It does not mean that human review is complete.

## Tracked files

```text
configs/paper_artifact_graph_manual_review.yaml
scripts/validation/check_paper_artifact_graph_manual_review.py
tests/smoke/test_paper_artifact_graph_manual_review.py
docs/paper_artifact_graph_manual_review_v0.md
```

This slice also updates:

```text
docs/roadmap.md
docs/refresh_contract_v1.md
```

## Generated reports

Generated reports are operational evidence and should not be treated as source truth:

```text
artifacts/reports/validation/paper_artifact_graph_manual_review_latest.json
artifacts/reports/validation/paper_artifact_graph_manual_review_latest.md
artifacts/reports/validation/history/paper_artifact_graph_manual_review_<run_ts>.json
artifacts/reports/validation/history/paper_artifact_graph_manual_review_<run_ts>.md
```

## Required inputs

```text
artifacts/reports/validation/paper_artifact_graph_line_checkpoint_latest.json
data/graphs/paper_artifact_graph/packages/v0.1/package_manifest.json
```

The line checkpoint report proves that the completed local graph line is green. The package manifest preserves the package-level safety boundaries.

## Optional diagnostic inputs

```text
artifacts/reports/validation/paper_artifact_graph_package_latest.json
artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.json
artifacts/reports/validation/paper_artifact_graph_inspection_latest.json
```

These reports may be inspected when present, but the required aggregate gate is the line checkpoint report.

## Manual-review categories

Required v0.1 categories:

```text
license_redistribution
provider_terms
artifact_metadata_caveats
provenance_completeness
trusted_link_policy_review
sample_paper_artifact_path_review
provider_distribution_sanity
topic_cluster_artifact_coverage_sanity
package_manifest_checksum_review
readme_clarity
known_limitations
publication_target_decision
manual_approval_state
```

Allowed category statuses:

```text
pending
in_progress
passed
failed
not_applicable
```

Default status is `pending`.

## Approval state

Allowed `approval_state` values:

```text
not_reviewed
in_progress
approved
rejected
```

In v0.1, `approved` means only that the manual checklist has been approved. It does not publish anything.

If all required categories are completed and `approval_state=approved`, the validator can report:

```text
manual_review_complete = true
publication_ready = false
publication_block_reason = publication_action_not_in_scope
```

Publication remains a separate future slice/action.

## Validator failure conditions

The validator should fail only on structural or safety problems, for example:

- missing required category;
- duplicate category ID;
- invalid category status;
- unsafe safety flag;
- line checkpoint report missing or not green;
- package manifest missing, unreadable, or unsafe;
- package manifest unexpectedly says `publication_ready=true`;
- `approval_state=approved` while required categories are pending, failed, or in progress;
- `publication_ready=true` in this v0.1 gate;
- inconsistent `publication_block_reason`.

Pending categories by themselves are not failures.

## Boundary / non-goals

This slice does not:

- publish the graph package;
- rebuild graph output;
- rebuild package output;
- mutate canonical documents;
- mutate artifact inputs;
- mutate topic inputs;
- touch Postgres;
- touch Qdrant;
- touch retrieval artifacts;
- change ranking;
- change API behavior;
- change UI behavior;
- create a graph runtime;
- introduce Neo4j, NetworkX runtime, or GraphRAG;
- redefine trusted-link policy.

The trusted-link policy remains owned by:

```text
radar_core/artifacts/trusted_links.py
```

The manual-review checklist may acknowledge/review that policy, but must not duplicate or override it.

## Commands

```bash
python -m py_compile scripts/validation/check_paper_artifact_graph_manual_review.py
python -m pytest tests/smoke/test_paper_artifact_graph_manual_review.py -q
python -m scripts.validation.check_paper_artifact_graph_manual_review --strict
```

Expected default result:

```text
summary.ok = true
summary.required_failed_count = 0
verdict.manual_review_required = true
verdict.manual_review_complete = false
verdict.publication_ready = false
verdict.publication_block_reason = manual_review_not_completed
```
