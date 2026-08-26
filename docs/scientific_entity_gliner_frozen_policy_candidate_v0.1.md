# Scientific Entity GLiNER Frozen Policy Candidate v0.1

## Status

```text
status = completed bounded dev candidate materialization
production_extractor_selected = false
full_corpus_build_authorized = false
publication_ready = false
canonical_truth_mutated = false
current_24_paper_dev_set_becomes_held_out = false
```

## Purpose

This checkpoint records the deterministic materialization of the frozen GLiNER
development policy selected by the accepted 24-paper calibration. The slice does
not rerun GLiNER and does not change model weights, prompts, canonical paper data,
or any serving layer. It converts one frozen prediction build into a new immutable
candidate evidence build with policy-aware evidence identity and explicit lineage.

## Frozen policy identity

```text
parent_build_id = scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z
calibration_id = scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z
selected_profile = balanced_f1
selected_trial_id = calibration-trial:1172aea9d875d59f3b39cc21488dec8f
default_threshold = 0.50
title_threshold = 0.55 inclusive
abstract_threshold = 0.65 inclusive
entity_type_thresholds = none
```

The policy is frozen. This materializer does not expose arbitrary threshold tuning.

## Identity semantics

The accepted identity decision is:

```text
mention_id remains stable
policy-aware extractor/config fingerprint changes
therefore evidence_id changes
```

The span, source field, source-text hash, entity type, surface text, and confidence
score are preserved from the parent prediction. The new evidence identity means
that the same mention is now emitted under a different effective evidence policy.

Parent/candidate evidence lineage is stored separately rather than changing the
base `ScientificEntityMentionEvidence` contract.

## Output layout

The standard six-file Scientific Entity Evidence layout is preserved:

```text
mentions.jsonl
manifest.json
schema.json
data_quality_summary.json
README.md
checksums.txt
```

The candidate adds structured derivation evidence:

```text
derivation_manifest.json
evidence_lineage.jsonl
```

`derivation_manifest.json` records parent/calibration/trial identity, policy,
selected/rejected counts, fingerprints, checksums, and safety facts.

`evidence_lineage.jsonl` records deterministic per-row mapping:

```text
mention_id
parent_evidence_id
candidate_evidence_id
```

## Execution boundary

The candidate is a read-only materialization over existing immutable artifacts.

```text
model_inference_executed = false
model_download_executed = false
provider_api_used = false
parent_build_mutated = false
canonical_documents_mutated = false
```

The materializer reuses the same `filter_predictions(...)` threshold kernel as
the dev calibration layer. This prevents calibration and materialization from
drifting to different threshold semantics.

## Accepted real build

```text
build_id = scientific-entity-gliner-small-v2.5-frozen-policy-v0.1-20260826T102020767519Z
input_document_count = 24
input_prediction_count = 546
selected_prediction_count = 391
rejected_prediction_count = 155
status = candidate
```

The specialized frozen-policy validator passed:

```text
total_checks = 69
required_failed_count = 0
mention_count = 391
```

The historical literal-baseline `check_scientific_entity_evidence_build` validator
is intentionally not the acceptance validator for this model-score candidate. It
encodes literal-baseline-specific assumptions such as the six-file-only layout
and `confidence_kind = not_available`. Frozen-policy acceptance therefore uses
the dedicated validator plus the extractor-independent evaluation harness.

## Dev evaluation reproduction

The materialized candidate was evaluated against the same already-consumed
24-paper / 435-reference development evidence. This is a semantic consistency
check, not new held-out evidence.

```text
evaluation_id = scientific-entity-evaluation-v0.1-20260826T102636476211Z
document_count = 24
reference_mention_count = 435
prediction_mention_count = 391
exact_match_count = 157
relaxed_only_match_count = 10
error_count = 405
validator = 69 / 69 required checks
```

Micro metrics reproduce the frozen calibration outcome exactly:

```text
exact precision = 0.401535
exact recall = 0.360920
exact F1 = 0.380146

relaxed precision = 0.427110
relaxed recall = 0.383908
relaxed F1 = 0.404358
```

Source-field metrics remain diagnostic:

```text
title exact F1 = 0.495049
abstract exact F1 = 0.364138
```

Error evidence:

```text
boundary_mismatch = 17
type_mismatch = 90
false_positive = 127
false_negative = 171
```

## Evidence sufficiency boundary

The evaluation correctly remains descriptive only:

```text
minimum_document_count = 32
document_count_sufficient = false
promotion_sample_sufficient = false
metrics_are_descriptive_only = true
production_extractor_selected = false
full_corpus_build_authorized = false
publication_ready = false
```

The existing 24-paper package has already been used for comparison, calibration,
and policy selection. It must never be relabeled as held-out evidence.

## Accepted next slice

The next authorized Scientific Entity slice is independent held-out review
evidence:

```text
new papers only
disjoint from the current 24-paper dev package
prediction-blind annotation
stratified sampling
hard minimum = 32 papers
preferred target = 48 papers when manual workload permits
no threshold tuning on held-out evidence
```

`task` degradation observed on the dev package is not repaired in this slice.
Per-type thresholds remain diagnostic only. A second-stage classifier, prompt
change, or alternative extractor requires separate evidence after held-out review.

## Non-goals

This checkpoint does not authorize:

- production extractor selection;
- full-corpus entity extraction;
- entity fields in canonical documents;
- threshold retuning on the current 24 papers;
- combined per-type policy selection;
- Qdrant/graph/dataset rebuilds;
- full-text ingestion;
- RAG/GraphRAG;
- Airflow, Ray, Kafka, or Kubernetes work.
