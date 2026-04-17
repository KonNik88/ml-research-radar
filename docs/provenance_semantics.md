# Provenance semantics

## Purpose

This document fixes the intended meaning of provenance-related fields in the canonical corpus.

It exists to prevent confusion between:
- identifier linkage,
- source provenance,
- contributing normalized rows,
- canonical merge counts.

This is especially important during refresh validation, reconcile debugging, and future source onboarding.

---

## Big picture

The project has two different data layers:

- **source-level normalized documents**  
  Individual normalized records from arXiv, OpenAlex, Semantic Scholar, Crossref, and future sources.

- **paper-level canonical documents**  
  Merged paper entities created by reconcile.

Because of this, not every canonical field has a strict one-to-one relationship with a single source row.

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

## What counts as a real structural error

The following should be treated as genuine canonical provenance errors:

1. `source_count != len(sources)`
2. `unique_source_count != number of unique source families in sources`
3. provenance source entries missing required `source` name
4. exact duplicate provenance row entries with the same `(source, source_record_id)`

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

This interpretation is consistent with current reconcile behavior and current validation results.

---

## Practical validation guidance

When auditing canonical provenance:

### treat as errors
- `source_count` mismatch
- `unique_source_count` mismatch
- malformed provenance entries
- exact duplicate provenance rows

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

---

## What this means for the current project state

The current project state can now be interpreted like this:

- the safe reconcile stage is functioning correctly,
- the candidate refresh path is functioning correctly,
- the canonical layer does not currently show mass structural provenance corruption,
- most of the earlier “anomalies” came from mixing together identifier semantics and provenance semantics.

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
