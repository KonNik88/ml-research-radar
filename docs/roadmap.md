# Roadmap

## Purpose

This roadmap describes the current implementation stage of ML Research Radar and the next planned stages.

The roadmap is intentionally incremental.

The project prefers closing stable vertical slices over expanding feature surface too early.

---

## 1. Completed / Current Stage

## 1.1 Canonical paper corpus foundation

Completed:

- source normalization layer
- canonical reconciliation layer
- paper-centric canonical corpus
- provenance-preserving merge
- arXiv backbone corpus
- aligned enrichment from:
  - OpenAlex
  - Semantic Scholar
  - Crossref
- conservative paper identity resolution
- source-level vs canonical-level identity separation

Status:

- done

Current stable paper sources:

- `arxiv`
- `openalex_alignment`
- `semantic_scholar_alignment`
- `crossref_alignment`

Current operational paper source of truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

Important principle:

The canonical JSONL corpus remains the paper-level source of truth.

---

## 1.2 Retrieval foundation

Completed:

- lexical retrieval
- dense retrieval
- hybrid retrieval
- retrieval artifacts build pipeline
- ranking layer
- retrieval evaluation utilities
- retrieval validation checks
- file-backend retrieval runtime

Status:

- done

Current retrieval build:

- corpus document count: 30008
- embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- retrieval artifacts are derived from the canonical paper corpus

---

## 1.3 Audit / diagnostics / evaluation layer

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

Status:

- done

---

## 1.4 Storage-backed core v1

Completed:

- Postgres infrastructure
- Qdrant infrastructure placeholder
- SQL schema for canonical serving tables
- export to Postgres
- Postgres document store
- DB-backed `/documents`
- dual-backend runtime foundation

Status:

- done

Important principle:

Postgres is a materialized serving layer.

The canonical JSONL corpus remains the operational source of truth.

---

## 1.5 DB-backed `/search` v1

Completed:

- DB backend `/search`
- lexical search only in DB backend v1
- explicit rejection of `dense` / `hybrid` in DB backend
- integration tests for DB search path
- preservation of existing file retrieval path

Status:

- done

Important principle:

File backend is retrieval-first.

DB backend is browse/filter + lexical search v1.

Dense/hybrid parity in DB backend is not required at this stage.

---

## 1.6 Backend-aware cleanup

Completed:

- backend-aware runtime snapshot
- backend-aware health semantics
- backend-aware reload semantics
- file-only vs db-only integration test split
- API/runtime contract cleanup
- documentation sync for current backend model

Status:

- done

---

## 1.7 Papers with Code rollback and source viability gate

Completed:

- Papers with Code live integration was evaluated and blocked
- PWC-specific active integration was removed from stable source paths
- active stable source core returned to four paper sources
- source viability checklist introduced
- source viability config introduced
- source viability validation script introduced
- candidate sources checked before integration work

Status:

- done

Current viability outcome:

- `github`: viable artifact source candidate
- `huggingface_hub`: viable artifact source candidate
- `acl_anthology`: viable paper source candidate
- `openreview`: viable paper source candidate
- `pubmed`: viable paper/domain source candidate
- `biorxiv`: viable paper/domain source candidate
- `medrxiv`: viable paper/domain source candidate
- `paperswithcode`: blocked / archived live source

Key lesson:

Viability first, integration later.

---

## 1.8 Green four-source baseline

Completed:

- reconcile after PWC rollback
- retrieval checks
- postpass audit
- known issues snapshot
- Postgres export
- DB smoke
- refresh Definition of Done

Status:

- done

Current baseline:

- canonical documents: 30008
- multi-source canonical documents: 5893
- active stable paper sources: 4
- DB export validated
- DoD passed

---

## 1.9 Artifact Layer v1

Completed:

- internal artifact URL extraction from existing canonical/source documents
- URL normalization
- artifact classification
- `artifact_entities_latest.jsonl`
- `artifact_links_latest.jsonl`
- artifact quality report
- separate SQL schema for artifact entities, observations and trusted paper-artifact links
- Postgres artifact export
- artifact DB smoke check
- artifact checks in refresh Definition of Done
- refresh pipeline artifact stages
- DB-backed artifact API:
  - `GET /artifacts`
  - `GET /documents/{canonical_id}/artifacts`
  - `GET /documents` trusted artifact filters
- integration tests for artifact API and document artifact filters

Status:

- done

Current artifact baseline:

```text
artifact_entities = 491
artifact_observations = 1646
paper_artifact_links = 492
linked_canonical_documents = 451
linked_artifact_entities = 482
```

Current provider distribution:

```text
generic   196
figshare  113
github    113
zenodo     32
youtube    28
bitbucket   9
```

Important principle:

Artifact Layer v1 is a separate evidence/materialization plane.

It does not modify canonical paper truth.

---

## 1.10 GitHub Artifact Enrichment v1

Completed:

- snapshot enrichment over existing GitHub `artifact_entities`
- default input from:

```text
data/enriched/artifact_links/artifact_entities_latest.jsonl
```

- GitHub REST API fetch for repository metadata
- timestamped + latest enrichment outputs
- enrichment report JSON/Markdown
- optional GitHub metadata merge in artifact Postgres export
- enriched GitHub metadata exposed through existing DB artifact API
- soft integration test for GitHub enrichment API exposure

Status:

- done

Current GitHub enrichment baseline:

```text
github_entities_total = 113
requested_count = 113
processed_count = 113
found_count = 110
not_found_count = 3
forbidden_count = 0
rate_limited_count = 0
error_count = 0
ok = true
```

Latest export baseline after GitHub metadata merge:

```text
artifact_entities_db_count = 491
artifact_observations_db_count = 1646
paper_artifact_links_db_count = 492
github_metadata_rows_count = 113
github_metadata_found_count = 110
github_metadata_applied_count = 113
github_metadata_found_applied_count = 110
github_metadata_not_found_applied_count = 3
github_metadata_missing_entity_count = 0
```

Enriched fields include:

- `description`
- `license`
- `stars`
- `forks`
- `topics`
- `fetched_at`
- `created_at`
- `updated_at`
- `metadata.github.status`
- `metadata.github.language`
- `metadata.github.watchers`
- `metadata.github.open_issues`
- `metadata.github.default_branch`
- `metadata.github.archived`
- `metadata.github.pushed_at`

Important principles:

- GitHub is an artifact enrichment source, not a paper source.
- GitHub enrichment does not alter canonical paper truth.
- `not_found` repositories are preserved as historical artifact evidence.
- archived repositories remain valid found artifacts.
- GitHub enrichment is not required by base `--require-artifacts` DoD because GitHub API is a live external dependency.

---

## 1.11 GitHub Artifact Enrichment operational hardening

Completed:

- standalone GitHub enrichment validation script
- strict validation report for GitHub artifact metadata
- optional GitHub enrichment checks in refresh DoD
- optional GitHub enrichment stages in refresh pipeline dry-run
- separation of `--include-github-enrichment` and `--require-github-enrichment`
- preservation of base `--require-artifacts` behavior without requiring live GitHub API

Status:

- done

Current validation baseline:

```text
github_entities_count = 113
metadata_rows_count = 113
found_count = 110
not_found_count = 3
forbidden_count = 0
rate_limited_count = 0
error_count = 0
duplicate_artifact_id_count = 0
unknown_artifact_id_count = 0
strict = true
ok = true
```

DoD modes:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-github-enrichment
```

Pipeline dry-run modes:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts --include-github-enrichment
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts --include-github-enrichment --require-github-enrichment
```

Important principle:

GitHub enrichment is operationally validated but remains optional because GitHub API is an external live dependency.

---

## 2. Current System State

The project is currently at this point:

- canonical paper corpus is stable enough for iterative growth
- retrieval works in file backend
- DB serving works for browse/filter and lexical search v1
- tests are green in both backend modes
- validation and DoD are operational
- source viability gate exists
- Papers with Code live source is blocked/archived
- Artifact Layer v1 is operational
- GitHub Artifact Enrichment v1 is operational
- GitHub enrichment has standalone strict validation
- GitHub enrichment can be required in DoD with an explicit optional flag
- refresh pipeline can include GitHub enrichment stages in dry-run/planned mode
- enriched GitHub repository metadata is visible through the DB artifact API
- canonical paper truth remains isolated from artifact enrichment

Current closed vertical slice:

```text
Artifact Layer v1
→ GitHub Artifact Enrichment v1
→ GitHub enrichment validation
→ optional GitHub DoD gate
→ optional refresh pipeline GitHub stages
→ Postgres artifact materialization
→ DB artifact API exposure
→ integration tests
→ DoD --require-artifacts green
→ DoD --require-artifacts --require-github-enrichment green
```

---

## 3. Next Stage: Artifact API enriched filters / next artifact source

The next stage should still remain close to the artifact/enrichment plane unless there is a deliberate decision to start a new paper-source vertical slice.

Do not jump immediately to RAG/full-text or broad product layers before the artifact enrichment and serving line remains stable.

---

## 3.1 Artifact API enriched filters

Planned:

- add useful filters over enriched GitHub artifact metadata
- expose repository state without changing canonical paper truth
- keep artifact filters DB-backed and deterministic

Candidate filters:

```text
min_stars
language
license
archived
github_status
has_github_metadata
```

Candidate sort modes:

```text
stars_desc
forks_desc
updated_desc
pushed_desc
```

Example target queries:

```http
GET /artifacts?provider=github&min_stars=100&language=Python&sort_by=stars_desc
GET /artifacts?provider=github&github_status=not_found
GET /artifacts?provider=github&archived=false
```

Status:

- planned

Important principle:

Repository popularity or activity metadata must remain artifact metadata. It must not become canonical paper quality or identity truth.

---

## 3.2 Hugging Face Hub enrichment v1

Planned:

- enrich extracted Hugging Face model/dataset/space URLs when present
- fetch Hub metadata through API or Python client
- preserve models/datasets/spaces as artifact entities
- do not treat Hugging Face Hub as a paper source

Possible fields:

- model id
- dataset id
- space id
- tags
- downloads
- likes
- pipeline tag
- license
- library name
- card metadata
- created_at
- last modified

Status:

- planned

Note:

The current extraction baseline did not produce Hugging Face entities, so this stage may require either future corpus expansion, source updates, or extraction-rule improvements before enrichment is meaningful.

---

## 3.3 Figshare normalization hardening

Planned:

- normalize Figshare artifacts by numeric article id
- reduce duplicate Figshare entities that share the same article id but differ by URL path
- preserve evidence provenance while improving artifact entity deduplication

Status:

- planned

---

## 4. New paper sources

New paper sources should be integrated only after viability checks and candidate validation.

The source onboarding order should remain:

```text
source viability
→ real-data smoke
→ source contract
→ ingestor/alignment
→ normalized snapshot
→ source audit
→ candidate reconcile impact check
→ export
→ validation
→ stable integration only if safe
```

---

## 4.1 First new paper source: ACL Anthology

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

Status:

- planned

---

## 4.2 OpenReview candidate source

Planned:

- ingest OpenReview papers by explicit venue/year scope
- start with selected ML venues
- use API v2 / Python client where appropriate
- preserve OpenReview identifiers
- avoid mixing reviews/decisions into core paper truth prematurely

Status:

- planned

---

## 4.3 Biomedical/domain sources

Planned later:

- PubMed
- bioRxiv
- medRxiv

Purpose:

- biomedical/domain expansion
- possible ML-for-biology / ML-for-medicine coverage
- separate domain-specific corpus slices

Status:

- later

---

## 5. Medium-Scale Corpus Expansion

Medium-scale corpus expansion remains important, but it should follow the artifact layer foundation and artifact enrichment stabilization.

Target direction:

- significantly larger but still manageable working corpus
- approximately 50k+ canonical papers for the next growth stage
- recent-balanced ML/AI slice
- incremental growth, not immediate maximal crawl

Possible target slice:

- years: 2020–2026
- categories:
  - `cs.LG`
  - `cs.AI`
  - `cs.CL`
  - `cs.CV`
  - `stat.ML`
  - `cs.IR`
  - `cs.NE`
  - `cs.RO`
  - `eess.AS`
  - `eess.IV`

Planned order:

1. define target corpus slice
2. expand arXiv backbone
3. run aligned enrichment over DOI-covered subset
4. rebuild canonical corpus
5. export refreshed corpus to Postgres
6. extract / validate artifacts
7. optionally enrich artifacts
8. rebuild retrieval artifacts
9. run audit / evaluation / performance checks
10. compare retrieval quality against current baseline

Status:

- planned

---

## 6. Search Hardening

Planned:

- improve SQL search quality
- improve retrieval validation queries
- reduce gap between DB lexical search and file retrieval ergonomics
- handle modern ML query failures
- improve ambiguous query diagnostics

Possible directions:

- trigram improvements
- `tsvector` / GIN
- more explicit lexical scoring
- query groups:
  - modern ML
  - ambiguous terms
  - historical topics
  - metadata-heavy queries
  - regression guards
- reranking experiments

Status:

- planned

---

## 7. Vector Serving Integration

Planned:

- integrate vector-serving path
- move toward serving-time dense retrieval
- prepare for future hybrid serving

Possible directions:

- Qdrant-backed serving
- hybrid SQL + vector candidate generation
- serving-time dense search
- DB metadata filters + vector candidates + ranker

Status:

- planned

Important principle:

Dense/hybrid serving should likely be implemented through a vector-serving layer, not by forcing dense retrieval into the current Postgres DB backend.

---

## 8. Reference / Provenance Endpoints

Planned:

- `/documents/{id}/sources`
- `/documents/{id}/references`
- source drilldown
- merge inspection utilities
- paper-artifact link drilldown

Status:

- planned

---

## 9. Later Product Layers

These are intentionally postponed until corpus, artifact, and serving foundations are stronger.

## 9.1 Full-text and chunking

Planned:

- full-text extraction
- chunk storage
- chunk-level retrieval

## 9.2 Structured extraction

Planned:

- NER / entity extraction
- richer paper metadata derivation
- structured research signals

## 9.3 LLM / RAG layer

Planned:

- summaries
- retrieval-augmented question answering
- citation-aware generation

## 9.4 Graph / analytics layer

Planned:

- reference graph
- artifact graph
- topic graph
- trend analytics
- related-paper surfaces

## 9.5 Product surfaces

Planned:

- search UI
- topic dashboards
- paper pages
- artifact pages
- repository/model/dataset pages
- trend/radar views

---

## 10. Explicit Non-Goals for the Current Stage

Not part of the immediate next step:

- full-text pipeline
- DB-native dense search parity
- DB-native hybrid parity
- LLM summaries
- RAG serving
- large-scale graph product layer
- automatic integration of all viable sources
- GitHub/Hugging Face as paper sources
- artifact evidence modifying canonical paper identity
- ranking papers by GitHub stars as a canonical-quality signal

The immediate next stage is artifact API enriched filtering and/or the next artifact-source hardening step, not another paper-truth source by default.

---

## 11. Guiding Principle

The roadmap is intentionally staged:

1. stabilize canonical paper core
2. stabilize serving and validation
3. add source viability gate
4. add separate artifact/entity data plane
5. enrich artifacts through APIs
6. add new paper/domain sources carefully
7. expand corpus
8. harden search
9. add vector serving
10. add richer product layers

This ordering is deliberate and should be preserved.

The key engineering rule is:

Viability first, candidate integration second, stable integration last.
