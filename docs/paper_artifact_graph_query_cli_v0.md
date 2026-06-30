# Paper-Artifact Graph Query CLI v0.1

Status: implemented local read-only query CLI
Slice: `graph/paper-artifact-graph-query-cli-v01`
Input: generated Paper-Artifact Graph Builder v0.1 output
Output status: terminal JSON/Markdown output, not committed reports

## Purpose

Paper-Artifact Graph Query CLI v0.1 adds a small offline command-line query layer over the generated local paper-artifact graph output.

The previous graph slices established:

```text
contract
→ builder
→ output validator
→ inspection / QA report
```

This slice adds the next safe layer:

```text
offline graph query
```

The goal is to make the generated graph practically inspectable without adding API, UI, Neo4j, GraphRAG, runtime dependencies, or new source-of-truth semantics.

## Position in architecture

The query CLI reads the generated graph output:

```text
data/graphs/paper_artifact_graph/v0.1/nodes.jsonl
data/graphs/paper_artifact_graph/v0.1/edges.jsonl
data/graphs/paper_artifact_graph/v0.1/manifest.json
```

It does not mutate:

```text
canonical documents
artifact inputs
topic inputs
graph output
Postgres
Qdrant
API
UI
ranking
retrieval artifacts
validation reports
```

It is not:

```text
canonical truth
a reconcile input
a graph builder
a graph validator
an API endpoint
a UI feature
a dataset release
a Neo4j/NetworkX/GraphRAG runtime
```

## Script

```text
scripts/graph/query_paper_artifact_graph.py
```

Smoke tests:

```text
tests/smoke/test_paper_artifact_graph_query_cli.py
```

Package marker:

```text
scripts/graph/__init__.py
```

## Supported query modes

### Paper to artifacts

```bat
python -m scripts.graph.query_paper_artifact_graph --paper-id <canonical_id> --top-k 5
```

Returns:

```text
paper node
linked artifacts
topic clusters
source families
manifest safety summary
```

### Artifact to papers

```bat
python -m scripts.graph.query_paper_artifact_graph --artifact-id <artifact_id> --top-k 5
```

Returns:

```text
artifact node
linked papers
providers
manifest safety summary
```

### Provider to artifacts

```bat
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5
```

Returns:

```text
provider node
top artifacts ranked by linked paper count
total artifacts for provider
total paper-artifact links for provider
manifest safety summary
```

### Topic cluster to artifact-ready papers

```bat
python -m scripts.graph.query_paper_artifact_graph --topic-cluster 7 --top-k 5
```

Returns:

```text
topic cluster node
artifact-ready papers in the cluster
sample artifacts per paper
topic paper count
artifact-ready paper count
paper-artifact link count
manifest safety summary
```

## Output formats

Default JSON:

```bat
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5
```

Markdown:

```bat
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5 --format markdown
```

## Current accepted local examples

Provider query:

```bat
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5
```

Accepted local result:

```text
found=True
provider=github
artifacts=5953
paper_artifact_links=6019
```

Markdown provider query:

```bat
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5 --format markdown
```

Accepted behavior:

```text
renders compact Markdown output with provider counts, top artifacts, and manifest safety flags
```

Topic-cluster query:

```bat
python -m scripts.graph.query_paper_artifact_graph --topic-cluster 7 --top-k 5
```

Accepted local result:

```text
found=True
topic_cluster=7
papers=465
artifact_ready_papers=21
paper_artifact_links=21
```

Paper query:

```bat
python -m scripts.graph.query_paper_artifact_graph --paper-id ad451908b69a77d206e1c961809df1b0 --top-k 5
```

Accepted behavior:

```text
returns the selected paper, linked artifact(s), source family, and topic cluster
```

Artifact query:

```bat
python -m scripts.graph.query_paper_artifact_graph --artifact-id 297f0564ec675d8e092296b9dd23ec13 --top-k 5
```

Accepted behavior:

```text
returns the selected artifact, linked paper(s), and provider node
```

## Manifest safety summary

Every result includes:

```text
canonical_truth
may_be_used_as_reconcile_input
publication_ready
dry_run
builder_input_mode
live_db_dependency
create_latest_pointer
```

Current accepted safety values:

```text
canonical_truth=False
may_be_used_as_reconcile_input=False
publication_ready=False
dry_run=False
builder_input_mode=file
live_db_dependency=False
create_latest_pointer=False
```

## Validation commands

```bat
python -m py_compile scripts/graph/query_paper_artifact_graph.py
python -m pytest tests/smoke/test_paper_artifact_graph_query_cli.py -q
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5 --format markdown
python -m scripts.graph.query_paper_artifact_graph --topic-cluster 7 --top-k 5
```

Expected smoke result:

```text
7 passed
```

## Non-goals

This slice does not introduce:

```text
graph rebuild
graph validation changes
canonical truth changes
reconcile input changes
Postgres changes
Qdrant changes
retrieval changes
ranking changes
API endpoints
Streamlit UI
Neo4j
NetworkX runtime
GraphRAG
dataset publication
latest pointer
generated reports
```

## Known limitations

The CLI only reads fields present in the generated graph output.

If a graph artifact node does not include URL-like properties, the CLI returns:

```text
url=null
```

This is not a CLI failure. It reflects the current graph output payload. Future graph builder/output schema slices may decide whether to include richer artifact URL metadata.

## Next possible layer

After this slice is merged, possible next graph steps are:

```text
Paper-Artifact Graph Packaging v0.1
```

or:

```text
Paper-Artifact Graph API Design v0.1
```

The safer next step is packaging/export hardening before API/UI runtime integration.
