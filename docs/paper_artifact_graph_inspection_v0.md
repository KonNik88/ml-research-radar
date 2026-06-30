# Paper-Artifact Graph Inspection v0.1

Status: implemented local read-only inspection layer  
Slice: `graph/paper-artifact-graph-inspection-v01`  
Input: generated Paper-Artifact Graph Builder v0.1 output  
Output status: validation/inspection reports, not committed

## Purpose

Paper-Artifact Graph Inspection v0.1 adds a read-only QA layer over the generated local paper-artifact graph output.

The builder and output validator already answer:

```text
Can the graph be built?
Is the graph structurally valid?
Do counts/checksums/schema/safety flags match?
```

The inspection layer answers a different question:

```text
Does the graph look meaningful as a research-artifact evidence graph?
```

It produces compact JSON and Markdown reports for human review.

## Position in architecture

The inspection layer is downstream of:

```text
canonical_documents
artifact_entities_latest
artifact_links_latest
topic clusters
paper-artifact graph output
```

It does not mutate:

```text
canonical documents
artifact inputs
topic inputs
graph output
Postgres
Qdrant
API
UI
ranking
retrieval artifacts
```

It is not:

```text
canonical truth
a reconcile input
a graph builder
a runtime API
a UI feature
a dataset release
```

## Script

```text
scripts/validation/check_paper_artifact_graph_inspection.py
```

Smoke tests:

```text
tests/smoke/test_paper_artifact_graph_inspection.py
```

## Reports

Generated reports:

```text
artifacts/reports/validation/paper_artifact_graph_inspection_latest.json
artifacts/reports/validation/paper_artifact_graph_inspection_latest.md
artifacts/reports/validation/history/paper_artifact_graph_inspection_<run_ts>.json
artifacts/reports/validation/history/paper_artifact_graph_inspection_<run_ts>.md
```

Generated reports are ignored and not committed.

Report schema:

```text
paper_artifact_graph_inspection_quality_v1
```

## Inspection signals

The report includes:

```text
node/edge overview
top providers by artifact nodes
top providers by paper-artifact edges
top source families by paper observations
papers with artifacts
papers without artifacts
artifacts with linked papers
artifacts without linked papers
artifacts linked to multiple papers
top artifacts by linked papers
topic clusters with artifact-ready papers
sample paper -> artifact edges
sample topic -> paper -> artifact paths
manifest safety flags
quality summary reference counters
```

## Required safety checks

The inspection validator checks that:

```text
required graph files exist
manifest.dry_run is false
manifest.canonical_truth is false
manifest.may_be_used_as_reconcile_input is false
manifest.publication_ready is false
builder input_mode is file
builder live_db_dependency is false
builder create_latest_pointer is false
data_quality.ok is true
nodes are non-empty
edges are non-empty
paper-artifact edges are present
provider distribution is non-empty
source-family distribution is non-empty
topic clusters with artifact-ready papers are present
sample paper-artifact edges are present
```

## Current accepted local result

The current local inspection run produced:

```text
ok=True
required_failed_count=0
nodes_count=68385
edges_count=163757
papers_with_artifacts_count=6673
topic_clusters_with_artifact_ready_papers_count=80
```

Interpretation:

```text
the graph output is structurally valid
trusted paper-artifact edges are present
artifact-ready papers are distributed across all 80 topic clusters
the inspection layer found meaningful provider/source/topic evidence
```

## Validation commands

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_inspection.py
python -m pytest tests/smoke/test_paper_artifact_graph_inspection.py -q
python -m scripts.validation.check_paper_artifact_graph_inspection --strict
```

Expected result:

```text
3 passed
ok=True
required_failed_count=0
```

## Non-goals

This slice does not introduce:

```text
Neo4j
NetworkX runtime
GraphRAG
API endpoints
Streamlit UI
graph query CLI
graph export packaging
parquet conversion
dataset publication
ranking changes
retrieval changes
Qdrant changes
canonical truth changes
```

## Next possible layer

After inspection is merged, the next natural graph layer is:

```text
Paper-Artifact Graph Query CLI v0.1
```

That layer can provide offline commands such as:

```text
paper -> artifacts
artifact -> papers
provider -> linked papers
topic_cluster -> artifact-ready papers
```

without introducing API/UI/runtime complexity.
