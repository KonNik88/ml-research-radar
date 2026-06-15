# ACL Anthology Integration v1

## Current status amendment

The candidate-only integration described in this document was completed and
subsequently promoted through the canonical reconcile and explicit promotion
lifecycle.

Current accepted checkpoint:

```text
ACL-family canonical documents = 957
ACL-only canonical documents = 954
existing canonical papers enriched with ACL provenance = 3
```

The remainder of this document preserves the original candidate-slice design,
constraints and historical scope.

## Purpose

This document defines the first candidate-only integration slice for ACL Anthology in ML Research Radar.

ACL Anthology is a paper/domain source for NLP and computational linguistics metadata. It belongs to the paper plane, not the artifact plane.

The goal of v1 is not to promote ACL Anthology into the stable canonical corpus immediately. The goal is to produce a small, deterministic, auditable `NormalizedDocument` snapshot and evaluate its quality before any reconcile/promotion decision.

---

## Historical v1 status

Status at the time of this slice: candidate ingestion v1.

Scope at the time of this slice: candidate-only.

Stable canonical promotion was intentionally not allowed inside v1 itself.
Promotion was performed later through a separate audited promotion step, as
recorded in the current status amendment above.

---

## Source role

ACL Anthology may contribute:

- ACL Anthology paper id
- title
- authors
- year
- venue / booktitle
- DOI where available
- landing page URL
- PDF URL
- abstract where available
- pages / bibkey as provenance comments

ACL Anthology must not bypass the canonical reconcile process.

---

## Source of metadata

ACL Anthology stores authoritative XML metadata in the official `acl-org/acl-anthology` GitHub repository under `data/xml`.

The v1 ingestor fetches XML files from:

```text
https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/<xml_id>.xml
```

Default smoke XML id:

```text
2024.acl
```

This corresponds to:

```text
https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/2024.acl.xml
```

---

## Outputs

Raw XML snapshots:

```text
data/raw/acl_anthology/<run_ts>/<xml_id>.xml
```

Normalized candidate snapshot:

```text
data/normalized/acl_anthology/documents.<run_ts>.jsonl
data/normalized/acl_anthology/documents_latest.jsonl
```

Reports:

```text
artifacts/reports/source_audit/acl_anthology_ingest_latest.json
artifacts/reports/source_audit/acl_anthology_ingest_latest.md
artifacts/reports/source_audit/acl_anthology_source_quality_latest.json
artifacts/reports/source_audit/acl_anthology_source_quality_latest.md
```

History reports:

```text
artifacts/reports/source_audit/history/acl_anthology_ingest_<run_ts>.json
artifacts/reports/source_audit/history/acl_anthology_ingest_<run_ts>.md
artifacts/reports/source_audit/history/acl_anthology_source_quality_<run_ts>.json
artifacts/reports/source_audit/history/acl_anthology_source_quality_<run_ts>.md
```

---

## Scripts

Main candidate ingestor:

```text
scripts/ingest/run_acl_anthology_ingest.py
```

Quality gate:

```text
scripts/validation/check_acl_anthology_source_quality.py
```

---

## Safe smoke commands

Syntax checks:

```bat
python -m py_compile scripts/ingest/run_acl_anthology_ingest.py
python -m py_compile scripts/validation/check_acl_anthology_source_quality.py
```

Small ingest smoke:

```bat
python -m scripts.ingest.run_acl_anthology_ingest --xml-ids 2024.acl --limit-docs 50
```

Quality smoke:

```bat
python -m scripts.validation.check_acl_anthology_source_quality
```

Strict quality smoke:

```bat
python -m scripts.validation.check_acl_anthology_source_quality --strict
```

A larger candidate slice can be run later, for example:

```bat
python -m scripts.ingest.run_acl_anthology_ingest --xml-ids 2024.acl
python -m scripts.validation.check_acl_anthology_source_quality --strict
```

---

## Offline mode

If the XML files are already downloaded or internet access is unavailable, place files in a local directory and run:

```bat
python -m scripts.ingest.run_acl_anthology_ingest --xml-ids 2024.acl --offline-xml-dir path\to\acl_xml
```

The offline directory must contain:

```text
2024.acl.xml
```

---

## Quality checks

The quality script checks:

- normalized JSONL exists
- rows are non-empty
- all rows have `source = acl_anthology`
- all rows are `document_type = paper`
- `doc_id` uniqueness
- `source_id` uniqueness
- `source_record_id` uniqueness
- title presence
- source id presence
- canonical ACL URL validity
- source record URL validity
- DOI format validity
- authors/year/landing page/PDF coverage in strict mode

Diagnostics include:

- DOI coverage
- abstract coverage
- author coverage
- year coverage
- duplicate DOI count
- duplicate title/year count
- code/dataset/model URL counts found inside abstracts
- distribution by year
- distribution by venue

---

## Candidate-only rule

This integration does not run reconcile.

This integration does not modify:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

This integration does not write to Postgres.

This integration does not rebuild retrieval.

This integration does not promote ACL Anthology into stable source paths.

---

## Next steps after green source quality

After candidate ingest and quality checks pass:

1. Compare ACL candidate snapshot against current canonical corpus by DOI.
2. Measure overlap with arXiv-backed 60k baseline.
3. Measure source-only ACL documents.
4. Inspect duplicate DOI and duplicate normalized title/year cases.
5. Run a reconcile candidate only, not promotion.
6. Run candidate impact audit.
7. Decide whether ACL can become stable or should remain candidate/domain slice.

---

## Important principles

ACL Anthology is a paper source.

GitHub and Hugging Face are artifact enrichment sources.

Papers with Code live remains blocked/archived.

Canonical JSONL remains the paper-level source of truth.

All ACL integration beyond candidate snapshots must go through source audit and candidate reconcile impact checks.
