# ML Research Radar — Current Project State Checkpoint v0.2

## Document status

```text
status = accepted post-orchestration planning checkpoint
checkpoint_date = 2026-08-19
supersedes_for_current_planning = docs/project_state_current_v0.1.md
historical_detail_retained_in = docs/project_state_current_v0.1.md
canonical_truth_changed_by_document = false
runtime_behavior_changed_by_document = false
generated_layers_rebuilt_by_document = false
publishes_dataset = false
current_extension = Bounded Scientific Entity Manual Review Evidence v0.1
```

This checkpoint records the accepted project state after the August 2026 safe
canonical refresh, derived-layer synchronization, operational refresh runbook,
and Refresh Operational Orchestration v0.1 merge.

It is a planning and transfer document. It is not a source dataset, reconcile
input, runtime manifest, release authorization, or replacement for build-scoped
validation reports.

---

## 1. Decision summary

The central architecture remains:

```text
canonical paper truth
→ rebuildable derived data and evidence layers
→ runtime and product surfaces
```

Current paper truth:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

Current accepted canonical state:

```text
pre_promotion_baseline_doc_count = 60,954
current_canonical_latest_doc_count = 61,075
doc_count_delta = +121
removed_count = 0
canonical_multisource_docs = 9,226
```

The value `60,954` remains valid for several older build-scoped outputs. It is
no longer the current canonical latest count.

---

## 2. Truth and identity boundaries

Identity domains remain separate:

```text
source_observation_id
= deterministic source-level observation identity

canonical_id
= reconciled paper identity

artifact_id
= normalized repository/model/dataset/demo identity

dense_index / Qdrant point_id
= serving identity inside one retrieval generation

future entity mention/entity identifiers
= derived scientific-entity evidence identities
```

No derived identity may redefine `canonical_id`.

Postgres, retrieval manifests, paper features, graphs, Qdrant collections,
release candidates, reports, APIs, and UIs remain materializations or consumers
of file-backed truth. They must remain rebuildable.

---

## 3. Current layer-state matrix

| Layer | Accepted state | Baseline identity | Current interpretation |
|---|---|---|---|
| Canonical latest | current | 61,075 papers | Paper-level source of truth |
| Refresh candidate | consumed by controlled promotion | 61,075 papers | No longer a competing truth |
| Retrieval artifacts | synchronized | build `20260818T105227Z`, 61,075 papers | Current file-backed retrieval generation |
| Postgres paper materialization | synchronized | canonical/DB count parity passed | Rebuildable serving projection |
| Paper features | synchronized | 61,075 rows | Current derived feature layer |
| Paper detail and similar papers | synchronized | rebuilt after current ranking sample | Bounded Discovery reports |
| Topic clusters | synchronized | build `20260818T110734Z`, 80 clusters | Current derived analytics layer |
| Topic projection | synchronized | build `20260818T111232Z`, 2,080 points | Current visualization sample |
| Discovery API quality | green | current synchronized reports | Derived API validation evidence |
| Streamlit Discovery UI quality | green | current synchronized reports | Thin-client validation evidence |
| Experimental Qdrant collection | previous build-scoped baseline | 60,954 points | Not promoted and not synchronized by the August refresh |
| Paper–Artifact Graph package/output | previous local build-scoped baseline | 60,954-paper generation | Completed local line; not rebuilt by core refresh orchestration |
| Citation / Reference Graph package/output | previous local build-scoped baseline | 60,954-paper generation | Completed local line; runtime must fail closed on incompatibility |
| Metadata dataset release candidate | previous local build-scoped baseline | 60,954 rows | Publication remains paused |
| Field-level provenance evidence | accepted bounded sample | 12 papers / 732 field records | Explanatory evidence, not full-corpus materialization |
| Scientific Entity Evidence Contract | accepted | v0.1 / six entity types | Exact span, identity, provenance, confidence, and build compatibility |
| Bounded Scientific Entity Extractor Baseline | implemented reference baseline | fixture/candidate only; max 100 documents | Deterministic derived evidence producer; no production model or full-corpus run |
| Scientific Entity Evaluation Harness | implemented descriptive evaluation | 4 synthetic documents / 18 references / 17 predictions | Exact/relaxed quality semantics and independent recomputation; no model promotion |
| Bounded Scientific Entity Manual Review Evidence | implemented local review tooling | 8-document synthetic fixture / 16 annotation rows / 6 references | Deterministic sampling and prediction-blind preparation/finalization; real review not completed |
| Refresh operational orchestration | implemented | v0.1 | Recommended operational refresh entrypoint |

The previous Qdrant, graph, and dataset candidates are not silently redefined as
current merely because canonical latest changed. Each requires its own explicit
rebuild, validation, and acceptance decision if it re-enters scope.

Source-observation count boundary:

```text
historical source-identity checkpoint selected observations = 88,178
later observed export inserted/updated source documents = 88,196
current source_documents count = not reasserted by this documentation checkpoint
```

Neither historical command output is promoted here as a fresh database row
count. A current value must come from a new database/export report with its own
build context.

---

## 4. Safe refresh checkpoint

The accepted refresh moved canonical latest from `60,954` to `61,075` papers
without destructive removals.

The refresh repaired and validated:

```text
ACL-only paper retention
full merged OpenAlex alignment coverage
full merged Semantic Scholar alignment coverage
full merged Crossref alignment coverage
retained multi-source paper observations
destructive versus additive source-coverage semantics
promotion readiness
controlled canonical promotion
core derived synchronization
Postgres parity
Discovery derived synchronization
```

Accepted promotion evidence included:

```text
promotion_ready = true
removed_count = 0
destructive_identifier_churn_count = 0
lost_alignment_source_observation_count = 0
required_failed_count = 0
```

The final Discovery-oriented Definition of Done passed with all selected
optional Discovery gates required.

---

## 5. Refresh operational ownership

Recommended operational entrypoint:

```bat
python -m scripts.update.run_refresh_operational_flow --phase <phase>
```

Public phases:

```text
preflight
candidate
promote
core-derived
postgres
discovery-derived
full
```

Accepted safety semantics:

```text
non-promote phases without --execute = plan only
promote without --execute = real non-mutating controlled-promotion dry-run
promote --execute = requires fresh matching successful dry-run
full = complete plan view
full --execute = fail-closed in v0.1
```

`run_refresh_pipeline_v1` remains supported as a lower-level/legacy runner,
especially for bounded candidate rehearsal. It is not an equal recommended
production full-refresh path.

The operational runner does not start Docker or Postgres and does not perform
dataset publication, Qdrant promotion, graph rebuilds, model replacement, or
Airflow scheduling.

Accepted merge lineage:

```text
refresh runbook docs commit = fcfadac
refresh runbook merge checkpoint = f48ea67
operational orchestration implementation commit = 29038fd
operational orchestration merge checkpoint = 66195df
```

---

## 6. Completed functional lines

The repository already contains validated implementations for:

```text
multi-source ingestion and normalization
canonical reconciliation and provenance
source-observation materialization identity
file-backed lexical/dense/hybrid retrieval
experimental Qdrant evaluation and serving evidence
Postgres paper materialization
artifact extraction and provider enrichment
paper features and ranking profiles
paper detail and similar papers
topic clusters and projection
Discovery API and Streamlit UI
saved research collections
paper comparison workspace
Paper–Artifact Graph local builder/inspection/query/package/checkpoint/review line
Citation / Reference Graph builder/inspection/query/package/API/UI/regression/review line
metadata-only dataset release candidate and review tooling
safe refresh rehearsal/readiness/promotion/runbook/orchestration
```

This means additional graph endpoints or another orchestration framework are not
the highest-value next step without a new concrete requirement.

---

## 7. Publication status

Dataset publication remains paused pending explicit redistribution guidance.

Current policy:

```text
local release candidate = allowed
local validation/review evidence = allowed
public upload = not authorized
reduced workaround publication = not selected
source attribution requirements = preserved
```

No public Kaggle, Hugging Face Dataset, GitHub release, or graph package upload
is authorized by this checkpoint.

---

## 8. Accepted next functional direction

The next macro-layer is:

```text
Scientific Entity Evidence Layer
```

Initial entity families:

```text
task
method
dataset
metric
model
domain
```

The layer must be derived from canonical paper text/evidence and must preserve:

```text
mention-level provenance
extractor and config versions
confidence semantics
source-field offsets
canonical corpus fingerprint
rebuildability
validation reports
no canonical mutation
```

The correct conceptual sequence is:

```text
mention extraction
→ mention normalization
→ optional entity linking
→ paper–entity evidence
→ accepted product/graph consumers
```

Classic NER tags alone are insufficient because tasks, methods, metrics,
datasets, models, and domains require typed normalization and evidence-aware
linking.

---

## 9. Next bounded slices

Recommended order:

1. **Scientific Entity Evidence Contract v0.1 — completed**
   - define mention schema, identity, provenance, confidence, output, and
     validation semantics;
   - no model download and no full-corpus generation.

2. **Bounded Scientific Entity Extractor Baseline v0.1 — completed**
   - deterministic adapter and small synthetic/curated fixtures;
   - explicit plan/execute boundary;
   - no claim of production NER quality.

3. **Scientific Entity Evaluation Harness v0.1 — completed**
   - exact/relaxed one-to-one matching;
   - micro, per-type, and source-field descriptive metrics;
   - independently recomputed structural error evidence;
   - no model promotion or full-corpus authorization.

4. **Bounded Scientific Entity Manual Review Evidence v0.1 — completed tooling**
   - deterministic 12-document uniform plus 12-document type-enriched sample;
   - prediction-blind reference-annotation preparation and explicit finalization;
   - immutable prepared/completed local packages and independent validator;
   - synthetic integration is green; real review remains incomplete.

5. **Bounded Real-Paper Scientific Entity Manual Review Execution v0.1 — next**
   - prepare the 24-paper sample from current canonical latest;
   - annotate all title/abstract rows prediction-blind;
   - keep raw third-party text and annotator identity outside Git;
   - validate and run the existing baseline/evaluation harness.

6. **Candidate Extractor Benchmark and Accepted Full Derived Entity Build**
   - only after quality gates;
   - model license, latency, memory, determinism, and provenance evidence;
   - build-scoped manifest and current-canonical compatibility checks;
   - explicit human acceptance decision.

7. **Product and Graph Integration**
   - Discovery facets, paper detail/comparison evidence, paper–entity edges;
   - only after the derived entity layer is accepted.

8. **Full-text / Chunk Provenance / Grounded RAG**
   - separate contract and acquisition-policy line;
   - no ungrounded chat layer.

---

## 10. Explicit immediate non-goals

```text
no public dataset upload
no Qdrant promotion
no new embedding generation
no retrieval model replacement
no Airflow/Prefect scheduler adoption
no Kafka/Ray/Kubernetes expansion
no Neo4j or graph DB materialization
no GraphRAG implementation
no full-text acquisition
no full-corpus entity extraction before contract/evaluation
no entity fields added to canonical documents
```

Airflow or another scheduler should be considered only after the local
operational runner has completed real refresh cycles and a concrete scheduling,
retry, observability, or multi-machine requirement exists.

---

## 11. Transfer-safe summary

```text
canonical latest = 61,075
pre-promotion baseline = 60,954
core retrieval/Postgres/Discovery layers = synchronized
retrieval_build_id = 20260818T105227Z
topic_cluster_build_id = 20260818T110734Z
topic_projection_build_id = 20260818T111232Z
Qdrant/graph/dataset outputs at 60,954 = previous build-scoped candidates
operational refresh entrypoint = run_refresh_operational_flow
legacy candidate runner = run_refresh_pipeline_v1
dataset publication = paused pending permission
next macro-layer = Scientific Entity Evidence
scientific entity evaluation harness = implemented descriptive evidence
scientific entity manual-review tooling = implemented prediction-blind preparation/finalization
scientific entity real review complete = false
scientific entity production model selected = false
scientific entity full-corpus build authorized = false
new model selection = deferred until bounded real manual-review evidence exists
```

The project is not restarting or replacing completed work. The next entity
layer extends the same paper-centric system and remains downstream of canonical
truth.
