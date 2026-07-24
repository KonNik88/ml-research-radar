# Field-Level Canonical Provenance Contract v0.1

## 1. Purpose

This document defines the first explicit field-level provenance contract for
ML Research Radar canonical papers.

The contract explains, for every field in `CanonicalDocument`:

```text
what reconciliation strategy produced the value
which contributing source observations were eligible
which source observations supplied the selected value or elements
which normalization or derivation steps were applied
which tie-break rule was used
whether the result is exactly reconstructable from current inputs
```

This slice documents and validates current executable reconciliation behavior.
It does not change that behavior.

---

## 2. Architectural boundaries

```text
canonical_documents.jsonl = canonical paper truth
field-level provenance evidence = derived explanatory artifact
Postgres = rebuildable materialized serving layer
source_observation_id = identity of one normalized provider observation
canonical_id = identity of one reconciled paper entity
```

Hard boundaries:

```text
canonical_truth_mutation = forbidden
reconciliation_behavior_change = forbidden_in_v0.1
canonical_document_schema_change = forbidden_in_v0.1
postgres_schema_change = not_required
api_change = not_required
streamlit_change = not_required
retrieval_change = forbidden
qdrant_change = forbidden
graph_change = forbidden
publication_state_change = forbidden
```

Field-level provenance must initially be emitted, inspected, and validated as a
separate derived evidence artifact. It must not be embedded into
`canonical_documents.jsonl` or treated as a reconcile input.

```text
may_be_used_as_reconcile_input = false
```

---

## 3. Identity domains

The contract distinguishes four identity domains.

```text
source_observation_id
= deterministic identity of one normalized source observation

legacy doc_id
= retained source-record compatibility/diagnostic identifier; not globally unique

canonical_id
= deterministic paper-level identity derived from reconciliation_key

field evidence record id
= optional deterministic derived evidence identifier; not paper identity
```

The source family is part of `source_observation_id`, so the same legacy
`doc_id` or DOI-backed canonical URL from different providers cannot collapse
source observations.

---

## 4. Observation participation states

These states must not be conflated.

```text
selected normalized observation
= a row in the selected timestamped normalized source snapshots

materialized observation
= a row represented in Postgres source_documents

contributing observation
= a source row present in CanonicalDocument.sources for one canonical paper

field candidate observation
= a contributing observation whose field value is eligible for one field rule

field selected observation
= a candidate observation whose value wins a scalar/min/max rule

field contributing observation
= an observation that contributes one or more elements/evidence signals to a
  union, boolean, aggregate, or derived result
```

Current operational counts:

```text
selected normalized observations = 88,178
materialized observations = 88,178
canonical provenance observations = 88,037
non-contributing observations = 141
```

The 141 non-contributing observations are materialized source evidence but are
not members of promoted canonical provenance. They must not appear as field
candidates for a canonical paper unless a future explicit reconciliation
change first makes them contributing observations.

---

## 5. Current reconciliation identity semantics

Canonical grouping uses conservative identity resolution:

```text
compatible DOI
→ arXiv base identity
→ normalized title + year fallback
```

Special DOI conflict rule:

```text
one DOI associated with multiple explicit arXiv base IDs
→ split by arXiv base
→ isolate DOI-only rows as doi_conflict::<doi>
```

Canonical identity:

```text
canonical_id = stable_hash(reconciliation_key, length=32)
```

Field-level provenance does not replace or reinterpret this grouping trace.
Identity provenance is recorded separately from value-selection provenance.

---

## 6. Provenance strategy taxonomy

The accepted strategy kinds are:

| Strategy kind | Meaning |
|---|---|
| `identity_derived` | Value is derived from the reconciliation identity/grouping process. |
| `winner` | One source observation supplies the selected scalar value. |
| `winner_with_normalization` | One winner is selected and then normalized or semantically rewritten. |
| `winner_with_quality_rank` | Candidates are ordered by explicit quality rank before source priority. |
| `ordered_first` | First eligible value in contributing observation order wins. |
| `ordered_union` | Elements are merged in deterministic observation order with deduplication. |
| `aggregate_min` | Minimum eligible source value wins. |
| `aggregate_max` | Maximum eligible source value wins. |
| `boolean_evidence` | Result is derived from positive, negative, or override evidence across observations. |
| `derived_flag` | Result is computed from explicit flags and/or merged field presence. |
| `derived_score` | Result is recomputed from merged canonical fields. |
| `row_level_provenance` | Result describes contributing rows or source-family counts. |
| `merged_identifier_map` | First non-empty value per identifier key is preserved. |
| `runtime_default` | Value is created by the output model at canonical-object construction time. |

---

## 7. Ordering and tie-break semantics

Contributing observation order is the order of `docs` inside the reconciliation
group. Current reconciliation does not globally sort every group before all
field rules.

Consequences:

```text
ordered_first and ordered_union strategies are input-order-sensitive
Python stable sort preserves original order for equal sort keys
some tuple sorts include a final string value and therefore use reverse
lexicographic ordering as the last tie-break
```

Current explicit tie-breaks:

```text
title / abstract:
  longest value, then OpenAlex on equal length; remaining exact ties preserve
  stable input order

preferred string:
  source priority, optional length, then reverse lexicographic value

license:
  normalized license quality, source priority, then reverse lexicographic value

repo_url:
  artifact-source priority, URL length; exact ties preserve stable input order

max/min:
  equal numeric/date values may have multiple co-winners
```

For equal-valued min/max results, evidence may list all observations that carry
the selected value rather than inventing one exclusive winner.

---

## 8. Field-selection matrix

### 8.1 Identity and identifier fields

| Canonical field | Strategy | Current implementation | Evidence requirement |
|---|---|---|---|
| `canonical_id` | `identity_derived` | `build_canonical_id` | reconciliation key and hash rule |
| `reconciliation_key` | `identity_derived` | `build_reconciliation_groups` | grouping basis, conflict branch, participating observation IDs |
| `doc_ids` | `ordered_union` | `dedupe_preserve_order` | element-to-observation contributors; note legacy non-uniqueness |
| `doi` | `ordered_first` | `choose_best_doi` | first direct DOI, otherwise first external DOI; order caveat |
| `arxiv_id` | `winner` | `choose_best_arxiv_id` | arXiv-source direct ID, then any direct ID, then external ID |
| `openalex_id` | `ordered_first` | `choose_best_openalex_id` | first direct ID, otherwise external ID |
| `source_ids` | `merged_identifier_map` | `merge_source_ids` | per-key contributing observation and first-value rule |
| `external_ids` | `merged_identifier_map` | `merge_external_ids` | per-key contributing observation and first-value rule |
| `pmid` | `ordered_first` | `choose_first_nonempty_string` | selected observation and contributing order |
| `pmcid` | `ordered_first` | `choose_first_nonempty_string` | selected observation and contributing order |
| `semantic_scholar_id` | `ordered_first` | `choose_first_nonempty_string` | selected observation and contributing order |
| `dblp_id` | `ordered_first` | `choose_first_nonempty_string` | selected observation and contributing order |
| `mag_id` | `ordered_first` | `choose_first_nonempty_string` | selected observation and contributing order |

### 8.2 Core content and dates

| Canonical field | Strategy | Current implementation | Evidence requirement |
|---|---|---|---|
| `title` | `winner` | `choose_best_title` | selected observation, title length, OpenAlex tie-break |
| `abstract` | `winner` | `choose_best_abstract` | selected observation, abstract length, OpenAlex tie-break |
| `authors` | `ordered_union` | `merge_unique_strings` | element-level contributors and case-insensitive deduplication |
| `published_at` | `aggregate_min` | `choose_best_published_at` | all eligible values and all equal minima |
| `publication_date` | `aggregate_min` | `choose_best_publication_date` | all eligible values and all equal minima |
| `updated_at` | `aggregate_max` | `choose_best_updated_at` | source `updated_source_at` values; naive timestamps coerced to UTC |
| `year` | `aggregate_min` | `choose_best_year` | accepted range and all equal minima |

### 8.3 Links, accessibility, and taxonomy

| Canonical field | Strategy | Current implementation | Evidence requirement |
|---|---|---|---|
| `landing_page_url` | `ordered_first` | `choose_best_landing_page_url` | selected observation and input-order caveat |
| `pdf_url` | `ordered_first` | `choose_best_pdf_url` | selected observation and input-order caveat |
| `repo_url` | `winner` | `choose_best_repo_url` | artifact-source priority and URL-length tie-break |
| `license` | `winner_with_quality_rank` | `choose_best_license` | raw value, normalized value, quality rank, source priority |
| `open_access` | `boolean_evidence` | `choose_canonical_open_access` | explicit true evidence, otherwise false evidence, otherwise null |
| `primary_category` | `ordered_first` | `choose_best_primary_category` | selected observation and input-order caveat |
| `categories` | `ordered_union` | `merge_unique_strings` | element-level contributors |
| `concepts` | `ordered_union` | `merge_unique_strings` | element-level contributors |
| `keywords` | `ordered_union` | `merge_unique_strings` | element-level contributors |
| `tags` | `ordered_union` | `merge_unique_strings` | element-level contributors |

### 8.4 Publication metadata

| Canonical field | Strategy | Current implementation | Evidence requirement |
|---|---|---|---|
| `comment` | `winner` | `choose_preferred_string` | comment source priority, length, final value tie-break |
| `journal_ref` | `winner` | `choose_preferred_string` | comment source priority, length, final value tie-break |
| `venue` | `winner_with_normalization` | `choose_preferred_string` + `normalize_venue_fields` | pre-normalization winner and transformation trace |
| `journal` | `winner_with_normalization` | `choose_preferred_string` + `normalize_venue_fields` | winner may be cleared for book-chapter series semantics |
| `conference` | `winner_with_normalization` | `choose_preferred_string` + `normalize_venue_fields` | winner may be cleared or derived from venue |
| `publisher` | `winner` | `choose_preferred_string` | bibliographic source priority and final tie-break |
| `publication_type` | `winner_with_normalization` | `choose_best_publication_type` | non-preprint semantic override and source-priority winner |
| `language` | `winner` | `choose_preferred_string` | default source priority and final tie-break |

### 8.5 Citation/reference and artifact fields

| Canonical field | Strategy | Current implementation | Evidence requirement |
|---|---|---|---|
| `cited_by_count` | `aggregate_max` | `choose_max_int` | all eligible values and all equal maxima |
| `references_count` | `aggregate_max` | `choose_max_int` | all eligible values and all equal maxima |
| `referenced_ids` | `ordered_union` | priority-sorted docs + `merge_unique_strings` | bibliographic priority order and element contributors |
| `referenced_dois` | `ordered_union` | priority-sorted docs + `merge_unique_strings` | bibliographic priority order and element contributors |
| `referenced_arxiv_ids` | `ordered_union` | priority-sorted docs + `merge_unique_strings` | bibliographic priority order and element contributors |
| `citation_graph_available` | `boolean_evidence` | `any` | all true evidence observations |
| `code_links` | `ordered_union` | `merge_unique_strings` | element-level contributors |
| `dataset_links` | `ordered_union` | `merge_unique_strings` | element-level contributors |
| `model_links` | `ordered_union` | `merge_unique_strings` | element-level contributors |
| `has_code_link` | `derived_flag` | explicit flag OR code links OR repo URL | evidence components and final OR trace |
| `has_dataset_link` | `derived_flag` | explicit flag OR dataset links | evidence components and final OR trace |
| `has_model_link` | `derived_flag` | explicit flag OR model links | evidence components and final OR trace |

### 8.6 Row-level provenance, quality, and type flags

| Canonical field | Strategy | Current implementation | Evidence requirement |
|---|---|---|---|
| `sources` | `row_level_provenance` | `build_source_links` | one entry per contributing observation, preserving order |
| `source_count` | `row_level_provenance` | `len(docs)` | contributing observation IDs |
| `unique_source_count` | `row_level_provenance` | distinct non-empty source families | contributing source-family set |
| `metadata_completeness_score` | `derived_score` | `compute_metadata_completeness_score` | twelve boolean component checks and recomputed score |
| `is_open_access` | `boolean_evidence` | `choose_canonical_is_open_access` | non-arXiv bibliographic true/false evidence only |
| `is_preprint` | `boolean_evidence` | `choose_canonical_is_preprint` | published/non-preprint override, flags, then type inference |
| `is_review` | `boolean_evidence` | `any` | true evidence observations |
| `is_survey` | `boolean_evidence` | `any` | true evidence observations |
| `is_withdrawn` | `boolean_evidence` | `any` | true evidence observations |
| `created_at` | `runtime_default` | `CanonicalDocument` default factory | canonical object construction timestamp; no source winner |
| `updated_record_at` | `runtime_default` | `CanonicalDocument` default factory | canonical object construction timestamp; distinct from merged `updated_at` |

---

## 9. Derived evidence record contract

The initial derived record shape is:

```json
{
  "schema_version": "field_level_canonical_provenance_v0.1",
  "canonical_id": "...",
  "reconciliation_key": "...",
  "field_name": "abstract",
  "strategy_kind": "winner",
  "implementation": ["choose_best_abstract"],
  "result_state": "value",
  "result_fingerprint": "sha256:...",
  "result_preview": "bounded diagnostic preview",
  "contributing_source_observation_ids": ["..."],
  "candidate_source_observation_ids": ["..."],
  "selected_source_observation_ids": ["..."],
  "element_contributors": [],
  "candidate_values": [],
  "selection_reason": "longest_non_empty",
  "tie_break_reason": "openalex_equal_length",
  "transformations": [],
  "deterministic": true,
  "reconstructable": true,
  "order_sensitive": false,
  "caveats": []
}
```

Required fields:

```text
schema_version
canonical_id
reconciliation_key
field_name
strategy_kind
implementation
result_state
contributing_source_observation_ids
deterministic
reconstructable
order_sensitive
caveats
```

Conditional fields:

```text
selected_source_observation_ids
= required for scalar winner/first/min/max when a source value exists

candidate_source_observation_ids
= required when eligibility can be represented as source observations

element_contributors
= required for ordered_union and merged_identifier_map evidence

transformations
= required when a selected value is normalized, cleared, copied, or derived

candidate_values
= optional bounded diagnostic evidence; must not expose restricted full payloads
```

---

## 10. Result states

Accepted `result_state` values:

```text
value
null
empty_collection
runtime_default
identity_derived
derived
```

A null result must still record candidate/evidence semantics. Null does not mean
that provenance is absent.

Examples:

```text
abstract = null
→ no contributing observation had a non-empty abstract

is_open_access = null
→ no non-arXiv bibliographic OA true/false evidence existed

conference = null
→ winner absent, or selected series-like value cleared by venue normalization
```

---

## 11. Value handling and privacy

Field-level evidence must default to fingerprints and bounded previews.

```text
full abstract reproduction = not required
full restricted provider payloads = forbidden
Semantic Scholar source rows = private diagnostic evidence only
PDF/full text = forbidden
credentials/.env = forbidden
```

Recommended fingerprint:

```text
sha256(canonical JSON serialization of the selected value)
```

For list/map fields, element fingerprints and contributor mappings are
preferred over copying unrestricted large values into every evidence row.

---

## 12. Determinism and reconstructability

`deterministic=true` means that the same ordered contributing observations and
the same implementation version produce the same field result and evidence.

`reconstructable=true` means the result can be reproduced from the contributing
normalized observations and current reconciliation implementation.

Known caveats:

```text
ordered_first and ordered_union depend on contributing observation order
runtime timestamps are not source-derived
exact source winner cannot be unique when equal min/max values occur
venue/conference normalization can produce a value not copied verbatim from one
source field
metadata_completeness_score depends on merged intermediate values
```

The evidence generator must describe these cases instead of fabricating a
single source winner.

---

## 13. Validation requirements

The contract validator must be read-only and must verify:

```text
all CanonicalDocument fields are classified
all non-default canonical assembly fields are explicitly written by reconcile
all required reconciliation helper functions exist
all accepted strategy kinds are documented
identity/materialization/contribution/field-selection states are distinct
canonical mutation is forbidden
Postgres/API/retrieval/Qdrant/graph changes are not required
field evidence is derived and not a reconcile input
```

The validator must not:

```text
run reconciliation over the full corpus
mutate canonical_documents.jsonl
mutate Postgres
call provider APIs
write public release artifacts
```

---

## 14. Deterministic fixture requirements

Smoke tests must cover at least:

```text
title longest + OpenAlex tie-break
abstract longest + OpenAlex tie-break
ordered-first DOI behavior
union with case-insensitive deduplication
preferred-string priority and final tie-break
license normalization and quality rank
venue/journal/conference normalization
min/max with equal co-winners
open_access and is_open_access distinction
published evidence overriding is_preprint
metadata_completeness_score recomputation
derived has_code_link
DOI conflict grouping
runtime-default timestamps
```

Synthetic fixtures are acceptable for branches absent from the current bounded
audit sample, including DOI conflict cases.

---

## 15. Initial implementation file plan

This contract slice creates:

```text
docs/field_level_canonical_provenance_contract_v0.1.md
scripts/validation/check_field_level_canonical_provenance_contract.py
tests/smoke/test_field_level_canonical_provenance_contract.py
```

It does not initially create:

```text
field-level provenance runtime API
Postgres provenance tables
CanonicalDocument provenance fields
Streamlit provenance UI
new reconciliation selectors
```

A later implementation slice may add a read-only builder that emits bounded
JSONL evidence for selected samples before any full-corpus generation is
considered.

---

## 16. Acceptance decision

```text
contract_status = accepted_candidate
implementation_scope = documentation_plus_static_validation
canonical_contract_change_required = false
reconciliation_behavior_change_required = false
postgres_change_required = false
runtime_change_required = false
next_slice = field_level_canonical_provenance_evidence_builder_v0.1
```

The next slice may begin only after this document, its validator, and its smoke
tests are green against the current repository implementation.
