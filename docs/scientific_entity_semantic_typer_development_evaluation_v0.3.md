# Scientific Entity Semantic Typer v0.3 — bounded candidate inference and development evaluation

## Scope

This slice executes the already frozen H1 hypothesis only on the immutable consumed-development package created by `Scientific Entity Semantic Typer Candidate v0.3`.

It does **not** create a new held-out set, modify upstream spans, tune thresholds, mutate canonical truth, select a production extractor, or authorize full-corpus inference.

## Inference boundary

Input is the immutable `development_cases.jsonl` package. The second-stage typer receives the target surface, bounded local context, and the six frozen semantic label definitions. Baseline type, baseline confidence, root-cause review labels, ambiguity labels, and reference type are not model features.

Inference produces an immutable prediction package containing:

- `manifest.json`
- `predictions.jsonl`
- `summary.json`
- `README.md`
- `checksums.txt`

If the exact synthetic target cannot be scored, the frozen baseline type is preserved as a fail-closed fallback. Coverage therefore remains an explicit gate and cannot be hidden by fallback behavior.

## Development evaluation

Primary metrics use only `primary_metric_eligible=true` cases. Same-span annotation-reference issues remain in diagnostics but are excluded from the primary gate.

The evaluator computes:

- baseline and candidate same-span accuracy;
- baseline and candidate macro F1 over the six canonical types;
- corrected baseline errors;
- newly introduced regressions;
- net corrected cases;
- regression rate over baseline-correct cases;
- second-stage typer coverage;
- `model -> method` reduction;
- `method -> task` counts;
- per-type metrics and bounded diagnostic slices.

## Frozen gates

The gates are inherited from `configs/scientific_entity_semantic_typer_candidate_v0.3.yaml` and are not changed after results are observed:

- typer coverage >= 0.95;
- same-span accuracy delta >= +0.01;
- net corrected cases >= 5;
- regression rate <= 0.05;
- `model -> method` reduction >= 10%;
- macro-F1 drop <= 0.

## Development decision

The decision policy is deterministic and frozen before real candidate results:

- `freeze_for_independent_acceptance` only if every gate passes;
- `revise_candidate` if the candidate has positive net improvement (`net_corrected_cases > 0` and accuracy delta > 0) but at least one gate fails;
- `reject_candidate` if positive net improvement is absent.

This decision is development-only. Even a frozen candidate still requires a new disjoint prediction-blind held-out before independent acceptance.

## Provenance and safety

Prediction and evaluation manifests pin the development package, candidate config/fingerprint, and parent prediction package by SHA-256. Strict validators recompute raw comparisons, metrics, gates, and the final development decision from immutable cases and predictions rather than trusting saved summaries.
