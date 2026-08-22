# Scientific Entity Literal Baseline Pilot Evaluation v0.1

## 1. Status

```text
status = completed bounded local descriptive pilot
checkpoint_date = 2026-08-22
base_git_commit = 7c48111
evaluation_status = candidate
metrics_are_descriptive_only = true
production_extractor_selected = false
full_corpus_build_authorized = false
canonical_truth_mutated = false
publication_ready = false
```

This checkpoint records the first real-paper execution of the accepted
Scientific Entity Evidence, manual-review, and evaluation contracts. It is an
aggregate evidence record. It does not commit paper title/abstract text,
reference annotations, annotator identity, generated prediction rows, or
generated evaluation rows.

The evaluated literal extractor remains a deterministic control implementation.
This document does not promote it to production and does not authorize a build
over canonical latest.

---

## 2. Architectural boundary

The evaluated path is:

```text
canonical latest
→ deterministic 24-paper local sample
→ prediction-blind manually adjudicated reference evidence
→ bounded literal candidate evidence
→ immutable exact/relaxed evaluation
→ independent strict validation
```

All outputs remain downstream of canonical paper truth:

```text
canonical_documents.jsonl = paper truth
manual review package = local derived reference evidence
literal prediction build = local derived candidate evidence
evaluation package = local derived descriptive evidence
```

No entity mention, reference, prediction, match, error, or metric may redefine
`canonical_id` or become reconciliation input.

---

## 3. Pinned provenance

### 3.1 Evaluation

```text
evaluation_id = scientific-entity-evaluation-v0.1-20260822T114935748579Z
generated_at_utc = 2026-08-22T11:52:05.135277Z
config_path = configs/scientific_entity_evaluation_v0.1.yaml
config_sha256 = 79dec3b87349d7edc2acd34bd9f9fa398d34efa5e6ecec97fb0e7492f322958a
metrics_sha256 = 2d5dc979f228e8c938757d0aa2da0ec5fb47904a8173d82afee1f6ce7f63a672
per_type_metrics_sha256 = d53e37fbbe94d394f8b2409373e203ab5d45cf3feb668a3f1346e4d5d85389b9
matches_sha256 = d6b77fd6f400d3cdce7854109131ffa4d7bb125eb54dc881077ef64eee0022b5
errors_sha256 = 04cef07596503e7437dffaa30fd15e8b4a68bfb5628a67d6fde7a2f94411a8cf
strict_validator_checks = 69 / 69
required_failed_count = 0
```

### 3.2 Canonical-shaped sample

```text
document_count = 24
canonical_input_sha256 = d7a640f64f4a096d3d278ad5ca57cc761b8efec214866613b79583b0bdba326e
sampling_shape = 12 uniform + 12 type-enriched documents
source_fields = title + abstract
annotation_rows = 48
```

The sample is a deterministic bounded candidate drawn from current canonical
latest. It is deliberately stratified and must not be interpreted as an IID
estimate of the whole 61,075-paper corpus.

### 3.3 Reference review

```text
review_id = scientific-entity-manual-review-v0.1-20260821T131320262656Z
review_status = reviewed_candidate
review_manifest_sha256 = 80c214ccdd5792d0fe29f292668dc232e83acbd241136b8ce45ee3a0db08162a
reference_mentions_sha256 = cbd1e31d548f064924b56938ad823baf659f3c1e21a054826195f1ecbbdb3e3f
reference_mention_count = 435
review_complete = true
prediction_blind = true
annotation_method = manual_adjudicated
annotation_assistance = AI-assisted human adjudication
```

The annotation was prediction blind with respect to the literal candidate and
was completed through AI-assisted human adjudication, with final review
decisions retained by the local reviewer. It is suitable as pilot/dev evidence.
It is not an independent human-only or multi-annotator held-out benchmark and
does not estimate inter-annotator agreement.

### 3.4 Literal candidate build

```text
build_id = scientific-entity-literal-v0.1-20260822T114316573133Z
build_status = candidate
prediction_manifest_sha256 = 875c0b2e15f92cfdb8dff156c115e5939725f486b27ea3d3e5cf135bdee44a0b
prediction_mentions_sha256 = 48ad845e2bc845608b7f4a6d29fdc4014ceda339c6e554b486f0baa8f208764d
extractor_fingerprint = 81574f26a1e5166460a927e45d160c8d51c7d7d5b2418944cbc1bfeeba6575fd
prediction_mention_count = 30
```

The literal v0.1 configuration contains a deliberately small fixed lexicon. It
exists to exercise the evidence pipeline, not to approximate production NER.

---

## 4. Matching policy

Exact matching requires the same:

```text
canonical/text identity
source field and source-text SHA-256
entity type
half-open character span
```

Relaxed matching additionally permits boundary differences when the entity type
and text identity are unchanged and character IoU is at least `0.5`. Assignment
is deterministic, greedy by descending IoU, and one-to-one.

---

## 5. Aggregate metrics

| Mode | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Exact | 10 | 20 | 425 | 0.333333 | 0.022989 | 0.043012 |
| Relaxed | 16 | 14 | 419 | 0.533333 | 0.036782 | 0.068818 |

```text
exact_match_count = 10
relaxed_only_match_count = 6
total_relaxed_match_count = 16
```

The literal control has measurable precision when it emits evidence, but recall
is far too low for product, graph, serving, or full-corpus use.

---

## 6. Source-field metrics

| Source field | Reference support | Prediction support | Exact P/R/F1 | Relaxed P/R/F1 |
|---|---:|---:|---|---|
| title | 58 | 0 | null / 0.000000 / null | null / 0.000000 / null |
| abstract | 377 | 30 | 0.333333 / 0.026525 / 0.049140 | 0.533333 / 0.042440 / 0.078624 |

The extractor is configured to inspect both source fields. Zero title
predictions mean that none of the small tracked literal rule set fired in the
sampled titles; it is not evidence that title processing was skipped.

---

## 7. Per-type metrics

| Entity type | References | Predictions | Exact P/R/F1 | Relaxed P/R/F1 | Support sufficient |
|---|---:|---:|---|---|---|
| task | 78 | 6 | 0.000000 / 0.000000 / 0.000000 | 0.500000 / 0.038462 / 0.071429 | true |
| method | 155 | 6 | 0.666667 / 0.025806 / 0.049689 | 1.000000 / 0.038710 / 0.074535 | true |
| dataset | 23 | 4 | 0.750000 / 0.130435 / 0.222223 | 1.000000 / 0.173913 / 0.296296 | true |
| metric | 38 | 4 | 0.750000 / 0.078947 / 0.142857 | 0.750000 / 0.078947 / 0.142857 | true |
| model | 108 | 10 | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | true |
| domain | 33 | 0 | null / 0.000000 / null | null / 0.000000 / null | true |

All six entity families meet the configured minimum of 20 reference mentions.
The document-count marker does not meet its configured minimum:

```text
minimum_document_count = 32
actual_document_count = 24
document_count_sufficient = false
promotion_sample_sufficient = false
metrics_are_descriptive_only = true
```

---

## 8. Structural error evidence

| Error kind | Count |
|---|---:|
| boundary_mismatch | 17 |
| type_mismatch | 2 |
| false_positive | 1 |
| false_negative | 406 |
| total | 426 |

`error_count` is not equal to exact `FP + FN`. A boundary or type mismatch
pairs one reference with one prediction into one structural error record.

Manual diagnostic inspection of the bounded evidence found a coherent rule-
baseline profile:

- compound task, method, dataset, and model names are often reduced to a shorter
  literal span;
- six boundary differences still satisfy relaxed IoU;
- eleven boundary differences remain below the relaxed threshold;
- two occurrences of `classification` overlap references typed as methods in
  their local context;
- the single unpaired false positive is a generic quality use of `accuracy`,
  not a named evaluation metric;
- the overwhelming error source is lexicon non-coverage, represented by 406
  unpaired false negatives.

These observations diagnose the control extractor. They are not new annotation
rules and must not be used to silently rewrite the frozen reference evidence.

---

## 9. Evidence-backed decision

The accepted decision is:

```text
literal baseline v0.1 = retain unchanged as deterministic control
current 24-paper review = pilot/dev evidence
literal lexicon expansion from this dev set = rejected as the next slice
duplicate evaluation harness = rejected
bounded candidate extractor selection and adapter = next authorized direction
production extractor selection = not yet performed
full-corpus entity build = not authorized
```

Adding terms observed in these 24 documents would improve the same-sample score
without establishing generalization. Any deterministic lexicon candidate must
instead have independent ontology provenance and licensing evidence.

The existing Scientific Entity Evaluation Harness remains the comparison
machinery for future candidates. The project should not create a second
competing benchmark truth.

---

## 10. Later annotation policy

Additional annotation is deferred until it answers a defined evidence need:

1. the current 24 documents may be used for bounded candidate diagnostics;
2. candidate selection must record model/data license, exact revision, artifact
   identity, resource requirements, determinism, and offline/cache behavior;
3. after a candidate is frozen, create a separate prediction-blind held-out
   sample, provisionally 48–64 documents;
4. do not tune rules, labels, prompts, or model choices on that held-out sample;
5. production or full-corpus acceptance requires a separate human decision.

The present evidence does not authorize training on the 435 reference mentions.

---

## 11. Storage and publication

The completed review and evaluation directories are generated local data and
remain ignored by Git. Because the annotation required manual work, their
immutable directories and checksums should be backed up privately.

```text
commit raw paper text = forbidden
commit local reference mentions = forbidden
commit annotator identity = forbidden
public dataset upload = not authorized
redistribution_allowed = false
publication_ready = false
```

This aggregate report contains no source-paper text and does not change the
project's paused publication decision.
