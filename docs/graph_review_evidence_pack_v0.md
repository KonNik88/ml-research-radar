# Graph Review Evidence Pack v0.1

## Status

```text
document = graph review evidence pack contract / operator notes
version = v0.1
status = local read-only review evidence layer
publication_ready = false
manual_review_required = true
may_be_used_as_reconcile_input = false
```

## Purpose

Graph Review Evidence Pack v0.1 consolidates local derived evidence from two completed graph lines:

- Citation / Reference Graph v0.1;
- Paper–Artifact Graph v0.1.

The pack exists to support manual review and future design decisions. It is not a publication step, runtime step, API implementation, GraphRAG step, Qdrant promotion, or graph database materialization step.

## Position in the project

```text
canonical_documents.jsonl
  = paper-level source of truth

retrieval / DB / artifacts / graph / reports / API / UI
  = derived layers

Graph Review Evidence Pack
  = local read-only report over already generated graph-line evidence
```

The evidence pack must not redefine paper identity, artifact identity, trusted-link semantics, reference semantics, source-family semantics, ranking, retrieval, API behavior, UI behavior, Postgres state, or Qdrant state.

## Inputs

Expected local inputs:

```text
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_package_latest.json
artifacts/reports/validation/citation_reference_graph_line_checkpoint_latest.json
artifacts/reports/validation/citation_reference_graph_manual_review_latest.json
artifacts/reports/validation/citation_reference_graph_analytics_latest.json

data/graphs/paper_artifact_graph/v0.1/manifest.json
data/graphs/paper_artifact_graph/v0.1/data_quality_summary.json
artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.json
artifacts/reports/validation/paper_artifact_graph_package_latest.json
artifacts/reports/validation/paper_artifact_graph_line_checkpoint_latest.json
artifacts/reports/validation/paper_artifact_graph_manual_review_latest.json
artifacts/reports/validation/paper_artifact_graph_analytics_latest.json
```

## Outputs

Generated reports are local validation artifacts and must not be committed:

```text
artifacts/reports/validation/graph_review_evidence_pack_latest.json
artifacts/reports/validation/graph_review_evidence_pack_latest.md
artifacts/reports/validation/history/graph_review_evidence_pack_<run_ts>.json
artifacts/reports/validation/history/graph_review_evidence_pack_<run_ts>.md
```

## Expected current counters

### Citation / Reference Graph v0.1

```text
nodes_count = 529295
edges_count = 745516
paper_nodes = 60954
external_reference_nodes = 468336
source_family_nodes = 5
paper_references_paper_edges = 6165
paper_references_external_edges = 703234
paper_has_reference_source_family_edges = 36117
reference_resolution_ratio = 0.00869
publication_ready = false
manual_review_required = true
manual_review_complete = false
```

Citation/reference caveats:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
unresolved_references_preserved_as_external_reference_nodes = true
```

### Paper–Artifact Graph v0.1

```text
nodes_count = 68385
edges_count = 163757
paper_nodes = 60954
artifact_nodes = 7336
provider_nodes = 10
source_family_nodes = 5
topic_cluster_nodes = 80
paper_has_artifact_edges = 7430
artifact_from_provider_edges = 7336
paper_observed_in_source_family_edges = 88037
paper_assigned_to_topic_cluster_edges = 60954
publication_ready = false
manual_review_required = true
manual_review_complete = false
```

Paper-artifact caveats:

```text
paper_has_artifact derives from trusted paper_artifact_links semantics
trusted artifact links are not raw artifact observations
legacy has_code_link is not trusted artifact evidence
graph is not artifact source of truth
```

## Validator behavior

The validator:

- loads the evidence-pack config;
- checks safety flags;
- reads graph manifests and data-quality summaries;
- reads release-candidate, package, line-checkpoint, manual-review, and analytics reports for both graph lines;
- verifies accepted counters;
- verifies manual-review and publication boundaries;
- emits one compact JSON and Markdown evidence-pack report.

The validator must be read-only with respect to graph inputs. It may only write its own validation reports unless `--no-write-reports` is used.

## Non-goals

```text
no graph rebuild
no package rebuild
no publication
no manual approval automation
no public graph API endpoint implementation
no Streamlit graph UI
no DB materialization
no DB schema change
no graph runtime
no NetworkX runtime
no Neo4j runtime
no GraphRAG
no Qdrant promotion
no canonical refresh/reconcile
no retrieval rebuild
no embedding model replacement
no ranking changes
no trusted-link policy redefinition
```

## Commands

Validate in strict mode:

```bash
python -m scripts.validation.check_graph_review_evidence_pack --strict
```

Validate without writing reports:

```bash
python -m scripts.validation.check_graph_review_evidence_pack --strict --no-write-reports
```

Run smoke tests:

```bash
python -m pytest tests/smoke/test_graph_review_evidence_pack.py -q
```

## Interpretation

A green evidence pack means:

```text
the two local graph lines have coherent review evidence;
the pack is useful for manual-review support and design planning;
manual review is still required;
publication is still blocked;
runtime/API/GraphRAG/Qdrant-promotion work is still out of scope.
```

A green evidence pack does not mean:

```text
human manual review is complete;
publication is approved;
graph data is canonical truth;
graph data may be used as reconcile input;
public graph API can be implemented without a design slice;
GraphRAG can be started without a design slice.
```
