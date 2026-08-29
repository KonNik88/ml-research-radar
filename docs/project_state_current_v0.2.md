# ML Research Radar — Current Project State Checkpoint v0.2

## Document status

```text
status = accepted post-orchestration and scientific-entity semantic-prompt-v0.2a comparison checkpoint
checkpoint_date = 2026-08-29
supersedes_for_current_planning = docs/project_state_current_v0.1.md
historical_detail_retained_in = docs/project_state_current_v0.1.md
canonical_truth_changed_by_document = false
runtime_behavior_changed_by_document = false
generated_layers_rebuilt_by_document = false
publishes_dataset = false
current_extension = Scientific Entity Semantic Prompt Candidate v0.2a
```

This checkpoint records the accepted project state after the August 2026 safe
canonical refresh, derived-layer synchronization, operational refresh runbook,
Refresh Operational Orchestration v0.1 merge, the first completed bounded
real-paper Scientific Entity evaluation, the frozen GLiNER-versus-literal
pilot/dev comparison, fixture-validated read-only calibration tooling, the real 24-paper calibration execution, the frozen balanced development policy, the independent 48-paper held-out gate, the completed structured held-out error analysis, and the completed semantic-prompt v0.2a controlled development comparison.

It is a planning and transfer document. It is not a source dataset, reconcile
input, runtime manifest, release authorization, or replacement for build-scoped
validation reports.

The corresponding aggregate real-paper pilot evidence is recorded in
[`docs/scientific_entity_literal_baseline_pilot_evaluation_v0.1.md`](scientific_entity_literal_baseline_pilot_evaluation_v0.1.md).

The current bounded candidate-adapter contract is recorded in
[`docs/scientific_entity_gliner_candidate_adapter_v0.1.md`](scientific_entity_gliner_candidate_adapter_v0.1.md).

The completed candidate comparison and decision record is
[`docs/scientific_entity_gliner_pilot_comparison_v0.1.md`](scientific_entity_gliner_pilot_comparison_v0.1.md).

The bounded threshold-policy calibration contract and local operator workflow
are recorded in
[`docs/scientific_entity_gliner_dev_calibration_v0.1.md`](scientific_entity_gliner_dev_calibration_v0.1.md).

The completed human policy review and frozen development policy are recorded in
[`docs/scientific_entity_gliner_dev_policy_review_v0.1.md`](scientific_entity_gliner_dev_policy_review_v0.1.md).

The independent v0.1 generalization gate is recorded in
[`docs/scientific_entity_gliner_heldout_evaluation_v0.1.md`](scientific_entity_gliner_heldout_evaluation_v0.1.md).

The completed post-held-out diagnosis and selected first v0.2 hypothesis are recorded in
[`docs/scientific_entity_heldout_error_analysis_v0.1.md`](scientific_entity_heldout_error_analysis_v0.1.md).

The completed v0.2a semantic-prompt contract, immutable development/input lineage,
unchanged-policy build, controlled comparison, and gate decision are recorded in
[`docs/scientific_entity_semantic_prompt_candidate_v0.2a.md`](scientific_entity_semantic_prompt_candidate_v0.2a.md).

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
| Scientific Entity Evaluation Harness | implemented descriptive evaluation | synthetic fixture plus independently validated real pilot | Exact/relaxed quality semantics and independent recomputation; no model promotion |
| Bounded Scientific Entity Manual Review Evidence | implemented tooling plus completed local pilot | review `scientific-entity-manual-review-v0.1-20260821T131320262656Z`; 24 papers / 48 rows / 435 references | Prediction-blind AI-assisted, human-adjudicated dev evidence; raw paper text remains outside Git |
| Scientific Entity Literal Baseline Pilot Evaluation | completed local descriptive checkpoint | evaluation `scientific-entity-evaluation-v0.1-20260822T114935748579Z`; 30 predictions | Exact F1 `0.043012`, relaxed F1 `0.068818`; literal v0.1 retained as control only |
| Bounded Scientific Entity GLiNER Candidate Adapter | implemented; immutable candidate build validated | build `scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z`; 24 papers / 546 mentions / 91 checks | Experimental candidate only; verified local config injection; no production selection or full-corpus authorization |
| Scientific Entity GLiNER Pilot Comparison | completed local descriptive checkpoint | evaluation `scientific-entity-evaluation-v0.1-20260823T124036780234Z`; 176 exact plus 19 relaxed-only matches / 69 checks | Exact F1 `0.358817`, relaxed F1 `0.397554`; retained for dev calibration, not promoted |
| Bounded Scientific Entity GLiNER Dev Calibration | real candidate execution complete; strict validation green | calibration `scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z` / 24 papers / 127 trials / 69 eligible / 29 Pareto / 53 checks | Balanced dev policy frozen at title `0.55`, abstract `0.65`; exact F1 `0.380146`, relaxed F1 `0.404358`; type probes diagnostic; no promotion or full-corpus claim |
| Scientific Entity GLiNER Frozen Policy Candidate | completed immutable dev materialization | 24 papers / 391 selected predictions / new policy-aware evidence identity | Dev evaluation reproduced exact F1 `0.380146` and relaxed F1 `0.404358`; still candidate-only |
| Scientific Entity Independent Held-Out Review and Evaluation | completed bounded generalization gate | review `scientific-entity-heldout-review-v0.1-20260827T092900455472Z`; 48 papers / 881 references; evaluation `scientific-entity-evaluation-v0.1-20260827T113112815887Z` | Exact F1 `0.396882`, relaxed F1 `0.414868`; bounded v0.1 extractor accepted; production/full-corpus remains unauthorized |
| Scientific Entity Held-Out Error Analysis | completed diagnostic decision checkpoint | analysis `scientific-entity-heldout-error-analysis-v0.1-20260828T121239202063Z`; 48 papers / 808 errors / 398 checks | `model -> method = 55`, `method -> task = 28`; window coverage complete; 5 markup-expanded wide-span FNs; first v0.2a hypothesis = more discriminative semantic prompts |
| Scientific Entity Semantic Prompt Candidate v0.2a | completed controlled development comparison; hard gate failed | development package `scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z`; raw build `scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z`; policy build `scientific-entity-semantic-prompt-policy-v0.2a-20260829T143901678616Z`; comparison `scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z` | 72 development papers / 1316 references / 977 selected predictions; consumed-48 exact F1 `0.383706` missed frozen floor `0.386882`; semantic confusion improved materially; next hypothesis = threshold calibration v0.2b |
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
   - synthetic integration remains green.

5. **Bounded Real-Paper Scientific Entity Manual Review Execution and Literal
   Baseline Pilot v0.1 — completed**
   - prepare the 24-paper sample from current canonical latest;
   - annotate all title/abstract rows prediction-blind;
   - keep raw third-party text and annotator identity outside Git;
   - finalized 48 rows and 435 references;
   - evaluated 30 literal predictions with 10 exact plus 6 relaxed-only matches;
   - passed the independent 69-check evaluation validator.

6. **Bounded GLiNER Candidate Extractor Selection and Adapter v0.1 — implemented**
   - reuse the existing evidence contract and evaluation harness;
   - pin Apache-2.0 model license, exact revision, FP16 artifact hash, auxiliary
     DeBERTa config revision/hash and runtime;
   - require explicit model download, offline execution, long-input windowing,
     exact model-score evidence, immutable output and independent validation;
   - fail closed if GLiNER requests any backbone configuration other than the
     verified locally injected config;
   - current 24-paper package is dev evidence, not a final held-out benchmark;
   - keep literal v0.1 unchanged as the deterministic control.

7. **GLiNER Candidate Comparison on Existing Pilot/Dev Evidence — completed**
   - run the frozen configuration on the existing 24-paper sample;
   - validate artifact identity, output, duration, peak CUDA memory and repeatability;
   - reuse the existing exact/relaxed evaluation harness;
   - evaluated 546 predictions against 435 references with exact F1 `0.358817`
     and relaxed F1 `0.397554`;
   - retained GLiNER as the leading bounded candidate without promotion;
   - do not tune and claim the same 24 papers as held-out evidence.

8. **Bounded Scientific Entity GLiNER Dev Calibration Tooling v0.1 — implemented**
   - read only one frozen prediction build and pinned baseline evaluation;
   - execute 127 declared baseline/global/source-pair/type-probe trials;
   - select descriptive exact F0.5/F1/F2 profiles plus a Pareto frontier;
   - keep per-type probes diagnostic and forbid combined type-policy selection;
   - independently reproduce all seven immutable output files byte for byte;
   - never run a model, reinterpret scores as probabilities, or claim promotion.

9. **Execute Candidate Calibration and Freeze at Most One Dev Policy — completed**
   - calibration `scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z` executed on 24 papers / 435 references / 546 frozen predictions;
   - strict validator passed `53 / 53`; 127 trials, 69 profile-eligible, 29 Pareto;
   - balanced policy frozen at `title >= 0.55 / abstract >= 0.65`;
   - exact F1 `0.380146`, relaxed F1 `0.404358`;
   - type probes remain diagnostic; no combined type-specific policy selected.

10. **Materialize Frozen Dev Policy as New Immutable Candidate — completed**
   - preserved the original 546-mention GLiNER build unchanged;
   - materialized 391 frozen-policy predictions with a policy-aware extractor fingerprint and new evidence IDs;
   - reproduced the selected dev metrics under a new immutable evaluation identity.

11. **Independent Held-Out Review Evidence and Frozen-Policy Evaluation — completed**
   - selected 48 new disjoint papers, 24 uniform plus 24 type-enriched;
   - finalized 96 prediction-blind annotation rows into 881 references;
   - reference package passed `4444 / 4444` strict checks;
   - one raw GLiNER run emitted 1145 predictions and passed `91 / 91` checks;
   - unchanged frozen policy selected 787 predictions and passed `4762 / 4762` checks;
   - held-out evaluation passed `69 / 69` checks with exact F1 `0.396882` and relaxed F1 `0.414868`;
   - generalization gate passed; v0.1 accepted only as a bounded working extractor.

12. **Scientific Entity Held-Out Error Analysis v0.1 — completed**
   - materialized analysis `scientific-entity-heldout-error-analysis-v0.1-20260828T121239202063Z`;
   - strict validator passed `398 / 398` required checks;
   - confirmed semantic typing as the dominant actionable failure: `model -> method = 55`, `method -> task = 28`, and `method` receives `94 / 176` type mismatches;
   - confirmed real `320`-token / `64`-overlap adapter windowing covers every source splitter token, with `0` windows above model `max_len=768`;
   - isolated five markup-like references wider than `model_max_width=12`; all five are false negatives and two do not fit wholly in any one adapter window;
   - superseded the earlier incorrect whole-document `max_len` diagnostic interpretation;
   - selected one first v0.2 hypothesis without retuning v0.1.

13. **Scientific Entity Semantic Prompt Candidate v0.2a — completed; hard gate failed**
   - froze six more discriminative GLiNER-facing prompts while keeping the pinned small-v2.5 model/revision/artifact, six canonical types, `320/64` windowing, raw threshold `0.50`, and first-comparison `title >= 0.55 / abstract >= 0.65` policy unchanged;
   - materialized a zero-overlap 72-paper development package from 24 old-DEV plus 48 consumed-v0.1-held-out papers;
   - raw v0.2a build emitted `1430` predictions and passed `91 / 91` GLiNER build checks; controlled identity verification changed the runtime-config SHA and extractor fingerprint while preserving model/revision/artifact identity;
   - unchanged policy selected `977` predictions and rejected `453`, with no model inference or threshold tuning in the policy slice;
   - controlled comparison `scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z` used `1316` references and validated with `required_failed_count=0`;
   - on the consumed-48 decision view, exact F1 `0.383706` failed the pre-frozen floor `0.386882`; all five semantic-confusion hard guardrails passed;
   - semantic typing improved materially: `model -> method 55 -> 31`, `method -> task 28 -> 21`, total type mismatches `176 -> 125`, method sink `94 -> 54`;
   - v0.2a is not accepted as the next candidate configuration and does not authorize production or full-corpus extraction.

14. **Scientific Entity Semantic Prompt Threshold Calibration v0.2b — next**
   - retain the v0.2a semantic prompts and the same pinned small-v2.5 runtime;
   - freeze the calibration/search space and decision criteria before threshold search;
   - use only the already-consumed 72-paper development evidence;
   - test whether source-field threshold recalibration can recover recall while retaining the v0.2a semantic-confusion gains;
   - do not spend a fresh independent held-out set during calibration.

15. **Fresh v0.2 Held-Out Gate — later**
   - select a new disjoint prediction-blind sample only after a promising v0.2 candidate is frozen;
   - require independent evidence before any v0.2 acceptance claim.

16. **Accepted Large-Scale Derived Entity Build — deferred**
   - requires a later production-quality decision and explicit full-corpus authorization;
   - build-scoped manifest and current-canonical compatibility checks;
   - current development evidence does not authorize a 61,075-paper entity run.

17. **Normalization / Linking / Product and Graph Integration — deferred**
   - avoid normalizing six-type evidence before weak types and semantic typing are hardened;
   - later add aliases, canonical entity IDs, Discovery facets, paper detail/comparison evidence, and paper–entity edges.

18. **Full-text / Chunk Provenance / Grounded RAG**
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
no full-corpus entity extraction before candidate and held-out acceptance
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
scientific entity real review complete = true (bounded local pilot/dev evidence)
scientific entity pilot review = 24 papers / 48 rows / 435 references
scientific entity literal candidate = 30 predictions / exact F1 0.043012 / relaxed F1 0.068818
scientific entity pilot evaluation id = scientific-entity-evaluation-v0.1-20260822T114935748579Z
scientific entity GLiNER adapter = implemented bounded candidate / immutable build validated
scientific entity GLiNER model = gliner-community/gliner_small-v2.5 / exact revision and FP16 SHA pinned
scientific entity GLiNER backbone config = microsoft/deberta-v3-small/config.json / exact revision, size and SHA pinned
scientific entity GLiNER candidate build = scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z / 24 papers / 546 mentions / 91 of 91 checks
scientific entity GLiNER evaluation id = scientific-entity-evaluation-v0.1-20260823T124036780234Z
scientific entity GLiNER exact metrics = precision 0.322344 / recall 0.404598 / F1 0.358817
scientific entity GLiNER relaxed metrics = precision 0.357143 / recall 0.448276 / F1 0.397554
scientific entity GLiNER comparison = completed descriptive pilot/dev checkpoint / retained for bounded calibration / not promoted
scientific entity GLiNER calibration tooling = implemented read-only fixed-prediction search / fixture 127 trials / 53 of 53 checks
scientific entity GLiNER real calibration = complete / scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z / 127 trials / 69 eligible / 29 Pareto / 53 of 53 checks
scientific entity GLiNER type probes = diagnostic only / combined policy selection forbidden
scientific entity confidence remains = model_score / no probability reinterpretation / mention calibration_id remains null
scientific entity current 24-paper dev set becomes held-out = false
scientific entity GLiNER frozen dev policy = balanced_f1 / title 0.55 / abstract 0.65 / no type overrides
scientific entity held-out review id = scientific-entity-heldout-review-v0.1-20260827T092900455472Z / 48 papers / 96 rows / 881 references / prediction-blind / dev overlap 0
scientific entity held-out reference validator = 4444 / 4444 required checks
scientific entity held-out raw build = scientific-entity-gliner-small-v2.5-v0.1-20260827T111030652864Z / 48 papers / 1145 predictions / 91 of 91 checks
scientific entity held-out frozen-policy build = scientific-entity-gliner-small-v2.5-heldout-frozen-policy-v0.1-20260827T112658493807Z / 787 selected / 358 rejected / 4762 of 4762 checks
scientific entity held-out evaluation id = scientific-entity-evaluation-v0.1-20260827T113112815887Z / 69 of 69 checks
scientific entity held-out exact metrics = precision 0.420584 / recall 0.375709 / F1 0.396882
scientific entity held-out relaxed metrics = precision 0.439644 / recall 0.392736 / F1 0.414868
scientific entity held-out weakest exact types = metric F1 0.209877 / domain F1 0.293707 / task recall 0.308571
scientific entity held-out decision = generalization gate passed / accept v0.1 as bounded working extractor / no production promotion
scientific entity production model selected = false
scientific entity full-corpus build authorized = false
scientific entity held-out error analysis = complete / scientific-entity-heldout-error-analysis-v0.1-20260828T121239202063Z / 398 of 398 checks
scientific entity dominant held-out error = semantic type disambiguation / model->method 55 / method->task 28 / method sink 94 of 176
scientific entity adapter windowing audit = 3 multi-window source texts / 101 inference windows / 0 uncovered splitter tokens / 0 windows above model max_len
scientific entity markup/max-width corner case = 5 markup-like references wider than max_width=12 / all 5 FN / 2 not fully contained in one adapter window
scientific entity first v0.2 hypothesis = more discriminative GLiNER-facing semantic prompts / completed as v0.2a
scientific entity v0.2a development package = scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z / 24 old DEV + 48 consumed held-out / 72 total / zero overlap
scientific entity v0.2a raw build = scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z / 72 documents / 1430 raw predictions / 91 of 91 build checks
scientific entity v0.2a policy build = scientific-entity-semantic-prompt-policy-v0.2a-20260829T143901678616Z / 977 selected / 453 rejected / title 0.55 / abstract 0.65
scientific entity v0.2a comparison = scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z / 1316 references / strict required_failed_count 0
scientific entity v0.2a decision = hard gate failed / consumed-48 exact F1 0.383706 below frozen floor 0.386882 / not accepted as next candidate configuration
scientific entity v0.2a semantic signal = model->method 31 / method->task 21 / type mismatches 125 / method sink 54
scientific entity next v0.2 hypothesis = semantic-prompt threshold recalibration v0.2b
next entity slice = Scientific Entity Semantic Prompt Threshold Calibration v0.2b design/freeze
```

The project is not restarting or replacing completed work. The next entity
layer extends the same paper-centric system and remains downstream of canonical
truth.
