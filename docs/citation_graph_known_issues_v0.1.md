# Citation Graph Known Issues v0.1

## Document status

```text
document = operator-facing known-issues checkpoint
scope = Citation Graph local-inspection API and current v0.1 graph evidence
canonical_truth = false
may_be_used_as_reconcile_input = false
mutates_graph_artifacts = false
mutates_canonical_documents = false
mutates_retrieval_artifacts = false
mutates_postgres = false
mutates_qdrant = false
mutates_api = false
mutates_ui = false
publishes_graph = false
manual_review_required = true
manual_review_complete = false
publication_ready = false
```

This document records the accepted limitations of the current Citation / Reference
Graph v0.1 and its seven-route local-inspection API surface.

It is not a defect backlog that authorizes broad implementation work. Some items
below are intentional v0.1 boundaries. Any change that promotes the graph into a
full runtime, graph database, GraphRAG subsystem, publication surface, or source
of paper truth requires a separate accepted design slice.

The paper-level source of truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

---

## 1. Evidence coverage is metadata-only

Current graph edges are derived from explicit metadata reference fields.

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
not_a_complete_citation_index = true
```

Consequences:

- absence of an edge does not prove absence of a citation;
- references present only in PDF/full-text bibliography sections are not covered;
- provider metadata coverage and formatting differences affect graph completeness;
- graph counts must not be interpreted as publication-grade bibliometrics.

---

## 2. Reference resolution remains limited

Accepted v0.1 counters:

```text
paper_references_paper = 6,165
paper_references_external = 703,234
reference_resolution_ratio = 0.00869
```

Most explicit reference observations remain unresolved `external_reference`
nodes. This is preserved evidence, not silent data loss.

```text
external_reference_is_unresolved = true
not_publication_grade_reference_entity = true
```

A higher resolution ratio would require a separate normalization/alignment slice
with dedicated regression evidence. It must not be achieved through aggressive
identity collapse.

---

## 3. Incoming citations are resolved-internal evidence only

```text
GET /citation-graph/papers/{canonical_id}/citations
```

returns only resolved `paper_references_paper` edges.

It does not include unresolved external references that may eventually map to the
paper. Therefore its counts are lower bounds over the current resolved graph, not
global citation counts.

---

## 4. Source-family diagnostics are not source coverage metrics

```text
GET /citation-graph/source-families
```

summarizes reference evidence associated with source-family provenance.

```text
source_family_reference_evidence_only = true
not_source_coverage_metric = true
```

The endpoint must not be used to rank providers or infer complete provider
coverage. Source-family nodes derive from canonical provenance rows, not from
`source_ids` alone.

---

## 5. Top-reference diagnostics are not bibliometric rankings

```text
GET /citation-graph/top-referenced-papers
```

uses resolved internal reference-edge counts only.

```text
resolved_internal_reference_count_only = true
not_global_citation_metric = true
not_publication_grade_ranking = true
```

```text
GET /citation-graph/top-external-references
```

uses unresolved external-reference evidence only.

```text
external_reference_is_unresolved = true
not_publication_grade_reference_entity = true
not_global_citation_metric = true
not_publication_grade_ranking = true
```

Neither endpoint is a replacement for provider citation counts, scholarly impact
metrics, or publication-grade entity resolution.

---

## 6. The API is local-inspection only

Current accepted surface:

```text
GET /citation-graph/status
GET /citation-graph/papers/{canonical_id}/references
GET /citation-graph/papers/{canonical_id}/citations
GET /citation-graph/external-references/{reference_id}/papers
GET /citation-graph/source-families
GET /citation-graph/top-referenced-papers
GET /citation-graph/top-external-references
```

Boundary:

```text
disabled_by_default = true
feature_flag = ML_RADAR_CITATION_GRAPH_API_ENABLED
exposure_mode = local_inspection
full_graph_runtime_loader = not implemented
graph_db_materialization = not implemented
full_graph_visualization_ui = not implemented
graphrag = not implemented
```

The file-backed `CitationGraphStore` is a bounded local query core. It is not a
promoted general graph runtime.

---

## 7. Store loading is intentionally whole-file and bounded by cache

The current store loads local `nodes.jsonl` and `edges.jsonl` into memory for
bounded local inspection.

```text
citation_graph_store_cache = bounded_by_graph_root
citation_graph_store_cache_maxsize = 2
citation_graph_store_cache_clear_on_reload = implemented
```

Known operational implication:

- the first traversal request after process start or cache invalidation may be
  comparatively expensive;
- a valid cached store remains in use until explicit cache invalidation;
- `POST /reload` clears the store cache but does not rebuild graph artifacts;
- failed loads are not cached;
- repaired files can be retried without restarting the API process.

This behavior is accepted for the current local-inspection surface. Promotion to
incremental loading, memory mapping, a graph database, or another runtime model
requires a separate design and performance slice.

---

## 8. Graph failures remain isolated from general API health

Accepted failure contract:

```text
missing graph artifact -> 503 graph_artifacts_not_found
invalid JSON / JSONL -> 503 graph_artifacts_invalid
filesystem OSError -> 503 graph_artifacts_invalid
```

Citation Graph failures must not make these general surfaces unhealthy:

```text
GET /health
GET /info
GET /runtime
GET /search
Discovery API
Postgres serving
Qdrant diagnostics / experimental serving
```

The graph remains an optional derived evidence layer.

---

## 9. Manual review and publication remain blocked

```text
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

A green technical validator, green live smoke, or `summary.ok=true` does not mean
manual approval and does not authorize publication.

The live smoke report is operational evidence only:

```text
citation_graph_live_smoke = operator_facing_opt_in
citation_graph_live_smoke_dod_gate = not_required
```

---

## 10. Current accepted next step

After live-smoke and known-issues hardening, the next safe slice is:

```text
Citation Graph Manual-Review Evidence Preparation v0.1
```

That slice may prepare evidence for selected pending review categories. It must
not silently mark review complete, change publication readiness, or introduce a
new runtime surface.
