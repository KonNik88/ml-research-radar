# ML Research Radar — Custom + UDR (Experimental)

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-ready-brightgreen)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)
![Postgres](https://img.shields.io/badge/Postgres-storage-316192)
![Qdrant](https://img.shields.io/badge/Qdrant-vector%20DB-orange)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED)
![RAG](https://img.shields.io/badge/RAG-enabled-black)
![PEFT](https://img.shields.io/badge/PEFT-optional-lightgrey)
![Ray](https://img.shields.io/badge/Ray-optional-lightgrey)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

> A portfolio‑ready project for **finding, organizing, and reasoning over ML papers & GitHub repos**.  
> Core is **hand‑built** (ingest → normalize → classify/score → RAG → UI), plus an **experimental NVIDIA UDR** tab to compare with a modern agentic framework.

---

## What you get
- **Custom pipeline** you control end‑to‑end: arXiv/GitHub ingest → Postgres + Qdrant → RAG with citations → Streamlit UI.
- **Actionable feed**: ranked items with TL;DR, tags, code links, and quick export.
- **Chat over your corpus** (RAG): ask focused questions; get grounded answers with sources.
- **Experimental UDR tab**: run the same query via NVIDIA **Universal Deep Research** and compare outputs side‑by‑side.
- Clean **Docker** setup (API, UI, Postgres, Qdrant) for one‑command local runs.

---

## Repository structure
```
ml-research-radar/
  api/                    # FastAPI: ingest/search/rag/summarize/score
    main.py
    deps.py
    schemas/
    services/
    workers/              # (optional) Ray tasks/actors
    requirements.txt
  ui/                     # Streamlit client
    streamlit_app.py
    requirements.txt
  ingest/                 # arXiv, GitHub, pdf->text
  nlp/                    # embeddings, keyphrases, taxonomy helpers
  peft/                   # scripts for LoRA/PEFT fine-tuning (optional)
  store/
    migrations/           # SQL (alembic optional)
    sql/
  docker/
    Dockerfile.api
    Dockerfile.ui
  configs/
    .env.example
    taxonomy.yaml
    scoring.yaml
  docker-compose.yml
  README.md
  LICENSE
```

---

## Services (MVP)
- **API (FastAPI)** — `/search`, `/feed`, `/rag/query`, `/summarize`, `/ingest/run`  
- **UI (Streamlit)** — *Feed*, *Chat (RAG)*, *Trends*, *Compare: Custom vs UDR*  
- **Postgres** — metadata storage (papers/repos, tags, scores)  
- **Qdrant** — vector index (abstracts/sections/readme embeddings)  
- **UDR (optional)** — separate container later; not required for MVP

---

## Quickstart (Docker)
1) Create `.env` from example and adjust secrets/paths:
```bash
cp configs/.env.example configs/.env
```
2) Build & run:
```bash
docker compose up --build
```
- API: <http://localhost:8000/docs>  
- UI:  <http://localhost:8501>

**`docker-compose.yml` (minimal sketch):**
```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16
    environment:
      - POSTGRES_USER=radar
      - POSTGRES_PASSWORD=radar
      - POSTGRES_DB=radar
    volumes: ["./pgdata:/var/lib/postgresql/data"]
    ports: ["5432:5432"]

  qdrant:
    image: qdrant/qdrant:latest
    volumes: ["./qdrant_storage:/qdrant/storage"]
    ports: ["6333:6333"]

  api:
    build: { context: ., dockerfile: docker/Dockerfile.api }
    env_file: [./configs/.env]
    depends_on: [postgres, qdrant]
    ports: ["8000:8000"]
    volumes: ["./artifacts:/app/artifacts:ro"]

  ui:
    build: { context: ., dockerfile: docker/Dockerfile.ui }
    env_file: [./configs/.env]
    depends_on: [api]
    ports: ["8501:8501"]
```
> For GPU usage later, switch to CUDA base images and run with `--gpus all` (or Compose device reservations).

---

## API sketch
**Health**
```
GET  /health
```

**Ingest**
```
POST /ingest/run
body: { "sources": ["arxiv","github"], "query": "time series transformer", "date_from": "2025-07-01" }
GET  /ingest/status/{job_id}
```

**Search & Feed**
```
POST /search
body: {
  "query": "graph neural networks", 
  "filters": {"has_code": true, "date_from": "2025-06-01"},
  "limit": 20, "use_vector": true
}

GET  /feed?days=7&limit=30&only_with_code=true
```

**Summarize & Classify**
```
POST /summarize   # TL;DR for id/raw text (optionally PEFT-backed)
POST /classify    # taxonomy tags for id/raw text
```

**RAG**
```
POST /rag/query
body: { "question": "How does TFT compare to N-BEATS on electricity?", "top_k": 5, "return_sources": true }
```

---

## UI sketch
- **Feed**: ranked cards (TL;DR, tags, code link, save/export).  
- **Chat (RAG)**: grounded Q&A with citations.  
- **Trends**: topic/time charts.  
- **Compare: Custom vs UDR**: same prompt → two columns (our pipeline vs UDR).

---

## NVIDIA UDR (experimental)
Add an **optional** container `udr` later and a tab in UI.  
**Why?** Compare our handcrafted pipeline with an agentic framework, highlight trade‑offs (control vs speed, PEFT vs no-finetune). UDR is not required to run the MVP.

---

## Roadmap
- [x] Repo skeleton, Docker scaffolding (API, UI, Postgres, Qdrant)
- [ ] Ingest MVP (arXiv + GitHub) → Postgres, text → Qdrant
- [ ] RAG endpoint with citations, Streamlit Chat
- [ ] Feed ranking (novelty/has_code/profile match), trends
- [ ] PEFT for TL;DR & taxonomy (optional)
- [ ] Ray for parallel ingest/vectorization (optional)
- [ ] UDR comparison tab + container (optional)
- [ ] Weekly digest export (CSV/Markdown/Telegram)

---

## Tech choices
- **Embeddings**: sentence‑transformers / E5 family (configurable)
- **LLM**: any provider via adapters; PEFT via LoRA when needed
- **Storage**: Postgres for metadata; Qdrant for vectors
- **Orchestration**: simple scheduler; Ray optional for parallel pipelines
- **Metrics**: manual accept/reject labels; compare Custom vs UDR outputs

---

## Config
`configs/.env.example` (sample keys):
```
API_HOST=0.0.0.0
API_PORT=8000
DB_URL=postgresql+psycopg2://radar:radar@postgres:5432/radar
QDRANT_URL=http://qdrant:6333
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
LLM_PROVIDER=openai|hf|local
UDR_URL=http://udr:8001   # optional
```

---

## License
This project is released under the **MIT License**.
