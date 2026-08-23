# Scientific Entity GLiNER Pilot Comparison v0.1

## Document status

```text
status = completed local descriptive pilot/dev comparison
checkpoint_date = 2026-08-23
base_git_commit = d2f92c1
canonical_truth_mutated = false
runtime_behavior_changed = false
production_extractor_selected = false
full_corpus_build_authorized = false
publication_ready = false
metrics_are_descriptive_only = true
```

This checkpoint compares the frozen bounded GLiNER v0.1 candidate with the
unchanged deterministic literal v0.1 control on the same completed 24-paper
manual-review package. It records local derived evidence only. It does not
promote an extractor, change the six-type Scientific Entity Evidence Contract,
add fields to canonical papers, authorize a current-canonical/full-corpus run,
or publish third-party paper text.

The 24-paper package is now explicitly a **development and diagnostic set**.
Any threshold, prompt, type policy, filtering, or adjudication informed by this
comparison is tuning. Results from the same package must not subsequently be
described as held-out evidence.

Related tracked contracts and checkpoints:

- [`scientific_entity_evidence_contract_v0.1.md`](scientific_entity_evidence_contract_v0.1.md)
- [`scientific_entity_evaluation_harness_v0.1.md`](scientific_entity_evaluation_harness_v0.1.md)
- [`scientific_entity_manual_review_evidence_v0.1.md`](scientific_entity_manual_review_evidence_v0.1.md)
- [`scientific_entity_literal_baseline_pilot_evaluation_v0.1.md`](scientific_entity_literal_baseline_pilot_evaluation_v0.1.md)
- [`scientific_entity_gliner_candidate_adapter_v0.1.md`](scientific_entity_gliner_candidate_adapter_v0.1.md)

## 1. Immutable local evidence chain

```text
review_id = scientific-entity-manual-review-v0.1-20260821T131320262656Z
review_document_count = 24
review_annotation_row_count = 48
reference_mention_count = 435
annotation_method = manual_adjudicated

literal_build_id = scientific-entity-literal-v0.1-20260822T114316573133Z
literal_evaluation_id = scientific-entity-evaluation-v0.1-20260822T114935748579Z
literal_prediction_mention_count = 30

gliner_build_id = scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z
gliner_evaluation_id = scientific-entity-evaluation-v0.1-20260823T124036780234Z
gliner_prediction_mention_count = 546
gliner_exact_match_count = 176
gliner_relaxed_only_match_count = 19
gliner_evaluation_error_count = 494

gliner_build_validator = 91 / 91 required checks
gliner_evaluation_validator = 69 / 69 required checks
required_failed_count = 0
```

The candidate build and evaluation directories remain immutable, local, and
ignored by Git under `data/entities/`. The repository records aggregate facts
and decision boundaries, not raw titles, abstracts, reference rows, prediction
rows, annotator identity, model weights, or generated runtime directories.

## 2. Frozen candidate provenance and runtime evidence

```text
model = gliner-community/gliner_small-v2.5
model_revision = f227d3cd637bd4e6757ae143935316d062393341
model_variant = fp16
model_artifact_sha256 = d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74
library = gliner==0.2.28
backbone_config = microsoft/deberta-v3-small/config.json
backbone_revision = a36c739020e01763fe789b4b85e2df55d6180012
backbone_config_sha256 = b0bb1caf90a50aa67d1085130508dfbf8646ac5a11928305e280b07a36e100ae
initial_threshold = 0.5
source_fields = title, abstract
entity_types = task, method, dataset, metric, model, domain
inference_duration_seconds = 2.095834
peak_cuda_memory_bytes = 419360768
model_artifact_verified = true
backbone_config_verified = true
backbone_config_injected = true
```

The runtime facts prove that the pinned candidate can execute safely inside the
current RTX 2070 SUPER resource envelope. They are not quality or scaling
acceptance evidence.

## 3. Primary comparison

### 3.1 Micro metrics

| Extractor | Match policy | TP | FP | FN | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| Literal v0.1 | Exact | 10 | 20 | 425 | 0.333333 | 0.022989 | 0.043012 |
| GLiNER v0.1 | Exact | 176 | 370 | 259 | 0.322344 | 0.404598 | 0.358817 |
| Literal v0.1 | Relaxed | 16 | 14 | 419 | 0.533333 | 0.036782 | 0.068818 |
| GLiNER v0.1 | Relaxed | 195 | 351 | 240 | 0.357143 | 0.448276 | 0.397554 |

Descriptive deltas:

```text
prediction volume = 546 / 30 = 18.2x literal
exact recall delta = +0.381609
exact recall ratio = 17.60x literal
exact F1 delta = +0.315805
exact F1 ratio = 8.34x literal
relaxed recall delta = +0.411494
relaxed recall ratio = 12.19x literal
relaxed F1 delta = +0.328736
relaxed F1 ratio = 5.78x literal
```

The literal control has slightly higher exact precision and materially higher
relaxed precision, but it emits only 30 predictions and misses almost the whole
reference set. GLiNER is therefore the first viable high-coverage candidate,
not an accepted extractor. Its principal remaining problems are precision and
semantic type assignment.

### 3.2 Source-field metrics

| Source field | Match policy | Reference | Prediction | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|
| Title | Exact | 58 | 44 | 0.568182 | 0.431034 | 0.490196 |
| Title | Relaxed | 58 | 44 | 0.590909 | 0.448276 | 0.509804 |
| Abstract | Exact | 377 | 502 | 0.300797 | 0.400531 | 0.343573 |
| Abstract | Relaxed | 377 | 502 | 0.336653 | 0.448276 | 0.384528 |

Title extraction is materially cleaner than abstract extraction. Of the 235
unpaired false-positive error records, 225 occur in abstracts and 10 in titles.
This supports evaluating source-field thresholds before introducing a new
classification stage. Raw error counts still reflect the much larger abstract
text and prediction volume and are not independent quality estimates.

### 3.3 Per-type metrics

| Entity type | Exact P | Exact R | Exact F1 | Relaxed P | Relaxed R | Relaxed F1 |
|---|---:|---:|---:|---:|---:|---:|
| task | 0.235849 | 0.320513 | 0.271739 | 0.311321 | 0.423077 | 0.358696 |
| method | 0.342246 | 0.412903 | 0.374269 | 0.379679 | 0.458065 | 0.415205 |
| dataset | 0.305556 | 0.478261 | 0.372882 | 0.305556 | 0.478261 | 0.372882 |
| metric | 0.326923 | 0.447368 | 0.377778 | 0.326923 | 0.447368 | 0.377778 |
| model | 0.429688 | 0.509259 | 0.466102 | 0.460938 | 0.546296 | 0.500000 |
| domain | 0.108108 | 0.121212 | 0.114286 | 0.108108 | 0.121212 | 0.114286 |

`model` is the strongest current type. `domain` is the clear weak point and may
eventually require a document-level classification treatment, but changing the
contract is not authorized by this pilot.

## 4. Structural error diagnostics

| Error kind | Count |
|---|---:|
| boundary_mismatch | 22 |
| type_mismatch | 113 |
| false_positive | 235 |
| false_negative | 124 |

The 494 error rows are structural diagnostic events, not the sum of metric FP
and FN. A paired type or boundary mismatch represents one linked diagnostic
record while contributing differently to exact/relaxed metric denominators.

### 4.1 Concentrated type confusion

| Reference type | Predicted type | Mention count |
|---|---|---:|
| model | method | 45 |
| method | task | 30 |
| task | method | 10 |

These three directions account for 85 of 113 type mismatches (`75.2%`). The
highest-confidence examples are repeated exact-span mentions of named systems
and model families such as `GRAPH-BERT`, `L2Dive`, `EAGLE-3`, `SVM`, and `GAN`.
The count is mention-level and is inflated by repeated mentions of the same
surface forms. It primarily diagnoses overlap between the current `model`,
`method`, and `task` semantics rather than failed span detection.

### 4.2 Confidence is not calibrated correctness

| Diagnostic outcome | Count | Minimum | Median | Mean | Maximum |
|---|---:|---:|---:|---:|---:|
| exact | 176 | 0.505371 | 0.827148 | 0.806810 | 0.989258 |
| type_mismatch | 113 | 0.501465 | 0.784180 | 0.777979 | 0.996582 |
| false_positive | 235 | 0.500488 | 0.676270 | 0.687060 | 0.988281 |
| boundary_mismatch | 22 | 0.514160 | 0.664795 | 0.682129 | 0.953613 |

False-positive scores are lower in aggregate, so threshold calibration is a
valid first experiment. The heavy overlap and near-exact median for
type-mismatch rows prove that a global threshold alone cannot repair semantic
typing. `confidence_score` remains an uncalibrated model score, not a
probability of correctness.

## 5. Qualitative error audit

The highest-confidence unmatched predictions fall into four practical groups:

1. **Generic non-entities** — standalone surfaces such as `metric`, `models`,
   `benchmarks`, `SOTA`, `application`, `real-world applications`, `nodes`,
   `Numerical evaluations`, and `Empirical research`.
2. **Outside the six-type contract** — for example `Science` used as a venue;
   venue already belongs to canonical metadata and must not be duplicated by
   the entity layer.
3. **Malformed or overlapping spans** — one high-confidence span crossed a
   sentence boundary and contained two `GRAPH-BERT` occurrences.
4. **Adjudication candidates** — `Reinforcement learning`, `OIM`,
   `learning-based medical screening`, and `Person ReID methods` may be omitted
   references, wider duplicate spans, or guideline-dependent cases.

The sample supports retaining the narrow, product-oriented six-type ontology.
It does not support expanding extraction to authors, venue, generic scientific
concepts, or other metadata already represented elsewhere. Any correction to
manual dev evidence must be versioned; the accepted reference package and this
evaluation are never edited in place.

## 6. Data sufficiency

```text
minimum_document_count = 32
actual_document_count = 24
document_count_sufficient = false
all_six_per_type_support_markers = true
promotion_sample_sufficient = false
metrics_are_descriptive_only = true
```

The 24-paper sample is useful for error analysis and bounded configuration
development. It is not sufficient evidence for a corpus of 61,075 papers and
cannot support future multi-million-paper scaling claims. A 32-paper disjoint
held-out set is only the minimum next gate, not final production evidence.
Before full-corpus acceptance, review evidence must grow in staged,
stratified, prediction-blind slices covering time, source families, research
areas, title/abstract behavior, rare entity types, and hard negatives.

## 7. Decision

```text
literal baseline v0.1 = retain unchanged as deterministic control
GLiNER candidate v0.1 = retain as leading bounded candidate
GLiNER candidate v0.1 production promotion = rejected
current 24-paper package = pilot/dev diagnostics only
threshold or prompt tuning on current package = allowed only as explicit dev tuning
same 24 papers described as held-out after tuning = forbidden
six-type contract expansion = not justified by this comparison
second-stage classifier = deferred until cheaper controls show a residual bottleneck
canonical truth mutation = forbidden
full-corpus extraction = forbidden
```

GLiNER materially outperforms the literal control and is worth bounded
calibration. It is not accurate enough, independently evidenced enough, or
calibrated enough for promotion.

## 8. Next authorized slice

The next code slice is **Bounded Scientific Entity GLiNER Dev Calibration
v0.1**. Its order is intentionally cost-aware:

1. reuse the immutable `>=0.5` candidate scores for a read-only global
   threshold sweep;
2. evaluate title and abstract thresholds before fitting per-type overrides;
3. avoid fitting 12 independent `source_field × entity_type` thresholds on 24
   documents;
4. test a small predeclared set of clearer `model`/`method`/`task`/`domain`
   prompts as new extractor fingerprints and immutable candidate builds;
5. test principled generic-surface and cross-sentence-span rejection rules,
   verifying that they reject no accepted reference span;
6. keep any manual dev adjudication versioned and separate from the original
   prediction-blind package;
7. freeze one candidate before preparing new held-out evidence.

A second-stage type/rejection classifier is authorized only if thresholds,
prompts, deterministic span rules, and improved evidence leave a measured
high-confidence type/rejection bottleneck.

After candidate freeze, create a disjoint prediction-blind review of at least
32 new papers. Further stratified evidence growth remains required before any
accepted full-corpus build. Normalization, linking, product integration,
paper-entity graph edges, RAG, and publication remain later slices.
