# Public Metadata Release Policy & Kaggle Packaging v0.1

## Document status

```text
status: implemented local policy and packaging layer
publication action: not performed
canonical truth impact: none
runtime/API/UI impact: none
slice: Public Metadata Dataset Release Policy & Kaggle Packaging v0.1
```

This document defines the source-aware public metadata projection and local
Kaggle-ready package contract for ML Research Radar.

The project goal is a non-commercial educational and portfolio research radar,
with useful versioned metadata datasets for the community. All contributing
sources are attributed. Article PDFs and full text are not redistributed;
users are directed to original publication pages.

---

## 1. Architecture boundary

```text
canonical_documents.jsonl
→ source-aware public metadata policy
→ field-level projection and fail-closed transformations
→ local candidate package
→ output and policy validation
→ explicit human release decision
→ optional future public upload
```

The local public package is a derived artifact. It is never:

- canonical paper truth;
- an input to reconciliation;
- a Postgres serving source;
- a retrieval manifest;
- an automatic Kaggle/Hugging Face/GitHub publication.

---

## 2. Policy contract

Tracked policy:

```text
configs/public_metadata_release_policy_v0.1.yaml
```

Validator:

```text
scripts/validation/check_public_metadata_release_policy.py
```

Smoke tests:

```text
tests/smoke/test_public_metadata_release_policy.py
```

The policy defines:

- project purpose and candidate publication targets;
- source-by-source attribution and terms links;
- allowed and forbidden content classes;
- explicit rules for all selected public dataset fields;
- source-aware abstract handling;
- link-only PDF URL semantics;
- fail-closed handling for unknown text provenance;
- local packaging requirements;
- the separate final compilation-license decision.

---

## 3. Source policies

Current canonical source families:

```text
arxiv
openalex
crossref
semantic_scholar
acl_anthology
```

Project-level attribution is required for all five sources.

### arXiv

- descriptive metadata is accepted for the public metadata projection;
- abstracts may be included under the current metadata-first policy;
- PDF URLs remain links to arXiv;
- PDF binaries and e-print full text are not copied into the package.

### OpenAlex

- selected metadata, identifiers, concepts, counts, and derived summaries may
  support the public projection;
- raw provider payloads are excluded;
- OpenAlex is not used as an independent public-abstract basis in v0.1.

### Crossref

- bibliographic metadata, identifiers, and reference/count metadata may be
  represented;
- Crossref abstracts are not used as an independent public-abstract basis in
  v0.1;
- raw API responses are excluded.

### Semantic Scholar

- canonical identifiers, selected metadata, counts, links, and summaries may be
  represented with attribution;
- raw API responses are not repackaged;
- Semantic Scholar is not used as an independent public-abstract basis in v0.1.

### ACL Anthology

- metadata, identifiers, and original-source links may be represented;
- public abstract output is allowed only for records from 2016 onward;
- pre-2016 ACL-backed abstract text is nulled by the exporter;
- PDF binaries remain excluded.

The machine-readable policy contains the official source and terms URLs used by
this review.

---

## 4. Field-level public projection

Every selected `data.parquet` column must have an explicit field policy.

Important rules:

```text
abstract:
  source-aware include-or-null
  arXiv-backed → include
  ACL-backed and year >= 2016 → include
  otherwise → null

pdf_url:
  include external URL only
  never download or package the PDF binary

provenance_summary:
  compact source-family/count summary only

external_ids_summary:
  compact identifier summary only

unknown selected field:
  exporter/validator failure

unknown text provenance:
  null or exclude
```

The data table retains its current 34-column schema. This slice changes public
release enforcement and package metadata, not canonical field semantics.

---

## 5. Local package layout

The generated local candidate now contains:

```text
data/datasets_release/ml_research_radar_metadata/v0.1/
├── data.parquet
├── schema.json
├── manifest.json
├── README.md
├── DATASET_CARD.md
├── ATTRIBUTION.md
├── field_release_policy.json
├── source_attribution.json
├── kaggle_metadata.template.json
├── data_quality_summary.json
└── checksums.txt
```

### `DATASET_CARD.md`

Documents purpose, source checkpoint, included/excluded content, source-aware
transformations, attribution, known limitations, and publication boundary.

### `ATTRIBUTION.md`

Lists every contributing source family, provider home page, terms/policy URL,
metadata basis, and redistribution exclusions.

### `field_release_policy.json`

A generated release artifact containing the exact policy for every exported
column in deterministic order.

### `source_attribution.json`

Machine-readable provider attribution and source-policy metadata.

### `kaggle_metadata.template.json`

A template only. It intentionally contains an unresolved
`__KAGGLE_OWNER__` placeholder, uses the non-overclaiming `other` license label,
and records `publication_action = not_performed`.

The exporter never calls the Kaggle API and never generates an upload command.

---

## 6. Versioned contract changes

This slice introduces:

```text
dataset_release_config_v2
dataset_release_manifest_v2
dataset_release_output_quality_v2
dataset_release_review_readiness_v2
public_metadata_release_policy_v1
public_metadata_release_policy_quality_v1
```

The `data.parquet` schema remains:

```text
dataset_release_schema_v1
```

because no data columns were added or removed.

---

## 7. Validation sequence

```bat
python -m scripts.validation.check_dataset_release_config --strict --check-paths
python -m scripts.validation.check_public_metadata_release_policy --strict --check-paths
python -m scripts.export.export_public_dataset --force
python -m scripts.validation.check_dataset_release_output --strict
python -m scripts.validation.check_dataset_release_review_readiness --strict
```

Expected state:

```text
config validation = green
public metadata policy validation = green
local package generation = green
output validation = green
technical_candidate_ready = true
public_policy_ready = true
manual_release_decision_required = true
publication_ready = false
publication_block_reason = public_release_decision_not_completed
```

---

## 8. Publication boundary

This slice does not:

- choose the final public compilation license;
- replace the Kaggle owner placeholder;
- create a Kaggle dataset;
- upload a new Kaggle version;
- publish to Hugging Face Datasets;
- create a GitHub Release;
- publish graph packages;
- include embeddings, full text, or PDF binaries;
- change canonical truth, reconciliation, retrieval, Qdrant, Postgres, API, UI,
  or ranking.

The next release-action slice must be explicit and human-owned.


## 9. Manual-review evidence layer

The policy/package layer is now followed by a separate 20-category manual-review
checklist and deterministic evidence-preparation validator:

```text
configs/public_metadata_release_review.yaml
configs/public_metadata_release_review_evidence.yaml
scripts/validation/check_public_metadata_release_review.py
scripts/validation/check_public_metadata_release_review_evidence.py
```

The evidence layer confirms that policy, attribution, package integrity,
field-level decisions, source-specific rules, and human-decision materials are
available. It keeps all category statuses pending and does not change the policy
status, final compilation-license state, Kaggle owner placeholder, or publication
status.
