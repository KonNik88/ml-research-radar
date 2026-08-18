# Refresh Runbook v1

## Purpose

This runbook describes the safe operational path for refreshing ML Research Radar
from source snapshots to canonical promotion and derived layer synchronization.

Canonical documents remain the source of truth. Retrieval artifacts, reports,
Postgres tables, paper features, similar papers, topic clusters, topic
projection, Discovery API checks, and Streamlit UI checks are derived layers.

## Safety Rules

- Do not promote a candidate unless promotion readiness passes.
- Do not treat Postgres, retrieval indexes, topic clusters, projections, or
  reports as canonical truth.
- Do not commit generated `data/`, `artifacts/`, `archive/`, local backup, or
  local database dump outputs unless explicitly intended.
- Stop at the first failed required gate.
- If a runtime manifest is regenerated, rebuild any report that records its
  `build_id`.
- Use `--execute` only for steps that are expected to mutate local canonical,
  derived, or database state.

## Branch Setup

Use a dedicated branch for code, test, config, or docs changes. Pure operational
refresh runs may leave `git status` clean if generated outputs are ignored.

```bat
git checkout main
git pull --ff-only origin main
git checkout -b chore/refresh-YYYYMMDD
git status --short
```

## Preflight

Build full merged alignment inputs and verify that all required refresh inputs
and reports are present before candidate rehearsal.

```bat
python -m scripts.update.build_refresh_alignment_merged_snapshots --execute --strict
python -m scripts.validation.check_refresh_preflight_contract --strict --require-known-issues --require-merged-inputs --require-refresh-cycle-report
```

Expected required checks:

```text
required_failed_count=0
required_failed_checks=[]
merge_snapshots_cover_baseline_alignment_sources=True
refresh_cycle_ready_for_reconcile_candidate=True
```

Database smoke checks may be reported in preflight output. They are operational
readiness signals, but DB availability is handled explicitly during Postgres
sync below.

## Candidate Rehearsal

Run a candidate rehearsal without mutating canonical latest.

```bat
python -m scripts.update.run_refresh_pipeline_v1 --candidate-rehearsal --execute
python -m scripts.validation.check_refresh_alignment_coverage
python -m scripts.validation.check_refresh_source_coverage
python -m scripts.validation.check_refresh_promotion_readiness --strict
```

Expected promotion readiness checks:

```text
promotion_ready=True
removed_count=0
destructive_identifier_churn_count=0
lost_alignment_source_observation_count=0
required_failed_count=0
required_failed_checks=[]
```

Additive source enrichment may be present and is not a promotion blocker when
destructive source loss, identifier churn, and alignment source loss are absent.

## Controlled Promotion

Dry-run the controlled promotion first. Execute only after the dry run reports
that the candidate is safe to promote.

```bat
python -m scripts.update.run_refresh_controlled_promotion --strict
```

Expected dry-run checks:

```text
safe_to_execute=True
controlled_promotion_complete=False
canonical_latest_mutated=False
required_failed_count=0
```

Execute the promotion:

```bat
python -m scripts.update.run_refresh_controlled_promotion --execute --strict
```

Expected execute checks:

```text
safe_to_execute=True
controlled_promotion_complete=True
canonical_latest_mutated=True
required_failed_count=0
```

Post-promotion canonical checks:

```bat
python -m scripts.validation.check_canonical_provenance_consistency
python -m scripts.validation.check_canonical_contract --strict
```

Expected checks:

```text
all_error_checks_clean=True
contract_ok=True
required_failed_count=0
```

Informational provenance findings and non-required duplicate `doc_ids` across
canonical rows should be reviewed, but they do not block promotion unless the
strict contract or required gates fail.

## Core Derived Rebuild

Rebuild retrieval and validation layers from the promoted canonical corpus.

```bat
python -m scripts.retrieval.build_indexes
python -m scripts.validation.run_retrieval_checks
python -m scripts.validation.run_postpass_audit
python -m scripts.validation.build_known_issues_snapshot
python -m scripts.update.check_refresh_definition_of_done --require-known-issues
```

Expected checks:

```text
corpus_doc_count=<canonical_doc_count>
canonical_vs_manifest_doc_count_match=True
canonical_vs_retrieval_checks_doc_count_match=True
canonical_vs_postpass_doc_count_match=True
canonical_vs_known_issues_doc_count_match=True
manifest_vs_retrieval_checks_build_id_match=True
manifest_vs_known_issues_build_id_match=True
required_failed_count=0
```

If `artifacts/retrieval/manifests/latest.json` is missing because generated
artifacts are ignored and no local build exists, rerun:

```bat
python -m scripts.retrieval.build_indexes
python -m scripts.validation.run_retrieval_checks
python -m scripts.validation.build_known_issues_snapshot
```

## Postgres Sync

Start the local Postgres container before DB checks or export.

```bat
docker compose -f infra/docker/docker-compose.yml up -d
```

Check current DB state, replace DB-derived paper tables from canonical and
normalized files, then verify the DB read layer.

```bat
python -m scripts.export.test_db_read
python -m scripts.export.export_postgres_v1 --replace
python -m scripts.export.test_db_read
python -m scripts.update.check_refresh_definition_of_done --require-known-issues
```

Expected checks:

```text
Ping: True
Total docs: <canonical_doc_count>
db_smoke_ok=True
db_ping_true=True
canonical_vs_db_doc_count_match=True
required_failed_count=0
```

`export_postgres_v1 --replace` truncates and rebuilds derived Postgres paper
tables from file-backed truth. Postgres must not contain manual canonical-only
state that is unavailable in canonical, normalized, or export files.

## Optional Discovery Derived Layers

Use this section when the Discovery/analytics layers must be synchronized with
the latest canonical and retrieval build.

Build and validate paper features:

```bat
python -m scripts.features.build_paper_features
python -m scripts.validation.check_paper_features --strict
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-paper-features
```

Expected checks:

```text
paper_features_rows_match_canonical=True
paper_features_quality_canonical_rows_match=True
required_failed_count=0
```

Build and validate detail and similar papers:

```bat
python -m scripts.details.build_paper_detail
python -m scripts.retrieval.find_similar_papers --from-latest-detail --top-k 20
python -m scripts.validation.check_similar_papers_report --strict
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-paper-features --require-similar-papers
```

Expected checks:

```text
similar_papers_quality_ok=True
similar_papers_target_found=True
similar_papers_results_non_empty=True
required_failed_count=0
```

Build and validate topic clusters and projection:

```bat
python -m scripts.analytics.build_topic_clusters
python -m scripts.validation.check_topic_clusters --strict
python -m scripts.analytics.build_topic_projection
python -m scripts.validation.check_topic_projection --strict
```

Expected checks:

```text
topic_clusters_assignment_count_matches_canonical=True
topic_clusters_retrieval_build_id_matches_manifest=True
topic_projection_cluster_build_id_matches_topic_clusters=True
topic_projection_retrieval_build_id_matches_manifest=True
required_failed_count=0
```

Validate Discovery API and Streamlit Discovery UI:

```bat
python -m scripts.validation.check_discovery_api --strict
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Expected checks:

```text
discovery_api_quality_ok=True
streamlit_discovery_ui_quality_ok=True
required_failed_count=0
```

Final optional derived Definition of Done:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-paper-features --require-similar-papers --require-topic-clusters --require-topic-projection --require-discovery-api --require-streamlit-discovery-ui
```

Expected checks:

```text
dod_passed=True
required_failed_count=0
```

## Optional Artifact And Enrichment Gates

Artifact, GitHub enrichment, Hugging Face enrichment, citation graph API
regression, and golden query gates are opt-in. Enable them only when the current
refresh scope includes those layers.

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-artifact-api-filters
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-github-enrichment --require-huggingface-enrichment
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-citation-graph-api-regression
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-golden-queries
```

Known non-blocking signals can appear when their corresponding `--require-*`
flag is not enabled. Do not treat optional stale layers as blockers for the core
refresh unless that layer is part of the current scope.

## Git Policy

Normal refresh PRs should contain only intentional repository changes:

- code
- tests
- docs
- configs
- contract changes

Generated outputs should normally remain local:

- `data/`
- `artifacts/`
- `archive/`
- local backups
- local database dumps

Before committing:

```bat
git status --short
git diff --check
```

If generated artifacts appear in `git status`, check whether they were already
tracked:

```bat
git ls-files artifacts archive data
```

To stop tracking a generated file while keeping it locally:

```bat
git rm --cached <path>
```

To stop tracking a generated directory while keeping it locally:

```bat
git rm -r --cached <path>
```

Keep these removals separate from feature work when possible.

## PR Checklist

- Candidate rehearsal passed.
- Promotion readiness passed.
- Controlled promotion dry run passed.
- Controlled promotion execute passed, if promotion was in scope.
- Canonical provenance consistency and canonical contract passed.
- Retrieval, postpass audit, known issues, and DB sync passed.
- Optional derived layers passed if they were in scope.
- Final DoD passed with the required flags for the current scope.
- `git status --short` contains only intentional repository changes.
- Generated outputs are not committed unless explicitly intended.

## Current Reference Refresh

The August 2026 refresh path validated this runbook shape with:

```text
baseline_doc_count=60954
candidate_doc_count=61075
doc_count_delta=121
removed_count=0
canonical_multisource_docs=9226
```

The final required Discovery-oriented DoD passed with:

```text
dod_passed=True
required_failed_count=0
```
