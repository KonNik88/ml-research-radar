# Refresh / Runtime Runbook v1

## Purpose

This runbook describes the current safe manual refresh, validation, runtime startup and Qdrant/Streamlit operational loop for **ML Research Radar**.

It is the operational companion to:

```text
docs/roadmap.md
docs/architecture.md
docs/api_reference.md
docs/experiment_safety_rules.md
docs/provenance_semantics.md
docs/data_contracts.md
docs/source_matrix.md
docs/merge_policy.md
```

The document is intentionally practical. It answers:

```text
What is source of truth?
What can be rebuilt?
What must be validated?
How do we start the project after a full computer restart?
How do we check API/Qdrant/Streamlit?
What is considered a green checkpoint?
```

---

## Current checkpoint

Current working checkpoint:

```text
Discovery Green Checkpoint — 2026-05
Qdrant runtime visibility sync — 2026-06
```

Current healthy baseline:

```text
canonical_documents = 60954
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

github_found_count ≈ 5339
huggingface_found_count ≈ 77

paper_features_rows_count = 60954
ranking_profiles_count = 9
topic_clusters_count = 80
topic_assignments_count = 60954
topic_projection_algorithm = umap
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

Important naming note:

```text
known_issues_snapshot_latest.json
```

not:

```text
known_issues_latest.json
```

---

## Core architecture invariants

```text
canonical_documents.jsonl = paper-level truth
Postgres = rebuildable materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization plane
GitHub/Hugging Face = artifact enrichment providers, not paper sources
paper_features = derived discovery feature layer
ranking / detail / similar = derived discovery/product layer
topic clusters / projection = derived analytics/discovery layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin API client
Qdrant = optional derived vector-serving benchmark / experimental layer
```

No derived layer is allowed to mutate canonical truth.

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
- `acl_anthology` is the first major source-expansion case.
- GitHub and Hugging Face enrich artifact entities; they are not paper-truth sources.
- Papers with Code live/source integration remains blocked/archived; PWC-like signals are artifact candidates only unless policy changes.

Current operational paper source of truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

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

Key rule:

```text
reconcile must run from full intended inputs, not accidental mini-batches
```

This prevents corpus collapse, source loss and misleading multisource counts.

---

# A. Daily startup after full computer restart

Use this when continuing normal development, not when rebuilding canonical truth.

## 1. Start Docker Desktop

Start Docker Desktop manually and wait until it is fully running.

## 2. Open Anaconda Prompt

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

## 3. Sync main

```bat
git checkout main
git pull --ff-only
git log --oneline -5
git status --short
```

Expected local status may include only local notebook notes:

```text
 M notebooks/Untitled.ipynb
```

Do not commit this notebook unless intentionally needed.

## 4. Start containers

```bat
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml ps
```

Expected:

```text
ml_radar_postgres = Up / healthy
ml_radar_qdrant = Up
```

## 5. Quick smoke checks

```bat
python -m scripts.validation.check_qdrant_collection --strict
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_smoke.py -q
python -m scripts.validation.check_qdrant_api_experimental --strict
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Expected:

```text
qdrant collection_exists = true
qdrant points_count = 60954
qdrant corpus_doc_count = 60954
test_api_smoke.py = 6 passed
experimental qdrant API = status_code 200, mode dense_qdrant
streamlit UI required_failed_count = 0
qdrant_runtime_status_ui_snippets_present = true
```

---

# B. Run API and Streamlit locally

## 1. FastAPI

Open Anaconda Prompt window 1:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_SEARCH_BACKEND=file
python -m uvicorn services.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Expected:

```text
Application startup complete.
```

Manual checks:

```bat
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runtime
```

Expected `/runtime.qdrant` healthy state:

```text
qdrant.ok = true
qdrant.collection_exists = true
qdrant.points_count = 60954
qdrant.expected_corpus_doc_count = 60954
qdrant.points_match_corpus = true
qdrant.vector_size = 384
qdrant.distance = Cosine
```

## 2. Streamlit

Open Anaconda Prompt window 2:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_API_BASE_URL=http://127.0.0.1:8000
streamlit run services/ui/app.py
```

Expected browser URL:

```text
http://localhost:8501
```

Expected sidebar:

```text
API is reachable
Backend: file
Corpus docs: 60954
Qdrant runtime
Qdrant: OK
Collection: ml_radar_dense_benchmark_v1
Points: 60954 / 60954
Points match corpus: True
Vector size: 384
Distance: Cosine
```

## 3. Streamlit Qdrant smoke

In the UI:

1. Open **Search**.
2. Expand **Experimental Qdrant dense search**.
3. Query:

```text
protein language models
```

4. Set top K to 5–10.
5. Click **Run experimental Qdrant search**.

Expected:

```text
Mode: dense_qdrant
Backend: qdrant
Returned > 0
```

Then click **Open Qdrant result in Paper workspace** and load:

```text
selected paper detail
selected paper similar papers
selected paper topic cluster
```

---

# C. Qdrant negative check

Use this when changing Qdrant runtime diagnostics, Qdrant UI status, or Qdrant settings.

Keep API and Streamlit running.

Open Anaconda Prompt window 3:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
docker compose -f infra/docker/docker-compose.yml stop qdrant
```

In Streamlit, click **Refresh**.

Expected:

```text
API remains reachable
Qdrant: unavailable
Qdrant diagnostic error is visible in an expander
UI does not crash
```

Manual API expectation:

```bat
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runtime
```

Expected:

```text
/health -> 200 OK if file runtime is ready
/runtime -> 200 OK
/runtime.qdrant.ok = false
/runtime.qdrant.error is populated
```

Return Qdrant:

```bat
docker compose -f infra/docker/docker-compose.yml up -d qdrant
python -m scripts.validation.check_qdrant_collection --strict
```

In Streamlit, click **Refresh** again.

Expected:

```text
Qdrant: OK
Points: 60954 / 60954
```

---

# D. Manual refresh flow

Use this only when refreshing canonical or derived artifacts, not for ordinary development startup.

There are two valid styles:

1. use the thin orchestration wrapper;
2. run individual steps manually while debugging.

## Option A — thin orchestration wrapper

Example:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --arxiv-input data\normalized\arxiv\documents.20260404T161108Z.jsonl --execute
```

Intended high-level sequence:

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

After wrapper completion, run downstream product checks if the wrapper does not already cover them.

## Option B — step-by-step execution

### 1. Build canonical candidate

```bat
python -m scripts.update.run_incremental_reconcile_stage --arxiv-input data\normalized\arxiv\documents.20260404T161108Z.jsonl --output-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl --execute
```

### 2. Audit candidate provenance

```bat
python -m scripts.validation.check_canonical_provenance_consistency --canonical-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl
```

Expected:

```text
docs_with_error = 0
```

Warnings must be interpreted through:

```text
docs/provenance_semantics.md
```

### 3. Promote candidate

```bat
python -m scripts.update.promote_canonical_candidate --candidate-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl --execute
```

### 4. Export canonical to Postgres

```bat
python -m scripts.export.export_postgres_v1 --replace
python -m scripts.export.test_db_read
```

### 5. Rebuild retrieval artifacts

```bat
python -m scripts.retrieval.build_indexes
```

Safe test build pattern:

```bat
python -m scripts.retrieval.build_indexes --no-write-latest
```

### 6. Run retrieval checks

```bat
python -m scripts.validation.run_retrieval_checks
```

### 7. Run postpass audit

```bat
python -m scripts.validation.run_postpass_audit
```

### 8. Refresh known issues snapshot

```bat
python -m scripts.validation.build_known_issues_snapshot
```

### 9. Rebuild / validate artifact layer

If canonical/source content changed enough to affect URLs/artifacts:

```bat
python -m scripts.enrich.extract_artifact_links
python -m scripts.validation.check_artifact_links_quality --strict
python -m scripts.export.export_artifacts_postgres_v1 --replace
python -m scripts.export.test_artifact_db_read
```

### 10. Validate GitHub enrichment

```bat
python -m scripts.validation.check_github_artifact_enrichment --strict
```

### 11. Validate Hugging Face enrichment

```bat
python -m scripts.validation.check_huggingface_artifact_enrichment --strict
```

Current non-blocking provider/extraction states unless policy changes:

```text
Hugging Face forbidden
Hugging Face skipped_invalid_external_id
GitHub not_found preserved as historical artifact evidence
```

### 12. Build / validate paper features

```bat
python -m scripts.features.build_paper_features
python -m scripts.validation.check_paper_features --strict
```

### 13. Validate ranking profiles

```bat
python -m scripts.validation.check_ranking_profiles --strict
```

### 14. Build / validate paper detail and similar papers

```bat
python -m scripts.ranking.demo_radar_ranking --profile huggingface_ready --top-k 5
python -m scripts.details.build_paper_detail --from-latest-ranking-rank 1
python -m scripts.retrieval.find_similar_papers --from-latest-detail --top-k 20
python -m scripts.validation.check_similar_papers_report --strict
```

### 15. Build / validate topic clusters

If retrieval embeddings, canonical corpus, or paper features changed:

```bat
python -m scripts.analytics.build_topic_clusters
python -m scripts.validation.check_topic_clusters --strict
```

### 16. Build / validate topic projection

If topic clusters changed or projection needs refresh:

```bat
python -m scripts.analytics.build_topic_projection
python -m scripts.validation.check_topic_projection --strict
```

### 17. Validate Discovery API

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_discovery.py -q
python -m scripts.validation.check_discovery_api --strict
```

### 18. Validate Streamlit Discovery UI

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Optional live API validation:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict --check-api
```

---

# E. Qdrant validation layers

## Qdrant collection check

```bat
python -m scripts.validation.check_qdrant_collection --strict
```

Expected current-green state:

```text
collection_name = ml_radar_dense_benchmark_v1
collection_exists = true
points_count = 60954
corpus_doc_count = 60954
required_failed_count = 0
```

## Qdrant serving POC checks

Use after a Qdrant benchmark has already created the benchmark collection.

```bat
python -m scripts.validation.check_qdrant_collection --strict
python -m scripts.evaluation.compare_qdrant_file_dense
python -m scripts.validation.check_qdrant_file_dense_comparison --strict
```

Expected current-green state:

```text
mean_overlap_ratio_at_k = 1.0
min_overlap_ratio_at_k = 1.0
required_failed_count = 0
```

These checks validate an existing collection. They do not recreate the collection or upload vectors.

## Full Qdrant benchmark

Use only when intentionally rebuilding/revalidating the vector-serving benchmark collection:

```bat
python -m scripts.evaluation.run_qdrant_retrieval_benchmark
python -m scripts.validation.check_qdrant_retrieval_benchmark --strict
```

This is heavier than the serving POC checks.

## Experimental Qdrant API endpoint

```bat
python -m scripts.validation.check_qdrant_api_experimental --strict
```

Expected:

```text
status_code = 200
mode = dense_qdrant
collection_name = ml_radar_dense_benchmark_v1
result_count > 0
required_failed_count = 0
```

Important boundaries:

```text
/search remains unchanged.
SearchRuntime remains unchanged.
ML_RADAR_SEARCH_BACKEND remains file/db.
Qdrant is not the production default backend.
```

---

# F. Discovery API regression runner

Quick discovery regression:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.run_discovery_api_regression
```

Common variants:

```bat
python -m scripts.validation.run_discovery_api_regression --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments --include-controlled-search-quality-experiments
python -m scripts.validation.run_discovery_api_regression --include-qdrant-serving-poc --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-qdrant-api --include-qdrant-serving-poc --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-qdrant-benchmark --include-qdrant-serving-poc --include-qdrant-api --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-db-smoke --include-dod
python -m scripts.validation.run_discovery_api_regression --include-live-ui-check
```

---

# G. Strict Definition of Done

Current full strict DoD command should include the active required gates supported by the current project codebase:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api --require-topic-clusters --require-topic-projection --require-streamlit-discovery-ui --require-golden-queries
```

Expected:

```text
dod_passed = true
required_failed_count = 0
```

If local `--help` does not show these gates, sync the DoD script before treating local docs as current.

---

# H. Hugging Face / VPN caveat

`SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` may make HEAD/metadata requests to Hugging Face even when weights are cached. If VPN/network is unstable, startup or tests may fail before project code is actually exercised.

First retry without VPN.

If the model is already cached, offline mode can be used for smoke tests:

```bat
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_smoke.py -q
```

If offline mode reports missing cache files, temporarily unset offline mode and warm the cache:

```bat
set HF_HUB_OFFLINE=
set TRANSFORMERS_OFFLINE=
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

Then retry the smoke tests.

---

# I. Git / artifact hygiene

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

Before committing:

```bat
git status --short
git diff --stat
git diff --cached --stat
```

---

# J. Blockers

Stop and investigate if any of these occur:

- reconcile uses unsafe/incomplete inputs;
- canonical doc count collapses unexpectedly;
- arXiv backbone is unexpectedly reduced;
- multisource docs collapse unexpectedly;
- duplicate canonical IDs appear;
- required canonical fields disappear;
- promotion fails;
- Postgres export/read smoke fails;
- retrieval manifest doc count mismatches canonical;
- retrieval checks fail;
- artifact quality/export/DB read fails;
- GitHub/HF enrichment strict checks fail outside known provider-state caveats;
- paper features rows do not match canonical;
- similar papers target/result checks fail;
- Discovery API quality fails;
- topic clusters/projection quality fails;
- Streamlit UI quality fails;
- Qdrant collection points mismatch current corpus;
- `/runtime.qdrant` reports `points_match_corpus=false` unexpectedly;
- strict DoD fails.

---

# K. Non-blocker diagnostics under current semantics

These are not automatic blockers unless policy changes:

```text
doc_ids_shorter_than_sources
repeated source families in provenance lists
arxiv_id present without a direct arXiv provenance row when provenance semantics explain it
source_ids containing more families than sources
Hugging Face forbidden provider states
Hugging Face skipped_invalid_external_id extraction/noise states
GitHub not_found repositories preserved as historical artifact evidence
heuristic topic label_candidates being imperfect
Qdrant unavailable during file runtime when Qdrant-specific checks are not in scope
```

---

## Final operational rule

```text
Viability first, candidate integration second, stable integration last.
```
