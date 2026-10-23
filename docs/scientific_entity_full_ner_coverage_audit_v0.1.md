# Scientific Entity Full NER Coverage Audit v0.1

## Goal

Measure the complete trusted production extractor over whole canonical `title` and `abstract` fields.

This audit is intentionally separate from the H2 v0.3 semantic-typing audit. H2 v0.3 is a closed trusted production baseline and its historical audit labels must not be reused for tuning.

## Sampling design

- 60 complete `title` fields.
- 60 complete `abstract` fields.
- deterministic uniform hash sampling within each field type;
- selection uses only the exact canonical corpus and a frozen seed;
- production prediction files are not read during sample selection;
- historical heldout/audit canonical IDs are excluded before selection;
- annotators receive no prediction counts, prediction types, strata, or model evidence.

This deliberately favors interpretability of later precision/recall estimates over prediction-density enrichment.

## Outputs

Immutable sample package:

`data/entities/scientific_entity_full_ner_coverage_audit/v0.1/<audit_id>/`

- `README.md`
- `ANNOTATION_GUIDE.md`
- `audit_fields.jsonl`
- `blank_annotations.jsonl`
- `manifest.json`
- `checksums.txt`

Mutable annotation workspace:

`data/entities/scientific_entity_full_ner_coverage_annotation_work/v0.1/<audit_id>/`

- `README.md`
- `ANNOTATION_GUIDE.md`
- `annotations_working.jsonl`

Only `annotations_working.jsonl` should be edited during manual annotation.

## Blindness boundary

The sampler may read the small trusted `latest.json` pointer to bind the audit to the active production baseline, but it must not read the trusted target `final_mentions.jsonl` or any other production prediction file.

The production predictions are joined only after the human reference is frozen in a later slice.
