# Citation / Reference Graph API Response Fixtures v0.1

## Status

```text
document = citation / reference graph api response fixtures
version = v0.1
status = design-only fixture contract
depends_on = Citation / Reference Graph API Design v0.1
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
manual_review_complete = false
publication_ready = false
```


## Implementation progress note

This fixture document remains a design/contract document. Since it was accepted,
the project has implemented the status surface and an internal fixture store:

```text
GET /citation-graph/status = implemented
read-only compatibility probe = implemented
internal CitationGraphStore fixture query core = implemented
traversal endpoints = not implemented
```

The traversal fixtures below remain future endpoint contracts. The internal
fixture store exercises their query semantics, but they must not be read as
implemented public API behavior.

## Purpose

This document defines expected JSON response and error fixtures for the candidate
Citation / Reference Graph API before any endpoint is implemented.

It is a design-hardening slice only. The fixtures are intended to make future
implementation reviewable, testable, and safe by fixing response shape, caveat
semantics, pagination shape, and error shape before runtime code exists.

This document does not implement:

```text
API endpoints
runtime graph loading
graph DB materialization
Postgres schema changes
Streamlit UI
GraphRAG
publication
```

## Shared response rules

Every successful graph-facing response should include the same high-level
envelope:

```text
graph
query
items
page
caveats
```

Every graph-facing response must preserve these caveat markers:

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

These markers are part of the safety contract. They prevent a future response
from being interpreted as canonical paper truth, complete citation data,
publication-grade graph data, or reconcile input.

## Shared graph metadata fixture

All successful response fixtures embed this graph metadata shape.

```json
{
  "name": "citation_reference_graph",
  "version": "v0.1",
  "nodes_count": 529295,
  "edges_count": 745516,
  "paper_nodes": 60954,
  "external_reference_nodes": 468336,
  "source_family_nodes": 5,
  "paper_references_paper_edges": 6165,
  "paper_references_external_edges": 703234,
  "paper_has_reference_source_family_edges": 36117,
  "resolved_reference_edges": 6165,
  "unresolved_reference_edges": 703234,
  "reference_resolution_ratio": 0.00869,
  "metadata_reference_fields_only": true,
  "full_text_parsed": false,
  "pdfs_parsed": false,
  "bibliography_sections_parsed": false,
  "manual_review_required": true,
  "manual_review_complete": false,
  "publication_ready": false,
  "may_be_used_as_reconcile_input": false,
  "not_a_complete_citation_index": true
}
```


## Internal fixture store coverage

The fixture-backed store is not a public API endpoint, but it intentionally
covers the core query semantics that future endpoint responses must preserve:

```text
outgoing references include resolved and external references
incoming citations include only resolved paper_references_paper edges
external reference lookup returns referencing papers
source-family diagnostics are bounded and caveated
top referenced papers are not global citation metrics
top external references remain unresolved/manual-review candidates
unknown ids return found=false at the store layer
limit/offset validation is enforced
```

Implemented internal files:

```text
services/api/citation_graph_store.py
tests/fixtures/citation_graph_v0_1/
tests/smoke/test_citation_graph_fixture_store.py
```

Boundary:

```text
fixture store is internal
fixture store is read-only
fixture store does not implement public routes
fixture store does not load the full graph as API runtime
fixture store does not publish or mutate anything
```

## Status fixture

Implemented endpoint:

```text
GET /citation-graph/status
```

Expected successful response:

```json
{
  "graph": {
    "name": "citation_reference_graph",
    "version": "v0.1",
    "nodes_count": 529295,
    "edges_count": 745516,
    "paper_nodes": 60954,
    "external_reference_nodes": 468336,
    "source_family_nodes": 5,
    "paper_references_paper_edges": 6165,
    "paper_references_external_edges": 703234,
    "paper_has_reference_source_family_edges": 36117,
    "resolved_reference_edges": 6165,
    "unresolved_reference_edges": 703234,
    "reference_resolution_ratio": 0.00869,
    "metadata_reference_fields_only": true,
    "full_text_parsed": false,
    "pdfs_parsed": false,
    "bibliography_sections_parsed": false,
    "manual_review_required": true,
    "manual_review_complete": false,
    "publication_ready": false,
    "may_be_used_as_reconcile_input": false,
    "not_a_complete_citation_index": true
  },
  "query": {
    "endpoint": "/citation-graph/status"
  },
  "items": [],
  "page": {
    "limit": 0,
    "offset": 0,
    "returned": 0,
    "total_estimate": null
  },
  "caveats": [
    "metadata_reference_fields_only",
    "not_a_complete_citation_index",
    "manual_review_required",
    "publication_ready_false"
  ],
  "availability": {
    "configured": true,
    "available": true,
    "runtime_enabled": true,
    "safe_to_serve_locally": true,
    "compatibility_probe_implemented": true,
    "runtime_loader_implemented": false,
    "traversal_endpoints_implemented": false
  }
}
```

Interpretation:

```text
available = true means local graph evidence can be inspected
publication_ready = false still blocks publication
manual_review_complete = false still blocks public exposure unless separately approved
```

## Outgoing references fixture

Candidate endpoint:

```text
GET /citation-graph/papers/{canonical_id}/references
```

Expected successful response:

```json
{
  "graph": {
    "name": "citation_reference_graph",
    "version": "v0.1",
    "metadata_reference_fields_only": true,
    "full_text_parsed": false,
    "pdfs_parsed": false,
    "bibliography_sections_parsed": false,
    "manual_review_required": true,
    "manual_review_complete": false,
    "publication_ready": false,
    "may_be_used_as_reconcile_input": false,
    "not_a_complete_citation_index": true
  },
  "query": {
    "endpoint": "/citation-graph/papers/{canonical_id}/references",
    "canonical_id": "paper:example-source",
    "limit": 50,
    "offset": 0,
    "reference_type": null,
    "resolved": null,
    "source_family": null
  },
  "items": [
    {
      "edge_type": "paper_references_paper",
      "source_canonical_id": "paper:example-source",
      "target_canonical_id": "paper:example-target",
      "target_title": "Example Target Paper",
      "target_year": 2024,
      "reference_type": "doi",
      "normalized_reference": "10.0000/example",
      "source_families": [
        "openalex"
      ],
      "evidence_count": 1,
      "resolved": true
    },
    {
      "edge_type": "paper_references_external",
      "source_canonical_id": "paper:example-source",
      "external_reference_id": "external_reference:openalex_id:W123",
      "reference_type": "openalex_id",
      "normalized_reference": "W123",
      "source_families": [
        "openalex"
      ],
      "evidence_count": 1,
      "resolved": false
    }
  ],
  "page": {
    "limit": 50,
    "offset": 0,
    "returned": 2,
    "total_estimate": 2
  },
  "caveats": [
    "metadata_reference_fields_only",
    "not_a_complete_citation_index",
    "unresolved_references_preserved_as_external_reference_nodes"
  ]
}
```

## Incoming citations fixture

Candidate endpoint:

```text
GET /citation-graph/papers/{canonical_id}/citations
```

Expected successful response:

```json
{
  "graph": {
    "name": "citation_reference_graph",
    "version": "v0.1",
    "metadata_reference_fields_only": true,
    "full_text_parsed": false,
    "pdfs_parsed": false,
    "bibliography_sections_parsed": false,
    "manual_review_required": true,
    "manual_review_complete": false,
    "publication_ready": false,
    "may_be_used_as_reconcile_input": false,
    "not_a_complete_citation_index": true
  },
  "query": {
    "endpoint": "/citation-graph/papers/{canonical_id}/citations",
    "canonical_id": "paper:example-target",
    "limit": 50,
    "offset": 0,
    "source_family": null
  },
  "items": [
    {
      "edge_type": "paper_references_paper",
      "source_canonical_id": "paper:example-source",
      "source_title": "Example Source Paper",
      "source_year": 2025,
      "target_canonical_id": "paper:example-target",
      "reference_type": "doi",
      "normalized_reference": "10.0000/example",
      "source_families": [
        "openalex"
      ],
      "evidence_count": 1
    }
  ],
  "page": {
    "limit": 50,
    "offset": 0,
    "returned": 1,
    "total_estimate": 1
  },
  "caveats": [
    "resolved_internal_references_only",
    "metadata_reference_fields_only",
    "not_a_complete_citation_index"
  ]
}
```

Incoming citations must use only resolved `paper_references_paper` edges.
Unresolved external references must not be counted as incoming canonical-paper
citations.

## External reference linked-papers fixture

Candidate endpoint:

```text
GET /citation-graph/external-references/{reference_id}/papers
```

Expected successful response:

```json
{
  "graph": {
    "name": "citation_reference_graph",
    "version": "v0.1",
    "metadata_reference_fields_only": true,
    "full_text_parsed": false,
    "pdfs_parsed": false,
    "bibliography_sections_parsed": false,
    "manual_review_required": true,
    "manual_review_complete": false,
    "publication_ready": false,
    "may_be_used_as_reconcile_input": false,
    "not_a_complete_citation_index": true
  },
  "query": {
    "endpoint": "/citation-graph/external-references/{reference_id}/papers",
    "external_reference_id": "external_reference:openalex_id:W123",
    "limit": 50,
    "offset": 0
  },
  "items": [
    {
      "source_canonical_id": "paper:example-source",
      "source_title": "Example Source Paper",
      "source_year": 2025,
      "external_reference_id": "external_reference:openalex_id:W123",
      "reference_type": "openalex_id",
      "normalized_reference": "W123",
      "source_families": [
        "openalex"
      ],
      "evidence_count": 1
    }
  ],
  "page": {
    "limit": 50,
    "offset": 0,
    "returned": 1,
    "total_estimate": 1
  },
  "caveats": [
    "external_reference_is_unresolved",
    "metadata_reference_fields_only",
    "not_publication_grade_reference_entity"
  ]
}
```

The `external_reference_id` is a normalized graph node id. Accepting raw DOI,
URL, arXiv, or OpenAlex lookup aliases requires a separate lookup contract.

## Source-family diagnostics fixture

Candidate endpoint:

```text
GET /citation-graph/source-families
```

Expected successful response:

```json
{
  "graph": {
    "name": "citation_reference_graph",
    "version": "v0.1",
    "metadata_reference_fields_only": true,
    "full_text_parsed": false,
    "pdfs_parsed": false,
    "bibliography_sections_parsed": false,
    "manual_review_required": true,
    "manual_review_complete": false,
    "publication_ready": false,
    "may_be_used_as_reconcile_input": false,
    "not_a_complete_citation_index": true
  },
  "query": {
    "endpoint": "/citation-graph/source-families"
  },
  "items": [
    {
      "source_family": "openalex",
      "paper_count_with_reference_evidence": 1,
      "reference_edge_count": 2,
      "resolved_edge_count": 1,
      "external_edge_count": 1
    }
  ],
  "page": {
    "limit": 50,
    "offset": 0,
    "returned": 1,
    "total_estimate": 1
  },
  "caveats": [
    "source_family_diagnostics_only",
    "metadata_reference_fields_only",
    "not_ranking_signal_by_default"
  ]
}
```

## Top referenced papers fixture

Candidate endpoint:

```text
GET /citation-graph/top-referenced-papers
```

Expected successful response:

```json
{
  "graph": {
    "name": "citation_reference_graph",
    "version": "v0.1",
    "metadata_reference_fields_only": true,
    "full_text_parsed": false,
    "pdfs_parsed": false,
    "bibliography_sections_parsed": false,
    "manual_review_required": true,
    "manual_review_complete": false,
    "publication_ready": false,
    "may_be_used_as_reconcile_input": false,
    "not_a_complete_citation_index": true
  },
  "query": {
    "endpoint": "/citation-graph/top-referenced-papers",
    "limit": 50,
    "offset": 0,
    "year_from": null,
    "year_to": null,
    "source_family": null
  },
  "items": [
    {
      "canonical_id": "paper:example-target",
      "title": "Example Target Paper",
      "year": 2024,
      "incoming_resolved_reference_count": 12,
      "source_families": [
        "openalex",
        "semantic_scholar"
      ]
    }
  ],
  "page": {
    "limit": 50,
    "offset": 0,
    "returned": 1,
    "total_estimate": null
  },
  "caveats": [
    "resolved_internal_references_only",
    "not_a_complete_citation_index",
    "not_a_global_citation_metric"
  ]
}
```

## Top external references fixture

Candidate endpoint:

```text
GET /citation-graph/top-external-references
```

Expected successful response:

```json
{
  "graph": {
    "name": "citation_reference_graph",
    "version": "v0.1",
    "metadata_reference_fields_only": true,
    "full_text_parsed": false,
    "pdfs_parsed": false,
    "bibliography_sections_parsed": false,
    "manual_review_required": true,
    "manual_review_complete": false,
    "publication_ready": false,
    "may_be_used_as_reconcile_input": false,
    "not_a_complete_citation_index": true
  },
  "query": {
    "endpoint": "/citation-graph/top-external-references",
    "limit": 50,
    "offset": 0,
    "reference_type": null,
    "source_family": null
  },
  "items": [
    {
      "external_reference_id": "external_reference:openalex_id:W123",
      "reference_type": "openalex_id",
      "normalized_reference": "W123",
      "referencing_paper_count": 8,
      "source_families": [
        "openalex"
      ]
    }
  ],
  "page": {
    "limit": 50,
    "offset": 0,
    "returned": 1,
    "total_estimate": null
  },
  "caveats": [
    "external_references_are_unresolved",
    "manual_review_candidate_list",
    "not_publication_grade_reference_entities"
  ]
}
```

## Error fixture contract

Graph API errors should use a structured shape compatible with the existing API
error contract where practical:

```json
{
  "error_code": "graph_runtime_not_enabled",
  "message": "Citation/reference graph runtime is not enabled.",
  "details": {
    "graph": "citation_reference_graph",
    "version": "v0.1",
    "manual_review_required": true,
    "publication_ready": false
  }
}
```

Candidate / implemented graph error codes:

```text
graph_runtime_not_enabled
graph_artifacts_not_found
graph_artifacts_invalid
graph_artifacts_unsafe
graph_version_unsupported
graph_canonical_baseline_mismatch
graph_package_stale
graph_manual_review_incomplete
graph_query_invalid
graph_result_limit_exceeded
canonical_id_not_found
external_reference_not_found
```

Required error fixtures:

| condition | status | error_code |
|---|---:|---|
| graph runtime disabled by config | 404 or 503 | `graph_runtime_not_enabled` |
| graph files missing | 503 | `graph_artifacts_not_found` |
| graph manifest unsafe | 503 | `graph_artifacts_unsafe` |
| unsupported graph version | 503 | `graph_version_unsupported` |
| canonical baseline mismatch | 503 | `graph_canonical_baseline_mismatch` |
| stale package/report mismatch | 503 | `graph_package_stale` |
| invalid query parameter | 400 or 422 | `graph_query_invalid` |
| result limit exceeded | 400 or 422 | `graph_result_limit_exceeded` |
| unknown canonical paper | 404 | `canonical_id_not_found` |
| unknown external reference | 404 | `external_reference_not_found` |

## Required future tests

Future endpoint implementation must add tests that assert:

```text
status response includes graph safety flags
all successful responses include graph/query/items/page/caveats
all successful responses include publication_ready=false until approved
all successful responses include manual_review_required=true until approved
all successful responses include not_a_complete_citation_index=true
outgoing references may include resolved and external items
incoming citations include only resolved paper_references_paper edges
external reference lookup returns only referencing papers for that external node
top referenced papers are not exposed as global citation metrics
top external references are explicitly unresolved/manual-review candidates
error responses use accepted graph error codes
unsafe graph manifests fail closed
missing graph artifacts fail closed
graph API does not mutate canonical documents
graph API does not mutate graph outputs
graph API does not mutate Postgres unless a separate materialization slice exists
graph API does not change /search behavior
graph API does not require Qdrant
```

## Implementation gates

Endpoint implementation must not start until these design gates are accepted:

```text
Citation / Reference Graph API Design v0.1
Citation / Reference Graph API Response Fixtures v0.1
Graph Runtime Stale-Version Compatibility Design v0.1
Graph API Implementation Plan v0.1
```

The fixture contract does not approve endpoint implementation by itself.

