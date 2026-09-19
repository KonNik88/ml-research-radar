# Scientific Entity v0.3 H2 Fresh Held-Out Sample

This layer prepares the new independent, prediction-blind held-out sample for the
already frozen H2 semantic-typing candidate.

Frozen candidate:

```text
scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method
fingerprint = 6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966
```

## Why a new held-out is required

H2 was selected using consumed development evidence derived from the previous
v0.2c fresh held-out. That previous 48-paper sample can no longer be reused for
independent acceptance.

The new exclusion boundary is therefore:

```text
72 earlier semantic-prompt development papers
+
48 previous v0.2c fresh-heldout papers
=
120 consumed documents
```

The two consumed sets must be disjoint and all 120 IDs must still exist in the
current canonical corpus. Sampling fails closed otherwise.

## Sampling mechanics

The established v0.2 mechanics are retained:

```text
24 deterministic uniform papers
+
4 deterministic type-enriched papers x 6 entity types
=
48 papers
```

A new v0.3-H2 seed is used after excluding the complete 120-document consumed
evidence boundary.

## Prediction blindness

Sampling requires the already frozen H2 identity but does not read or generate
H1/H2 predictions. The annotation template is blank:

```text
annotation_complete = false
mentions = []
reviewer_note = null
```

No prediction, predicted type, score margin or per-type score fields are emitted.
H2 inference is forbidden until the human reference has been completed and
frozen in a later slice.

## Output

```text
data/entities/scientific_entity_fresh_heldout_sample/v0.3/<sample_id>/

canonical_documents.sample.jsonl
sample_assignments.jsonl
annotations_working.jsonl
selected_papers.tsv
exclusion_provenance.json
manifest.json
README.md
checksums.txt
```

`exclusion_provenance.json` records the consumed evidence boundary and exact H2
candidate fingerprint without exposing predictions.

## Validation

Strict validation independently reloads the canonical corpus and all three
immutable parents:

- 72-paper development package;
- previous 48-paper v0.2c fresh held-out;
- frozen H2 candidate.

It then recomputes the entire sample byte-for-byte and requires:

```text
selected documents = 48
uniform = 24
type-enriched = 24
each enriched entity type = 4
annotation rows = 96
consumed union = 120
sample/consumed overlap = 0
prediction blind = true
H2 inference = false
reference frozen = false
threshold tuning = false
policy revision = false
canonical truth mutation = false
production extractor selected = false
full-corpus build authorized = false
```

After strict validation the next slice is:

```text
prediction_blind_manual_annotation_and_reference_freeze_for_h2
```
