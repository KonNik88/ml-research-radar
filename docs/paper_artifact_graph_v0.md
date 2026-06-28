# Paper–Artifact Graph Contract v0.1

Status: active contract-only slice
Scope: derived graph contract, no graph build/export/runtime behavior changes
Config: `configs/paper_artifact_graph.yaml`
Validator: `scripts/validation/check_paper_artifact_graph_contract.py`
Smoke tests: `tests/smoke/test_paper_artifact_graph_contract.py`

## Purpose

Paper–Artifact Graph Contract v0.1 defines the first explicit contract for a future derived graph layer connecting canonical ML/AI papers to their trusted software, dataset, model, demo, provider, source-family, and topic-cluster evidence.

This slice does **not** build a graph. It only fixes the contract that future graph builders, graph validators, graph exports, graph APIs, and graph dataset releases must follow.

The main goal is to preserve the current ML Research Radar architecture while making the future graph layer explicit and safe:

```text
canonical paper corpus
+ artifact evidence plane
+ provider metadata
+ canonical provenance
+ topic clusters
→ future derived paper-artifact evidence graph
```

## Non-goals

This slice intentionally does not introduce:

- graph builder;
- `nodes.parquet` / `edges.parquet` generation;
- Neo4j, NetworkX, GraphRAG, or any graph runtime;
- new API endpoints;
- Streamlit UI changes;
- Postgres schema changes;
- canonical reconcile changes;
- retrieval behavior changes;
- Qdrant behavior changes;
- ranking/default behavior changes;
- dataset publication;
- full-text acquisition;
- chunking;
- NER/entity extraction.

The contract is a foundation for those future layers, not their implementation.

## Architectural boundary

The graph layer is derived and rebuildable. It must not become a new source of paper truth.

Current truth and derived-layer boundaries remain unchanged:

```text
data/analytics/reconciled/canonical_documents.jsonl
= paper-level canonical truth

Postgres
= materialized serving layer

retrieval artifacts / Qdrant
= derived retrieval/vector-serving layers

artifact_entities / artifact_observations / paper_artifact_links
= artifact evidence/materialization plane

paper_features / topic clusters / topic projection
= derived discovery/analytics layers

paper-artifact graph
= future derived graph representation
```

The graph must preserve existing identity domains instead of inventing new paper or artifact identity semantics.

## Source checkpoint

The accepted contract checkpoint is recorded in `configs/paper_artifact_graph.yaml` under `source_checkpoint`.

The current v0.1 checkpoint metadata is:

```yaml
expected_canonical_doc_count: 60954
retrieval_build_id: "20260504T164021Z"
artifact_entities_db_count: 7333
artifact_observations_db_count: 38246
paper_artifact_links_db_count: 7430
topic_clusters_count: 80
topic_assignments_count: 60954
```

These values describe the accepted project checkpoint for this contract. In v0.1 the validator treats them as contract metadata and sanity-checks their shape/value positivity. It does not run live DB checks.

Future graph builder/output validators may add live consistency checks against local files, Postgres, or generated graph outputs.

## Node types

The contract requires the following node types:

```text
paper
artifact
provider
source_family
topic_cluster
```

### `paper`

Represents a canonical paper.

Identity source:

```text
canonical_documents.canonical_id
```

Node ID policy:

```text
paper:<canonical_id>
```

Required fields:

```text
node_id
node_type
canonical_id
title
year
source_count
unique_source_count
```

Optional fields:

```text
doi
arxiv_id
primary_category
publication_type
metadata_completeness_score
has_trusted_artifact
topic_cluster_id
```

### `artifact`

Represents a normalized research artifact from the artifact evidence plane.

Identity source:

```text
artifact_entities.artifact_id
```

Node ID policy:

```text
artifact:<artifact_id>
```

Required fields:

```text
node_id
node_type
artifact_id
provider
artifact_type
normalized_url
```

Optional fields:

```text
owner
name
title
description
license
stars
forks
downloads
likes
topics
tags
archived
github_status
huggingface_status
last_seen_at
fetched_at
created_at
updated_at
pushed_at
```

Provider metadata fields are artifact metadata only. They must not override canonical paper title, authors, abstract, venue, year, publication type, identifiers, or identity.

### `provider`

Represents a normalized artifact provider value.

Node ID policy:

```text
provider:<provider>
```

Required fields:

```text
node_id
node_type
provider
```

Provider node values must be derived from normalized values already present in `artifact_entities.provider`. The graph contract must not invent a broader provider enum by hand.

### `source_family`

Represents a canonical paper source family.

Node ID policy:

```text
source_family:<source_family>
```

Required fields:

```text
node_id
node_type
source_family
```

Source-family nodes must respect canonical provenance semantics:

```text
sources     = row-level provenance
source_ids  = merged identifier map, not strict provenance by itself
```

The graph must not treat `source_ids` alone as strict provenance.

### `topic_cluster`

Represents a derived topic cluster assignment from the topic-clustering layer.

Node ID policy:

```text
topic_cluster:<cluster_id>
```

Required fields:

```text
node_id
node_type
cluster_id
```

Optional fields:

```text
label
label_candidates
size
cluster_build_id
retrieval_build_id
mean_radar_score
artifact_ready_count
```

Topic clusters are derived navigation/analytics objects, not a curated ontology and not paper truth.

## Edge types

The contract requires the following edge types:

```text
paper_has_artifact
artifact_from_provider
paper_observed_in_source_family
paper_assigned_to_topic_cluster
```

Default edge ID policy:

```text
typed_source_target_hash
```

Common required edge fields:

```text
edge_id
edge_type
source_node_id
target_node_id
provenance_kind
source_layer
confidence
```

### `paper_has_artifact`

Connects a canonical paper to a trusted artifact.

Trusted source:

```text
paper_artifact_links
```

Required fields:

```text
canonical_id
artifact_id
provider
artifact_type
relation_type
confidence
evidence_source
```

Important rule:

```text
artifact_observations = broad evidence layer
paper_artifact_links  = trusted serving/evidence edge source
paper_has_artifact    = graph edge from trusted paper_artifact_links
```

The graph must not create trusted paper-artifact edges directly from broad `artifact_observations`.

### `artifact_from_provider`

Connects an artifact node to its provider node.

Source:

```text
artifact_entities
```

Required fields:

```text
artifact_id
provider
```

### `paper_observed_in_source_family`

Connects a canonical paper to the source families that contributed source-level observations.

Source:

```text
canonical_documents
```

Required fields:

```text
canonical_id
source_family
```

This edge must respect provenance semantics and must not infer strict provenance from `source_ids` alone.

### `paper_assigned_to_topic_cluster`

Connects a canonical paper to its derived topic cluster assignment.

Source:

```text
topic_clusters
```

Required fields:

```text
canonical_id
cluster_id
cluster_build_id
retrieval_build_id
```

## Provenance policy

Required provenance kinds:

```text
canonical_provenance
artifact_evidence
provider_metadata
topic_assignment
derived_summary
```

Allowed source layers:

```text
canonical_documents
artifact_db
artifact_extraction
provider_enrichment
paper_features
topic_clusters
topic_projection
```

Required provenance policies:

```yaml
artifact_metadata_not_paper_truth: true
graph_not_reconcile_input: true
source_ids_not_strict_provenance: true
trusted_artifact_edges_from_paper_artifact_links: true
```

## Safety policy

The graph contract must preserve all current project safety boundaries.

Required safety flags:

```yaml
canonical_truth_impact: none
may_overwrite_operational_latest: false
may_be_used_as_reconcile_input: false
may_change_api_behavior: false
may_change_retrieval_behavior: false
may_change_qdrant_behavior: false
may_change_ranking_behavior: false
may_publish_without_manual_review: false
```

These flags make the contract explicit:

- no canonical truth changes;
- no operational latest overwrite;
- no reconcile input usage;
- no API behavior changes;
- no retrieval behavior changes;
- no Qdrant behavior changes;
- no ranking behavior changes;
- no publication without manual review.

## Future output layout

This slice does not generate graph outputs.

The expected future graph output layout is recorded as:

```yaml
outputs:
  status: future_layout_only
  generated_in_this_slice: false
  expected_future_layout:
    - nodes.parquet
    - edges.parquet
    - schema.json
    - manifest.json
    - README.md
    - data_quality_summary.json
    - checksums.txt
```

A future graph builder slice may generate this layout. A future graph output validator should validate row counts, ID uniqueness, node/edge references, schema version, provenance fields, checksums, and manifest consistency.

## Validator

The contract validator is:

```text
scripts/validation/check_paper_artifact_graph_contract.py
```

Default behavior is config/report-only:

```bat
python -m scripts.validation.check_paper_artifact_graph_contract --strict
```

The validator checks:

- config existence;
- schema version;
- graph metadata;
- contract-only status;
- source checkpoint metadata;
- required node types;
- required node ID policies;
- required edge types;
- common edge fields;
- trusted `paper_has_artifact` source;
- provider value policy;
- source-family provenance policy;
- provenance kinds;
- allowed source layers;
- safety flags;
- future-layout-only output status;
- validation flags.

Optional path checks:

```bat
python -m scripts.validation.check_paper_artifact_graph_contract --strict --check-paths
```

`--check-paths` only checks configured local file paths. It does not connect to Postgres, does not call API endpoints, does not query Qdrant, and does not run live provider checks.

## Reports

The validator writes latest and history reports:

```text
artifacts/reports/validation/paper_artifact_graph_contract_latest.json
artifacts/reports/validation/paper_artifact_graph_contract_latest.md
artifacts/reports/validation/history/paper_artifact_graph_contract_<run_ts>.json
artifacts/reports/validation/history/paper_artifact_graph_contract_<run_ts>.md
```

Report schema:

```text
paper_artifact_graph_contract_quality_v1
```

Generated reports are validation artifacts. They are not part of the source contract unless explicitly promoted by repository policy.

## Smoke tests

Smoke tests live in:

```text
tests/smoke/test_paper_artifact_graph_contract.py
```

They cover:

- valid config passes;
- missing required node type fails;
- missing required edge type fails;
- bad graph status fails;
- bad identity policy fails;
- bad safety flag fails;
- hardcoded provider enum fails;
- `paper_has_artifact` must use trusted links;
- output status must remain future-layout-only;
- missing future layout file fails;
- `--check-paths` passes for existing configured files;
- `--check-paths` fails for missing configured file.

## Validation commands

Minimal slice checks:

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_contract.py
python -m pytest tests/smoke/test_paper_artifact_graph_contract.py -q
python -m scripts.validation.check_paper_artifact_graph_contract --strict
python -m scripts.validation.check_paper_artifact_graph_contract --strict --check-paths
```

Expected result for the config-only validator:

```text
required_failed_count=0
required_failed_checks=[]
```

## DoD integration

This v0.1 slice does not add a new strict DoD required gate.

Reason: the layer is contract-only and does not yet produce a graph artifact. The existing validation path is sufficient for this slice:

```text
config
+ validator
+ smoke tests
+ documentation
```

Future graph builder/output validator slices may add a DoD-readable report and, later, an optional or required DoD flag.

## Future slices

Recommended next graph-line sequence:

```text
1. Paper–Artifact Graph Contract v0.1
2. Paper–Artifact Graph Builder v0.1
3. Graph Output Validator v0.1
4. Graph Analytics Summary v0.1
5. Optional Graph Dataset Release Candidate
6. Graph API / UI Explorer
7. Entity / NER Contract
8. Full-text Acquisition + Chunk Contract
9. RAG / GraphRAG only after grounded provenance/chunk policy
```

The next slice after this contract should build graph outputs only after this contract is merged and accepted.
