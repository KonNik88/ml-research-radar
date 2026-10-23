# Full NER Coverage v0.1 — Completed Annotation Validation & Freeze (9B)

This slice binds **completed prediction-blind human labels** to the *immutable* 9A field sample and creates a one-time immutable reference. It does **not** run full-corpus inference, evaluate predictions, tune policies, or change production/canonical artifacts.

## Frozen inputs

- Parent 9A config, immutable sample manifest + `audit_fields.jsonl`, 9A strict checker.
- Human-completed `annotations_working.jsonl` (or explicit `--annotations-path`).
- Exact reviewed file SHA: `95e231b4187de26fa57d9c71b3ec74c4d5303ce3c22c5a96560059c948235c75`.
- 120 complete fields, 972 spans, 68 uncertain, 5 overlapping mention pairs.

**Important:** The uploaded completed file and the local file used for freeze must be byte-identical. If the PLAN fails its SHA check, do not execute: locate the correct reviewed completed file or investigate byte drift. Do not hand-edit JSONL just to satisfy a checksum.

## Parent integrity and safety

PLAN uses the parent 9A strict validator, checks each completed row against `audit_fields.jsonl` **in original order**, requires exactly identical `source_text`, SHA, identifiers, and schema; checks completed rows, span bounds/substring via Pydantic, duplicates and explanation for every `uncertain=true`. No production predictions are read.

The uncertain labels are deliberately preserved as **unresolved**. Before unblind, a separate scoring contract must define masking/handling of uncertain references and matching in the presence of overlaps. Do not simply count uncertain spans as unquestionable gold or treat all overlapping model predictions as false positives.

## Workflow

1. Branch, unpack this tooling slice, run 9B smoke + PLAN (no changes).
2. Commit/merge tooling via PR, switch to `main`, rerun smoke + PLAN.
3. Run **one** `--execute` (writes immutable timestamp-independent reference ID, not latest).
4. Run `python -m scripts.validation.check_scientific_entity_full_ner_coverage_reference --strict`.
5. If strict PASS, continue with pre-registered evaluation policy and **sample-scoped unblind using existing trusted `final_mentions.jsonl`**. No 18–20-hour full-corpus model inference needed.

`--annotations-path` may select another completed file under the repo, but the approved SHA remains mandatory.

## Output

`data/entities/scientific_entity_full_ner_coverage_reference/v0.1/scientific-entity-full-ner-coverage-reference-v0.1-3cc6e3c779fee351/`:

- `annotations.jsonl` — **exact original source bytes**, no normalization/rewrites;
- `summary.json` — counts, type breakdown, 68 preserved uncertainties and overlap diagnostics;
- `manifest.json` — sample/target lineage, source SHA and explicit no-unblind flags;
- `checksums.txt`, `README.md`.

Tooling never changes `latest.json`, the candidate, canonical, or old reference labels. Immutable destination must not exist before execute. Do not commit mutable annotation work or large data artifacts unless repository policy explicitly permits that data family.
