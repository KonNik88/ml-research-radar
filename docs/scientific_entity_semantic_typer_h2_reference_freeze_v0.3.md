# Scientific Entity H2 v0.3 — Prediction-Blind Reference Freeze

## Purpose

This slice provides the versioned annotation/reference-freeze tooling for the new independent H2 v0.3 held-out sample.

It reuses the existing Scientific Entity manual-annotation primitives and reference semantics from the v0.2 independent held-out cycle. It does **not** redesign annotation, taxonomy, span handling, H2 policy, or the frozen independent-acceptance gate.

## Frozen lineage

Candidate:

`scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method`

Candidate fingerprint:

`6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966`

Fresh held-out sample:

`scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z`

Review ID:

`scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z`

Sample shape:

- 48 documents
- 96 title/abstract annotation rows
- 120 previously consumed documents excluded
- overlap with consumed union = 0
- prediction-blind sample
- H2 inference not executed
- evaluation not executed

The tooling is also bound to the already frozen H2 independent-acceptance gate canonical config SHA-256:

`3ed17739796807046269b88aab40ced2cc10ca1e45ff67dc8965a98070c17a89`

## Reused annotation semantics

The annotation semantics remain unchanged:

- annotation method: `manual_adjudicated`
- guideline: `scientific_entity_annotation_guidelines_v0.1`
- source fields: `title`, `abstract`
- entity types: `task`, `method`, `dataset`, `metric`, `model`, `domain`
- all 96 annotation rows must be completed
- unresolved uncertain mentions must equal zero
- each entity type must have at least 20 reference mentions
- total references must not exceed 5000
- mention surface must match the exact source slice
- duplicate typed spans are forbidden

Existing reusable primitives remain authoritative:

- `ScientificEntityBlindAnnotationRow`
- `validate_completed_annotations()`
- `build_reference_mentions()`
- `annotation_counts()`

## Parent validation

Before either a working copy or frozen reference can be produced, the tooling validates:

1. the frozen H2 independent-acceptance gate identity;
2. candidate ID and fingerprint consistency;
3. exact H2 fresh-held-out sample identity;
4. sample manifest SHA-256 and selected-ID SHA-256;
5. 48-document / 96-row shape;
6. 120-document consumed-evidence exclusion boundary;
7. zero overlap with consumed evidence;
8. prediction blindness and fail-closed safety flags;
9. the full existing `validate_h2_fresh_heldout_sample()` strict parent validator.

This intentionally preserves the already proven sample-validation path instead of creating a second sampling validator.

## Working copy

The preparation command creates a mutable non-evidence copy:

`data/entities/scientific_entity_semantic_typer_h2_annotation_work/v0.3/<review_id>/annotations_completed.jsonl`

The immutable sample `annotations_working.jsonl` is never edited.

The working copy contains no model predictions or score margins.

## Frozen reference package

After manual annotation is complete and adequate, freeze materializes an immutable package under:

`data/entities/scientific_entity_semantic_typer_h2_reference/v0.3/<review_id>/`

Files:

- `completed_annotations.jsonl`
- `review_manifest.json`
- `reference_mentions.jsonl`
- `completion_manifest.json`
- `annotation_audit_summary.json`
- `README.md`
- `checksums.txt`

The completion manifest binds the reference evidence to:

- H2 candidate ID;
- H2 candidate fingerprint;
- independent-acceptance gate canonical SHA-256;
- fresh held-out sample identity;
- sample manifest and source-artifact hashes;
- selected canonical IDs;
- annotation/reference counts and adequacy;
- fail-closed safety state.

## Safety boundary

Until the reference package is frozen and strict validation is green:

- baseline/H1/H2 predictions must not be inspected for this held-out;
- H2 inference must not run;
- evaluation must not run;
- threshold/policy tuning is forbidden;
- taxonomy/span policy changes are forbidden;
- no full-corpus build is authorized.

Freezing the human reference does not accept H2 and does not authorize production extraction.

## Next slice

After strict reference validation:

`run_frozen_h2_independent_inference`

Only then may the frozen v0.2c baseline and frozen H2 intervention be materialized for the 48 held-out papers.
