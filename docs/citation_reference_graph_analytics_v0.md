# Citation / Reference Graph Analytics v0.1

## Status

```text
status = local read-only analytics/report layer
schema = citation_reference_graph_analytics_v1
publication_ready = false
manual_review_support = true
```

## Purpose

Citation / Reference Graph Analytics v0.1 adds a compact read-only analytics report over the already generated Citation / Reference Graph v0.1 output.

It exists to support manual review and future API/UI/design decisions by making the generated citation/reference graph easier to inspect.

It answers questions such as:

```text
How many references are resolved to canonical papers?
How many references remain unresolved external_reference nodes?
What is the internal reference resolution ratio?
Which reference identifier types dominate?
Which source families contribute reference-bearing papers?
Which canonical papers are most frequently referenced internally?
Which unresolved external references are most common?
Are the metadata-only / no full-text parsing caveats preserved for review?
```

## Position in the citation/reference graph line

This slice follows the completed local graph line and the manual-review gate:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection
→ query CLI
→ docs counter refresh
→ release candidate
→ package
→ line checkpoint
→ manual review checklist
→ analytics report
```

Analytics is evidence/support only. It does not approve manual review and does not publish anything.

## Tracked files

```text
configs/citation_reference_graph_analytics.yaml
scripts/validation/check_citation_reference_graph_analytics.py
tests/smoke/test_citation_reference_graph_analytics.py
docs/citation_reference_graph_analytics_v0.md
```

This slice also updates:

```text
docs/roadmap.md
docs/refresh_contract_v1.md
```

## Generated reports

Generated reports are operational evidence and should not be committed by default:

```text
artifacts/reports/validation/citation_reference_graph_analytics_latest.json
artifacts/reports/validation/citation_reference_graph_analytics_latest.md
artifacts/reports/validation/history/citation_reference_graph_analytics_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_analytics_<run_ts>.md
```

## Inputs

Required graph inputs:

```text
data/graphs/citation_reference_graph/v0.1/nodes.jsonl
data/graphs/citation_reference_graph/v0.1/edges.jsonl
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
```

Required governance input:

```text
artifacts/reports/validation/citation_reference_graph_manual_review_latest.json
```

The analytics validator reads existing local files only. It does not rebuild the graph and does not read live Postgres, Qdrant, API, Streamlit, or provider state.

## Computed analytics

The report computes:

```text
node and edge counts
node and edge type counts
resolved_reference_edges_count
unresolved_reference_edges_count
reference_edges_count
reference_resolution_ratio
papers_with_outgoing_reference_edges_count
papers_with_internal_reference_edges_count
papers_with_external_reference_edges_count
papers_with_incoming_internal_reference_edges_count
papers_without_outgoing_reference_edges_count
reference type distribution
reference field distribution
source-family distribution
top internally referenced canonical papers
top unresolved external references
sample paper→paper reference edges
sample paper→external_reference edges
sample paper→source_family reference evidence edges
```

## Accepted v0.1 counters

```text
nodes_count = 529295
edges_count = 745516
paper_nodes_count = 60954
external_reference_nodes_count = 468336
source_family_nodes_count = 5
paper_references_paper_edges_count = 6165
paper_references_external_edges_count = 703234
paper_has_reference_source_family_edges_count = 36117
reference_resolution_ratio = 0.00869
```

## Citation/reference-specific caveats

The analytics layer intentionally preserves the v0.1 limitations already captured by the manual-review gate:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
raw_reference_strings_without_identifiers_parsed = false
unresolved_references_preserved_as_external_reference_nodes = true
low_resolution_ratio_expected_in_v0_1 = true
reference_resolution_ratio = 0.00869
```

The low internal resolution ratio is not treated as a validator failure in v0.1. It is a review caveat and coverage diagnostic.

## Validation semantics

The validator checks that:

```text
config schema is correct
analytics metadata is local_read_only_analytics
analytics is not publication-ready
analytics supports manual review but does not approve it
analytics cannot be used as a reconcile input
safety flags preserve read-only boundaries
required graph inputs exist and are readable
manual-review report exists, is green, and remains publication-blocked
manifest identity is Citation / Reference Graph v0.1
manifest safety flags preserve derived-layer boundaries
data_quality_summary is ok
required node and edge types are present
accepted graph counters match the post-normalization baseline
accepted reference_resolution_ratio matches the post-normalization baseline
reference analytics baseline expectations pass
required reference types are present
required source families are present
internal and external reference samples are available
manual-review caveats preserve known v0.1 limitations
```

Expected local result on the accepted graph output:

```text
ok = true
required_failed_count = 0
warning_count = 0
```

## Commands

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_analytics.py
python -m pytest tests/smoke/test_citation_reference_graph_analytics.py -q
python -m scripts.validation.check_citation_reference_graph_analytics --strict
```

Optional report-free validation:

```bat
python -m scripts.validation.check_citation_reference_graph_analytics --strict --no-write-reports
```

## Smoke tests

Smoke test path:

```text
tests/smoke/test_citation_reference_graph_analytics.py
```

The tests cover:

```text
green fixture path
no-write reports path
missing required edge type
accepted count mismatch
manifest safety drift
data_quality_summary not ok
manual-review report not green
unsafe analytics config flag
missing required reference type
manual-review caveat drift
validator CLI --no-write-reports path
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
run reconcile
change DB schema
materialize graph into Postgres
change API behavior
change Streamlit/UI behavior
change retrieval behavior
change Qdrant behavior
change ranking behavior
create a runtime graph
introduce Neo4j / NetworkX / GraphRAG runtime
parse full text
parse PDFs
parse bibliography/reference sections
parse raw reference strings without metadata identifiers
```

## Relationship to Manual Review Checklist v0.1

Manual Review Checklist v0.1 defines the governance gate.

Citation / Reference Graph Analytics v0.1 provides additional read-only evidence to help a human reviewer understand the graph/package candidate.

It does not change the manual-review verdict by itself.

Default publication state remains:

```text
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

## Relationship to Inspection v0.1

Inspection v0.1 is a compact QA/sanity layer.

Analytics v0.1 is a richer review-support layer focused on distributions, coverage summaries, top-N reference targets, and explicit caveats.

Both are read-only. Neither is canonical truth, reconcile input, publication, API/UI, DB materialization, or runtime graph.
