# arXiv Ingestion Strategy

## 1. Purpose

This document defines the operational ingestion strategy for arXiv as
the backbone source of the ML Research Radar system.

It fixes how bulk data, incremental updates, and enrichment triggers are
handled.

------------------------------------------------------------------------

## 2. Role of arXiv

arXiv is the primary backbone for: - corpus coverage - titles,
abstracts, authors - categories - PDF links - preprint/open-access
manifestation

------------------------------------------------------------------------

## 3. Ingestion model overview

arXiv ingestion follows a hybrid model:

bulk seed → incremental updates → merge → enrichment → reconcile

------------------------------------------------------------------------

## 4. Bulk seed (initial dataset)

Source: - Kaggle arXiv snapshot

Process: - import snapshot - normalize into source-level documents -
store as primary arXiv base dataset

This defines the initial corpus backbone.

------------------------------------------------------------------------

## 5. Incremental updates

Source: - arXiv API

Process: - fetch new/updated papers - normalize records - store as
incremental batches

------------------------------------------------------------------------

## 6. Merge incremental batches

Incremental batches are merged into the main arXiv dataset:

-   deduplicate by arXiv_id
-   overwrite outdated records
-   keep latest version

Result: - updated arXiv primary snapshot

------------------------------------------------------------------------

## 7. DOI candidate extraction

From updated arXiv snapshot:

-   extract papers with DOI
-   filter new or updated entries

Output: - DOI candidate set for enrichment

------------------------------------------------------------------------

## 8. Selective enrichment

For DOI candidates:

enrich using: - OpenAlex - Semantic Scholar - Crossref

Output: - selective enrichment snapshots

------------------------------------------------------------------------

## 9. Merge into full alignment snapshots

Selective enrichment results are merged back into:

-   full OpenAlex snapshot
-   full Semantic Scholar snapshot
-   full Crossref snapshot

Important: Reconcile must use FULL merged snapshots, not selective-only
outputs.

------------------------------------------------------------------------

## 10. Reconcile step

Run reconcile on:

-   updated arXiv snapshot
-   merged enrichment snapshots

Output: - canonical candidate dataset

------------------------------------------------------------------------

## 11. Validation and promotion

Steps:

-   run validation checks
-   run post-pass audit
-   verify metrics (counts, multisource, etc.)

Then:

-   promote candidate → canonical latest

Promotion is explicit and manual.

------------------------------------------------------------------------

## 12. Refresh loop summary

Full pipeline:

bulk (once) → incremental fetch → merge arXiv → extract DOI candidates →
selective enrichment → merge enrichment into full snapshots → reconcile
→ validate → promote → export → rebuild retrieval → audit

------------------------------------------------------------------------

## 13. Key invariants

-   arXiv is always the backbone
-   incremental never replaces bulk, only updates it
-   enrichment is selective, not full re-fetch
-   reconcile always runs on full merged inputs
-   promotion is never automatic

------------------------------------------------------------------------

## 14. Future considerations

Possible extensions:

-   better incremental scheduling
-   retry/failure tracking
-   partial reprocessing
-   priority-based enrichment

These are not required for v1 stability.
