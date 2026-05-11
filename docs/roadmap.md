# Roadmap

## Purpose

This roadmap describes the current implementation stage of **ML Research Radar** and the next planned stages.

The roadmap is intentionally incremental. The project prefers closing stable vertical slices over expanding feature surface too early.

Current strategic direction:

```text
stable canonical corpus
→ derived retrieval/materialized layers
→ product discovery API
→ thin UI
→ topic maps / vector serving / future RAG
```

The project has moved beyond a source-ingestion-only phase. The current priority is to preserve canonical/data-contract discipline while building useful product/discovery workflows over the corpus.

---

## 1. Guiding architecture

ML Research Radar is a paper-centric canonical corpus platform for ML/AI research.

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
→ topic clusters / future topic map
→ future vector serving / RAG / analytics / dataset releases
```

Main invariants:

```text
canonical_documents.jsonl = paper-level truth
Postgres = materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization plane
paper_features / ranking / detail / similar = derived discovery layer
topic clusters = derived analytics/discovery layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin client over Discovery API
```

GitHub and Hugging Face enrich artifacts. They are not paper truth sources.

Topic clusters and future topic maps are derived from retrieval/canonical/features artifacts. They are not paper truth and do not modify canonical identity.

---

## 2. Completed / Current Stage

## 2.1 Canonical paper corpus foundation

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

Status: done

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
arXiv backbone = 60000
ACL-family docs = 957
ACL-only docs = 954
ACL-enriched existing docs = 3
DoD passed = true
```

ACL integration outcome:

```text
1030 normalized ACL records
957 ACL-family docs in stable canonical
954 ACL-only docs
3 ACL-enriched existing docs
73 title-year-only overlaps excluded from automatic merge
```

Important principle: canonical JSONL remains the paper-level source of truth. Postgres, retrieval artifacts, artifact tables, paper features, clustering artifacts and APIs are materializations over that truth.

---

## 2.2 Retrieval foundation

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
- manifest-based dense artifact resolution reused by topic clusters.

Status: done

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

Important principle: retrieval artifacts are derived from the canonical paper corpus and are not source of truth.

Current caveat:

```text
all-MiniLM-L6-v2 is accepted for functional validation v1.
Stronger scientific embeddings are a future quality milestone.
```

---

## 2.3 Audit / diagnostics / evaluation layer

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
- paper features quality check;
- ranking profiles quality check;
- ranking report quality check;
- paper detail quality check;
- similar papers quality check;
- Discovery API quality check;
- Streamlit Discovery UI smoke check;
- topic clusters quality check.

Status: done

Current strict DoD command:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api
```

Expected result:

```text
dod_passed = true
required_failed_count = 0
```

Important note:

```text
--require-similar-papers checks latest similar_papers_quality report.
It does not create a corpus-wide similar-papers artifact.
```

Before strict DoD with similar-papers requirement, generate/validate latest similar report when needed:

```bat
python -m scripts.ranking.demo_radar_ranking --profile huggingface_ready --top-k 5
python -m scripts.details.build_paper_detail --from-latest-ranking-rank 1
python -m scripts.retrieval.find_similar_papers --from-latest-detail --top-k 20
python -m scripts.validation.check_similar_papers_report --strict
```

Topic clusters are currently validated by a standalone strict validator:

```bat
python -m scripts.validation.check_topic_clusters --strict
```

Topic clusters are green, but not yet required by the main refresh DoD. Optional DoD integration through `--require-topic-clusters` is a planned hardening step.

---

## 2.4 Storage-backed core v1

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

Status: done

Current Postgres paper DB baseline:

```text
canonical_documents = 60954
```

Postgres remains a materialized serving layer. The canonical JSONL corpus remains the operational source of truth.

---

## 2.5 DB-backed `/search` v1

Completed:

- DB backend `/search`;
- lexical search only in DB backend v1;
- explicit rejection of `dense` / `hybrid` in DB backend;
- integration tests for DB search path;
- preservation of existing file retrieval path.

Status: done

Important principle: file backend is retrieval-first; DB backend is browse/filter + lexical search v1. Dense/hybrid parity in DB backend is not required at this stage.

---

## 2.6 Source viability gate

Completed:

- Papers with Code live integration was evaluated and blocked;
- PWC-specific active integration was removed from stable source paths;
- source viability checklist introduced;
- source viability config introduced;
- source viability validation script introduced;
- candidate sources checked before integration work;
- ACL Anthology validated and promoted as the first major source onboarding case.

Status: done

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

Key lesson:

```text
viability first, candidate integration second, stable integration last
```

---

## 2.7 Artifact Layer v1

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
  - `GET /documents/{canonical_id}/artifacts`;
  - `GET /documents` trusted artifact filters;
- integration tests for artifact API and document artifact filters.

Status: done

Current artifact baseline, approximate:

```text
artifact_entities ≈ 7333–7336
artifact_observations ≈ 38246
paper_artifact_links ≈ 7430
linked canonical docs ≈ 6673
```

Important principle: Artifact Layer v1 is a separate evidence/materialization plane. It does not modify canonical paper truth.

---

## 2.8 GitHub Artifact Enrichment v1

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

Status: done

Current GitHub enrichment baseline, approximate:

```text
github_entities_count ≈ 5953
metadata_rows_count ≈ 5953
found_count ≈ 5339
not_found_count ≈ 614
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

## 2.9 Hugging Face Artifact Enrichment v1

Completed:

- extracted Hugging Face model/dataset/space entities enriched through Hub API;
- provider-specific snapshot metadata written to:

```text
data/enriched/huggingface_artifacts/huggingface_artifact_metadata.<ts>.jsonl
data/enriched/huggingface_artifacts/huggingface_artifact_metadata_latest.jsonl
```

- standalone strict validation report;
- HF metadata merge in `export_artifacts_postgres_v1.py`;
- Postgres materialization into `artifact_entities.metadata.huggingface`;
- selected generic artifact columns materialized where available;
- optional HF checks in refresh DoD;
- optional HF stages in refresh pipeline;
- HF metadata consumed by paper features and paper detail cards.

Status: done

Current Hugging Face enrichment baseline, approximate:

```text
huggingface_entities_count ≈ 100
metadata_rows_count ≈ 100
found_count ≈ 77
forbidden_count ≈ 2
skipped_invalid_external_id_count ≈ 21
rate_limited_count = 0
error_count = 0
ok = true
```

Important principles:

- Hugging Face is an artifact enrichment provider, not a paper source.
- `forbidden` rows are provider/access states and remain diagnostic.
- `skipped_invalid_external_id` rows are recognized extraction/noise states and remain diagnostic.
- Neither state should fail the core strict gate unless policy changes later.
- Provider-specific Hugging Face API filters are postponed.

---

## 2.10 Paper Features v1

Completed:

- file-first feature layer over canonical truth and artifact/enrichment snapshots;
- `data/features/paper_features_latest.jsonl`;
- strict paper features validator;
- feature quality report;
- DoD integration through `--require-paper-features`.

Status: done

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

Important principle: paper features are derived, transparent v1 heuristics. They are not canonical paper truth and not ML-learned quality labels.

---

## 2.11 Ranking / Paper Detail / Similar Papers v1

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
- similar papers optional DoD gate.

Status: done

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

Status note: all-MiniLM-L6-v2 is accepted for functional validation v1. Stronger scientific embeddings are a later retrieval-quality milestone.

---

## 2.12 Discovery API v1

Completed:

- API namespace for product discovery:
  - `GET /discovery/profiles`;
  - `GET /discovery/ranking/{profile_name}`;
  - `GET /discovery/papers/{canonical_id}`;
  - `GET /discovery/papers/{canonical_id}/similar`;
- file-first `DiscoveryService`;
- profile-based ranking endpoint;
- paper detail endpoint;
- semantic/radar-adjusted similar papers endpoint;
- integration tests for Discovery API;
- Discovery API quality validator:

```bat
python -m scripts.validation.check_discovery_api --strict
```

- optional DoD gate:

```text
--require-discovery-api
```

- Discovery API similar runtime cache:
  - dense bundle cache;
  - normalized embeddings cache;
  - dense id index cache;
  - feature lookup cache;
  - canonical lookup cache;
- `test_api_discovery.py` module-scoped client fixture to avoid repeated API startup.

Status: done

---

## 2.13 Discovery API v1.1 — ranking query overrides

Completed:

- extended `GET /discovery/ranking/{profile_name}` with controlled query overrides;
- kept ranking profiles as base presets;
- query parameters now override or add filters without changing core ranking logic;
- response `profile.filters` remains base profile filters;
- response `filters` now represents effective filters after overrides;
- boolean overrides support `true` and `false` explicitly;
- `top_k` is capped by API settings;
- invalid `sort_by` is rejected by API validation;
- invalid `min_year > max_year` is rejected as bad request;
- integration tests cover combined overrides, false boolean override, sort override and invalid params;
- Discovery API quality gate checks an override smoke;
- strict DoD under `--require-discovery-api` requires the new override checks.

Status: done

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

Required checks include:

```text
discovery_api_ranking_overrides_endpoint_ok
discovery_api_ranking_overrides_results_non_empty
discovery_api_ranking_overrides_min_year_filter_echoed
discovery_api_ranking_overrides_has_code_filter_echoed
discovery_api_ranking_overrides_results_match_filters
```

Current strict discovery command:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_discovery.py -q
python -m scripts.validation.check_discovery_api --strict
```

Current full strict DoD command:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api
```

Current result:

```text
dod_passed = true
required_failed_count = 0
```

Impact:

```text
ML Research Radar exposes a usable product/discovery API workflow:
profile ranking + query overrides → paper card → similar papers
```

---

## 2.14 Streamlit Discovery UI v0.2

Completed:

- old search-oriented UI replaced with discovery-oriented UI;
- thin client over FastAPI `/discovery/*`;
- no local JSONL reading in Streamlit;
- no embedding loading in Streamlit;
- no ranking or similar-papers computation in Streamlit;
- profile selector;
- top-k control;
- title query;
- source family filter;
- min/max year filters;
- tri-state boolean filters:
  - profile default;
  - true;
  - false;
- sort selector;
- descending toggle;
- reset filters button;
- ranking cards/table;
- paper detail tabs;
- artifact/source evidence display;
- similar papers tab;
- semantic vs radar-adjusted similar mode selector;
- raw JSON expanders;
- empty-state guidance;
- API base URL input;
- health/info/runtime status display;
- API reload button.

Status: done

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

Streamlit UI smoke validator:

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

## 2.15 Clustering / Topic Clusters v1

Completed:

- file-first topic clustering layer over current retrieval embeddings;
- manifest-based input resolution;
- MiniBatchKMeans clustering over L2-normalized dense embeddings;
- cluster assignments artifact;
- cluster summary artifact;
- heuristic label candidates artifact;
- latest pointer;
- build report;
- quality validator;
- cluster inspect utility;
- generated reports under `artifacts/reports/clusters/`.

Status: done / green as derived layer

Inputs:

```text
artifacts/retrieval/manifests/latest.json
dense_embeddings_path from retrieval manifest
dense_ids_path from retrieval manifest
data/analytics/reconciled/canonical_documents.jsonl
data/features/paper_features_latest.jsonl
configs/topic_clusters_v1.yaml
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
artifacts/reports/clusters/topic_cluster_<cluster_id>_inspect_latest.json
artifacts/reports/clusters/topic_cluster_<cluster_id>_inspect_latest.md
```

Current topic cluster build:

```text
cluster_build_id = 20260511T151842Z
retrieval_build_id = 20260504T164021Z
cluster_config_hash = 34bfa8908a6536cf
algorithm = minibatch_kmeans
n_clusters = 80
random_state = 42
batch_size = 4096
max_iter = 100
n_init = 3
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]
assigned_rows_count = 60954
cluster_count = 80
empty_cluster_count = 0
largest_cluster_size = 1493
largest_cluster_ratio = 0.024494
```

Build command:

```bat
python -m scripts.analytics.build_topic_clusters
```

Quality command:

```bat
python -m scripts.validation.check_topic_clusters --strict
```

Current quality result:

```text
ok = true
required_failed_count = 0
assignment_count = 60954
actual_cluster_count = 80
empty_cluster_count = 0
```

Inspect examples:

```bat
python -m scripts.analytics.inspect_topic_cluster --cluster-id 41
python -m scripts.analytics.inspect_topic_cluster --cluster-id 0
python -m scripts.analytics.inspect_topic_cluster --cluster-id 57
python -m scripts.analytics.inspect_topic_cluster --cluster-id 46
python -m scripts.analytics.inspect_topic_cluster --cluster-id 32
python -m scripts.analytics.inspect_topic_cluster --cluster-id 71
python -m scripts.analytics.inspect_topic_cluster --cluster-id 79
python -m scripts.analytics.inspect_topic_cluster --cluster-id 3
```

Observed topic examples from v1:

```text
cluster 41: computer vision / object detection / convolutional networks
cluster 0: classical ML / anomaly detection / random forest / time series
cluster 57: machine translation / multilingual NLP / low-resource languages / LLMs
cluster 46: LLM reasoning / mathematical reasoning / question answering
cluster 32: graph neural networks / graph convolutional networks / graph learning
cluster 71: reinforcement learning / deep RL / imitation learning / control
cluster 79: evolutionary / swarm / genetic optimization
cluster 3: LLMs / transformers / language models / NLP
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

Current limitation:

```text
No projection/UMAP artifact in v1.
No cluster API endpoints yet.
No Streamlit topic-map tab yet.
No LLM-generated labels in v1.
```

---

## 3. Current System State

The project is currently at this point:

- canonical 60,954-paper corpus is green;
- arXiv 60k backbone is preserved;
- ACL Anthology is integrated and sanitized;
- OpenAlex, Semantic Scholar and Crossref enrich the arXiv backbone;
- retrieval artifacts are built and validated on 60,954 docs;
- Postgres paper serving layer is green;
- artifact extraction is green;
- artifact DB materialization is green;
- GitHub artifact enrichment is green and optional in DoD/pipeline;
- Hugging Face artifact enrichment is green and optional in DoD/pipeline;
- paper features layer is green;
- ranking profiles are green;
- paper detail/card is green;
- similar papers are green;
- Discovery API v1 is green and DoD-gated;
- Discovery API v1.1 ranking query overrides are green and DoD-gated;
- Streamlit Discovery UI v0.2 is green;
- Streamlit UI smoke check is green;
- topic clusters v1 are green as file-first derived analytics artifacts;
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
→ Discovery API
→ Streamlit Discovery UI
→ topic clusters v1
→ strict validation reports
→ optional DoD gates
```

---

## 4. Near-Term Roadmap

Recommended next order:

```text
1. Expose topic clusters through Discovery API.
2. Add a Streamlit topic/cluster tab over the new cluster API endpoints.
3. Add optional topic-clusters gate to refresh DoD.
4. Consider UMAP/PCA projection artifact for UI after cluster API is stable.
5. Consider stronger scientific embeddings / retrieval profiles.
6. Consider vector serving / Qdrant for serving-time dense retrieval.
7. Consider the next paper-source candidate, likely OpenReview.
```

Rationale:

The project has already closed the ingestion/reconcile/artifact/features/ranking/detail/similar/API/UI/topic-cluster vertical slices. The next value comes from making the topic landscape usable through existing product surfaces rather than continuing offline label tuning.

---

## 4.1 Discovery API cluster endpoints v1

Planned:

- expose topic cluster artifacts through `/discovery/*`;
- keep API file-first for cluster v1;
- do not read clusters from Postgres in v1;
- do not compute clustering at request time;
- use `artifacts/clusters/topic/latest.json` as cluster latest pointer.

Candidate endpoints:

```text
GET /discovery/clusters
GET /discovery/clusters/{cluster_id}
GET /discovery/papers/{canonical_id}/cluster
```

Possible `GET /discovery/clusters` response content:

```text
cluster_id
size
label_candidates
artifact_ready_count
mean_radar_score
top_years
top_source_families
representative_papers
```

Possible `GET /discovery/clusters/{cluster_id}` response content:

```text
cluster summary
label candidates
representative papers
top papers by radar_score
top papers by implementation_readiness_score
optional sample papers
```

Possible `GET /discovery/papers/{canonical_id}/cluster` response content:

```text
canonical_id
cluster_id
cluster_build_id
retrieval_build_id
rank_within_cluster
distance_to_centroid
similarity_to_centroid
cluster label candidates
cluster summary link/payload
```

Status: next

Important principle:

```text
API serves existing cluster artifacts.
API does not trigger clustering.
```

---

## 4.2 Streamlit Topic/Cluster Tab v0.1

Planned after cluster API endpoints:

- add topic/cluster tab to existing Streamlit Discovery UI;
- cluster list/table;
- label candidates display;
- cluster size;
- artifact-ready count;
- mean radar score;
- representative papers;
- selected cluster detail;
- top papers in cluster;
- link from paper detail to its cluster;
- no local JSONL/artifact loading in Streamlit;
- no clustering computation in Streamlit.

Status: planned after API cluster endpoints

Important principle:

```text
Streamlit remains a thin API client.
```

---

## 4.3 Topic clusters DoD hardening

Planned:

- add optional `--require-topic-clusters` flag to `scripts/update/check_refresh_definition_of_done.py`;
- require latest topic cluster quality report when the flag is passed;
- verify cluster build is aligned with latest retrieval manifest/corpus count;
- keep flag optional at first.

Candidate command after integration:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api --require-topic-clusters
```

Status: planned hardening

---

## 4.4 Projection / Topic Map Visualization Artifact

Planned after cluster API/UI v0.1:

- add 2D projection artifact for visualization;
- prefer scalable approach first:
  - PCA for full corpus smoke;
  - UMAP for sampled or filtered subsets;
- avoid t-SNE for full corpus;
- do not compute projections on every API/UI request;
- build projection offline as derived artifact;
- keep projection optional and rebuildable.

Possible outputs:

```text
artifacts/clusters/topic/runs/<cluster_build_id>/projection_pca.jsonl
artifacts/clusters/topic/runs/<cluster_build_id>/projection_sample_umap.jsonl
artifacts/reports/clusters/topic_projection_quality_latest.json
```

Status: later, after API/UI cluster surfaces

Scalability principle:

```text
Full-corpus clustering/projection is an offline build step.
Interactive user-subset clustering/projection is a separate future feature with strict size limits.
```

---

## 4.5 Stronger embeddings / retrieval quality milestone

Planned:

- research stronger scientific paper embedding models;
- add retrieval profile config;
- build alternate dense embedding index;
- compare similar-papers and topic-cluster quality;
- keep fast default profile with all-MiniLM-L6-v2;
- add scientific semantic profile if quality justifies it.

Possible future profiles:

```text
fast_default = sentence-transformers/all-MiniLM-L6-v2
scientific_semantic = stronger scientific paper embedding model
citation_aware = dense similarity + citation graph signals
hybrid = dense semantic + lexical BM25 + artifact/radar re-ranking
```

Status: later; not a blocker for cluster API/UI v0.1

---

## 4.6 Vector Serving Integration

Planned:

- integrate vector-serving path;
- move toward serving-time dense retrieval;
- prepare for future hybrid serving.

Possible directions:

- Qdrant-backed serving;
- hybrid SQL + vector candidate generation;
- serving-time dense search;
- DB metadata filters + vector candidates + ranker;
- Qdrant-backed similar papers endpoint after API contract stabilizes.

Status: planned

Important principle: dense/hybrid serving should likely be implemented through a vector-serving layer, not by forcing dense retrieval into the current Postgres DB backend.

---

## 4.7 OpenReview candidate source

Planned:

- ingest OpenReview papers by explicit venue/year scope;
- start with selected ML venues;
- use API v2 / Python client where appropriate;
- preserve OpenReview identifiers;
- keep reviews/ratings/decisions as separate review/signal layer, not canonical paper truth v1;
- candidate-only until source audit and candidate reconcile impact checks are green.

Status: planned after current product/discovery/topic-map slice

---

## 4.8 Biomedical/domain sources

Planned later:

- PubMed;
- bioRxiv;
- medRxiv.

Purpose:

- biomedical/domain expansion;
- possible ML-for-biology / ML-for-medicine coverage;
- separate domain-specific corpus slices.

Status: later

---

## 5. Search / API / Product hardening

Planned:

- expose topic clusters through Discovery API;
- add Streamlit topic/cluster tab;
- add optional topic-clusters DoD gate;
- improve SQL search quality;
- improve retrieval validation queries;
- reduce gap between DB lexical search and file retrieval ergonomics;
- handle modern ML query failures;
- add richer artifact provider filters when provider metadata stabilizes;
- add document/source/reference drilldown endpoints;
- add Discovery API compact/detail response modes;
- add Discovery API latency diagnostics / cache stats;
- add cluster API latency diagnostics / cache stats.

Hugging Face-specific API filters remain postponed until there is a clear product need.

---

## 6. Later Product Layers

These are intentionally postponed until corpus, artifact, discovery, topic-map and serving foundations are stronger.

### 6.1 Full-text and chunking

Planned:

- full-text extraction;
- chunk storage;
- chunk-level retrieval.

### 6.2 Structured extraction

Planned:

- NER / entity extraction;
- richer paper metadata derivation;
- structured research signals.

### 6.3 LLM / RAG layer

Planned:

- summaries;
- retrieval-augmented question answering;
- citation-aware generation.

### 6.4 Graph / analytics layer

Planned:

- reference graph;
- artifact graph;
- topic graph;
- trend analytics;
- related-paper surfaces.

### 6.5 Dataset release track

Planned:

- clean metadata dataset;
- paper-artifact graph exports;
- topic/cluster exports;
- dataset cards;
- Kaggle / Hugging Face dataset release track if useful.

### 6.6 Full frontend / public product packaging

Planned later, after backend/product layers are mature:

- full web frontend, likely React/Next.js;
- proper landing page;
- hosted FastAPI backend;
- deployed Postgres;
- vector serving if needed;
- domain name;
- public demo packaging;
- monitoring and observability.

Status: later

Important principle:

```text
First Streamlit as a thin API demo.
Full frontend/site only after product workflow and backend contracts stabilize.
```

---

## 7. Explicit Non-Goals for the Current Stage

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
- full frontend before the Streamlit/API workflow is proven.

---

## 8. Guiding principle

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
11. expose topic clusters through Discovery API and Streamlit;
12. add stronger embeddings / projection / vector serving carefully;
13. add new paper/domain sources carefully;
14. add richer product/RAG layers;
15. package the project as a full web product only after the core is mature.

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
