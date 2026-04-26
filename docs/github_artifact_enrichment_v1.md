# GitHub Artifact Enrichment v1

## Purpose

GitHub Artifact Enrichment v1 enriches already extracted GitHub repository artifacts with repository metadata from the GitHub REST API.

This layer is an **artifact enrichment layer**, not a paper-source layer.

It must not modify canonical paper truth.

## Architectural position

```text
canonical/source paper metadata
→ internal artifact extraction
→ artifact_entities / artifact_observations / trusted paper_artifact_links
→ GitHub artifact metadata snapshot
→ optional Postgres artifact_entities enrichment
→ /artifacts API exposure
```

Important invariant:

```text
canonical_documents.jsonl = paper truth
GitHub metadata = artifact metadata snapshot
Postgres = materialized serving layer
```

GitHub metadata must not overwrite paper fields such as title, abstract, venue, journal, publisher, publication_type, citation counts or references.

## Input

Default input:

```text
data/enriched/artifact_links/artifact_entities_latest.jsonl
```

Only rows with:

```text
provider == "github"
artifact_type == "github_repository"
```

are fetched.

Default input intentionally comes from the artifact extraction output, not Postgres, so the enrichment is reproducible and does not depend on current materialized DB state.

## Script

```text
scripts/enrich/enrich_github_artifacts.py
```

Example commands:

```bash
python -m scripts.enrich.enrich_github_artifacts --dry-run --limit 5
python -m scripts.enrich.enrich_github_artifacts --limit 5
python -m scripts.enrich.enrich_github_artifacts
```

Optional environment variable:

```text
GITHUB_TOKEN
```

The token is never written to reports or logs. Reports only include:

```text
token_present: true/false
```

## Outputs

Timestamped output:

```text
data/enriched/github_artifacts/github_artifact_metadata.<ts>.jsonl
```

Latest pointer:

```text
data/enriched/github_artifacts/github_artifact_metadata_latest.jsonl
```

Reports:

```text
artifacts/reports/validation/github_artifact_enrichment_latest.json
artifacts/reports/validation/github_artifact_enrichment_latest.md
artifacts/reports/validation/history/github_artifact_enrichment_<ts>.json
artifacts/reports/validation/history/github_artifact_enrichment_<ts>.md
```

## Output row contract

For found repositories:

```json
{
  "artifact_id": "...",
  "provider": "github",
  "external_id": "owner/repo",
  "owner": "owner",
  "name": "repo",
  "normalized_url": "https://github.com/owner/repo",
  "github_api_url": "https://api.github.com/repos/owner/repo",
  "fetched_at": "2026-04-26T...+00:00",
  "status": "found",
  "http_status": 200,
  "description": "...",
  "homepage": "...",
  "language": "Python",
  "license": "mit",
  "stars": 1234,
  "forks": 123,
  "watchers": 1234,
  "open_issues": 12,
  "topics": ["machine-learning", "pytorch"],
  "default_branch": "main",
  "archived": false,
  "disabled": false,
  "private": false,
  "created_at": "...",
  "updated_at": "...",
  "pushed_at": "...",
  "metadata": {
    "source": "github_api",
    "enrichment_stage": "github_artifact_enrichment_v1"
  }
}
```

For unavailable repositories:

```json
{
  "artifact_id": "...",
  "provider": "github",
  "external_id": "owner/repo",
  "normalized_url": "https://github.com/owner/repo",
  "github_api_url": "https://api.github.com/repos/owner/repo",
  "fetched_at": "2026-04-26T...+00:00",
  "status": "not_found",
  "http_status": 404,
  "error": "..."
}
```

Supported statuses:

```text
found
not_found
forbidden
rate_limited
error
skipped_invalid_external_id
```

## Current baseline

Latest successful full run:

```text
github_entities_total = 113
requested_count = 113
processed_count = 113
found_count = 110
not_found_count = 3
forbidden_count = 0
rate_limited_count = 0
error_count = 0
skipped_invalid_external_id_count = 0
ok = true
```

## Postgres export integration

GitHub metadata is integrated into Postgres through:

```text
scripts/export/export_artifacts_postgres_v1.py
```

The export remains backward-compatible:

```text
if GitHub metadata latest exists or --github-metadata is explicitly provided:
    merge GitHub metadata into artifact_entities before upsert
else:
    export artifact layer as before
```

GitHub metadata is optional and must not be required for the base artifact export.

Dedicated artifact columns populated from GitHub metadata:

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

GitHub-specific fields are stored under:

```json
{
  "metadata": {
    "github": {
      "status": "found",
      "http_status": 200,
      "language": "Python",
      "watchers": 123,
      "open_issues": 4,
      "default_branch": "main",
      "archived": false,
      "disabled": false,
      "private": false,
      "pushed_at": "...",
      "homepage": "...",
      "github_api_url": "..."
    }
  }
}
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

## API exposure

GitHub metadata is exposed through the existing DB artifact API:

```text
GET /artifacts?provider=github
GET /documents/{canonical_id}/artifacts
```

Example exposed fields:

```text
stars
forks
license
topics
fetched_at
metadata.github.status
metadata.github.language
metadata.github.watchers
metadata.github.open_issues
metadata.github.default_branch
metadata.github.archived
metadata.github.pushed_at
```

No new endpoint is required for v1.

## Validation

Successful checks:

```bash
python -m scripts.export.export_artifacts_postgres_v1 --replace
python -m scripts.export.test_artifact_db_read
python -m pytest tests/integration/test_api_artifacts_db.py -q
python -m pytest tests/integration/test_api_documents_artifact_filters_db.py -q
python -m pytest tests/integration/test_api_github_enrichment_db.py -q
python -m scripts.update.check_refresh_definition_of_done --require-artifacts
```

Observed passing tests:

```text
test_api_artifacts_db.py: 8 passed
test_api_documents_artifact_filters_db.py: 8 passed
test_api_github_enrichment_db.py: 2 passed
DoD --require-artifacts: dod_passed=True, required_failed_count=0
```

## Semantics for unavailable repositories

`not_found` repositories are preserved.

They are not removed from `artifact_entities` or `paper_artifact_links` because paper evidence still historically points to that URL. A repository may have been deleted, renamed, made private or temporarily unavailable.

`archived` repositories are valid found artifacts. The trusted paper-artifact link is not downgraded because archived status is an artifact state, not evidence invalidation.

## DoD policy

GitHub enrichment is **not** part of the base `--require-artifacts` DoD.

Reason:

```text
GitHub API is an external live dependency with rate limits and possible temporary failures.
The base artifact layer must remain green without live external enrichment.
```

A future optional flag may be added:

```text
--require-github-enrichment
```

## Non-goals

Not part of GitHub Artifact Enrichment v1:

```text
using GitHub as a paper source
changing canonical paper truth
changing has_code_link semantics
ranking papers by stars
refresh pipeline live dependency by default
GitHub issue/PR/content mining
repository README embedding
repository search endpoint
```
