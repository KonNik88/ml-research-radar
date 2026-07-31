# Paper Comparison Workspace v0.1

## Document status

```text
contract_version = v0.1
decision_status = accepted
implementation_status = core/API, Streamlit UI, bounded regression runner, and operator live-smoke validator implemented
merge_gate = targeted regression + strict Streamlit validator + live HTTP smoke
product_mode = local single-user
canonical_truth = false
mutates_canonical_documents = false
search_backend_independent = true
workspace_postgres_required = false
```

---

## 1. Purpose

Paper Comparison Workspace v0.1 turns existing ML Research Radar evidence into a
single deterministic research workflow.

The user selects between two and five canonical papers and receives one
comparison response containing:

- canonical metadata;
- identifiers and links;
- categories, concepts and keywords;
- source/provenance evidence;
- Radar and component scores;
- trusted artifact evidence;
- GitHub and Hugging Face signals;
- citation/reference evidence;
- topic-cluster context;
- exact pairwise semantic similarity from the active file-first dense build;
- shared and paper-specific comparison dimensions.

The first version is deliberately not LLM-generated. It supplies a stable,
inspectable comparison foundation on which later summarization or reasoning may
be built.

---

## 2. Architectural boundary

### 2.1 Truth and ownership

`canonical_documents.jsonl` remains paper truth.

Comparison is a read-only derived view over:

- canonical documents;
- `paper_features_latest.jsonl`;
- trusted artifact link/entity outputs;
- GitHub and Hugging Face enrichment snapshots;
- the current dense retrieval generation;
- the current topic-cluster generation;
- the accepted read-only citation/reference graph, when enabled.

The comparison response is not persisted and cannot feed reconciliation.

### 2.2 API ownership

Comparison semantics belong to the core/API layer.

Streamlit must:

- maintain only the temporary comparison basket in `st.session_state`;
- send one batch request;
- render the returned contract;
- avoid reading JSONL, embeddings, graph files or Postgres directly;
- avoid recomputing similarity, set intersections, score ranges or graph
  relationships.

### 2.3 No N+1 UI workflow

The UI must not issue a complete detail/similar/cluster/artifact request chain
for every selected paper.

One batch endpoint owns the server-side composition:

```text
POST /discovery/papers/compare
```

The API loads or reuses indexes once and returns the complete comparison.

---

## 3. v0.1 scope

### 3.1 Selection

- minimum: 2 papers;
- maximum: 5 papers;
- every value is a non-empty `canonical_id`;
- IDs must be unique;
- request order is preserved in `canonical_ids` and `papers`;
- pairwise rows use deterministic input-order combinations.

Papers may be added by the future UI from:

- Search;
- Discovery ranking;
- Paper workspace;
- Topic clusters and Topic map;
- Collections;
- manual `canonical_id` input.

### 3.2 Per-paper evidence

Each paper row contains:

- title, abstract, authors, year and publication metadata;
- DOI, arXiv, ACL, OpenAlex, Semantic Scholar, PMID and PMCID identifiers when
  known;
- canonical links, PDF/landing links and code links;
- categories, concepts, keywords and tags;
- `source_count`, `unique_source_count`, source families and source IDs;
- metadata completeness;
- Radar, implementation readiness, source confidence, citation signal and
  recency scores;
- trusted artifact counts and detailed trusted artifact rows;
- aggregate GitHub and Hugging Face evidence;
- canonical and feature-level citation counts;
- bounded citation/reference graph counts and selected-paper relationships when
  that optional capability is available;
- topic-cluster assignment and labels when available.

### 3.3 Pairwise evidence

For every unordered paper pair, the API returns:

- exact cosine similarity using normalized vectors from one active dense build;
- same-cluster status;
- whether the left paper references the right;
- whether the right paper references the left;
- shared, left-only and right-only:
  - categories;
  - concepts;
  - keywords;
  - source families;
  - artifact types.

### 3.4 Whole-selection summary

The response includes:

- values shared by every selected paper for the same five dimensions;
- year range;
- min/max ranges for the five Radar scores;
- whether all selected papers belong to the same available cluster.

---

## 4. Explicit non-goals

The following are outside v0.1:

- LLM-generated prose or conclusions;
- RAG or GraphRAG;
- automatic judgment of which paper is “better”;
- recommendations based on the comparison;
- new graph traversal endpoints;
- graph visualization;
- NetworkX, Neo4j or graph-database runtime;
- Qdrant promotion or Qdrant dependency;
- changes to retrieval or ranking defaults;
- changes to canonical/reconciliation semantics;
- new Postgres tables or Alembic migrations;
- saved comparison sessions;
- multi-user comparison ownership;
- comparison export;
- comparison sharing;
- background jobs, notifications or digests.

Saved Research Collections already provide durable storage for the selected
papers. Comparison v0.1 intentionally keeps the active basket ephemeral.

---

## 5. Request contract

```http
POST /discovery/papers/compare
Content-Type: application/json
```

```json
{
  "canonical_ids": [
    "paper-id-a",
    "paper-id-b",
    "paper-id-c"
  ]
}
```

Validation:

| Condition | Result |
|---|---|
| 2–5 unique, non-empty IDs | request accepted |
| fewer than 2 IDs | `422` |
| more than 5 IDs | `422` |
| duplicate IDs | `422` |
| blank ID | `422` |
| ID longer than 256 characters | `422` |
| one or more IDs absent from canonical truth | `404` with all missing IDs |

The success contract is all-or-nothing for canonical identity. Optional derived
capabilities may degrade independently without turning a valid metadata
comparison into an error.

---

## 6. Response contract

The response shape is:

```json
{
  "schema_version": "paper_comparison_v0.1",
  "mode": "paper_comparison",
  "canonical_ids": ["paper-id-a", "paper-id-b"],
  "paper_count": 2,
  "input_order_preserved": true,
  "papers": [],
  "pairwise": [],
  "summary": {},
  "capabilities": {},
  "warnings": []
}
```

### 6.1 `papers`

Each row has this stable top-level structure:

```json
{
  "canonical_id": "paper-id-a",
  "title": "Example paper",
  "abstract": null,
  "authors": [],
  "year": 2025,
  "publication_date": null,
  "published_at": null,
  "venue": null,
  "journal": null,
  "conference": null,
  "publisher": null,
  "publication_type": null,
  "language": null,
  "open_access": null,
  "is_preprint": null,
  "is_review": null,
  "is_survey": null,
  "is_withdrawn": null,
  "identifiers": {},
  "links": {},
  "taxonomy": {},
  "provenance": {},
  "scores": {},
  "artifact_evidence": {},
  "citation_evidence": {},
  "cluster": {}
}
```

`artifact_evidence.details` reuses the accepted trusted artifact-detail
semantics. It does not expose raw untrusted URL observations.

### 6.2 `pairwise`

For `n` papers, `pairwise` contains `n * (n - 1) / 2` rows.

```json
{
  "left_canonical_id": "paper-id-a",
  "right_canonical_id": "paper-id-b",
  "semantic": {
    "available": true,
    "similarity": 0.812345,
    "reason": null
  },
  "same_cluster": false,
  "left_references_right": null,
  "right_references_left": null,
  "dimensions": {
    "categories": {
      "shared": [],
      "left_only": [],
      "right_only": []
    },
    "concepts": {
      "shared": [],
      "left_only": [],
      "right_only": []
    },
    "keywords": {
      "shared": [],
      "left_only": [],
      "right_only": []
    },
    "source_families": {
      "shared": [],
      "left_only": [],
      "right_only": []
    },
    "artifact_types": {
      "shared": [],
      "left_only": [],
      "right_only": []
    }
  }
}
```

Set comparison is case-insensitive and order-stable. Display spelling comes
from the relevant input paper.

### 6.3 `capabilities`

The response always reports these independently:

```text
artifact_details
semantic_similarity
topic_clusters
citation_graph
```

Each capability contains at least:

```json
{
  "available": true,
  "reason": null
}
```

Build identifiers and safe input-path diagnostics may be included where
available.

---

## 7. Missing-data semantics

Unknown is not zero.

- unknown scalar count: `null`;
- known zero count: `0`;
- unknown boolean: `null`;
- known false boolean: `false`;
- known empty taxonomy set: `[]`;
- unavailable semantic similarity: `available=false`, `similarity=null`;
- unavailable cluster relation: `same_cluster=null`;
- unavailable graph relationship: `left_references_right=null`;
- available graph with no selected relationship: `false`.

The UI must render `null` as unknown/unavailable, not as zero or false.

---

## 8. Optional capability isolation

### 8.1 Semantic similarity

The API reuses the active file-first dense bundle and normalized embedding
matrix. It does not query or promote Qdrant.

If dense artifacts cannot be loaded, the metadata comparison still succeeds:

```text
semantic.available = false
semantic.similarity = null
```

### 8.2 Topic clusters

Cluster context is valid only within the reported `cluster_build_id` and
`retrieval_build_id`.

If cluster artifacts are unavailable, paper cluster status is `unavailable`.
If the build exists but does not contain a paper, status is
`paper_not_in_build`.

### 8.3 Citation/reference graph

Comparison uses the existing accepted read-only graph store only when the graph
status contract reports it available.

It returns counts and direct relationships among selected papers. It does not
return an unbounded adjacency list.

If the graph is disabled, incompatible, missing or invalid:

- the endpoint still returns `200`;
- canonical `cited_by_count` / `references_count` remain available when known;
- feature-level `citation_count` and `citation_signal_score` remain available;
- graph counts and relationships are `null`;
- `capabilities.citation_graph.available=false`;
- a warning explains the degradation.

---

## 9. Cache and reload semantics

The API-owned comparison path may cache:

- canonical rows by `canonical_id`;
- feature rows by `canonical_id`;
- artifact links grouped by `canonical_id`;
- artifact entities and enrichment rows by `artifact_id`;
- normalized dense embeddings and ID index;
- topic assignments and summaries;
- the accepted citation graph store.

`POST /reload` must invalidate the DiscoveryService comparison caches through
the existing `DiscoveryService.reload()` path. The existing citation graph
reload cache behavior remains unchanged.

No comparison request writes data or produces `latest` pointers.

---

## 10. Streamlit UI contract

The Streamlit UI adds a top-level `Comparison` tab.

Required basket behavior:

- `st.session_state` stores only ordered unique canonical IDs;
- maximum five IDs;
- add buttons are reusable from Search, ranking, Paper workspace and
  Collections;
- manual input is supported;
- individual removal and clear-all are supported;
- Compare is disabled until two papers are selected;
- one Compare action sends one batch request;
- changing the basket invalidates the previous response;
- opening a compared paper in Paper workspace reuses the existing selection
  helper;
- saving a paper reuses existing Collections membership controls.

Required rendering:

- compact metadata/score comparison table;
- semantic similarity matrix or pair table;
- shared/different taxonomy and source evidence;
- artifact and implementation evidence;
- citation/reference evidence with caveats;
- cluster context;
- expandable abstracts and raw response.

The UI must remain usable when workspace PostgreSQL is unavailable. Collections
controls may report `workspace_unavailable`, while Comparison itself continues
to work.

---

## 11. Verification matrix

### 11.1 Core/API

- two-paper comparison;
- five-paper comparison and ten pairwise rows;
- input-order preservation;
- duplicate rejection;
- one-ID rejection;
- six-ID rejection;
- blank-ID rejection;
- unknown/orphaned canonical ID returns `404`;
- exact semantic similarity from selected dense rows;
- dense ID absent from current build degrades to `null`;
- same-cluster and different-cluster pairs;
- paper absent from cluster build;
- citation graph enabled;
- citation graph disabled/unavailable without endpoint failure;
- direct selected-paper citation relationship;
- unknown values remain `null`;
- known zero and false remain `0` and `false`;
- artifact files scanned/indexed once, not once per selected paper;
- reload invalidates new indexes.

### 11.2 UI

- add from every supported surface;
- duplicate add is idempotent;
- sixth add is rejected visibly;
- remove and clear;
- Compare disabled for fewer than two papers;
- result invalidated after basket change;
- two- and five-paper layouts;
- long titles and abstracts;
- missing metadata;
- unavailable optional capabilities;
- unavailable workspace PostgreSQL;
- Search, Discovery, Paper workspace and Collections regressions remain green.

---

## 12. Delivery slices

The implementation is intentionally split into reviewable commits:

1. `feat(comparison): add deterministic paper comparison API`
   - contract;
   - pure comparison builder;
   - cached DiscoveryService composition;
   - batch endpoint;
   - citation graph evidence adapter;
   - API/core tests.

2. `feat(comparison): add paper comparison workspace UI`
   - temporary basket;
   - reusable add controls;
   - Comparison tab;
   - thin API client;
   - UI tests and validator updates.

3. `test(comparison): harden comparison regression and live smoke`
   - complete regression matrix;
   - bounded file-backed regression runner;
   - operator-facing live HTTP validator;
   - docs/API reference updates;
   - ignored local live-smoke evidence reports.

No later slice may silently expand v0.1 into LLM/RAG, persistence or a promoted
graph runtime.

---

## 13. Final regression and live-smoke gate

The final v0.1 gate is intentionally bounded to the existing comparison
workflow. It does not rebuild retrieval, query or promote Qdrant, require
workspace PostgreSQL, create a migration, or mutate canonical data.

### 13.1 Targeted regression

With the project environment active:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.run_paper_comparison_regression
```

The runner executes the accepted core/API/UI matrix, including:

- pure comparison builder and DiscoveryService cache/reload behavior;
- two-paper and five-paper API contracts;
- validation and missing-paper errors;
- citation graph evidence and failure isolation;
- temporary basket and thin API client behavior;
- Search, Discovery, Paper workspace and Collections add surfaces;
- Streamlit static ownership checks;
- the live-smoke validator's own fail-closed unit tests.

It then runs:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

The runner writes ignored local evidence to:

```text
artifacts/reports/validation/paper_comparison_regression_latest.json
artifacts/reports/validation/paper_comparison_regression_latest.md
artifacts/reports/validation/history/paper_comparison_regression_<timestamp>.json
artifacts/reports/validation/history/paper_comparison_regression_<timestamp>.md
```

### 13.2 Live HTTP smoke

Start the API in a separate terminal with the normal file-first Discovery
runtime:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m uvicorn services.api.app:app --host 127.0.0.1 --port 8000
```

Then run either the live validator directly:

```bat
python -m scripts.validation.check_paper_comparison_live_smoke --strict
```

or the complete merge gate in one command:

```bat
python -m scripts.validation.run_paper_comparison_regression --include-live-smoke
```

The live validator:

1. confirms `/health`, `/info`, and `/runtime`;
2. selects five unique real papers from
   `recent_artifact_ready` Discovery ranking;
3. validates deterministic two-paper comparison and repeat equality;
4. validates five-paper comparison with ten pairwise rows;
5. requires semantic similarity from the active file-first dense build;
6. validates one-ID, duplicate, six-ID, blank-ID and missing-ID errors;
7. confirms general runtime health remains ready after comparison calls.

Citation Graph availability is recorded but is not required: its accepted
failure-isolation contract permits comparison to remain valid while graph
evidence is unavailable.

Live reports:

```text
artifacts/reports/validation/paper_comparison_live_smoke_latest.json
artifacts/reports/validation/paper_comparison_live_smoke_latest.md
artifacts/reports/validation/history/paper_comparison_live_smoke_<timestamp>.json
artifacts/reports/validation/history/paper_comparison_live_smoke_<timestamp>.md
```

These reports are operational evidence and are not committed. A green gate
means the deterministic comparison slice is ready for PR review; it does not
authorize LLM/RAG, comparison persistence, graph-runtime promotion, Qdrant
promotion, or changes to canonical truth.
