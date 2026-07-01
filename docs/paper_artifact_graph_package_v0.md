# Paper-Artifact Graph Package v0.1

Status: implemented local package candidate layer  
Slice: `graph/paper-artifact-graph-package-v01`  
Input: generated Paper-Artifact Graph Builder v0.1 output and green Release Candidate v0.1 report  
Output status: generated local package files, not committed

## Purpose

Paper-Artifact Graph Package v0.1 adds a small local packaging layer for the already generated and already validated Paper-Artifact Graph output.

It answers one operational question:

```text
Can the local graph candidate be packaged into a portable local archive without changing graph data or runtime behavior?
```

This is not publication. It is a local packaging step after the graph release-candidate gate.

## Position in architecture

The graph line now has this sequence:

```text
contract
→ builder
→ output validator
→ inspection / QA report
→ query CLI
→ release-candidate readiness gate
→ package builder
→ package validator
```

The package slice depends on the already generated graph output:

```text
data/graphs/paper_artifact_graph/v0.1/
```

and on the latest release-candidate report:

```text
artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.json
artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.md
```

The package builder refuses to package a graph if the release-candidate report is not green.

## Tracked files

```text
configs/paper_artifact_graph_package.yaml
scripts/export/package_paper_artifact_graph.py
scripts/validation/check_paper_artifact_graph_package.py
tests/smoke/test_paper_artifact_graph_package.py
docs/paper_artifact_graph_package_v0.md
```

## Generated output

Generated local package output:

```text
data/graphs/paper_artifact_graph/packages/v0.1/
├── paper_artifact_graph_v0.1.zip
├── package_manifest.json
├── README.md
└── checksums.txt
```

This directory is generated output and should remain ignored by Git.

## Archive contents

The package archive contains graph output files plus release-candidate evidence:

```text
paper_artifact_graph_v0.1/nodes.jsonl
paper_artifact_graph_v0.1/edges.jsonl
paper_artifact_graph_v0.1/schema.json
paper_artifact_graph_v0.1/manifest.json
paper_artifact_graph_v0.1/data_quality_summary.json
paper_artifact_graph_v0.1/README.md
paper_artifact_graph_v0.1/checksums.txt
paper_artifact_graph_v0.1/validation/paper_artifact_graph_release_candidate_latest.json
paper_artifact_graph_v0.1/validation/paper_artifact_graph_release_candidate_latest.md
```

Accepted local package size from the first validated run:

```text
zip_size_bytes=14930380
included_files_count=9
```

The exact zip size may change if source graph output or validation reports are regenerated. The validator checks structure, manifest, checksums, counters, and safety boundaries rather than requiring a fixed zip byte size.

## Config

Config path:

```text
configs/paper_artifact_graph_package.yaml
```

Important config identity:

```text
schema_version=paper_artifact_graph_package_config_v1
package.name=paper_artifact_graph
package.version=v0.1
package.status=local_package_candidate
package.archive_name=paper_artifact_graph_v0.1.zip
package.archive_root=paper_artifact_graph_v0.1
package.publication_ready=false
package.manual_review_required=true
package.may_be_used_as_reconcile_input=false
```

Required graph files:

```text
nodes.jsonl
edges.jsonl
schema.json
manifest.json
data_quality_summary.json
README.md
checksums.txt
```

Accepted graph counters:

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

## Package builder

Builder path:

```text
scripts/export/package_paper_artifact_graph.py
```

Dry run:

```bat
python -m scripts.export.package_paper_artifact_graph --dry-run
```

Expected dry-run evidence:

```text
schema_version=paper_artifact_graph_package_dry_run_v1
dry_run=true
included_files_count=9
release_candidate.summary_ok=true
release_candidate.required_failed_count=0
release_candidate.technical_graph_candidate_ready=true
release_candidate.manual_review_required=true
release_candidate.publication_ready=false
graph.quality_summary.nodes_count=68385
graph.quality_summary.edges_count=163757
```

Create or refresh the local package:

```bat
python -m scripts.export.package_paper_artifact_graph --force
```

Expected result:

```text
schema_version=paper_artifact_graph_package_result_v1
ok=true
dry_run=false
included_files_count=9
zip_path=data/graphs/paper_artifact_graph/packages/v0.1/paper_artifact_graph_v0.1.zip
```

The builder writes only local package files. It does not rebuild graph output.

## Package validator

Validator path:

```text
scripts/validation/check_paper_artifact_graph_package.py
```

Validation command:

```bat
python -m scripts.validation.check_paper_artifact_graph_package --strict
```

Accepted local result:

```text
{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 10,
  "warning_count": 0
}
```

The validator checks:

```text
package files exist
package manifest is readable
package manifest schema is correct
package safety flags preserve candidate boundaries
package boundaries preserve project invariants
embedded release-candidate summary is green
packaged graph counters match accepted v0.1 baseline
package checksums match
zip archive is readable
zip contains all manifest-listed included files
```

Generated validation reports:

```text
artifacts/reports/validation/paper_artifact_graph_package_latest.json
artifacts/reports/validation/paper_artifact_graph_package_latest.md
artifacts/reports/validation/history/paper_artifact_graph_package_<run_ts>.json
artifacts/reports/validation/history/paper_artifact_graph_package_<run_ts>.md
```

Generated reports are operational evidence and are not committed by default.

## Smoke tests

Smoke test path:

```text
tests/smoke/test_paper_artifact_graph_package.py
```

Validation commands:

```bat
python -m py_compile scripts/export/package_paper_artifact_graph.py
python -m py_compile scripts/validation/check_paper_artifact_graph_package.py
python -m pytest tests/smoke/test_paper_artifact_graph_package.py -q
```

Accepted local result:

```text
5 passed
```

The tests cover:

```text
package builder + validator green path
dry-run does not write package files
failed release-candidate report is rejected
package checksum mismatch is detected
validator CLI --no-write-reports path
```

## Boundaries

This slice is local and generated-output only.

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
create a graph runtime
introduce Neo4j
introduce NetworkX runtime
introduce GraphRAG
```

The package remains:

```text
local package candidate
not canonical truth
not a reconcile input
not publication-ready
manual review required before publication
```

## Git hygiene

Commit tracked files only:

```text
configs/paper_artifact_graph_package.yaml
scripts/export/package_paper_artifact_graph.py
scripts/validation/check_paper_artifact_graph_package.py
tests/smoke/test_paper_artifact_graph_package.py
docs/paper_artifact_graph_package_v0.md
docs/roadmap.md
docs/refresh_contract_v1.md
```

Do not commit generated package output:

```text
data/graphs/paper_artifact_graph/packages/v0.1/
```

Do not commit generated validation report history unless an explicit artifact-retention policy is added.

## Relationship to publication

This package is a portability artifact, not a public release.

A future publication slice would require a separate decision and review layer:

```text
license review
provenance review
PII / sensitive content review
README/public docs review
publication target decision
manual release approval
```

No public upload is performed in this slice.

## Next possible steps

After Package v0.1 is merged, the paper-artifact graph line has a complete local candidate path:

```text
generated graph
→ inspected graph
→ queryable graph
→ release-candidate checked graph
→ locally packaged graph
```

Reasonable future directions:

```text
Paper-Artifact Graph Manual Review Checklist v0.1
Paper-Artifact Graph API Design v0.1
Paper-Artifact Graph UI Explorer v0.1
Paper-Artifact Graph Analytics v0.1
Citation / Reference Graph Contract v0.1
```

The citation/reference graph should remain a separate derived graph line and should not be mixed into the paper-artifact package slice.
