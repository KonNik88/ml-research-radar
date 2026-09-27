# Scientific Entity H2 v0.3 Independent Comparative Evaluation

## Purpose

This slice evaluates the already-frozen H2 selective semantic-typing intervention on the
already-frozen fresh held-out reference.

It is intentionally separate from both model inference and the final acceptance decision.

The sequence is:

```text
prediction-blind reference freeze
→ frozen H2 independent inference
→ strict inference validation
→ this comparative evaluation
→ strict evaluation validation
→ immutable acceptance decision
```

## Inputs

Frozen candidate:

```text
scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method
```

Candidate fingerprint:

```text
6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966
```

Frozen independent inference:

```text
scientific-entity-semantic-typer-h2-independent-inference-v0.3-20260927T102527705827Z
```

Fresh held-out sample:

```text
scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z
```

Frozen human review:

```text
scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z
```

Expected structural counts:

- 48 documents
- 929 reference mentions
- 830 frozen baseline predictions
- 830 H2 final typing predictions
- typer coverage 0.983133
- 39 frozen H2 overrides

These inference counts are lineage facts, not evaluation thresholds.

## Reused evaluation semantics

The slice reuses the existing Scientific Entity Evaluation v0.1 matcher:

- exact match = same text identity, same type, same half-open character span
- relaxed match = same text identity and same type with character IoU >= 0.5
- deterministic one-to-one matching
- six entity types
- decimal precision = 6

No new span matcher is introduced.

## Comparative typing population

The comparative typing population is independent of entity type.

A same-span case exists when a frozen baseline prediction and a human reference mention have:

- the same `canonical_id`
- the same source field
- the same source-text SHA-256
- the same `char_start`
- the same `char_end`

Within an identical span key, references are ordered by `reference_id` and baseline
predictions by `evidence_id`, then paired deterministically.

H2 is compared on the exact same baseline prediction identity through
`baseline_prediction_evidence_id`.

Therefore H2 cannot gain or lose cases by changing spans: H2 is a typing-only intervention.

## Comparative metrics

The slice computes:

- baseline same-span typing accuracy
- H2 same-span typing accuracy
- accuracy delta
- baseline six-type classification macro-F1
- H2 six-type classification macro-F1
- macro-F1 delta
- corrected errors
- introduced regressions
- net corrected cases
- regression rate
- baseline model→method count
- H2 model→method count
- model→method reduction fraction

Regression rate is:

```text
introduced_regressions / baseline_correct_same_span_cases
```

Model→method reduction is:

```text
(baseline_model_to_method - h2_model_to_method)
/
baseline_model_to_method
```

Required denominators fail closed if absent.

## Extraction metrics

In addition to typing-only comparative metrics, both frozen baseline predictions and H2
final predictions are evaluated against all 929 reference mentions with the existing v0.1
extraction matcher.

The slice stores:

- exact precision / recall / F1
- relaxed precision / recall / F1
- exact and relaxed match counts
- historical type-mismatch diagnostics

Historical diagnostics remain descriptive and are not promoted into new hard H2 criteria.

## Required diagnostic materialization

The immutable package includes:

- `same_span_cases.jsonl`
- `corrected_errors.jsonl`
- `introduced_regressions.jsonl`
- `model_to_method_direct_corrections.jsonl`
- `model_to_method_wrong_to_wrong.jsonl`

`model_to_method_wrong_to_wrong` means a baseline model→method case changed type but still
did not become correct. For the bounded H2 method→model intervention this file may
legitimately be empty.

## Frozen acceptance thresholds

This slice binds to the preregistered H2 gate:

- typer coverage >= 0.95
- same-span accuracy delta >= +0.01
- net corrected cases >= 5
- regression rate <= 0.05
- model→method reduction fraction >= 0.10
- macro-F1 delta >= 0.0
- exact F1 >= 0.396882
- relaxed F1 >= 0.414868 is desirable, not a hard gate

However this slice does **not** emit ACCEPT or REJECT.

The later immutable decision slice applies these frozen thresholds mechanically to the
validated evaluation evidence.

## Safety boundary

This slice:

- does not run GLiNER
- does not run the semantic typer
- does not tune the H2 threshold
- does not revise H2 policy
- does not mutate spans
- does not change taxonomy
- does not filter evaluation cases by human labels
- does not mutate canonical truth
- does not select a production extractor
- does not authorize a full-corpus build
- does not publish anything

Plan mode validates lineage but does not compute or expose quality metrics.

## Output

Immutable output root:

```text
data/entities/scientific_entity_semantic_typer_h2_independent_evaluation/v0.3/
```

Evaluation ID:

```text
scientific-entity-semantic-typer-h2-independent-evaluation-v0.3-20260927T102527705827Z
```

Required files:

```text
manifest.json
comparative_summary.json
baseline_evaluation.json
h2_evaluation.json
same_span_cases.jsonl
corrected_errors.jsonl
introduced_regressions.jsonl
model_to_method_direct_corrections.jsonl
model_to_method_wrong_to_wrong.jsonl
README.md
checksums.txt
```

After strict validation the next slice is:

```text
make_immutable_h2_independent_acceptance_decision
```
