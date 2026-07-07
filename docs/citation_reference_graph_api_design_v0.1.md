# Citation / Reference Graph API Design v0.1

## Status

```text
document = citation / reference graph api design
version = v0.1
status = design-only
implements_public_api = false
creates_runtime_graph = false
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
publication_ready = false
```

## Purpose

This document defines a safe design boundary for a possible future public or
internal Citation / Reference Graph API.

It is intentionally a design-hardening slice only. It describes possible query
modes, response contracts, caveats, error semantics, implementation gates, and
non-goals before any endpoint, runtime loader, DB materialization, UI, GraphRAG,
or publication work is started.

The design exists because Citation / Reference Graph v0.1 is now a completed
local derived graph line with validation, inspection, query CLI, release
candidate, package, manual-review, analytics, and review-evidence support. A
future API may be useful, but it must not silently convert a local review graph
into canonical truth or runtime truth.

## Current graph boundary

Citation / Reference Graph v0.1 is a local derived evidence graph over the
canonical paper corpus.

Input scope:

```text
referenced_dois
referenced_ids
referenced_arxiv_ids
```

Non-inputs:

```text
full text
PDF
HTML
raw bibliography strings
in-text citation contexts
manual bibliography extraction
```

Node types:

```text
paper
external_reference
source_family
```

Edge types:

```text
paper_references_paper
paper_references_external
paper_has_reference_source_family
```

Accepted v0.1 counters:

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
publication_ready = false
manual_review_required = true
manual_review_complete = false
```

The API design must preserve this interpretation:

```text
graph outputs = derived review/evidence artifacts
canonical_documents.jsonl = paper-level source of truth
```

## Design goals

The future API, if implemented after this design is accepted, should:

- expose citation/reference graph evidence for inspection and diagnostics;
- make metadata-only caveats visible in every graph-facing response;
- distinguish resolved paper references from unresolved external references;
- support simple bounded queries suitable for product/API use;
- avoid exposing raw graph dumps as publication-ready data;
- preserve manual-review and publication blockers;
- keep graph access read-only;
- fail closed when graph evidence is missing, stale, or unsafe;
- avoid changing existing `/search`, Discovery API, DB, Qdrant, ranking, or UI behavior.

## Non-goals

```text
no endpoint implementation in this slice
no runtime graph loader in this slice
no graph DB materialization in this slice
no Postgres schema change in this slice
no Streamlit graph UI in this slice
no GraphRAG in this slice
no Neo4j runtime in this slice
no NetworkX runtime in this slice
no Qdrant promotion in this slice
no retrieval rebuild in this slice
no ranking change in this slice
no canonical refresh in this slice
no reconcile input from graph outputs
no publication dataset
no manual approval automation
no full-text citation parsing
no bibliography extraction
```

## Proposed API surface

The following endpoints are design candidates only. They must not be implemented
until the implementation gates in this document are satisfied.

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

Preferred naming:

```text
citation-graph
```

Rationale:

- the line contains both resolved citations and unresolved references;
- the shorter public prefix is easier to use;
- response metadata must still use precise terms such as `resolved_reference`,
  `external_reference`, and `metadata_reference_fields_only`.

Alternative names:

```text
reference-graph
citation-reference-graph
```

These may be used only if API review decides that precision matters more than
URL compactness.

## Query modes

### Status

```text
GET /citation-graph/status
```

Purpose:

- expose graph availability;
- expose accepted counters;
- expose manifest safety flags;
- expose manual-review/publication status;
- expose caveats.

This endpoint should be read-only and should not trigger graph rebuilds,
downloads, package rebuilds, latest-pointer writes, or validation report writes.

### Paper outgoing references

```text
GET /citation-graph/papers/{canonical_id}/references
```

Purpose:

- list references emitted by one canonical paper;
- include both resolved `paper_references_paper` edges and unresolved
  `paper_references_external` edges;
- optionally filter by reference type.

Candidate query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | 50 | bounded by service max |
| `offset` | int | 0 | pagination offset |
| `reference_type` | string | null | `doi`, `arxiv_id`, `openalex_id`, `other` |
| `resolved` | bool | null | true for canonical-paper targets, false for external references |
| `source_family` | string | null | source-family diagnostic filter |

### Paper incoming citations

```text
GET /citation-graph/papers/{canonical_id}/citations
```

Purpose:

- list canonical papers that reference the requested canonical paper;
- use only resolved `paper_references_paper` edges;
- make clear that this is not a complete citation index.

Candidate query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | 50 | bounded by service max |
| `offset` | int | 0 | pagination offset |
| `source_family` | string | null | source-family diagnostic filter |

### External reference linked papers

```text
GET /citation-graph/external-references/{reference_id}/papers
```

Purpose:

- list canonical papers that reference one unresolved external reference node;
- support manual review of highly repeated unresolved references.

The `reference_id` must be the normalized graph external-reference node id, not
a raw user-provided DOI/URL string unless a separate lookup contract is designed.

### Source-family diagnostics

```text
GET /citation-graph/source-families
```

Purpose:

- summarize source-family reference coverage;
- expose source-family counts and caveats;
- support diagnostics, not ranking.

### Top referenced papers

```text
GET /citation-graph/top-referenced-papers
```

Purpose:

- list canonical papers with highest incoming resolved reference count;
- support local inspection and UI prototypes after design acceptance;
- avoid representing counts as global citation metrics.

Candidate query parameters:

| parameter | type | default | notes |
|---|---:|---:|---|
| `limit` | int | 50 | bounded by service max |
| `offset` | int | 0 | pagination offset |
| `year_from` | int | null | optional paper metadata filter |
| `year_to` | int | null | optional paper metadata filter |
| `source_family` | string | null | diagnostic filter |

### Top external references

```text
GET /citation-graph/top-external-references
```

Purpose:

- list unresolved external reference nodes with highest referencing-paper count;
- identify manual-review candidates;
- support future resolution-improvement work.

This endpoint is especially caveated because unresolved external references are
not publication-grade entities.

## Response envelope

Future graph API responses should include a shared metadata envelope:

```json
{
  "graph": {
    "name": "citation_reference_graph",
    "version": "v0.1",
    "publication_ready": false,
    "manual_review_required": true,
    "manual_review_complete": false,
    "metadata_reference_fields_only": true,
    "full_text_parsed": false,
    "pdfs_parsed": false,
    "bibliography_sections_parsed": false,
    "may_be_used_as_reconcile_input": false
  },
  "query": {},
  "items": [],
  "page": {
    "limit": 50,
    "offset": 0,
    "returned": 0,
    "total_estimate": null
  },
  "caveats": []
}
```

Required caveat markers:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
manual_review_required = true
publication_ready = false
may_be_used_as_reconcile_input = false
not_a_complete_citation_index = true
```

## Item shape candidates

### Resolved reference item

```json
{
  "edge_type": "paper_references_paper",
  "source_canonical_id": "paper:...",
  "target_canonical_id": "paper:...",
  "target_title": "...",
  "target_year": 2024,
  "reference_type": "doi",
  "normalized_reference": "10....",
  "source_families": ["openalex"],
  "evidence_count": 1
}
```

### External reference item

```json
{
  "edge_type": "paper_references_external",
  "source_canonical_id": "paper:...",
  "external_reference_id": "external_reference:...",
  "reference_type": "openalex_id",
  "normalized_reference": "W...",
  "source_families": ["openalex"],
  "evidence_count": 1,
  "resolved": false
}
```

### Source-family diagnostic item

```json
{
  "source_family": "openalex",
  "paper_count_with_reference_evidence": 0,
  "reference_edge_count": 0,
  "resolved_edge_count": 0,
  "external_edge_count": 0
}
```

## Error semantics

The graph API, if implemented, should use structured errors compatible with the
existing API error contract where practical.

Candidate error codes:

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
```

Expected status mapping:

| condition | status | error_code |
|---|---:|---|
| graph API disabled by config | 404 or 503 | `graph_runtime_not_enabled` |
| graph files missing | 503 | `graph_artifacts_not_found` |
| graph manifest unsafe | 503 | `graph_artifacts_unsafe` |
| unsupported graph version | 503 | `graph_version_unsupported` |
| invalid query parameter | 400 or 422 | `graph_query_invalid` |
| unknown canonical paper | 404 | `canonical_id_not_found` |
| unknown external reference | 404 | `external_reference_not_found` |

Manual review incomplete should not necessarily block local inspection endpoints,
but every response must expose:

```text
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

If an endpoint or deployment mode is intended for public users, an accepted
policy must decide whether incomplete manual review blocks the endpoint entirely
or only appears as a response caveat.

## Runtime and storage options for a future implementation

This design does not choose an implementation. A future implementation slice
must choose one option explicitly.

### Option A: file-backed read-only graph index

Load validated graph package/output files into bounded in-memory indexes.

Pros:

- simplest continuation of current local graph-line model;
- no DB schema changes;
- easy to keep read-only;
- easy to disable.

Risks:

- memory footprint must be measured;
- reload semantics must be designed;
- stale package detection must be explicit.

### Option B: Postgres materialized read model

Materialize selected query tables from validated graph outputs.

Pros:

- better pagination/filtering;
- operationally closer to existing DB serving layer;
- easier to inspect with SQL.

Risks:

- can be mistaken for canonical truth;
- requires schema/export/migration contract;
- needs stronger stale-version and rebuild gates.

### Option C: graph database runtime

Use a graph database or graph engine for graph queries.

Pros:

- more expressive graph traversal;
- may support exploratory analysis.

Risks:

- premature for current needs;
- higher operational complexity;
- easy to drift toward GraphRAG/runtime graph without accepted design.

Recommendation for any first implementation:

```text
Option A first, if implementation is approved.
Option B only after query needs justify materialization.
Option C only after a separate graph-runtime design.
```

## Required implementation gates

Before any endpoint is implemented, the project must have:

```text
accepted Citation / Reference Graph API Design v0.1
green citation_reference_graph output validator
green citation_reference_graph inspection report
green citation_reference_graph release candidate report
green citation_reference_graph package report
green citation_reference_graph manual review report
green citation_reference_graph analytics report
green graph_review_evidence_pack report
explicit graph runtime enable/disable config design
explicit stale graph/version compatibility check
explicit response caveat contract
explicit pagination and limit policy
explicit error-code tests
explicit no-mutation tests
```

Additional gate before public exposure:

```text
manual_review_complete = true
publication_ready = true
explicit product/API approval
security/privacy review if exposed outside local environment
```

Until those additional public-exposure gates pass, the graph API must remain
local, experimental, disabled, or design-only.

## Validation plan for a future implementation

Minimum test groups:

```text
status endpoint exposes safety flags
outgoing references returns resolved and external references
incoming citations uses only resolved paper_references_paper edges
external reference lookup returns referencing papers
source-family diagnostics are read-only
top referenced papers are bounded and caveated
top external references are bounded and caveated
unknown canonical_id returns 404
unknown external_reference_id returns 404
unsafe manifest blocks runtime
missing graph files block runtime
manual-review status appears in every response
publication_ready=false appears in every response until approved
no endpoint mutates graph outputs
no endpoint mutates canonical documents
no endpoint mutates Postgres unless a separate materialization slice exists
no endpoint changes /search behavior
no endpoint requires Qdrant
```

## Interaction with existing API layers

The graph API must not change:

```text
GET /search
GET /documents
GET /artifacts
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/papers
GET /documents/{canonical_id}/artifacts
Discovery API ranking/detail/similar/topic-cluster endpoints
experimental Qdrant endpoint
```

Citation/reference evidence may be linked from future paper-detail responses
only after a separate API contract update. That future contract must distinguish:

```text
paper metadata
artifact evidence
reference evidence
ranking features
graph-derived diagnostics
```

## Open design questions

These must be answered before implementation:

1. Should first implementation be file-backed only, or should it wait for a DB
   read-model design?
2. Should graph API be local-only until manual review is complete?
3. Should incomplete manual review block endpoints or appear as response caveats?
4. What is the exact max `limit` for graph queries?
5. Should `reference_id` accept only graph node ids, or should the API support
   normalized DOI/arXiv/OpenAlex lookup aliases?
6. Should top-reference endpoints return exact totals or bounded estimates?
7. How should stale graph outputs be compared with the active canonical/retrieval
   build?
8. Should paper-detail endpoints link to graph evidence, or should graph API
   remain separate?

## Recommended next step

After this design doc is accepted, the safest next slice is not endpoint
implementation. The next slice should be one of:

```text
Citation / Reference Graph API Design Review v0.1
Graph API response fixture design
Graph runtime stale-version compatibility design
Graph API local-only implementation plan
```

Endpoint implementation should start only after design review resolves the open
questions and accepts the required implementation gates.

