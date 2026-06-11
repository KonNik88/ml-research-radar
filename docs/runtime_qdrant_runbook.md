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
- reload reset;
- Git hygiene.

It is intentionally narrower than `docs/refresh_contract_v1.md`. It does not
describe a full canonical refresh.

---

## Current baseline

```text
checkpoint = Qdrant Runtime Observability v1
checkpoint date = 2026-06-11
implementation commit = f89574e
feature branch = retrieval/qdrant-runtime-observability-v1

main before branch = 7539dd4
previous checkpoint = Qdrant Failure Contract v1 merged in PR #17

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
runtime_probe_ttl_sec = 30
```

---

## Core boundaries

```text
canonical_documents.jsonl is paper truth
Qdrant is optional and derived
Qdrant is not required for /health readiness
Qdrant does not change public /search defaults
Qdrant experimental search lives under /experimental/search/qdrant
hidden fallback is prohibited
Streamlit is a thin API client
```

Public search remains:

```text
/search?mode=lexical → public lexical
/search?mode=dense   → file dense
/search?mode=hybrid  → file dense component
```

---

## 1. After full computer restart

Start Docker Desktop first and wait until it is fully ready.

### Git Bash

```bash
cd /d/ML/ML_Research_Radar
git fetch origin --prune
git branch --show-current
git log -5 --oneline --decorate
git status -sb
git status --short
```

Expected branch during this slice:

```text
retrieval/qdrant-runtime-observability-v1
```

Expected commit:

```text
f89574e api: add Qdrant runtime observability
```

Expected local-only change may be:

```text
 M notebooks/Untitled.ipynb
```

Do not stage the notebook unless it is intentionally part of a separate commit.

### Anaconda Prompt

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_SEARCH_BACKEND=file
```

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

For file/Qdrant checks, Postgres is useful but is not the core blocker.
Qdrant must be running for live Qdrant checks.

---

## 3. Minimal validation after restart

```bat
python -m scripts.validation.check_qdrant_collection --strict
python -m pytest tests/smoke/test_api_qdrant_backend_composition.py -q
python -m pytest tests/integration/test_api_smoke.py -q
python -m scripts.validation.check_qdrant_api_experimental --strict
```

Expected:

```text
Qdrant collection strict validation = green
backend composition / observability = 6 passed
API smoke = 7 passed
experimental Qdrant API = 200 / dense_qdrant
```

Run heavy test groups as separate Python processes.

---

## 4. Start FastAPI

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

Keep this terminal open to inspect server logs.

---

## 5. Runtime probe semantics

Open Anaconda Prompt window 2:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

### 5.1 Forced live probe

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

### 5.2 Cached probe

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

After the TTL expires, an ordinary `/runtime` request performs a new live probe.

---

## 6. Successful experimental Qdrant request

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

Inspect runtime state:

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

A first cold encode may be much slower than later warm encodes. Record it as
performance evidence; do not treat one request as a benchmark.

---

## 7. Negative Qdrant check

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

Force a fresh runtime probe:

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

Check general readiness:

```bat
curl -i http://127.0.0.1:8000/health
```

Expected:

```text
HTTP 200
ready = true
backend_mode = file
```

Check public file dense:

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

A locale-dependent Windows socket message may display incorrectly in the
best-effort probe `error` field. Use the stable fields for automation:

```text
last_failure_category
last_failure_stage
HTTP error_code
```

---

## 8. Recovery check

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

The previous failure evidence remains intentionally available:

```text
last_failure_at is populated
last_failure_category = dense_backend_unavailable
last_failure_stage = backend_search
last_failure_message is populated
```

No API restart or runtime reload is required for transient Qdrant recovery.

---

## 9. Reload reset check

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

Expected:

```text
4 passed
```

---

## 10. Start Streamlit

Open another Anaconda Prompt:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_API_BASE_URL=http://127.0.0.1:8000
streamlit run services/ui/app.py
```

Expected URL:

```text
http://localhost:8501
```

The UI remains a thin API client. Runtime observability does not move backend
logic into Streamlit.

---

## 11. Milestone regression

Stop standalone Uvicorn before heavy validation to release model/GPU resources.

Run separate processes:

```bat
set ML_RADAR_SEARCH_BACKEND=file

python -m pytest tests/integration/test_api_errors.py -q
python -m pytest tests/integration/test_api_discovery.py -q
python -m scripts.validation.check_qdrant_api_experimental --strict
```

Integrated regression:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-qdrant-serving-poc ^
  --include-qdrant-api
```

Full strict Definition of Done:

```bat
python -m scripts.update.check_refresh_definition_of_done ^
  --require-known-issues ^
  --require-artifacts ^
  --require-github-enrichment ^
  --require-huggingface-enrichment ^
  --require-paper-features ^
  --require-similar-papers ^
  --require-discovery-api ^
  --require-topic-clusters ^
  --require-topic-projection ^
  --require-streamlit-discovery-ui ^
  --require-golden-queries
```

Expected milestone result:

```text
Discovery API regression passed
dod_passed = true
required_failed_count = 0
```

---

## 12. Hugging Face / VPN caveat

`SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` may make
HEAD or metadata requests to Hugging Face even when model weights are cached.

If VPN or network is unstable, startup or tests may fail before project code is
exercised.

Offline smoke mode:

```bat
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_smoke.py -q
```

If cache files are incomplete, temporarily unset offline mode and warm the
cache:

```bat
set HF_HUB_OFFLINE=
set TRANSFORMERS_OFFLINE=
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

---

## 13. Git hygiene

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

Do not use `git add .` in this workflow.

---

## 14. Minimal daily smoke

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

This is sufficient to validate the current runtime/Qdrant surface before a
small feature branch.
