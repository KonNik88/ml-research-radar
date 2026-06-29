# Paper-Artifact Graph Builder v0.1

Status: implemented local derived builder
Slice: `graph/paper-artifact-graph-builder-v01`
Output status: local generated artifact, not committed
Graph version: `v0.1`

## Purpose

Paper-Artifact Graph Builder v0.1 builds the first local derived graph artifact for ML Research Radar from accepted file-backed layers.

It turns the already accepted project layers into a graph-shaped representation:

- canonical papers
- extracted artifact entities
- trusted paper-artifact links
- provider nodes
- canonical source-family evidence
- topic-cluster assignments

The builder does not create new canonical truth. It only materializes a derived representation of existing accepted data.

## Position in architecture

Canonical truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

The graph is downstream of canonical and enriched layers:

```text
canonical_documents
  + artifact_entities_latest
  + artifact_links_latest
  + topic latest assignments
  -> local derived paper-artifact graph
```

The graph is not:

- a reconcile input
- a canonical document source
- a Postgres replacement
- a retrieval artifact
- a Qdrant artifact
- a ranking input
- a public dataset release

## Contract relationship

The graph contract remains in:

```text
configs/paper_artifact_graph.yaml
```

That file describes the graph semantics and remains contract-only.

The builder execution config is separate:

```text
configs/paper_artifact_graph_builder.yaml
```

This separation is intentional:

```text
paper_artifact_graph.yaml
= what the graph means

paper_artifact_graph_builder.yaml
= how the local v0.1 graph artifact is built
```

The builder config points to the contract config and requires the contract to stay:

```text
graph.status = contract_only
outputs.status = future_layout_only
generated_in_this_slice = false
```

## Inputs

Required file-backed inputs:

```text
data/analytics/reconciled/canonical_documents.jsonl
data/enriched/artifact_links/artifact_entities_latest.jsonl
data/enriched/artifact_links/artifact_links_latest.jsonl
artifacts/clusters/topic/latest.json
```

Optional inputs are listed in config but disabled for v0.1:

```text
data/enriched/github_artifacts/github_artifact_metadata_latest.jsonl
data/enriched/huggingface_artifacts/huggingface_artifact_metadata_latest.jsonl
data/features/paper_features_latest.jsonl
```

In v0.1:

```text
include_topic_clusters = true
include_paper_features = false
include_provider_metadata = false
```

## Trusted links

Trusted paper-artifact links are produced from artifact observations through the shared helper:

```text
radar_core/artifacts/trusted_links.py
```

The helper is used by:

```text
scripts/export/export_artifacts_postgres_v1.py
scripts/validation/check_artifact_links_quality.py
scripts/export/build_paper_artifact_graph.py
```

This avoids a third copy of trusted-link policy in the graph builder.

Trusted link policy version:

```text
artifact_trusted_links_policy_v1
```

Trusted link dedupe key:

```text
canonical_id
artifact_id
relation_type
```

The builder does not create a global `paper_artifact_links_latest.jsonl` bridge. If such a bridge is needed later, it should be a separate slice.

## Outputs

Local graph output directory:

```text
data/graphs/paper_artifact_graph/v0.1
```

Generated files:

```text
nodes.jsonl
edges.jsonl
schema.json
manifest.json
data_quality_summary.json
README.md
checksums.txt
```

This directory is ignored by Git:

```text
/data/graphs/
```

Generated graph outputs should not be committed in this slice.

## Output format

v0.1 writes JSONL:

```text
nodes.jsonl
edges.jsonl
```

The earlier graph contract describes future layout, but parquet/publication packaging is not part of this slice.

JSONL is used here because the first goal is a simple, inspectable, reproducible local derived artifact.

## Node types

Required node types:

```text
paper
artifact
provider
source_family
topic_cluster
```

Node ID policy:

```text
paper:{canonical_id}
artifact:{artifact_id}
provider:{provider}
source_family:{source_family}
topic_cluster:{cluster_id}
```

## Edge types

Required edge types:

```text
paper_has_artifact
artifact_from_provider
paper_observed_in_source_family
paper_assigned_to_topic_cluster
```

Important edge semantics:

```text
paper_has_artifact
= canonical paper -> artifact entity
= built only from trusted artifact observations

artifact_from_provider
= artifact entity -> provider

paper_observed_in_source_family
= canonical paper -> source family
= derived from canonical `sources`, not from `source_ids`

paper_assigned_to_topic_cluster
= canonical paper -> topic cluster
= derived from topic assignments resolved via artifacts/clusters/topic/latest.json
```

## Real build result

The accepted local build produced:

```text
nodes_count = 68385
edges_count = 163757
```

Node type counts:

```text
artifact = 7336
paper = 60954
provider = 10
source_family = 5
topic_cluster = 80
```

Edge type counts:

```text
artifact_from_provider = 7336
paper_assigned_to_topic_cluster = 60954
paper_has_artifact = 7430
paper_observed_in_source_family = 88037
```

Input/load counters:

```text
canonical_papers_loaded = 60954
canonical_papers_with_ids = 60954
artifact_entities_loaded = 7336
artifact_entities_with_ids = 7336
artifact_observations_loaded = 38246
trusted_links_raw_count = 7430
trusted_links_used_count = 7430
topic_assignments_loaded = 60954
topic_assignments_valid = 60954
topic_edges_count = 60954
```

Skipped counters:

```text
skipped_trusted_links_missing_paper = 0
skipped_trusted_links_missing_artifact = 0
topic_assignments_missing_paper = 0
topic_assignments_missing_cluster = 0
```

## Validation

Builder config validator:

```text
scripts/validation/check_paper_artifact_graph_builder_config.py
tests/smoke/test_paper_artifact_graph_builder_config.py
```

Graph output validator:

```text
scripts/validation/check_paper_artifact_graph_output.py
tests/smoke/test_paper_artifact_graph_output_validator.py
```

Builder smoke tests:

```text
tests/smoke/test_paper_artifact_graph_builder.py
```

Trusted-link helper smoke tests:

```text
tests/smoke/test_trusted_artifact_links.py
```

Validated commands:

```bat
python -m py_compile radar_core/artifacts/trusted_links.py
python -m py_compile scripts/export/build_paper_artifact_graph.py
python -m py_compile scripts/export/export_artifacts_postgres_v1.py
python -m py_compile scripts/validation/check_artifact_links_quality.py
python -m py_compile scripts/validation/check_paper_artifact_graph_builder_config.py
python -m py_compile scripts/validation/check_paper_artifact_graph_output.py

python -m pytest tests/smoke/test_trusted_artifact_links.py tests/smoke/test_paper_artifact_graph_builder_config.py tests/smoke/test_paper_artifact_graph_builder.py tests/smoke/test_paper_artifact_graph_output_validator.py -q

python -m scripts.validation.check_artifact_links_quality --strict
python -m scripts.validation.check_paper_artifact_graph_builder_config --strict
python -m scripts.validation.check_paper_artifact_graph_builder_config --strict --check-paths
python -m scripts.validation.check_paper_artifact_graph_output --strict
```

Expected test result:

```text
34 passed
```

Expected validator result:

```text
ok=True
required_failed_count=0
required_failed_checks=[]
```

## Safety guarantees

The builder is file-first and read-only with respect to accepted inputs.

It does not mutate:

```text
canonical documents
artifact input files
topic input files
retrieval artifacts
Qdrant
Postgres
API
ranking
```

It does not:

```text
create a latest pointer
create a global trusted links bridge
change canonical truth
change search behavior
change dataset release behavior
```

## Non-goals

Not included in v0.1:

- Neo4j export
- GraphRAG
- API endpoint
- UI integration
- NER/entity promotion
- provider metadata expansion
- paper feature enrichment
- parquet publication package
- public dataset release
- graph-backed ranking
- graph-backed retrieval

## Current status

Paper-Artifact Graph Builder v0.1 is implemented and validated as a local derived artifact builder.

The graph output is reproducible from accepted local files and guarded by config/output validators.

The graph remains downstream and derived, not canonical.
