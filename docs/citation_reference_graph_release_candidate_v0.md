# Citation / Reference Graph Release Candidate v0.1

Status: implemented local read-only release-candidate readiness gate
Slice: `graph/citation-reference-graph-release-candidate-v01`
Input: generated Citation / Reference Graph Builder v0.1 output
Output status: validation JSON/Markdown reports only, not committed generated graph artifacts

## Purpose

Citation / Reference Graph Release Candidate v0.1 adds a read-only readiness gate over the generated local Citation / Reference Graph output.

The goal is to answer one operational question:

```text
Can the already generated citation/reference graph output be treated as a local reviewable candidate artifact?
```

This slice does not build a graph, package graph output, publish data, expose an API/UI surface, or introduce a graph runtime. It aggregates existing graph safety, structure, output validation, inspection, query-CLI, checksum, and normalization evidence into one release-candidate style validator.

## Position in architecture

The release-candidate validator sits after the existing citation/reference graph layers:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection / QA report
→ query CLI
→ docs counter refresh
→ release-candidate readiness gate
```

It reads the generated graph output:

```text
data/graphs/citation_reference_graph/v0.1/nodes.jsonl
data/graphs/citation_reference_graph/v0.1/edges.jsonl
data/graphs/citation_reference_graph/v0.1/schema.json
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
data/graphs/citation_reference_graph/v0.1/README.md
data/graphs/citation_reference_graph/v0.1/checksums.txt
```

In strict mode it also reads the latest output and inspection reports:

```text
artifacts/reports/validation/citation_reference_graph_output_latest.json
artifacts/reports/validation/citation_reference_graph_inspection_latest.json
```

It checks the Query CLI file exists:

```text
scripts/graph/query_citation_reference_graph.py
```

It writes only validation reports:

```text
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.md
artifacts/reports/validation/history/citation_reference_graph_release_candidate_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_release_candidate_<run_ts>.md
```

Generated reports are local operational evidence and are not committed by default.

## Script

```text
scripts/validation/check_citation_reference_graph_release_candidate.py
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_release_candidate.py
```

## What the validator checks

Required checks:

```text
graph output files exist
graph JSON/JSONL files are readable
schema identity is citation_reference_graph / v0.1
manifest identity is citation_reference_graph / v0.1
manifest safety flags preserve derived-layer boundaries
builder input mode is file
manifest has no live DB dependency
data_quality_summary.ok is true
no duplicate node IDs
no duplicate edge IDs
edges reference existing nodes
edge confidence values are in [0, 1]
accepted post-normalization graph counters match
checksums match required graph files
OpenAlex references are normalized as openalex_id and not DOI-like URL values
query CLI file exists
```

Strict-mode report checks:

```text
latest output validator report exists and is green
latest inspection report exists and is green
```

Diagnostic checks:

```text
accepted inspection counters match current post-normalization diagnostics
```

Current accepted post-normalization graph counters:

```text
nodes_count=529295
edges_count=745516
paper=60954
external_reference=468336
source_family=5
paper_references_paper=6165
paper_references_external=703234
paper_has_reference_source_family=36117
reference_resolution_ratio=0.00869
```

Current accepted inspection counters:

```text
resolved_reference_edges_count=6165
unresolved_reference_edges_count=703234
reference_resolution_ratio=0.00869
```

## OpenAlex normalization smoke

The release-candidate validator preserves the important normalization fix from the previous slice:

```text
OpenAlex IDs from referenced_ids must be classified as openalex_id.
They must not be represented as doi:https://openalex.org/... values.
```

This is intentionally part of the release-candidate gate because the normalization fix changed the accepted graph counters and doubled the internal resolved reference count relative to the stale pre-normalization baseline.

## Validation commands

Recommended sequence:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_release_candidate.py
python -m pytest tests/smoke/test_citation_reference_graph_release_candidate.py -q
python -m scripts.validation.check_citation_reference_graph_output --strict
python -m scripts.validation.check_citation_reference_graph_inspection --strict
python -m scripts.validation.check_citation_reference_graph_release_candidate --strict
```

Expected local result:

```text
6 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 18,
  "warning_count": 0
}
```

The exact `total_checks` may only change if this validator is intentionally extended; `ok=true` and `required_failed_count=0` are the important green-state semantics.

## Release-candidate verdict

The validator reports:

```text
technical_graph_candidate_ready
manual_review_required
manual_review_complete
publication_ready
publication_block_reason
required_failed_checks
warning_checks
```

Current expected green state:

```text
technical_graph_candidate_ready=true
manual_review_required=true
manual_review_complete=false
publication_ready=false
publication_block_reason=manual_review_not_completed
required_failed_checks=[]
warning_checks=[]
```

This mirrors the project's safe candidate pattern:

```text
technical candidate ready
≠
publication ready
```

Manual review remains required before any public packaging, dataset publication, API exposure, Streamlit exposure, DB materialization, or external use.

## Boundaries

This slice is read-only.

It does not:

```text
rebuild graph output
package graph output
publish graph output
mutate canonical truth
change reconcile behavior
change Postgres
change DB schema
change Qdrant
change retrieval
change ranking
change API
change Streamlit UI
create a latest pointer
introduce NetworkX runtime
introduce Neo4j runtime
introduce GraphRAG
parse full text, PDFs, or bibliography sections
```

The graph remains:

```text
derived representation
rebuildable local evidence artifact
not canonical truth
not a reconcile input
not a DB source
not a runtime graph
not publication-ready
```

## Notes from implementation

The release-candidate validator deliberately checks graph files and latest validation reports rather than rebuilding anything.

The accepted counters are the post-normalization counters:

```text
nodes_count=529295
edges_count=745516
paper_references_paper=6165
paper_references_external=703234
external_reference_nodes_count=468336
reference_resolution_ratio=0.00869
```


## Next possible slices

After this release-candidate gate is accepted, the next conservative steps are:

```text
Citation / Reference Graph Package v0.1
→ Citation / Reference Graph Line Checkpoint v0.1
→ Citation / Reference Graph Manual Review Checklist v0.1
→ Citation / Reference Graph API Design v0.1
```

API, UI, DB materialization, NetworkX, Neo4j, and GraphRAG remain deferred design decisions, not implicit consequences of this release-candidate slice.
