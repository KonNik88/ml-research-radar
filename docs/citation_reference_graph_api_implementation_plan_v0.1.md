# Citation / Reference Graph API Implementation Plan v0.1

## Status

```text
document = citation / reference graph api implementation plan
version = v0.1
status = implementation-plan-only
depends_on = Citation / Reference Graph API Design v0.1
depends_on = Citation / Reference Graph API Response Fixtures v0.1
depends_on = Citation / Reference Graph Runtime Compatibility Design v0.1
implements_public_api = false
implements_endpoint_code = false
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


## Implementation progress after this plan

This plan document remains implementation-plan-only, but later code slices have
now implemented the first four narrow steps from the rollout path:

```text
Citation Graph API Disabled Status Endpoint v0.1 = implemented
Citation Graph Status Compatibility Probe v0.1 = implemented
Citation Graph Fixture Store v0.1 = implemented_internal
Citation Graph Outgoing References Endpoint v0.1 = implemented
```

Current implemented public API surface is limited to:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
```

An internal fixture-backed `CitationGraphStore` exists for query-semantics
hardening and now backs the first narrow outgoing-references route.

The implemented compatibility probe is read-only. It checks local graph
artifacts/reports for status compatibility when explicitly enabled. The fixture
store and outgoing references endpoint are also read-only and feature/compatibility
gated. These slices do not implement incoming citations, external-reference
lookup, source-family/top-reference endpoints, a full runtime graph loader, DB
materialization, Streamlit UI, GraphRAG, publication, or canonical/retrieval
mutation.

## Purpose

This document defines a future implementation plan for a local read-only
Citation / Reference Graph API.

It is not the implementation. It lists the modules, configuration flags, runtime
objects, endpoint order, tests, failure semantics, and rollout gates that must
be used when a later implementation slice starts.

The plan exists to prevent accidental drift from:

```text
design / fixtures / compatibility
```

to:

```text
runtime endpoint implementation
```

without explicit gates.

## Implementation position

The future implementation should be:

```text
file-backed
read-only
disabled by default
local-inspection oriented
bounded by compatibility checks
independent from /health readiness by default
independent from /search behavior
independent from Qdrant
not publication
not GraphRAG
not a graph DB runtime
```

First implementation should not materialize graph data into Postgres. Postgres
materialization is a separate future design if file-backed runtime proves
insufficient.

## Preconditions

Implementation must not start until these are accepted and green:

```text
Citation / Reference Graph API Design v0.1
Citation / Reference Graph API Response Fixtures v0.1
Citation / Reference Graph Runtime Compatibility Design v0.1
Graph Review Evidence Pack v0.1
```

Required local reports before serving graph evidence:

```text
citation_reference_graph_release_candidate_latest.json
citation_reference_graph_package_latest.json
citation_reference_graph_line_checkpoint_latest.json
citation_reference_graph_manual_review_latest.json
citation_reference_graph_analytics_latest.json
graph_review_evidence_pack_latest.json
```

Required interpretation:

```text
summary.ok=true means structural/safety validation passed
manual_review_complete=false means human review is incomplete
publication_ready=false means publication is blocked
```

## Future configuration

Proposed environment variables:

```text
ML_RADAR_CITATION_GRAPH_API_ENABLED=false
ML_RADAR_CITATION_GRAPH_EXPOSURE_MODE=local_inspection
ML_RADAR_CITATION_GRAPH_ROOT=data/graphs/citation_reference_graph/v0.1
ML_RADAR_CITATION_GRAPH_REPORTS_ROOT=artifacts/reports/validation
ML_RADAR_CITATION_GRAPH_VERSION=v0.1
ML_RADAR_CITATION_GRAPH_MAX_LIMIT=100
ML_RADAR_CITATION_GRAPH_DEFAULT_LIMIT=50
ML_RADAR_CITATION_GRAPH_REQUIRE_REVIEW_FOR_PUBLIC=true
```

Default behavior:

```text
API disabled by default
exposure mode defaults to local_inspection only when explicitly enabled
public exposure must remain unavailable until separate approval
```

Invalid configuration should fail closed:

```text
missing graph root -> graph_artifacts_not_found
unsupported version -> graph_version_unsupported
public mode with incomplete manual review -> graph_manual_review_incomplete
```

## Future module layout

The implementation slice should prefer small, isolated modules.

Candidate files:

```text
services/api/app.py
services/api/models.py
services/api/runtime.py
services/api/citation_graph.py
services/api/errors.py
```

If the repo already has a graph/runtime package, reuse it instead of creating a
parallel structure.

Suggested responsibility split:

```text
citation_graph.py
  - read-only graph runtime classes
  - manifest/report loading
  - compatibility check orchestration
  - bounded query helpers
  - item shaping helpers

models.py
  - response schemas if the API uses typed Pydantic models
  - request/query enum definitions only where useful

errors.py
  - graph error code mapping if existing error helpers allow it

runtime.py
  - optional graph runtime state holder
  - reload/cache integration only if already used for other optional subsystems

app.py
  - route registration
  - config gate
  - thin endpoint functions
```

The endpoint functions should stay thin. Compatibility, loading, query logic,
and response shaping should live outside route functions.

## Future runtime objects

Suggested internal objects:

```text
CitationGraphSettings
CitationGraphCompatibilityReport
CitationGraphRuntime
CitationGraphStore
CitationGraphQueryService
```

Suggested behavior:

```text
CitationGraphSettings
  parses env/config and applies defaults

CitationGraphCompatibilityReport
  records graph availability, compatibility, counters, caveats, and failure code

CitationGraphRuntime
  owns optional loaded graph state
  is disabled unless explicitly configured
  never rebuilds graph outputs

CitationGraphStore
  loads validated local graph files/package files read-only
  exposes bounded lookup methods

CitationGraphQueryService
  maps store results to response fixtures
  enforces pagination and limits
  keeps endpoint functions thin
```

## Future endpoints

The first implementation should use the already accepted candidate surface:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

Implementation order:

1. `GET /citation-graph/status`
2. `GET /citation-graph/papers/{canonical_id}/references`
3. `GET /citation-graph/papers/{canonical_id}/citations`
4. `GET /citation-graph/external-references/{reference_id}/papers`
5. `GET /citation-graph/source-families`
6. `GET /citation-graph/top-referenced-papers`
7. `GET /citation-graph/top-external-references`

The status endpoint should land first because it exercises configuration,
availability, compatibility, caveats, and error mapping without exposing graph
traversal complexity.

## Response contract

Successful responses must follow:

```text
graph
query
items
page
caveats
```

Required graph markers in every successful response:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
manual_review_required = true
manual_review_complete = false
publication_ready = false
may_be_used_as_reconcile_input = false
not_a_complete_citation_index = true
```

The implementation must not expose graph counts or top-reference lists as global
citation metrics.

## Error contract

Required error codes:

```text
graph_runtime_not_enabled
graph_artifacts_not_found
graph_artifacts_invalid
graph_artifacts_unsafe
graph_version_unsupported
graph_manual_review_incomplete
graph_query_invalid
graph_result_limit_exceeded
canonical_id_not_found
external_reference_not_found
graph_canonical_baseline_mismatch
graph_package_stale
```

The implementation plan intentionally includes the compatibility-introduced
codes:

```text
graph_canonical_baseline_mismatch
graph_package_stale
```

Before endpoint implementation, the response fixture contract or API reference
must include these codes explicitly.

## Compatibility behavior

Future runtime must check:

```text
graph_name = citation_reference_graph
graph_version = v0.1
canonical_doc_count = 60954
retrieval_build_id = 20260504T164021Z when required
nodes_count = 529295
edges_count = 745516
paper_nodes = 60954
external_reference_nodes = 468336
source_family_nodes = 5
paper_references_paper_edges = 6165
paper_references_external_edges = 703234
paper_has_reference_source_family_edges = 36117
reference_resolution_ratio = 0.00869
```

Stale or incompatible graph artifacts must fail closed. The runtime must not
auto-rebuild graph outputs.

## Health and runtime semantics

Graph API readiness must be separate from general service readiness.

Required behavior:

```text
/health readiness does not require citation graph runtime
/search behavior does not change
Discovery API behavior does not change
Qdrant behavior does not change
DB backend behavior does not change
```

If graph runtime is disabled:

```text
/health may remain ready
/citation-graph/status returns disabled/unavailable status or graph_runtime_not_enabled
```

If graph runtime is enabled but incompatible:

```text
/health may remain ready
/citation-graph/* fails with graph_artifacts_* / graph_version_* / graph_*_mismatch code
```

## No-mutation requirements

The future implementation must not:

```text
write validation reports at request time
write latest pointers
rebuild graph outputs
rebuild packages
promote graph outputs
modify canonical documents
modify Postgres
modify Qdrant
modify retrieval artifacts
modify ranking features
publish datasets
```

Reload behavior, if added, may clear and re-read an in-memory graph runtime cache.
It must not rebuild or mutate graph artifacts.

## Test plan

Minimum future test files:

```text
tests/integration/test_citation_graph_api_status.py
tests/integration/test_citation_graph_api_references.py
tests/integration/test_citation_graph_api_errors.py
tests/smoke/test_citation_graph_runtime_compatibility.py
```

Required test cases:

```text
api disabled returns graph_runtime_not_enabled or unavailable status
status endpoint returns graph/query/items/page/caveats envelope
status endpoint includes required graph safety markers
compatible fixture runtime passes local_inspection mode
missing manifest fails with graph_artifacts_not_found
unsafe manifest fails with graph_artifacts_unsafe
wrong graph version fails with graph_version_unsupported
canonical baseline mismatch fails with graph_canonical_baseline_mismatch
stale package/report mismatch fails with graph_package_stale
manual_review_complete=false allowed in local_inspection mode with caveats
manual_review_complete=false fails in public exposure mode
outgoing references include resolved and external references
incoming citations include only resolved paper_references_paper edges
external reference lookup returns linked papers
source-family diagnostics are bounded and caveated
top referenced papers are not global citation metrics
top external references are unresolved/manual-review candidates
unknown canonical_id returns canonical_id_not_found
unknown external_reference_id returns external_reference_not_found
limit above max fails with graph_result_limit_exceeded or validation_error
/health remains independent from graph runtime readiness
/search behavior remains unchanged
Qdrant is not required for citation graph API
```

## Rollout plan

Recommended future implementation sequence:

1. Add config/settings and disabled-by-default status endpoint. **Done.**
2. Add compatibility checker/status probe with fixture tests. **Done for status only.**
3. Add read-only file-backed graph store for tiny fixture graph. **Done for internal fixture store.**
4. Add one narrow references endpoint on the fixture-backed store. **Done for outgoing references only.**
5. Add incoming citations and external-reference endpoints in later slices, one endpoint at a time.
6. Add source-family and top-reference endpoints only after the paper reference/citation endpoints are stable.
7. Add integration tests against accepted local graph artifacts only after the
   fixture-backed behavior is stable.
8. Update API reference after implementation tests are green.
9. Keep Streamlit UI out of scope until API behavior is accepted.

## Rollback plan

Rollback must be simple:

```text
set ML_RADAR_CITATION_GRAPH_API_ENABLED=false
```

This must disable graph endpoints or make them return the accepted disabled
error/status without changing:

```text
/health
/search
Discovery API
Artifact API
Qdrant diagnostics
Postgres serving
Streamlit UI
```

## Explicit non-goals

```text
no additional endpoint code in this docs slice
no full runtime loader in this slice
no graph DB materialization
no Postgres schema change
no Streamlit graph UI
no GraphRAG
no Qdrant promotion
no publication
no canonical refresh
no retrieval rebuild
no ranking changes
```

## Current next step after outgoing references endpoint

After the disabled status endpoint, read-only compatibility probe, internal
fixture store, and outgoing references endpoint have been implemented, the next
safe slice is documentation synchronization.

Current implemented status:

```text
Citation Graph API Disabled Status Endpoint v0.1 = done
Citation Graph Status Compatibility Probe v0.1 = done
Citation Graph Fixture Store v0.1 = done_internal
Citation Graph Outgoing References Endpoint v0.1 = done
GET /citation-graph/status = implemented
GET /citation-graph/papers/{canonical_id}/references = implemented
GET /citation-graph/papers/{canonical_id}/citations = not implemented
GET /citation-graph/external-references/{reference_id}/papers = not implemented
GET /citation-graph/source-families = not implemented
GET /citation-graph/top-referenced-papers = not implemented
GET /citation-graph/top-external-references = not implemented
full graph runtime query service = not implemented
```

Recommended next code direction after docs sync:

```text
Citation Graph Incoming Citations Endpoint v0.1
```

The next code slice should add at most one endpoint and must preserve feature
flagging, compatibility checks, pagination bounds, graph caveats, and fail-closed
error mapping.
