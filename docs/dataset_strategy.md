# Dataset Release Strategy

## Document status

```text
status: future track / placeholder contract
current implementation priority: not active
canonical truth impact: none
```

This document defines the boundary for future public dataset releases from ML Research Radar.

A dataset release is a **derived public artifact**. It is not:

- canonical paper truth;
- a Postgres serving state;
- a retrieval-generation manifest;
- a replacement for source snapshots;
- an input that may silently overwrite operational `latest` artifacts.

---

## 1. Source-of-truth boundary

Operational paper truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

Future dataset releases are generated from an explicit accepted checkpoint and must record:

- canonical corpus fingerprint;
- canonical document count;
- retrieval build ID when retrieval-derived data is included;
- feature/cluster/graph build IDs where applicable;
- export configuration;
- creation timestamp;
- schema version;
- license and provenance notes.

A published release must never become an implicit upstream source for canonical reconciliation.

---

## 2. Potential release families

### 2.1 Clean research metadata

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

### 2.2 Paper–artifact links

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

### 2.3 Topic and discovery artifacts

Possible content:

- cluster assignments;
- heuristic labels;
- representative papers;
- projection coordinates;
- transparent paper-feature scores.

These releases are build-scoped and must include their retrieval/cluster/projection identifiers.

### 2.4 Research graph exports

Possible future edge families:

- paper → paper reference;
- paper → artifact;
- paper → source observation;
- paper → topic/cluster.

Graph exports require a dedicated entity/edge contract before publication.

### 2.5 Temporal and trend datasets

Possible content:

- publication counts over time;
- topic frequencies;
- artifact adoption;
- venue/source trends.

Aggregations must remain reproducible from a named accepted checkpoint.

### 2.6 Retrieval evaluation datasets

Possible content:

- query–positive pairs;
- query–candidate judgments;
- hard negatives;
- paper similarity pairs;
- benchmark splits.

Human labels, weak labels, and generated labels must be distinguished explicitly.

---

## 3. Release lifecycle

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

Operational `latest` aliases should not replace immutable release versions.

---

## 4. Validation expectations

A release validator should eventually check:

- schema version;
- required columns;
- unique IDs;
- row counts;
- null/coverage statistics;
- duplicate rows;
- foreign-key consistency;
- build/fingerprint consistency;
- license/provenance metadata;
- checksums;
- deterministic regeneration where applicable.

---

## 5. Candidate publication targets

Potential targets:

- GitHub Releases;
- Hugging Face Datasets;
- Kaggle.

The target is selected per dataset after checking file-size, licensing, update, and versioning constraints.

---

## 6. Current non-goals

Not part of Current-State and Evidence Sync v1:

- implementing dataset export code;
- publishing a dataset;
- selecting a public license for provider-derived metadata;
- generating graph exports;
- generating retrieval pairs;
- scheduling releases;
- integrating releases into Airflow;
- treating a release as operational truth.

The concrete dataset track should begin only after one release family is selected with an explicit schema, audience, license review, and Definition of Done.
