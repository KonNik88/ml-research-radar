# Runtime / Qdrant / Streamlit Runbook

## Purpose

This runbook describes the normal development and validation loop for
**ML Research Radar** after a full computer restart.

It covers:

- Git checkpoint verification;
- Docker service startup;
- file-runtime startup;
- Qdrant collection validation;
- FastAPI and Streamlit startup;
- cached and forced `/runtime` diagnostics;
- successful, failed, and recovered experimental Qdrant search;
- gRPC transport verification;
- serving-performance validation;
- reload reset;
- milestone regression;
- Git hygiene.

It is intentionally narrower than `docs/refresh_contract_v1.md`. It does not
describe a full canonical refresh.

---

## Current baseline

```text
checkpoint = Qdrant Serving Performance v1
checkpoint date = 2026-06-12
feature branch = retrieval/qdrant-serving-performance-v1
previous checkpoint = Qdrant Runtime Observability v1 merged in PR #18

canonical_documents = 60954
canonical_multisource_docs = 9192
retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]

qdrant_image = qdrant/qdrant:v1.17.0
qdrant_collection = ml_radar_dense_benchmark_v1
qdrant_points_count = 60954
qdrant_vector_size = 384
qdrant_distance = Cosine
qdrant_profile = ef_256
qdrant_hnsw_ef = 256

qdrant_rest_port = 6333
qdrant_grpc_port = 6334
qdrant_prefer_grpc = true
experimental_transport = grpc

runtime_probe_ttl_sec = 30
public_dense_backend = file
public_hybrid_dense_component = file
```

Current validated serving evidence:

```text
Golden Set queries = 34
quality comparisons = 681
exact comparisons = 681
serving errors = 0

backend Qdrant concurrency 8 = 680 / 680
API Qdrant concurrency 8 = 204 / 204
strict performance validator failures = 0
full strict DoD failures = 0
```

---

## Core boundaries

```text
canonical_documents.jsonl is paper truth
Qdrant is optional and derived
Qdrant is not required for /health readiness
Qdrant does not change public /search defaults
Qdrant experimental search lives under /experimental/search/qdrant
experimental Qdrant serving uses gRPC
hidden fallback is prohibited
Streamlit is a thin API client
```

Public search remains:

```text
/search?mode=lexical → public lexical
/search?mode=dense   → file dense
/search?mode=hybrid  → file dense component
```

Experimental Qdrant remains:

```text
/experimental/search/qdrant
→ QdrantDenseBackend
→ gRPC port 6334
```

REST port `6333` remains available for collection health and administrative
client operations where the Qdrant client uses REST.

---

## 1. After full computer restart

Start Docker Desktop first and wait until it is fully ready.

### Git Bash

```bash
cd /d/ML/ML_Research_Radar
git fetch origin --prune
git branch --show-current
git log -8 --oneline --decorate
git status -sb
git status --short
```

Expected branch before this PR is merged:

```text
retrieval/qdrant-serving-performance-v1
```

After merge:

```bash
git switch main
git pull --ff-only
```

Expected local-only change may be:

```text
 M notebooks/Untitled.ipynb
```

Do not stage the notebook unless it belongs to a separate intentional commit.

### Anaconda Prompt

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_SEARCH_BACKEND=file
```

Confirm:

```bat
echo %ML_RADAR_SEARCH_BACKEND%
python -c "import os; print(os.getenv('ML_RADAR_SEARCH_BACKEND'))"
```

Expected:

```text
file
file
```

The project `.env` may contain a different backend default. Always set the
file backend explicitly before file-runtime integration tests.

---

## 2. Start Docker services

```bat
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml ps
docker ps
```

Expected:

```text
ml_radar_postgres = Up / healthy
ml_radar_qdrant   = Up
```

Qdrant must expose:

```text
6333 = REST
6334 = gRPC
```

Inspect if necessary:

```bat
docker inspect ml_radar_qdrant --format "{{.State.Status}} {{.State.OOMKilled}} {{.RestartCount}}"
```

Expected:

```text
running false 0
```

---

## 3. Minimal validation after restart

```bat
set ML_RADAR_SEARCH_BACKEND=file

python -m scripts.validation.check_qdrant_collection --strict
python -m pytest tests/smoke/test_api_qdrant_backend_composition.py -q
python -m pytest tests/integration/test_api_smoke.py -q
python -m scripts.validation.check_qdrant_api_experimental --strict
python -m scripts.validation.check_qdrant_serving_performance --strict
```

Expected:

```text
Qdrant collection strict validation = green
backend composition = green
API smoke = green
experimental Qdrant API = 200 / dense_qdrant
runtime transport = grpc
performance report preset = full
performance required_failed_count = 0
```

Run heavy test groups as separate Python processes.

---

## 4. Direct gRPC probe

Use this after transport-related changes:

```bat
python -c "from radar_core.retrieval.qdrant_store import QdrantRetrievalStore; s=QdrantRetrievalStore(host='localhost', port=6333, grpc_port=6334, prefer_grpc=True, collection_name='ml_radar_dense_benchmark_v1', timeout_sec=120, check_compatibility=False); print('transport=', s.transport); print('exists=', s.collection_exists()); print('count=', s.count_points()); print('info=', s.get_collection_info())"
```

Expected:

```text
transport= grpc
exists= True
count= 60954
```

This probe does not mutate the collection.

---

## 5. Start FastAPI

Open Anaconda Prompt window 1:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_SEARCH_BACKEND=file
python -m uvicorn services.api.app:app --host 127.0.0.1 --port 8000
```

Wait for:

```text
Application startup complete.
```

Keep the terminal open to inspect logs.

---

## 6. Runtime probe semantics

Open Anaconda Prompt window 2:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

### 6.1 Forced live probe

```bat
curl -s "http://127.0.0.1:8000/runtime?refresh_qdrant=true" | python -m json.tool
```

Expected Qdrant fields:

```text
ok = true
collection_exists = true
points_count = 60954
expected_corpus_doc_count = 60954
points_match_corpus = true
vector_size = 384
distance = Cosine

port = 6333
grpc_port = 6334
prefer_grpc = true
transport = grpc

probe_cached = false
probe_cache_age_sec = 0.0
probe_ttl_sec = 30.0

profile_name = ef_256
exact = false
hnsw_ef = 256
build_id = 20260504T164021Z

request_count = 0
success_count = 0
failure_count = 0
last_status = never
```

### 6.2 Cached probe

Immediately repeat:

```bat
curl -s "http://127.0.0.1:8000/runtime" | python -m json.tool
```

Expected:

```text
probe_cached = true
probe_checked_at unchanged
probe_cache_age_sec > 0
probe_cache_age_sec <= 30
```

After TTL expiry, an ordinary `/runtime` request performs a new live probe.

---

## 7. Successful experimental Qdrant request

```bat
curl -G -s ^
  --data-urlencode "query=protein language models" ^
  --data-urlencode "top_k=3" ^
  http://127.0.0.1:8000/experimental/search/qdrant ^
  | python -m json.tool
```

Expected:

```text
HTTP 200
mode = dense_qdrant
result_count = 3
vector_backend = qdrant
source_backend = file_runtime
```

Inspect runtime:

```bat
curl -s "http://127.0.0.1:8000/runtime" | python -m json.tool
```

Expected:

```text
backend_created = true
compatibility_checked = true
compatibility_ok = true

request_count = 1
success_count = 1
failure_count = 0
last_status = ok

requested_vector_backend = qdrant
effective_vector_backend = qdrant
fallback_applied = false

last_result_count = 3
last_timing_ms contains:
  encode_ms
  qdrant_search_ms
  hydrate_ms
  total_ms
```

The first request may be much slower because backend and gRPC channel creation
are lazy. Record it as operational evidence; do not treat one request as a
benchmark.

---

## 8. Negative Qdrant check

Keep FastAPI running.

Stop only Qdrant:

```bat
docker compose -f infra/docker/docker-compose.yml stop qdrant
```

Run the experimental request:

```bat
curl -G -i ^
  --data-urlencode "query=protein language models" ^
  --data-urlencode "top_k=3" ^
  http://127.0.0.1:8000/experimental/search/qdrant
```

Expected:

```text
HTTP 503
error_code = dense_backend_unavailable
```

Force a fresh probe:

```bat
curl -s "http://127.0.0.1:8000/runtime?refresh_qdrant=true" | python -m json.tool
```

Expected:

```text
ok = false
probe_cached = false
error is populated

request_count = 2
success_count = 1
failure_count = 1
last_status = error

last_failure_category = dense_backend_unavailable
last_failure_stage = backend_search
last_failure_at is populated
last_failure_message is populated

requested_vector_backend = qdrant
effective_vector_backend = null
fallback_applied = false
```

General health must remain ready:

```bat
curl -i http://127.0.0.1:8000/health
```

Expected:

```text
HTTP 200
ready = true
backend_mode = file
```

Public file dense must remain available:

```bat
curl -G -i ^
  --data-urlencode "query=graph neural networks" ^
  --data-urlencode "mode=dense" ^
  --data-urlencode "top_k=3" ^
  http://127.0.0.1:8000/search
```

Expected:

```text
HTTP 200
mode = dense
```

Use stable machine-readable fields for automation, not localized OS messages:

```text
last_failure_category
last_failure_stage
HTTP error_code
```

---

## 9. Recovery check

Restart Qdrant:

```bat
docker compose -f infra/docker/docker-compose.yml up -d qdrant
docker compose -f infra/docker/docker-compose.yml ps
python -m scripts.validation.check_qdrant_collection --strict
```

Run the experimental request again:

```bat
curl -G -s ^
  --data-urlencode "query=protein language models" ^
  --data-urlencode "top_k=3" ^
  http://127.0.0.1:8000/experimental/search/qdrant ^
  | python -m json.tool
```

Force a fresh probe:

```bat
curl -s "http://127.0.0.1:8000/runtime?refresh_qdrant=true" | python -m json.tool
```

Expected:

```text
ok = true

request_count = 3
success_count = 2
failure_count = 1
last_status = ok

requested_vector_backend = qdrant
effective_vector_backend = qdrant
fallback_applied = false
```

Previous failure evidence remains available intentionally.

No API restart or runtime reload is required for transient recovery.

---

## 10. Reload reset check

`POST /reload` resets:

- cached Qdrant backend;
- live-probe cache;
- request/success/failure counters;
- timestamps;
- last-failure state;
- last timings;
- requested/effective backend state.

Manual check:

```bat
curl -X POST http://127.0.0.1:8000/reload
curl -s "http://127.0.0.1:8000/runtime" | python -m json.tool
```

Expected:

```text
backend_created = false
request_count = 0
success_count = 0
failure_count = 0
last_status = never
last_failure_category = null
last_timing_ms = {}
```

Automated check:

```bat
python -m pytest tests/integration/test_api_reload.py -x -vv
```

---

## 11. Start Streamlit

Open another Anaconda Prompt:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_API_BASE_URL=http://127.0.0.1:8000
python -m streamlit run services/ui/app.py
```

Expected URL:

```text
http://localhost:8501
```

The UI remains a thin API client.

---

## 12. Serving-performance benchmark

Stop standalone Uvicorn before benchmark runs so the benchmark can own its
temporary port and GPU/model resources.

Check the benchmark port:

```bat
netstat -ano | findstr :8011
```

Expected: no listener.

Run:

```bat
set ML_RADAR_SEARCH_BACKEND=file

python -m scripts.evaluation.run_qdrant_serving_performance ^
  --preset full
```

Expected:

```text
preset = full
query_count = 34
qdrant_transport = grpc
error_count = 0
quality_ok = true
```

Strict validation:

```bat
python -m scripts.validation.check_qdrant_serving_performance --strict
```

Expected:

```text
source_error_count = 0
source_comparison_count = 681
required_failed_count = 0
```

Quick check:

```bat
python -c "import json; p=json.load(open('artifacts/reports/evaluation/qdrant_serving_performance_latest.json', encoding='utf-8')); print({k:p['summary'][k] for k in ('query_count','qdrant_transport','error_count','quality_ok')})"
```

Do not weaken the zero-error policy if a transport error appears. Inspect:

- `error_chain`;
- `query_id`;
- `top_k`;
- `round`;
- concurrency;
- Qdrant container logs.

---

## 13. Milestone regression

Stop standalone Uvicorn before heavy validation.

Targeted suite:

```bat
set ML_RADAR_SEARCH_BACKEND=file

python -m pytest ^
  tests/smoke/test_dense_backend_contract.py ^
  tests/smoke/test_qdrant_dense_backend.py ^
  tests/smoke/test_api_qdrant_backend_composition.py ^
  tests/smoke/test_qdrant_serving_performance.py ^
  tests/smoke/test_qdrant_serving_performance_validator.py ^
  tests/smoke/test_qdrant_regression_runner.py ^
  tests/integration/test_api_smoke.py ^
  tests/integration/test_api_errors.py ^
  tests/integration/test_api_reload.py ^
  tests/integration/test_api_discovery.py ^
  -q
```

Current checkpoint evidence:

```text
145 passed
4 expected DB-only skips under file runtime
```

Moderate integrated regression:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-qdrant-serving-poc ^
  --include-qdrant-api
```

Final milestone regression:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-qdrant-serving-poc ^
  --include-qdrant-profile-sweep ^
  --include-qdrant-serving-performance ^
  --include-qdrant-api ^
  --include-db-smoke ^
  --include-dod
```

Expected:

```text
selected ef_256 = 34 / 34 exact
exact oracle = 34 / 34 exact
serving error_count = 0
serving required_failed_count = 0
experimental Qdrant API = green
DB total documents = 60954
dod_passed = true
required_failed_count = 0
Discovery API regression passed
```

---

## 14. Hugging Face / VPN caveat

`SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` may make
metadata requests even when weights are cached.

If network is unstable, startup may fail before project code is exercised.

Offline mode:

```bat
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_smoke.py -q
```

If cache files are incomplete:

```bat
set HF_HUB_OFFLINE=
set TRANSFORMERS_OFFLINE=
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

---

## 15. Git hygiene

Git operations belong in Git Bash.

Before committing:

```bash
git status --short
git diff --check
git diff --stat
```

Do not commit by default:

```text
notebooks/Untitled.ipynb
artifacts/reports/**/history/
large generated retrieval artifacts
Qdrant storage
Postgres dumps
.env
```

Prefer explicit staging:

```bash
git add <intentional files only>
```

Do not use `git add .`.

---

## 16. Minimal daily smoke

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
docker compose -f infra/docker/docker-compose.yml up -d
set ML_RADAR_SEARCH_BACKEND=file

python -m scripts.validation.check_qdrant_collection --strict
python -m pytest tests/smoke/test_api_qdrant_backend_composition.py -q
python -m pytest tests/integration/test_api_smoke.py -q
python -m scripts.validation.check_qdrant_api_experimental --strict
```

Optional evidence check without rerunning the benchmark:

```bat
python -m scripts.validation.check_qdrant_serving_performance --strict
```

This validates the current runtime/Qdrant surface before a small feature branch.
