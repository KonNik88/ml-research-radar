# Scientific Entity Fresh v0.2 Held-Out Sample

## Status

```text
status = materialized and strictly validated
parent = Scientific Entity Fresh v0.2 Held-Out Gate Design Freeze
sample_id = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z
review_id = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z
sample selected = true
model inference = forbidden
evaluation = forbidden
next = prediction-blind manual annotation and reference freeze
```

## Materialized result

```text
sample_id = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z
review_id = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z
canonical input rows = 61075
eligible non-development documents = 60997
excluded consumed development documents = 72 / 72
held-out/development overlap = 0
uniform documents = 24
type-enriched documents = 24
selected documents = 48
annotation rows = 96
selected canonical IDs SHA-256 = 0c4bf55fa47192d8523a5ccd0d89b3326562ff6b464f108d330d87286feb7d7a
strict independent validation = 43 / 43
required failures = 0

prediction blind = true
candidate predictions read during sampling = false
model inference executed = false
evaluation executed = false
fresh held-out reference consumed = false
canonical truth mutated = false
production extractor selected = false
full-corpus build authorized = false
```

The validator reproduced this exact sample from the frozen gate configuration,
current canonical corpus and immutable 72-paper development parent.

## Purpose

This layer materializes the sample defined by the already-frozen
`scientific_entity_fresh_heldout_gate_v0.2` contract.

It reuses the established held-out mechanics:

```text
24 deterministic uniform papers
+
4 deterministic type-enriched papers x 6 entity types
=
48 fresh papers
```

The v0.2 change is the exclusion boundary: all 72 canonical IDs are loaded from
the immutable v0.2a development package rather than hard-coded.

## Fail-closed lineage

Required development parent:

```text
scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z
documents = 72
```

Preparation verifies the parent ID/schema/SHA/count and requires all 72 consumed
IDs to still exist in the current canonical corpus.

## Output

```text
data/entities/scientific_entity_fresh_heldout_sample/v0.2/<sample_id>/

canonical_documents.sample.jsonl
sample_assignments.jsonl
annotations_working.jsonl
selected_papers.tsv
manifest.json
README.md
checksums.txt
```

The 96 annotation rows preserve the established
`scientific_entity_blind_annotation_v0.1` schema and are all initially blank:

```text
annotation_complete = false
mentions = []
reviewer_note = null
```

No candidate predictions are read or emitted.

## Validation

The independent validator reloads the frozen gate, canonical corpus and exact
72-paper development parent, then recomputes the deterministic sample. It
requires byte-for-byte reproduction of the sample, assignments, blank
annotation template, overview, README and manifest.

Required shape:

```text
selected documents = 48
uniform = 24
type-enriched = 24
each enriched entity type = 4
annotation rows = 96
development overlap = 0
prediction blind = true
model inference = false
evaluation = false
fresh references consumed = false
production extractor selected = false
full-corpus build authorized = false
```

PLAN is non-writing and `--execute` refuses overwrite.

After strict validation:

```text
next = prediction_blind_manual_annotation_and_reference_freeze
```
