# Citation / Reference Graph Contract v0.1

## Status

```text
status = contract-only
version = v0.1
graph_family = paper_reference_evidence_graph
outputs_generated_in_this_slice = false
publication_ready = false
```

This document defines the first contract for a future **Citation / Reference Graph** in ML Research Radar.

The graph is a derived paper-to-paper and paper-to-external-reference evidence layer. It is not canonical truth, not a reconcile input, not a runtime graph, and not a public API/UI feature in this slice.

---

## Purpose

The purpose of this slice is to define the graph contract before building outputs.

The future graph should answer questions such as:

```text
Which canonical papers reference other canonical papers?
Which references cannot yet be resolved to canonical papers?
Which source families contributed reference evidence?
What reference identifiers are available and unresolved?
```

This contract intentionally does **not** answer those questions yet. It only defines the expected structure, identity policy, provenance semantics, and safety boundaries for a future builder.

---

## Source fields

The future graph will be derived from the current canonical paper layer, especially:

```text
referenced_ids
referenced_dois
referenced_arxiv_ids
references_count
cited_by_count
sources
external_ids
canonical_id
```

Important distinction:

```text
references_count / cited_by_count = diagnostic metadata
paper_references_* edges = explicit reference evidence only
```

A high `references_count` alone must not fabricate edges.

---

## Node types

Required node types:

```text
paper
external_reference
source_family
```

### `paper`

Represents a canonical ML Research Radar paper entity.

Node ID policy:

```text
paper:<canonical_id>
```

### `external_reference`

Represents a reference identifier that is present in canonical reference fields but cannot yet be resolved to a canonical paper node.

Node ID policy:

```text
external_reference:<reference_key_hash>
```

Allowed reference types:

```text
doi
arxiv_id
openalex_id
semantic_scholar_id
raw_external_id
```

Allowed resolution statuses:

```text
resolved_to_canonical
unresolved_external
```

### `source_family`

Represents source families that contributed reference-bearing evidence.

Node ID policy:

```text
source_family:<source_family>
```

Important policy:

```text
source_family nodes must derive from canonical provenance rows, not source_ids only
```

---

## Edge types

Required edge types:

```text
paper_references_paper
paper_references_external
paper_has_reference_source_family
```

### `paper_references_paper`

Represents a resolved reference from one canonical paper to another canonical paper.

Source:

```text
canonical_documents
```

Target node type:

```text
paper
```

### `paper_references_external`

Represents an unresolved reference from a canonical paper to an external reference identifier.

Source:

```text
canonical_documents
```

Target node type:

```text
external_reference
```

This preserves unresolved evidence instead of dropping it or forcing incorrect canonical matches.

### `paper_has_reference_source_family`

Represents source-family evidence related to reference fields.

Source:

```text
canonical_documents
```

Target node type:

```text
source_family
```

---

## Edge identity policy

Default edge ID policy:

```text
typed_source_target_hash
```

Required common edge fields:

```text
edge_id
edge_type
source_node_id
target_node_id
provenance_kind
source_layer
confidence
```

---

## Provenance policy

Required provenance kinds:

```text
canonical_reference
external_identifier_reference
source_family_reference
derived_summary
```

Allowed source layers:

```text
canonical_documents
canonical_reference_fields
source_provenance
```

Required policies:

```text
graph_not_reconcile_input = true
reference_edges_derived_from_canonical_fields = true
unresolved_references_stay_external = true
citation_count_not_edge_truth = true
source_ids_not_strict_provenance = true
references_count_is_diagnostic_not_edge_count_gate = true
```

---

## Safety boundaries

This slice must not:

```text
build graph outputs
change canonical truth
run reconcile
change DB schema
change API behavior
change Streamlit behavior
change retrieval behavior
change Qdrant behavior
change ranking behavior
require graph runtime
publish anything
```

The future graph must remain:

```text
derived
rebuildable
evidence-oriented
manual-review-bound before publication/exposure
```

---

## Future output layout

Future builder output may use:

```text
data/graphs/citation_reference_graph/v0.1/
├── nodes.jsonl
├── edges.jsonl
├── schema.json
├── manifest.json
├── README.md
├── data_quality_summary.json
└── checksums.txt
```

This layout is **future-layout only** in this slice.

---

## Validator

Config:

```text
configs/citation_reference_graph.yaml
```

Validator:

```text
scripts/validation/check_citation_reference_graph_contract.py
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_contract.py
```

Recommended validation:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_contract.py
python -m pytest tests/smoke/test_citation_reference_graph_contract.py -q
python -m scripts.validation.check_citation_reference_graph_contract --strict
```

Optional path-aware validation:

```bat
python -m scripts.validation.check_citation_reference_graph_contract --strict --check-paths
```

`--check-paths` remains file/path-only. It does not run DB, API, Qdrant, retrieval, or graph-runtime checks.

Generated reports, not committed by default:

```text
artifacts/reports/validation/citation_reference_graph_contract_latest.json
artifacts/reports/validation/citation_reference_graph_contract_latest.md
artifacts/reports/validation/history/citation_reference_graph_contract_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_contract_<run_ts>.md
```

---

## Non-goals

```text
no builder
no generated graph output
no package
no publication
no manual approval
no DB materialization
no public graph API
no Streamlit graph UI
no NetworkX runtime
no Neo4j runtime
no GraphRAG
no canonical refresh/reconcile
no retrieval rebuild
no embedding model replacement
no Qdrant promotion
no ranking changes
```

---

## Future slices

Recommended future order:

```text
Citation / Reference Graph Builder v0.1
→ Output Validator v0.1
→ Inspection / Analytics v0.1
→ Query CLI v0.1
→ Release Candidate / Package / Line Checkpoint
→ API Design v0.1
→ DB Materialization only if needed
→ Streamlit UI only after API semantics are accepted
→ optional graph runtime / GraphRAG only after quality review
```
