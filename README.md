# ML Research Radar

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-green)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)
![Postgres](https://img.shields.io/badge/Postgres-Serving%20DB-blue)
![Qdrant](https://img.shields.io/badge/Qdrant-Experimental%20Vector%20Serving-purple)
![Docker](https://img.shields.io/badge/Docker-Local%20Infrastructure-blue)

Roadmap technologies:

![Airflow](https://img.shields.io/badge/Airflow-Planned-blue)
![Ray](https://img.shields.io/badge/Ray-Planned-orange)
![Kafka](https://img.shields.io/badge/Kafka-Planned-black)
![Kubernetes](https://img.shields.io/badge/Kubernetes-Planned-blue)
![Observability](https://img.shields.io/badge/Observability-Planned-orange)
![RAG](https://img.shields.io/badge/RAG-Planned-purple)

**ML Research Radar** is a long-horizon, paper-centric platform for discovering,
organizing, evaluating, and reasoning over machine-learning research.

The project is intentionally staged. It is not an arXiv-only parser, not a
vector-database wrapper, and not a one-off RAG demo. The repository combines:

1. a working, validated local research-discovery system;
2. a documented engineering roadmap toward richer retrieval, public datasets,
   research graphs, full-text retrieval, RAG, personalization, observability,
   orchestration, and deployable infrastructure.

New technologies are introduced only when they strengthen the same
paper-centric research-discovery system.

---

## Current validated checkpoint

```text
checkpoint = Retrieval Serving Checkpoint v1 / Search API Semantics Cleanup v1
public behavior change = none
public dense/hybrid backend = file
experimental Qdrant endpoint = explicit
fallback = absent
Qdrant promotion = not performed
```

Current corpus and retrieval baseline:

```text
canonical documents = 60,954
multisource documents = 9,192
documents with DOI = 10,183

arXiv backbone = 60,000
ACL-family documents = 957
ACL-only documents = 954
ACL-enriched existing documents = 3

retrieval build = 20260504T164021Z
embedding model = sentence-transformers/all-MiniLM-L6-v2
embedding shape = [60954, 384]
dense vectors normalized = true
```

Current discovery baseline:

```text
paper feature rows = 60,954
topic clusters = 80
topic projection rows = 2,080
ranking profiles = 9
```

Current Qdrant baseline:

```text
collection = ml_radar_dense_benchmark_v1
points = 60,954
vector size = 384
distance = Cosine
experimental transport = gRPC
selected ANN profile = ef_256
```

Current Golden Set and evaluation baseline:

```text
enabled Golden queries = 34
explicit canonical-labeled queries = 34
weak-pattern-only enabled queries = 0
```

---

## Current public search behavior

Public search remains file-backed:

```text
GET /search?mode=lexical
→ file BM25 / lexical retrieval

GET /search?mode=dense
→ exact file dense retrieval

GET /search?mode=hybrid
→ file lexical + exact file dense hybrid retrieval
```

Experimental Qdrant search remains explicit:

```text
GET /experimental/search/qdrant
→ Qdrant dense search over the same retrieval build
```

Important boundaries:

```text
Qdrant is optional.
Qdrant is not canonical truth.
Qdrant is not required for /health readiness.
Qdrant does not change /search defaults.
Qdrant does not introduce fallback.
Qdrant is not the public dense/hybrid default.
```

The file backend remains the exact reference, evaluation oracle, and rollback
path.

---

## Ranking status

Free-form `/search` has an explicit `rank` flag.

Current accepted semantics:

```text
rank=false
→ default and reference behavior

rank=true
→ explicit optional/experimental heuristic reranking
```

Accepted ranking evidence concluded:

```text
recommended_outcome = reject_heuristic_reranking
reference_behavior = unranked hybrid
public_behavior_change = false
```

The current heuristic reranking formula is not promoted as a default relevance
strategy.

---

## Architectural foundation

The central invariant is:

```text
data/analytics/reconciled/canonical_documents.jsonl
= paper-level source of truth
```

Derived layers:

```text
Postgres
= rebuildable materialized serving layer

retrieval artifacts
= rebuildable lexical/dense retrieval layer

Qdrant
= optional derived vector-serving implementation

artifact entities and links
= separate evidence/materialization plane

paper features, ranking, similar papers, clusters, projections
= derived discovery and analytics layers

FastAPI
= service boundary

Streamlit
= thin API client
```

No derived layer may redefine canonical paper identity.

Identity domains remain separate:

```text
source_doc_id / doc_id
= source-level observation identity

canonical_id
= reconciled paper-level identity

artifact_id
= normalized repository/model/dataset/demo identity

Qdrant point_id / dense_index
= serving mapping inside one retrieval generation
```

Paper identity priority:

```text
DOI
→ external DOI
→ arXiv ID
→ external arXiv ID
→ normalized title + year fallback
```

---

## Current source landscape

Stable paper sources:

```text
arXiv
OpenAlex alignment
Semantic Scholar alignment
Crossref alignment
ACL Anthology
```

Operational artifact providers:

```text
GitHub
Hugging Face Hub
```

GitHub and Hugging Face metadata enrich artifact entities. They do not overwrite
canonical paper title, authors, abstract, venue, year, publication type, or
identity.

Candidate future paper/domain sources include OpenReview, PubMed / Europe PMC,
bioRxiv, medRxiv, and additional conference or repository sources when justified.

Papers with Code live integration is currently blocked/archived. Any future use
requires a separate offline or historical viability experiment.

---

## Operational pipeline

```text
paper sources
→ raw source records
→ normalized source observations
→ alignment / enrichment
→ identity resolution and reconcile
→ canonical paper corpus
→ Postgres materialization
→ artifact extraction and provider enrichment
→ paper features
→ retrieval generation
→ ranking / paper detail / similar papers
→ topic clusters / projection
→ FastAPI
→ Streamlit
→ evaluation / validators / Definition of Done
```

Refresh follows candidate-first safety semantics:

```text
experiment
→ timestamped candidate
→ source and reconcile audits
→ explicit promotion
→ rebuild derived layers
→ strict Definition of Done
```

Selective enrichment batches are not treated as the complete accepted source
state. They must be merged into an explicit full snapshot before stable
reconciliation.

---

## Implemented capabilities

### Canonical paper core

- normalized source contracts;
- source-level and paper-level identity separation;
- conservative DOI/arXiv conflict handling;
- multi-source reconciliation;
- field-level merge policy;
- provenance preservation;
- canonical contract and audit tooling;
- candidate/promotion/rollback workflow.

### Retrieval

- BM25 lexical retrieval;
- exact file dense retrieval;
- hybrid retrieval;
- build-scoped retrieval manifests;
- Golden Set evaluation;
- controlled weight and candidate-depth experiments;
- similar-paper retrieval;
- backend-neutral hybrid merge;
- exact file reference backend.

### Serving

- FastAPI service boundary;
- file runtime;
- Postgres materialized runtime;
- document and artifact browsing;
- file lexical/dense/hybrid search;
- DB lexical search v1;
- runtime reload and diagnostics;
- experimental Qdrant dense endpoint.

### Artifact evidence plane

- artifact entities;
- artifact observations;
- trusted paper-artifact links;
- GitHub enrichment;
- Hugging Face enrichment;
- artifact filters and API surfaces;
- artifact-aware paper features.

Current artifact baseline:

```text
artifact entities in DB = 7,333
artifact observations = 38,246
paper-artifact links = 7,430
linked canonical papers = 6,673

GitHub found = 5,339
Hugging Face found = 77
```

### Discovery and analytics

- transparent paper features;
- ranking profiles;
- paper detail;
- semantic and radar-adjusted similar papers;
- 80 MiniBatchKMeans topic clusters;
- full-corpus assignments;
- UMAP topic projection;
- cluster navigation and map API;
- Streamlit Discovery UI.

### Qdrant serving line

Completed slices:

```text
Qdrant collection build/upload and strict validation
Qdrant / file-dense parity
Qdrant profile sweep
DenseSearchBackend abstraction
Qdrant failure contract
Qdrant runtime observability
Qdrant serving performance
Qdrant hybrid evaluation
Retrieval serving checkpoint gate
```

Qdrant hybrid evaluation result:

```text
34 queries
136 scenarios
136 / 136 same final result sets
134 / 136 same final order
132 / 136 exact dense + final parity
0 blocking classifications
0 measured Hit / Precision / Recall / MRR regression
```

---

## Search and discovery contracts

### Free-form search

```text
GET /search
```

Modes:

```text
lexical
dense
hybrid
```

Current hybrid defaults:

```text
lexical weight = 0.55
dense weight = 0.45
```

`rank=false` is the current reference behavior.

### Experimental Qdrant search

```text
GET /experimental/search/qdrant
```

This endpoint is explicit and experimental. It uses Qdrant gRPC over the current
retrieval build and selected profile. It does not change `/search`.

### Similar papers

```text
GET /discovery/papers/{canonical_id}/similar
```

Modes:

```text
semantic
radar_adjusted
```

This contract starts from a paper embedding and requires self-exclusion. It is
intentionally separate from text-query search.

### Discovery ranking

```text
GET /discovery/ranking/{profile}
```

Profiles use derived paper features such as recency, source confidence,
implementation readiness, citation signal, and artifact availability.

### Topic navigation

Current topic artifacts:

```text
clusters = 80
assignments = 60,954
projection rows = 2,080
```

Cluster labels are heuristic, build-scoped navigation hints rather than stable
curated taxonomy.

---

## Validation and evidence

Validation is part of the architecture.

Current families include:

- canonical contract;
- canonical provenance consistency;
- source and postpass audits;
- retrieval checks;
- Golden Set quality;
- controlled search experiments;
- artifact and enrichment checks;
- paper features;
- ranking profiles;
- similar papers;
- Discovery API;
- clusters and projection;
- Streamlit UI;
- Qdrant collection, parity, profile sweep, performance, and hybrid evaluation;
- retrieval-serving checkpoint gate;
- strict Definition of Done.

Current provenance evidence:

```text
documents checked = 60,954
structural errors = 0
warnings = 0
informational doc_ids_shorter_than_sources = 9,095
```

The informational count is expected because `doc_ids` are deduplicated while
`sources` preserve contributing provenance rows.

Recommended lightweight retrieval-serving gate:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint
```

Extended local gate:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint ^
  --include-serving-performance-evidence ^
  --include-qdrant-collection-live ^
  --include-api-smoke
```

Generated reports under `artifacts/reports/...` are evidence/materializations
and should not be committed unless a separate artifact-retention policy says so.

---

## Data layers

```text
data/
├── raw/                   # source responses and bulk snapshots
├── normalized/            # source-level normalized observations
├── analytics/reconciled/  # canonical paper truth
├── enriched/              # artifact/provider materializations
├── features/              # derived paper features
└── datasets_release/      # future immutable public releases
```

Generated evidence and build outputs live under:

```text
artifacts/
├── reports/
├── retrieval/
└── clusters/
```

---

## Repository structure

```text
ML_Research_Radar/
├── artifacts/
├── configs/
├── data/
├── docs/
├── environment/
├── experiments/
├── infra/
├── notebooks/
├── polyglot/
├── radar_core/
├── requirements/
├── scripts/
├── services/
├── store/
├── tests/
├── .gitignore
└── README.md
```

Important boundaries:

- `radar_core/` contains core contracts and business logic;
- `services/api/` exposes FastAPI;
- `services/ui/` remains a thin Streamlit client;
- `scripts/` contains explicit ingest, refresh, export, evaluation, and validation entry points;
- `store/sql/` contains Postgres materialization;
- `infra/docker/` contains current local infrastructure;
- future orchestration and deployment layers must not absorb canonical/retrieval business logic.

---

## Current technology stack

Implemented/core:

- Python 3.11
- Pydantic
- FastAPI
- Streamlit
- PostgreSQL
- Qdrant
- Docker Compose
- Sentence Transformers
- PyTorch
- NumPy / pandas
- scikit-learn
- Plotly
- UMAP
- pytest

Planned extensions:

- stronger scientific embedding models;
- cross-encoder reranking;
- learned sparse retrieval;
- full-text parsing and chunk retrieval;
- grounded RAG;
- LangGraph workflows;
- Airflow;
- Ray;
- Kafka;
- Kubernetes;
- Prometheus / Grafana;
- Loki or another structured-log backend;
- OpenTelemetry / Jaeger or Tempo;
- Alembic migrations.

These planned items are staged roadmap options, not immediate implementation
requirements.

---

## Near-term roadmap

Recommended order:

1. **Search API Semantics Cleanup v1**  
   Synchronize API, runtime, Qdrant, ranking, and validation documentation.

2. **Dataset Export Contract v0.1**  
   Define metadata-only public export schema, provenance, checksum, and data-card policy.

3. **Deployment Vector Backend Selector Design v1**  
   Design `ML_RADAR_VECTOR_BACKEND=file|qdrant` without changing defaults.

4. **Public Qdrant Promotion v1**  
   Only after explicit design, regression gates, rollback policy, and acceptance evidence.

5. **Next retrieval generation**  
   New embeddings, larger Golden Set, and retrieval rebuild only as a separate build-scoped slice.

---

## Safety stance

Current accepted policy:

```text
Do not change public retrieval defaults by intuition.
Do not promote Qdrant because it is available.
Do not promote ranking because it exists.
Do not commit generated reports by accident.
Prefer small, evidence-backed vertical slices.
```

The project should remain paper-centric and evidence-driven.
