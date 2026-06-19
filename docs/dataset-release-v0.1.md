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
        └── checksums.txt
```

The current contract slice does not have to create this directory.

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
