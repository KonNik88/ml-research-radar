# Citation / Reference Graph Inspection v0.1

Status: local read-only inspection/report layer accepted after reference-id normalization fix.

## Purpose

Citation / Reference Graph Inspection v0.1 adds a compact QA and analytics report over the already generated local Citation / Reference Graph v0.1 output.

It answers:

```text
What does the local citation/reference graph look like in terms of resolved versus unresolved references, source-family evidence, internal paper-reference coverage, top referenced papers, and sample paths for manual inspection?
```

This slice is intentionally read-only. It does not rebuild the graph and does not change canonical truth, DB, API, UI, retrieval, Qdrant, ranking, runtime behavior, or publication state.

## Inputs

Required generated graph output:

```text
data/graphs/citation_reference_graph/v0.1/nodes.jsonl
data/graphs/citation_reference_graph/v0.1/edges.jsonl
data/graphs/citation_reference_graph/v0.1/schema.json
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
data/graphs/citation_reference_graph/v0.1/README.md
data/graphs/citation_reference_graph/v0.1/checksums.txt
```

Config:

```text
configs/citation_reference_graph.yaml
```

## Tracked files

```text
scripts/validation/check_citation_reference_graph_inspection.py
tests/smoke/test_citation_reference_graph_inspection.py
docs/citation_reference_graph_inspection_v0.md
```

## Generated reports

Generated reports are local operational evidence and are not committed by default:

```text
artifacts/reports/validation/citation_reference_graph_inspection_latest.json
artifacts/reports/validation/citation_reference_graph_inspection_latest.md
artifacts/reports/validation/history/citation_reference_graph_inspection_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_inspection_<run_ts>.md
```

## Validation

Recommended validation sequence:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_inspection.py
python -m pytest tests/smoke/test_citation_reference_graph_inspection.py -q
python -m scripts.validation.check_citation_reference_graph_inspection --strict
```

The validator reads existing graph output and writes JSON/Markdown inspection reports.

Accepted current validation:

```text
7 passed
ok = true
required_failed_count = 0
total_checks = 35
warning_count = 0
```

Accepted current inspection counters after reference-id normalization fix:

```text
nodes_count = 529295
edges_count = 745516
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference_resolution_ratio = 0.00869
```

## Inspection metrics

The report includes:

```text
nodes_count
edges_count
paper_nodes_count
external_reference_nodes_count
source_family_nodes_count
paper_references_paper_edges_count
paper_references_external_edges_count
paper_has_reference_source_family_edges_count
resolved_reference_edges_count
unresolved_reference_edges_count
reference_resolution_ratio
papers_with_outgoing_reference_edges_count
papers_with_internal_reference_edges_count
papers_with_external_reference_edges_count
papers_with_incoming_internal_reference_edges_count
papers_with_reference_source_family_edges_count
papers_without_outgoing_reference_edges_count
reference_type_distribution
reference_field_distribution
source_family_distribution
top_referenced_papers
top_external_references
sample_paper_to_paper_edges
sample_paper_to_external_edges
```

## Expected interpretation

The first builder output is conservative. Most explicit references are expected to remain unresolved external references because the builder only resolves references when an identifier maps uniquely to an existing canonical paper.

The current accepted `reference_resolution_ratio` is `0.00869`. A low ratio is not automatically a failure in v0.1. It is diagnostic evidence for future reference-resolution and source-quality work.

## Safety boundary

This inspection layer must not:

```text
rebuild citation/reference graph output
publish anything
change canonical truth
run reconcile
change DB schema
change API behavior
change Streamlit behavior
change retrieval behavior
change Qdrant behavior
change ranking behavior
require NetworkX/Neo4j/GraphRAG runtime
be used as a reconcile input
```

## Next possible slices

After this inspection slice, the Query CLI v0.1 slice was accepted.

Possible next steps are:

```text
Citation / Reference Graph Release Candidate v0.1
Citation / Reference Graph Package v0.1
Citation / Reference Graph Line Checkpoint v0.1
```

API/UI/runtime/GraphRAG decisions remain intentionally deferred until local evidence is complete.
