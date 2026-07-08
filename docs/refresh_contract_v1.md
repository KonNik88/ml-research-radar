# Refresh / Runtime Runbook v1

## Purpose

This runbook describes the current safe manual refresh, validation, runtime startup and Qdrant/Streamlit operational loop for **ML Research Radar**.

It is the operational companion to:

```text
docs/roadmap.md
docs/architecture.md
docs/api_reference.md
docs/experiment_safety_rules.md
docs/provenance_semantics.md
docs/data_contracts.md
docs/source_matrix.md
docs/merge_policy.md
```

The document is intentionally practical. It answers:

```text
What is source of truth?
What can be rebuilt?
What must be validated?
How do we start the project after a full computer restart?
How do we check API/Qdrant/Streamlit?
What is considered a green checkpoint?
```

---

## Current checkpoint

Current working checkpoint:

```text
Discovery Green Checkpoint — 2026-05
Qdrant runtime visibility sync — 2026-06
Artifact API filters validation + DoD gate — 2026-06
Regression runner DB preflight — 2026-06
Discovery regression runner summary report — 2026-06
Dataset release track checkpoint — 2026-06
Paper–Artifact Graph Line Checkpoint v0.1 — 2026-07 completed read-only graph-line checkpoint
Paper–Artifact Graph Manual Review Checklist v0.1 — 2026-07 completed read-only manual-review governance slice
Paper–Artifact Graph Analytics v0.1 — 2026-07 completed read-only graph analytics/report slice
Citation / Reference Graph Contract v0.1 — 2026-07 completed contract-only derived citation/reference graph slice
Citation / Reference Graph Builder v0.1 — 2026-07 completed file-first derived citation/reference graph builder slice
Citation / Reference Graph Inspection v0.1 — 2026-07 completed read-only citation/reference graph inspection/report slice
Citation / Reference Graph Reference Normalization Fix v0.1.1 — 2026-07 completed OpenAlex/reference-id normalization fix
Citation / Reference Graph Query CLI v0.1 — 2026-07 completed read-only offline citation/reference graph query slice
Citation / Reference Graph Docs Counter Refresh v0.1 — 2026-07 completed docs-only counter/status refresh
Citation / Reference Graph Release Candidate v0.1 — 2026-07 completed read-only release-candidate readiness gate
Citation / Reference Graph Package v0.1 — 2026-07 completed local package candidate layer
Citation / Reference Graph Line Checkpoint v0.1 — 2026-07 completed read-only line checkpoint
Citation / Reference Graph Manual Review Checklist v0.1 — 2026-07 completed read-only manual-review governance gate
Citation / Reference Graph Analytics v0.1 — 2026-07 completed read-only analytics/report layer
Graph Review Evidence Pack v0.1 — 2026-07 completed local read-only graph review evidence pack
Citation / Reference Graph API Design v0.1 — 2026-07 completed design-only API contract
Graph API Response Fixture Design v0.1 — 2026-07 completed design-only response/caveat fixture contract
Graph Runtime Stale-Version Compatibility Design v0.1 — 2026-07 completed design-only compatibility contract
Citation / Reference Graph API Implementation Plan v0.1 — 2026-07 completed implementation-plan-only checkpoint
Citation Graph API Disabled Status Endpoint v0.1 — 2026-07 completed status-only disabled-by-default API slice
Citation Graph API Docs Sync v0.1 — 2026-07 active docs synchronization slice
```

Current healthy baseline:

```text
canonical_documents = 60954
canonical_multisource_docs = 9192
doi_count = 10183
arXiv backbone = 60000
ACL-family docs = 957
ACL-only docs = 954
ACL-enriched existing docs = 3

retrieval_build_id = 20260504T164021Z
embedding_model = sentence-transformers/all-MiniLM-L6-v2
embedding_shape = [60954, 384]

artifact_entities_db_count = 7333
artifact_observations_db_count = 38246
paper_artifact_links_db_count = 7430

github_found_count ≈ 5339
huggingface_found_count ≈ 77

artifact_api_filters_check = ok
artifact_api_filters_required_failed_count = 0
artifact_api_filters_dod_gate = optional by default / required with --require-artifact-api-filters
regression_runner_db_preflight = enabled for DB-backed regression steps
discovery_api_regression_runner_report = enabled
dataset_release_track_checkpoint = local_candidate_validation_enabled
paper_artifact_graph_contract = accepted
paper_artifact_graph_builder = accepted_local_derived_builder
paper_artifact_graph_inspection = accepted_read_only_inspection
paper_artifact_graph_query_cli = accepted_read_only_query_cli
paper_artifact_graph_release_candidate = accepted_read_only_release_candidate
paper_artifact_graph_package = accepted_local_package_candidate
paper_artifact_graph_line_checkpoint = accepted_read_only_line_checkpoint
paper_artifact_graph_manual_review = accepted_read_only_manual_review_gate
paper_artifact_graph_analytics = accepted_read_only_analytics_report
citation_reference_graph_contract = accepted_contract_only
citation_reference_graph_builder = accepted_local_derived_builder
citation_reference_graph_inspection = accepted_read_only_inspection
citation_reference_graph_reference_normalization_fix = accepted_openalex_reference_id_normalization
citation_reference_graph_query_cli = accepted_read_only_query_cli
citation_reference_graph_release_candidate = accepted_read_only_release_candidate
citation_reference_graph_package = accepted_local_package_candidate
citation_reference_graph_line_checkpoint = accepted_read_only_line_checkpoint
citation_reference_graph_manual_review = accepted_read_only_manual_review_gate
citation_reference_graph_analytics = accepted_read_only_analytics_report
graph_review_evidence_pack = accepted_local_read_only_review_evidence_pack
citation_reference_graph_api_design = accepted_design_only
citation_reference_graph_api_response_fixtures = accepted_design_only
citation_reference_graph_runtime_compatibility_design = accepted_design_only
citation_reference_graph_api_implementation_plan = accepted_plan_only
citation_graph_api_disabled_status_endpoint = implemented_disabled_by_default_status_only
citation_graph_api_traversal_endpoints = not_implemented
citation_graph_runtime_loader = not_implemented
paper_artifact_graph_dod_gate = not required yet
paper_artifact_graph_manual_review_dod_gate = not required yet
paper_artifact_graph_analytics_dod_gate = not required yet
citation_reference_graph_dod_gate = not required yet
citation_reference_graph_builder_dod_gate = not required yet
citation_reference_graph_inspection_dod_gate = not required yet
citation_reference_graph_query_cli_dod_gate = not required yet
citation_reference_graph_release_candidate_dod_gate = not required yet
citation_reference_graph_package_dod_gate = not required yet

paper_features_rows_count = 60954
ranking_profiles_count = 9
topic_clusters_count = 80
topic_assignments_count = 60954
topic_projection_algorithm = umap
topic_projection_rows_count = 2080

golden_queries_enabled_count = 34
golden_queries_explicit_count = 34
golden_queries_weak_pattern_count = 0

qdrant_benchmark_collection = ml_radar_dense_benchmark_v1
qdrant_benchmark_uploaded_count = 60954

strict_dod_required_failed_count = 0
strict_dod_passed = true
strict_dod_required_checks = see latest check_refresh_definition_of_done report
```

Current retrieval manifest:

```text
artifacts/retrieval/manifests/latest.json
```

Current known issues snapshot path:

```text
artifacts/reports/validation/known_issues_snapshot_latest.json
```

Important naming note:

```text
known_issues_snapshot_latest.json
```

not:

```text
known_issues_latest.json
```

---

## Core architecture invariants

```text
canonical_documents.jsonl = paper-level truth
Postgres = rebuildable materialized serving layer
retrieval artifacts = derived retrieval layer
artifact DB = derived evidence/materialization plane
GitHub/Hugging Face = artifact enrichment providers, not paper sources
paper_features = derived discovery feature layer
ranking / detail / similar = derived discovery/product layer
topic clusters / projection = derived analytics/discovery layer
Discovery API = product/discovery API over derived layers
Streamlit UI = thin API client
Qdrant = optional derived vector-serving benchmark / experimental layer
```

No derived layer is allowed to mutate canonical truth.

---

## Current active source set

Current stable paper sources:

```text
arxiv
openalex_alignment
semantic_scholar_alignment
crossref_alignment
acl_anthology
```

Current roles:

- `arxiv` is the 60k backbone.
- `openalex_alignment`, `semantic_scholar_alignment`, and `crossref_alignment` enrich the backbone.
- `acl_anthology` is the first major source-expansion case.
- GitHub and Hugging Face enrich artifact entities; they are not paper-truth sources.
- Papers with Code live/source integration remains blocked/archived; PWC-like signals are artifact candidates only unless policy changes.

Current operational paper source of truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

---

## Core safety principle

Never treat a selective/latest enrichment batch as a complete source snapshot.

Correct pattern:

```text
selective enrichment
→ merge selective batch into full alignment snapshot
→ reconcile using explicit full merged inputs
→ validate candidate
→ promote candidate
→ export/rebuild derived layers
→ validate reports
→ strict DoD
```

Key rule:

```text
reconcile must run from full intended inputs, not accidental mini-batches
```

This prevents corpus collapse, source loss and misleading multisource counts.

---

# A. Daily startup after full computer restart

Use this when continuing normal development, not when rebuilding canonical truth.

## 1. Start Docker Desktop

Start Docker Desktop manually and wait until it is fully running.

## 2. Open Anaconda Prompt

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
```

## 3. Sync main

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

## 4. Start containers

```bat
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml ps
```

Expected:

```text
ml_radar_postgres = Up / healthy
ml_radar_qdrant = Up
```

## 5. Quick smoke checks

```bat
python -m scripts.validation.check_qdrant_collection --strict
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_smoke.py -q
python -m pytest tests/integration/test_api_citation_graph_status.py -q
python -m scripts.validation.check_qdrant_api_experimental --strict
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Expected:

```text
qdrant collection_exists = true
qdrant points_count = 60954
qdrant corpus_doc_count = 60954
test_api_smoke.py = 7 passed
citation graph status endpoint = 3 passed, disabled-by-default/status-only
experimental qdrant API = status_code 200, mode dense_qdrant
streamlit UI required_failed_count = 0
qdrant_runtime_status_ui_snippets_present = true
```

---

# B. Run API and Streamlit locally

## 1. FastAPI

Open Anaconda Prompt window 1:

```bat
conda activate ml_radar
cd /d D:\ML\ML_Research_Radar
set ML_RADAR_SEARCH_BACKEND=file
python -m uvicorn services.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Expected:

```text
Application startup complete.
```

Manual checks:

```bat
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runtime
curl http://127.0.0.1:8000/citation-graph/status
```

Expected citation graph status endpoint interpretation:

```text
endpoint is reachable
status-only surface
disabled by default unless ML_RADAR_CITATION_GRAPH_API_ENABLED is explicitly enabled
no graph traversal endpoints
no graph runtime loader
manual_review_required = true
publication_ready = false
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

## 2. Streamlit

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

## 3. Streamlit Qdrant smoke

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

Then click **Open Qdrant result in Paper workspace** and load:

```text
selected paper detail
selected paper similar papers
selected paper topic cluster
```

---

# C. Qdrant negative check

Use this when changing Qdrant runtime diagnostics, Qdrant UI status, or Qdrant settings.

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

# D. Manual refresh flow

Use this only when refreshing canonical or derived artifacts, not for ordinary development startup.

There are two valid styles:

1. use the thin orchestration wrapper;
2. run individual steps manually while debugging.

## Option A — thin orchestration wrapper

Example:

```bat
python -m scripts.update.run_refresh_pipeline_v1 --arxiv-input data\normalized\arxiv\documents.20260404T161108Z.jsonl --execute
```

Intended high-level sequence:

```text
reconcile candidate
→ candidate provenance audit
→ promote candidate
→ export canonical to Postgres
→ rebuild retrieval artifacts
→ run retrieval checks
→ run postpass audit
→ build known issues snapshot
→ DoD check
```

After wrapper completion, run downstream product checks if the wrapper does not already cover them.

## Option B — step-by-step execution

### 1. Build canonical candidate

```bat
python -m scripts.update.run_incremental_reconcile_stage --arxiv-input data\normalized\arxiv\documents.20260404T161108Z.jsonl --output-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl --execute
```

### 2. Audit candidate provenance

```bat
python -m scripts.validation.check_canonical_provenance_consistency --canonical-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl
```

Expected:

```text
docs_with_error = 0
```

Warnings must be interpreted through:

```text
docs/provenance_semantics.md
```

### 3. Promote candidate

```bat
python -m scripts.update.promote_canonical_candidate --candidate-path data\analytics\reconciled\canonical_documents.candidate_refresh_v1.jsonl --execute
```

### 4. Export canonical to Postgres

```bat
python -m scripts.export.export_postgres_v1 --replace
python -m scripts.export.test_db_read
```

### 5. Rebuild retrieval artifacts

```bat
python -m scripts.retrieval.build_indexes
```

Safe test build pattern:

```bat
python -m scripts.retrieval.build_indexes --no-write-latest
```

### 6. Run retrieval checks

```bat
python -m scripts.validation.run_retrieval_checks
```

### 7. Run postpass audit

```bat
python -m scripts.validation.run_postpass_audit
```

### 8. Refresh known issues snapshot

```bat
python -m scripts.validation.build_known_issues_snapshot
```

### 9. Rebuild / validate artifact layer

If canonical/source content changed enough to affect URLs/artifacts:

```bat
python -m scripts.enrich.extract_artifact_links
python -m scripts.validation.check_artifact_links_quality --strict
python -m scripts.export.export_artifacts_postgres_v1 --replace
python -m scripts.export.test_artifact_db_read
```

### 10. Validate GitHub enrichment

```bat
python -m scripts.validation.check_github_artifact_enrichment --strict
```

### 11. Validate Artifact API filters

This is a DB-backed API/report validation layer. It does not mutate canonical
truth, retrieval artifacts, Qdrant, ranking, or enrichment outputs.

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m scripts.validation.check_artifact_api_filters --strict
```

Expected:

```text
ok = true
required_failed_count = 0
runtime_backend_mode = db
runtime_ready = true
runtime_db_connected = true
```

The standalone validator still owns the full Artifact API filter contract. The
regression runner preflight added below is only an earlier environment/readiness
check; it does not replace this validator and does not write validation reports.

Generated reports:

```text
artifacts/reports/validation/artifact_api_filters_check_latest.json
artifacts/reports/validation/artifact_api_filters_check_latest.md
artifacts/reports/validation/history/artifact_api_filters_check_<timestamp>.json
artifacts/reports/validation/history/artifact_api_filters_check_<timestamp>.md
```

### 12. Validate Hugging Face enrichment

```bat
python -m scripts.validation.check_huggingface_artifact_enrichment --strict
```

Current non-blocking provider/extraction states unless policy changes:

```text
Hugging Face forbidden
Hugging Face skipped_invalid_external_id
GitHub not_found preserved as historical artifact evidence
```

### 13. Build / validate paper features

```bat
python -m scripts.features.build_paper_features
python -m scripts.validation.check_paper_features --strict
```

### 14. Validate ranking profiles

```bat
python -m scripts.validation.check_ranking_profiles --strict
```

### 15. Build / validate paper detail and similar papers

```bat
python -m scripts.ranking.demo_radar_ranking --profile huggingface_ready --top-k 5
python -m scripts.details.build_paper_detail --from-latest-ranking-rank 1
python -m scripts.retrieval.find_similar_papers --from-latest-detail --top-k 20
python -m scripts.validation.check_similar_papers_report --strict
```

### 16. Build / validate topic clusters

If retrieval embeddings, canonical corpus, or paper features changed:

```bat
python -m scripts.analytics.build_topic_clusters
python -m scripts.validation.check_topic_clusters --strict
```

### 17. Build / validate topic projection

If topic clusters changed or projection needs refresh:

```bat
python -m scripts.analytics.build_topic_projection
python -m scripts.validation.check_topic_projection --strict
```

### 18. Validate Discovery API

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_discovery.py -q
python -m scripts.validation.check_discovery_api --strict
```

### 19. Validate Streamlit Discovery UI

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict
```

Optional live API validation:

```bat
python -m scripts.validation.check_streamlit_discovery_ui --strict --check-api
```

---

# E. Citation / Reference Graph Inspection v0.1 validation

Use this when checking the accepted read-only inspection/report layer for the local Citation / Reference Graph v0.1 output.

This validation reads the generated graph output under `data/graphs/citation_reference_graph/v0.1/`. It does not rebuild graph output and does not change canonical truth, Postgres serving, retrieval artifacts, Qdrant, ranking, API behavior, Streamlit behavior, DB schema, package output, or any publication state.

This accepted slice follows the builder/output-validator checkpoint and adds the inspection/report portion of the separate citation/reference graph line:

```text
contract
→ builder
→ output validator
→ reference-id normalization fix
→ inspection
→ query CLI
```

Inspection script:

```text
scripts/validation/check_citation_reference_graph_inspection.py
```

Inspection documentation:

```text
docs/citation_reference_graph_inspection_v0.md
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_inspection.py
```

Required local graph inputs:

```text
data/graphs/citation_reference_graph/v0.1/nodes.jsonl
data/graphs/citation_reference_graph/v0.1/edges.jsonl
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
```

Recommended validation sequence:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_inspection.py
python -m pytest tests/smoke/test_citation_reference_graph_inspection.py -q
python -m scripts.validation.check_citation_reference_graph_inspection --strict
```

Expected current result:

```text
7 passed

{
  "ok": true,
  "required_failed_count": 0,
  "total_checks": 35,
  "warning_count": 0
}
```

Accepted local inspection counters after the reference-id normalization fix:

```text
nodes_count = 529295
edges_count = 745516
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference_resolution_ratio = 0.00869
```

Current v0.1 interpretation:

```text
reference_resolution_ratio ≈ 0.87%
Most explicit references remain unresolved external_reference evidence.
This is a quality/coverage diagnostic, not a failure of the inspection slice.
Internal paper→paper reference edges remain conservative resolved links only.
OpenAlex references from `referenced_ids` are now normalized as `openalex_id`, not DOI-like URL values.
```

The inspection report computes:

```text
resolved versus unresolved reference edges
reference_resolution_ratio
papers with outgoing reference edges
papers with internal reference edges
papers with external reference edges
papers with incoming internal reference edges
papers without outgoing explicit reference edges
reference type distribution
reference field distribution
source-family distribution
top referenced canonical papers
top external references
sample paper→paper edges
sample paper→external_reference edges
```

Generated reports:

```text
artifacts/reports/validation/citation_reference_graph_inspection_latest.json
artifacts/reports/validation/citation_reference_graph_inspection_latest.md
artifacts/reports/validation/history/citation_reference_graph_inspection_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_inspection_<run_ts>.md
```

## Citation / Reference Graph Query CLI v0.1 validation

Use this when checking the accepted read-only offline query CLI over the generated Citation / Reference Graph v0.1 output. The CLI reads the local graph output and does not rebuild graph output, write validation reports, change canonical truth, mutate DB state, change API/UI behavior, or require NetworkX/Neo4j/GraphRAG runtime.

CLI script:

```text
scripts/graph/query_citation_reference_graph.py
```

CLI documentation:

```text
docs/citation_reference_graph_query_cli_v0.md
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_query_cli.py
```

Recommended validation sequence:

```bat
python -m py_compile scripts/graph/query_citation_reference_graph.py
python -m pytest tests/smoke/test_citation_reference_graph_query_cli.py -q
python -m scripts.graph.query_citation_reference_graph --top-referenced-papers --top-k 5
python -m scripts.graph.query_citation_reference_graph --top-external-references --top-k 5 --format markdown
```

Expected current result:

```text
8 passed
JSON output returns found=true for top referenced papers
Markdown output returns found=true for top external references
```

Accepted current graph/query counters:

```text
nodes_count = 529295
edges_count = 745516
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference_resolution_ratio = 0.00869
```

Supported query modes:

```text
paper -> outgoing references
paper <- incoming internal citing papers
external_reference -> citing papers
top internal referenced canonical papers
top unresolved external references
source_family -> reference-bearing papers
```

Important v0.1 caveat:

```text
The graph is built from explicit canonical metadata reference fields only.
It does not parse paper full text, PDFs, HTML body text, bibliography/reference sections, in-text citation contexts, or raw reference strings without metadata identifiers.
Unresolved references are preserved as external_reference nodes.
Low internal resolution ratio is expected for v0.1.
```

Important boundary:

```text
The citation/reference graph inspection layer is read-only.
It must not rebuild graph output.
It must not publish anything.
It must not package anything.
It must not change canonical truth.
It must not run reconcile.
It must not mutate Postgres.
It must not change DB schema.
It must not change API behavior.
It must not change Streamlit behavior.
It must not change retrieval behavior.
It must not change Qdrant behavior.
It must not change ranking behavior.
It must not require NetworkX/Neo4j/GraphRAG runtime.
It must not be used as a reconcile input.
It does not add a DoD required gate in this slice.
Generated reports are not committed.
```

## Related graph validators

Use these when debugging already completed graph-line components, not as part of ordinary citation/reference inspection edits:

```bat
python -m scripts.validation.check_citation_reference_graph_contract --strict
python -m scripts.validation.check_citation_reference_graph_contract --strict --check-paths
python -m scripts.validation.check_citation_reference_graph_output --strict
python -m scripts.graph.query_citation_reference_graph --top-referenced-papers --top-k 5
python -m scripts.graph.query_citation_reference_graph --top-external-references --top-k 5 --format markdown
python -m scripts.validation.check_paper_artifact_graph_output --strict
python -m scripts.validation.check_paper_artifact_graph_inspection --strict
python -m scripts.validation.check_paper_artifact_graph_release_candidate --strict
python -m scripts.validation.check_paper_artifact_graph_package --strict
python -m scripts.validation.check_paper_artifact_graph_line_checkpoint --strict
python -m scripts.validation.check_paper_artifact_graph_manual_review --strict
python -m scripts.validation.check_paper_artifact_graph_analytics --strict
```


## Citation / Reference Graph Release Candidate v0.1 validation

Use this when checking the active read-only release-candidate readiness gate over the generated Citation / Reference Graph v0.1 output.

This validation reads the existing local graph output and latest validation reports. It does not rebuild graph output, package graph output, publish anything, change canonical truth, mutate DB state, change API/UI behavior, or require NetworkX/Neo4j/GraphRAG runtime.

Release-candidate script:

```text
scripts/validation/check_citation_reference_graph_release_candidate.py
```

Release-candidate documentation:

```text
docs/citation_reference_graph_release_candidate_v0.md
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_release_candidate.py
```

Required local graph inputs:

```text
data/graphs/citation_reference_graph/v0.1/nodes.jsonl
data/graphs/citation_reference_graph/v0.1/edges.jsonl
data/graphs/citation_reference_graph/v0.1/schema.json
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
data/graphs/citation_reference_graph/v0.1/README.md
data/graphs/citation_reference_graph/v0.1/checksums.txt
```

Strict-mode report inputs:

```text
artifacts/reports/validation/citation_reference_graph_output_latest.json
artifacts/reports/validation/citation_reference_graph_inspection_latest.json
```

Recommended validation sequence:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_release_candidate.py
python -m pytest tests/smoke/test_citation_reference_graph_release_candidate.py -q
python -m scripts.validation.check_citation_reference_graph_output --strict
python -m scripts.validation.check_citation_reference_graph_inspection --strict
python -m scripts.validation.check_citation_reference_graph_release_candidate --strict
```

Expected current result:

```text
6 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "warning_count": 0
}
```

Accepted local release-candidate counters:

```text
nodes_count = 529295
edges_count = 745516
paper_nodes_count = 60954
external_reference_nodes_count = 468336
source_family_nodes_count = 5
paper_references_paper_edges_count = 6165
paper_references_external_edges_count = 703234
paper_has_reference_source_family_edges_count = 36117
reference_resolution_ratio = 0.00869
```

Expected release-candidate verdict:

```text
technical_graph_candidate_ready = true
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Important boundary:

```text
The citation/reference graph release-candidate validator is read-only.
It must not rebuild graph output.
It must not package graph output.
It must not publish anything.
It must not change canonical truth.
It must not run reconcile.
It must not mutate Postgres.
It must not change DB schema.
It must not change API behavior.
It must not change Streamlit behavior.
It must not change retrieval behavior.
It must not change Qdrant behavior.
It must not change ranking behavior.
It must not require NetworkX/Neo4j/GraphRAG runtime.
It must not be used as a reconcile input.
Generated reports are not committed.
```


## Citation / Reference Graph Package v0.1 validation

Use this when checking the active local package candidate layer over the generated and release-candidate-validated Citation / Reference Graph v0.1 output.

This validation reads the existing local graph output, latest release-candidate report, and generated package files. It does not rebuild graph output, publish anything, change canonical truth, mutate DB state, change API/UI behavior, parse full text/PDFs/bibliography sections, or require NetworkX/Neo4j/GraphRAG runtime.

Package config:

```text
configs/citation_reference_graph_package.yaml
```

Package builder:

```text
scripts/export/package_citation_reference_graph.py
```

Package validator:

```text
scripts/validation/check_citation_reference_graph_package.py
```

Package documentation:

```text
docs/citation_reference_graph_package_v0.md
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_package.py
```

Required local graph inputs:

```text
data/graphs/citation_reference_graph/v0.1/nodes.jsonl
data/graphs/citation_reference_graph/v0.1/edges.jsonl
data/graphs/citation_reference_graph/v0.1/schema.json
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
data/graphs/citation_reference_graph/v0.1/README.md
data/graphs/citation_reference_graph/v0.1/checksums.txt
```

Required release-candidate input:

```text
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.md
```

Generated package output, not committed:

```text
data/graphs/citation_reference_graph/packages/v0.1/citation_reference_graph_v0.1.zip
data/graphs/citation_reference_graph/packages/v0.1/package_manifest.json
data/graphs/citation_reference_graph/packages/v0.1/README.md
data/graphs/citation_reference_graph/packages/v0.1/checksums.txt
```

Generated package validation reports, not committed:

```text
artifacts/reports/validation/citation_reference_graph_package_latest.json
artifacts/reports/validation/citation_reference_graph_package_latest.md
artifacts/reports/validation/history/citation_reference_graph_package_<run_ts>.json
artifacts/reports/validation/history/citation_reference_graph_package_<run_ts>.md
```

Recommended validation sequence:

```bat
python -m py_compile scripts/export/package_citation_reference_graph.py
python -m py_compile scripts/validation/check_citation_reference_graph_package.py
python -m pytest tests/smoke/test_citation_reference_graph_package.py -q
python -m scripts.validation.check_citation_reference_graph_release_candidate --strict
python -m scripts.export.package_citation_reference_graph --dry-run
python -m scripts.export.package_citation_reference_graph --force
python -m scripts.validation.check_citation_reference_graph_package --strict
```

Expected current result:

```text
5 passed

package dry-run:
dry_run = true
included_files_count = 9

package build:
ok = true
included_files_count = 9

package validator:
ok = true
required_failed_count = 0
warning_count = 0
```

Accepted package counters:

```text
nodes_count = 529295
edges_count = 745516
paper_nodes_count = 60954
external_reference_nodes_count = 468336
source_family_nodes_count = 5
paper_references_paper_edges_count = 6165
paper_references_external_edges_count = 703234
paper_has_reference_source_family_edges_count = 36117
reference_resolution_ratio = 0.00869
```

Expected package verdict:

```text
package_candidate_ready = true
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Important boundary:

```text
The citation/reference graph package builder does not rebuild graph output.
The citation/reference graph package validator is read-only.
The package must not publish anything.
The package must not change canonical truth.
The package must not run reconcile.
The package must not mutate Postgres.
The package must not change DB schema.
The package must not change API behavior.
The package must not change Streamlit behavior.
The package must not change retrieval behavior.
The package must not change Qdrant behavior.
The package must not change ranking behavior.
The package must not parse full text, PDFs, or bibliography/reference sections.
The package must not require NetworkX/Neo4j/GraphRAG runtime.
The package must not be used as a reconcile input.
Generated package output and reports are not committed.
```


## Citation / Reference Graph Line Checkpoint v0.1 validation

Use this when checking the active read-only line checkpoint over the completed local Citation / Reference Graph v0.1 line.

This validation reads existing graph output, existing package output, and latest validation reports. It does not rebuild graph output, rebuild package output, publish anything, change canonical truth, mutate DB state, change API/UI behavior, or require NetworkX/Neo4j/GraphRAG runtime.

Line-checkpoint script:

```text
scripts/validation/check_citation_reference_graph_line_checkpoint.py
```

Line-checkpoint documentation:

```text
docs/citation_reference_graph_line_checkpoint_v0.md
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_line_checkpoint.py
```

Recommended validation sequence:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_line_checkpoint.py
python -m pytest tests/smoke/test_citation_reference_graph_line_checkpoint.py -q
python -m scripts.validation.check_citation_reference_graph_line_checkpoint --strict
```

Expected current result:

```text
5 passed
ok = true
required_failed_count = 0
warning_count = 0
```

Required existing local inputs:

```text
data/graphs/citation_reference_graph/v0.1/
data/graphs/citation_reference_graph/packages/v0.1/
artifacts/reports/validation/citation_reference_graph_output_latest.json
artifacts/reports/validation/citation_reference_graph_inspection_latest.json
artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json
artifacts/reports/validation/citation_reference_graph_package_latest.json
```

Expected line-checkpoint verdict:

```text
citation_reference_graph_line_complete = true
line_checkpoint_ready = true
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Important boundary:

```text
The citation/reference graph line-checkpoint validator is read-only.
It must not rebuild graph output.
It must not rebuild package output.
It must not publish anything.
It must not change canonical truth.
It must not run reconcile.
It must not mutate Postgres.
It must not change DB schema.
It must not change API behavior.
It must not change Streamlit behavior.
It must not change retrieval behavior.
It must not change Qdrant behavior.
It must not change ranking behavior.
It must not require NetworkX/Neo4j/GraphRAG runtime.
It must not be used as a reconcile input.
Generated reports are not committed.
```


## Citation / Reference Graph Manual Review Checklist v0.1 validation

Use this when checking the active read-only manual-review governance gate over the completed local Citation / Reference Graph v0.1 line and package candidate.

This validation reads the line checkpoint report and package manifest. It does not rebuild graph output, rebuild package output, publish anything, change canonical truth, run reconcile, mutate DB state, change API/UI behavior, or require NetworkX/Neo4j/GraphRAG runtime.

Manual-review script:

```text
scripts/validation/check_citation_reference_graph_manual_review.py
```

Manual-review documentation:

```text
docs/citation_reference_graph_manual_review_v0.md
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_manual_review.py
```

Required local inputs:

```text
artifacts/reports/validation/citation_reference_graph_line_checkpoint_latest.json
data/graphs/citation_reference_graph/packages/v0.1/package_manifest.json
```

Recommended validation sequence:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_manual_review.py
python -m pytest tests/smoke/test_citation_reference_graph_manual_review.py -q
python -m scripts.validation.check_citation_reference_graph_manual_review --strict
```

Expected current result:

```text
ok = true
required_failed_count = 0
warning_count = 0
manual_review_required = true
manual_review_complete = false
publication_ready = false
publication_block_reason = manual_review_not_completed
```

Important v0.1 semantics:

```text
pending categories block publication
pending categories do not fail the validator
summary.ok=true means the gate is structurally valid, not that review is complete
```

Citation/reference-specific caveats preserved by the gate:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
raw_reference_strings_without_identifiers_parsed = false
unresolved_references_preserved_as_external_reference_nodes = true
reference_resolution_ratio = 0.00869
```

Important boundary:

```text
The citation/reference graph manual-review checklist is read-only.
It must not rebuild graph output.
It must not rebuild package output.
It must not publish anything.
It must not change canonical truth.
It must not run reconcile.
It must not mutate Postgres.
It must not change DB schema.
It must not change API behavior.
It must not change Streamlit behavior.
It must not change retrieval behavior.
It must not change Qdrant behavior.
It must not change ranking behavior.
It must not require NetworkX/Neo4j/GraphRAG runtime.
It must not parse full text, PDFs, or bibliography/reference sections.
It must not be used as a reconcile input.
Generated reports are not committed.
```


## Citation / Reference Graph Analytics v0.1 validation

Use this when checking the active read-only analytics/report layer over the completed local Citation / Reference Graph v0.1 line and manual-review gate.

This validation reads the generated graph output and latest manual-review report. It does not rebuild graph output, rebuild package output, publish anything, approve manual review, change canonical truth, run reconcile, mutate DB state, change API/UI behavior, or require NetworkX/Neo4j/GraphRAG runtime.

Analytics script:

```text
scripts/validation/check_citation_reference_graph_analytics.py
```

Analytics documentation:

```text
docs/citation_reference_graph_analytics_v0.md
```

Smoke tests:

```text
tests/smoke/test_citation_reference_graph_analytics.py
```

Required local inputs:

```text
data/graphs/citation_reference_graph/v0.1/nodes.jsonl
data/graphs/citation_reference_graph/v0.1/edges.jsonl
data/graphs/citation_reference_graph/v0.1/manifest.json
data/graphs/citation_reference_graph/v0.1/data_quality_summary.json
artifacts/reports/validation/citation_reference_graph_manual_review_latest.json
```

Recommended validation sequence:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_analytics.py
python -m pytest tests/smoke/test_citation_reference_graph_analytics.py -q
python -m scripts.validation.check_citation_reference_graph_analytics --strict
```

Expected current result:

```text
ok = true
required_failed_count = 0
warning_count = 0
nodes_count = 529295
edges_count = 745516
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference_resolution_ratio = 0.00869
```

Computed analytics include:

```text
resolved versus unresolved reference edges
reference_resolution_ratio
papers with outgoing reference edges
papers with internal reference edges
papers with external reference edges
papers with incoming internal reference edges
papers without outgoing explicit reference edges
reference type distribution
reference field distribution
source-family distribution
top referenced canonical papers
top external references
sample paper→paper edges
sample paper→external_reference edges
manual-review caveat summary
```

Citation/reference-specific caveats preserved by the analytics layer:

```text
metadata_reference_fields_only = true
full_text_parsed = false
pdfs_parsed = false
bibliography_sections_parsed = false
raw_reference_strings_without_identifiers_parsed = false
unresolved_references_preserved_as_external_reference_nodes = true
reference_resolution_ratio = 0.00869
```

Important boundary:

```text
The citation/reference graph analytics layer is read-only.
It must not rebuild graph output.
It must not rebuild package output.
It must not publish anything.
It must not approve manual review.
It must not change canonical truth.
It must not run reconcile.
It must not mutate Postgres.
It must not change DB schema.
It must not change API behavior.
It must not change Streamlit behavior.
It must not change retrieval behavior.
It must not change Qdrant behavior.
It must not change ranking behavior.
It must not require NetworkX/Neo4j/GraphRAG runtime.
It must not parse full text, PDFs, or bibliography/reference sections.
It must not be used as a reconcile input.
Generated reports are not committed.
```




# F. Citation Graph API disabled status endpoint validation

Use this when checking the first narrow Citation / Reference Graph API code
slice.

Current endpoint:

```text
GET /citation-graph/status
```

Current implementation state:

```text
status_only = true
disabled_by_default = true
feature_flag = ML_RADAR_CITATION_GRAPH_API_ENABLED
graph_runtime_loader = not implemented
graph_traversal_endpoints = not implemented
graph_db_materialization = not implemented
streamlit_graph_ui = not implemented
graphrag = not implemented
publication_ready = false
manual_review_required = true
```

Recommended validation sequence:

```bat
python -m py_compile services/api/settings.py services/api/schemas.py services/api/citation_graph_service.py services/api/app.py

set ML_RADAR_SEARCH_BACKEND=file
python -m pytest tests/integration/test_api_citation_graph_status.py -q
python -m pytest tests/integration/test_api_smoke.py -q
python -m pytest tests/integration/test_api_reload.py -q
python -m pytest tests/integration/test_api_search_filters.py -q
python -m pytest tests/integration/test_api_errors.py -q

set ML_RADAR_SEARCH_BACKEND=db
python -m pytest tests/integration/test_api_db_smoke.py -q
python -m pytest tests/integration/test_api_search_db_backend.py -q
python -m pytest tests/integration/test_api_citation_graph_status.py -q
```

Accepted local result for the completed slice:

```text
test_api_citation_graph_status.py = 3 passed
test_api_smoke.py = 7 passed
test_api_reload.py = 4 passed
test_api_search_filters.py = 7 passed
test_api_errors.py = 4 passed
test_api_db_smoke.py = 7 passed
test_api_search_db_backend.py = 2 passed
```

Boundary:

```text
The status endpoint is read-only.
It must not load graph nodes or edges.
It must not expose outgoing references or incoming citations.
It must not mutate canonical truth.
It must not mutate graph output/package/reports.
It must not mutate Postgres.
It must not change /search behavior.
It must not change Discovery API behavior.
It must not change Qdrant behavior.
It must not change ranking behavior.
It must not create Streamlit graph UI.
It must not implement GraphRAG.
It must not publish anything.
```

Recommended next slice:

```text
Citation Graph Status Compatibility Probe v0.1
```

The next slice should still remain status/compatibility-only and must not add
traversal endpoints.

---

# G. Artifact API filters validation and DoD gate

Use this when changing DB-backed Artifact API filters, artifact/date metadata
filtering, artifact-document links, or the Artifact API validation contract.

## Standalone validator

```bat
set ML_RADAR_SEARCH_BACKEND=db
python -m scripts.validation.check_artifact_api_filters --strict
```

Expected:

```text
ok = true
required_failed_count = 0
runtime_backend_mode = db
runtime_ready = true
runtime_db_connected = true
```

The validator checks:

```text
/runtime DB readiness
/artifacts?provider=github
/artifacts?has_github_metadata=true
/artifacts?github_status=found
stars_desc / forks_desc sort modes
min_stars
language
archived=false
pushed_desc / pushed_after
updated_desc / updated_before
invalid pushed/updated date ranges -> 400
/artifacts/{artifact_id}
/artifacts/{artifact_id}/papers
/documents?has_trusted_artifact=true
/documents?artifact_provider=github
/documents/{canonical_id}/artifacts?provider=github
```

Generated reports:

```text
artifacts/reports/validation/artifact_api_filters_check_latest.json
artifacts/reports/validation/artifact_api_filters_check_latest.md
artifacts/reports/validation/history/artifact_api_filters_check_<timestamp>.json
artifacts/reports/validation/history/artifact_api_filters_check_<timestamp>.md
```

## DoD aggregation

The refresh DoD aggregator does not run the Artifact API validator itself. It
only reads the latest validation report.

Default optional/diagnostic DoD:

```bat
python -m scripts.update.check_refresh_definition_of_done ^
  --require-artifacts ^
  --require-github-enrichment
```

Required Artifact API filters gate:

```bat
python -m scripts.update.check_refresh_definition_of_done ^
  --require-artifacts ^
  --require-github-enrichment ^
  --require-artifact-api-filters
```

Expected required-gate verdict:

```text
artifact_api_filters_check_exists = true
artifact_api_filters_check_ok = true
artifact_api_filters_required_failed_count_zero = true
artifact_api_filters_required = true
dod_passed = true
required_failed_count = 0
```

Important boundary:

```text
Artifact API filters validation is derived/report-level evidence.
It does not change canonical truth, retrieval, Qdrant, ranking, enrichment
fetchers, Postgres schema, or Streamlit response schemas.
Generated reports are not committed.
```

## Regression runner integration

The Discovery API regression runner can generate the Artifact API filters report
before running the DoD aggregation step. This keeps the DoD aggregator as a
report reader while still giving one command for the common regression path.

DB-backed regression steps are guarded by an early preflight. When the runner is
called with `--include-artifact-api-filters` or `--include-db-smoke`, it first
checks the local DB environment before starting the longer file-backed
regression sequence.

The preflight verifies:

```text
configured backend mode resolves to db for the preflight
Postgres connection ping succeeds
canonical_documents exists and is non-empty
artifact_entities exists and is non-empty
paper_artifact_links exists and is non-empty
```

The preflight is intentionally read-only. It does not mutate canonical truth,
Postgres tables, retrieval artifacts, Qdrant, ranking, enrichment outputs, or
validation reports. It temporarily resolves DB settings for the preflight and
then restores the caller environment before running the normal regression steps.

Full local regression with Artifact API filters and DoD:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --include-artifact-api-filters ^
  --include-dod
```

When `--include-artifact-api-filters` and `--include-dod` are used together,
the runner forwards `--require-artifact-api-filters` to the DoD command.

Use a shorter local variant when similar-paper rebuilding is not in scope:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-artifact-api-filters ^
  --include-dod
```

Expected preflight output in a healthy local DB environment:

```text
[RUN] db_runtime_preflight
[INFO] DB-backed regression steps require Postgres and ML_RADAR_SEARCH_BACKEND=db.
[OK] configured_backend_mode=db
[OK] db_preflight_ping=True
[OK] db_preflight_table_exists_canonical_documents=True
[OK] db_preflight_table_rows_canonical_documents=60954
[OK] db_preflight_table_exists_artifact_entities=True
[OK] db_preflight_table_rows_artifact_entities=7333
[OK] db_preflight_table_exists_paper_artifact_links=True
[OK] db_preflight_table_rows_paper_artifact_links=7430
[OK] db_runtime_preflight passed
```

If Postgres is stopped or unreachable, the runner should fail before the long
regression sequence and print the recommended recovery action, for example:

```bat
docker compose -f infra/docker/docker-compose.yml up -d postgres
```

## Regression runner summary report

The Discovery API regression runner writes a lightweight report for the runner
execution itself. This is separate from reports produced by individual validators.

Generated reports:

```text
artifacts/reports/validation/discovery_api_regression_runner_latest.json
artifacts/reports/validation/discovery_api_regression_runner_latest.md
artifacts/reports/validation/history/discovery_api_regression_runner_<timestamp>.json
artifacts/reports/validation/history/discovery_api_regression_runner_<timestamp>.md
```

The report records:

```text
schema_version = discovery_api_regression_runner_report_v1
selected CLI inputs
overall ok / failed step count / total duration
step name
step kind
step command
step environment override
step return code
step duration
step ok flag
failed steps
whether execution stopped after first failure
```

DB preflight is included as a reportable `preflight` step when DB-backed
regression steps are selected. Normal validator commands are included as
`subprocess` steps.

Validation example:

```bat
python -m scripts.validation.run_discovery_api_regression ^
  --skip-similar-rebuild ^
  --include-artifact-api-filters ^
  --include-dod

python -c "import json; p='artifacts/reports/validation/discovery_api_regression_runner_latest.json'; r=json.load(open(p, encoding='utf-8')); assert r['schema_version']=='discovery_api_regression_runner_report_v1'; assert r['summary']['ok'] is True; assert r['summary']['failed_steps_count']==0; assert any(s['name']=='db_runtime_preflight' for s in r['steps']); print('runner summary ok')"
```

Expected healthy report summary:

```text
summary.ok = true
summary.failed_steps_count = 0
verdict.failed_steps = []
db_runtime_preflight present when DB-backed steps are selected
check_artifact_api_filters present when --include-artifact-api-filters is selected
strict_dod_with_discovery_api present when --include-dod is selected
```

Important boundary:

```text
The regression runner summary report is operational evidence.
It does not replace the individual validator reports.
It is not currently a DoD input.
Generated runner reports are not committed.
```

---


# H. Dataset release candidate validation

Use this when checking the metadata-only local dataset-release candidate track.
This validation does not publish a dataset and does not change canonical truth,
retrieval artifacts, Postgres serving state, Qdrant, ranking, API behavior, or
Streamlit behavior.

Current local candidate identity:

```text
dataset_name = ml_research_radar_metadata
version = v0.1
release_family = clean_research_metadata
publication_status = not_published
manual_review_required_before_publication = true
```

Expected generated local candidate layout:

```text
data/datasets_release/ml_research_radar_metadata/v0.1/
├── data.parquet
├── schema.json
├── manifest.json
├── README.md
├── data_quality_summary.json
└── checksums.txt
```

Recommended validation sequence:

```bat
python -m scripts.validation.check_dataset_release_config --strict --check-paths
python -m scripts.export.export_public_dataset --force
python -m scripts.validation.check_dataset_release_output --strict
python -m scripts.validation.check_dataset_release_review_readiness --strict
```

Expected final review-readiness state:

```text
technical_candidate_ready = true
manual_review_required = true
publication_ready = false
publication_block_reason = manual_review_not_completed
required_failed_count = 0
```

Important boundary:

```text
The generated dataset directory is a local candidate artifact.
It is not a public release.
It must not be used as a reconcile input.
It must not overwrite operational latest files.
It must not be committed by default.
Public upload requires a separate manual license/provenance review and release decision.
```

Generated reports:

```text
artifacts/reports/validation/dataset_release_config_latest.json
artifacts/reports/validation/dataset_release_output_latest.json
artifacts/reports/validation/dataset_release_review_readiness_latest.json
artifacts/reports/validation/history/dataset_release_*.json
```

Generated report history should not be committed unless a separate
artifact-retention policy explicitly says otherwise.

# I. Qdrant validation layers

## Qdrant collection check

```bat
python -m scripts.validation.check_qdrant_collection --strict
```

Expected current-green state:

```text
collection_name = ml_radar_dense_benchmark_v1
collection_exists = true
points_count = 60954
corpus_doc_count = 60954
required_failed_count = 0
```

## Qdrant serving POC checks

Use after a Qdrant benchmark has already created the benchmark collection.

```bat
python -m scripts.validation.check_qdrant_collection --strict
python -m scripts.evaluation.compare_qdrant_file_dense
python -m scripts.validation.check_qdrant_file_dense_comparison --strict
```

Expected current-green state:

```text
mean_overlap_ratio_at_k = 1.0
min_overlap_ratio_at_k = 1.0
required_failed_count = 0
```

These checks validate an existing collection. They do not recreate the collection or upload vectors.

## Full Qdrant benchmark

Use only when intentionally rebuilding/revalidating the vector-serving benchmark collection:

```bat
python -m scripts.evaluation.run_qdrant_retrieval_benchmark
python -m scripts.validation.check_qdrant_retrieval_benchmark --strict
```

This is heavier than the serving POC checks.

## Experimental Qdrant API endpoint

```bat
python -m scripts.validation.check_qdrant_api_experimental --strict
```

Expected:

```text
status_code = 200
mode = dense_qdrant
collection_name = ml_radar_dense_benchmark_v1
result_count > 0
required_failed_count = 0
```

Important boundaries:

```text
/search remains unchanged.
SearchRuntime remains unchanged.
ML_RADAR_SEARCH_BACKEND remains file/db.
Qdrant is not the production default backend.
```

---

# J. Discovery API regression runner

Quick discovery regression:

```bat
set ML_RADAR_SEARCH_BACKEND=file
python -m scripts.validation.run_discovery_api_regression
```

Common variants:

```bat
python -m scripts.validation.run_discovery_api_regression --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments
python -m scripts.validation.run_discovery_api_regression --include-retrieval-eval --include-search-quality-experiments --include-controlled-search-quality-experiments
python -m scripts.validation.run_discovery_api_regression --include-qdrant-serving-poc --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-qdrant-api --include-qdrant-serving-poc --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-qdrant-benchmark --include-qdrant-serving-poc --include-qdrant-api --skip-similar-rebuild
python -m scripts.validation.run_discovery_api_regression --include-db-smoke --include-dod
python -m scripts.validation.run_discovery_api_regression --include-artifact-api-filters --include-dod
python -m scripts.validation.run_discovery_api_regression --skip-similar-rebuild --include-artifact-api-filters --include-dod
python -m scripts.validation.run_discovery_api_regression --include-live-ui-check
```

---

# K. Strict Definition of Done

Current full strict DoD command should include the active required gates supported by the current project codebase:

```bat
python -m scripts.update.check_refresh_definition_of_done --require-known-issues --require-artifacts --require-artifact-api-filters --require-github-enrichment --require-huggingface-enrichment --require-paper-features --require-similar-papers --require-discovery-api --require-topic-clusters --require-topic-projection --require-streamlit-discovery-ui --require-golden-queries
```

Expected:

```text
dod_passed = true
required_failed_count = 0
```

Citation / Reference Graph Inspection v0.1, Query CLI v0.1, Release Candidate v0.1, and Package v0.1 are intentionally not required strict DoD gates in this package slice. They have their own validators, smoke tests, and CLI smoke commands. DoD integration should be reconsidered only after citation/reference graph-line checkpoint evidence exists.

If local `--help` does not show these gates, sync the DoD script before treating local docs as current.

---

# L. Hugging Face / VPN caveat

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

# M. Git / artifact hygiene

Do not commit large generated artifacts by default:

```text
data/raw/
data/normalized/
data/analytics/reconciled/canonical_documents.jsonl
data/features/paper_features_latest.jsonl
artifacts/retrieval/dense/*.npy
artifacts/retrieval/lexical/*.pkl
artifacts/reports/**/history/
Postgres dumps
Qdrant storage
```

Prefer committing:

```text
code
configs
docs
tests
small sample fixtures
small latest JSON reports only when intentionally used as documentation evidence
```

Before committing:

```bat
git status --short
git diff --stat
git diff --cached --stat
```

---

# N. Blockers

Stop and investigate if any of these occur:

- reconcile uses unsafe/incomplete inputs;
- canonical doc count collapses unexpectedly;
- arXiv backbone is unexpectedly reduced;
- multisource docs collapse unexpectedly;
- duplicate canonical IDs appear;
- required canonical fields disappear;
- promotion fails;
- Postgres export/read smoke fails;
- retrieval manifest doc count mismatches canonical;
- retrieval checks fail;
- artifact quality/export/DB read fails;
- Artifact API filters validation fails when the gate is in scope;
- GitHub/HF enrichment strict checks fail outside known provider-state caveats;
- paper features rows do not match canonical;
- similar papers target/result checks fail;
- Discovery API quality fails;
- topic clusters/projection quality fails;
- Streamlit UI quality fails;
- Qdrant collection points mismatch current corpus;
- `/runtime.qdrant` reports `points_match_corpus=false` unexpectedly;
- strict DoD fails.

---

# O. Non-blocker diagnostics under current semantics

These are not automatic blockers unless policy changes:

```text
doc_ids_shorter_than_sources
repeated source families in provenance lists
arxiv_id present without a direct arXiv provenance row when provenance semantics explain it
source_ids containing more families than sources
Hugging Face forbidden provider states
Hugging Face skipped_invalid_external_id extraction/noise states
GitHub not_found repositories preserved as historical artifact evidence
heuristic topic label_candidates being imperfect
Qdrant unavailable during file runtime when Qdrant-specific checks are not in scope
Low citation/reference `reference_resolution_ratio` in v0.1 inspection when output validator remains green
```

---

## Final operational rule

```text
Viability first, candidate integration second, stable integration last.
```

<!-- PAPER_ARTIFACT_GRAPH_BUILDER_V01_START -->
## Paper-Artifact Graph Builder v0.1 checkpoint

Status: local derived graph builder implemented and validated.

New tracked files:

- `configs/paper_artifact_graph_builder.yaml`
- `radar_core/artifacts/__init__.py`
- `radar_core/artifacts/trusted_links.py`
- `scripts/export/build_paper_artifact_graph.py`
- `scripts/validation/check_paper_artifact_graph_builder_config.py`
- `scripts/validation/check_paper_artifact_graph_output.py`
- `tests/smoke/test_trusted_artifact_links.py`
- `tests/smoke/test_paper_artifact_graph_builder_config.py`
- `tests/smoke/test_paper_artifact_graph_builder.py`
- `tests/smoke/test_paper_artifact_graph_output_validator.py`
- `docs/paper_artifact_graph_builder_v0.md`

Generated local output, not committed:

- `data/graphs/paper_artifact_graph/v0.1/nodes.jsonl`
- `data/graphs/paper_artifact_graph/v0.1/edges.jsonl`
- `data/graphs/paper_artifact_graph/v0.1/schema.json`
- `data/graphs/paper_artifact_graph/v0.1/manifest.json`
- `data/graphs/paper_artifact_graph/v0.1/data_quality_summary.json`
- `data/graphs/paper_artifact_graph/v0.1/README.md`
- `data/graphs/paper_artifact_graph/v0.1/checksums.txt`

Git ignore update:

- `/artifacts/` ignores root generated reports/artifacts only
- `/data/graphs/` ignores generated local graph outputs
- `radar_core/artifacts/` is intentionally tracked

Validated commands:

```bat
python -m py_compile radar_core/artifacts/trusted_links.py
python -m py_compile scripts/export/build_paper_artifact_graph.py
python -m py_compile scripts/export/export_artifacts_postgres_v1.py
python -m py_compile scripts/validation/check_artifact_links_quality.py
python -m py_compile scripts/validation/check_paper_artifact_graph_builder_config.py
python -m py_compile scripts/validation/check_paper_artifact_graph_output.py

python -m pytest tests/smoke/test_trusted_artifact_links.py tests/smoke/test_paper_artifact_graph_builder_config.py tests/smoke/test_paper_artifact_graph_builder.py tests/smoke/test_paper_artifact_graph_output_validator.py -q

python -m scripts.validation.check_artifact_links_quality --strict
python -m scripts.validation.check_paper_artifact_graph_builder_config --strict
python -m scripts.validation.check_paper_artifact_graph_builder_config --strict --check-paths
python -m scripts.validation.check_paper_artifact_graph_output --strict
```

Expected result:

```text
34 passed
ok=True
required_failed_count=0
required_failed_checks=[]
```

Accepted local graph output counters:

```text
nodes_count=68385
edges_count=163757
paper=60954
artifact=7336
provider=10
source_family=5
topic_cluster=80
paper_has_artifact=7430
paper_assigned_to_topic_cluster=60954
artifact_from_provider=7336
paper_observed_in_source_family=88037
trusted_links_used_count=7430
topic_edges_count=60954
skipped_trusted_links_missing_paper=0
skipped_trusted_links_missing_artifact=0
topic_assignments_missing_paper=0
topic_assignments_missing_cluster=0
```

Boundary notes:

- graph is derived representation, not canonical truth
- graph must not be used as reconcile input
- builder is file-first
- no live DB dependency
- no public API change
- no Qdrant/retrieval/ranking change
- no latest pointer
- no global trusted-links bridge
- graph output remains local/generated and ignored by Git
<!-- PAPER_ARTIFACT_GRAPH_BUILDER_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_INSPECTION_V01_START -->
## Paper-Artifact Graph Inspection v0.1 checkpoint

Status: local read-only inspection layer implemented and validated.

Tracked files:

- `scripts/validation/check_paper_artifact_graph_inspection.py`
- `tests/smoke/test_paper_artifact_graph_inspection.py`
- `docs/paper_artifact_graph_inspection_v0.md`

Generated reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_inspection_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_inspection_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_inspection_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_inspection_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_inspection.py
python -m pytest tests/smoke/test_paper_artifact_graph_inspection.py -q
python -m scripts.validation.check_paper_artifact_graph_inspection --strict
```

Expected result:

```text
3 passed
ok=True
required_failed_count=0
```

Accepted local inspection counters:

```text
nodes_count=68385
edges_count=163757
papers_with_artifacts_count=6673
topic_clusters_with_artifact_ready_papers_count=80
```

Boundary notes:

- inspection is read-only
- graph remains derived representation, not canonical truth
- graph must not be used as reconcile input
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- generated inspection reports are ignored and not committed
<!-- PAPER_ARTIFACT_GRAPH_INSPECTION_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_QUERY_CLI_V01_START -->
## Paper-Artifact Graph Query CLI v0.1 checkpoint

Status: local read-only query CLI implemented and validated.

Tracked files:

- `scripts/graph/__init__.py`
- `scripts/graph/query_paper_artifact_graph.py`
- `tests/smoke/test_paper_artifact_graph_query_cli.py`
- `docs/paper_artifact_graph_query_cli_v0.md`

Validation commands:

```bat
python -m py_compile scripts/graph/query_paper_artifact_graph.py
python -m pytest tests/smoke/test_paper_artifact_graph_query_cli.py -q
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5
python -m scripts.graph.query_paper_artifact_graph --provider github --top-k 5 --format markdown
python -m scripts.graph.query_paper_artifact_graph --topic-cluster 7 --top-k 5
```

Expected result:

```text
7 passed
provider query returns found=True
topic-cluster query returns found=True
```

Accepted local provider-query counters:

```text
provider=github
artifacts=5953
paper_artifact_links=6019
```

Accepted local topic-cluster query counters:

```text
topic_cluster=7
papers=465
artifact_ready_papers=21
paper_artifact_links=21
```

Boundary notes:

- CLI is read-only
- graph remains derived representation, not canonical truth
- graph must not be used as reconcile input
- no graph rebuild
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no generated reports are written by the CLI
<!-- PAPER_ARTIFACT_GRAPH_QUERY_CLI_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_RELEASE_CANDIDATE_V01_START -->
## Paper-Artifact Graph Release Candidate v0.1 checkpoint

Status: local read-only release-candidate readiness gate implemented and validated.

Tracked files:

- `scripts/validation/check_paper_artifact_graph_release_candidate.py`
- `tests/smoke/test_paper_artifact_graph_release_candidate.py`
- `docs/paper_artifact_graph_release_candidate_v0.md`

Generated reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_release_candidate_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_release_candidate_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_release_candidate.py
python -m pytest tests/smoke/test_paper_artifact_graph_release_candidate.py -q
python -m scripts.validation.check_paper_artifact_graph_release_candidate --strict
```

Expected result:

```text
5 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 12,
  "warning_count": 0
}
```

Expected release-candidate verdict:

```text
technical_graph_candidate_ready=true
manual_review_required=true
publication_ready=false
publication_block_reason=manual_review_not_completed
required_failed_checks=[]
warning_checks=[]
```

The validator checks:

```text
graph output files exist
graph JSON/JSONL files are readable
manifest safety flags preserve derived-layer boundaries
builder input mode is file
data_quality_summary.ok is true
duplicate node/edge IDs are absent
accepted graph v0.1 counters match
checksums match
inspection report is ok in strict mode
GitHub provider smoke counters match accepted diagnostics
```

Accepted local graph counters:

```text
nodes_count=68385
edges_count=163757
paper=60954
artifact=7336
provider=10
source_family=5
topic_cluster=80
paper_has_artifact=7430
artifact_from_provider=7336
paper_observed_in_source_family=88037
paper_assigned_to_topic_cluster=60954
```

Accepted local inspection counters:

```text
papers_with_artifacts_count=6673
topic_clusters_with_artifact_ready_papers_count=80
```

Accepted local provider smoke counters:

```text
provider=github
artifacts=5953
paper_artifact_links=6019
```

Boundary notes:

- release-candidate validator is read-only
- graph remains derived representation, not canonical truth
- graph must not be used as reconcile input
- no graph rebuild
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no dataset publication
- generated validation reports are ignored and not committed
<!-- PAPER_ARTIFACT_GRAPH_RELEASE_CANDIDATE_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_PACKAGE_V01_START -->
## Paper-Artifact Graph Package v0.1 checkpoint

Status: local package candidate layer implemented and validated.

Tracked files:

- `configs/paper_artifact_graph_package.yaml`
- `scripts/export/package_paper_artifact_graph.py`
- `scripts/validation/check_paper_artifact_graph_package.py`
- `tests/smoke/test_paper_artifact_graph_package.py`
- `docs/paper_artifact_graph_package_v0.md`

Generated local package output, not committed:

- `data/graphs/paper_artifact_graph/packages/v0.1/paper_artifact_graph_v0.1.zip`
- `data/graphs/paper_artifact_graph/packages/v0.1/package_manifest.json`
- `data/graphs/paper_artifact_graph/packages/v0.1/README.md`
- `data/graphs/paper_artifact_graph/packages/v0.1/checksums.txt`

Generated validation reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_package_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_package_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_package_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_package_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/export/package_paper_artifact_graph.py
python -m py_compile scripts/validation/check_paper_artifact_graph_package.py
python -m pytest tests/smoke/test_paper_artifact_graph_package.py -q
python -m scripts.export.package_paper_artifact_graph --dry-run
python -m scripts.export.package_paper_artifact_graph --force
python -m scripts.validation.check_paper_artifact_graph_package --strict
```

Expected result:

```text
5 passed

package build:
ok=true
included_files_count=9
zip_size_bytes=14930380

package validator:
{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 10,
  "warning_count": 0
}
```

Expected archive members:

```text
paper_artifact_graph_v0.1/nodes.jsonl
paper_artifact_graph_v0.1/edges.jsonl
paper_artifact_graph_v0.1/schema.json
paper_artifact_graph_v0.1/manifest.json
paper_artifact_graph_v0.1/data_quality_summary.json
paper_artifact_graph_v0.1/README.md
paper_artifact_graph_v0.1/checksums.txt
paper_artifact_graph_v0.1/validation/paper_artifact_graph_release_candidate_latest.json
paper_artifact_graph_v0.1/validation/paper_artifact_graph_release_candidate_latest.md
```

The package validator checks:

```text
package files exist
package manifest is readable
package manifest schema is correct
package safety flags preserve candidate boundaries
package boundaries preserve project invariants
embedded release-candidate summary is green
packaged graph counters match accepted v0.1 baseline
package checksums match
zip archive is readable
zip contains all manifest-listed included files
```

Accepted local graph counters:

```text
nodes_count=68385
edges_count=163757
paper=60954
artifact=7336
provider=10
source_family=5
topic_cluster=80
paper_has_artifact=7430
artifact_from_provider=7336
paper_observed_in_source_family=88037
paper_assigned_to_topic_cluster=60954
```

Boundary notes:

- package builder is local and conservative
- package builder requires a green release-candidate report
- package builder does not rebuild graph output
- package validator is read-only
- graph remains derived representation, not canonical truth
- graph/package must not be used as reconcile input
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no dataset publication
- generated package output and validation reports are ignored and not committed
<!-- PAPER_ARTIFACT_GRAPH_PACKAGE_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_LINE_CHECKPOINT_V01_START -->
## Paper-Artifact Graph Line Checkpoint v0.1 checkpoint

Status: local read-only line checkpoint implemented and validated.

Tracked files:

- `configs/paper_artifact_graph_line_checkpoint.yaml`
- `scripts/validation/check_paper_artifact_graph_line_checkpoint.py`
- `tests/smoke/test_paper_artifact_graph_line_checkpoint.py`
- `docs/paper_artifact_graph_line_checkpoint_v0.md`

Generated validation reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_line_checkpoint_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_line_checkpoint_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_line_checkpoint_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_line_checkpoint_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_line_checkpoint.py
python -m pytest tests/smoke/test_paper_artifact_graph_line_checkpoint.py -q
python -m scripts.validation.check_paper_artifact_graph_line_checkpoint --strict
```

Expected result:

```text
4 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 14,
  "warning_count": 0
}
```

The checkpoint validates that the following completed graph-line components are present and internally consistent:

```text
contract
builder
output validator
inspection
query CLI
release candidate
package
```

The line checkpoint checks:

```text
line checkpoint config schema
required graph-line tracked files are present
required graph output files are present
graph manifest is readable
graph manifest safety flags preserve derived-layer boundaries
graph counters match accepted checkpoint baseline
inspection report is green
release-candidate report is green
package report is green
required package files are present
package manifest is readable
package manifest safety flags preserve checkpoint boundaries
package zip is readable
checkpoint config safety flags preserve project boundaries
```

Accepted local graph counters:

```text
nodes_count=68385
edges_count=163757
paper=60954
artifact=7336
provider=10
source_family=5
topic_cluster=80
paper_has_artifact=7430
artifact_from_provider=7336
paper_observed_in_source_family=88037
paper_assigned_to_topic_cluster=60954
trusted_links_used_count=7430
topic_edges_count=60954
```

Boundary notes:

- checkpoint validator is read-only
- graph remains derived representation, not canonical truth
- graph/package/checkpoint must not be used as reconcile input
- no graph rebuild
- no package rebuild
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no dataset publication
- no latest pointer
- no graph runtime
- generated checkpoint reports are ignored and not committed
<!-- PAPER_ARTIFACT_GRAPH_LINE_CHECKPOINT_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_MANUAL_REVIEW_V01_START -->
## Paper-Artifact Graph Manual Review Checklist v0.1 checkpoint

Status: local read-only manual-review gate implemented and validated.

Tracked files:

- `configs/paper_artifact_graph_manual_review.yaml`
- `scripts/validation/check_paper_artifact_graph_manual_review.py`
- `tests/smoke/test_paper_artifact_graph_manual_review.py`
- `docs/paper_artifact_graph_manual_review_v0.md`

Generated validation reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_manual_review_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_manual_review_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_manual_review_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_manual_review_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_manual_review.py
python -m pytest tests/smoke/test_paper_artifact_graph_manual_review.py -q
python -m scripts.validation.check_paper_artifact_graph_manual_review --strict
```

Expected result:

```text
9 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 20,
  "warning_count": 0
}
```

Key semantic contract:

```text
pending categories block publication
pending categories do not fail the validator
```

Default verdict:

```text
manual_review_required=true
manual_review_complete=false
publication_ready=false
publication_block_reason=manual_review_not_completed
```

The validator checks:

```text
manual-review config schema
review metadata
approval_state validity
required category presence
category status validity
pending-category publication block semantics
line checkpoint report green
package manifest readable
package manifest safety flags
package remains publication_ready=false
manual-review safety flags preserve project boundaries
```

Boundary notes:

- validator is read-only
- pending manual-review categories are normal default state
- graph/package/manual-review reports remain derived evidence
- graph/package/manual-review must not be used as reconcile input
- no graph rebuild
- no package rebuild
- no publication
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no latest pointer
- no graph runtime
- no Neo4j/NetworkX/GraphRAG runtime
- no trusted-link policy redefinition
<!-- PAPER_ARTIFACT_GRAPH_MANUAL_REVIEW_V01_END -->

<!-- PAPER_ARTIFACT_GRAPH_ANALYTICS_V01_START -->
## Paper-Artifact Graph Analytics v0.1 checkpoint

Status: local read-only analytics/report layer implemented and validated.

Tracked files:

- `configs/paper_artifact_graph_analytics.yaml`
- `scripts/validation/check_paper_artifact_graph_analytics.py`
- `tests/smoke/test_paper_artifact_graph_analytics.py`
- `docs/paper_artifact_graph_analytics_v0.md`

Generated validation reports, not committed:

- `artifacts/reports/validation/paper_artifact_graph_analytics_latest.json`
- `artifacts/reports/validation/paper_artifact_graph_analytics_latest.md`
- `artifacts/reports/validation/history/paper_artifact_graph_analytics_<run_ts>.json`
- `artifacts/reports/validation/history/paper_artifact_graph_analytics_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/validation/check_paper_artifact_graph_analytics.py
python -m pytest tests/smoke/test_paper_artifact_graph_analytics.py -q
python -m scripts.validation.check_paper_artifact_graph_analytics --strict
```

Expected result:

```text
8 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "total_checks": 40,
  "warning_count": 0
}
```

The validator/report checks:

```text
analytics config schema
analytics safety flags
required graph files exist
manifest safety flags preserve derived-layer boundaries
data_quality_summary is green
node and edge type counters
paper-artifact link coverage
provider distribution over artifact nodes
provider distribution over paper-artifact edges
source-family distribution
topic-cluster artifact-ready paper coverage
top multi-paper artifacts
sample IDs for manual inspection
```

Boundary notes:

- analytics validator is read-only
- analytics reports are derived evidence
- graph/package/manual-review/analytics must not be used as reconcile input
- no graph rebuild
- no package rebuild
- no publication
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no latest pointer
- no graph runtime
- no Neo4j/NetworkX/GraphRAG runtime
- no trusted-link policy redefinition
- no manual approval state change
<!-- PAPER_ARTIFACT_GRAPH_ANALYTICS_V01_END -->

<!-- CITATION_REFERENCE_GRAPH_CONTRACT_V01_START -->
## Citation / Reference Graph Contract v0.1 checkpoint

Status: local contract-only citation/reference graph definition implemented and validated.

Tracked files:

- `configs/citation_reference_graph.yaml`
- `scripts/validation/check_citation_reference_graph_contract.py`
- `tests/smoke/test_citation_reference_graph_contract.py`
- `docs/citation_reference_graph_v0.md`

Generated validation reports, not committed:

- `artifacts/reports/validation/citation_reference_graph_contract_latest.json`
- `artifacts/reports/validation/citation_reference_graph_contract_latest.md`
- `artifacts/reports/validation/history/citation_reference_graph_contract_<run_ts>.json`
- `artifacts/reports/validation/history/citation_reference_graph_contract_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_contract.py
python -m pytest tests/smoke/test_citation_reference_graph_contract.py -q
python -m scripts.validation.check_citation_reference_graph_contract --strict
python -m scripts.validation.check_citation_reference_graph_contract --strict --check-paths
```

Expected result:

```text
10 passed

{
  "ok": true,
  "required_failed_count": 0,
  "total_checks": 48,
  "warning_count": 0
}

{
  "ok": true,
  "required_failed_count": 0,
  "total_checks": 50,
  "warning_count": 0
}
```

The contract validates:

```text
config schema version
contract-only status
source checkpoint declaration
required future node types
required future edge types
node and edge identity policies
reference-field policy
provenance kinds and source layers
future-layout-only output declaration
safety flags preserving project boundaries
optional path-aware canonical/retrieval input existence
```

Boundary notes:

- contract-only validator and documentation
- no builder
- no generated graph output
- no package
- no publication
- no manual approval
- no DB materialization
- no DB schema change
- no public graph API
- no Streamlit graph UI
- no NetworkX/Neo4j/GraphRAG runtime
- no canonical refresh/reconcile
- no retrieval rebuild
- no embedding model replacement
- no Qdrant promotion
- no ranking changes
- generated contract reports are ignored and not committed
<!-- CITATION_REFERENCE_GRAPH_CONTRACT_V01_END -->

<!-- CITATION_REFERENCE_GRAPH_BUILDER_V01_START -->
## Citation / Reference Graph Builder v0.1 checkpoint

Status: local file-first derived citation/reference graph builder and output validator implemented and validated.

Tracked files:

- `scripts/export/build_citation_reference_graph.py`
- `scripts/validation/check_citation_reference_graph_output.py`
- `tests/smoke/test_citation_reference_graph_builder.py`
- `tests/smoke/test_citation_reference_graph_output_validator.py`
- `docs/citation_reference_graph_builder_v0.md`

Generated local output, not committed:

- `data/graphs/citation_reference_graph/v0.1/nodes.jsonl`
- `data/graphs/citation_reference_graph/v0.1/edges.jsonl`
- `data/graphs/citation_reference_graph/v0.1/schema.json`
- `data/graphs/citation_reference_graph/v0.1/manifest.json`
- `data/graphs/citation_reference_graph/v0.1/data_quality_summary.json`
- `data/graphs/citation_reference_graph/v0.1/README.md`
- `data/graphs/citation_reference_graph/v0.1/checksums.txt`

Validation commands:

```bat
python -m py_compile scripts/export/build_citation_reference_graph.py
python -m py_compile scripts/validation/check_citation_reference_graph_output.py
python -m pytest tests/smoke/test_citation_reference_graph_builder.py tests/smoke/test_citation_reference_graph_output_validator.py -q
python -m scripts.export.build_citation_reference_graph --dry-run
python -m scripts.export.build_citation_reference_graph --force
python -m scripts.validation.check_citation_reference_graph_output --strict
```

Expected result after reference-id normalization fix:

```text
13 passed

builder:
ok = true
nodes_count = 529295
edges_count = 745516

output validator:
{
  "ok": true,
  "required_failed_count": 0,
  "total_checks": 36,
  "warning_count": 0
}
```

Accepted local graph counters:

```text
nodes_count = 529295
edges_count = 745516

paper = 60954
external_reference = 468336
source_family = 5

paper_references_paper = 6165
paper_references_external = 703234
paper_has_reference_source_family = 36117
```

Boundary notes:

- builder is file-first
- graph output is derived, local, and rebuildable
- graph output is not canonical truth
- graph output must not be used as reconcile input
- unresolved references remain external_reference nodes
- no DB materialization
- no DB schema change
- no public graph API
- no Streamlit graph UI
- no NetworkX/Neo4j/GraphRAG runtime
- no canonical refresh/reconcile
- no retrieval rebuild
- no embedding model replacement
- no Qdrant promotion
- no ranking changes
- generated graph output is ignored and not committed
<!-- CITATION_REFERENCE_GRAPH_BUILDER_V01_END -->

<!-- CITATION_REFERENCE_GRAPH_INSPECTION_V01_START -->
## Citation / Reference Graph Inspection v0.1 checkpoint

Status: local read-only citation/reference graph inspection/report layer implemented and validated.

Tracked files:

- `scripts/validation/check_citation_reference_graph_inspection.py`
- `tests/smoke/test_citation_reference_graph_inspection.py`
- `docs/citation_reference_graph_inspection_v0.md`

Generated validation reports, not committed:

- `artifacts/reports/validation/citation_reference_graph_inspection_latest.json`
- `artifacts/reports/validation/citation_reference_graph_inspection_latest.md`
- `artifacts/reports/validation/history/citation_reference_graph_inspection_<run_ts>.json`
- `artifacts/reports/validation/history/citation_reference_graph_inspection_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_inspection.py
python -m pytest tests/smoke/test_citation_reference_graph_inspection.py -q
python -m scripts.validation.check_citation_reference_graph_inspection --strict
```

Expected result:

```text
7 passed

{
  "ok": true,
  "required_failed_count": 0,
  "total_checks": 35,
  "warning_count": 0
}
```

Accepted local inspection counters:

```text
nodes_count = 529295
edges_count = 745516
resolved_reference_edges_count = 6165
unresolved_reference_edges_count = 703234
reference_resolution_ratio = 0.00869
```

The validator/report checks:

```text
required graph files exist
manifest safety flags preserve derived-layer boundaries
data_quality_summary is green
node and edge type counters
resolved versus unresolved reference edges
reference_resolution_ratio
papers with outgoing/internal/external/incoming reference evidence
papers without outgoing explicit reference edges
reference type and field distributions
source-family distribution
top referenced canonical papers
top external references
sample paper→paper and paper→external_reference edges
```

Boundary notes:

- inspection validator is read-only
- inspection reports are derived evidence
- graph/inspection must not be used as reconcile input
- no graph rebuild
- no package rebuild
- no publication
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no latest pointer
- no graph runtime
- no Neo4j/NetworkX/GraphRAG runtime
- generated inspection reports are ignored and not committed
<!-- CITATION_REFERENCE_GRAPH_INSPECTION_V01_END -->



<!-- CITATION_REFERENCE_GRAPH_QUERY_CLI_V01_START -->
## Citation / Reference Graph Query CLI v0.1 checkpoint

Status: local read-only offline query CLI implemented and validated.

Tracked files:

- `scripts/graph/query_citation_reference_graph.py`
- `tests/smoke/test_citation_reference_graph_query_cli.py`
- `docs/citation_reference_graph_query_cli_v0.md`

Validation commands:

```bat
python -m py_compile scripts/graph/query_citation_reference_graph.py
python -m pytest tests/smoke/test_citation_reference_graph_query_cli.py -q
python -m scripts.graph.query_citation_reference_graph --top-referenced-papers --top-k 5
python -m scripts.graph.query_citation_reference_graph --top-external-references --top-k 5 --format markdown
```

Expected result:

```text
8 passed
JSON output works
Markdown output works
```

Accepted current graph/query counters:

```text
nodes_count = 529295
edges_count = 745516
paper_references_paper = 6165
paper_references_external = 703234
reference_resolution_ratio = 0.00869
```

Boundary notes:

- CLI is read-only
- graph remains derived representation, not canonical truth
- graph must not be used as reconcile input
- no graph rebuild
- no generated validation reports by default
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no publication/package
- no Neo4j/NetworkX/GraphRAG runtime
<!-- CITATION_REFERENCE_GRAPH_QUERY_CLI_V01_END -->

<!-- CITATION_REFERENCE_GRAPH_RELEASE_CANDIDATE_V01_START -->
## Citation / Reference Graph Release Candidate v0.1 checkpoint

Status: local read-only release-candidate readiness gate implemented and validated.

Tracked files:

- `scripts/validation/check_citation_reference_graph_release_candidate.py`
- `tests/smoke/test_citation_reference_graph_release_candidate.py`
- `docs/citation_reference_graph_release_candidate_v0.md`

Generated validation reports, not committed:

- `artifacts/reports/validation/citation_reference_graph_release_candidate_latest.json`
- `artifacts/reports/validation/citation_reference_graph_release_candidate_latest.md`
- `artifacts/reports/validation/history/citation_reference_graph_release_candidate_<run_ts>.json`
- `artifacts/reports/validation/history/citation_reference_graph_release_candidate_<run_ts>.md`

Validation commands:

```bat
python -m py_compile scripts/validation/check_citation_reference_graph_release_candidate.py
python -m pytest tests/smoke/test_citation_reference_graph_release_candidate.py -q
python -m scripts.validation.check_citation_reference_graph_output --strict
python -m scripts.validation.check_citation_reference_graph_inspection --strict
python -m scripts.validation.check_citation_reference_graph_release_candidate --strict
```

Expected result:

```text
6 passed

{
  "ok": true,
  "required_failed_count": 0,
  "strict": true,
  "warning_count": 0
}
```

The validator checks:

```text
graph output files exist
schema/manifest/data_quality_summary are readable and safe
node and edge IDs are unique
edges reference existing nodes
edge confidence values are in [0, 1]
accepted post-normalization graph counters match
checksums match
OpenAlex references remain normalized as openalex_id
latest output validator report is green in strict mode
latest inspection report is green in strict mode
query CLI file exists
```

Accepted local graph counters:

```text
nodes_count=529295
edges_count=745516
paper=60954
external_reference=468336
source_family=5
paper_references_paper=6165
paper_references_external=703234
paper_has_reference_source_family=36117
reference_resolution_ratio=0.00869
```

Expected release-candidate verdict:

```text
technical_graph_candidate_ready=true
manual_review_required=true
manual_review_complete=false
publication_ready=false
publication_block_reason=manual_review_not_completed
```

Boundary notes:

- release-candidate validator is read-only
- graph remains derived representation, not canonical truth
- graph must not be used as reconcile input
- no graph rebuild
- no package rebuild
- no DB/Qdrant/API/UI/retrieval/ranking behavior change
- no dataset publication
- no latest pointer
- no graph runtime
- generated validation reports are ignored and not committed
<!-- CITATION_REFERENCE_GRAPH_RELEASE_CANDIDATE_V01_END -->


<!-- CITATION_REFERENCE_GRAPH_PACKAGE_V01_START -->
## Citation / Reference Graph Package v0.1

Status: implemented local package candidate layer.

This slice packages the already generated and already release-candidate-validated Citation / Reference Graph Builder v0.1 output into a local non-public portable archive.

Implemented files:

- `configs/citation_reference_graph_package.yaml`
- `scripts/export/package_citation_reference_graph.py`
- `scripts/validation/check_citation_reference_graph_package.py`
- `tests/smoke/test_citation_reference_graph_package.py`
- `docs/citation_reference_graph_package_v0.md`

Generated local package output, not committed:

- `data/graphs/citation_reference_graph/packages/v0.1/citation_reference_graph_v0.1.zip`
- `data/graphs/citation_reference_graph/packages/v0.1/package_manifest.json`
- `data/graphs/citation_reference_graph/packages/v0.1/README.md`
- `data/graphs/citation_reference_graph/packages/v0.1/checksums.txt`

Accepted local validation:

```text
python -m py_compile scripts/export/package_citation_reference_graph.py
python -m py_compile scripts/validation/check_citation_reference_graph_package.py
python -m pytest tests/smoke/test_citation_reference_graph_package.py -q
python -m scripts.export.package_citation_reference_graph --dry-run
python -m scripts.export.package_citation_reference_graph --force
python -m scripts.validation.check_citation_reference_graph_package --strict
```

Expected result:

```text
5 passed
package build ok=True
included_files_count=9
package validator ok=True
required_failed_count=0
warning_count=0
```

Boundary:

- local package candidate only
- no graph rebuild
- no canonical truth changes
- no reconcile input changes
- no DB/Qdrant/API/UI/retrieval/ranking changes
- no full-text/PDF/bibliography parsing
- no dataset publication
- no latest pointer
- no graph runtime
- generated package output is not committed
- no Neo4j/NetworkX/GraphRAG runtime

See: `docs/citation_reference_graph_package_v0.md`.
<!-- CITATION_REFERENCE_GRAPH_PACKAGE_V01_END -->
