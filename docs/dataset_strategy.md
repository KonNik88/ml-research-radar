# Dataset Release Strategy

## Document status

```text
status: active local candidate release track / no publication yet
current checkpoint: Dataset Release Track Checkpoint v0.1
current local pipeline: implemented
canonical truth impact: none
public dataset publication: not performed
```

This document defines the strategic boundary for future public dataset releases
from **ML Research Radar**.

A dataset release is a **derived public artifact candidate**. It is not:

- canonical paper truth;
- a Postgres serving state;
- a retrieval-generation manifest;
- a replacement for source snapshots;
- an input that may silently overwrite operational `latest` artifacts.

The current dataset work supports a local candidate-release pipeline only:

```text
accepted operational checkpoint
→ explicit export config
→ local candidate release directory
→ schema/output validation
→ data-quality summary
→ technical review-readiness gate
→ manual license/provenance review
→ separate explicit release decision
```

The current track stops before public publication.

---

## 1. Source-of-truth boundary

Operational paper truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

Dataset releases are generated from an explicit accepted checkpoint and must
record:

- canonical document count;
- retrieval build ID when retrieval-derived metadata is referenced;
- embedding model identity when relevant;
- export configuration;
- creation timestamp;
- schema version;
- license and provenance notes;
- non-publication/manual-review status until approved.

A published release must never become an implicit upstream source for canonical
reconciliation.

Current accepted source checkpoint for the v0.1 metadata candidate:

```text
canonical_doc_count = 60954
retrieval_build_id = 20260504T164021Z
retrieval_corpus_doc_count = 60954
embedding_model = sentence-transformers/all-MiniLM-L6-v2
release_family = clean_research_metadata
publication_status = not_published
```

---

## 2. Current candidate: metadata-only v0.1

The first candidate release family is:

```text
clean_research_metadata
```

Purpose:

```text
A reproducible metadata-only public dataset candidate derived from an accepted
canonical corpus checkpoint.
```

Potential audience:

- ML/retrieval/RAG practitioners;
- research-discovery and bibliographic-mining projects;
- portfolio reviewers who need a reproducible corpus artifact;
- future Hugging Face Datasets / Kaggle notebooks.

Current non-publication stance:

```text
The project may generate and validate a local candidate now.
Actual public upload requires a separate release decision and license review.
```

---

## 3. Current local pipeline

The v0.1 track currently consists of:

```text
configs/dataset_release.yaml
scripts/validation/check_dataset_release_config.py
scripts/export/export_public_dataset.py
scripts/validation/check_dataset_release_output.py
scripts/validation/check_dataset_release_review_readiness.py
```

Expected local candidate layout:

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

Correct technical end state before manual review:

```text
technical_candidate_ready = true
manual_review_required = true
publication_ready = false
publication_block_reason = manual_review_not_completed
```

---

## 4. Release families

### 4.1 Clean research metadata

Possible content:

- canonical ID;
- title;
- abstract;
- authors;
- year/date;
- categories and concepts;
- venue/publication metadata;
- external identifiers;
- source-count and provenance summaries.

Current status:

```text
selected for v0.1 local candidate release track
```

### 4.2 Paper–artifact links

Possible content:

- canonical paper ID;
- artifact ID;
- provider;
- artifact type;
- normalized URL;
- relation type;
- evidence/confidence metadata;
- selected public provider fields.

Provider terms and live metadata redistribution rules must be checked explicitly.

Current status:

```text
deferred
```

### 4.3 Topic and discovery artifacts

Possible content:

- cluster assignments;
- heuristic labels;
- representative papers;
- projection coordinates;
- transparent paper-feature scores.

These releases are build-scoped and must include retrieval, cluster, and
projection identifiers.

Current status:

```text
deferred
```

### 4.4 Research graph exports

Possible future edge families:

- paper -> paper reference;
- paper -> artifact;
- paper -> source observation;
- paper -> topic/cluster.

Graph exports require a dedicated entity/edge contract before publication.

Current status:

```text
deferred
```

### 4.5 Temporal and trend datasets

Possible content:

- publication counts over time;
- topic frequencies;
- artifact adoption;
- venue/source trends.

Aggregations must remain reproducible from a named accepted checkpoint.

Current status:

```text
deferred
```

### 4.6 Retrieval evaluation datasets

Possible content:

- query-positive pairs;
- query-candidate judgments;
- hard negatives;
- paper similarity pairs;
- benchmark splits.

Human labels, weak labels, and generated labels must be distinguished explicitly.

Current status:

```text
deferred
```

---

## 5. Dataset config contract

The active config is:

```text
configs/dataset_release.yaml
```

The config defines:

```text
schema_version
release metadata
source checkpoint
export options
required / optional / forbidden columns
validation requirements
license-review requirements
safety policy
expected output layout
```

The v0.1 metadata track intentionally sets:

```text
include_embeddings = false
include_full_text = false
include_pdfs = false
include_raw_provider_payloads = false
publish_without_manual_review = false
may_be_used_as_reconcile_input = false
may_overwrite_operational_latest = false
```

The expected output layout must include:

```text
data.parquet
schema.json
manifest.json
README.md
data_quality_summary.json
checksums.txt
```

---

## 6. Validation expectations

Config validation:

```bat
python -m scripts.validation.check_dataset_release_config --strict --check-paths
```

Local candidate export:

```bat
python -m scripts.export.export_public_dataset --force
```

Output validation:

```bat
python -m scripts.validation.check_dataset_release_output --strict
```

Review-readiness validation:

```bat
python -m scripts.validation.check_dataset_release_review_readiness --strict
```

A generated candidate may be considered locally reproducible only when config
validation and output validation are green. It may be considered for publication
only after a separate manual license/provenance review and release decision.

---

## 7. Candidate publication targets

Potential targets:

- GitHub Releases;
- Hugging Face Datasets;
- Kaggle.

Preliminary preference for the first public metadata release:

```text
Hugging Face Datasets
→ best fit for ML/retrieval/RAG audience and versioned dataset cards

Kaggle
→ useful for portfolio visibility and notebooks
```

The target is selected per dataset after checking file-size, licensing, update,
and versioning constraints.

---

## 8. Current non-goals

Not part of Dataset Release Track Checkpoint v0.1:

- public upload;
- final license approval;
- provenance approval;
- graph export;
- paper-code links dataset;
- topic cluster dataset;
- temporal trends dataset;
- retrieval pairs dataset;
- Airflow scheduling for releases;
- dataset API endpoint;
- Streamlit dataset page;
- automatic publication;
- treating a release as operational truth.

---

## 9. Operational interpretation

The dataset track is now a safe local metadata-release candidate pipeline.

Current accepted interpretation:

```text
We can generate and validate a local release candidate.
We should not publish yet.
We should not export everything by default.
We should not let the release become an input source.
Manual review remains required before any public release.
```

The first public release, if approved later, must be an explicit separate slice.
