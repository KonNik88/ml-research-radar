# Scientific Entity H2 v0.3 — Full-Corpus Candidate Materialization

## Purpose

This slice materializes the independently accepted H2 bounded semantic-typing intervention over the exact canonical snapshot authorized by the immutable production authorization record.

It is **candidate-only**. It does not promote a production/latest entity layer, mutate canonical truth, overwrite any trusted latest artifact, or authorize publication.

## Frozen inputs

- authorization: `scientific-entity-semantic-typer-h2-production-authorization-v0.3-3cc6e3c779fee351-6d3782fb`
- canonical SHA-256: `3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff`
- canonical documents: `61075`
- H2 candidate fingerprint: `6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966`
- frozen baseline: v0.2c raw-floor policy
- semantic typer: frozen H1 configuration
- H2 rule: baseline `method` + typer `model` + `score_margin >= 0.10` -> `model`; otherwise preserve baseline.

## Execution semantics

PLAN is read-only and performs no model inference.

EXECUTE first revalidates the immutable production authorization and exact canonical SHA/count. This occurs before model loading. A canonical mismatch fails closed.

The builder streams the corpus document by document. It stores:

- `upstream_raw_mentions.jsonl`
- `baseline_mentions.jsonl`
- `semantic_typer_cases.jsonl`
- `semantic_typer_predictions.jsonl`
- `h2_overrides.jsonl`
- `final_mentions.jsonl`
- `summary.json`
- `manifest.json`
- `README.md`
- `checksums.txt`

The semantic typer is run only for baseline mentions typed `method`. This is a semantics-preserving optimization because the frozen H2 intervention can only change `method -> model`; every non-method baseline mention is preserved exactly.

## Authorization consumption

One successful immutable candidate package consumes the authorization. Before EXECUTE the builder scans the candidate output root for an existing manifest bound to the same authorization ID and fails closed if one already exists.

Failed attempts that never publish an immutable final package do not create a successful candidate materialization.

## Validation and promotion

The strict validator revalidates authorization and canonical identity, checks checksums/layout/schemas, recomputes the frozen baseline from raw predictions, verifies that semantic cases are exactly the baseline-method subset, recomputes H2 override semantics, and verifies every final span against the authorized canonical snapshot.

A valid candidate still has:

- `production_latest_promotion_authorized = false`
- `canonical_truth_mutated = false`

Promotion requires a separate later gate and explicit decision.
