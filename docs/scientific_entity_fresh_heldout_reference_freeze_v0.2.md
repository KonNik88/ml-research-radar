# Scientific Entity Fresh v0.2 Prediction-Blind Reference Freeze

## Status

```text
status = tooling frozen
fresh sample = materialized and independently validated
manual annotations = not yet completed
reference evidence = not yet frozen
model inference = forbidden
candidate evaluation = forbidden
```

## Purpose

This layer supplies the bounded workflow that converts the already-materialized
fresh v0.2 held-out sample into immutable human reference evidence **without
exposing annotators to v0.2c predictions**.

It deliberately reuses the established v0.1 annotation/reference semantics:

- `scientific_entity_blind_annotation_v0.1` rows;
- exact half-open Unicode offsets;
- the same six scientific entity types;
- `manual_adjudicated` reference evidence;
- deterministic `mention_id` / `reference_id` construction;
- existing evaluation-harness `review_manifest.json` and
  `reference_mentions.jsonl` formats.

No second annotation framework is introduced.

## Frozen sample identity

```text
sample_id = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z
review_id = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z
selected canonical IDs SHA-256 = 0c4bf55fa47192d8523a5ccd0d89b3326562ff6b464f108d330d87286feb7d7a
documents = 48
annotation rows = 96
development overlap = 0
```

Before either working-copy preparation or reference freeze, the implementation
reruns the independent fresh-sample validator against canonical truth and the
immutable 72-paper development exclusion package.

## Mutable annotation working copy

The immutable sample package is never edited.

The helper creates a separate mutable non-evidence directory:

```text
data/entities/scientific_entity_fresh_heldout_annotation_work/v0.2/<review_id>/

annotations_completed.jsonl
README.md
```

`annotations_completed.jsonl` begins as an exact copy of the frozen blank
`annotations_working.jsonl` template.

During manual review only these fields may change:

```text
annotation_complete
mentions
reviewer_note
```

The source text, source hash, sample stratum, enrichment type, canonical ID,
review ID, and source field remain immutable.

## Reference adequacy gate

Reference freeze is fail-closed until all of the following are true:

```text
annotation rows = 96
all annotation_complete = true
unresolved uncertain mentions = 0
reference mentions per task >= 20
reference mentions per method >= 20
reference mentions per dataset >= 20
reference mentions per metric >= 20
reference mentions per model >= 20
reference mentions per domain >= 20
total reference mentions <= 5000
```

If one entity type does not reach 20 references, the candidate still must not be
run. Any sample-remediation rule would need a separate prediction-blind design;
model predictions cannot be used to repair reference coverage.

## Immutable reference package

After a successful PLAN and explicit `--execute`, the layer freezes:

```text
data/entities/scientific_entity_fresh_heldout_reference/v0.2/<review_id>/

completed_annotations.jsonl
review_manifest.json
reference_mentions.jsonl
completion_manifest.json
annotation_audit_summary.json
README.md
checksums.txt
```

Overwrite is forbidden.

The independent validator revalidates the parent sample, compares completed
annotations against the original blank template, recomputes every reference
mention, checks all hashes/checksums and adequacy gates, and requires fail-closed
safety provenance.

## Safety boundary

Before a successful immutable reference freeze:

```text
v0.2c predictions visible during annotation = false
v0.2c inference = forbidden
threshold tuning = forbidden
prompt/model changes = forbidden
candidate evaluation = forbidden
canonical truth mutation = false
production selection = false
full-corpus build authorization = false
```

After strict reference validation, and only then:

```text
next = run_frozen_v02c_raw_inference_once
```
