# Paper-Artifact Graph Release Candidate v0.1

Status: implemented local read-only release-candidate readiness gate  
Slice: `graph/paper-artifact-graph-release-candidate-v01`  
Input: generated Paper-Artifact Graph Builder v0.1 output  
Output status: validation JSON/Markdown reports, not committed generated artifacts

## Purpose

Paper-Artifact Graph Release Candidate v0.1 adds a read-only readiness gate over the generated local Paper-Artifact Graph output.

The goal is to answer one operational question:

```text
Can the already generated graph output be treated as a local reviewable candidate artifact?
```

This slice does not build a graph and does not package or publish a dataset. It aggregates the existing graph safety, structure, inspection, and diagnostic evidence into one release-candidate style validator.

## Position in architecture

The release-candidate validator sits after the existing graph layers:

```text
contract
→ builder
→ output validator
→ inspection / QA report
→ query CLI
→ release-candidate readiness gate
```

It reads the generated graph output:

```text
data/graphs/paper_artifact_graph/v0.1/nodes.jsonl
data/graphs/paper_artifact_graph/v0.1/edges.jsonl
data/graphs/paper_artifact_graph/v0.1/schema.json
data/graphs/paper_artifact_graph/v0.1/manifest.json
data/graphs/paper_artifact_graph/v0.1/data_quality_summary.json
data/graphs/paper_artifact_graph/v0.1/README.md
data/graphs/paper_artifact_graph/v0.1/checksums.txt
```

It also reads the latest inspection report when strict mode is used:

```text
artifacts/reports/validation/paper_artifact_graph_inspection_latest.json
```

It writes only validation reports:

```text
artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.json
artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.md
artifacts/reports/validation/history/paper_artifact_graph_release_candidate_<run_ts>.json
artifacts/reports/validation/history/paper_artifact_graph_release_candidate_<run_ts>.md
```

Generated reports are local operational evidence and are not committed by default.

## Script

```text
scripts/validation/check_paper_artifact_graph_release_candidate.py
```

Smoke tests:

```text
tests/smoke/test_paper_artifact_graph_release_candidate.py
```

## What the validator checks

Required checks:

```text
graph output files exist
graph JSON/JSONL files are readable
manifest safety flags preserve derived-layer boundaries
builder input mode is file
data_quality_summary.ok is true
no duplicate node IDs
no duplicate edge IDs
accepted graph v0.1 counters match
checksums match required graph files
inspection report is ok in strict mode
```

Diagnostic checks:

```text
github provider smoke counters match accepted diagnostics
inspection diagnostic counters match accepted values
```

Current accepted graph counters:

```text
nodes_count=68385
edges_count=163757
paper=60954
artifact=7336
provider=10
source_family=5
topic_cluster=80
paper_has_artifact=7430
artifact_from_provider=7336
paper_observed_in_source_family=88037
paper_assigned_to_topic_cluster=60954
```

Current accepted inspection counters:

```text
papers_with_artifacts_count=6673
topic_clusters_with_artifact_ready_papers_count=80
```

Current accepted provider smoke counters:

```text
provider=github
artifacts=5953
paper_artifact_links=6019
```

## Validation commands

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_release_candidate.py
python -m pytest tests/smoke/test_paper_artifact_graph_release_candidate.py -q
python -m scripts.validation.check_paper_artifact_graph_release_candidate --strict
```

Accepted local result:

```text
5 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 12,
  "warning_count": 0
}
```

## Release-candidate verdict

The validator reports:

```text
technical_graph_candidate_ready
manual_review_required
publication_ready
publication_block_reason
required_failed_checks
warning_checks
```

Current expected green state:

```text
technical_graph_candidate_ready=true
manual_review_required=true
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

Manual review remains required before any public packaging, dataset publication, API exposure, or external use.

## Boundaries

This slice is read-only.

It does not:

```text
rebuild graph output
mutate canonical truth
mutate artifact inputs
mutate topic inputs
change reconcile behavior
change Postgres
change Qdrant
change retrieval
change ranking
change API
change Streamlit UI
publish a dataset
create a latest pointer
create a graph package archive
introduce Neo4j
introduce NetworkX runtime
introduce GraphRAG
```

The graph remains:

```text
derived representation
not canonical truth
not a reconcile input
not publication-ready
```

## Notes from implementation

The real graph manifest stores builder mode under:

```text
builder.input_mode=file
```

The real graph edge format uses:

```text
source_node_id
target_node_id
```

The release-candidate validator intentionally supports this actual graph output schema.

## Next possible steps

After this release-candidate gate is merged, the current paper-artifact graph line becomes a stable local checkpoint.

Possible later graph directions:

```text
Paper-Artifact Graph Packaging v0.1
Paper-Artifact Graph API Design v0.1
Paper-Artifact Graph UI Explorer v0.1
Paper-Artifact Graph Analytics v0.1
Citation / Reference Graph Contract v0.1
```

The citation/reference graph should remain a separate future graph line and should not be mixed into this release-candidate slice.
