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
checkpoint = Current Project State Checkpoint v0.2 / Scientific Entity Literal Baseline Pilot Evaluation v0.1
base checkpoint = safe canonical refresh and synchronized core/Discovery derived layers
scientific entity status = bounded literal baseline + deterministic evaluation harness + completed prediction-blind 24-paper pilot
scientific entity quality status = descriptive pilot evidence; literal control not production-selected; no full-corpus build
public behavior change = none
public dense/hybrid backend = file
experimental Qdrant endpoint = explicit
fallback = absent
Qdrant promotion = not performed
dataset public upload = not performed
recommended refresh entrypoint = scripts.update.run_refresh_operational_flow
```

The transfer-safe current-state record is
[`docs/project_state_current_v0.2.md`](docs/project_state_current_v0.2.md).

The aggregate real-paper pilot record is
[`docs/scientific_entity_literal_baseline_pilot_evaluation_v0.1.md`](docs/scientific_entity_literal_baseline_pilot_evaluation_v0.1.md).

Current corpus and retrieval baseline:

```text
pre-promotion canonical baseline = 60,954
current canonical latest = 61,075
canonical delta = +121
removed documents = 0
multisource documents = 9,226

retrieval build = 20260818T105227Z
retrieval corpus documents = 61,075
embedding model = sentence-transformers/all-MiniLM-L6-v2
embedding shape = [61075, 384]
dense vectors normalized = true
```

Current discovery baseline:

```text
paper feature rows = 61,075
topic clusters = 80
topic cluster build = 20260818T110734Z
topic projection rows = 2,080
topic projection build = 20260818T111232Z
ranking profiles = 9
```

Previous experimental Qdrant build-scoped baseline:

```text
collection = ml_radar_dense_benchmark_v1
points = 60,954
vector size = 384
distance = Cosine
experimental transport = gRPC
selected ANN profile = ef_256
synchronized to current canonical = false
publicly promoted = false
```

Paper–Artifact Graph, Citation / Reference Graph, Qdrant, and metadata release
outputs tied to `60,954` remain valid historical/build-scoped candidates. They
are not silently current against canonical latest `61,075` and require an
explicit rebuild and validation decision before reuse as current outputs.

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

Experimental Qdrant search remains explicit and build-scoped:

```text
GET /experimental/search/qdrant
→ configured Qdrant dense collection
→ recorded local collection currently belongs to the previous 60,954-paper build
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

scientific entity mention evidence
= contract-first derived evidence layer; no canonical mutation or entity linking in v0.1

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

scientific mention_id / evidence_id
= typed source span identity / extractor observation identity
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


### Dataset release track

Implemented local metadata-only dataset release candidate pipeline:

```text
contract
→ config validation
→ local export runner
→ output validation
→ data-quality summary
→ review-readiness gate
```

Current candidate identity:

```text
dataset = ml_research_radar_metadata
version = v0.1
release_family = clean_research_metadata
publication_status = not_published
manual_review_required_before_publication = true
```

Expected local candidate layout:

```text
data/datasets_release/ml_research_radar_metadata/v0.1/
├── data.parquet
├── schema.json
├── manifest.json
├── README.md
├── data_quality_summary.json
└── checksums.txt
```

A green review-readiness gate means the candidate is technically ready for
manual review. It does not approve public publication.

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

This endpoint is explicit and experimental. It uses Qdrant gRPC and the selected
profile, but the recorded collection is not synchronized with the current
`61,075`-paper retrieval generation. It does not change `/search`.

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
assignments = 61,075
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
- Scientific Entity Evidence Contract and deterministic fixture;
- bounded Scientific Entity Extractor Baseline build and output validation;
- Scientific Entity Evaluation Harness exact/relaxed metrics and independent validation;
- bounded Scientific Entity Manual Review preparation/finalization and independent validation;
- 24-paper Scientific Entity literal-baseline pilot evaluation checkpoint;
- Qdrant collection, parity, profile sweep, performance, and hybrid evaluation;
- retrieval-serving checkpoint gate;
- strict Definition of Done.

Previous `60,954`-paper provenance evidence:

```text
documents checked = 60,954
structural errors = 0
warnings = 0
informational doc_ids_shorter_than_sources = 9,095
```

The informational count is expected because `doc_ids` are deduplicated while
`sources` preserve contributing provenance rows. This older report remains
build-scoped and is not presented as the current `61,075`-paper provenance
report.

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

1. **Scientific Entity Evidence Contract v0.1 — implemented.**
   The accepted foundation defines mention/evidence identity, six entity types,
   exact Unicode spans, extractor provenance, confidence semantics, and
   immutable build compatibility without downloading a model.

2. **Bounded Scientific Entity Extractor Baseline v0.1 — implemented.**
   A deterministic literal adapter, plan/execute builder, immutable six-file
   output, independent validator, and synthetic regression fixtures exercise
   the contract without full-corpus generation or production NER claims.

3. **Scientific Entity Evaluation Harness v0.1 — implemented.**
   Exact and relaxed one-to-one matching, per-type/source-field metrics,
   structural error evidence, immutable output, and independent recomputation
   are executable on a deterministic synthetic fixture.

4. **Bounded Scientific Entity Manual Review Evidence v0.1 — implemented.**
   Deterministic uniform/type-enriched sampling, prediction-blind annotation
   preparation, explicit finalization, immutable local packages, and independent
   validation are executable. Its tracked fixture remains synthetic.

5. **Bounded Real-Paper Manual Review and Literal Baseline Pilot v0.1 — completed.**
   The local 24-paper, 48-row prediction-blind review contains 435 reference
   mentions. The literal candidate emitted 30 predictions and passed the
   immutable evaluation plus 69-check independent validation. Exact F1 is
   `0.043012`; relaxed F1 is `0.068818`. Metrics remain descriptive.

6. **Bounded Candidate Extractor Selection and Adapter — next.**
   Reuse the existing evidence contract and evaluation harness. Compare a
   bounded candidate only after recording quality, license, exact revision,
   latency, memory, determinism, artifact identity, and provenance. Literal
   v0.1 remains the unchanged control.

7. **Accepted Derived Entity Build**
   Requires a separately frozen candidate, held-out prediction-blind evidence,
   reproducibility gates, and explicit human acceptance before full-corpus use.

8. **Product Integration**
   Only after quality gates; entities remain downstream of canonical truth.

9. **Full-text / Chunk Provenance / Grounded RAG**
   Separate acquisition and evidence contract after the entity layer is stable.

Dataset publication remains paused pending explicit redistribution guidance.
Qdrant promotion, new embeddings, Airflow, and GraphRAG remain deferred until a
measured requirement justifies their separate acceptance slices.

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
