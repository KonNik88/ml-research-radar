# Scientific Entity H2 v0.3 — Production Audit Reference Freeze

## Scope

This slice freezes the completed **prediction-blind human annotations** for the H2 v0.3 production audit into immutable reference evidence.

It is deliberately separated from unblinding and promotion-gate evaluation.

Bound audit:

- audit ID: `scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z`
- cases: `240`
- candidate build: `scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z`
- candidate fingerprint: `6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966`
- materialization fingerprint: `5c528cab17e2d48c812f6013fbd4f7d966d8e0ccab5eff4e86de166e92641366`
- canonical snapshot: `61075` papers, SHA-256 `3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff`.

## Input

Completed annotations are expected at:

`data/entities/scientific_entity_semantic_typer_h2_production_audit_annotation_work/v0.3/scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z/annotations_completed.jsonl`

The immutable audit sample remains the authority for all source/span fields.

The freeze verifies that every completed row matches the corresponding blank annotation row exactly for:

- audit ID / case ID;
- canonical ID;
- source field;
- source-text SHA-256;
- source text;
- character offsets;
- surface text;
- row order.

Only the human annotation fields may differ.

## Frozen package

The immutable reference package contains exactly:

- `reference_annotations.jsonl` — frozen human labels for all 240 audit spans;
- `annotation_summary.json` — descriptive counts only;
- `manifest.json` — frozen lineage, hashes and safety flags;
- `README.md`;
- `checksums.txt`.

The summary may report overall annotation counts/rates, but this slice does **not** evaluate preregistered promotion gates and does not reconstruct hidden audit strata.

## Safety boundary

This slice must not read:

- `final_mentions.jsonl`;
- `h2_overrides.jsonl`;
- `semantic_typer_predictions.jsonl`;
- any other candidate prediction file.

It must not:

- reconstruct override/preserved/fallback strata;
- run inference;
- evaluate H2 quality or promotion gates;
- tune thresholds or revise H2;
- mutate canonical truth;
- promote production `latest`.

## Workflow

1. Merge this tooling before reference execution.
2. Run PLAN against the completed annotation file.
3. Confirm `candidate_prediction_files_read=False`, `unblinding_executed=False`, and 240/240 completed rows.
4. Execute the freeze exactly once.
5. Strict-validate the immutable reference package.
6. Only after strict validation may the next slice unblind the sample, reconstruct the three frozen strata, and evaluate the preregistered promotion gates.
