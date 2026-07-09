# Citation / Reference Graph Runtime Compatibility Design v0.1

## Status

```text
document = citation / reference graph runtime compatibility design
version = v0.1
status = design-only compatibility contract
depends_on = Citation / Reference Graph API Design v0.1
depends_on = Citation / Reference Graph API Response Fixtures v0.1
implements_public_api = false
creates_runtime_graph = false
implements_runtime_loader = false
materializes_graph_in_db = false
implements_graphrag = false
mutates_canonical_documents = false
mutates_retrieval_artifacts = false
mutates_qdrant = false
mutates_postgres = false
mutates_api = false
mutates_ui = false
mutates_ranking = false
publishes_dataset = false
may_be_used_as_reconcile_input = false
manual_review_required = true
manual_review_complete = false
publication_ready = false
```


## Implementation progress note

This document remains a compatibility design contract. Since it was accepted, the
project has implemented compatibility checks through the
`GET /citation-graph/status` status surface and has added an internal fixture
store for query-semantics hardening. The implementation remains read-only and
not publicly traversable:

```text
Citation Graph Status Compatibility Probe v0.1 = implemented
Citation Graph Fixture Store v0.1 = implemented_internal
traversal endpoints = not implemented
full runtime graph query service = not implemented
DB materialization = not implemented
Streamlit graph UI = not implemented
GraphRAG = not implemented
```

## Purpose

This document defines compatibility checks and stale-version failure semantics
for a possible future Citation / Reference Graph runtime.

It is a design-hardening contract. The later status compatibility probe implements
the read-only status-check portion of this contract, and the fixture store
implements internal fixture-backed query semantics. These do not implement a
public traversal API endpoint, full runtime graph loader, Postgres
materialization, Streamlit UI, GraphRAG, graph DB runtime, package rebuild,
graph rebuild, or publication step.

The goal is to decide how future code will verify that local graph artifacts are
safe to read before serving graph evidence through any API surface.

## Why this layer exists

The project now has:

```text
Citation / Reference Graph v0.1
Citation / Reference Graph API Design v0.1
Citation / Reference Graph API Response Fixtures v0.1
```

Those layers define graph evidence and response shapes, but they do not yet
answer runtime compatibility questions:

```text
Does the graph output match the expected graph version?
Does the graph output match the accepted canonical corpus baseline?
Do manifest counters match the accepted v0.1 counters?
Are graph safety flags still false?
Are package/release/manual-review reports coherent with the graph output?
Is the graph stale relative to the active runtime baseline?
Should the future API fail closed or serve caveated local evidence?
```

This design fixes those questions before implementation.

## Compatibility target

The first compatible target is:

```text
graph_name = citation_reference_graph
graph_version = v0.1
canonical_doc_count = 60954
retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
topic_clusters_count = 80
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

Accepted graph counters:

```text
nodes_count = 529295
edges_count = 745516
paper_nodes = 60954
external_reference_nodes = 468336
source_family_nodes = 5
paper_references_paper_edges = 6165
paper_references_external_edges = 703234
paper_has_reference_source_family_edges = 36117
resolved_reference_edges = 6165
unresolved_reference_edges = 703234
reference_resolution_ratio = 0.00869
```

Required caveats:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
not_a_complete_citation_index = true
```

## Candidate runtime inputs

A future runtime loader may read only validated local graph artifacts and reports.

Candidate inputs:

```text
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_package_latest.json
artifacts/reports/validation/citation_reference_graph_line_checkpoint_latest.json
artifacts/reports/validation/citation_reference_graph_manual_review_latest.json
artifacts/reports/validation/citation_reference_graph_analytics_latest.json
artifacts/reports/validation/graph_review_evidence_pack_latest.json
```

Optional future package inputs:

```text
data/graphs/citation_reference_graph/v0.1/package/manifest.json
data/graphs/citation_reference_graph/v0.1/package/checksums.txt
```

The runtime compatibility check must be read-only. It must not rebuild graph
outputs, regenerate packages, write latest pointers, promote reports, mutate
canonical documents, mutate Postgres, mutate Qdrant, mutate API state, mutate UI
state, or publish anything.

## Required compatibility checks

### Graph identity checks

```text
graph_name_matches_expected
graph_version_matches_expected
graph_manifest_exists
graph_data_quality_summary_exists
```

Expected failure mapping:

```text
missing file -> graph_artifacts_not_found
wrong graph name/version -> graph_version_unsupported
invalid JSON/schema -> graph_artifacts_invalid
```

### Canonical baseline checks

```text
paper_nodes_matches_canonical_doc_count
manifest_canonical_doc_count_matches_expected_if_present
line_checkpoint_canonical_doc_count_matches_expected_if_present
graph_review_pack_canonical_doc_count_matches_expected_if_present
```

Expected failure mapping:

```text
canonical baseline mismatch -> graph_canonical_baseline_mismatch
```

A mismatch must fail closed. It must not silently serve graph evidence with a
different canonical baseline.

### Counter checks

```text
nodes_count_matches_expected
edges_count_matches_expected
paper_nodes_matches_expected
external_reference_nodes_matches_expected
source_family_nodes_matches_expected
paper_references_paper_edges_matches_expected
paper_references_external_edges_matches_expected
paper_has_reference_source_family_edges_matches_expected
resolved_reference_edges_matches_expected
unresolved_reference_edges_matches_expected
reference_resolution_ratio_matches_expected
```

Expected failure mapping:

```text
counter mismatch -> graph_artifacts_invalid
```

Counter mismatches may indicate stale graph artifacts, partial outputs, or a
changed graph build. They must not be treated as warnings for runtime serving.

### Safety flag checks

Required false flags:

```text
canonical_truth = false
may_be_used_as_reconcile_input = false
publication_ready = false
creates_runtime_graph = false
implements_graphrag = false
materializes_graph_in_db = false
mutates_canonical_documents = false
mutates_retrieval_artifacts = false
mutates_qdrant = false
mutates_postgres = false
mutates_api = false
mutates_ui = false
mutates_ranking = false
publishes_dataset = false
```

Required true/false manual-review flags:

```text
manual_review_required = true
manual_review_complete = false
```

Expected failure mapping:

```text
unsafe manifest/report flag -> graph_artifacts_unsafe
publication_ready=true without explicit public-exposure gate -> graph_artifacts_unsafe
```

### Report coherence checks

Required reports before any runtime can serve graph evidence:

```text
release_candidate_report_ok = true
package_report_ok = true
line_checkpoint_report_ok = true
manual_review_report_ok = true
analytics_report_ok = true
graph_review_evidence_pack_ok = true
```

Manual review semantics:

```text
summary.ok=true means structural/safety gate ok
manual_review_complete=false means human review is not complete
publication_ready=false means publication is blocked
```

Expected failure mapping:

```text
missing report -> graph_artifacts_not_found
report not ok -> graph_artifacts_invalid
manual review incomplete in local-only mode -> serve with required caveats
manual review incomplete in public-exposure mode -> graph_manual_review_incomplete
```

## Local-only vs public-exposure modes

Future runtime design must distinguish at least two exposure modes.

### Local inspection mode

```text
graph_exposure_mode = local_inspection
```

Allowed if:

```text
all structural compatibility checks pass
manual_review_required = true
manual_review_complete = false
publication_ready = false
responses include mandatory caveats
```

Interpretation:

```text
local inspection may serve caveated graph evidence
local inspection does not imply public publication
local inspection does not imply manual review complete
```

### Public exposure mode

```text
graph_exposure_mode = public
```

Allowed only if a separate future publication/product gate explicitly approves:

```text
manual_review_complete = true
publication_ready = true
public_exposure_approved = true
```

Until that exists, public exposure must fail closed:

```text
graph_manual_review_incomplete
```

## Stale-version semantics

The runtime must fail closed when graph artifacts are stale or incompatible.

Stale conditions:

```text
graph_version != v0.1
paper_nodes != 60954
canonical_doc_count != 60954 when present
retrieval_build_id != 20260504T164021Z when runtime requires retrieval-build alignment
accepted counters mismatch
manifest checksum mismatch when package checksum is available
latest graph report older than selected graph package when timestamps are available
graph review evidence pack references a different graph version or counters
```

Expected failure mapping:

```text
graph_version_unsupported
graph_canonical_baseline_mismatch
graph_package_stale
graph_artifacts_invalid
graph_artifacts_unsafe
```

The future runtime must not auto-rebuild graph outputs to repair staleness. A
graph rebuild is a separate explicit graph-line slice.

## Error mapping

Compatibility failures must map to the error fixture contract:

| compatibility condition | error_code |
|---|---|
| runtime disabled | `graph_runtime_not_enabled` |
| required files missing | `graph_artifacts_not_found` |
| invalid JSON/schema/counters | `graph_artifacts_invalid` |
| unsafe manifest or report flags | `graph_artifacts_unsafe` |
| unsupported graph version | `graph_version_unsupported` |
| canonical baseline mismatch | `graph_canonical_baseline_mismatch` |
| stale package/report mismatch | `graph_package_stale` |
| public exposure while manual review incomplete | `graph_manual_review_incomplete` |
| invalid query | `graph_query_invalid` |
| result limit exceeded | `graph_result_limit_exceeded` |
| unknown paper | `canonical_id_not_found` |
| unknown external reference | `external_reference_not_found` |

New error codes introduced by this compatibility design:

```text
graph_canonical_baseline_mismatch
graph_package_stale
```

These should be added to the response fixture contract or implementation plan
before endpoint implementation.

## Runtime readiness semantics

Future graph runtime readiness must not affect general API health by default.

Required distinction:

```text
/health ready = existing API runtime readiness
graph runtime ready = optional graph subsystem readiness
```

If the graph runtime is disabled or incompatible:

```text
/health may remain ready
/citation-graph/status should report graph unavailable or return graph_runtime_not_enabled / graph_artifacts_* error
/search behavior must not change
Discovery API behavior must not change
Qdrant behavior must not change
```

## No-mutation requirements

Future compatibility checks must be read-only.

They must not:

```text
write validation reports by default
write latest pointers
rebuild graph outputs
rebuild packages
promote graph outputs
modify canonical documents
modify Postgres
modify Qdrant
modify retrieval artifacts
modify API routes dynamically
modify Streamlit UI
modify ranking features
publish datasets
```

If future validators write reports, report writing must be explicit and must not
be part of request-time runtime compatibility checks.

## Future test plan

Future implementation must include tests for:

```text
compatible fixture passes
fixture store query semantics pass on tiny graph
missing manifest fails with graph_artifacts_not_found
wrong graph version fails with graph_version_unsupported
paper_nodes/canonical count mismatch fails with graph_canonical_baseline_mismatch
counter mismatch fails with graph_artifacts_invalid
unsafe manifest flag fails with graph_artifacts_unsafe
missing release/package/checkpoint/manual-review/analytics/evidence-pack report fails
manual_review_complete=false is allowed in local_inspection mode with caveats
manual_review_complete=false fails in public mode with graph_manual_review_incomplete
stale package checksum/timestamp mismatch fails with graph_package_stale
graph runtime incompatibility does not affect /health readiness
graph runtime incompatibility does not change /search behavior
compatibility checks do not write graph outputs or reports at request time
```

## Implementation gates

Traversal/runtime endpoint implementation must not start until these design gates are accepted, the status compatibility probe remains green, and the fixture store semantics remain green:

```text
Citation / Reference Graph API Design v0.1
Citation / Reference Graph API Response Fixtures v0.1
Citation / Reference Graph Runtime Compatibility Design v0.1
Graph API Implementation Plan v0.1
```

The compatibility design, status probe, and fixture store do not approve broad traversal/runtime promotion by themselves. They only allow a narrow fixture-backed endpoint slice when caveats and fail-closed behavior remain intact.

