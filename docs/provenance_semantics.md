# Provenance semantics

## Purpose

This document fixes the intended meaning of provenance-related fields in the canonical corpus.

It exists to prevent confusion between:
- identifier linkage,
- source provenance,
- contributing normalized rows,
- operational source-observation identity,
- canonical merge counts,
- field-level selection and element-level contribution evidence.

This is especially important during refresh validation, reconcile debugging, and future source onboarding.

---

## Big picture

The project has two semantic data layers plus a derived provenance
governance/evidence family:

- **source-level normalized documents**
  Individual normalized records from arXiv, OpenAlex, Semantic Scholar, Crossref, ACL Anthology, and future sources.

- **paper-level canonical documents**
  Merged paper entities created by reconcile.

- **field-level canonical provenance contract**
  A read-only description of how each canonical field is selected, merged,
  normalized, aggregated, or derived from contributing observations.

- **bounded field-level canonical provenance evidence**
  Deterministic explanatory records for synthetic fixtures and selected audit
  samples, one record per `canonical_id + field_name`.

- **field-level evidence review and regression hardening**
  A read-only comparison of accepted evidence runs and the bounded audit package
  that detects semantic drift and pins the accepted baseline.

- **Field-Level Canonical Provenance Evidence Checkpoint v0.1**
  A final fail-closed read-only report that aggregates the accepted contract,
  evidence-validation, and semantic-review reports and closes the bounded line.

- **Scientific Entity Evidence Contract v0.1**
  A downstream contract for exact typed spans in canonical title/abstract text,
  with extractor-independent mention identity and extractor-specific evidence
  identity. It does not explain reconciliation and does not modify canonical
  provenance.

- **Bounded Scientific Entity Extractor Baseline v0.1**
  A deterministic rule-based producer of fixture/candidate mention evidence.
  It records canonical input, semantic config, dependency environment, and code
  fingerprints, but remains downstream of canonical truth and cannot become a
  reconcile input.

The contract, evidence, review, and checkpoint are not a third truth layer and do
not add fields to `CanonicalDocument`. They document, explain, and validate current
reconciliation behavior.

Because of this, not every canonical field has a strict one-to-one relationship
with a single source row.

---

## Core rule

A canonical document is a **merged paper entity**.

That means different fields in the canonical object answer different questions:

- some fields describe the merged paper identity,
- some fields describe which source rows contributed to the merge,
- some fields describe identifiers that were carried through merge,
- some fields describe counts of contributing rows or source families.

So fields that look related are **not always interchangeable**.

---

## Field semantics

### `source_ids`

`source_ids` is a **merged identifier map**.

It is **not** a strict provenance structure.

It may include identifiers that were:
- present directly in a contributing normalized row,
- carried through external linkage fields,
- inferred through merge of source metadata.

Example:
- a Semantic Scholar normalized row may contain an `arxiv_id`,
- after reconcile, canonical `source_ids` may contain `"arxiv": "..."`,
- even if there is no separate arXiv provenance row inside `sources`.

So:
- presence of `"arxiv"` in `source_ids`,
- or presence of `arxiv_id` in canonical,

**does not automatically mean** that canonical provenance must contain an arXiv source row.

---

### `sources`

`sources` is the **provenance rows list** for the canonical document.

Each entry in `sources` corresponds to a **contributing normalized input row** used during canonical merge.

Important:
- `sources` is **row-level provenance**,
- not just source-family-level provenance.

That means multiple entries from the same source family may appear in `sources` if multiple contributing normalized rows were merged.

Example:
- two contributing arXiv manifestation rows,
- both may appear in `sources`,
- this increases `source_count`,
- but not `unique_source_count`.

So repeated source families in `sources` are not automatically an error.

---

### `source_count`

`source_count` means:

> number of contributing normalized documents merged into the canonical document

It is expected to match:

```text
len(sources)
```

It is **not** the number of unique source families.

---

### `unique_source_count`

`unique_source_count` means:

> number of unique source families among contributing provenance rows

It is expected to match:

```text
len(set(source_name for source_name in sources))
```

Examples:
- arXiv + OpenAlex + Semantic Scholar + Crossref
  → `source_count = 4`, `unique_source_count = 4`

- two arXiv rows + OpenAlex + Semantic Scholar + Crossref
  → `source_count = 5`, `unique_source_count = 4`

---

### `source_observation_id`

`source_observation_id` is the deterministic identity of one selected source
observation in the Postgres materialization layer.

It is derived from the source observation mapping through the shared source
identity helper. It is the authoritative physical key used by:

```text
source_documents.source_observation_id
canonical_source_links.source_observation_id
```

Operational rules:

- it is globally unique for materialized source observations;
- it is the primary key of `source_documents`;
- canonical links reference it directly;
- it does not replace `canonical_id`;
- it does not change reconciliation or canonical paper identity;
- a valid selected observation may remain unlinked when it did not contribute to
  canonical provenance.

Current accepted counts:

```text
selected source observations = 88,178
canonical provenance pairs = 88,037
valid non-contributing observations = 141
```

---

### `doc_id`

`doc_id` remains a normalized-document identifier and legacy diagnostic field.
It is **not globally unique across all source observations** and must not be used
as the physical primary key of the operational source materialization.

Current Postgres semantics:

```text
source_documents.doc_id = NOT NULL, non-unique
canonical_source_links.doc_id = nullable legacy diagnostic
```

The same legacy `doc_id` may occur in observations from different source
families. That is not a canonical collision and must not cause one observation
to overwrite another.

---

### `doc_ids`

`doc_ids` is the **deduplicated** list of contributing normalized `doc_id` values.

Important:
- `doc_ids` is deduplicated,
- `sources` is not deduplicated,
- therefore `len(doc_ids)` may be smaller than `len(sources)`.

This is **not automatically an error**.

So the condition:

```text
len(doc_ids) < len(sources)
```

is an informational signal, not a structural failure by itself.

---

### `arxiv_id`

`arxiv_id` in canonical is a merged canonical identity field.

It may come from:
- a true arXiv normalized row,
- or an external linkage carried by another source, such as Semantic Scholar.

Therefore:
- canonical `arxiv_id` present,
- but no `arxiv` entry in `sources`,

is possible and not necessarily a bug.

This should be treated as a warning-level situation only when provenance interpretation matters.

---


## Provenance levels

The project distinguishes three provenance resolutions.

### Row-level provenance

```text
CanonicalDocument.sources
= ordered contributing normalized observations for one canonical paper
```

Row-level provenance answers which observations participated in the canonical
merge. It does not by itself explain which observation supplied every field.

### Field-selection provenance

Field-selection provenance answers:

```text
which contributing observations were eligible for one field
which observation or observations supplied the result
which selector, aggregate, or normalization rule was applied
whether ordering or a tie-break affected the result
```

A source observation may be:

```text
selected normalized observation
materialized observation
contributing observation
field candidate observation
field selected observation
field contributing observation
```

These states are not interchangeable. In particular, the 141 valid
non-contributing observations are materialized but are not field candidates for
the promoted canonical corpus.

### Element-level provenance

Union and merged-map fields may contain elements from several observations.

Examples:

```text
authors
categories
concepts
keywords
tags
referenced_ids
referenced_dois
referenced_arxiv_ids
code_links
dataset_links
model_links
source_ids
external_ids
doc_ids
```

For these fields, a single scalar winner would be misleading. The implemented
bounded evidence maps each retained element or identifier key to contributing
`source_observation_id` values and preserves first-contributor and duplicate
evidence where applicable.

---

## Downstream scientific-entity evidence provenance

Scientific entity mention evidence is downstream of canonical reconciliation:

```text
canonical_id
+ exact canonical source_field text
+ source_text_sha256
+ Unicode code-point [char_start, char_end)
+ contextual entity_type
= mention_id

mention_id
+ immutable extractor descriptor fingerprint
= evidence_id
```

This is a separate evidence axis, not another canonical reconciliation
provenance resolution.

```text
source_observation_id = provider observation identity
canonical_id = paper identity
field evidence record_id = canonical field-selection evidence identity
scientific mention_id = exact typed text-span identity
scientific evidence_id = extractor observation identity
future entity_id = normalization/linking identity, not defined in v0.1
```

The global canonical file SHA-256 and document count belong to the entity-build
manifest. The per-record `source_text_sha256` prevents stale offsets while
avoiding global mention-ID churn when an unrelated paper changes.

Entity evidence must not be embedded in `CanonicalDocument.sources`, used as a
field-selection winner, or treated as source-observation provenance.

---

## Field-level strategy semantics

The accepted Field-Level Canonical Provenance Contract v0.1 classifies all 61
`CanonicalDocument` fields using these strategy families:

```text
identity_derived
winner
winner_with_normalization
winner_with_quality_rank
ordered_first
ordered_union
aggregate_min
aggregate_max
boolean_evidence
derived_flag
derived_score
row_level_provenance
merged_identifier_map
runtime_default
```

Important examples:

```text
title / abstract
= longest non-empty value; OpenAlex wins equal-length ties

doi
= first direct DOI in contributing order; otherwise first external DOI

published_at / publication_date / year
= minimum eligible value

updated_at / cited_by_count / references_count
= maximum eligible value

authors and taxonomy/reference/link lists
= deterministic ordered union with deduplication

venue / journal / conference / publication_type
= source selection followed by possible semantic normalization

metadata_completeness_score
= recomputed from merged canonical fields, not copied from one observation

created_at / updated_record_at
= canonical-object runtime defaults, not source-derived values
```

Ordering caveat:

```text
ordered_first and ordered_union are deterministic only relative to the ordered
contributing observation list used by reconciliation
```

Equal minima/maxima may have multiple co-winning observations. Normalized or
derived fields may have no single verbatim source winner. Evidence must preserve
that ambiguity rather than inventing a unique source.

Current contract validation:

```text
canonical fields classified = 61 / 61
static validator = 99 / 99
contract smoke tests = 8 passed
contract_matches_current_reconciliation = true
```

Current bounded evidence validation:

```text
canonical papers = 12
contributing source observations = 33
canonical source links = 33
unmatched source links = 0
field records = 732
source-reconstructable matches = 708
runtime-default records = 24
required value mismatches = 0
independent validator = 34 / 34
new smoke tests = 16 passed
builder-slice related regression = 45 passed
```

Current review/hardening validation:

```text
review validator = 58 / 58
review smoke tests = 7 passed
field-level evidence block = 23 passed
related regression = 52 passed

strategy families = 14
semantic files compared = 3
semantic file differences = 0
record-key differences = 0
record-content differences = 0
value mismatches = 0
unmatched source links = 0
```

Accepted semantic hashes:

```text
field_evidence.jsonl
= d3a42644e51854226343e98f048856a16b2f9cd52289bb3dd6e5676f751077b0

paper_summary.jsonl
= dc3d3ab43d4bc3bf82c14593f0b274f8989efbd7bd79694c5a397f7b58d7356d

data_quality_summary.json
= 825d49a0f5b1b95be39a6bff77a000adc03842c8290c758716a202b04bb52236
```

Review semantics:

```text
directory-driven evidence and ZIP-driven evidence must be semantically identical
package integrity checks and semantic-drift checks are separate protections
recomputed checksums do not make changed evidence an accepted baseline
audit package identity and bounded counts remain part of the review contract
```

Evidence-record semantics:

```text
record_id = deterministic evidence identity
canonical_id = unchanged paper identity
selected/co-winning IDs = subset of contributing source_observation_id values
comparison_status = match | mismatch | not_applicable
runtime-default fields = not source-reconstructable
mismatch = report only; never repair canonical data
```

Current final checkpoint validation:

```text
checkpoint validator = 35 / 35
checkpoint smoke tests = 9 passed
required_failed_count = 0

contract = 99 / 99
evidence package validator = 34 / 34
semantic review = 58 / 58

field_level_provenance_line_complete = true
bounded_evidence_checkpoint_ready = true
```

Checkpoint semantics:

```text
the checkpoint consumes existing reports only
missing/unreadable reports fail closed
report identity/schema/status drift fails closed
field/count/hash/strategy drift fails closed
semantic differences, mismatches, or unmatched links fail closed
mutation/publication safety-flag drift fails closed
the checkpoint never repairs or rebuilds evidence
```

The contract, evidence packages, semantic review, and final checkpoint are
static/read-only or bounded/read-only derived layers. No full-corpus output,
Postgres table, API, UI, publication path, or reconcile-input role is authorized
by the bounded implementation.

---

## What counts as a real structural error

The following should be treated as genuine canonical provenance or materialization errors:

1. `source_count != len(sources)`
2. `unique_source_count != number of unique source families in sources`
3. provenance source entries missing required `source` name
4. exact duplicate provenance row entries with the same `(source, source_record_id)`
5. duplicate `source_observation_id` values in `source_documents`
6. NULL or dangling authoritative `canonical_source_links.source_observation_id`
7. selected source observations missing from the operational materialization

These indicate broken provenance assembly or broken reconcile output.

---

## What counts as a warning, not an error

The following may be suspicious but are not automatically invalid:

1. `source_ids` contains more source families than `sources`
2. `arxiv_id` exists but `arxiv` is missing from provenance
3. repeated source families in `sources`

These cases require interpretation in the context of merge semantics.

---

## What counts as informational only

The following should be treated as informational diagnostics, not validation failures:

1. `len(doc_ids) < len(sources)`

This often follows naturally from current reconcile design because `doc_ids` is deduplicated while provenance rows are not.

---

## Current project interpretation

As of the current refresh cycle design:

- `source_ids` = merged identifier map
- `sources` = contributing provenance rows
- `source_count` = number of contributing normalized rows
- `unique_source_count` = number of unique source families
- `source_observation_id` = deterministic operational identity of one source observation
- `doc_id` = legacy normalized-document identifier, not a global materialization key

This interpretation is consistent with current reconcile behavior and current validation results.

---

## Practical validation guidance

When auditing canonical provenance:

### treat as errors
- `source_count` mismatch
- `unique_source_count` mismatch
- malformed provenance entries
- exact duplicate provenance rows
- duplicate source-observation identities
- NULL/dangling authoritative source-observation links
- selected observations missing from materialization

### treat as warnings
- identifier/provenance family mismatch
- arXiv identifier without arXiv provenance
- repeated source families

### treat as info
- `doc_ids` shorter than `sources`

---

## Operational consequence

Refresh validation should **not fail** only because:
- canonical `source_ids` contains `"arxiv"`,
- while provenance `sources` does not contain an arXiv row.

This can be a valid outcome of merged external linkage.

Refresh validation should fail only on **true structural inconsistencies**.

Operational source materialization validation must additionally enforce:

```text
source_documents rows = all selected observations
canonical_source_links rows = contributing canonical provenance pairs
resolved authoritative links = canonical_source_links rows
NULL authoritative links = 0
dangling authoritative links = 0
missing selected observations = 0
```

The difference between selected observations and canonical provenance pairs is
not automatically an error. In the accepted operational baseline, 141 selected
observations are valid but non-contributing.

---

## What this means for the current project state

The current project state can now be interpreted like this:

- the safe reconcile stage is functioning correctly,
- the candidate refresh path is functioning correctly,
- the corrected source-observation materialization is now operational under `ml_radar`,
- all 88,178 selected observations are preserved physically,
- all 88,037 canonical provenance links resolve through `source_observation_id`,
- 141 valid non-contributing observations remain unlinked by design,
- the canonical layer does not currently show mass structural provenance corruption,
- all 61 canonical fields have an explicit field-selection strategy classification,
- the field-level contract validator is green at 99/99,
- the bounded evidence layer explains 732 field records across 12 papers using 33 contributing observations,
- 708 source-reconstructable records match and 24 runtime-default records are correctly not applicable,
- the independent evidence validator is green at 34/34 with zero required mismatches,
- the semantic review validator is green at 58/58 across all 14 strategy families,
- directory- and ZIP-driven runs have zero semantic, record-key, or record-content differences,
- the full related regression set is green at 52/52,
- the final checkpoint validator is green at 35/35 with nine smoke tests,
- `field_level_provenance_line_complete=true` and `bounded_evidence_checkpoint_ready=true`,
- the bounded field-level provenance line is closed,
- most earlier anomalies came from mixing identifier, row-level provenance, field-level provenance, and physical materialization semantics.

That means future work should focus on:
- keeping refresh safe,
- documenting semantics clearly,
- expanding sources in a controlled way,
- and only then layering on top full text, embeddings, repositories, graph features, and MLOps automation.

---

## Next related steps

This document should stay aligned with:

- `radar_core/normalize/reconcile.py`
- canonical validation scripts
- refresh validation rules
- source onboarding rules
- future refresh contract updates
- `radar_core/utils/source_observation_identity.py`
- `scripts/export/export_postgres_v1.py`
- source-observation parity and operational-promotion validators
- `docs/field_level_canonical_provenance_contract_v0.1.md`
- `scripts/validation/check_field_level_canonical_provenance_contract.py`
- `docs/field_level_canonical_provenance_evidence_v0.1.md`
- `scripts/validation/build_field_level_canonical_provenance_evidence.py`
- `scripts/validation/check_field_level_canonical_provenance_evidence.py`
- `docs/field_level_canonical_provenance_evidence_review_v0.1.md`
- `scripts/validation/check_field_level_canonical_provenance_evidence_review.py`
- `tests/smoke/test_field_level_canonical_provenance_evidence_review.py`
- `docs/field_level_canonical_provenance_evidence_checkpoint_v0.1.md`
- `scripts/validation/check_field_level_canonical_provenance_evidence_checkpoint.py`
- `tests/smoke/test_field_level_canonical_provenance_evidence_checkpoint.py`
