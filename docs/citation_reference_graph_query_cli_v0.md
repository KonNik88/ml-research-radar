# Citation / Reference Graph Query CLI v0.1

## Status

```text
status = local read-only query CLI
scope = offline queries over generated citation/reference graph output
publication_status = not_published
runtime_status = not_runtime
```

This slice adds a small offline command-line query surface over the generated
Citation / Reference Graph v0.1 output.

It does not build graph output, mutate canonical truth, materialize anything to
Postgres, expose any API/UI surface, or require a graph runtime.

---

## Purpose

The CLI answers practical local inspection questions over the already generated
citation/reference graph:

```text
paper -> outgoing references
paper <- incoming internal citing papers
external_reference -> citing papers
top internal referenced canonical papers
top unresolved external references
source_family -> reference-bearing papers
```

This gives a lightweight query layer before any release-candidate/package/API/UI
or graph-runtime decision.

---

## Input

Primary generated graph input:

```text
data/graphs/citation_reference_graph/v0.1/
├── nodes.jsonl
├── edges.jsonl
├── schema.json
├── manifest.json
├── data_quality_summary.json
├── README.md
└── checksums.txt
```

The graph output is local, derived, rebuildable, and ignored by Git.

---

## Important v0.1 caveat

This graph is built from explicit canonical metadata reference fields only:

```text
referenced_dois
referenced_arxiv_ids
referenced_ids
```

It does not parse:

```text
paper full text
PDFs
HTML body text
bibliography/reference sections
in-text citation contexts
raw reference strings without metadata identifiers
```

Unresolved references are preserved as `external_reference` nodes. A low internal
resolution ratio is expected for v0.1 because the current canonical corpus is a
curated 60,954-paper ML/AI corpus, not a complete OpenAlex/Semantic Scholar/
Crossref universe.

Current accepted inspection diagnostics after the reference-id normalization fix:

```text
nodes_count = 529295
edges_count = 745516
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference_resolution_ratio = 0.00869
```

OpenAlex references from `referenced_ids` are normalized as `openalex_id` values, for example `openalex_id:W2194775991`, rather than DOI-like URL values.

---

## Tracked files

```text
scripts/graph/query_citation_reference_graph.py
tests/smoke/test_citation_reference_graph_query_cli.py
docs/citation_reference_graph_query_cli_v0.md
```

No generated reports are written by the CLI.

---

## Supported selectors

Exactly one selector must be provided.

### Paper outgoing references

```bat
python -m scripts.graph.query_citation_reference_graph --paper <canonical_id> --top-k 20
```

Returns:

```text
internal_references
external_references
source_families
```

### Incoming internal citations to a canonical paper

```bat
python -m scripts.graph.query_citation_reference_graph --cited-paper <canonical_id> --top-k 20
```

Returns canonical papers that cite the selected canonical paper through internal
`paper_references_paper` edges.

### Papers citing an unresolved external reference

```bat
python -m scripts.graph.query_citation_reference_graph --external-reference <reference_key_or_node_id_or_normalized_value> --top-k 20
```

The selector accepts:

```text
external_reference:<node_hash>
doi:<normalized_doi>
openalex_id:<normalized_openalex_id>
semantic_scholar_id:<normalized_s2_id>
raw normalized value
```

### Top internal referenced canonical papers

```bat
python -m scripts.graph.query_citation_reference_graph --top-referenced-papers --top-k 20
```

Ranks canonical papers by incoming `paper_references_paper` edge count.

### Top unresolved external references

```bat
python -m scripts.graph.query_citation_reference_graph --top-external-references --top-k 20
```

Ranks unresolved `external_reference` nodes by citing-paper edge count.

### Source-family reference evidence

```bat
python -m scripts.graph.query_citation_reference_graph --source-family openalex_alignment --top-k 20
```

Returns papers with reference evidence observed through the selected source
family via `paper_has_reference_source_family` edges.

---

## Output formats

Default JSON:

```bat
python -m scripts.graph.query_citation_reference_graph --top-external-references --top-k 10
```

Markdown:

```bat
python -m scripts.graph.query_citation_reference_graph --top-external-references --top-k 10 --format markdown
```

Every payload includes metadata and the v0.1 caveat:

```text
graph_name = citation_reference_graph
graph_version = v0.1
read_only = true
reference_resolution_ratio = 0.00869
```

---

## Validation

Recommended validation sequence:

```bat
python -m py_compile scripts/graph/query_citation_reference_graph.py
python -m pytest tests/smoke/test_citation_reference_graph_query_cli.py -q
python -m scripts.graph.query_citation_reference_graph --top-referenced-papers --top-k 5
python -m scripts.graph.query_citation_reference_graph --top-external-references --top-k 5 --format markdown
```

Expected smoke result:

```text
8 passed
```

The live CLI smoke commands should return `found=true` when the generated graph
output exists and contains accepted Citation / Reference Graph Builder v0.1 data.

---

## Boundary

This slice is intentionally read-only:

```text
no graph rebuild
no generated validation reports by default
no DB materialization
no DB schema change
no public graph API
no Streamlit graph UI
no NetworkX runtime
no Neo4j runtime
no GraphRAG
no publication
no package
no canonical refresh/reconcile
no retrieval rebuild
no embedding model replacement
no Qdrant promotion
no ranking changes
```

The CLI is an offline local query tool over generated graph artifacts. It is not
a serving contract and must not be treated as canonical paper truth.

---

## Future work

The full citation graph should remain a later staged line, for example:

```text
full-text / PDF acquisition policy
→ bibliography/reference-section extraction
→ parsed reference table
→ DOI/arXiv/title-year resolver
→ confidence scoring
→ persistent derived citation-reference evidence table
→ graph enrichment builder
→ validation and review gates
```

That future line should store extracted evidence in a durable derived layer, not
reparse full text on every query.
