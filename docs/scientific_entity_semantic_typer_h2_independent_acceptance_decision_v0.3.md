# H2 v0.3 — Immutable Independent Acceptance Decision

## Purpose

This decision slice applies the **previously frozen** v0.3 acceptance gate to the
**already executed and independently validated** H2 comparative evaluation.
It **does not create new candidate criteria** or adjust any thresholds after
seeing held-out metrics. A clean exit from the evaluation tool alone is not evidence;
this slice re-runs the Slice 6 strict validator (including independent recomputation).

## Inputs

- `configs/scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml`
  (semantic SHA-256 `3ed17739796807046269b88aab40ced2cc10ca1e45ff67dc8965a98070c17a89`)
- `configs/scientific_entity_semantic_typer_h2_independent_evaluation_v0.3.yaml`
- immutable H2 independent evaluation package, 48 documents, 929 frozen human labels,
  830 baseline and 830 H2 predictions
- the same inference, sample, reference, development package, previous held-out
  sample and frozen-candidate inputs needed by the Slice 6 validator
- `completion_manifest.json` from the prediction-blind human reference freeze.

## Decision logic

Hard gates (ALL required):

1. reference adequacy = PASS (strictly validated frozen manual annotation);
2. candidate fingerprint matches frozen H2 candidate;
3. typer coverage >= 0.95;
4. same-span accuracy delta >= 0.01;
5. net corrected cases >= 5;
6. introduced regression rate <= 0.05;
7. model-to-method error reduction fraction >= 0.10;
8. macro-F1 delta >= 0.0;
9. independent H2 extraction exact F1 >= 0.396882.

`relaxed F1 >= 0.414868` is a **desirable, NON-HARD** diagnostic.
Historical v0.2c absolute confusion caps are **NON-HARD** diagnostics from a
*different* held-out. Missing critical denominators cause `fail closed` (no
verdict artifact), not a fabricated pass.

If all hard gates pass, use the exact frozen decision token:

`accept_h2_as_independently_validated_bounded_semantic_typing_intervention`

Otherwise use:

`reject_h2_independent_acceptance`

The latter consumes held-out evidence. Any later candidate revision requires a
**new independent disjoint held-out**; no retuning against this evaluation.

## Output and safety

One-shot immutable directory contains only:

- `decision.json` — all nine hard gates and final decision, plus relaxed-F1 diagnostic;
- `historical_diagnostics.json` — descriptive v0.2c-style counts, not gates;
- `manifest.json` — source/config SHA-256 lineage and fail-closed safety state;
- `README.md` and `checksums.txt` — human explanation and file integrity.

The PLAN does not make a decision, leak quality metrics, or write any output.
`--execute` must run only **once**, after tooling is merged to `main`. No inference,
evaluation, tuning, policy revision, canonical corpus mutation, reconciliation,
production extractor selection, full corpus build, or publication is authorized.

## Workflow

1. Merge new tooling and tests before decision execution.
2. Run PLAN without `--execute` with the same input paths as Slice 6,
   adding `--evaluation-dir` for the immutable Slice 6 output.
3. Verify the plan reports strict validation OK, reference adequacy true,
   and `decision_made=False`; it must not print quality metrics or verdict.
4. Run `--execute` once with exactly the same arguments.
5. Run the paired decision validator with `--decision-dir` and `--strict`.
6. Record the result. Production selection/full-corpus authorization remain
   independent future work.
