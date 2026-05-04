# Artifact Layer v1

## Purpose

This document defines the current Artifact Layer v1 of ML Research Radar.

The artifact layer stores external software, dataset, model, demo, video, repository and project-page artifacts related to canonical ML/AI research papers.

It is a separate data plane from the canonical paper corpus.

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
  → optional provider metadata enrichment
```

The central paper entity is:

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

These files are operational extraction artifacts derived from canonical/source metadata. They are not paper truth.

### Provider enrichment outputs

Provider enrichment snapshots are external metadata snapshots over extracted artifact entities.

Current provider enrichment outputs:

```text
data/enriched/github_artifacts/github_artifact_metadata_latest.jsonl
data/enriched/huggingface_artifacts/huggingface_artifact_metadata_latest.jsonl
```

These are not paper truth and do not modify canonical documents.

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

Do not create separate `paper_artifact_links` rows only because evidence came from a different field or source. Evidence multiplicity belongs in JSON metadata.

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

Current artifact providers observed in the 60k baseline include:

```text
github
generic
youtube
huggingface
zenodo
figshare
gitlab
bitbucket
kaggle
codeberg
```

Current provider enrichment stages:

```text
github_artifact_enrichment_v1
huggingface_artifact_enrichment_v1
```

---

## Artifact extraction v1

Artifact extraction v1 uses internal extraction only.

The extraction step itself does not call external APIs. External metadata enrichment is handled by separate snapshot enrichment stages, such as GitHub Artifact Enrichment v1 and Hugging Face Artifact Enrichment v1.

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

The config fixes explicit source snapshots for reproducible extraction. Source directories can contain derivative snapshots such as `.updated.jsonl` or `.unchanged.jsonl`, which are not full stable snapshots.

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

The quality gate explicitly allows broad observations to include some untrusted rows. Trusted serving rows are produced later through export filtering.

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
- GitLab repository
- Bitbucket repository
- Codeberg repository
- Hugging Face model
- Hugging Face dataset
- Hugging Face Space
- Figshare article/dataset
- Zenodo record
- YouTube video
- Kaggle dataset
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

Provider-specific metadata is stored in:

```text
metadata.github
metadata.huggingface
```

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

GitHub metadata snapshot
  → artifact_entities.metadata.github + selected columns

Hugging Face metadata snapshot
  → artifact_entities.metadata.huggingface + selected columns
```

Important behavior:

- deduplicates entities by normalized URL
- remaps observations when deduplication occurs
- exports broad observations to `artifact_observations`
- exports only trusted links to `paper_artifact_links`
- aggregates multiple observations into one trusted link row
- stores evidence list in `metadata.evidence`
- merges provider enrichment metadata without modifying canonical paper truth

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

## Current 60k baseline

Artifact extraction:

```text
raw artifact_entities_latest = 7173
artifact_observations = 37582
trusted_unique_paper_artifact_links = 7262
linked_canonical_docs = 6507
```

Artifact DB:

```text
canonical_documents_count = 60000
artifact_entities_count = 7170
artifact_observations_count = 37582
paper_artifact_links_count = 7262
join_canonical_artifact_entities_count = 7262
join_canonical_documents_count = 6507
join_artifact_entities_count = 7170
ok = true
```

Provider distribution from extraction:

```text
github = 5796
generic = 897
youtube = 233
huggingface = 96
zenodo = 65
figshare = 63
gitlab = 12
bitbucket = 5
kaggle = 4
codeberg = 2
```

Artifact type distribution includes:

```text
github_repository = 5796
huggingface_model = 45
huggingface_dataset = 42
huggingface_space = 9
```

---

## GitHub Artifact Enrichment v1

GitHub Artifact Enrichment v1 enriches already extracted GitHub repository artifacts.

Input:

```text
data/enriched/artifact_links/artifact_entities_latest.jsonl
```

Outputs:

```text
data/enriched/github_artifacts/github_artifact_metadata.<ts>.jsonl
data/enriched/github_artifacts/github_artifact_metadata_latest.jsonl
artifacts/reports/validation/github_artifact_enrichment_latest.json
artifacts/reports/validation/github_artifact_enrichment_latest.md
artifacts/reports/validation/github_artifact_enrichment_check_latest.json
artifacts/reports/validation/github_artifact_enrichment_check_latest.md
```

Current strict validation baseline:

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
strict = true
ok = true
```

Populated dedicated fields for found repositories:

```text
description
license
stars
forks
topics
fetched_at
created_at
updated_at
```

GitHub-specific fields are stored in `artifact_entities.metadata.github`.

`not_found` repositories are preserved as historical artifact evidence.

---

## Hugging Face Artifact Enrichment v1

Hugging Face Artifact Enrichment v1 enriches already extracted Hugging Face model/dataset/space artifacts.

Input:

```text
data/enriched/artifact_links/artifact_entities_latest.jsonl
```

Outputs:

```text
data/enriched/huggingface_artifacts/huggingface_artifact_metadata.<ts>.jsonl
data/enriched/huggingface_artifacts/huggingface_artifact_metadata_latest.jsonl
artifacts/reports/validation/huggingface_artifact_enrichment_latest.json
artifacts/reports/validation/huggingface_artifact_enrichment_latest.md
artifacts/reports/validation/huggingface_artifact_enrichment_check_latest.json
artifacts/reports/validation/huggingface_artifact_enrichment_check_latest.md
```

Current strict validation baseline:

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

Current DB verification:

```text
hf_entities = 96
hf_metadata = 96
hf_found = 73
hf_downloads = 64
```

Populated dedicated fields for found HF repos where available:

```text
description
license
downloads
likes
tags
fetched_at
created_at
updated_at
```

Hugging Face-specific fields are stored in `artifact_entities.metadata.huggingface`:

```text
status
http_status
repo_type
repo_id
huggingface_api_url
pipeline_tag
library_name
private
gated
disabled
input_normalized_url
input_external_id
error
card_data
```

`forbidden` and `skipped_invalid_external_id` rows are diagnostic provider/extraction states. They do not fail the core strict gate.

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

### Optional GitHub enrichment DoD

Command:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-github-enrichment
```

Required GitHub checks include:

```text
github_enrichment_check_exists
github_enrichment_check_ok
github_enrichment_rows_non_empty
github_enrichment_found_non_empty
github_enrichment_no_rate_limited
github_enrichment_no_errors
github_enrichment_metadata_vs_entities_match
github_enrichment_no_unknown_artifact_ids
github_enrichment_no_duplicate_artifact_ids
```

### Optional Hugging Face enrichment DoD

Command:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-huggingface-enrichment
```

Full provider-enriched strict mode:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-github-enrichment --require-huggingface-enrichment
```

Required Hugging Face checks include:

```text
huggingface_enrichment_check_exists
huggingface_enrichment_check_ok
huggingface_enrichment_rows_non_empty
huggingface_enrichment_found_non_empty
huggingface_enrichment_no_rate_limited
huggingface_enrichment_no_errors
huggingface_enrichment_metadata_vs_entities_match
huggingface_enrichment_no_unknown_artifact_ids
huggingface_enrichment_no_duplicate_artifact_ids
```

Diagnostic-only Hugging Face checks:

```text
huggingface_enrichment_no_forbidden
huggingface_enrichment_no_skipped_invalid_external_ids
```

The base `--require-artifacts` mode does not require provider enrichment because provider APIs are live external dependencies.

---

## Refresh pipeline integration

Main wrapper:

```text
scripts/update/run_refresh_pipeline_v1.py
```

Artifact stages are included when:

```bat
--require-artifacts
```

or when a provider enrichment stage is explicitly included:

```bat
--include-github-enrichment
--include-huggingface-enrichment
```

Artifact-aware pipeline order with both provider enrichments enabled:

```text
reconcile_candidate
→ candidate_provenance_audit
→ promote_candidate
→ export_postgres
→ extract_artifacts
→ artifact_quality_check
→ github_artifact_enrichment
→ github_artifact_enrichment_check
→ huggingface_artifact_enrichment
→ huggingface_artifact_enrichment_check
→ export_artifacts_postgres
→ artifact_db_smoke
→ rebuild_retrieval
→ retrieval_checks
→ postpass_audit
→ known_issues
→ dod_check
```

Provider stages are included only when explicitly requested:

```bat
--include-github-enrichment
--include-huggingface-enrichment
```

Strict final DoD can require provider enrichment reports with:

```bat
--require-github-enrichment
--require-huggingface-enrichment
```

The include and require flags are separate:

```text
--include-*-enrichment
  includes live provider enrichment and validation stages

--require-*-enrichment
  makes final DoD require the latest provider validation report
```

Dry run with artifact stages only:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts
```

Dry run with both provider enrichments and strict final DoD:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts --include-github-enrichment --include-huggingface-enrichment --require-github-enrichment --require-huggingface-enrichment
```

Dry run to Hugging Face enrichment check checkpoint:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts --include-huggingface-enrichment --stop-after huggingface_artifact_enrichment_check
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

The artifact API is DB-only. The file backend does not load artifact tables and does not provide artifact browse/filter support.

Current provider-specific enriched API filters exist for GitHub. Hugging Face-specific API filters are intentionally postponed until after the next source/source-expansion slices, to avoid repeatedly redesigning API contracts.

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

`has_code_link` remains a legacy canonical/source field. `has_trusted_code_artifact` is the new trusted artifact-layer signal.

---

## Tests and validation

Core artifact checks:

```bat
python -m scripts.validation.check_artifact_links_quality --strict
python -m scripts.export.export_artifacts_postgres_v1 --dry-run
python -m scripts.export.export_artifacts_postgres_v1 --replace
python -m scripts.export.test_artifact_db_read
```

Provider checks:

```bat
python -m scripts.validation.check_github_artifact_enrichment --strict
python -m scripts.validation.check_huggingface_artifact_enrichment --strict
```

Strict DoD modes:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-artifacts
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-github-enrichment
python -m scripts.update.check_refresh_definition_of_done --require-artifacts --require-github-enrichment --require-huggingface-enrichment
```

Pipeline dry-run with provider enrichments:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --require-artifacts --include-github-enrichment --include-huggingface-enrichment --require-github-enrichment --require-huggingface-enrichment
```

---

## Known technical debt

### Figshare URL normalization

Some Figshare artifacts currently appear as separate entities even when they share the same numeric article id.

Future improvement:

```text
Normalize Figshare artifacts by numeric article id.
```

This is not a blocker for Artifact Layer v1.

### Generic URL confidence

Generic artifact URLs are useful but less reliable than provider-specific URLs.

Trusted generic URLs must remain filtered conservatively.

### Hugging Face extraction cleanup

Current HF enrichment has identified some malformed extracted IDs and collection URLs. These are now classified as `skipped_invalid_external_id` rather than provider API errors.

Future improvement:

```text
Move more Hugging Face URL cleanup upstream into extract_artifact_links.py.
Optionally model Hugging Face collections separately if they become useful.
```

This is not a blocker for Hugging Face Artifact Enrichment v1.

---

## Summary

Artifact Layer v1 is now a working operational layer:

```text
internal extraction
→ quality gate
→ SQL schema
→ provider enrichment snapshots
→ Postgres export
→ DB smoke
→ DoD integration
→ refresh pipeline integration
→ artifact API
→ document artifact filters
→ integration tests
```

The current layer supports GitHub Artifact Enrichment v1 and Hugging Face Artifact Enrichment v1 while preserving the core invariant:

```text
artifact metadata does not modify canonical paper truth.
```
