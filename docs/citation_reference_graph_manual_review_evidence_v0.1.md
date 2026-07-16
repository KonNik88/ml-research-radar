# Citation / Reference Graph Manual-Review Evidence v0.1

## Status

```text
status = local read-only manual-review evidence and decision synchronization
schema = citation_reference_graph_manual_review_evidence_v1
manual_review_support = true
automated_approval = false
manual_review_required = true
manual_review_complete = true
approval_state = approved
publication_ready = false
```

## Purpose

This slice prepares deterministic review material for every category in the
existing Citation / Reference Graph v0.1 manual-review checklist.

It does not perform or automate the human review. After the separate manual-review execution updates the checklist, this validator reads and mirrors those explicit human decisions without mutating them.

The key interpretation is:

```text
evidence_ready = review material is present
evidence_ready != category passed
summary.ok = evidence layer is structurally valid
summary.ok = evidence and decision synchronization is structurally valid
reviewer_decision values come from the human-owned manual-review config
no automated category approval
no automated final approval
publication_ready remains false
```

## Position in the graph line

```text
contract
→ builder
→ output validator
→ reference normalization fix
→ inspection
→ query CLI
→ release candidate
→ package
→ line checkpoint
→ manual-review checklist
→ analytics
→ API/UI/regression hardening
→ live smoke / known issues
→ manual-review evidence preparation
→ manual review execution / decision record
```

The evidence layer is a derived review-support report. It is not graph truth,
paper truth, a reconcile input, a runtime graph, or a publication action.

## Tracked files

```text
configs/citation_reference_graph_manual_review_evidence.yaml
scripts/validation/check_citation_reference_graph_manual_review_evidence.py
tests/smoke/test_citation_reference_graph_manual_review_evidence.py
docs/citation_reference_graph_manual_review_evidence_v0.1.md
```

Living documentation synchronized by this slice:

```text
docs/architecture.md
docs/project_state_current_v0.1.md
docs/refresh_contract_v1.md
docs/roadmap.md
```

The evidence validator never changes the manual-review config. The separate human review execution updates this human-owned source of review state:

```text
configs/citation_reference_graph_manual_review.yaml
```

## Inputs

The validator reads accepted local evidence only:

```text
configs/citation_reference_graph_manual_review.yaml
artifacts/reports/validation/citation_reference_graph_manual_review_latest.json
artifacts/reports/validation/citation_reference_graph_analytics_latest.json
artifacts/reports/validation/citation_reference_graph_inspection_latest.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_package_latest.json
artifacts/reports/validation/citation_reference_graph_line_checkpoint_latest.json
artifacts/reports/validation/citation_graph_live_smoke_latest.json
artifacts/reports/validation/citation_graph_api_regression_latest.json
artifacts/reports/validation/graph_review_evidence_pack_latest.json

data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
data/graphs/citation_reference_graph/v0.1/README.md
data/graphs/citation_reference_graph/packages/v0.1/package_manifest.json
data/graphs/citation_reference_graph/packages/v0.1/README.md

docs/citation_graph_known_issues_v0.1.md
docs/source_matrix.md
docs/merge_policy.md
docs/citation_reference_graph_manual_review_decision_record_v0.1.md
```

It does not read `nodes.jsonl` or `edges.jsonl` again. Existing analytics and
inspection reports already contain the accepted distributions, samples, top
reference targets, and graph counters required for this review-support layer.

## Current source review state

The accepted reviewed state is:

```text
required_category_count = 18
category_status_counts = {passed: 18}
approval_state = approved
manual_review_required = true
manual_review_complete = true
publication_ready = false
publication_block_reason = publication_action_not_in_scope
```

The evidence validator requires its report to match this human-owned state. It
does not create or alter the decisions.

## Category model

Each category report row contains:

```text
category_id
category_title
category_required
category_status
category_reviewer_note
evidence_mode
evidence_ready
source_paths
facts
samples
review_questions
automated_decision = false
reviewer_decision = category_status for completed human decisions
reviewer_note = human reviewer rationale from the manual-review config
```

### Automated-support categories

The validator prepares technical evidence for 13 categories:

```text
reference_metadata_caveats
explicit_reference_fields_only
unresolved_external_reference_caveats
low_resolution_ratio_caveat
openalex_normalization_review
doi_reference_policy_review
source_family_reference_distribution_review
top_internal_referenced_papers_review
top_external_references_review
full_text_not_parsed_caveat
bibliography_not_parsed_caveat
package_manifest_checksum_review
known_limitations
```

`automated_support` means evidence can be assembled and checked automatically.
It never means the category has been passed automatically.

### Human-decision categories

Five categories remain explicitly human-owned:

```text
license_redistribution
source_provider_terms
readme_clarity
publication_target_decision
manual_approval_state
```

For these categories, the report provides source documents, facts, and review
questions, but no legal, policy, publication, or approval conclusion.

## Evidence examples

### Reference coverage

```text
reference_resolution_ratio = 0.00869
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference fields = referenced_dois / referenced_ids
reference types = doi / openalex_id
```

### OpenAlex normalization

Evidence includes:

```text
openalex_id edge distribution
sample OpenAlex paper→paper edges
sample OpenAlex paper→external_reference edges
release-candidate openalex_reference_normalization check
```

### DOI policy

Evidence includes DOI edge distributions and small DOI samples. Human review
must still confirm that normalization and matching remain conservative and do
not introduce identity collapse.

### Source-family distribution

Evidence includes the accepted distribution over:

```text
acl_anthology
arxiv
crossref
openalex
semantic_scholar
```

These are reference-bearing provenance diagnostics, not complete provider
coverage metrics.

### Top-reference diagnostics

Evidence includes bounded top lists from the accepted analytics report.

```text
top internal papers = resolved internal reference counts only
top external references = unresolved external evidence counts only
not global citation metrics
not publication-grade rankings
```

### Package integrity

Evidence includes:

```text
package_checksums_match
included file SHA-256 values
archive SHA-256
archive size
package status and publication flags
```

### README clarity

The validator checks required scope markers in the graph and package README
files. This is an automated completeness check only. Final wording clarity is a
human decision.

## Generated reports

```text
artifacts/reports/validation/citation_reference_graph_manual_review_evidence_latest.json
artifacts/reports/validation/citation_reference_graph_manual_review_evidence_latest.md

artifacts/reports/validation/history/
  citation_reference_graph_manual_review_evidence_<run_ts>.json
  citation_reference_graph_manual_review_evidence_<run_ts>.md
```

Generated reports are local operational evidence and should not be committed by
default.

## Expected result

```text
categories_count = 18
automated_support_categories_count = 13
human_decision_categories_count = 5
evidence_ready_categories_count = 18
source_category_status_counts = {passed: 18}
source_approval_state = approved
source_manual_review_complete = true
evidence_validator_mutated_category_status = false
evidence_validator_mutated_manual_review_complete = false
evidence_validator_mutated_approval_state = false
publication_ready = false
required_failed_count = 0
ok = true
```

## Commands

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_manual_review_evidence.py
python -m pytest tests/smoke/test_citation_reference_graph_manual_review_evidence.py -q
python -m scripts.validation.check_citation_reference_graph_manual_review_evidence --strict
```

Report-free check:

```bat
python -m scripts.validation.check_citation_reference_graph_manual_review_evidence --strict --no-write-reports
```

## Failure conditions

The validator fails on structural evidence drift, including:

- missing or unreadable required input;
- non-green accepted source report;
- manual-review category-set drift;
- category-policy overlap or omission;
- source category statuses or approval state not matching the accepted reviewed state;
- graph/package identity or safety drift;
- accepted count/distribution/resolution-ratio drift;
- missing README boundary markers;
- missing known-issues markers;
- missing OpenAlex normalization evidence;
- failed package checksum evidence;
- missing evidence source paths;
- any automated category decision;
- reviewer decisions or notes not synchronized with the human-owned manual-review config;
- an incomplete manual-review decision record.

Pending categories themselves remain valid and publication-blocking.

## Boundaries

The evidence validator itself does not mutate review state. The separate human
review execution updates the manual-review config before this validator reads it.
The evidence validator does not:

```text
mutate manual-review category statuses
mutate approval_state
automatically mark manual_review_complete=true
mark publication_ready=true
publish or upload anything
rebuild graph or package output
read/reprocess the full graph JSONL
change canonical truth
change retrieval
change Postgres
change Qdrant
change ranking
change API routes or schemas
change Streamlit
create a full graph runtime
introduce NetworkX/Neo4j/GraphRAG runtime
```

## Next action after this slice

The human review is complete and the report can be used as closure evidence. The next action is not another graph validator; it is a separate project-level decision about a source-aware public metadata/Kaggle release and later frontend work.

The human decisions remain owned by
`configs/citation_reference_graph_manual_review.yaml` and the tracked decision
record. Publication remains a separate future action after approval.
