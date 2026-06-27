# Dataset Release v0.1

## Document status

```text
status: active local candidate release track / not published
slice: Dataset Release Track Checkpoint v0.1
release family: clean_research_metadata
public upload: not performed
canonical truth impact: none
runtime behavior change: none
```

This document defines the current dataset-release track for **ML Research Radar**.

The track is no longer only a contract proposal. It now covers the complete local
candidate pipeline:

```text
contract
→ config validation
→ local export runner
→ output validation
→ data-quality summary
→ review-readiness gate
```

The dataset release remains a derived artifact. It is not canonical truth, not a
serving state, not a retrieval manifest, and not a source for reconciliation.

---

## 1. Release identity

Current local candidate:

```text
dataset_name = ml_research_radar_metadata
version = v0.1
release_family = clean_research_metadata
status = candidate_local_export / not_published
```

Candidate publication targets remain preliminary only:

```text
huggingface_datasets
kaggle
```

No public target is selected as final until license/provenance review is complete.

---

## 2. Source checkpoint

The v0.1 track is tied to the accepted ML Research Radar corpus checkpoint:

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

The dataset release is derived from this checkpoint and must never become a
silent input into reconciliation.

---

## 3. Scope

Included in the v0.1 metadata release candidate:

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
need a separate artifact-size, licensing, model-card, regeneration, and review
policy.

---

## 4. Config contract

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

Required safety boundaries:

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

---

## 5. Expected local release layout

The local candidate release directory is:

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

`data_quality_summary.json` is part of the required layout. It records review
signals such as row/column counts, canonical ID uniqueness, field coverage,
year range, source-family distribution, publication-type distribution, language
distribution, and source-count distributions.

Generated release directories are local candidate artifacts. They are not
committed by default and are not public releases.

---

## 6. Implemented dataset-release stages

### 6.1 Dataset Export Contract v0.1

Status: **done / green when config validation passes**

Defines the metadata-only release boundary, allowed/forbidden columns, source
checkpoint, output layout, license-review policy, and safety flags.

Validator:

```bat
python -m scripts.validation.check_dataset_release_config --strict
python -m scripts.validation.check_dataset_release_config --strict --check-paths
```

Expected reports:

```text
artifacts/reports/validation/dataset_release_config_latest.json
artifacts/reports/validation/dataset_release_config_latest.md
artifacts/reports/validation/history/dataset_release_config_<timestamp>.json
artifacts/reports/validation/history/dataset_release_config_<timestamp>.md
```

### 6.2 Dataset Export Runner v0.1

Status: **implemented local candidate generation**

Runner:

```bat
python -m scripts.export.export_public_dataset
```

Explicit config command:

```bat
python -m scripts.export.export_public_dataset --config-path configs/dataset_release.yaml
```

If the configured release directory already exists and is non-empty, the runner
fails by default. Rewriting a local candidate requires explicit intent:

```bat
python -m scripts.export.export_public_dataset --force
```

The runner must not export embeddings, full text, PDF binaries, raw provider
payloads, private notes, or full source records.

### 6.3 Dataset Release Output Validation v0.1

Status: **implemented**

Validator:

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
- `data_quality_summary.json` is readable and consistent with `data.parquet`;
- checksums match generated files.

### 6.4 Dataset Release Output Hardening v0.1

Status: **implemented**

Adds:

```text
data_quality_summary.json
```

This file supports local inspection and future manual release review. It is not
a publication decision and not canonical truth.

### 6.5 Dataset Release Review Readiness v0.1

Status: **implemented**

Validator:

```bat
python -m scripts.validation.check_dataset_release_review_readiness --strict
```

A green review-readiness report means:

```text
technical_candidate_ready = true
manual_review_required = true
publication_ready = false
publication_block_reason = manual_review_not_completed
```

This is intentional. The gate confirms that the generated local candidate is
technically ready for manual license/provenance review. It does not approve
public publication.

---

## 7. Recommended validation sequence

Use this sequence when checking the dataset-release track locally:

```bat
python -m scripts.validation.check_dataset_release_config --strict --check-paths
python -m scripts.export.export_public_dataset --force
python -m scripts.validation.check_dataset_release_output --strict
python -m scripts.validation.check_dataset_release_review_readiness --strict
```

Expected final state:

```text
config validation ok
local candidate export generated
output validation ok
technical_candidate_ready = true
manual_review_required = true
publication_ready = false
publication_block_reason = manual_review_not_completed
required_failed_count = 0
```

---

## 8. Public publication boundary

The current track does **not** perform:

```text
public upload
license approval
provenance approval
Kaggle publication
Hugging Face publication
GitHub Release publication
```

Any real public publication requires a separate release-decision slice after
manual review.

---

## 9. Acceptance criteria for the checkpoint

Dataset Release Track Checkpoint v0.1 is accepted when:

- [ ] `configs/dataset_release.yaml` validates in strict mode;
- [ ] `data_quality_summary.json` is included in the configured expected layout;
- [ ] the local candidate export can be generated explicitly;
- [ ] output validation returns `required_failed_count = 0`;
- [ ] review-readiness validation returns `technical_candidate_ready = true`;
- [ ] review-readiness validation returns `publication_ready = false`;
- [ ] generated dataset files are not committed;
- [ ] generated validation report history is not committed;
- [ ] no public upload is performed;
- [ ] no operational source/retrieval/runtime files are modified.

---

## 10. Future work

Valid future slices:

```text
Manual License and Provenance Review v0.1
Public Dataset Release Decision v0.1
Hugging Face Dataset Card v0.1
Kaggle Dataset Packaging v0.1
Paper–Artifact Links Dataset v0.1
Topic/Discovery Dataset v0.1
Research Graph Export Contract v0.1
Retrieval Evaluation Dataset v0.1
```

Out of scope for the current checkpoint:

```text
public upload
full-text release
embedding release
graph export
retrieval-pair dataset
RAG/full-text chunk release
automatic publication
```
