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
→ vector serving / topic maps / future RAG
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
→ UI / future RAG / analytics / dataset releases
```

Main invariants:

```text
canonical_documents.jsonl = paper-level truth
Postgres = materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization plane
paper_features / ranking / detail / similar = derived discovery layer
Discovery API = product/discovery API over derived layers
```

GitHub and Hugging Face enrich artifacts. They are not paper truth sources.

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

Important principle: canonical JSONL remains the paper-level source of truth. Postgres, retrieval artifacts, artifact tables, paper features and APIs are materializations over that truth.

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
- manifest-based dense artifact resolution for similar papers.

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
- Discovery API quality check.

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
ML Research Radar now exposes a usable product/discovery API workflow:
profile ranking + query overrides → paper card → similar papers
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
- source viability gate exists;
- Papers with Code live source remains blocked/archived;
- canonical paper truth remains isolated from artifact enrichment.

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
→ strict validation reports
→ optional DoD gates
```

---

## 4. Near-Term Roadmap

Recommended next order:

```text
1. Build a small local Streamlit UI over /discovery/*.
2. Harden Discovery API response ergonomics where needed for UI.
3. Consider clustering/topic map v1.
4. Consider stronger scientific embeddings / retrieval profiles.
5. Consider the next paper-source candidate, likely OpenReview.
```

Rationale:

The project has already spent enough time proving ingestion/reconcile/artifact foundations. The next value comes from making the corpus usable as a research radar.

---

## 4.1 Streamlit Discovery UI v0.1

Planned:

- thin Streamlit client over FastAPI `/discovery/*`;
- no local JSONL reading in the UI;
- no ranking/business logic inside Streamlit;
- profile selector;
- top-k control;
- year filters;
- title query;
- artifact readiness checkboxes;
- source/HF/ACL/DOI filters where useful;
- sort selector;
- ranking results table/cards;
- clickable paper detail/card;
- similar papers panel;
- semantic vs radar-adjusted toggle;
- artifact/code/model indicators;
- GitHub/HF badges and links.

Status: next

Purpose:

```text
turn the backend into a portfolio-visible research radar demo
```

Important principle:

```text
Streamlit UI = temporary thin demo layer over API
FastAPI Discovery API = stable backend contract
future full frontend = separate product milestone
```

---

## 4.2 Discovery API ergonomics v1.2

Planned if UI reveals need:

- compact paper detail view;
- smaller artifact metadata view;
- endpoint examples optimized for UI;
- explicit DiscoveryService cache stats;
- latency diagnostics;
- lighter discovery validator startup path if needed.

Status: planned after UI v0.1 feedback

---

## 4.3 Clustering / topic map v1

Planned:

- topic clusters over embeddings;
- UMAP/PCA projection artifacts;
- KMeans/HDBSCAN candidate experiments;
- cluster label candidates from titles/keywords/categories;
- cluster reports;
- topic navigation API later.

Status: planned

Important distinction:

```text
similar papers = local nearest neighbors around one paper
clustering = global topic landscape / map
ranking = promising/useful/artifact-ready papers
```

Clustering must not replace similar papers.

---

## 4.4 Stronger embeddings / retrieval quality milestone

Planned:

- research stronger scientific paper embedding models;
- add retrieval profile config;
- build alternate dense embedding index;
- compare similar-papers quality;
- keep fast default profile with all-MiniLM-L6-v2;
- add scientific semantic profile if quality justifies it.

Possible future profiles:

```text
fast_default = sentence-transformers/all-MiniLM-L6-v2
scientific_semantic = stronger scientific paper embedding model
citation_aware = dense similarity + citation graph signals
hybrid = dense semantic + lexical BM25 + artifact/radar re-ranking
```

Status: later; not a blocker for Discovery API/UI v0.1

---

## 4.5 OpenReview candidate source

Planned:

- ingest OpenReview papers by explicit venue/year scope;
- start with selected ML venues;
- use API v2 / Python client where appropriate;
- preserve OpenReview identifiers;
- keep reviews/ratings/decisions as separate review/signal layer, not canonical paper truth v1;
- candidate-only until source audit and candidate reconcile impact checks are green.

Status: planned after current product/discovery slice

---

## 4.6 Biomedical/domain sources

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

- improve SQL search quality;
- improve retrieval validation queries;
- reduce gap between DB lexical search and file retrieval ergonomics;
- handle modern ML query failures;
- add richer artifact provider filters when provider metadata stabilizes;
- add document/source/reference drilldown endpoints;
- add Discovery API compact/detail response modes;
- add Discovery API latency diagnostics / cache stats.

Hugging Face-specific API filters remain postponed until there is a clear product need.

---

## 6. Vector Serving Integration

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

## 7. Later Product Layers

These are intentionally postponed until corpus, artifact, discovery, and serving foundations are stronger.

### 7.1 Full-text and chunking

Planned:

- full-text extraction;
- chunk storage;
- chunk-level retrieval.

### 7.2 Structured extraction

Planned:

- NER / entity extraction;
- richer paper metadata derivation;
- structured research signals.

### 7.3 LLM / RAG layer

Planned:

- summaries;
- retrieval-augmented question answering;
- citation-aware generation.

### 7.4 Graph / analytics layer

Planned:

- reference graph;
- artifact graph;
- topic graph;
- trend analytics;
- related-paper surfaces.

### 7.5 Dataset release track

Planned:

- clean metadata dataset;
- paper-artifact graph exports;
- topic/cluster exports;
- dataset cards;
- Kaggle / Hugging Face dataset release track if useful.

### 7.6 Full frontend / public product packaging

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

## 8. Explicit Non-Goals for the Current Stage

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
- replacing canonical truth with Postgres/materialized views;
- full frontend before the Streamlit/API workflow is proven.

---

## 9. Guiding principle

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
10. add topic map / stronger embeddings / vector serving;
11. add new paper/domain sources carefully;
12. add richer product/RAG layers;
13. package the project as a full web product only after the core is mature.

The key engineering rule is:

```text
Viability first, candidate integration second, stable integration last.
```

The key product rule is:

```text
Do not collect sources forever without adding usable discovery workflows.
```
