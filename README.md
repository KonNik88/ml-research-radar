# ML Research Radar

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-green)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)
![Postgres](https://img.shields.io/badge/Postgres-DB-blue)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20DB-purple)
![Docker](https://img.shields.io/badge/Docker-Containers-blue)
![Kubernetes](https://img.shields.io/badge/Kubernetes-Orchestration-blue)
![Ray](https://img.shields.io/badge/Ray-Distributed-orange)
![Kafka](https://img.shields.io/badge/Kafka-Event%20Streaming-black)
![Observability](https://img.shields.io/badge/Observability-Grafana%20%7C%20Loki%20%7C%20Tempo-orange)

Custom end-to-end platform to discover, organize, rank, analyze, and reason over machine learning papers, repositories, and research trends.

---

## Overview

**ML Research Radar** is a long-horizon, production-like ML systems project focused on research discovery and analysis.

The platform is designed to:

- ingest multi-source ML research content
- normalize and deduplicate documents
- enrich records with summaries, tags, entities, and links
- support semantic and hybrid retrieval
- provide RAG-based question answering over a private corpus
- surface trends, clusters, timelines, and similarity maps
- evolve toward observability, orchestration, event-driven processing, and Kubernetes deployment
- generate structured public research datasets as a natural by-product of the pipeline

This is not a single-model demo. It is an **expandable research platform** with a clear architectural roadmap.

---

## Core Goals

- Build a strong end-to-end ML research discovery system
- Practice modern ML / LLM / MLOps tooling in one coherent project
- Keep the architecture modular and extensible from the start
- Grow the project through versioned vertical slices instead of uncontrolled feature creep
- Reuse derived data later for public dataset releases (Kaggle / GitHub / Hugging Face)

---

## What the System Does

### Research ingestion
Collects data from multiple sources such as:

- arXiv
- GitHub
- OpenAlex
- Crossref

Planned next sources:

- Semantic Scholar
- Hugging Face
- Papers with Code
- domain-specific sources later when justified

### Document normalization
The pipeline normalizes documents and metadata into a stable internal schema using:

- canonical URLs
- stable `doc_id`
- `content_hash`
- source harmonization
- deduplication logic

### Enrichment
Each item can be enriched with:

- TL;DR summary
- taxonomy tags
- task and method labels
- datasets and metrics
- entities and research objects
- paper ↔ repository links
- scoring and ranking features

### Retrieval and RAG
The platform supports:

- semantic search
- similar document retrieval
- hybrid retrieval and reranking later
- RAG answers with citations
- paper comparison workflows
- research-agent style exploration later

### Analytics
The platform is designed to support:

- trend analysis
- topic evolution
- weekly topic maps
- clustering and pseudo-labeling
- research timelines
- graph-based exploration

### Product features
Planned product-facing features include:

- feed and filters
- bookmarks and saved searches
- Telegram digests and alerts
- reading-list generation
- learning-path generation
- explainability (“why recommended?”)

---

## High-Level Architecture

The system follows this pipeline:

```text
Sources
  ↓
Ingest
  ↓
Normalize / Deduplicate
  ↓
Enrich
  ↓
Store
  ↓
Serve
  ↓
Analyze / Export
```

Additional cross-cutting layers:

- LLM workflows
- analytics
- observability
- orchestration
- dataset export

---

## Data Layers

The project separates data into explicit layers:

```text
data/
├── raw/
├── normalized/
├── enriched/
├── analytics/
└── datasets_release/
```

### raw
Raw responses from upstream sources.

Examples:
- API JSON payloads
- source metadata dumps
- PDF references
- raw HTML snapshots when needed

### normalized
Cleaned, canonicalized, deduplicated records.

Examples:
- unified titles/authors/date fields
- canonical URLs
- stable IDs
- cleaned metadata schema

### enriched
Derived ML/LLM outputs.

Examples:
- summaries
- tags
- entities
- repo links
- scores
- clusters
- topic labels

### analytics
Artifacts and structured outputs from analysis workflows.

Examples:
- trend tables
- graph exports
- similarity maps
- topic evolution outputs

### datasets_release
Prepared public dataset exports.

Examples:
- clean metadata dataset
- enriched metadata dataset
- graph/linkage dataset
- topic/cluster dataset

---

## Repository Structure

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

### `radar_core/`
The project’s business logic lives here.

Modules include:

- `ingest/`
- `normalize/`
- `enrich/`
- `retrieval/`
- `ranking/`
- `rag/`
- `analytics/`
- `dataset_export/`
- `contracts/`
- `models/`
- `utils/`

### `services/`
Service wrappers and entry points.

Includes:

- `api/` — FastAPI
- `ui/` — Streamlit
- `workers/`
- `notifications/`
- `airflow/` later
- `langgraph/` later

### `store/`
Persistence layer.

- `sql/`
- `alembic/`
- `qdrant/`

### `infra/`
Infrastructure layout.

- `docker/`
- `k8s/`
- `observability/`

### `docs/`
Project architecture and planning docs.

- `architecture.md`
- `roadmap.md`
- `data_contracts.md`
- `dataset_strategy.md`
- `api_reference.md`

---

## Storage Strategy

### PostgreSQL
Used for:

- canonical documents
- source mappings
- processing state
- enrichments
- tags and relationships
- scores
- feedback
- release metadata

### Qdrant
Used for:

- embeddings
- semantic retrieval
- similarity search
- lightweight payload for search workflows

### File-based storage
Used for:

- raw dumps
- analytics artifacts
- export bundles
- reports and figures

---

## Data Contracts

Several architectural invariants are fixed from the start:

- stable `doc_id`
- `content_hash`
- stage tracking
- pipeline versioning
- schema versioning
- idempotent processing
- separation of raw / derived / serving concerns

Pipeline stages:

```text
FOUND
FETCHED
PARSED
EMBEDDED
ENRICHED
INDEXED
```

These contracts are critical for:

- deduplication
- reproducibility
- re-indexing
- future Kafka integration
- dataset versioning

---

## Tech Stack

### Current / core stack
- Python 3.11
- FastAPI
- Streamlit
- PostgreSQL
- Qdrant
- Pydantic
- Alembic
- Docker Compose
- Sentence Transformers
- PyTorch
- Plotly
- UMAP / HDBSCAN

### Planned stack extensions
- LangChain
- LangGraph
- Ray
- Kafka
- Airflow
- Kubernetes
- Prometheus
- Grafana
- Loki
- Tempo
- Grafana Alloy / OpenTelemetry-based observability

---

## Environment Notes

The project uses a dedicated environment and installs dependencies incrementally by stages.

Environment snapshots are stored in:

```text
environment/
```

Locked package snapshots are stored in:

```text
requirements/
```

This helps keep the project reproducible while the stack grows.

---

## Observability Plan

The observability layer is planned as:

- **Prometheus** for metrics
- **Grafana** for dashboards
- **Loki** for logs
- **Tempo** for traces
- **Alloy** for unified telemetry collection

This layer is intentionally staged later in development, after the core platform becomes functional.

---

## Dataset Release Track

A major side outcome of the project is the ability to release structured public datasets.

Planned dataset families:

1. **Clean Research Metadata**
   - titles, authors, dates, sources, abstracts, tags, methods, tasks

2. **Paper ↔ Code Linking Dataset**
   - paper-to-repository relationships and derived metadata

3. **Topic / Cluster Dataset**
   - cluster IDs, pseudo-labels, topic keywords

4. **Research Graph Dataset**
   - nodes and edges for graph ML and link prediction

5. **Temporal Research Trends Dataset**
   - topic and method evolution across time

Potential release platforms:

- Kaggle
- GitHub Releases
- Hugging Face Datasets

The public dataset track is an extension of the main pipeline, not a separate project.

---

## Roadmap

### v0.1 — Foundation + Core Ingestion
- repository structure
- source adapters (initial)
- Postgres + Qdrant setup
- contracts
- raw ingestion
- normalization foundations

### v0.2 — Search Core
- search API
- similar items
- feed UI
- initial ranking

### v0.3 — Enrichment Layer
- summaries
- structured extraction
- taxonomy tags
- enriched records in Postgres

### v0.4 — RAG Layer
- question answering over corpus
- citations
- source panels
- chat tab in UI

### v0.5 — Product UX Expansion
- bookmarks
- saved searches
- compare papers
- reading lists
- Telegram digests

### v0.6 — Analytics Layer
- trends
- topic maps
- clustering
- timelines
- similarity exploration

### v0.7 — Retrieval Quality Upgrade
- hybrid retrieval
- rerankers
- improved scoring
- feedback-aware ranking

### v0.8 — ML Enrichment Expansion
- NER / entity extraction
- novelty heuristics
- personalization
- user-interest modeling

### v0.9 — Evaluation Layer
- retrieval evaluation
- RAG evaluation
- regression suites
- golden sets

### v1.0 — Observability / MLOps Layer
- metrics
- logs
- traces
- dashboards

### v1.1 — Airflow Orchestration
- scheduled ingest/enrich/export/eval pipelines

### v1.2 — LangGraph / LLM Workflows
- compare workflows
- digest workflows
- research-agent workflows

### v1.3 — Ray Layer
- parallel ingestion
- parallel parsing
- parallel embedding/enrichment

### v1.4 — Kafka Event Layer
- event contracts
- decoupled workers
- retries / DLQ
- event-driven pipeline evolution

### v1.5 — Kubernetes Layer
- deployment separation
- persistent workloads
- monitoring in cluster

### v1.6+ — Polyglot Expansion
- Rust utilities
- Java microservices
- C++ educational vector tooling
- Bash automation

---

## Planned Functional Extensions

### Product
- feed
- filters
- bookmarks
- exports
- watchlists
- saved searches
- Telegram alerts
- explainability
- compare papers
- compare with external pipelines
- reading list generation
- learning path generation

### Analytics
- weekly topic clusters
- similarity maps
- topic dashboards
- topic evolution
- research timeline
- graph views

### ML / retrieval
- rerank models
- taxonomy classifier
- NER / entity extraction
- novelty scoring
- preference modeling
- personalized ranking

### LLM / reasoning
- summarize
- structured extraction
- RAG
- digest generation
- comparison reasoning
- research agent mode
- automatic survey / overview generation

### Engineering
- provider abstraction
- evaluation suite
- observability
- Airflow
- LangGraph
- Ray
- Kafka
- Kubernetes
- CI quality stack

---

## What Is Intentionally Out of Scope

To keep the project coherent, the following are intentionally not part of the plan:

- multimodal generation
- image generation
- unrelated RL demos
- training large models from scratch
- isolated toy features that do not strengthen research discovery, retrieval, ranking, reasoning, or analytics

---

## Implementation Principles

- Build from simple to complex
- Release in vertical slices
- Keep business logic inside `radar_core`
- Keep services as wrappers, not logic containers
- Add new features as modules, stages, workers, endpoints, or tabs
- Avoid rewriting the foundation when extending the system

---

## Current Status

At the current stage:

- project vision is defined
- architecture is formalized
- future extensions are planned
- environment is prepared at a base level
- repository structure is initialized

The next real development step is to start implementing the **core data contracts and document pipeline foundations**.

---

## License

MIT License

---

## Project Summary

**ML Research Radar** is an expandable platform for discovering, structuring, analyzing, and reasoning over machine learning research content — with a roadmap that spans semantic retrieval, RAG, analytics, public datasets, observability, orchestration, event-driven processing, and polyglot engineering extensions.
