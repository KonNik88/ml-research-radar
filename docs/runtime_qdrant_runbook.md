# Runtime / Qdrant / Streamlit Runbook

## Purpose

This runbook describes the day-to-day operational loop for running **ML Research Radar** after a full computer restart, validating the current file runtime, checking Qdrant, and opening the Streamlit Discovery UI.

It is intentionally narrower than `docs/refresh_contract_v1.md`: this file is for normal development startup and Qdrant/runtime/UI smoke checks, not for full canonical refresh.

---

## Current baseline

```text
Discovery Green Checkpoint — 2026-05
Qdrant runtime visibility sync — 2026-06
canonical_documents = 60954
retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]
qdrant_collection = ml_radar_dense_benchmark_v1
qdrant_points_count = 60954
```

---

## Core boundaries

```text
Qdrant is optional and derived.
Qdrant is not canonical truth.
Qdrant is not required for /health readiness.
Qdrant does not change /search defaults.
Qdrant experimental search lives under /experimental/search/qdrant.
Streamlit is a thin API client.
```

---

## 1. After full computer restart

Start Docker Desktop first and wait until it is fully running.

Then open Anaconda Prompt:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

Synchronize the local branch:

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

---

## 2. Start Docker services

From the project root:

```bat
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml ps
```

Expected:

```text
ml_radar_postgres = Up / healthy
ml_radar_qdrant = Up
```

If only file/Qdrant checks are needed, Postgres being healthy is useful but not the core blocker. Qdrant must be up for Qdrant checks.

---

## 3. Quick validation after restart

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
streamlit UI = required_failed_count 0
qdrant_runtime_status_ui_snippets_present = true
```

---

## 4. Start FastAPI

Open Anaconda Prompt window 1:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_SEARCH_BACKEND=file
python -m uvicorn services.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Wait for:

```text
Application startup complete.
```

Manual API checks from another terminal:

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

---

## 5. Start Streamlit

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

---

## 6. Streamlit smoke path

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

Then click **Open Qdrant result in Paper workspace** and load detail/similar/topic cluster from the Paper workspace.

---

## 7. Negative Qdrant check

Use this check when changing Qdrant runtime/status UI logic.

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

## 8. Hugging Face / VPN caveat

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

## 9. Git hygiene after checks

Before committing:

```bat
git status --short
git diff --stat
```

Do not commit by default:

```text
notebooks/Untitled.ipynb
artifacts/reports/**/history/
large generated retrieval artifacts
Qdrant storage
Postgres dumps
```

Prefer committing:

```text
code
tests
docs
configs
small intentional validation reports only when used as documentation evidence
```

---

## 10. Minimal daily smoke

For ordinary development:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
docker compose -f infra/docker/docker-compose.yml up -d
python -m scripts.validation.check_qdrant_collection --strict
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_smoke.py -q
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

This is enough to verify the current runtime/UI/Qdrant surface before starting a small feature branch.
