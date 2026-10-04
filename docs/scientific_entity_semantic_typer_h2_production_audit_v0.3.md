# Scientific Entity H2 v0.3 — Production Audit / Promotion Gate

## Scope

This slice is a **prediction-blind production safety audit** of the already accepted and strictly validated H2 full-corpus candidate. It does not run model inference, change H2, mutate the canonical corpus, or promote `latest`.

Bound candidate:

- build: `scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z`
- canonical snapshot: `61075` documents, SHA-256 `3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff`
- final mentions: `846264`
- H2 overrides: `33469`
- materialization fingerprint: `5c528cab17e2d48c812f6013fbd4f7d966d8e0ccab5eff4e86de166e92641366`
- prior strict validation: `42` checks, `0` required failures.

## Why an audit after strict validation?

The full-corpus validator proved that the frozen pipeline was executed correctly and reproducibly. This audit asks a different question: does the accepted intervention still look semantically safe when applied at production scale?

The audit is stratified and therefore **must not be interpreted as corpus-wide accuracy estimation**.

## Frozen sample

The sample contains 240 baseline-`method` mentions:

- 100 H2 overrides (`method -> model`),
- 100 preserved non-fallback methods,
- 40 semantic-typer fallback methods.

Selection is deterministic by SHA-256 ranking under frozen seeds. Final annotation order is independently hash-shuffled and does not expose stratum, candidate prediction, score, or H2 decision.

The immutable sample package contains:

- `audit_cases.jsonl` — prediction-blind cases;
- `blank_annotations.jsonl` — blank working schema;
- `reviewer.html` — local offline reviewer;
- `manifest.json`;
- `README.md`;
- `checksums.txt`.

Do **not** search sampled case IDs in the candidate files before reference freeze. The next slice will reconstruct the hidden stratum from the immutable candidate only after the human reference is frozen.

## Annotation labels

For each already extracted span choose:

- entity type: `task`, `method`, `dataset`, `metric`, `model`, `domain`;
- span status: `valid_entity_span`, `boundary_issue`, `not_an_entity`, or temporary `uncertain`;
- confidence: `high`, `medium`, `low`.

For `valid_entity_span` and `boundary_issue`, an entity type is required. For `not_an_entity` and `uncertain`, entity type must be empty. Boundary issues are recorded but are diagnostic-only for this H2 typing promotion cycle because span repair is a separate future hypothesis.

## Frozen promotion-safety gates

These gates are fixed **before annotation starts**:

- overall uncertain rate <= 10%;
- overall `not_an_entity` rate <= 15%;
- override stratum: >=80 usable cases, model-reference rate >=45%, method-reference rate <=30%, and model-minus-method net support >=15 percentage points;
- preserved-method stratum: >=80 usable cases, method-reference rate >=50%, model-reference rate <=30%;
- fallback stratum: >=30 usable cases and (`uncertain` + `not_an_entity`) rate <=25%.

The rates are promotion sanity gates, not new tuning targets. If they fail, the candidate remains a candidate; thresholds or H2 policy must not be changed and re-tested on this audit.

## Workflow

1. Merge this tooling before sample execution.
2. PLAN: no sample output and no candidate predictions exposed.
3. Execute sample once and strict-validate it.
4. Create mutable annotation work from `blank_annotations.jsonl`.
5. Annotate prediction-blind and export frequently.
6. In the next slice, freeze the completed reference **before** unblinding/evaluation.
7. Evaluate the frozen gates and create a separate immutable promotion decision.

At no point in this slice is production `latest` promotion authorized.
