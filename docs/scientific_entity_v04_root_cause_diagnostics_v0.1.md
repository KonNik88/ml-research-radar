# Scientific Entity v0.4-A — historical root-cause review v0.1

## Status and authorization

**Diagnostic-only tool**, not a new NER version, not a candidate experiment, and not an acceptance evaluation. This package includes the historical 9E report at `docs/scientific_entity_full_ner_coverage_results_review_v0.1.md`. The 9D audit has already been unblinded. We may use it to **describe and hypothesize** error mechanisms, but not to optimize v0.4 or report its improvement. No changes to H2 v0.3 production, 9B frozen reference or 9C frozen policy are permitted.

## Fixed evidence

- 9D evaluation ID: `scientific-entity-full-ner-coverage-unblind-evaluation-v0.1-3cc6e3c779fee351`.
- 120 sample fields, 60 `title` and 60 `abstract`.
- 972 annotations, including 68 `uncertain` (primary 9D evaluation uses 904 certain gold mentions).
- 851 selected predictions, 34 uncertain-only predictions ignored for the primary panel.
- Typed-exact P/R/F1: 0.408812729498164 / 0.3694690265486726 / 0.3881464264962231.
- 9D `diagnostics`: 114 exact-span wrong-type, 26 boundary-only, 9 boundary+type; residual 421 gold and 334 predictions are *post-matching residuals*, not a proven mechanistic taxonomy.
- 9D strict validator: 22/22 checks passed at execution time; this tool also checks hashes and row/lineage identity before making a queue.

## Scope

This tool reads ONLY the immutable 9D `manifest.json`, `summary.json`, `cases.jsonl`, `selected_predictions.jsonl` and the immutable 9B `annotations.jsonl`. It verifies file hashes against the 9D manifest and the frozen annotations SHA. **It does not read** the production `final_mentions.jsonl`, call models, tune thresholds, or write to the frozen directories. `PLAN` does not write anything; `--execute` writes a human-editable review work folder, refusing to overwrite prior work.

`review_items.jsonl` includes a full source-field text and a proposed review example with an optional reference span, an optional prediction span, and empty *review* fields. For uncertain annotations, consult the original reference rather than rewriting it. Do not interpret the candidate's category as adjudicated root cause.

## Sampling protocol

Deterministic seed: `scientific-entity-v04-historical-error-review-v0.1`. The script selects up to **76** examples by fixed quotas: 20 residual FN, 20 residual FP, 16 exact-span wrong-type, 8 boundary-only, 6 boundary+type, 6 zero-prediction title FN. It cycles across `(field, entity type)` strata, with a maximum of four review items per original field. The output manifest records realized counts; if a quota cannot be satisfied, execution fails instead of silently substituting examples. The fixed sample is **purposeful, not representative**; frequency proportions in this subset are not unbiased error rates. One historical field may contribute several distinct examples.

## Manual review (two reviewers where feasible)

For each item, inspect **the complete `source_text`**, and both spans, then fill:

- `review_status`: `reviewed`, `needs_adjudication`, or `deferred`.
- `root_cause`: choose one of `candidate_missing`, `candidate_partial`, `generic_candidate`, `type_taxonomy_confusion`, `boundary_mismatch`, `nested_overlap`, `annotation_scope_disagreement`, `multifactor`, `other`, `not_error_under_guideline`; leave `null` until reviewed. **One dominant cause is a qualitative finding, not a scoring-policy rewrite.**
- `annotation_guideline_question`: optional formulation of an ambiguity; it is *not* a change to frozen gold labels.
- `reviewer_notes`: evidence from wording and coordinates, avoid unsupported conjecture about GLiNER internals.
- `suggested_hypothesis`: a falsifiable next-step hypothesis that will be tested on **new disjoint development data**.

When reviewers disagree, use `needs_adjudication`; record both rationales outside the immutable output. Avoid altering any source spans or model predictions. Review queue files with full source text belong to the local analysis work area, **not a public code commit by default**.

## Execution

1. Commit the tooling and 9E report in a feature branch; merge to `main` before creating local work outputs.
2. Run `python -m pytest tests/smoke/test_scientific_entity_v04_root_cause_diagnostics.py -q`.
3. Run PLAN: `python -m scripts.entities.build_scientific_entity_v04_root_cause_review_queue`. Check sample counts, hashes, `model_inference_executed=False`, `full_production_predictions_read=False`, `plan_writes_output=False`, `output_already_exists=False`.
4. On `main`, run `python -m scripts.entities.build_scientific_entity_v04_root_cause_review_queue --execute` **once** to create a separate work folder under `data/entities/scientific_entity_v04_root_cause_review_work/v0.1/`.
5. Manual review; summarize hypotheses in a separate interpretive note (no metric tuning).
6. Only then define a fresh, disjoint v0.4 development annotation cohort plus an additional independent acceptance heldout, with exclusions against historical IDs and samples.

## Stop conditions

Stop on any mismatch in 9D checksums, reference SHA, per-case lineage or prediction counts, output path already existing, insufficient quotas, or missing data. Never weaken a frozen validator/alter historic reference to "fix" a diagnostic. No full-corpus inference is needed for this work.
