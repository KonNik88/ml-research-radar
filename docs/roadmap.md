# Roadmap

## Purpose

This roadmap is the primary living planning document for **ML Research Radar**.

It describes:

- what the project is;
- what is already green;
- what architectural invariants must not be broken;
- what should be done next;
- what is intentionally postponed.

The roadmap is intentionally incremental. The project prefers closing stable, validated vertical slices over expanding feature surface too early.

Current strategic direction:

```text
stable canonical corpus
→ derived retrieval/materialized layers
→ artifact evidence layer
→ paper features
→ product discovery API
→ thin Streamlit UI
→ topic clusters / topic map
→ retrieval-quality hardening
→ vector serving / future RAG / analytics / dataset releases
```

The project has moved beyond a source-ingestion-only phase. The current priority is to preserve canonical/data-contract discipline while making the corpus useful through validated discovery workflows.

---

## 0. Current checkpoint

Current working checkpoint:

```text
Discovery Green Checkpoint — 2026-05
```

This is a working green checkpoint, not necessarily a formal versioned public release.

Current green state:

```text
canonical_doc_count = 60954
canonical_multisource_docs = 9192
doi_count = 10183

arXiv backbone = 60000
ACL-family docs = 957
ACL-only docs = 954
ACL-enriched existing docs = 3

retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]

artifact_entities_db_count = 7333
artifact_observations_db_count = 38246
paper_artifact_links_db_count = 7430

github_found_count = 5339
huggingface_found_count = 77

paper_features_rows_count = 60954

topic_clusters_count = 80
topic_cluster_assignments_count = 60954
topic_projection_algorithm = umap
topic_projection_points_count = 2080

strict_DoD_required_checks = 132
strict_DoD_failed_checks = 0
strict_DoD_passed = true
```

Current source of truth for the actual implementation state:

```text
fresh code + latest reports + strict DoD
```

If older documentation conflicts with fresh validators/reports/code, the fresh validators/reports/code win.

---

## 1. Guiding architecture

ML Research Radar is a **paper-centric canonical corpus and discovery platform** for ML/AI research.

It is not:

- just an arXiv parser;
- just a JSONL search toy;
- just a RAG demo;
- just a set of disconnected ingest scripts.

Core architecture:

```text
sources
→ raw/source records
→ normalized source-level documents
→ alignment / enrichment
→ reconcile / identity resolution
→ canonical paper corpus
→ retrieval artifacts
→ Postgres serving layer
→ artifact evidence layer
→ paper features
→ ranking / paper detail / similar papers
→ Discovery API
→ Streamlit Discovery UI
→ topic clusters / topic projection
→ retrieval evaluation / controlled experiments
→ future vector serving / RAG / analytics / dataset releases
```

Main invariants:

```text
canonical_documents.jsonl = paper-level truth
Postgres = materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization plane
paper_features / ranking / detail / similar = derived discovery layer
topic clusters / topic projection = derived analytics/discovery layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin client over Discovery API
```

GitHub and Hugging Face enrich artifacts. They are not paper truth sources.

Topic clusters and topic projections are derived from retrieval/canonical/features artifacts. They are not paper truth and do not modify canonical identity.

---

## 2. Completed / current stages

### 2.1 Canonical paper corpus foundation

Status: **done / green**

Completed:

- source normalization layer;
- canonical reconciliation layer;
- paper-centric canonical corpus;
- provenance-preserving merge;
- arXiv-backed medium-scale corpus;
- aligned enrichment from:
  - OpenAlex;
  - Semantic Scholar;
  - Crossref;
- ACL Anthology integration as the first source-expansion case;
- conservative paper identity resolution;
- DOI normalization hardening;
- DOI conflict guard: DOI must not collapse different arXiv base IDs;
- canonical contract validator;
- canonical sanitize after ACL extra-field issue;
- source-level vs canonical-level identity separation.

Current stable paper sources:

```text
arxiv
openalex_alignment
semantic_scholar_alignment
crossref_alignment
acl_anthology
```

Current operational paper source of truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

Current green corpus baseline:

```text
canonical_doc_count = 60954
canonical_multisource_docs = 9192
doi_count = 10183
arXiv backbone = 60000
ACL-family docs = 957
ACL-only docs = 954
ACL-enriched existing docs = 3
```

ACL integration outcome:

```text
1030 normalized ACL records
957 ACL-family docs in stable canonical
954 ACL-only docs
3 ACL-enriched existing docs
73 title-year-only overlaps excluded from automatic merge
```

Important principle:

```text
Canonical JSONL remains the paper-level source of truth.
Postgres, retrieval artifacts, artifact tables, features, clustering artifacts and APIs are materializations over that truth.
```

---

### 2.2 Retrieval foundation

Status: **done / green**

Completed:

- lexical retrieval;
- dense retrieval;
- hybrid retrieval;
- retrieval artifact build pipeline;
- retrieval manifest;
- retrieval evaluation utilities;
- retrieval validation checks;
- file-backend retrieval runtime;
- manifest-based dense artifact resolution for similar papers;
- manifest-based dense artifact resolution reused by topic clusters and topic projection.

Current retrieval build:

```text
build_id = 20260504T164021Z
corpus_doc_count = 60954
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]
```

Current retrieval manifest:

```text
artifacts/retrieval/manifests/latest.json
```

Current dense paths are resolved from the retrieval manifest, not by naive auto-discovery:

```text
artifacts/retrieval/dense/embeddings_20260504T164021Z.npy
artifacts/retrieval/dense/ids_20260504T164021Z.json
artifacts/retrieval/dense/meta_20260504T164021Z.json
```

Important principle:

```text
Retrieval artifacts are derived from the canonical paper corpus and are not source of truth.
```

Current caveat:

```text
all-MiniLM-L6-v2 is accepted for functional validation v1.
Stronger scientific embeddings are a future quality milestone.
```

---

### 2.3 Storage-backed core v1

Status: **done / green**

Completed:

- Postgres infrastructure;
- Qdrant infrastructure placeholder;
- SQL schema for canonical serving tables;
- export to Postgres;
- Postgres document store;
- DB-backed `/documents`;
- dual-backend runtime foundation;
- `export_postgres_v1 --replace` hardening;
- source lookup index folded into `store/sql/02_indexes.sql`.

Current Postgres paper DB baseline:

```text
canonical_documents = 60954
```

Postgres remains a materialized serving layer. The canonical JSONL corpus remains the operational source of truth.

---

### 2.4 DB-backed `/search` v1

Status: **done**

Completed:

- DB backend `/search`;
- lexical search only in DB backend v1;
- explicit rejection of `dense` / `hybrid` in DB backend;
- integration tests for DB search path;
- preservation of existing file retrieval path.

Important principle:

```text
file backend = retrieval-first
DB backend = browse/filter + lexical search v1
```

Dense/hybrid parity in DB backend is not required at this stage. Future dense serving should likely go through a vector-serving layer rather than forcing dense retrieval into the current SQL backend.

---

### 2.5 Source viability gate

Status: **done**

Completed:

- Papers with Code live integration was evaluated and blocked;
- PWC-specific active integration was removed from stable source paths;
- source viability checklist introduced;
- source viability config introduced;
- source viability validation script introduced;
- candidate sources checked before integration work;
- ACL Anthology validated and promoted as the first major source onboarding case.

Current viability outcome:

```text
github: operational artifact enrichment provider
huggingface_hub: operational artifact enrichment provider
acl_anthology: integrated paper source
openreview: viable paper source candidate
pubmed: viable domain paper source candidate
biorxiv: viable domain paper source candidate
medrxiv: viable domain paper source candidate
paperswithcode: blocked / archived live source
```

Key rule:

```text
viability first, candidate integration second, stable integration last
```

---

### 2.6 Artifact Layer v1

Status: **done / green**

Completed:

- internal artifact URL extraction from canonical/source documents;
- URL normalization;
- artifact classification;
- `artifact_entities_latest.jsonl`;
- `artifact_links_latest.jsonl`;
- artifact quality report;
- SQL schema for artifact entities, observations and trusted paper-artifact links;
- Postgres artifact export;
- artifact DB smoke check;
- artifact checks in refresh Definition of Done;
- refresh pipeline artifact stages;
- DB-backed artifact API:
  - `GET /artifacts`;
  - `GET /artifacts/{artifact_id}`;
  - `GET /artifacts/{artifact_id}/papers`;
  - `GET /documents/{canonical_id}/artifacts`;
  - `GET /documents` trusted artifact filters;
- integration tests for artifact API and document artifact filters.

Current artifact baseline:

```text
artifact_entities_raw_count = 7336
artifact_entities_db_count = 7333
artifact_observations_count = 38246
trusted_paper_artifact_links_count = 7430
```

Important principle:

```text
Artifact Layer v1 is a separate evidence/materialization plane.
It does not modify canonical paper truth.
```

---

### 2.7 GitHub Artifact Enrichment v1

Status: **done / green**

Completed:

- snapshot enrichment over extracted GitHub `artifact_entities`;
- GitHub REST API fetch for repository metadata;
- timestamped + latest enrichment outputs;
- standalone strict validation report;
- optional GitHub metadata merge in artifact Postgres export;
- optional GitHub enrichment checks in refresh DoD;
- optional GitHub enrichment stages in refresh pipeline;
- enriched GitHub metadata exposed through existing DB artifact API;
- DB artifact API supports GitHub-specific enriched filters;
- GitHub metadata is consumed by paper features and paper detail cards.

Current GitHub enrichment baseline:

```text
github_entities_count = 5953
metadata_rows_count = 5953
found_count = 5339
not_found_count = 614
forbidden_count = 0
rate_limited_count = 0
error_count = 0
ok = true
```

Important principles:

- GitHub is an artifact enrichment source, not a paper source.
- GitHub enrichment does not alter canonical paper truth.
- `not_found` repositories are preserved as historical artifact evidence.
- GitHub enrichment remains optional because GitHub API is a live external dependency.
- `GITHUB_TOKEN` should be used for large enrichment reruns.

---

### 2.8 Hugging Face Artifact Enrichment v1

Status: **done / green with expected diagnostics**

Completed:

- extracted Hugging Face model/dataset/space entities enriched through Hub API;
- provider-specific snapshot metadata;
- standalone strict validation report;
- HF metadata merge in `export_artifacts_postgres_v1.py`;
- Postgres materialization into `artifact_entities.metadata.huggingface`;
- selected generic artifact columns materialized where available;
- optional HF checks in refresh DoD;
- optional HF stages in refresh pipeline;
- HF metadata consumed by paper features and paper detail cards.

Current Hugging Face enrichment baseline:

```text
huggingface_entities_count = 100
metadata_rows_count = 100
found_count = 77
forbidden_count = 2
skipped_invalid_external_id_count = 21
rate_limited_count = 0
error_count = 0
ok = true
```

Important principles:

- Hugging Face is an artifact enrichment provider, not a paper source.
- `forbidden` rows are provider/access states and remain diagnostic.
- `skipped_invalid_external_id` rows are recognized extraction/noise states and remain diagnostic.
- Neither state fails the current core strict gate.
- Provider-specific Hugging Face API filters are postponed until there is a clear product need.

---

### 2.9 Paper Features v1

Status: **done / green**

Completed:

- file-first feature layer over canonical truth and artifact/enrichment snapshots;
- `data/features/paper_features_latest.jsonl`;
- strict paper features validator;
- feature quality report;
- DoD integration through `--require-paper-features`.

Current feature build baseline:

```text
features_rows_count = 60954
canonical_rows_count = 60954
features_vs_canonical_rows_match = true
scores_in_range = true
required_fields_present = true
```

Feature coverage:

```text
has_acl_count = 957
has_arxiv_count = 60000
has_doi_count = 10183
has_code_artifact_count = 6218
has_dataset_artifact_count = 192
has_model_artifact_count = 48
has_demo_artifact_count = 319
github_found_repo_paper_count = 5354
hf_found_paper_count = 68
```

Scores:

```text
implementation_readiness_score
source_confidence_score
citation_signal_score
recency_score
radar_score
```

Important principle:

```text
Paper features are derived, transparent v1 heuristics.
They are not canonical paper truth and not ML-learned quality labels.
```

---

### 2.10 Ranking / Paper Detail / Similar Papers v1

Status: **done / green**

Completed:

- profile-based ranking over `paper_features_latest.jsonl`;
- ranking profile config;
- ranking profile validator;
- ranking report validator;
- paper detail/card builder;
- paper detail validator;
- semantic similar papers over current dense retrieval embeddings;
- radar-adjusted similar papers mode;
- similar papers validator;
- similar papers DoD gate.

Current ranking profiles:

```text
acl_artifact_ready
acl_radar
high_confidence_radar
huggingface_ready
recent_artifact_ready
recent_code_radar
recent_dataset_ready
recent_model_ready
recent_transformer_radar
```

Current default profile:

```text
recent_artifact_ready
```

Current product workflow:

```text
ranking profile
→ paper detail/card
→ similar papers
→ validators
→ strict DoD
```

Current similar modes:

```text
semantic
radar_adjusted
```

Current `radar_adjusted` formula:

```text
0.85 * semantic_similarity_norm
+ 0.10 * radar_score
+ 0.05 * implementation_readiness_score
```

Current similar-papers quality state:

```text
target_found = true
results_non_empty = true
self_not_in_results = true
canonical_ids_unique = true
scores_in_range = true
sorted_correctly = true
ids_count_matches_input_rows = true
```

---

### 2.11 Discovery API

Status: **done / green**

Completed:

- product discovery namespace:
  - `GET /discovery/profiles`;
  - `GET /discovery/ranking/{profile_name}`;
  - `GET /discovery/papers/{canonical_id}`;
  - `GET /discovery/papers/{canonical_id}/similar`;
  - `GET /discovery/papers/{canonical_id}/cluster`;
  - `GET /discovery/clusters`;
  - `GET /discovery/clusters/{cluster_id}`;
  - `GET /discovery/clusters/map`;
- file-first `DiscoveryService`;
- profile-based ranking endpoint;
- ranking query overrides;
- paper detail endpoint;
- semantic/radar-adjusted similar papers endpoint;
- topic-cluster endpoints;
- topic-map endpoint;
- integration tests for Discovery API;
- Discovery API quality validator;
- DoD gate through `--require-discovery-api`.

Supported ranking override parameters:

```text
top_k
min_year
max_year
query_title
source_family
has_code
has_dataset
has_model
has_demo
has_github
has_hf
has_acl
has_doi
sort_by
descending
```

Override semantics:

```text
profile filters = base preset
query params = explicit overrides/additions
response.filters = effective filters after overrides
response.sort_by = effective sort field
response.descending = effective sort direction
```

Quality-gate override smoke:

```http
GET /discovery/ranking/recent_artifact_ready?top_k=5&min_year=2025&has_code=true
```

Current Discovery API quality state:

```text
profile_count = 9
ranking_results_count = 5
ranking_overrides_results_count = 5
similar_semantic_results_count = 5
similar_radar_adjusted_results_count = 5
topic_cluster_count = 80
topic_cluster_map_projection_algorithm = umap
required_failed_count = 0
```

Impact:

```text
ML Research Radar exposes a usable product/discovery API workflow:
profile ranking + query overrides → paper card → similar papers → cluster/topic navigation
```

---

### 2.12 Streamlit Discovery UI

Status: **done / green**

Completed:

- old search-oriented UI replaced with discovery-oriented UI;
- thin client over FastAPI;
- no local JSONL reading in Streamlit;
- no embedding loading in Streamlit;
- no ranking/similar/clustering computation in Streamlit;
- Discovery ranking;
- search tab;
- profile selector;
- filter controls;
- sort controls;
- paper workspace;
- paper detail display;
- similar papers display;
- semantic vs radar-adjusted similar mode selector;
- topic clusters;
- topic map;
- cluster detail filters;
- artifact explorer;
- artifact linked-papers navigation;
- selected paper artifact navigation;
- raw JSON expanders;
- API base URL input;
- health/info/runtime status display;
- API reload button;
- static UI validator.

Run FastAPI:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m uvicorn services.api.app:app --host 127.0.0.1 --port 8000
```

Run Streamlit:

```bat
python -m streamlit run services\ui\app.py --server.port 8501
```

Open:

```text
http://localhost:8501
```

Streamlit UI validators:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
python -m scripts.validation.check_streamlit_discovery_ui --strict --check-api
```

Important principle:

```text
Streamlit UI = thin demo/client layer
Discovery API / radar_core = business logic layer
```

---

### 2.13 Topic Clusters v1

Status: **done / green**

Completed:

- file-first topic clustering layer over current retrieval embeddings;
- manifest-based input resolution;
- MiniBatchKMeans clustering over L2-normalized dense embeddings;
- cluster assignments artifact;
- cluster summary artifact;
- heuristic label candidates artifact;
- cluster label overrides;
- latest pointer;
- build report;
- quality validator;
- cluster inspect utility;
- generated reports under `artifacts/reports/clusters/`;
- Discovery API cluster endpoints;
- Streamlit topic cluster UI.

Current topic cluster build:

```text
cluster_build_id = 20260511T151842Z
retrieval_build_id = 20260504T164021Z
algorithm = minibatch_kmeans
n_clusters = 80
embedding_shape = [60954, 384]
assigned_rows_count = 60954
cluster_count = 80
empty_cluster_count = 0
largest_cluster_ratio = 0.024494
```

Core implementation files:

```text
configs/topic_clusters_v1.yaml
radar_core/analytics/topic_clusters.py
scripts/analytics/build_topic_clusters.py
scripts/analytics/inspect_topic_cluster.py
scripts/validation/check_topic_clusters.py
```

Generated outputs:

```text
artifacts/clusters/topic/runs/<cluster_build_id>/assignments.jsonl
artifacts/clusters/topic/runs/<cluster_build_id>/summary.json
artifacts/clusters/topic/runs/<cluster_build_id>/label_candidates.json
artifacts/clusters/topic/latest.json

artifacts/reports/clusters/topic_clusters_latest.json
artifacts/reports/clusters/topic_clusters_latest.md
artifacts/reports/clusters/topic_clusters_quality_latest.json
artifacts/reports/clusters/topic_clusters_quality_latest.md
```

Quality command:

```bat
python -m scripts.validation.check_topic_clusters --strict
```

Important semantics:

```text
label_candidates = heuristic topic hints
label_candidates are not canonical labels
label_candidates are not curated taxonomy
cluster_id is stable only inside a specific cluster_build_id/config/input corpus
```

Important principles:

- topic clusters are derived analytics/discovery artifacts;
- topic clusters do not modify canonical truth;
- topic clusters do not replace similar papers;
- similar papers = local nearest neighbors around one paper;
- topic clusters = corpus-level landscape / navigation layer;
- ranking = promising/useful/artifact-ready papers;
- generated clustering artifacts should not be committed.

---

### 2.14 Topic Projection / Topic Map v1

Status: **done / green**

Completed:

- offline 2D projection artifact;
- UMAP-based topic map;
- projection summary;
- topic map endpoint;
- topic map UI support;
- projection quality validator;
- DoD gate through `--require-topic-projection`.

Current projection state:

```text
projection_build_id = 20260515T154038Z
cluster_build_id = 20260511T151842Z
retrieval_build_id = 20260504T164021Z
projection_algorithm = umap
projection_rows_count = 2080
centroid_count = 80
representative_count = 800
sampled_count = 1200
```

Quality state:

```text
projection_enabled = true
projection_exists = true
projection_rows_non_empty = true
projection_xy_finite = true
one_centroid_per_cluster = true
centroid_count_matches_cluster_count = true
cluster_build_id_matches_topic_clusters = true
retrieval_build_id_matches_manifest = true
required_failed_count = 0
```

Important principle:

```text
Projection is an offline derived artifact.
It is not computed on every API/UI request.
```

---

### 2.15 Retrieval evaluation / search quality layer

Status: **done / green**

Completed:

- golden query based retrieval evaluation;
- lexical/dense/hybrid/hybrid_ranked comparison;
- retrieval eval quality validator;
- search-quality experiments;
- controlled search-quality experiments;
- golden labeling candidates export;
- quality validators for all major evaluation reports.

Current retrieval eval state:

```text
enabled_cases_count = 18
executed_cases_count = 18
expected modes = lexical / dense / hybrid / hybrid_ranked
runtime_errors = 0

hybrid_empty_result_rate = 0.0
hybrid_hit_at_10 = 1.0
hybrid_mrr_at_10 = 1.0
hybrid_recall_at_10 = 0.80415
hybrid_ndcg_at_10 = 0.852013
```

Current search-quality experiments:

```text
mode_table_count = 4
pareto_frontier_count = 3
recommendations_count = 10
required_failed_count = 0
```

Current controlled experiments:

```text
enabled_cases_count = 18
variants_count = 32
hybrid_variants_count = 30
runs_count = 576
error_count = 0
pareto_frontier_count = 4
recommendations_count = 7
required_failed_count = 0
```

Current golden labeling candidates:

```text
enabled_queries_count = 10
queries_with_candidates_count = 10
modes_count = 4
total_candidates_count = 300
mode_error_count = 0
```

Important principle:

```text
Do not change retrieval defaults purely by intuition.
Use retrieval eval, controlled experiments and golden labeling expansion.
```

Current caveat:

```text
The golden set is still relatively small.
Retrieval-quality conclusions are useful but should not be treated as final scientific benchmarking.
```

---

### 2.16 Audit / diagnostics / validation / DoD layer

Status: **done / green**

Completed:

- corpus audit;
- source corpus audit;
- overlap diagnostics;
- source-to-canonical comparison;
- source metadata diagnostics;
- multisource inspection;
- retrieval checks;
- postpass audit;
- known issues snapshot;
- refresh Definition of Done;
- provenance consistency checks;
- canonical contract check;
- artifact links quality check;
- GitHub enrichment check;
- Hugging Face enrichment check;
- paper features quality check;
- ranking profiles quality check;
- ranking report quality check;
- paper detail quality check;
- similar papers quality check;
- Discovery API quality check;
- topic clusters quality check;
- topic projection quality check;
- Streamlit Discovery UI quality check.

Current strict DoD command:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api --require-topic-clusters --require-topic-projection --require-streamlit-discovery-ui
```

Current expected result:

```text
dod_passed = true
required_failed_count = 0
```

Current latest known-issues path:

```text
artifacts/reports/validation/known_issues_snapshot_latest.json
```

Important note:

```text
--require-similar-papers checks latest similar_papers_quality report.
It does not create a corpus-wide all-pairs similar-papers artifact.
```

Before strict DoD with similar-papers requirement, generate/validate latest similar report when needed:

```bat
python -m scripts.ranking.demo_radar_ranking --profile huggingface_ready --top-k 5
python -m scripts.details.build_paper_detail --from-latest-ranking-rank 1
python -m scripts.retrieval.find_similar_papers --from-latest-detail --top-k 20
python -m scripts.validation.check_similar_papers_report --strict
```

Important principle:

```text
Validation reports are not just logs.
They are the operational evidence that a derived layer is aligned with canonical truth.
```

---

## 3. Current system state summary

The project is currently at this point:

- canonical 60,954-paper corpus is green;
- arXiv 60k backbone is preserved;
- ACL Anthology is integrated and sanitized;
- OpenAlex, Semantic Scholar and Crossref enrich the arXiv backbone;
- retrieval artifacts are built and validated on 60,954 docs;
- Postgres paper serving layer is green;
- artifact extraction is green;
- artifact DB materialization is green;
- GitHub artifact enrichment is green;
- Hugging Face artifact enrichment is green with expected diagnostics;
- paper features layer is green;
- ranking profiles are green;
- paper detail/card is green;
- similar papers are green;
- Discovery API is green;
- ranking query overrides are green;
- topic cluster endpoints are green;
- topic map endpoint is green;
- Streamlit Discovery UI is green;
- topic clusters v1 are green as file-first derived analytics artifacts;
- topic projection / topic map v1 is green;
- retrieval eval/search-quality/controlled experiments are green;
- source viability gate exists;
- Papers with Code live source remains blocked/archived;
- canonical paper truth remains isolated from artifact enrichment and all derived discovery layers.

Current closed vertical slice:

```text
60954 canonical corpus
→ retrieval artifacts
→ Postgres serving layer
→ Artifact Layer v1
→ GitHub Artifact Enrichment v1
→ Hugging Face Artifact Enrichment v1
→ paper_features v1
→ ranking profiles + query overrides
→ paper detail/card
→ similar papers
→ topic clusters
→ topic projection / topic map
→ Discovery API
→ Streamlit Discovery UI
→ retrieval/search-quality evaluation
→ strict validation reports
→ full strict DoD
```

---

## 4. Near-term roadmap

Recommended next order:

```text
1. Documentation sync and runbook hardening.
2. Retrieval evaluation / Golden Set Expansion v2.
3. Controlled experiment group-level metrics and default-policy decision support.
4. Topic cluster label/description improvement and UI polish.
5. Qdrant/vector serving proof-of-concept.
6. Stronger scientific embeddings / retrieval profiles.
7. OpenReview candidate source.
8. Future RAG/full-text layer.
```

Rationale:

The project has already closed ingestion/reconcile/artifact/features/ranking/detail/similar/API/UI/topic-cluster/topic-map vertical slices. The next risk is not lack of features, but loss of clarity, insufficient evaluation depth, and accidental duplication of already implemented functionality.

---

### 4.1 Documentation sync and runbook hardening

Status: **next**

Goal:

```text
Make roadmap/docs/runbook match current code + latest reports + strict DoD.
```

Tasks:

- update roadmap with the current checkpoint;
- update architecture docs if they still describe implemented components as planned;
- update API reference for current Discovery API/topic/artifact endpoints;
- update source matrix to mark ACL as integrated and PWC as blocked/archived;
- update merge policy with current source/identity semantics;
- update refresh contract/runbook with current strict DoD flags;
- document quick smoke vs full regression vs full strict DoD;
- document that `known_issues_snapshot_latest.json` is the current known-issues snapshot filename.

Important principle:

```text
Docs should not overrule fresh validation reports.
Docs should explain them.
```

---

### 4.2 Retrieval evaluation / Golden Set Expansion v2

Status: **near-term**

Goal:

```text
Expand evaluation coverage before changing retrieval defaults.
```

Tasks:

- review `golden_labeling_candidates_latest.json`;
- manually label selected candidates;
- expand `data/eval/retrieval/golden_queries.jsonl`;
- add more query groups:
  - broad topics;
  - method-specific;
  - artifact-seeking;
  - recent-work queries;
  - ACL/NLP queries;
  - edge/diagnostic queries;
  - ambiguous queries;
- rerun retrieval eval;
- rerun search quality experiments;
- rerun controlled experiments;
- compare group-level behavior.

Important principle:

```text
No retrieval default change without evidence.
```

---

### 4.3 Controlled experiment group-level metrics

Status: **near-term**

Goal:

```text
Understand which retrieval policy wins for which query families.
```

Candidate additions:

- metrics by query group;
- metrics by query intent;
- mode winners by group;
- latency by group;
- failure patterns by group;
- ranked vs unranked effects by group;
- candidate_k sensitivity by group;
- hybrid weight sensitivity by group.

Output:

```text
artifacts/reports/evaluation/search_quality_controlled_experiments_latest.json
artifacts/reports/evaluation/search_quality_controlled_experiments_latest.md
```

Potential decision:

```text
Keep current default if evidence is not strong enough.
Introduce named retrieval profiles instead of one universal default.
```

---

### 4.4 Topic cluster labels / descriptions / UI polish

Status: **near-term**

Goal:

```text
Make topic clusters more interpretable and useful in the product UI.
```

Tasks:

- expand `cluster_label_overrides.json`;
- inspect high-value clusters;
- add curated labels/descriptions where stable;
- expose curated labels in API/UI;
- improve cluster cards;
- improve topic map interactions;
- improve cluster → paper → artifact navigation;
- keep label candidates as hints, not truth.

Important principle:

```text
Cluster labels are discovery aids.
They are not canonical taxonomy.
```

---

### 4.5 Qdrant / vector serving proof-of-concept

Status: **planned after docs/eval hardening**

Goal:

```text
Add a serving-time vector path without changing canonical truth.
```

Candidate tasks:

- create Qdrant collection for paper embeddings;
- upsert canonical_id + vector + metadata payload;
- add vector serving helper;
- add API/backend mode for vector retrieval or similar papers;
- compare file dense vs Qdrant dense:
  - result parity;
  - latency;
  - filtering ergonomics;
  - operational complexity;
- add validator/regression checks.

Important principle:

```text
Qdrant is a derived vector serving layer.
It is not source of truth.
```

---

### 4.6 Stronger embeddings / retrieval quality milestone

Status: **planned**

Goal:

```text
Improve semantic search/similar/clustering quality with scientific embeddings.
```

Candidate tasks:

- research stronger scientific paper embedding models;
- add retrieval profile config;
- build alternate dense embedding index;
- compare similar-papers and topic-cluster quality;
- keep fast default profile with all-MiniLM-L6-v2 unless evidence supports change;
- add scientific semantic profile if quality justifies it.

Possible future profiles:

```text
fast_default = sentence-transformers/all-MiniLM-L6-v2
scientific_semantic = stronger scientific paper embedding model
citation_aware = dense similarity + citation graph signals
hybrid = dense semantic + lexical BM25 + artifact/radar re-ranking
```

---

### 4.7 OpenReview candidate source

Status: **planned later**

Goal:

```text
Add selected OpenReview venues carefully through the viability/candidate/stable pipeline.
```

Tasks:

- ingest OpenReview papers by explicit venue/year scope;
- start with selected ML venues;
- use API v2 / Python client where appropriate;
- preserve OpenReview identifiers;
- keep reviews/ratings/decisions as a separate review/signal layer, not canonical paper truth v1;
- candidate-only until source audit and candidate reconcile impact checks are green.

Important principle:

```text
OpenReview review data should not directly mutate canonical paper identity.
```

---

### 4.8 Biomedical/domain sources

Status: **planned later**

Candidates:

- PubMed;
- bioRxiv;
- medRxiv.

Purpose:

- biomedical/domain expansion;
- possible ML-for-biology / ML-for-medicine coverage;
- separate domain-specific corpus slices.

---

### 4.9 Full-text / RAG / analytics layers

Status: **later**

Planned:

- full-text extraction;
- section-aware chunking;
- chunk-level retrieval;
- citation-aware paper QA;
- cluster summaries;
- research brief generation;
- reference graph;
- artifact graph;
- topic graph;
- trend analytics;
- dataset export track.

Important principle:

```text
RAG is a future product layer over canonical/retrieval/evidence infrastructure.
RAG is not the core project identity.
```

---

### 4.10 Public product packaging / full frontend

Status: **later**

Planned after backend/product contracts are stable:

- full web frontend, likely React/Next.js;
- proper landing page;
- hosted FastAPI backend;
- deployed Postgres;
- vector serving if needed;
- domain name;
- public demo packaging;
- monitoring and observability.

Important principle:

```text
First Streamlit as a thin API demo.
Full frontend/site only after product workflow and backend contracts stabilize.
```

---

## 5. Search / API / product hardening backlog

Planned improvements:

- improve SQL search quality;
- improve retrieval validation queries;
- reduce gap between DB lexical search and file retrieval ergonomics;
- handle modern ML query failures;
- add richer artifact provider filters when provider metadata stabilizes;
- add document/source/reference drilldown endpoints;
- add Discovery API compact/detail response modes;
- add Discovery API latency diagnostics / cache stats;
- add cluster API latency diagnostics / cache stats;
- add retrieval profile selection to API/UI if experiments justify it.

Hugging Face-specific API filters remain postponed until there is a clear product need.

---

## 6. Explicit non-goals for the current stage

Not part of the immediate next step:

- full-text pipeline;
- DB-native dense search parity;
- DB-native hybrid parity;
- LLM summaries;
- RAG serving;
- large-scale graph product layer;
- automatic integration of all viable sources;
- GitHub or Hugging Face as paper sources;
- artifact evidence modifying canonical paper identity;
- ranking papers by GitHub stars or Hugging Face downloads as canonical-quality signals;
- provider-specific API filter redesign after every new provider;
- replacing similar papers with clustering;
- replacing ranking with clustering;
- treating topic cluster labels as curated taxonomy;
- computing clustering or UMAP on every UI/API request;
- replacing canonical truth with Postgres/materialized views;
- full frontend before the Streamlit/API workflow is proven;
- changing retrieval defaults before expanding/validating the golden set.

---

## 7. Guiding principle

The roadmap is intentionally staged:

1. stabilize canonical paper core;
2. stabilize serving and validation;
3. add source viability gate;
4. add separate artifact/entity data plane;
5. enrich artifacts through APIs;
6. add paper features and discovery functions;
7. expose discovery through API;
8. harden discovery API ergonomics;
9. build a thin local UI over Discovery API;
10. add file-first topic clusters / topic map layer;
11. validate discovery, search quality and UI through reports/DoD;
12. strengthen evaluation before changing retrieval defaults;
13. add vector serving carefully;
14. add new paper/domain sources carefully;
15. add richer product/RAG layers;
16. package the project as a full web product only after the core is mature.

The key engineering rule is:

```text
Viability first, candidate integration second, stable integration last.
```

The key product rule is:

```text
Do not collect sources forever without adding usable discovery workflows.
```

The key analytics/discovery rule is:

```text
Derived layers must be rebuildable, validated, and safe to delete/rebuild.
```

The key documentation rule is:

```text
Docs should describe the current validated system, not historical intentions.
```
