# Artifact Layer v1

## Purpose

This document defines the current Artifact Layer v1 of ML Research Radar.

The artifact layer stores external software, dataset, model, demo, video, repository and project-page artifacts related to canonical ML/AI research papers.

It is a separate data plane from the canonical paper corpus.

The canonical paper corpus remains the paper-level source of truth.

The artifact layer does **not** override bibliographic paper truth.

---

## Core architectural rule

ML Research Radar has two distinct truth layers:

```text
paper layer:
  source-level observations
  → normalized documents
  → reconcile
  → canonical paper corpus

artifact layer:
  canonical/source metadata
  → artifact evidence extraction
  → artifact entities
  → artifact observations
  → trusted paper-artifact links
```

The central paper entity is still:

```text
CanonicalDocument
```

The central artifact entity is:

```text
artifact_entities.artifact_id
```

The trusted connection between the two is:

```text
paper_artifact_links
```

---

## Source of truth model

### Paper truth

Current paper-level source of truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

This file remains the canonical paper corpus.

### Artifact extraction outputs

Current artifact extraction outputs:

```text
data/enriched/artifact_links/artifact_entities_latest.jsonl
data/enriched/artifact_links/artifact_links_latest.jsonl
```

These files are operational extraction artifacts derived from canonical/source metadata.

They are not paper truth.

### Artifact DB materialization

Current Postgres artifact tables:

```text
artifact_entities
artifact_observations
paper_artifact_links
```

These are materialized serving tables for artifact API and document filters.

---

## Key distinction: observations vs trusted links

The artifact layer intentionally separates broad evidence from trusted materialized links.

### `artifact_observations`

Broad evidence layer.

Contains extracted artifact-like URLs and relation guesses from canonical/source metadata.

It preserves:

- raw URL
- normalized URL
- provider
- artifact type
- source layer
- source name
- source document id
- canonical id
- source field
- evidence text
- relation type
- confidence
- extraction metadata

This table can contain untrusted or lower-confidence observations.

### `paper_artifact_links`

Trusted serving layer.

Contains deduplicated and trusted paper-artifact links.

One row represents:

```text
canonical_id + artifact_id + relation_type
```

Multiple observations supporting the same trusted link are preserved in:

```text
paper_artifact_links.metadata.evidence
paper_artifact_links.metadata.observation_ids
```

The top-level evidence fields are representative fields only.

---

## Current SQL invariant

The public/materialized trusted-link invariant is:

```sql
UNIQUE (canonical_id, artifact_id, relation_type)
```

This matches the export logic:

```text
one trusted link = one paper + one artifact + one relation type
```

Do not create separate `paper_artifact_links` rows only because evidence came from a different field or source.

Evidence multiplicity belongs in JSON metadata.

---

## Artifact entity types

Currently supported / expected artifact entity types:

```text
github_repository
gitlab_repository
bitbucket_repository
codeberg_repository
huggingface_model
huggingface_dataset
huggingface_space
kaggle_dataset
zenodo_artifact
figshare_artifact
youtube_video
generic_code_url
generic_dataset_url
generic_model_url
generic_artifact_url
```

Not all types are present in the current corpus.

Current v1 extraction found:

```text
bitbucket_repository
figshare_artifact
generic_artifact_url
generic_code_url
generic_dataset_url
generic_model_url
github_repository
youtube_video
zenodo_artifact
```

---

## Relation types

Current trusted relation types:

```text
code
dataset
demo
model
```

Possible future relation types:

```text
benchmark
project_page
supplementary_material
unknown
```

`unknown` observations should not be exported to trusted `paper_artifact_links`.

---

## Current providers

Current artifact providers:

```text
bitbucket
figshare
generic
github
youtube
zenodo
```

Future providers:

```text
gitlab
codeberg
huggingface
kaggle
openreview
publisher_supplementary
```

---

## Artifact extraction v1

Artifact Layer v1 currently uses internal extraction only.

It does not yet call GitHub API or Hugging Face Hub API.

Input layers:

```text
canonical documents
source documents
```

Primary input fields:

```text
abstract
comment
repo_url
code_links
dataset_links
model_links
external_urls
metadata
```

Excluded fields:

```text
pdf_url
landing_page_url
canonical_url
source_record_url
```

Reason: these fields often contain bibliographic or full-text URLs rather than artifact URLs.

---

## Extraction configuration

Main config:

```text
configs/artifact_extraction.yaml
```

The config fixes explicit source snapshots for reproducible extraction.

Current explicit source snapshots:

```yaml
source_files:
  arxiv: "data/normalized/arxiv/documents.20260404T161108Z.jsonl"
  openalex_alignment: "data/normalized/openalex_alignment/documents.20260412T162220Z.jsonl"
  semantic_scholar_alignment: "data/normalized/semantic_scholar_alignment/documents.20260412T162234Z.jsonl"
  crossref_alignment: "data/normalized/crossref_alignment/documents.20260412T162249Z.jsonl"
```

This is important because source directories can contain derivative snapshots such as `.updated.jsonl` or `.unchanged.jsonl`, which are not full stable snapshots.

---

## Extraction script

Main script:

```text
scripts/enrich/extract_artifact_links.py
```

Main command:

```bat
python -m scripts.enrich.extract_artifact_links
```

Outputs:

```text
data/enriched/artifact_links/artifact_entities_latest.jsonl
data/enriched/artifact_links/artifact_links_latest.jsonl
artifacts/reports/validation/artifact_links_quality_latest.json
artifacts/reports/validation/artifact_links_quality_latest.md
artifacts/reports/validation/history/artifact_links_quality_<ts>.json
artifacts/reports/validation/history/artifact_links_quality_<ts>.md
```

Notes:

- extraction output is broad evidence
- strict quality check determines whether extraction output is acceptable
- export applies trusted filtering before materializing `paper_artifact_links`

---

## Quality gate

Main script:

```text
scripts/validation/check_artifact_links_quality.py
```

Strict command:

```bat
python -m scripts.validation.check_artifact_links_quality --strict
```

Checks include:

```text
entities file exists
observations file exists
entities non-empty
observations non-empty
required fields present
entity ids unique
observation ids unique
observations reference known artifact entities
canonical_id_none_count == 0
invalid canonical refs == 0
technical noise == 0
generic_from_abstract == 0
unknown count within threshold
trusted observations count
trusted unique paper-artifact links count
bad generic domain observations counted
untrusted observations counted
```

The quality gate explicitly allows broad observations to include some untrusted rows.

Trusted serving rows are produced later through export filtering.

---

## SQL layer

Main SQL file:

```text
store/sql/03_artifact_layer.sql
```

Schema cleanup:

```text
store/sql/04_fix_paper_artifact_links_unique.sql
```

Tables:

```text
artifact_entities
artifact_observations
paper_artifact_links
```

### `artifact_entities`

Normalized external artifact objects.

Examples:

- GitHub repository
- Bitbucket repository
- Figshare article/dataset
- Zenodo record
- YouTube video
- generic code URL
- generic dataset URL

Important fields:

```text
artifact_id
artifact_type
provider
external_id
normalized_url
canonical_url
name
owner
title
description
license
stars
forks
downloads
likes
topics
tags
metadata
first_seen_at
last_seen_at
fetched_at
created_at
updated_at
```

Some enrichment fields are currently empty and reserved for future GitHub/Hugging Face enrichment.

### `artifact_observations`

Broad evidence observations.

Important fields:

```text
observation_id
artifact_id
artifact_type
provider
raw_url
normalized_url
source_layer
source_name
source_doc_id
canonical_id
source_field
evidence_text
relation_type
confidence
observed_at
metadata
```

### `paper_artifact_links`

Trusted paper-artifact links.

Important fields:

```text
link_id
canonical_id
artifact_id
relation_type
confidence
evidence_source
evidence_url
source_field
source_doc_id
metadata
created_at
updated_at
```

Invariant:

```text
canonical_id + artifact_id + relation_type
```

---

## Artifact export

Main script:

```text
scripts/export/export_artifacts_postgres_v1.py
```

Dry run:

```bat
python -m scripts.export.export_artifacts_postgres_v1 --dry-run
```

Replace/export:

```bat
python -m scripts.export.export_artifacts_postgres_v1 --replace
```

Export behavior:

```text
artifact_entities_latest.jsonl
  → artifact_entities

artifact_links_latest.jsonl
  → artifact_observations

trusted filtered observations
  → paper_artifact_links
```

Important behavior:

- deduplicates entities by normalized URL
- remaps observations when deduplication occurs
- exports broad observations to `artifact_observations`
- exports only trusted links to `paper_artifact_links`
- aggregates multiple observations into one trusted link row
- stores evidence list in `metadata.evidence`

---

## DB smoke check

Main script:

```text
scripts/export/test_artifact_db_read.py
```

Command:

```bat
python -m scripts.export.test_artifact_db_read
```

Checks:

```text
canonical_documents table exists
artifact_entities table exists
artifact_observations table exists
paper_artifact_links table exists
canonical_documents non-empty
artifact_entities non-empty
artifact_observations non-empty
paper_artifact_links non-empty
all paper_artifact_links join to canonical_documents and artifact_entities
provider distribution readable
relation distribution readable
sample joined links readable
```

---

## Current baseline

Current baseline after Artifact Layer v1 API/filter integration:

```text
canonical_documents_count = 30008
artifact_entities_count = 491
artifact_observations_count = 1646
paper_artifact_links_count = 492
linked_canonical_documents_count = 451
linked_artifact_entities_count = 482
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

Current trusted link relation distribution:

```text
code     237
dataset  158
demo      90
model      7
```

Current document filter counts:

```text
documents with any trusted artifact       = 451
documents with trusted code artifact      = 215
documents with trusted dataset artifact   = 154
documents with trusted GitHub artifact    = 111
documents with trusted GitHub code        = 111
documents without trusted artifacts       = 29557
```

Consistency check:

```text
451 + 29557 = 30008
```

---

## DoD integration

Artifact checks are integrated into the refresh Definition of Done.

Main script:

```text
scripts/update/check_refresh_definition_of_done.py
```

Default behavior:

```bat
python -m scripts.update.check_refresh_definition_of_done
```

Artifact checks are evaluated and reported, but not required.

Strict artifact mode:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts
```

In strict mode, the following checks are required:

```text
artifact_quality_exists
artifact_quality_ok
artifact_export_exists
artifact_export_ok
artifact_db_read_exists
artifact_db_read_ok
artifact_entities_db_non_empty
artifact_observations_db_non_empty
paper_artifact_links_db_non_empty
artifact_links_join_all_rows
artifact_export_vs_db_entities_match
artifact_export_vs_db_observations_match
artifact_export_vs_db_links_match
artifact_quality_vs_export_entities_match
artifact_quality_vs_export_observations_match
artifact_quality_vs_export_links_match
```

---

## Refresh pipeline integration

Main wrapper:

```text
scripts/update/run_refresh_pipeline_v1.py
```

Artifact stages are included only when:

```bat
--require-artifacts
```

Artifact-aware pipeline order:

```text
reconcile_candidate
→ candidate_provenance_audit
→ promote_candidate
→ export_postgres
→ extract_artifacts
→ artifact_quality_check
→ export_artifacts_postgres
→ artifact_db_smoke
→ rebuild_retrieval
→ retrieval_checks
→ postpass_audit
→ known_issues
→ dod_check
```

Dry run:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts
```

Dry run to artifact checkpoint:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts --stop-after artifact_db_smoke
```

Do not run full execute mode unless intentionally performing a refresh cycle.

---

## API integration

Artifact Layer v1 is exposed through the DB backend API.

Implemented endpoints:

```text
GET /artifacts
GET /documents/{canonical_id}/artifacts
GET /documents with trusted artifact filters
```

The artifact API is DB-only.

The file backend does not load artifact tables and does not provide artifact browse/filter support.

---

## Document filters

`GET /documents` supports trusted artifact filters:

```text
has_trusted_artifact
has_trusted_code_artifact
has_trusted_dataset_artifact
has_trusted_model_artifact
has_trusted_demo_artifact
artifact_provider
artifact_type
```

These filters operate through:

```text
paper_artifact_links
JOIN artifact_entities
```

They must not be confused with legacy canonical fields.

---

## Legacy fields vs artifact layer

Legacy canonical/source fields:

```text
has_code_link
code_links
repo_url
dataset_links
model_links
has_dataset_link
has_model_link
```

New trusted artifact-layer filters:

```text
has_trusted_artifact
has_trusted_code_artifact
has_trusted_dataset_artifact
has_trusted_model_artifact
has_trusted_demo_artifact
artifact_provider
artifact_type
```

Rule:

```text
Do not silently redefine has_code_link.
```

`has_code_link` remains a legacy canonical/source field.

`has_trusted_code_artifact` is the new trusted artifact-layer signal.

---

## Tests

Artifact API tests:

```bat
python -m pytest tests/integration/test_api_artifacts_db.py -q
```

Document artifact filter tests:

```bat
python -m pytest tests/integration/test_api_documents_artifact_filters_db.py -q
```

Strict DoD:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts
```

Recommended regression check:

```bat
python -m pytest tests/integration/test_api_artifacts_db.py -q
python -m pytest tests/integration/test_api_documents_artifact_filters_db.py -q
python -m scripts.update.check_refresh_definition_of_done --require-artifacts
```

---

## Known technical debt

### Figshare URL normalization

Some Figshare artifacts currently appear as separate entities even when they share the same numeric article id.

Example pattern:

```text
https://figshare.com/articles/.../6475511
https://figshare.com/articles/journal_contribution/.../6475511
```

Future improvement:

```text
Normalize Figshare artifacts by numeric article id.
```

This is not a blocker for Artifact Layer v1.

### Generic URL confidence

Generic artifact URLs are useful but less reliable than provider-specific URLs.

Trusted generic URLs must remain filtered conservatively.

### External enrichment

Artifact Layer v1 does not yet enrich GitHub/Hugging Face metadata through APIs.

Current GitHub fields such as stars, forks, topics, license and language are reserved but mostly empty.

---

## Next stage: GitHub enrichment v1

Next planned artifact-layer extension:

```text
scripts/enrich/enrich_github_artifacts.py
```

Input:

```sql
SELECT *
FROM artifact_entities
WHERE provider = 'github';
```

Potential GitHub fields:

```text
description
stars
forks
watchers
open_issues
license
topics
language
default_branch
archived
disabled
created_at
updated_at
pushed_at
homepage
```

Output:

```text
data/enriched/github_artifacts/github_artifact_metadata.<ts>.jsonl
data/enriched/github_artifacts/github_artifact_metadata_latest.jsonl
artifacts/reports/validation/github_artifact_enrichment_latest.json
artifacts/reports/validation/github_artifact_enrichment_latest.md
```

GitHub enrichment must remain artifact enrichment.

GitHub must not become a paper-source truth layer.

---

## Summary

Artifact Layer v1 is now a working operational layer:

```text
internal extraction
→ quality gate
→ SQL schema
→ Postgres export
→ DB smoke
→ DoD integration
→ refresh pipeline integration
→ artifact API
→ document artifact filters
→ integration tests
```

The current layer is ready to support future external artifact enrichment, starting with GitHub.