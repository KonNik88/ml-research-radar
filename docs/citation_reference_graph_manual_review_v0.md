# Citation / Reference Graph Manual Review Checklist v0.1

## Purpose

This slice adds a read-only manual-review gate for the local Citation / Reference Graph v0.1 package.

It exists after the completed local citation/reference graph line checkpoint:

```text
contract -> builder -> output validator -> reference-id normalization fix -> inspection -> query CLI -> docs counter refresh -> release candidate -> package -> line checkpoint -> manual review checklist
```

The checklist answers:

```text
What must a human review before the Citation / Reference Graph v0.1 package can be published, shared externally, or exposed through a public runtime/API/UI surface?
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
configs/citation_reference_graph_manual_review.yaml
scripts/validation/check_citation_reference_graph_manual_review.py
tests/smoke/test_citation_reference_graph_manual_review.py
docs/citation_reference_graph_manual_review_v0.md
```

This slice also updates:

```text
docs/roadmap.md
docs/refresh_contract_v1.md
```

## Generated reports

Generated reports are operational evidence and should not be treated as source truth:

```text
artifacts/reports/validation/citation_reference_graph_manual_review_latest.json
artifacts/reports/validation/citation_reference_graph_manual_review_latest.md
artifacts/reports/validation/history/citation_reference_graph_manual_review_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_manual_review_<run_ts>.md
```

## Required inputs

```text
artifacts/reports/validation/citation_reference_graph_line_checkpoint_latest.json
data/graphs/citation_reference_graph/packages/v0.1/package_manifest.json
```

The line checkpoint report proves that the completed local graph line is green. The package manifest preserves the package-level safety boundaries.

## Optional diagnostic inputs

```text
artifacts/reports/validation/citation_reference_graph_package_latest.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_inspection_latest.json
```

These reports may be inspected when present, but the required aggregate gate is the line checkpoint report.

## Manual-review categories

Required v0.1 categories:

```text
license_redistribution
source_provider_terms
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

## Citation/reference-specific caveats

The manual-review gate explicitly records the core limitations of Citation / Reference Graph v0.1:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
raw_reference_strings_without_identifiers_parsed = false
unresolved_references_preserved_as_external_reference_nodes = true
reference_resolution_ratio = 0.00869
```

The low internal resolution ratio is an expected v0.1 coverage limitation, not a validator failure. It must be reviewed and documented before publication, API/UI exposure, DB materialization, runtime graph work, or GraphRAG use.

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
- unsafe citation/reference caveat flag;
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

```text
publish the graph package
rebuild graph output
rebuild package output
mutate canonical documents
run reconcile
touch Postgres
touch DB schema
touch Qdrant
touch retrieval artifacts
change ranking
change API behavior
change Streamlit UI behavior
create a graph runtime
introduce Neo4j, NetworkX runtime, or GraphRAG
parse full text, PDFs, or bibliography/reference sections
redefine reference normalization policy
```

The manual-review checklist may acknowledge/review the OpenAlex/reference-id normalization policy, but must not duplicate or override the builder logic.

## Commands

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_manual_review.py
python -m pytest tests/smoke/test_citation_reference_graph_manual_review.py -q
python -m scripts.validation.check_citation_reference_graph_manual_review --strict
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

## Git hygiene

Commit tracked files only:

```text
configs/citation_reference_graph_manual_review.yaml
scripts/validation/check_citation_reference_graph_manual_review.py
tests/smoke/test_citation_reference_graph_manual_review.py
docs/citation_reference_graph_manual_review_v0.md
docs/roadmap.md
docs/refresh_contract_v1.md
```

Do not commit generated graph output, package output, or validation report history.
