# ML Research Radar

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-green)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)
![Postgres](https://img.shields.io/badge/Postgres-Serving%20DB-blue)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20Serving-purple)
![Docker](https://img.shields.io/badge/Docker-Local%20Infrastructure-blue)

Roadmap technologies:

![Airflow](https://img.shields.io/badge/Airflow-Planned-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Planned-purple)
![Ray](https://img.shields.io/badge/Ray-Planned-orange)
![Kafka](https://img.shields.io/badge/Kafka-Planned-black)
![Kubernetes](https://img.shields.io/badge/Kubernetes-Planned-blue)
![Observability](https://img.shields.io/badge/Observability-Planned-orange)

**ML Research Radar** is a long-horizon, paper-centric platform for discovering, organizing, ranking, analyzing, and reasoning over machine-learning research.

The repository serves two purposes at once:

1. a working, validated research-discovery system;
2. a staged engineering roadmap toward richer retrieval, research graphs, RAG, personalization, observability, orchestration, event-driven processing, distributed execution, and production-style deployment.

The roadmap is intentionally broader than the current implementation. Planned technologies remain visible here, but they are introduced only when a concrete product or operational need justifies them.

---

## Project vision

ML Research Radar is designed to grow into an end-to-end research platform that can:

- ingest partially overlapping scientific sources;
- resolve source-level records into stable paper-level identities;
- preserve field-level provenance;
- connect papers with repositories, models, datasets, demos, and other research artifacts;
- support lexical, dense, hybrid, and later graph-aware retrieval;
- rank papers for different research and implementation-oriented scenarios;
- expose paper pages, artifact pages, similar papers, topic maps, and research graphs;
- support full-text retrieval, grounded RAG, paper comparison, and survey generation;
- create watchlists, digests, saved searches, and personalized discovery flows;
- publish reproducible public datasets derived from accepted corpus checkpoints;
- evolve toward observable, scheduled, distributed, event-driven, and deployable infrastructure.

This is not a single-model demo and not a collection of unrelated technologies. New components are added only when they strengthen the same research-discovery system.

---

## Current validated checkpoint

```text
canonical documents = 60,954
multisource documents = 9,192
documents with DOI = 10,183

arXiv backbone = 60,000
ACL-family documents = 957
ACL-only documents = 954
existing papers enriched with ACL provenance = 3

retrieval build = 20260504T164021Z
embedding model = sentence-transformers/all-MiniLM-L6-v2
embedding shape = [60954, 384]
dense vectors normalized = true

paper feature rows = 60,954
topic clusters = 80
topic projection rows = 2,080

Qdrant collection = ml_radar_dense_benchmark_v1
Qdrant points = 60,954
selected ANN profile = ef_256
```

Current public search behavior:

```text
/search?mode=lexical
→ file BM25

/search?mode=dense
→ exact file dense

/search?mode=hybrid
→ BM25 + exact file dense

/experimental/search/qdrant
→ Qdrant gRPC
```

Qdrant has completed parity, backend-abstraction, failure-contract, runtime-observability, serving-performance, and controlled hybrid-evaluation slices. It has not been promoted to the public dense/hybrid default.

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
= rebuildable lexical/dense generation

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

A canonical URL is useful metadata, but it is not the sole identity rule.

---

## Current source landscape

### Stable paper sources

- arXiv
- OpenAlex alignment
- Semantic Scholar alignment
- Crossref alignment
- ACL Anthology

Roles:

- **arXiv** provides the main preprint backbone.
- **OpenAlex** contributes semantic concepts, citation/reference signals, external identifiers, and venue/publisher hints.
- **Semantic Scholar** contributes identifier and citation support.
- **Crossref** stabilizes DOI-oriented publication metadata, publisher, publication type, dates, and references.
- **ACL Anthology** is the first promoted domain source and adds NLP/computational-linguistics coverage.

### Operational artifact providers

- GitHub
- Hugging Face Hub

These providers enrich artifact entities. Their metadata does not overwrite canonical paper title, authors, abstract, venue, year, publisher, publication type, or identity.

### Candidate future paper/domain sources

- OpenReview
- PubMed / Europe PMC
- bioRxiv
- medRxiv
- additional conference and repository sources when justified

Papers with Code live integration is currently blocked/archived. Any future use requires a separate offline or historical viability experiment.

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

A selective enrichment batch is not treated as the complete accepted source state. It must be merged into an explicit full snapshot before stable reconciliation.

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
- exact dense retrieval;
- hybrid retrieval;
- build-scoped manifests;
- Golden Set evaluation;
- controlled weight and candidate-depth experiments;
- similar-paper retrieval;
- backend-neutral hybrid merge;
- exact file reference backend.

### Serving

- FastAPI;
- file runtime;
- Postgres materialized runtime;
- document and artifact browsing;
- file lexical/dense/hybrid search;
- DB lexical search v1;
- runtime reload and diagnostics.

### Artifact evidence plane

- artifact entities;
- artifact observations;
- trusted paper-artifact links;
- GitHub enrichment;
- Hugging Face enrichment;
- artifact filters and API surfaces;
- artifact-aware paper features.

Current baseline:

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

- collection build/upload and strict validation;
- file-vs-Qdrant parity;
- ANN profile sweep;
- `DenseSearchBackend` abstraction;
- `FileDenseBackend`;
- `QdrantDenseBackend`;
- typed failure semantics;
- strict result/mapping validation;
- runtime observability;
- gRPC serving benchmark;
- controlled file-vs-Qdrant hybrid evaluation.

Hybrid evaluation result:

```text
34 queries
136 scenarios
136 / 136 same final result sets
134 / 136 same final order
132 / 136 exact dense + final parity
0 blocking classifications
0 measured Hit / Precision / Recall / MRR regression
```

The file backend remains the exact reference, evaluation oracle, and rollback path.

---

## Search and discovery contracts

### Free-form search

```text
GET /search
```

Modes:

- `lexical`
- `dense`
- `hybrid`

Current hybrid defaults:

```text
lexical weight = 0.55
dense weight = 0.45
```

An evaluated dense-heavier candidate exists, but the production default has not been changed.

### Similar papers

```text
GET /discovery/papers/{canonical_id}/similar
```

Modes:

- `semantic`
- `radar_adjusted`

This contract starts from a paper embedding and requires self-exclusion. It is intentionally separate from text-query search.

### Discovery ranking

```text
GET /discovery/ranking/{profile}
```

Profiles use derived paper features such as:

- recency;
- source confidence;
- implementation readiness;
- citation signal;
- artifact availability.

### Topic navigation

Current topic artifacts:

```text
clusters = 80
assignments = 60,954
projection rows = 2,080
```

Cluster labels are heuristic, build-scoped navigation hints rather than a stable curated taxonomy.

---

## Validation and evidence

Validation is a first-class part of the architecture.

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
- strict Definition of Done.

Current provenance evidence:

```text
documents checked = 60,954
structural errors = 0
warnings = 0
informational doc_ids_shorter_than_sources = 9,095
```

The informational count is expected because `doc_ids` are deduplicated while `sources` preserve contributing provenance rows.

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

Generated artifacts are evidence/materializations, not substitutes for accepted source contracts.

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

### Implemented/core

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

### Planned extensions

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
- Alembic when incremental DB migrations become necessary;
- a dedicated frontend after API contracts stabilize;
- graph-aware retrieval and GraphRAG-like reasoning;
- selected Rust/Java/C++/C utilities where justified.

Planned technologies are options in a staged architecture, not mandatory checklist items.

---

## Long-term functional roadmap

The roadmap below describes intended capabilities, not the chronological status of the current repository. Many foundations and several later evaluation/discovery capabilities are already implemented in a different order.

### Foundation and source platform

- source adapters;
- raw and normalized snapshots;
- canonical reconciliation;
- provenance;
- Postgres materialization;
- artifact evidence;
- safe refresh and promotion.

### Retrieval and ranking

- lexical, dense, and hybrid retrieval;
- scientific embedding generations;
- hybrid-weight studies;
- rerankers;
- learned sparse methods;
- graph-aware retrieval;
- feedback-aware and personalized ranking.

### Enrichment and research objects

- structured task/method/dataset/metric extraction;
- summaries;
- taxonomy labels;
- entities;
- novelty signals;
- citation and evidence graphs;
- stronger paper-artifact linkage.

### Product and UX

- feed and filters;
- bookmarks;
- saved searches;
- watchlists;
- reading lists;
- exports;
- alerts and digests;
- paper comparison;
- “why recommended?” explanations;
- learning paths;
- richer paper and artifact workspaces;
- dedicated frontend when justified.

### Analytics and graphs

- topic evolution;
- research timelines;
- citation/reference graph;
- artifact graph;
- source/evidence graph;
- trend dashboards;
- cluster comparison;
- graph exports.

### Full text, RAG, and research workflows

- full-text acquisition;
- section/chunk contracts;
- chunk embeddings;
- grounded RAG with citations;
- paper comparison;
- survey generation;
- guided research workflows;
- research-agent mode.

### Dataset release track

Potential releases:

1. clean paper metadata;
2. paper–artifact links;
3. topic/cluster artifacts;
4. research graph exports;
5. temporal trends;
6. retrieval pairs and benchmark data.

Potential publication targets:

- GitHub Releases;
- Hugging Face Datasets;
- Kaggle.

Dataset releases remain immutable derived outputs from named accepted checkpoints.

### Observability and MLOps

Staged path:

```text
structured logs
→ Prometheus / Grafana
→ container and host metrics
→ OpenTelemetry tracing
→ Loki / Jaeger / Tempo or equivalent where justified
```

### Batch and workflow orchestration

- Airflow for recurring batch ingest, enrichment, rebuild, evaluation, and release DAGs;
- LangGraph for interactive/stateful LLM research workflows.

Airflow is not used as an interactive agent framework, and LangGraph is not used as a batch ETL scheduler.

### Distributed execution

Ray becomes relevant when measured bottlenecks justify parallel:

- embeddings;
- parsing;
- provider enrichment;
- analytics;
- large candidate builds.

### Event-driven architecture

Kafka remains a future stage for:

- continuous source events;
- multiple independent consumers;
- replay;
- retry/DLQ contracts;
- event-driven indexing.

It is not required for daily or weekly batch refresh.

### Deployment maturity

Kubernetes becomes relevant only after the project has:

- independently scalable services;
- workers and recurring jobs;
- stable storage contracts;
- secrets management;
- observability;
- real need for replicas, rollout, and recovery.

### Polyglot extensions

Possible focused additions:

- Rust for fast JSONL/CSV streaming and text utilities;
- Java for a bounded metadata-service experiment;
- C++ for educational ANN/performance tooling;
- C for narrowly justified streaming utilities;
- Bash for bootstrap, smoke, and local automation.

Polyglot work must reinforce the platform rather than fragment it.

---

## Current development sequence

The current representative corpus is intentionally retained while semantics remain cheap to rebuild, evaluate, and inspect.

Accepted sequence:

```text
current-state and evidence synchronization
→ choose one focused technical/product slice
→ validate the next retrieval generation
→ medium-scale candidate rehearsal
→ deployment-level Qdrant selector
→ larger accepted corpus
→ orchestration and distributed infrastructure only when justified
```

Candidate next focused slices:

- Ranking Evaluation and Hardening v1
- Retrieval Generation Study v1
- Graph/Evidence Contract v1
- Lexical Performance Profiling v1
- Discovery Product Enhancement

The next slice is selected explicitly. Public Qdrant promotion, a new embedding model, hybrid-weight changes, and ranking redesign are not bundled together.

---

## Implementation principles

- Build from simple to complex.
- Prefer complete vertical slices over feature sprawl.
- Preserve canonical truth and provenance.
- Keep derived layers rebuildable.
- Separate retrieval strategy from serving backend.
- Keep business logic in `radar_core`.
- Keep services thin.
- Measure quality before changing defaults.
- Treat generated reports as evidence.
- Promote candidates explicitly.
- Add infrastructure only after operational triggers appear.
- Preserve exact references and rollback paths.
- Review code ownership as the project grows.

---

## Explicitly out of scope

To keep the project coherent, the roadmap excludes unrelated additions that do not strengthen research discovery, retrieval, ranking, evidence, reasoning, analytics, or platform operation.

Examples:

- unrelated reinforcement-learning demos;
- image-generation features;
- training large foundation models from scratch;
- isolated technology demos without integration into the platform.

---

## Documentation map

- `docs/architecture.md` — current architecture and responsibilities
- `docs/roadmap.md` — primary living roadmap and validated checkpoints
- `docs/data_contracts.md` — paper/source contracts
- `docs/merge_policy.md` — canonical merge semantics
- `docs/provenance_semantics.md` — provenance interpretation
- `docs/source_matrix.md` — current source landscape
- `docs/source_onboarding_v1.md` — source onboarding lifecycle
- `docs/refresh_contract_v1.md` — refresh/promotion safety
- `docs/api_reference.md` — API surfaces
- `docs/dataset_strategy.md` — future public dataset boundary
- `docs/scaling-and-vector-serving-strategy-v1.md` — accepted scaling strategy

---

## Local workflow

Git operations:

```text
Git Bash
```

Python, tests, validators, and project scripts:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

Local Postgres and Qdrant infrastructure:

```text
infra/docker/
```

---

## License

MIT License
