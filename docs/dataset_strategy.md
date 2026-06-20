# Dataset Release Strategy

## Document status

```text
status: active contract track / no publication yet
current implementation priority: Dataset Export Contract v0.1
canonical truth impact: none
public dataset publication: not performed
```

This document defines the boundary for future public dataset releases from
**ML Research Radar**.

A dataset release is a **derived public artifact**. It is not:

- canonical paper truth;
- a Postgres serving state;
- a retrieval-generation manifest;
- a replacement for source snapshots;
- an input that may silently overwrite operational `latest` artifacts.

The current active dataset work is intentionally narrow:

```text
define release config
define metadata-only schema boundary
define validation contract
do not export yet
do not publish yet
```

---

## 1. Source-of-truth boundary

Operational paper truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

Future dataset releases are generated from an explicit accepted checkpoint and
must record:

- canonical corpus fingerprint when available;
- canonical document count;
- retrieval build ID when retrieval-derived data is included;
- feature, cluster, or graph build IDs where applicable;
- export configuration;
- creation timestamp;
- schema version;
- license and provenance notes.

A published release must never become an implicit upstream source for canonical
reconciliation.

Current accepted source checkpoint for the first candidate contract:

```text
canonical_doc_count = 60954
retrieval_build_id = 20260504T164021Z
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
The project may define and validate the release contract now.
Actual public upload requires a separate release decision and license review.
```

---

## 3. Potential release families

### 3.1 Clean research metadata

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

Sensitive or provider-restricted fields must be reviewed before release.

Current status:

```text
selected for v0.1 contract
```

### 3.2 Paper–artifact links

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

### 3.3 Topic and discovery artifacts

Possible content:

- cluster assignments;
- heuristic labels;
- representative papers;
- projection coordinates;
- transparent paper-feature scores.

These releases are build-scoped and must include their retrieval, cluster, and
projection identifiers.

Current status:

```text
deferred
```

### 3.4 Research graph exports

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

### 3.5 Temporal and trend datasets

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

### 3.6 Retrieval evaluation datasets

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

## 4. Release lifecycle

Required future lifecycle:

```text
accepted operational checkpoint
→ explicit export config
→ candidate release directory
→ schema and row-count validation
→ provenance/license review
→ reproducibility manifest
→ sample inspection
→ explicit release decision
→ immutable versioned publication
```

Recommended layout:

```text
data/datasets_release/
└── <dataset_name>/
    └── <version>/
        ├── data.*
        ├── schema.json
        ├── manifest.json
        ├── README.md
        └── checksums.txt
```

Operational `latest` aliases must not replace immutable release versions.

---

## 5. Dataset config contract

The first active config is:

```text
configs/dataset_release.yaml
```

The config must define:

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

The first contract intentionally sets:

```text
include_embeddings = false
include_full_text = false
include_pdfs = false
include_raw_provider_payloads = false
publish_without_manual_review = false
may_be_used_as_reconcile_input = false
may_overwrite_operational_latest = false
```

This prevents accidental over-release or accidental use of a public release as an
operational source.

---

## 6. Validation expectations

The release config validator should check:

- schema version;
- release name/version/family;
- source checkpoint fields;
- expected row count;
- retrieval build identity when present;
- export format and output layout;
- required columns;
- forbidden columns;
- license review status;
- safety flags;
- no publication without manual review;
- no full text/PDF/raw payload/embedding release in metadata-only v0.1;
- deterministic output-order policy.

Future release-output validators should also check:

- actual output schema;
- unique IDs;
- row counts;
- null/coverage statistics;
- duplicate rows;
- foreign-key consistency;
- build/fingerprint consistency;
- checksums;
- deterministic regeneration where applicable.

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

Not part of Dataset Export Contract v0.1:

- implementing the full dataset export pipeline;
- publishing a dataset;
- selecting a final public license;
- generating graph exports;
- generating retrieval pairs;
- scheduling releases;
- integrating releases into Airflow;
- treating a release as operational truth;
- exporting full text, PDFs, embeddings, or raw provider payloads.

---

## 9. Definition of Done for Dataset Export Contract v0.1

Complete when:

- [ ] `configs/dataset_release.yaml` defines the v0.1 metadata-only contract;
- [ ] `docs/dataset-release-v0.1.md` explains the release boundary and DoD;
- [ ] `docs/dataset_strategy.md` is synchronized with the active contract;
- [ ] `scripts/validation/check_dataset_release_config.py` validates the config;
- [ ] smoke tests cover accepted and rejected config cases;
- [ ] no export files are generated;
- [ ] no public dataset is published;
- [ ] no operational `latest` files are modified.

---

## 10. Operational interpretation

The dataset track should begin with a contract because dataset release is a
public-facing boundary.

Current accepted interpretation:

```text
We can prepare the release contract now.
We should not publish yet.
We should not export everything by default.
We should not let the release become an input source.
```

The first dataset slice is therefore a safety and reproducibility layer, not a
new data-ingestion or product-feature layer.

---

## 11. Dataset Export Runner v0.1

After the Dataset Export Contract v0.1 slice, the next bounded implementation
slice is a local metadata export runner.

Scope:

```text
scripts/export/export_public_dataset.py
scripts/validation/check_dataset_release_output.py
tests/smoke/test_public_dataset_export_contract.py
tests/smoke/test_dataset_release_output_validator.py
```

The runner creates a local candidate release directory from
`configs/dataset_release.yaml` and the accepted canonical corpus checkpoint:

```text
data/datasets_release/ml_research_radar_metadata/v0.1/
├── data.parquet
├── schema.json
├── manifest.json
├── README.md
└── checksums.txt
```

This slice is still not a publication slice.

Non-goals remain:

- public upload to Kaggle, Hugging Face Datasets, or GitHub Releases;
- embedding export;
- full-text or PDF export;
- raw provider payload export;
- full source-record export;
- graph export;
- RAG or GraphRAG;
- retrieval rebuild;
- Qdrant promotion;
- search or ranking behavior changes;
- mutation of canonical latest or operational serving state.

The output validator is intentionally separate from the config validator:

```text
check_dataset_release_config.py  -> validates the release contract
check_dataset_release_output.py  -> validates the generated local candidate artifact
```

A generated candidate may be considered locally reproducible only when both the
config validator and the output validator are green. It may be considered for
publication only after a separate manual license/provenance review.
