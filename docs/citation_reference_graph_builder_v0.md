# Citation / Reference Graph Builder v0.1

## Status

```text
status = local derived builder
publication_status = not_published
runtime_status = offline_file_artifact_only
```

This slice implements the first local builder and output validator for the derived Citation / Reference Graph v0.1.

It follows the previously accepted contract in:

```text
configs/citation_reference_graph.yaml
```

The graph remains a derived evidence artifact. It is not canonical truth, not a reconcile input, not a DB source, not an API feature, and not a runtime graph.

---

## Purpose

The builder creates a local paper-reference graph from the current canonical corpus:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

The goal is to materialize reference evidence into a compact graph layout that can later be inspected and validated before any API, UI, DB, graph runtime, publication, or GraphRAG work is considered.

---

## Scope

Tracked files in this slice:

```text
scripts/export/build_citation_reference_graph.py
scripts/validation/check_citation_reference_graph_output.py
tests/smoke/test_citation_reference_graph_builder.py
tests/smoke/test_citation_reference_graph_output_validator.py
docs/citation_reference_graph_builder_v0.md
```

Generated local output, not committed:

```text
data/graphs/citation_reference_graph/v0.1/nodes.jsonl
data/graphs/citation_reference_graph/v0.1/edges.jsonl
data/graphs/citation_reference_graph/v0.1/schema.json
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
data/graphs/citation_reference_graph/v0.1/README.md
data/graphs/citation_reference_graph/v0.1/checksums.txt
```

Generated validation reports, not committed:

```text
artifacts/reports/validation/citation_reference_graph_output_latest.json
artifacts/reports/validation/citation_reference_graph_output_latest.md
artifacts/reports/validation/history/citation_reference_graph_output_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_output_<run_ts>.md
```

---

## Graph model

### Node types

```text
paper
external_reference
source_family
```

### Edge types

```text
paper_references_paper
paper_references_external
paper_has_reference_source_family
```

### Resolution policy

The builder uses canonical paper identifiers and external IDs to resolve references.

Resolution priority is conservative:

```text
canonical_id direct match
DOI match
arXiv ID match
OpenAlex ID match
Semantic Scholar ID match
otherwise unresolved external reference
```

Unresolved references are preserved as `external_reference` nodes instead of being dropped or forced into paper nodes.

`references_count` and `cited_by_count` are diagnostic fields only. They are not treated as edge truth.

---

## Builder command

Dry run:

```bat
python -m scripts.export.build_citation_reference_graph --dry-run
```

Build local output:

```bat
python -m scripts.export.build_citation_reference_graph --force
```

Optional explicit paths:

```bat
python -m scripts.export.build_citation_reference_graph ^
  --config configs/citation_reference_graph.yaml ^
  --canonical-path data/analytics/reconciled/canonical_documents.jsonl ^
  --output-dir data/graphs/citation_reference_graph/v0.1 ^
  --force
```

The builder is file-first and has no live DB dependency.

---

## Output validation

```bat
python -m scripts.validation.check_citation_reference_graph_output --strict
```

The output validator checks:

```text
required graph output files exist
JSON/JSONL files are readable
required node types are present
required edge types are present
node IDs are unique
edge IDs are unique
edges reference existing nodes
common edge fields are present
edge confidence values are in [0, 1]
schema identity is correct
manifest identity is correct
manifest input mode is file
manifest has no live DB dependency
data_quality_summary is green
manifest safety flags preserve derived-layer boundaries
paper node count matches expected canonical doc count when not using a limit
manifest counts match actual files
data_quality_summary counts match actual files
checksums cover required files
checksums match current files
```

---

## Recommended local validation sequence

```bat
python -m py_compile scripts/export/build_citation_reference_graph.py
python -m py_compile scripts/validation/check_citation_reference_graph_output.py
python -m pytest tests/smoke/test_citation_reference_graph_builder.py tests/smoke/test_citation_reference_graph_output_validator.py -q
python -m scripts.export.build_citation_reference_graph --dry-run
python -m scripts.export.build_citation_reference_graph --force
python -m scripts.validation.check_citation_reference_graph_output --strict
```

The final command writes the latest/history validation reports under:

```text
artifacts/reports/validation/
```

Those reports are local operational evidence and are not committed by default.

---

## Boundaries

This slice intentionally does not add:

```text
public graph API
Streamlit graph UI
DB schema changes
Postgres graph materialization
NetworkX runtime
Neo4j runtime
GraphRAG
Qdrant changes
retrieval rebuild
embedding model replacement
ranking changes
canonical refresh/reconcile
publication/export release
```

The graph output must not be used as a reconcile input.

---

## Future slices

Possible future work after this builder is green:

```text
Citation / Reference Graph Inspection v0.1
Citation / Reference Graph Query CLI v0.1
Citation / Reference Graph Release Candidate v0.1
Citation / Reference Graph Package v0.1
Citation / Reference Graph Line Checkpoint v0.1
Citation / Reference Graph API Design v0.1
```

API, UI, DB, NetworkX, Neo4j, and GraphRAG should remain future decisions, not implicit consequences of this builder.
