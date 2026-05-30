# Refresh Runbook v1

## Purpose

This runbook describes the current **manual safe refresh / validation loop v1** for **ML Research Radar**.

It is the operational companion to:

- `docs/roadmap.md`
- `docs/experiment_safety_rules.md`
- `docs/provenance_semantics.md`
- `docs/data_contracts.md`
- `docs/api_reference.md`

This document is intentionally practical: it explains what to rebuild, what to validate, what is considered source of truth, and which checks define a green checkpoint.

---

## Current checkpoint

Current working checkpoint:

```text
Discovery Green Checkpoint — 2026-05
```

Current system status:

```text
canonical_doc_count = 60954
canonical_multisource_docs = 9192
doi_count = 10183
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
topic_projection_rows_count = 2080

golden_queries_enabled_count = 22
golden_queries_explicit_count = 15
golden_queries_weak_pattern_count = 7
qdrant_benchmark_collection = ml_radar_dense_benchmark_v1
qdrant_benchmark_uploaded_count = 60954

strict_dod_required_checks = 132
strict_dod_required_failed_count = 0
strict_dod_passed = true
```

Current retrieval manifest:

```text
artifacts/retrieval/manifests/latest.json
```

Current known issues snapshot path:

```text
artifacts/reports/validation/known_issues_snapshot_latest.json
```

Important naming note: the current file is `known_issues_snapshot_latest.json`, not `known_issues_latest.json`.

---

## Core architecture

ML Research Radar is a paper-centric canonical corpus and discovery platform.

Current operational chain:

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
→ GitHub / Hugging Face enrichment
→ paper features
→ ranking / paper detail / similar papers
→ Discovery API
→ Streamlit Discovery UI
→ topic clusters / topic projection
→ evaluation / regression / strict DoD
```

Main invariants:

```text
canonical_documents.jsonl = paper-level truth
Postgres = rebuildable materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization plane
paper_features = derived discovery feature layer
ranking / detail / similar = derived discovery layer
topic clusters / projection = derived analytics/discovery layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin API client
```

GitHub and Hugging Face enrich artifacts. They are not paper-truth sources.

Topic clusters and topic projections are derived from current retrieval/canonical/features artifacts. They do not modify canonical identity.

---

## Current active source set

Current stable paper sources:

```text
arxiv
openalex_alignment
semantic_scholar_alignment
crossref_alignment
acl_anthology
```

Current roles:

- `arxiv` is the 60k backbone.
- `openalex_alignment`, `semantic_scholar_alignment`, and `crossref_alignment` enrich the backbone.
- `acl_anthology` is integrated as the first major source-expansion case.
- GitHub and Hugging Face are artifact enrichment providers, not paper sources.
- Papers with Code live/source integration remains blocked/archived; PWC-like signals should be treated as artifact candidates only unless policy changes later.

Current operational paper source of truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

---

## What this runbook covers

Use this runbook when you need to safely refresh or revalidate one or more of these layers:

- canonical corpus;
- Postgres serving layer;
- retrieval artifacts;
- artifact extraction / artifact DB;
- GitHub artifact enrichment;
- Hugging Face artifact enrichment;
- paper features;
- ranking / paper detail / similar papers;
- Discovery API;
- topic clusters;
- topic projection;
- Streamlit Discovery UI validation;
- retrieval evaluation and search-quality experiments;
- strict Definition of Done.

---

## What this runbook does not cover yet

Not part of the current refresh v1 loop:

- full-text ingestion;
- chunk-level retrieval;
- RAG serving;
- automatic Airflow orchestration;
- Kubernetes deployment;
- Kafka/event streaming;
- public production frontend;
- automatic integration of all viable sources;
- DB-native dense/hybrid parity;
- Qdrant production serving path (the current Qdrant benchmark is evaluation-only).

These are future staged layers and must not be mixed into the core refresh loop until each has its own validator and DoD gate.

---

## Core safety principle

Never treat a selective/latest enrichment batch as a complete source snapshot.

Correct pattern:

```text
selective enrichment
→ merge selective batch into full alignment snapshot
→ reconcile using explicit full merged inputs
→ validate candidate
→ promote candidate
→ export/rebuild derived layers
→ validate reports
→ strict DoD
```

The key safety rule:

```text
reconcile must run from full intended inputs, not accidental mini-batches
```

This prevents accidental corpus collapse, source loss, and misleading multisource counts.

---

## Preconditions

Before running any refresh or rebuild, confirm:

- project environment is active;
- working tree status is understood;
- current canonical exists;
- current retrieval manifest exists;
- latest validation reports exist;
- latest known issues snapshot exists;
- Docker/Postgres is running if DB export or DB smoke is included;
- large generated artifacts are not accidentally staged for Git;
- backups are allowed before canonical promotion or retrieval replacement.

Recommended environment:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

Recommended Docker startup when DB checks are needed:

```bat
cd /d D:\ML\ML_Research_Radar\infra\docker
docker compose up -d
docker ps
cd /d D:\ML\ML_Research_Radar
```

---

## Quick status checks

Use these when you only need to check whether the current system is still coherent.

```bat
python -m scripts.export.test_db_read
python -m scripts.validation.run_retrieval_checks
python -m scripts.validation.run_postpass_audit
python -m scripts.validation.build_known_issues_snapshot
```

Discovery/API/UI lightweight checks:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_discovery.py -q
python -m scripts.validation.check_discovery_api --strict
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Topic checks:

```bat
python -m scripts.validation.check_topic_clusters --strict
python -m scripts.validation.check_topic_projection --strict
```

Similar-papers check:

```bat
python -m scripts.validation.check_similar_papers_report --strict
```

---

## Manual refresh flow

There are two valid styles:

1. use the thin orchestration wrapper;
2. run individual steps manually while debugging.

The wrapper is preferred when the intended input set and run conditions are clear.

---

## Option A — thin orchestration wrapper

Example:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --arxiv-input data\normalized\arxiv\documents.20260404T161108Z.jsonl --execute
```

The exact wrapper behavior may evolve, but the intended high-level sequence is:

```text
reconcile candidate
→ candidate provenance audit
→ promote candidate
→ export canonical to Postgres
→ rebuild retrieval artifacts
→ run retrieval checks
→ run postpass audit
→ build known issues snapshot
→ DoD check
```

After wrapper completion, run the extended downstream/product checks if the wrapper does not already cover them.

---

## Option B — step-by-step execution

Use this if debugging or isolating a specific stage.

### 1. Build canonical candidate

```bat
python -m scripts.update.run_incremental_reconcile_stage --arxiv-input data\normalized\arxiv\documents.20260404T161108Z.jsonl --output-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl --execute
```

Expected:

```text
candidate file created
input mode is safe/full
candidate doc count remains sane
multisource count remains sane
```

### 2. Audit candidate provenance

```bat
python -m scripts.validation.check_canonical_provenance_consistency --canonical-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl
```

Expected:

```text
docs_with_error = 0
```

Warnings can exist and must be interpreted through `docs/provenance_semantics.md`.

### 3. Promote candidate

```bat
python -m scripts.update.promote_canonical_candidate --candidate-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl --execute
```

Expected:

```text
backup created
promotion completed
postcheck match = true
```

### 4. Export canonical to Postgres

Recommended clean reload:

```bat
python -m scripts.export.export_postgres_v1 --replace
```

Expected:

```text
Postgres canonical serving tables match canonical latest
test DB read returns total_docs = canonical_doc_count
```

Check:

```bat
python -m scripts.export.test_db_read
```

### 5. Rebuild retrieval artifacts

```bat
python -m scripts.retrieval.build_indexes
```

Safe test build pattern when needed:

```bat
python -m scripts.retrieval.build_indexes --no-write-latest
```

Expected:

```text
new or validated retrieval build id
manifest corpus_doc_count matches canonical rows
dense ids count matches corpus rows
embedding rows match corpus rows
```

### 6. Run retrieval checks

```bat
python -m scripts.validation.run_retrieval_checks
```

Expected:

```text
latest retrieval checks updated
build_id matches latest retrieval manifest
corpus_doc_count matches canonical
```

### 7. Run postpass audit

```bat
python -m scripts.validation.run_postpass_audit
```

Expected:

```text
total docs match canonical
multisource docs match canonical summary
```

### 8. Refresh known issues snapshot

```bat
python -m scripts.validation.build_known_issues_snapshot
```

Expected:

```text
known_issues_snapshot_latest.json exists
known issues doc_count matches canonical
known issues retrieval build_id matches manifest
```

### 9. Rebuild / validate artifact layer

If canonical or source content changed enough to affect URLs/artifacts, run:

```bat
python -m scripts.enrich.extract_artifact_links
python -m scripts.validation.check_artifact_links_quality --strict
python -m scripts.export.export_artifacts_postgres_v1 --replace
python -m scripts.export.test_artifact_db_read
```

Expected current-green style counts:

```text
artifact_entities ≈ 7333–7336
artifact_observations ≈ 38246
paper_artifact_links ≈ 7430
```

### 10. Validate GitHub enrichment

If artifact layer changed or GitHub metadata was refreshed:

```bat
python -m scripts.validation.check_github_artifact_enrichment --strict
```

Expected current-green style state:

```text
github_entities_count ≈ 5953
found_count ≈ 5339
rate_limited_count = 0
error_count = 0
```

### 11. Validate Hugging Face enrichment

If artifact layer changed or HF metadata was refreshed:

```bat
python -m scripts.validation.check_huggingface_artifact_enrichment --strict
```

Expected current-green style state:

```text
huggingface_entities_count ≈ 100
found_count ≈ 77
forbidden_count ≈ 2
skipped_invalid_external_id_count ≈ 21
rate_limited_count = 0
error_count = 0
```

Important:

```text
forbidden and skipped_invalid_external_id are currently diagnostic provider/extraction states.
They are not core blockers unless policy changes.
```

### 12. Build / validate paper features

```bat
python -m scripts.features.build_paper_features
python -m scripts.validation.check_paper_features --strict
```

Expected:

```text
paper_features_rows_count = canonical_doc_count
scores_in_range = true
required_fields_present = true
canonical_ids_unique = true
```

Current feature coverage:

```text
has_arxiv_count = 60000
has_acl_count = 957
has_doi_count = 10183
has_code_artifact_count = 6218
has_dataset_artifact_count = 192
has_model_artifact_count = 48
has_demo_artifact_count = 319
github_found_repo_paper_count = 5354
hf_found_paper_count = 68
```

### 13. Validate ranking profiles

```bat
python -m scripts.validation.check_ranking_profiles --strict
```

Required profiles:

```text
recent_artifact_ready
huggingface_ready
acl_radar
```

### 14. Build / validate paper detail and similar papers

Recommended seed flow:

```bat
python -m scripts.ranking.demo_radar_ranking --profile huggingface_ready --top-k 5
python -m scripts.details.build_paper_detail --from-latest-ranking-rank 1
python -m scripts.retrieval.find_similar_papers --from-latest-detail --top-k 20
python -m scripts.validation.check_similar_papers_report --strict
```

Expected:

```text
target_found = true
results_non_empty = true
self_not_in_results = true
canonical_ids_unique = true
scores_in_range = true
sorted_correctly = true
ids_count_matches_input_rows = true
```

### 15. Build / validate topic clusters

If retrieval embeddings, canonical corpus, or paper features changed:

```bat
python -m scripts.analytics.build_topic_clusters
python -m scripts.validation.check_topic_clusters --strict
```

Expected current-green style state:

```text
assignment_count = canonical_doc_count
actual_cluster_count = 80
empty_cluster_count = 0
retrieval_build_id matches manifest
```

### 16. Build / validate topic projection

If topic clusters changed or projection needs refresh:

```bat
python -m scripts.analytics.build_topic_projection
python -m scripts.validation.check_topic_projection --strict
```

Expected current-green style state:

```text
projection_algorithm = umap
rows_count = 2080
centroid_count = 80
representative_count = 800
sampled_count = 1200
cluster_build_id matches latest topic cluster build
retrieval_build_id matches manifest
```

### 17. Validate Discovery API

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_discovery.py -q
python -m scripts.validation.check_discovery_api --strict
```

Discovery API quality currently checks:

```text
profiles
ranking
ranking overrides
paper detail
similar semantic
similar radar-adjusted
topic clusters
topic cluster detail
topic cluster map
paper topic cluster
selected sort/filter cases
```

### 18. Validate Streamlit Discovery UI

Static UI validation:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Optional live API validation:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict --check-api
```

Expected:

```text
py_compile_ok = true
Discovery snippets present
Search tab snippets present
Topic cluster snippets present
Topic map snippets present
Artifact explorer snippets present
Paper workspace snippets present
legacy search endpoint absent
deprecated use_container_width absent
```

---

## Evaluation / search-quality flow

Use this when tuning retrieval or validating search quality.

### Retrieval evaluation

```bat
python -m scripts.evaluation.run_retrieval_eval
python -m scripts.validation.check_retrieval_eval --strict
```

Current-green style metrics:

```text
enabled_cases_count = 22
runtime_errors = 0
hybrid_hit_at_10 = 1.0
hybrid_mrr_at_10 = 1.0
hybrid_recall_at_10 ≈ 0.804
hybrid_ndcg_at_10 ≈ 0.852
```

### Search quality experiments

```bat
python -m scripts.evaluation.run_search_quality_experiments
python -m scripts.validation.check_search_quality_experiments --strict
```

### Controlled search quality experiments

```bat
python -m scripts.evaluation.run_search_quality_controlled_experiments
python -m scripts.validation.check_search_quality_controlled_experiments --strict
```

Controlled experiments are evaluation-only. They must not silently change API defaults.

### Qdrant / vector-serving benchmark

Use this when validating Qdrant as a future derived vector-serving layer.

```bat
python -m scripts.evaluation.run_qdrant_retrieval_benchmark
python -m scripts.validation.check_qdrant_retrieval_benchmark --strict
```

Current-green state:

```text
collection_name = ml_radar_dense_benchmark_v1
uploaded_count = 60954
collection_points_count = 60954
enabled_queries_count = 22
query_count = 22
error_count = 0
required_failed_count = 0
```

This benchmark:

- reads dense artifacts from `artifacts/retrieval/manifests/latest.json`;
- creates or recreates a benchmark Qdrant collection;
- uploads current dense paper vectors;
- runs enabled golden queries;
- compares Qdrant dense retrieval against current file-dense retrieval;
- writes evaluation and validation reports.

It is evaluation-only. It does not change `canonical_documents.jsonl`, retrieval manifests, `/search` defaults, `SearchRuntime`, or the Discovery API.

### Qdrant serving POC checks

Use this after a Qdrant benchmark has already created the benchmark collection.

```bat
python -m scripts.validation.check_qdrant_collection --strict
python -m scripts.evaluation.compare_qdrant_file_dense
python -m scripts.validation.check_qdrant_file_dense_comparison --strict
```

Current-green state:

```text
collection_name = ml_radar_dense_benchmark_v1
collection_exists = true
points_count = 60954
corpus_doc_count = 60954
enabled_queries_count = 22
query_count = 22
error_count = 0
mean_overlap_ratio_at_k = 1.0
min_overlap_ratio_at_k = 1.0
required_failed_count = 0
```

These checks are lightweight compared with the full Qdrant benchmark. They do not recreate the collection and do not upload vectors. They validate the existing Qdrant collection and compare Qdrant dense retrieval against the current file-dense retrieval artifacts.

### Experimental Qdrant API endpoint

Use this after the Qdrant benchmark collection exists and the lightweight Qdrant serving POC checks are green.

```bash
python -m scripts.validation.check_qdrant_api_experimental --strict
```

This validates:

- FastAPI endpoint `GET /experimental/search/qdrant`;
- file backend runtime availability;
- Qdrant collection availability;
- query embedding through the current runtime embedding model;
- Qdrant dense search response shape;
- `mode=dense_qdrant`;
- non-empty results with `canonical_id`, `title`, `rank`, and dense score;
- strict `required_failed_count=0`.

This endpoint is experimental and must not be treated as the default production `/search` path. It does not change canonical truth, retrieval manifests, `/search` modes, or `ML_RADAR_SEARCH_BACKEND`.

This is still a POC / evaluation layer. It does not change `/search`, `SearchRuntime`, retrieval manifests, canonical truth, or Discovery API defaults.

### Golden queries quality gate

```bat
python -m scripts.validation.check_golden_queries --strict
```

Current-green state:

```text
enabled_cases_count = 22
explicit_canonical_labeled_enabled_count = 15
weak_pattern_enabled_count = 7
required_failed_count = 0
```

Golden queries are a small regression/evaluation set, not a final global optimization target. They are used to detect retrieval regressions when the corpus, embeddings, serving layer, reranker, or vector backend changes.

### Golden labeling candidates

```bat
python -m scripts.evaluation.export_golden_labeling_candidates
python -m scripts.validation.check_golden_labeling_candidates --strict
```

Use this to expand the human-reviewed golden set before making retrieval default changes.

---

## Discovery API regression runner

Quick discovery regression:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.run_discovery_api_regression
```

Skip rebuilding latest similar report when appropriate:

```bat
python -m scripts.validation.run_discovery_api_regression --skip-similar-rebuild
```

Include retrieval evaluation:

```bat
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval
```

Include search-quality analysis:

```bat
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments
```

Include controlled search-quality experiments:

```bat
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments --include-controlled-search-quality-experiments
```

Include Qdrant benchmark:

```bat
python -m scripts.validation.run_discovery_api_regression --include-qdrant-benchmark --skip-similar-rebuild
```

Include Qdrant benchmark together with retrieval/search-quality checks:

```bat
python -m scripts.validation.run_discovery_api_regression --include-qdrant-benchmark --include-retrieval-eval --include-search-quality-experiments --skip-similar-rebuild
```

Include lightweight Qdrant serving POC checks over an existing collection:

```bat
python -m scripts.validation.run_discovery_api_regression --include-qdrant-serving-poc --skip-similar-rebuild

Include experimental Qdrant API endpoint check:

```bash
python -m scripts.validation.run_discovery_api_regression --include-qdrant-api --include-qdrant-serving-poc --skip-similar-rebuild
```
```

Include both full Qdrant benchmark and lightweight Qdrant serving POC checks:

```bat
python -m scripts.validation.run_discovery_api_regression --include-qdrant-benchmark --include-qdrant-serving-poc --include-qdrant-api --skip-similar-rebuild
```

Include DB smoke and DoD:

```bat
python -m scripts.validation.run_discovery_api_regression --include-db-smoke --include-dod
```

Live UI check requires running FastAPI / API base URL:

```bat
python -m scripts.validation.run_discovery_api_regression --include-live-ui-check
```

Supported runner flags:

```text
--skip-similar-rebuild
--similar-top-k
--include-retrieval-eval
--include-search-quality-experiments
--include-controlled-search-quality-experiments
--include-qdrant-benchmark
--include-qdrant-serving-poc
--include-qdrant-api
--include-db-smoke
--include-dod
--include-live-ui-check
```

---

## Strict Definition of Done

Current checkpoint DoD report includes these required layers:

```text
known issues
artifacts
GitHub enrichment
Hugging Face enrichment
paper features
similar papers
Discovery API
topic clusters
topic projection
Streamlit Discovery UI
```

Current-green checkpoint result:

```text
required_check_count = 132
required_failed_count = 0
dod_passed = true
```

Current full strict DoD command should include the active required gates supported by the current project codebase:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api --require-topic-clusters --require-topic-projection --require-streamlit-discovery-ui
```

If your local `--help` output does not show all flags, the local script is stale relative to the latest checkpoint reports. In that case, sync `scripts/update/check_refresh_definition_of_done.py` before updating docs or treating DoD as complete.

Minimum legacy DoD for old refresh-only loops:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues
```

This legacy check is no longer sufficient for the full Discovery Green Checkpoint.

---

## Expected success criteria

A full green refresh/checkpoint is successful when:

- canonical candidate is built safely from full intended inputs;
- candidate provenance is valid;
- canonical promotion succeeds;
- canonical contract passes;
- Postgres export/read smoke passes;
- retrieval manifest and retrieval checks match canonical;
- postpass audit matches canonical;
- known issues snapshot matches canonical/retrieval build;
- artifact layer quality/export/DB read pass;
- GitHub enrichment check passes;
- Hugging Face enrichment check passes under current provider-state policy;
- paper features pass;
- ranking profiles pass;
- paper detail and similar papers pass;
- Discovery API passes;
- topic clusters pass;
- topic projection passes;
- Streamlit Discovery UI passes;
- strict DoD passes with `required_failed_count = 0`.

---

## Current healthy values

At the current Discovery Green Checkpoint, healthy values are:

```text
canonical docs = 60954
multisource docs = 9192
doi_count = 10183
retrieval build_id = 20260504T164021Z
embedding shape = [60954, 384]

artifact DB entities = 7333
artifact observations = 38246
paper-artifact links = 7430

GitHub found repos = 5339
Hugging Face found artifacts = 77

paper features rows = 60954
topic clusters = 80
topic assignments = 60954
topic projection rows = 2080
strict DoD required checks = 132
strict DoD failed checks = 0
```

During future refreshes, exact values may change, but they must remain internally consistent across:

```text
canonical
retrieval manifest
retrieval checks
postpass audit
Postgres
known issues snapshot
artifact reports
paper features
similar papers
Discovery API
topic clusters
topic projection
Streamlit UI quality
DoD
```

---

## Blockers

Stop and investigate if any of these occur:

- reconcile uses unsafe/incomplete inputs;
- canonical doc count collapses unexpectedly;
- arXiv backbone is unexpectedly reduced;
- multisource docs collapse unexpectedly;
- canonical contract fails;
- duplicate canonical IDs appear;
- required canonical fields disappear;
- promotion fails;
- Postgres export/read smoke fails;
- retrieval build fails;
- retrieval manifest doc count mismatches canonical;
- retrieval checks fail;
- artifact quality/export/DB read fails;
- GitHub/HF enrichment strict checks fail outside known provider-state caveats;
- paper features rows do not match canonical;
- similar papers target/result checks fail;
- Discovery API quality fails;
- topic clusters/projection quality fails;
- Streamlit UI quality fails;
- strict DoD fails.

---

## Non-blocker diagnostics under current semantics

These are not automatic blockers unless policy changes:

- `doc_ids_shorter_than_sources`;
- repeated source families in provenance lists;
- `arxiv_id` present without a direct arXiv provenance row when provenance semantics explain it;
- `source_ids` containing more families than `sources`;
- Hugging Face `forbidden` provider states;
- Hugging Face `skipped_invalid_external_id` extraction/noise states;
- GitHub `not_found` repositories preserved as historical artifact evidence;
- heuristic topic `label_candidates` being imperfect.

Interpret provenance through:

```text
docs/provenance_semantics.md
```

Interpret artifact/provider states through the artifact/enrichment validation reports.

---

## Key supporting files

### Docs

```text
docs/roadmap.md
docs/api_reference.md
docs/experiment_safety_rules.md
docs/provenance_semantics.md
docs/data_contracts.md
docs/source_matrix.md
docs/merge_policy.md
```

### Configs

```text
configs/artifact_extraction.yaml
configs/paper_features_v1.yaml
configs/ranking_profiles_v1.yaml
configs/retrieval_eval_v1.yaml
configs/search_quality_experiments_v1.yaml
configs/search_quality_controlled_experiments_v1.yaml
configs/golden_labeling_v1.yaml
configs/topic_clusters_v1.yaml
configs/validation_queries.yaml
```

### Core update scripts

```text
scripts/update/run_incremental_reconcile_stage.py
scripts/update/promote_canonical_candidate.py
scripts/update/check_refresh_definition_of_done.py
scripts/update/run_refresh_pipeline_v1.py
```

### Validation / evaluation scripts

```text
scripts/validation/check_canonical_provenance_consistency.py
scripts/validation/run_retrieval_checks.py
scripts/validation/run_postpass_audit.py
scripts/validation/build_known_issues_snapshot.py
scripts/validation/check_artifact_links_quality.py
scripts/validation/check_github_artifact_enrichment.py
scripts/validation/check_huggingface_artifact_enrichment.py
scripts/validation/check_paper_features.py
scripts/validation/check_ranking_profiles.py
scripts/validation/check_similar_papers_report.py
scripts/validation/check_discovery_api.py
scripts/validation/check_topic_clusters.py
scripts/validation/check_topic_projection.py
scripts/validation/check_streamlit_discovery_ui.py
scripts/validation/run_discovery_api_regression.py
scripts/evaluation/run_retrieval_eval.py
scripts/evaluation/run_search_quality_experiments.py
scripts/evaluation/run_search_quality_controlled_experiments.py
scripts/evaluation/run_qdrant_retrieval_benchmark.py
scripts/validation/check_qdrant_retrieval_benchmark.py
scripts/evaluation/export_golden_labeling_candidates.py
```

### Runtime / API / UI

```text
services/api/
services/ui/
radar_core/
store/sql/
```

---

## Important output locations

### Canonical

```text
data/analytics/reconciled/canonical_documents.jsonl
```

### Retrieval

```text
artifacts/retrieval/manifests/latest.json
artifacts/retrieval/lexical/
artifacts/retrieval/dense/
```

### Artifact layer

```text
data/enriched/artifact_links/artifact_entities_latest.jsonl
data/enriched/artifact_links/artifact_links_latest.jsonl
data/enriched/github_artifacts/github_artifact_metadata_latest.jsonl
data/enriched/huggingface_artifacts/huggingface_artifact_metadata_latest.jsonl
```

### Features

```text
data/features/paper_features_latest.jsonl
artifacts/reports/features/paper_features_latest.json
artifacts/reports/features/paper_features_quality_latest.json
```

### Ranking/detail/similar

```text
artifacts/reports/ranking/demo_radar_ranking_latest.json
artifacts/reports/details/paper_detail_latest.json
artifacts/reports/retrieval/similar_papers_latest.json
artifacts/reports/retrieval/similar_papers_quality_latest.json
```

### Topic clusters/projection

```text
artifacts/clusters/topic/latest.json
artifacts/clusters/topic/runs/<cluster_build_id>/summary.json
artifacts/clusters/topic/runs/<cluster_build_id>/label_candidates.json
artifacts/clusters/topic/runs/<cluster_build_id>/assignments.jsonl
artifacts/clusters/topic/runs/<cluster_build_id>/projection_2d.jsonl
artifacts/clusters/topic/runs/<cluster_build_id>/projection_summary.json
artifacts/reports/clusters/topic_clusters_quality_latest.json
artifacts/reports/clusters/topic_projection_quality_latest.json
```

### Validation / update reports

```text
artifacts/reports/validation/retrieval_checks_latest.json
artifacts/reports/validation/postpass_audit_summary_latest.json
artifacts/reports/validation/known_issues_snapshot_latest.json
artifacts/reports/validation/canonical_contract_latest.json
artifacts/reports/api/discovery_api_quality_latest.json
artifacts/reports/ui/streamlit_discovery_ui_quality_latest.json
artifacts/reports/update/check_refresh_definition_of_done_latest.json
artifacts/reports/evaluation/qdrant_retrieval_benchmark_latest.json
artifacts/reports/validation/qdrant_retrieval_benchmark_quality_latest.json
```

---

## Git / artifact hygiene

Do not commit large generated artifacts by default:

```text
data/raw/
data/normalized/
data/analytics/reconciled/canonical_documents.jsonl
data/features/paper_features_latest.jsonl
artifacts/retrieval/dense/*.npy
artifacts/retrieval/lexical/*.pkl
artifacts/reports/**/history/
Postgres dumps
Qdrant storage
```

Prefer committing:

```text
code
configs
docs
tests
small sample fixtures
small latest JSON reports only when intentionally used as documentation evidence
```

If in doubt, check `.gitignore` and inspect `git status` carefully before committing.

---

## Recommended working style

Keep the system modular.

Preferred pattern:

```text
small focused script
→ explicit report
→ strict validator
→ optional DoD gate
→ docs/runbook update
```

Avoid:

```text
large hidden side-effect scripts
implicit latest-file discovery when manifest exists
unvalidated generated layers
derived layers modifying canonical truth
new product features without quality gates
```

---

## Next operational improvements

Near-term:

```text
docs/runbook sync after each new checkpoint
Golden Set Expansion v2
group-level metrics in controlled experiments
topic label / UI polish
```

Later:

```text
Qdrant/vector serving
scientific embedding profiles
OpenReview source onboarding
full-text / RAG layer
Airflow orchestration
observability
```

Final rule:

```text
Viability first, candidate integration second, stable integration last.
```
