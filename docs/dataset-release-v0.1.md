# Dataset Release v0.1

## Document status

```text
status: proposed contract / not published
slice: Dataset Export Contract v0.1
release family: clean_research_metadata
public upload: not performed
canonical truth impact: none
runtime behavior change: none
```

This document defines the first dataset-release contract for **ML Research
Radar**.

The goal is not to publish immediately. The goal is to make any future
publication reproducible, bounded, validated, and safe.

---

## 1. Release identity

Planned candidate:

```text
dataset_name = ml_research_radar_metadata
version = v0.1
release_family = clean_research_metadata
status = candidate_contract
```

Candidate publication targets:

```text
huggingface_datasets
kaggle
```

No target is selected as final until license/provenance review is complete.

---

## 2. Source checkpoint

The v0.1 contract is tied to the accepted ML Research Radar corpus checkpoint:

```text
canonical_doc_count = 60954
retrieval_build_id = 20260504T164021Z
retrieval_corpus_doc_count = 60954
embedding_model = sentence-transformers/all-MiniLM-L6-v2
```

Operational truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

The dataset release is derived from that checkpoint and must never become a
silent input into reconciliation.

---

## 3. Scope

Included in the first candidate contract:

```text
canonical paper identifiers
bibliographic metadata
abstracts when available
authors
year
categories/concepts
venue/publication metadata
external identifiers
source count summaries
provenance/source-family summaries
metadata completeness signals
```

Excluded from v0.1:

```text
raw provider payloads
raw source snapshots
full text
PDF binaries
embedding vectors
private notes
unreviewed provider-restricted fields
```

Embeddings are intentionally excluded in v0.1. A future embedding release would
need a separate artifact-size, licensing, model-card, and regeneration policy.

---

## 4. Config file

The release contract is defined in:

```text
configs/dataset_release.yaml
```

The config must include:

- schema version;
- release name/version/family/status;
- source checkpoint;
- export options;
- required/optional/forbidden columns;
- validation requirements;
- license-review policy;
- safety flags;
- expected output layout.

---

## 5. Safety policy

The v0.1 contract must enforce:

```text
canonical_truth_impact = none
may_overwrite_operational_latest = false
may_be_used_as_reconcile_input = false
include_full_text = false
include_pdfs = false
include_embeddings = false
include_raw_provider_payloads = false
publish_without_manual_review = false
```

These are required safety boundaries.

---

## 6. Expected release layout

Future release candidate directory:

```text
data/datasets_release/
└── ml_research_radar_metadata/
    └── v0.1/
        ├── data.parquet
        ├── schema.json
        ├── manifest.json
        ├── README.md
        ├── data_quality_summary.json
        └── checksums.txt
```

The current export-runner slice creates this directory as a local candidate artifact only.
It does not publish the dataset and does not change operational truth.

---

## 7. Validation

The config validator is:

```text
scripts/validation/check_dataset_release_config.py
```

Default command:

```bat
python -m scripts.validation.check_dataset_release_config
```

Strict command:

```bat
python -m scripts.validation.check_dataset_release_config --strict
```

Optional path-aware command:

```bat
python -m scripts.validation.check_dataset_release_config --check-paths
```

Expected report outputs:

```text
artifacts/reports/validation/dataset_release_config_latest.json
artifacts/reports/validation/dataset_release_config_latest.md
artifacts/reports/validation/history/dataset_release_config_<timestamp>.json
artifacts/reports/validation/history/dataset_release_config_<timestamp>.md
```

Generated reports should not be committed unless a separate artifact-retention
policy explicitly says otherwise.

---

## 8. Acceptance criteria

Dataset Export Contract v0.1 is accepted when:

- [ ] `configs/dataset_release.yaml` exists and validates;
- [ ] `docs/dataset_strategy.md` is synchronized with the active v0.1 contract;
- [ ] this document exists;
- [ ] validator smoke tests pass;
- [ ] full config validation returns `required_failed_count = 0`;
- [ ] no export data files are created;
- [ ] no public upload is performed;
- [ ] no operational source/retrieval files are modified.

Suggested smoke test:

```bat
python -m pytest tests\smoke\test_dataset_release_config.py -q
```

Suggested validation:

```bat
python -m scripts.validation.check_dataset_release_config --strict
```

---

## 9. Future work after this contract

Valid follow-up slices:

```text
Dataset Export Runner v0.1
Dataset Output Validator v0.1
Dataset Card / README Generator v0.1
Dataset Release Output Hardening v0.1
License and Provenance Review v0.1
Candidate Release Dry Run v0.1
Public Release Decision v0.1
```

Out of scope for this contract:

```text
public upload
full export pipeline
graph export
retrieval evaluation dataset
embeddings release
RAG/full-text chunk release
```

---

## 10. Operational interpretation

This slice creates the safety rails before public release work.

Accepted interpretation:

```text
The project is ready to define a dataset-release contract.
The project is not yet publishing a dataset.
The first public candidate should be metadata-only.
Every future release must be tied to an accepted checkpoint and validated.
```

---

## 11. Dataset Export Runner v0.1

Dataset Export Runner v0.1 turns the accepted metadata-only contract into a
local candidate release directory. It does not publish the dataset and does not
change operational truth.

Runner command:

```bat
python -m scripts.export.export_public_dataset
```

Explicit config command:

```bat
python -m scripts.export.export_public_dataset --config-path configs/dataset_release.yaml
```

If the configured release directory already exists and is non-empty, the runner
fails by default. Rewriting a generated candidate requires an explicit flag:

```bat
python -m scripts.export.export_public_dataset --force
```

Expected local candidate output:

```text
data/datasets_release/ml_research_radar_metadata/v0.1/
├── data.parquet
├── schema.json
├── manifest.json
├── README.md
└── checksums.txt
```

Generated candidate releases remain derived artifacts:

```text
canonical_truth_impact = none
may_overwrite_operational_latest = false
may_be_used_as_reconcile_input = false
publication_status = not_published
manual_review_required_before_publication = true
```

The runner must not export embeddings, full text, PDF binaries, raw provider
payloads, private notes, or full source records.

---

## 12. Dataset release output validation

Generated candidate output is validated separately from the config contract.

Validator command:

```bat
python -m scripts.validation.check_dataset_release_output --strict
```

The output validator checks:

- required release files exist;
- `data.parquet` is readable;
- schema and manifest files are readable;
- columns match the configured required + optional export schema;
- forbidden columns are absent;
- `canonical_id` is unique;
- titles are non-empty;
- row order is deterministic;
- manifest row count matches the data file;
- safety and non-publication flags are preserved;
- checksums match generated files.

Suggested Dataset Export Runner v0.1 checks:

```bat
python -m pytest tests\smoke\test_dataset_release_config.py tests\smoke\test_public_dataset_export_contract.py tests\smoke\test_dataset_release_output_validator.py -q
python -m scripts.validation.check_dataset_release_config --strict --check-paths
python -m scripts.export.export_public_dataset
python -m scripts.validation.check_dataset_release_output --strict
```

The release directory is still a local candidate after these commands. Public
upload requires a separate manual license/provenance review and a separate
release decision.


## 10. Dataset Release Output Hardening v0.1

The follow-up hardening slice extends the local candidate release with a machine-readable data-quality summary:

```text
data_quality_summary.json
```

The summary is generated from `data.parquet` export rows and records non-publication review signals such as:

- row and column counts;
- canonical ID uniqueness and duplicate counts;
- field coverage counts and ratios;
- year range;
- metadata completeness score summary;
- source-family distribution;
- publication-type, language, and primary-category counts;
- source-count and unique-source-count distributions.

This file is intended to support local inspection and future manual release review. It is still a derived local candidate artifact, not a publication decision and not canonical truth.

The output validator must check that `data_quality_summary.json` exists, is readable, is listed in `manifest.json`, is covered by `checksums.txt`, and agrees with `data.parquet` on core counts and canonical ID statistics.

---

## 12. Dataset Release Review Readiness v0.1

After the local candidate export and output validation slices, the next safety gate is a review-readiness check.

The review-readiness validator is:

```text
scripts/validation/check_dataset_release_review_readiness.py
```

Default command:

```bat
python -m scripts.validation.check_dataset_release_review_readiness --strict
```

The gate reads the generated local candidate release plus the latest output-validation report and verifies that the candidate is technically ready for manual review.

Inputs:

```text
configs/dataset_release.yaml
data/datasets_release/ml_research_radar_metadata/v0.1/manifest.json
data/datasets_release/ml_research_radar_metadata/v0.1/schema.json
data/datasets_release/ml_research_radar_metadata/v0.1/README.md
data/datasets_release/ml_research_radar_metadata/v0.1/data_quality_summary.json
artifacts/reports/validation/dataset_release_output_latest.json
```

Expected report outputs:

```text
artifacts/reports/validation/dataset_release_review_readiness_latest.json
artifacts/reports/validation/dataset_release_review_readiness_latest.md
artifacts/reports/validation/history/dataset_release_review_readiness_<timestamp>.json
artifacts/reports/validation/history/dataset_release_review_readiness_<timestamp>.md
```

A green review-readiness report means:

```text
technical_candidate_ready = true
manual_review_required = true
publication_ready = false
publication_block_reason = manual_review_not_completed
```

This is intentional. The review-readiness gate does not approve public publication. It only confirms that the generated local candidate artifact is technically ready for human license/provenance review.

The gate checks, among other things:

- the generated release directory exists;
- review-critical files are present;
- `manifest.json`, `schema.json`, and `data_quality_summary.json` are readable;
- `README.md` states the non-publication/manual-review boundary;
- `manifest.json` states `publication_status = not_published`;
- `manifest.json` states `manual_review_required_before_publication = true`;
- `license_review.publication_allowed_before_review = false`;
- `safety.publish_without_manual_review = false`;
- `safety.canonical_truth_impact = none`;
- `data_quality_summary.json` contains core review metrics;
- duplicate canonical ID count is zero;
- expected row count matches the accepted checkpoint;
- the latest dataset output-validation report is green and points to the same release directory.

The review-readiness gate still does not perform:

```text
public upload
license approval
provenance approval
Kaggle publication
Hugging Face publication
GitHub Release publication
```

Any real public publication requires a separate release decision after manual review.
