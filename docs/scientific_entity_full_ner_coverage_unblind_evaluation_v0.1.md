# 9D — Full NER Coverage Audit: Controlled unblind and immutable evaluation

## Purpose

Compare the existing trusted H2 v0.3 `final_mentions.jsonl` with 9B's immutable, prediction-blind 120-field reference. All scoring rules were locked in 9C before looking at predictions. 9D cannot update production, change reference, revise thresholds, or run a model. Its only outputs are immutable evaluation artifacts.

## Evaluation scope and constraints

- 60 sampled titles plus 60 sampled abstracts, **not corpus-prevalence-weighted**. Report pooled *balanced-field* and title/abstract metrics separately; do not extrapolate pooled P/R/F1 as population truth.
- Parent 9B reference: 120 fields, 972 human mentions, of which 68 are uncertain and 904 certain.
- Source: currently trusted full-corpus H2 candidate with 846,264 final mentions, SHA `518f3984d3dcd2aa5e2a84c96eec2fadce8b6dc6b49eef0d7a908533145394c1`.
- **PLAN does not read the prediction JSONL**. EXECUTE reads that existing file *once*, hashes and counts every record, but parses/retains predictions only for sampled fields. No inference.
- Strict validation rereads the existing JSONL to reproduce all immutable evaluation files; this is additional I/O, not an inference run.

## Frozen matching rules (9C)

Primary `typed_exact`; secondary `span_only_exact`, `span_only_relaxed`, `typed_relaxed`. Relaxed means positive character overlap with IoU at least 0.50. One-to-one per field; maximize cardinality first, then sum of IoU; deterministic stable tie-breaking. Duplicate predictions remain independent and count as FP when unmatched. Nested gold spans are permitted.

Primary gold = certain mentions only. Before matching, predictions overlapping uncertain gold but **not** any certain gold are ignored and separately counted. Predictions touching a certain mention are kept even when they also overlap uncertain. Sensitivity analysis includes all uncertain references as provisional gold and all predictions, with distinct labeling. Primary / secondary panels are all generated for `balanced`, `title`, `abstract`. Per-type metrics are for typed panels; macro F1 covers reference-supported types only. Undefined ratios are `null`.

## Diagnostic output and caveats

`cases.jsonl` lists 120 per-field scored outcomes and unmatched examples, `selected_predictions.jsonl` preserves only sampled-field production predictions, `summary.json` provides panels, per-type metrics and uncertainty sensitivity. Diagnostics for unmatched errors distinguish exact type mismatches, boundary-only same type, both boundary and type, and remaining unmatched items; these are post-evaluation descriptions, not reference edits. Primary scores do not carry a precommitted PASS/FAIL threshold and make no production promotion decision.

## Operations

1. Add tooling in a new feature branch, run tests and PLAN. PLAN must report `production_prediction_file_read=False`, `unblind_executed=False`, `plan_writes_output=False`, and `evaluation_record_already_exists=False`.
2. Merge tooling into `main`, run tests + PLAN again.
3. Run exactly one `--execute` (reads existing trusted predictions; no model calls). Once it succeeds, **do not rerun EXECUTE**.
4. `python -m scripts.validation.check_scientific_entity_full_ner_coverage_unblind_evaluation --strict`. Requires zero failed checks and exact byte-for-byte reproducibility.
5. Examine 9D metrics and design v0.4 diagnosis (if necessary) without changing frozen 9A–9D.

Never commit source data, large predictions, working labels, or generated immutable packages unless repository policy explicitly permits. Keep previous production latest untouched. Original heldout and 240-case audit are historical evidence only, not tuning data.
