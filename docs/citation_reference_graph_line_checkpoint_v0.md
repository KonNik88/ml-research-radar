# Citation / Reference Graph Line Checkpoint v0.1

Status: implemented local read-only line checkpoint
Slice: `graph/citation-reference-graph-line-checkpoint-v01`
Input: completed Citation / Reference Graph v0.1 local graph line artifacts, package output, and reports
Output status: generated validation reports, not committed by default

## Purpose

Citation / Reference Graph Line Checkpoint v0.1 is the final local checkpoint gate for the completed Citation / Reference Graph v0.1 line.

It answers one operational question:

```text
Is the whole local citation/reference graph line internally complete and safe to treat as a closed checkpoint?
```

This slice does not add a new graph feature. It aggregates evidence from the completed graph line and records a read-only checkpoint over accepted local artifacts.

## Position in the graph line

The full local citation/reference graph line is:

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
→ line checkpoint
```

The line checkpoint is intentionally after package. It reads existing files and reports. It does not rebuild the graph, recreate package output, or run heavy jobs.

## Tracked files

```text
configs/citation_reference_graph_line_checkpoint.yaml
scripts/validation/check_citation_reference_graph_line_checkpoint.py
tests/smoke/test_citation_reference_graph_line_checkpoint.py
docs/citation_reference_graph_line_checkpoint_v0.md
```

This slice also updates:

```text
docs/roadmap.md
docs/refresh_contract_v1.md
```

## Generated reports

Generated validation reports, not committed by default:

```text
artifacts/reports/validation/citation_reference_graph_line_checkpoint_latest.json
artifacts/reports/validation/citation_reference_graph_line_checkpoint_latest.md
artifacts/reports/validation/history/citation_reference_graph_line_checkpoint_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_line_checkpoint_<run_ts>.md
```

## Inputs

The checkpoint reads existing generated graph output:

```text
data/graphs/citation_reference_graph/v0.1/
```

Existing generated package output:

```text
data/graphs/citation_reference_graph/packages/v0.1/
```

And the latest green reports:

```text
artifacts/reports/validation/citation_reference_graph_output_latest.json
artifacts/reports/validation/citation_reference_graph_inspection_latest.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_package_latest.json
```

## Config

Config path:

```text
configs/citation_reference_graph_line_checkpoint.yaml
```

Important config identity:

```text
schema_version=citation_reference_graph_line_checkpoint_config_v1
checkpoint.name=citation_reference_graph_line_checkpoint
checkpoint.version=v0.1
checkpoint.status=local_line_checkpoint
checkpoint.publication_ready=false
checkpoint.manual_review_required=true
checkpoint.manual_review_complete=false
checkpoint.may_be_used_as_reconcile_input=false
```

Accepted line components:

```text
contract=accepted_contract_only
builder=accepted_local_derived_builder
output_validator=accepted_strict_validator
reference_normalization_fix=accepted_openalex_reference_id_normalization
inspection=accepted_read_only_inspection
query_cli=accepted_read_only_query_cli
docs_counter_refresh=accepted_docs_counter_refresh
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
citation_reference_graph_v0.1.zip
package_manifest.json
README.md
checksums.txt
```

## Accepted graph counters

```text
nodes_count=529295
edges_count=745516
paper_nodes_count=60954
external_reference_nodes_count=468336
source_family_nodes_count=5
paper_references_paper_edges_count=6165
paper_references_external_edges_count=703234
paper_has_reference_source_family_edges_count=36117
reference_resolution_ratio=0.00869
```

## Validator

Validator path:

```text
scripts/validation/check_citation_reference_graph_line_checkpoint.py
```

Validation command:

```bat
python -m scripts.validation.check_citation_reference_graph_line_checkpoint --strict
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

The exact `total_checks` may change only if the validator is intentionally extended. The important green-state semantics are `ok=true`, `required_failed_count=0`, and `warning_count=0`.

The validator checks:

```text
line checkpoint config schema
line checkpoint identity and safety flags
accepted line component statuses
required graph-line tracked files are present
required graph output files are present
graph manifest is readable
graph manifest identity is citation_reference_graph / v0.1
graph manifest safety flags preserve derived-layer boundaries
graph counters match accepted post-normalization baseline
output validator report is green
inspection report is green
release-candidate report is green
package report is green
required package files are present
package manifest is readable
package manifest safety flags preserve checkpoint boundaries
package manifest graph counters match accepted baseline
package zip is readable
```

## Smoke tests

Smoke test path:

```text
tests/smoke/test_citation_reference_graph_line_checkpoint.py
```

Validation commands:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_line_checkpoint.py
python -m pytest tests/smoke/test_citation_reference_graph_line_checkpoint.py -q
python -m scripts.validation.check_citation_reference_graph_line_checkpoint --strict
```

Expected local result:

```text
5 passed
ok=true
required_failed_count=0
warning_count=0
```

The tests cover:

```text
complete fixture passes
failed package report is detected
graph count mismatch is detected
unsafe package manifest is detected
validator CLI --no-write-reports path
```

## Boundaries

This slice is read-only and checkpoint-only.

It does not:

```text
rebuild graph output
rebuild package output
mutate canonical truth
change reconcile behavior
change Postgres
change DB schema
change Qdrant
change retrieval
change ranking
change API
change Streamlit UI
publish a graph
publish a dataset
create a latest pointer
create a graph runtime
introduce NetworkX runtime
introduce Neo4j
introduce GraphRAG
parse full text
parse PDFs
parse bibliography/reference sections
```

The line checkpoint remains:

```text
local checkpoint evidence
not canonical truth
not a reconcile input
not a DB source
not a runtime graph
not publication-ready
manual review required before publication or exposure
```

## Git hygiene

Commit tracked files only:

```text
configs/citation_reference_graph_line_checkpoint.yaml
scripts/validation/check_citation_reference_graph_line_checkpoint.py
tests/smoke/test_citation_reference_graph_line_checkpoint.py
docs/citation_reference_graph_line_checkpoint_v0.md
docs/roadmap.md
docs/refresh_contract_v1.md
```

Do not commit generated graph output:

```text
data/graphs/citation_reference_graph/v0.1/
```

Do not commit generated package output:

```text
data/graphs/citation_reference_graph/packages/v0.1/
```

Do not commit generated validation report history unless an explicit artifact-retention policy is added.

## Relationship to publication

This checkpoint does not publish anything.

A future publication or external exposure path would require a separate manual review path:

```text
license / redistribution review
provider terms review
citation/reference limitations review
unresolved external-reference caveat review
source-family evidence review
README/public docs review
publication target decision
manual release approval
```

## Completion meaning

After this checkpoint is green, the local Citation / Reference Graph v0.1 line is complete as a derived local artifact path:

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
Citation / Reference Graph Manual Review Checklist v0.1
Citation / Reference Graph API Design v0.1
Citation / Reference Graph Analytics v0.1
Citation / Reference Graph DB Materialization Design v0.1
```

API, UI, DB materialization, runtime graph, GraphRAG, and publication must remain separate from this checkpoint.
