# Citation / Reference Graph Package v0.1

Status: implemented local package candidate layer
Slice: `graph/citation-reference-graph-package-v01`
Input: generated Citation / Reference Graph Builder v0.1 output and green Release Candidate v0.1 report
Output status: generated local package files, not committed

## Purpose

Citation / Reference Graph Package v0.1 adds a small local packaging layer for the already generated and already release-candidate-validated Citation / Reference Graph output.

It answers one operational question:

```text
Can the local citation/reference graph candidate be packaged into a portable local archive without changing graph data or runtime behavior?
```

This is not publication. It is a local packaging step after the graph release-candidate gate.

## Position in architecture

The citation/reference graph line now has this sequence:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection / QA report
→ query CLI
→ docs counter refresh
→ release-candidate readiness gate
→ package builder
→ package validator
```

The package slice depends on the already generated graph output:

```text
data/graphs/citation_reference_graph/v0.1/
```

and on the latest release-candidate report:

```text
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.md
```

The package builder refuses to package a graph if the release-candidate report is not green.

## Tracked files

```text
configs/citation_reference_graph_package.yaml
scripts/export/package_citation_reference_graph.py
scripts/validation/check_citation_reference_graph_package.py
tests/smoke/test_citation_reference_graph_package.py
docs/citation_reference_graph_package_v0.md
```

This slice also updates:

```text
docs/roadmap.md
docs/refresh_contract_v1.md
```

## Generated output

Generated local package output:

```text
data/graphs/citation_reference_graph/packages/v0.1/
├── citation_reference_graph_v0.1.zip
├── package_manifest.json
├── README.md
└── checksums.txt
```

This directory is generated output and should remain ignored by Git.

## Archive contents

The package archive contains graph output files plus release-candidate evidence:

```text
citation_reference_graph_v0.1/nodes.jsonl
citation_reference_graph_v0.1/edges.jsonl
citation_reference_graph_v0.1/schema.json
citation_reference_graph_v0.1/manifest.json
citation_reference_graph_v0.1/data_quality_summary.json
citation_reference_graph_v0.1/README.md
citation_reference_graph_v0.1/checksums.txt
citation_reference_graph_v0.1/validation/citation_reference_graph_release_candidate_latest.json
citation_reference_graph_v0.1/validation/citation_reference_graph_release_candidate_latest.md
```

The exact zip size may change if source graph output or validation reports are regenerated. The validator checks structure, manifest, checksums, counters, and safety boundaries rather than requiring a fixed zip byte size.

## Config

Config path:

```text
configs/citation_reference_graph_package.yaml
```

Important config identity:

```text
schema_version=citation_reference_graph_package_config_v1
package.name=citation_reference_graph
package.version=v0.1
package.status=local_package_candidate
package.archive_name=citation_reference_graph_v0.1.zip
package.archive_root=citation_reference_graph_v0.1
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

## Package builder

Builder path:

```text
scripts/export/package_citation_reference_graph.py
```

Dry run:

```bat
python -m scripts.export.package_citation_reference_graph --dry-run
```

Expected dry-run evidence:

```text
schema_version=citation_reference_graph_package_dry_run_v1
dry_run=true
included_files_count=9
release_candidate.summary_ok=true
release_candidate.required_failed_count=0
release_candidate.technical_graph_candidate_ready=true
release_candidate.manual_review_required=true
release_candidate.manual_review_complete=false
release_candidate.publication_ready=false
graph.counts.nodes_count=529295
graph.counts.edges_count=745516
```

Create or refresh the local package:

```bat
python -m scripts.export.package_citation_reference_graph --force
```

Expected result:

```text
schema_version=citation_reference_graph_package_result_v1
ok=true
dry_run=false
included_files_count=9
zip_path=data/graphs/citation_reference_graph/packages/v0.1/citation_reference_graph_v0.1.zip
```

The builder writes only local package files. It does not rebuild graph output.

## Package validator

Validator path:

```text
scripts/validation/check_citation_reference_graph_package.py
```

Validation command:

```bat
python -m scripts.validation.check_citation_reference_graph_package --strict
```

Expected local result:

```text
{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
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
packaged graph counters match accepted post-normalization v0.1 baseline
package checksums match
zip archive is readable
zip contains all manifest-listed included files
```

Generated validation reports:

```text
artifacts/reports/validation/citation_reference_graph_package_latest.json
artifacts/reports/validation/citation_reference_graph_package_latest.md
artifacts/reports/validation/history/citation_reference_graph_package_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_package_<run_ts>.md
```

Generated reports are operational evidence and are not committed by default.

## Smoke tests

Smoke test path:

```text
tests/smoke/test_citation_reference_graph_package.py
```

Validation commands:

```bat
python -m py_compile scripts/export/package_citation_reference_graph.py
python -m py_compile scripts/validation/check_citation_reference_graph_package.py
python -m pytest tests/smoke/test_citation_reference_graph_package.py -q
```

Expected local result:

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
change reconcile behavior
change Postgres
change DB schema
change Qdrant
change retrieval
change ranking
change API
change Streamlit UI
parse paper full text
parse PDFs
parse bibliography/reference sections
publish a dataset
publish a graph
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
configs/citation_reference_graph_package.yaml
scripts/export/package_citation_reference_graph.py
scripts/validation/check_citation_reference_graph_package.py
tests/smoke/test_citation_reference_graph_package.py
docs/citation_reference_graph_package_v0.md
docs/roadmap.md
docs/refresh_contract_v1.md
```

Do not commit generated package output:

```text
data/graphs/citation_reference_graph/packages/v0.1/
```

Do not commit generated validation report history unless an explicit artifact-retention policy is added.

## Relationship to publication

This package is a portability artifact, not a public release.

A future publication slice would require a separate decision and review layer:

```text
license review
provenance review
README/public docs review
limitations review
publication target decision
manual release approval
```

## Next possible steps

After this package layer is green, the next conservative graph-line step is:

```text
Citation / Reference Graph Line Checkpoint v0.1
```

API, UI, DB materialization, NetworkX, Neo4j, and GraphRAG should remain future decisions, not implicit consequences of this package layer.
