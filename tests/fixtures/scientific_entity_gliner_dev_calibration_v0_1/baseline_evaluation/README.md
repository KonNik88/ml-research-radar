# Scientific Entity Evaluation v0.1

This directory contains bounded, deterministic quality evidence for
scientific-entity mention extraction. It is derived and rebuildable.

It is not canonical paper truth, not a reconcile input, not a production
extractor selection, not a full-corpus authorization, and not publication ready.

## Evaluation

- evaluation_id: `scientific-entity-gliner-calibration-fixture-baseline-v0.1`
- status: `fixture`
- generated_at_utc: `2026-08-23T09:00:00+00:00`
- document_count: `4`
- reference_mention_count: `18`
- prediction_mention_count: `17`
- exact_match_count: `14`
- relaxed_only_match_count: `1`
- error_count: `5`

## Files

- `manifest.json` — immutable input/output provenance and safety state
- `metrics.json` — micro and source-field exact/relaxed metrics
- `per_type_metrics.json` — exact/relaxed metrics for all six types
- `matches.jsonl` — deterministic one-to-one exact/relaxed matches
- `errors.jsonl` — automatic structural error evidence
- `checksums.txt` — raw-byte SHA-256 checksums

Metrics are descriptive only. Manual review evidence and a separate
acceptance decision are required before model selection or scale-up.
