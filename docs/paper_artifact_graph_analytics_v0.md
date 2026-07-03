# Paper-Artifact Graph Analytics v0.1

## Status

```text
status = local read-only analytics/report layer
schema = paper_artifact_graph_analytics_v1
publication_ready = false
manual_review_support = true
```

## Purpose

Paper-Artifact Graph Analytics v0.1 adds a compact, read-only analytics report over the already generated Paper-Artifact Graph v0.1 output.

It exists to support manual review and future publication/exposure decisions by making the generated graph easier to inspect.

It answers questions such as:

```text
Which providers dominate the graph?
How many papers have trusted artifacts?
How many artifacts are linked to papers?
Which topic clusters contain artifact-ready papers?
Which artifacts are linked to multiple papers?
Are there obvious coverage or distribution limitations to document during manual review?
```

## Scope

Tracked files:

```text
configs/paper_artifact_graph_analytics.yaml
scripts/validation/check_paper_artifact_graph_analytics.py
tests/smoke/test_paper_artifact_graph_analytics.py
docs/paper_artifact_graph_analytics_v0.md
```

Generated reports, not committed:

```text
artifacts/reports/validation/paper_artifact_graph_analytics_latest.json
artifacts/reports/validation/paper_artifact_graph_analytics_latest.md
artifacts/reports/validation/history/paper_artifact_graph_analytics_<run_ts>.json
artifacts/reports/validation/history/paper_artifact_graph_analytics_<run_ts>.md
```

## Inputs

Required graph inputs:

```text
data/graphs/paper_artifact_graph/v0.1/nodes.jsonl
data/graphs/paper_artifact_graph/v0.1/edges.jsonl
data/graphs/paper_artifact_graph/v0.1/manifest.json
data/graphs/paper_artifact_graph/v0.1/data_quality_summary.json
```

The analytics layer reads existing graph output only. It does not rebuild the graph and does not read live Postgres/Qdrant/API state.

## Computed analytics

The report computes:

```text
node/edge counts
node/edge type counts
papers_with_artifacts_count
artifacts_with_linked_papers_count
multi_paper_artifacts_count
isolated_artifacts_count
provider distribution over artifact nodes
provider distribution over paper-artifact links
source-family distribution
topic-cluster artifact-ready paper coverage
top multi-paper artifacts
small sample IDs for inspection
```

## Validation semantics

The validator checks that:

```text
config schema is correct
analytics status is local_read_only_analytics
analytics is not publication-ready
analytics cannot be used as reconcile input
safety flags preserve read-only boundaries
graph output files exist
graph JSONL files are readable
manifest safety flags preserve derived-layer boundaries
data_quality_summary is readable and ok
required graph node and edge types are present
paper_has_artifact edges exist
provider coverage exists
topic cluster artifact coverage exists
accepted v0.1 counts match config expectations
provider smoke expectations pass
```

Expected local result on the accepted graph output:

```text
ok = true
required_failed_count = 0
warning_count = 0
```

## Commands

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_analytics.py
python -m pytest tests/smoke/test_paper_artifact_graph_analytics.py -q
python -m scripts.validation.check_paper_artifact_graph_analytics --strict
```

Optional report-free validation:

```bat
python -m scripts.validation.check_paper_artifact_graph_analytics --strict --no-write-reports
```

## Boundaries

This slice is intentionally narrow.

It does not:

```text
publish the graph
approve manual review
rebuild graph output
rebuild package output
change canonical truth
change reconcile inputs
change artifact inputs
change topic inputs
change Postgres
change Qdrant
change retrieval
change ranking
change API behavior
change Streamlit/UI behavior
create a runtime graph
create Neo4j / NetworkX / GraphRAG runtime
redefine trusted-link policy
```

## Relationship to Manual Review Checklist v0.1

Manual Review Checklist v0.1 defines the governance gate.

Paper-Artifact Graph Analytics v0.1 provides additional read-only evidence to help a human reviewer understand the graph/package candidate.

It does not change the manual-review verdict by itself.

Default publication state remains:

```text
manual_review_required = true
publication_ready = false
publication_block_reason = manual_review_not_completed
```

## Relationship to Paper-Artifact Graph Inspection v0.1

Inspection v0.1 is a compact QA/sanity layer.

Analytics v0.1 is a slightly richer review-support layer focused on distributions and coverage summaries.

Both are read-only. Neither is canonical truth, reconcile input, publication, API/UI, or runtime graph.
