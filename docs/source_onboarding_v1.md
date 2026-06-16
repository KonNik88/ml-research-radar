# ML Research Radar — Source Onboarding v1

## Purpose

This document defines the safe, repeatable process for adding a new data source to ML Research Radar.

It complements `docs/source_matrix.md`.

- `source_matrix.md` answers: **what sources exist, what plane they belong to, what they contribute, and how much they are trusted.**
- `source_onboarding_v1.md` answers: **how a new source moves from idea → viability → candidate integration → validated stable integration.**

### Configuration roles

The source-related configuration files have different responsibilities:

- `configs/sources.yaml` defines arXiv ingestion/backfill profiles and related ingestion defaults. Its `sources.enabled` list is not the authoritative registry of accepted canonical paper sources.
- `configs/source_viability.yaml` stores viability, onboarding-state, provider-policy, and current evidence metadata for candidate and operational sources. It does not directly select reconcile inputs.
- `docs/source_matrix.md` is the authoritative human-readable current source landscape.
- Actual canonical participation is determined by explicit normalized inputs, reconcile/promotion decisions, and accepted canonical evidence.

Persisted source-family names such as `openalex`, `semantic_scholar`, and `crossref` may differ from pipeline-role labels such as `openalex_alignment`, `semantic_scholar_alignment`, and `crossref_alignment`. This distinction is intentional and must not be changed through bulk renaming.

ML Research Radar is a paper-centric canonical corpus platform, but not every source is a paper source. The project explicitly separates:

1. paper sources
2. artifact sources
3. signal sources
4. future full-text/chunk sources

This separation prevents repositories, models, datasets, demos, reviews, trending signals, and full-text chunks from being accidentally treated as bibliographic paper truth.

---

## 1. Core invariants

### 1.1 Paper truth remains canonical JSONL

The operational paper-level source of truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

Postgres, retrieval artifacts, artifact tables, API views, and future vector/full-text layers are materializations derived from canonical truth.

### 1.2 Source-level rows are observations

Every external source contributes observations.

A source row is not automatically paper truth.

Correct flow:

```text
raw/source record
→ normalized source-level document or artifact observation
→ candidate validation
→ optional canonical/materialized integration
```

### 1.3 Plane determines integration semantics

A source must be assigned to one primary plane before implementation.

| Plane | Examples | Can change canonical paper truth? | Main output |
|---|---|---:|---|
| paper | arXiv, OpenAlex, Semantic Scholar, Crossref, ACL Anthology, OpenReview, PubMed, bioRxiv, medRxiv | yes, after reconcile validation | `data/normalized/<source>/documents.<ts>.jsonl` |
| artifact | GitHub, Hugging Face Hub, Figshare, Zenodo, Papers with Code offline | no | `artifact_entities`, `artifact_observations`, `paper_artifact_links`, provider metadata |
| signal | trending papers, GitHub trending, social/news signals | no | ranking/discovery signals, reports, optional feature tables |
| full-text/chunk | PDFs, parsed paper text, sections, chunks | no direct bibliographic truth | full-text documents, sections, chunks, embeddings |

### 1.4 Viability first, integration later

No source should be added to stable ingestion, reconcile, export, refresh, or DoD until it passes a viability check and a real-data smoke test.

### 1.5 Candidate first, promotion later

Any source that can affect canonical paper truth must first be integrated as a candidate source.

Never write unvalidated source output directly into the stable canonical path.

Correct pattern:

```text
source viability
→ real-data smoke
→ source contract
→ candidate ingestor/alignment
→ normalized snapshot
→ source audit
→ candidate reconcile impact check
→ export/materialization check
→ validation/DoD
→ stable integration only if safe
```

---

## 2. Source onboarding states

Every source should move through explicit states.

| State | Meaning | Stable pipeline access |
|---|---|---:|
| proposed | source is listed as a possible future source | no |
| viable_candidate | viability checks pass on real data | no |
| candidate_ingest | ingestor/enricher exists, outputs candidate snapshots | no |
| candidate_validated | candidate output passes audits and impact checks | limited / explicit candidate runs only |
| stable | source is allowed in stable refresh path | yes |
| blocked | source is not usable in current form | no |
| archived_only | source may be used only from offline/historical dumps | no live refresh |

---

## 3. Required source contract

Before writing a stable ingestor or enrichment step, define the following contract.

### 3.1 Identity contract

For each source, specify primary and fallback identifiers.

Examples:

| Source | Primary identity | Fallback identity |
|---|---|---|
| arXiv | arXiv id | DOI, title+year |
| OpenAlex | DOI / OpenAlex id | title+year |
| Semantic Scholar | DOI / arXiv id / CorpusId | title+year |
| Crossref | DOI | title+year |
| ACL Anthology | ACL id / DOI | title+venue+year |
| OpenReview | forum id / DOI / arXiv id | title+venue+year |
| PubMed | PMID / DOI | title+journal+year |
| bioRxiv/medRxiv | DOI | title+date |
| GitHub | normalized repository URL / owner/repo | redirected repo URL |
| Hugging Face Hub | repo type + namespace/name | normalized Hub URL |

### 3.2 Plane and truth contract

For every source, explicitly state:

```text
source_type: paper | artifact | signal | fulltext
can_affect_canonical_paper_truth: true | false
can_create_artifact_entities: true | false
can_create_paper_artifact_links: true | false
can_affect_ranking: true | false
```

### 3.3 Output contract

The source must declare expected outputs.

Paper source output:

```text
data/raw/<source>/<run_ts>/...
data/normalized/<source>/documents.<run_ts>.jsonl
artifacts/reports/<source>_ingest_latest.json
artifacts/reports/<source>_ingest_latest.md
```

Artifact source output:

```text
data/enriched/<provider>_artifacts/<provider>_artifact_metadata.<run_ts>.jsonl
artifacts/reports/validation/<provider>_artifact_enrichment_latest.json
artifacts/reports/validation/<provider>_artifact_enrichment_latest.md
```

Signal source output:

```text
artifacts/reports/signals/<source>_<run_ts>.json
optional materialized signal table later
```

Full-text/chunk source output:

```text
data/fulltext/<source>/<run_ts>/...
data/chunks/<source>/<run_ts>/...
artifacts/embeddings/chunks/<build_id>/...
```

---

## 4. Mandatory gates

### Gate 1 — viability check

The source must be represented in:

```text
configs/source_viability.yaml
```

The check must answer:

- is the source reachable?
- does it return usable machine-readable data?
- can we fetch 5–20 real records?
- are stable identifiers available?
- is authentication optional or required?
- are rate limits acceptable?
- is the source paper/artifact/signal/fulltext?
- is live refresh viable, or only offline backfill?

### Gate 2 — real-data smoke

A smoke run must produce a small but real sample.

Minimum expectations:

- successful request or local parse
- at least one usable record where applicable
- identifiers inspected manually
- schema shape understood
- failure modes documented

### Gate 3 — source contract

The source must have a short integration note or section in the relevant doc describing:

- plane
- identity keys
- trusted fields
- weak/not trusted fields
- output paths
- candidate/stable status
- non-goals

### Gate 4 — normalized/candidate output

For paper sources, the output must conform to the project `Document` / normalized source-level model.

For artifact sources, the output must conform to provider artifact metadata and/or artifact entity semantics.

### Gate 5 — quality audit

A source-specific audit should check:

- row count
- required identifiers
- title/abstract coverage for paper sources
- DOI/arXiv/PMID/etc. coverage where relevant
- URL normalization for artifact sources
- duplicate IDs
- malformed records
- known API failure rows
- sample records

### Gate 6 — candidate reconcile impact check

Required for any source that can affect paper truth.

The candidate impact check must compare baseline vs candidate:

- canonical doc count
- multisource doc count
- DOI/arXiv/PMID/ACL/OpenReview identifier impact
- source_count / unique_source_count behavior
- title/abstract/venue/publication_type changes
- suspicious merges/splits
- provenance consistency
- sample changed papers

### Gate 7 — materialization/export check

If the source affects serving layers, verify:

- Postgres export works
- DB smoke works
- retrieval rebuild works if canonical changed
- artifact export works if artifacts changed
- API endpoints still work

### Gate 8 — DoD

Stable promotion requires relevant DoD checks.

Examples:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-github-enrichment
```

New source-specific required checks should be added only after the source becomes operationally stable.

---

## 5. Paper source onboarding template

Use this for OpenReview, PubMed, bioRxiv, medRxiv, and future paper sources. ACL Anthology has already completed this lifecycle and is now an active stable source; its integration remains the reference example.

```text
1. Add/update configs/source_viability.yaml entry.
2. Run source viability check.
3. Create docs/<source>_integration_v1.md or add a source-specific section to source docs.
4. Implement raw/smoke fetch or parser.
5. Implement normalized output to data/normalized/<source>/documents.<ts>.jsonl.
6. Add source audit report.
7. Run candidate reconcile with explicit source input.
8. Compare candidate vs baseline.
9. Run canonical provenance consistency check.
10. Export to Postgres in candidate/stable mode only after promotion decision.
11. Rebuild retrieval only after canonical promotion.
12. Update source_matrix.md and roadmap.md.
13. Commit as one vertical slice.
```

Important: paper sources are allowed to contribute to canonical paper truth only through reconcile and only after candidate validation.

---

## 6. Artifact source onboarding template

Use this for Hugging Face Hub, future GitHub expansion, offline Papers with Code backfill, model hubs, dataset repositories, and similar sources.

```text
1. Confirm source is artifact plane, not paper plane.
2. Add/update configs/source_viability.yaml entry.
3. Run source viability check.
4. Confirm whether artifact URLs/entities already exist in artifact_entities.
5. If not, add discovery/extraction rules first.
6. Run artifact extraction.
7. Run artifact quality gate.
8. Implement provider enrichment script only when provider entities exist.
9. Write provider metadata snapshot under data/enriched/<provider>_artifacts/.
10. Add validation script for provider metadata.
11. Merge metadata into artifact_entities during export if appropriate.
12. Add API exposure/filters only after metadata is materialized.
13. Keep enrichment optional if it depends on a live external API.
```

Important: artifact metadata must not modify canonical paper title, abstract, authors, venue, publisher, publication type, citation counts, or paper identity.

---

## 7. Signal source onboarding template

Use this later for trending, alerts, ranking hints, and discovery surfaces.

```text
1. Define signal semantics: discovery, ranking, alerting, or prioritization.
2. Confirm signal cannot modify canonical paper truth.
3. Define signal freshness and decay policy.
4. Store signal observations separately.
5. Add diagnostics and provenance.
6. Use signals only in explicit ranking/discovery layers.
```

---

## 8. Full-text/chunk source onboarding template

Full text is a separate derived layer, not a paper metadata source.

```text
1. Start from canonical papers with stable IDs.
2. Define allowed full-text source: arXiv PDF, publisher OA, PubMed Central, etc.
3. Store raw full text/PDF separately.
4. Parse sections and references into derived files.
5. Chunk text with deterministic chunk IDs.
6. Build chunk embeddings.
7. Add retrieval/RAG evaluation before product use.
8. Never let parsed full text override bibliographic paper truth without explicit metadata extraction validation.
```

---

## 9. Recommended onboarding order

Current accepted source state:

```text
stable paper sources:
- arXiv
- OpenAlex alignment
- Semantic Scholar alignment
- Crossref alignment
- ACL Anthology

operational optional artifact providers:
- GitHub
- Hugging Face Hub
```

Recommended future onboarding order is selected by product and research value rather than by the historical ACL sequence:

```text
1. Keep the current stable source set reproducible and auditable.
2. Choose one explicit next paper/domain source only after a fresh viability and overlap review.
3. OpenReview is the leading ML-conference candidate when conference coverage becomes the selected goal.
4. PubMed / bioRxiv / medRxiv remain later biomedical-domain expansion candidates.
5. Refresh GitHub/Hugging Face enrichment when a selected slice depends on fresher artifact evidence.
6. Add full-text/chunk/RAG sources only after chunk contracts and retrieval evaluation are defined.
7. Add Airflow orchestration only after the underlying source scripts and gates are stable and recurring.
```

ACL Anthology should no longer appear as a future candidate in current-state planning. Its historical candidate lifecycle is documented in `docs/acl_anthology_integration_v1.md`.

---

## 10. Airflow and orchestration policy

Airflow should not replace source scripts.

Airflow should orchestrate scripts that are already stable, idempotent, and validated.

Do not start with Airflow for a new source.

Correct progression:

```text
manual script
→ repeatable script with reports
→ validation gates
→ stable operational runbook
→ Airflow DAG
```

Airflow is appropriate when:

- commands are stable
- inputs/outputs are explicit
- reruns are idempotent
- reports and DoD gates exist
- failure recovery is clear
- volume/storage strategy is known

---

## 11. Storage policy during source onboarding

Small source smoke tests and candidate integrations can run before Docker volume migration.

Large corpus expansion, full-text collection, vector store growth, and massive artifact enrichment should not begin until storage is checked.

Recommended before large growth:

```text
1. Check free space on OS disk and data disk.
2. Create Postgres backup via pg_dump.
3. Confirm Docker volume/bind mount strategy.
4. Move Postgres/Qdrant storage off OS disk before million-scale corpus or full-text ingestion.
```

Practical rule:

- for smoke/candidate source work: volume migration can wait;
- for 50k+ corpus, full-text, Qdrant embeddings, or million-scale data: migrate first.

---

## 12. Current source status snapshot

Stable paper sources:

```text
arxiv
openalex_alignment
semantic_scholar_alignment
crossref_alignment
```

Operational artifact layer:

```text
internal artifact extraction
GitHub Artifact Enrichment v1
```

Viable candidate artifact sources:

```text
github
huggingface_hub
```

Viable candidate paper/domain sources:

```text
acl_anthology
openreview
pubmed
biorxiv
medrxiv
```

Blocked/archived:

```text
paperswithcode live integration
```

---

## 13. Non-goals for immediate onboarding

Do not do these during the first source onboarding step:

- integrate all viable sources at once
- start with Airflow before scripts are stable
- treat artifact metadata as paper truth
- add full-text/RAG before retrieval evaluation is stronger
- write new source output directly into canonical latest
- launch million-scale ingestion before storage is ready
- add source-specific logic directly into API without materialization contracts
