# Paper-Artifact Graph Line Checkpoint v0.1

Status: implemented local read-only line checkpoint  
Slice: `graph/paper-artifact-graph-line-checkpoint-v01`  
Input: completed Paper-Artifact Graph v0.1 local graph line artifacts and reports  
Output status: generated validation reports, not committed by default

## Purpose

Paper-Artifact Graph Line Checkpoint v0.1 is the final local checkpoint gate for the completed Paper-Artifact Graph v0.1 line.

It answers one operational question:

```text
Is the whole local paper-artifact graph line internally complete and safe to treat as a closed checkpoint?
```

This slice does not add a new graph feature. It aggregates evidence from the completed graph line and records a read-only checkpoint over the accepted local artifacts.

## Position in the graph line

The full local graph line is:

```text
contract
→ builder
→ output validator
→ inspection / QA report
→ query CLI
→ release-candidate readiness gate
→ package builder
→ package validator
→ line checkpoint
```

The line checkpoint is intentionally last. It reads existing files and reports. It does not rebuild the graph, recreate package output, or run heavy jobs.

## Tracked files

```text
configs/paper_artifact_graph_line_checkpoint.yaml
scripts/validation/check_paper_artifact_graph_line_checkpoint.py
tests/smoke/test_paper_artifact_graph_line_checkpoint.py
docs/paper_artifact_graph_line_checkpoint_v0.md
```

## Generated reports

Generated validation reports, not committed by default:

```text
artifacts/reports/validation/paper_artifact_graph_line_checkpoint_latest.json
artifacts/reports/validation/paper_artifact_graph_line_checkpoint_latest.md
artifacts/reports/validation/history/paper_artifact_graph_line_checkpoint_<run_ts>.json
artifacts/reports/validation/history/paper_artifact_graph_line_checkpoint_<run_ts>.md
```

## Inputs

The checkpoint reads existing generated graph output:

```text
data/graphs/paper_artifact_graph/v0.1/
```

Existing generated package output:

```text
data/graphs/paper_artifact_graph/packages/v0.1/
```

And the latest green reports:

```text
artifacts/reports/validation/paper_artifact_graph_inspection_latest.json
artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.json
artifacts/reports/validation/paper_artifact_graph_package_latest.json
```

## Config

Config path:

```text
configs/paper_artifact_graph_line_checkpoint.yaml
```

Important config identity:

```text
schema_version=paper_artifact_graph_line_checkpoint_config_v1
checkpoint.name=paper_artifact_graph_line_checkpoint
checkpoint.version=v0.1
checkpoint.status=local_line_checkpoint
checkpoint.publication_ready=false
checkpoint.manual_review_required=true
checkpoint.may_be_used_as_reconcile_input=false
```

Accepted line components:

```text
contract=accepted
builder=accepted_local_derived_builder
output_validator=accepted_strict_validator
inspection=accepted_read_only_inspection
query_cli=accepted_read_only_query_cli
release_candidate=accepted_read_only_release_candidate
package=accepted_local_package_candidate
```

## Required graph output files

```text
nodes.jsonl
edges.jsonl
schema.json
manifest.json
data_quality_summary.json
README.md
checksums.txt
```

## Required package files

```text
paper_artifact_graph_v0.1.zip
package_manifest.json
README.md
checksums.txt
```

## Accepted graph counters

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
trusted_links_used_count=7430
topic_edges_count=60954
```

## Validator

Validator path:

```text
scripts/validation/check_paper_artifact_graph_line_checkpoint.py
```

Validation command:

```bat
python -m scripts.validation.check_paper_artifact_graph_line_checkpoint --strict
```

Accepted local result:

```text
{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 14,
  "warning_count": 0
}
```

The validator checks:

```text
line checkpoint config schema
required graph-line tracked files are present
required graph output files are present
graph manifest is readable
graph manifest safety flags preserve derived-layer boundaries
graph counters match accepted checkpoint baseline
inspection report is green
release-candidate report is green
package report is green
required package files are present
package manifest is readable
package manifest safety flags preserve checkpoint boundaries
package zip is readable
checkpoint config safety flags preserve project boundaries
```

## Smoke tests

Smoke test path:

```text
tests/smoke/test_paper_artifact_graph_line_checkpoint.py
```

Validation commands:

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_line_checkpoint.py
python -m pytest tests/smoke/test_paper_artifact_graph_line_checkpoint.py -q
python -m scripts.validation.check_paper_artifact_graph_line_checkpoint --strict
```

Accepted local result:

```text
4 passed
ok=true
required_failed_count=0
warning_count=0
```

The tests cover:

```text
complete fixture passes
failed package report is detected
graph count mismatch is detected
validator CLI --no-write-reports path
```

## Boundaries

This slice is read-only and checkpoint-only.

It does not:

```text
rebuild graph output
rebuild package output
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
create a graph runtime
introduce Neo4j
introduce NetworkX runtime
introduce GraphRAG
```

The line checkpoint remains:

```text
local checkpoint evidence
not canonical truth
not a reconcile input
not publication-ready
manual review required before publication
```

## Git hygiene

Commit tracked files only:

```text
configs/paper_artifact_graph_line_checkpoint.yaml
scripts/validation/check_paper_artifact_graph_line_checkpoint.py
tests/smoke/test_paper_artifact_graph_line_checkpoint.py
docs/paper_artifact_graph_line_checkpoint_v0.md
docs/roadmap.md
docs/refresh_contract_v1.md
```

Do not commit generated graph output:

```text
data/graphs/paper_artifact_graph/v0.1/
```

Do not commit generated package output:

```text
data/graphs/paper_artifact_graph/packages/v0.1/
```

Do not commit generated validation report history unless an explicit artifact-retention policy is added.

## Relationship to publication

This checkpoint does not publish anything.

A future publication or external release would require a separate manual review path:

```text
license review
provenance review
README/public docs review
artifact/content review
publication target decision
manual release approval
```

## Completion meaning

After this checkpoint is green, the local Paper-Artifact Graph v0.1 line is complete as a derived local artifact path:

```text
generated graph
→ validated graph
→ inspected graph
→ queryable graph
→ release-candidate checked graph
→ locally packaged graph
→ line checkpoint
```

Reasonable next directions are separate slices:

```text
Paper-Artifact Graph Manual Review Checklist v0.1
Paper-Artifact Graph API Design v0.1
Paper-Artifact Graph UI Explorer v0.1
Paper-Artifact Graph Analytics v0.1
Citation / Reference Graph Contract v0.1
```

The citation/reference graph should remain a separate derived graph line and should not be mixed into the Paper-Artifact Graph v0.1 line checkpoint.
