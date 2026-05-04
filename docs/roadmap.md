# Roadmap

## Purpose

This roadmap describes the current implementation stage of ML Research Radar and the next planned stages.

The roadmap is intentionally incremental. The project prefers closing stable vertical slices over expanding feature surface too early.

---

## 1. Completed / Current Stage

### 1.1 Canonical paper corpus foundation

Completed:

- source normalization layer
- canonical reconciliation layer
- paper-centric canonical corpus
- provenance-preserving merge
- arXiv-backed medium-scale corpus
- aligned enrichment from:
  - OpenAlex
  - Semantic Scholar
  - Crossref
- conservative paper identity resolution
- DOI normalization hardening
- DOI conflict guard: DOI must not collapse different arXiv base IDs
- source-level vs canonical-level identity separation

Status: done

Current stable paper sources:

- `arxiv`
- `openalex_alignment`
- `semantic_scholar_alignment`
- `crossref_alignment`

Current operational paper source of truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

Current green 60k baseline:

```text
canonical_doc_count = 60000
canonical_multisource_docs = 9192
DoD passed = true
```

Important principle: canonical JSONL remains the paper-level source of truth. Postgres, retrieval artifacts, artifact tables and APIs are materializations over that truth.

---

### 1.2 Retrieval foundation

Completed:

- lexical retrieval
- dense retrieval
- hybrid retrieval
- retrieval artifacts build pipeline
- ranking layer
- retrieval evaluation utilities
- retrieval validation checks
- file-backend retrieval runtime

Status: done

Current retrieval build:

```text
build_id = 20260502T153402Z
corpus_doc_count = 60000
embedding_model = sentence-transformers/all-MiniLM-L6-v2
```

Retrieval artifacts are derived from the canonical paper corpus and are not source of truth.

---

### 1.3 Audit / diagnostics / evaluation layer

Completed:

- corpus audit
- source corpus audit
- overlap diagnostics
- source-to-canonical comparison
- source metadata diagnostics
- multisource inspection
- retrieval checks
- postpass audit
- known issues snapshot
- refresh Definition of Done
- provenance consistency checks

Status: done

Current strict DoD baseline:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-github-enrichment --require-huggingface-enrichment
```

Expected result:

```text
dod_passed = true
required_failed_count = 0
```

---

### 1.4 Storage-backed core v1

Completed:

- Postgres infrastructure
- Qdrant infrastructure placeholder
- SQL schema for canonical serving tables
- export to Postgres
- Postgres document store
- DB-backed `/documents`
- dual-backend runtime foundation
- `export_postgres_v1 --replace` hardening
- source lookup index folded into `store/sql/02_indexes.sql`

Status: done

Current Postgres paper DB baseline:

```text
canonical_documents = 60000
source_documents = 69214
canonical_source_links = 87080
document_references = 709662
```

Important principle: Postgres is a materialized serving layer. The canonical JSONL corpus remains the operational source of truth.

---

### 1.5 DB-backed `/search` v1

Completed:

- DB backend `/search`
- lexical search only in DB backend v1
- explicit rejection of `dense` / `hybrid` in DB backend
- integration tests for DB search path
- preservation of existing file retrieval path

Status: done

Important principle: file backend is retrieval-first; DB backend is browse/filter + lexical search v1. Dense/hybrid parity in DB backend is not required at this stage.

---

### 1.6 Source viability gate

Completed:

- Papers with Code live integration was evaluated and blocked
- PWC-specific active integration was removed from stable source paths
- active stable source core returned to four paper sources
- source viability checklist introduced
- source viability config introduced
- source viability validation script introduced
- candidate sources checked before integration work

Status: done

Current viability outcome:

```text
github: operational artifact enrichment provider
huggingface_hub: operational artifact enrichment provider
acl_anthology: viable paper source candidate
openreview: viable paper source candidate
pubmed: viable domain paper source candidate
biorxiv: viable domain paper source candidate
medrxiv: viable domain paper source candidate
paperswithcode: blocked / archived live source
```

Key lesson: viability first, integration later.

---

### 1.7 Artifact Layer v1

Completed:

- internal artifact URL extraction from canonical/source documents
- URL normalization
- artifact classification
- `artifact_entities_latest.jsonl`
- `artifact_links_latest.jsonl`
- artifact quality report
- SQL schema for artifact entities, observations and trusted paper-artifact links
- Postgres artifact export
- artifact DB smoke check
- artifact checks in refresh Definition of Done
- refresh pipeline artifact stages
- DB-backed artifact API:
  - `GET /artifacts`
  - `GET /documents/{canonical_id}/artifacts`
  - `GET /documents` trusted artifact filters
- integration tests for artifact API and document artifact filters

Status: done

Current 60k artifact extraction baseline:

```text
raw artifact_entities_latest = 7173
artifact_observations = 37582
trusted paper_artifact_links = 7262
linked canonical docs = 6507
```

Current artifact DB baseline:

```text
artifact_entities = 7170
artifact_observations = 37582
paper_artifact_links = 7262
normalized_url_collisions = 3
```

Important principle: Artifact Layer v1 is a separate evidence/materialization plane. It does not modify canonical paper truth.

---

### 1.8 GitHub Artifact Enrichment v1

Completed:

- snapshot enrichment over extracted GitHub `artifact_entities`
- GitHub REST API fetch for repository metadata
- timestamped + latest enrichment outputs
- standalone strict validation report
- optional GitHub metadata merge in artifact Postgres export
- optional GitHub enrichment checks in refresh DoD
- optional GitHub enrichment stages in refresh pipeline
- enriched GitHub metadata exposed through existing DB artifact API
- DB artifact API supports GitHub-specific enriched filters

Status: done

Current 60k GitHub enrichment baseline:

```text
github_entities_count = 5796
metadata_rows_count = 5796
found_count = 5188
not_found_count = 608
forbidden_count = 0
rate_limited_count = 0
error_count = 0
duplicate_artifact_id_count = 0
unknown_artifact_id_count = 0
ok = true
```

Important principles:

- GitHub is an artifact enrichment source, not a paper source.
- GitHub enrichment does not alter canonical paper truth.
- `not_found` repositories are preserved as historical artifact evidence.
- GitHub enrichment remains optional because GitHub API is a live external dependency.

---

### 1.9 Hugging Face Artifact Enrichment v1

Completed:

- extracted Hugging Face model/dataset/space entities enriched through Hub API
- provider-specific snapshot metadata written to:

```text
data/enriched/huggingface_artifacts/huggingface_artifact_metadata.<ts>.jsonl
data/enriched/huggingface_artifacts/huggingface_artifact_metadata_latest.jsonl
```

- standalone strict validation report:

```text
artifacts/reports/validation/huggingface_artifact_enrichment_check_latest.json
```

- HF metadata merge in `export_artifacts_postgres_v1.py`
- Postgres materialization into:
  - `artifact_entities.metadata.huggingface`
  - selected generic columns: `description`, `license`, `downloads`, `likes`, `tags`, `fetched_at`, `created_at`, `updated_at`
- optional HF checks in refresh DoD:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-github-enrichment --require-huggingface-enrichment
```

- optional HF stages in refresh pipeline:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts --include-huggingface-enrichment --require-huggingface-enrichment
```

Status: done

Current 60k Hugging Face enrichment baseline:

```text
huggingface_entities_count = 96
metadata_rows_count = 96
found_count = 73
forbidden_count = 2
skipped_invalid_external_id_count = 21
rate_limited_count = 0
error_count = 0
duplicate_artifact_id_count = 0
unknown_artifact_id_count = 0
strict = true
ok = true
```

Current DB check:

```text
hf_entities = 96
hf_metadata = 96
hf_found = 73
hf_downloads = 64
```

Important principles:

- Hugging Face is an artifact enrichment provider, not a paper source.
- `forbidden` rows are provider/access states and remain diagnostic.
- `skipped_invalid_external_id` rows are recognized extraction/noise states and remain diagnostic.
- Neither state should fail the core strict gate unless it becomes policy-relevant later.
- API-specific Hugging Face filters are postponed until after the next source/source-expansion slices.

---

## 2. Current System State

The project is currently at this point:

- canonical 60k arXiv-backed paper corpus is green
- four active paper/metadata sources are integrated: arXiv, OpenAlex, Semantic Scholar, Crossref
- retrieval artifacts are built and validated on 60k docs
- Postgres paper serving layer is green
- artifact extraction is green
- artifact DB materialization is green
- GitHub artifact enrichment is green and optional in DoD/pipeline
- Hugging Face artifact enrichment is green and optional in DoD/pipeline
- API currently exposes generic artifact browse/filter and GitHub enriched filters
- Hugging Face API-specific filters are intentionally postponed
- source viability gate exists
- Papers with Code live source remains blocked/archived
- canonical paper truth remains isolated from artifact enrichment

Current closed vertical slice:

```text
60k canonical corpus
→ retrieval artifacts
→ Postgres serving layer
→ Artifact Layer v1
→ GitHub Artifact Enrichment v1
→ Hugging Face Artifact Enrichment v1
→ artifact export / DB materialization
→ strict validation reports
→ optional provider-specific DoD gates
→ optional provider-specific refresh pipeline stages
```

---

## 3. Near-Term Roadmap

Recommended next order:

```text
1. Commit the current green 60k + artifact enrichment hardening slice.
2. Start the first new paper-source candidate slice: ACL Anthology.
3. Keep ACL candidate-only until source audit and candidate reconcile impact checks are green.
4. Then consider OpenReview as the next paper source.
5. Postpone PubMed/bioRxiv/medRxiv until a biomedical/domain expansion milestone is explicit.
6. Postpone Hugging Face-specific API filters until after the next source/source-expansion work.
```

---

## 3.1 First new paper source: ACL Anthology

Planned:

- ingest ACL Anthology metadata as candidate paper source
- parse bulk XML metadata
- normalize into `NormalizedDocument`
- run source quality audit
- run candidate reconcile impact check
- integrate into stable paper pipeline only after validation

Reason:

ACL Anthology is a good first new paper source because it is:

- structured
- domain-relevant for NLP/ML
- bulk-friendly
- relatively low API risk

Status: next

---

## 3.2 OpenReview candidate source

Planned:

- ingest OpenReview papers by explicit venue/year scope
- start with selected ML venues
- use API v2 / Python client where appropriate
- preserve OpenReview identifiers
- avoid mixing reviews/decisions into core paper truth prematurely

Status: planned after ACL candidate slice

---

## 3.3 Biomedical/domain sources

Planned later:

- PubMed
- bioRxiv
- medRxiv

Purpose:

- biomedical/domain expansion
- possible ML-for-biology / ML-for-medicine coverage
- separate domain-specific corpus slices

Status: later

---

## 4. Search / API / Product hardening

Planned after source/corpus hardening:

- improve SQL search quality
- improve retrieval validation queries
- reduce gap between DB lexical search and file retrieval ergonomics
- handle modern ML query failures
- add richer artifact provider filters when provider metadata stabilizes
- add document/source/reference drilldown endpoints

Hugging Face-specific API filters are intentionally postponed until after the next source/source-expansion slices to avoid repeatedly redesigning API contracts.

---

## 5. Vector Serving Integration

Planned:

- integrate vector-serving path
- move toward serving-time dense retrieval
- prepare for future hybrid serving

Possible directions:

- Qdrant-backed serving
- hybrid SQL + vector candidate generation
- serving-time dense search
- DB metadata filters + vector candidates + ranker

Status: planned

Important principle: dense/hybrid serving should likely be implemented through a vector-serving layer, not by forcing dense retrieval into the current Postgres DB backend.

---

## 6. Later Product Layers

These are intentionally postponed until corpus, artifact, and serving foundations are stronger.

### 6.1 Full-text and chunking

Planned:

- full-text extraction
- chunk storage
- chunk-level retrieval

### 6.2 Structured extraction

Planned:

- NER / entity extraction
- richer paper metadata derivation
- structured research signals

### 6.3 LLM / RAG layer

Planned:

- summaries
- retrieval-augmented question answering
- citation-aware generation

### 6.4 Graph / analytics layer

Planned:

- reference graph
- artifact graph
- topic graph
- trend analytics
- related-paper surfaces

### 6.5 Dataset release track

Planned:

- clean metadata dataset
- paper-artifact graph exports
- topic/cluster exports
- dataset cards
- Kaggle / Hugging Face dataset release track if useful

---

## 7. Explicit Non-Goals for the Current Stage

Not part of the immediate next step:

- full-text pipeline
- DB-native dense search parity
- DB-native hybrid parity
- LLM summaries
- RAG serving
- large-scale graph product layer
- automatic integration of all viable sources
- GitHub or Hugging Face as paper sources
- artifact evidence modifying canonical paper identity
- ranking papers by GitHub stars or Hugging Face downloads as canonical-quality signals
- provider-specific API filter redesign after every new provider

---

## 8. Guiding Principle

The roadmap is intentionally staged:

1. stabilize canonical paper core
2. stabilize serving and validation
3. add source viability gate
4. add separate artifact/entity data plane
5. enrich artifacts through APIs
6. add new paper/domain sources carefully
7. expand corpus
8. harden search/API
9. add vector serving
10. add richer product layers

The key engineering rule is:

```text
Viability first, candidate integration second, stable integration last.
```
