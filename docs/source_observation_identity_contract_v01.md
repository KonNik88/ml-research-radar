# Source Observation Identity Contract v0.1

## Status

Design and validation contract. This slice does not migrate PostgreSQL, does not
change the normalized document schema, and does not rewrite existing snapshots or
the canonical corpus.

## Problem

ML Research Radar has two different identity levels:

1. **Paper identity** — one real paper after reconciliation.
2. **Source-observation identity** — one normalized record supplied by one source.

The existing legacy `doc_id` is built from `canonical_url`. DOI-aligned Crossref,
OpenAlex, and Semantic Scholar records can therefore receive the same `doc_id`.
That behavior is useful as a paper-alignment signal, but it is too coarse to be
the unique identity of a source observation.

The canonical model remains correct:

```text
source observations -> reconciliation -> canonical paper
```

This contract adds a parallel, source-aware identifier without changing existing
paper identity or merge behavior.

## Identity terms

### `canonical_id`

Stable paper-level identity created after reconciliation. Multiple source
observations may contribute to the same `canonical_id`.

### Legacy `doc_id`

Current normalized-record field, usually `hash(canonical_url)`. It remains
unchanged in v0.1 for backward compatibility. It must not be assumed globally
unique across source families.

### `source_observation_id`

Deterministic identity for one normalized record from one source family.
Different sources must not collapse merely because they share a DOI, canonical
URL, or legacy `doc_id`.

## Formula

```text
source_observation_id = stable_hash(
    JSON([
        "source_observation_v1",
        normalized_source,
        identity_basis,
        normalized_identity_value
    ])
)
```

The hash is SHA-256 truncated to 32 hexadecimal characters, matching the existing
project ID length convention.

## Identity-basis precedence

The first non-empty usable value wins:

1. `source_record_id`
2. `source_id`
3. `source_record_url`
4. `source_api_url`
5. legacy `doc_id`
6. `canonical_url`

The selected basis name is part of the hash payload. The source family is always
part of the hash payload, including URL and legacy-`doc_id` fallbacks.

A record with no source or no usable identity field fails closed with
`ValueError`.

## Source normalization

Source names are trimmed, lower-cased, and normalized to underscore-separated
families. Alignment-directory aliases map to their source family:

```text
openalex_alignment          -> openalex
semantic_scholar_alignment  -> semantic_scholar
crossref_alignment          -> crossref
acl                         -> acl_anthology
```

## Provider identity normalization

### Crossref

`source_record_id` and `source_id` are normalized DOI values:

- lower-case;
- remove `doi:`;
- remove `http(s)://doi.org/` and `http(s)://dx.doi.org/`;
- remove a trailing slash.

### OpenAlex

OpenAlex Work IDs are normalized to:

```text
https://openalex.org/W<digits>
```

### Semantic Scholar

Semantic Scholar `paperId` is trimmed and lower-cased. Known API and paper URL
prefixes are removed when present.

### arXiv

Known arXiv URL and `arxiv:` prefixes are removed. The ID is lower-cased and a
version suffix is retained when present. Contract v0.1 follows the current
normalized `source_record_id` semantics; deciding whether a future source-record
identity should use the base arXiv ID is outside this slice.

### ACL Anthology

ACL Anthology URL prefixes and trailing slashes are removed and the anthology ID
is lower-cased.

### URL fallbacks

URL bases use the existing project `canonicalize_url()` helper. They are fallback
identity evidence only and do not replace provider-native record IDs.

## Invariants

For exporter-selected normalized snapshots:

- every valid row produces one deterministic `source_observation_id`;
- the same descriptor produces the same ID on repeated calls;
- different source families do not share a `source_observation_id`;
- one generated ID never maps to two different normalized descriptors;
- legacy cross-source `doc_id` collisions are reported as diagnostic evidence,
  not as a failure of this new contract;
- duplicate rows with the same descriptor are reported separately from hash or
  identity conflicts.

## Selected snapshots

The validator mirrors the current PostgreSQL exporter input-selection rule and
uses the lexicographically latest exact timestamped primary file:

```text
data/normalized/arxiv/documents.<timestamp>.jsonl
data/normalized/openalex_alignment/documents.<timestamp>.jsonl
data/normalized/semantic_scholar_alignment/documents.<timestamp>.jsonl
data/normalized/crossref_alignment/documents.<timestamp>.jsonl
data/normalized/acl_anthology/documents.<timestamp>.jsonl
```

Files such as `documents_latest.jsonl`, `.new.jsonl`, `.updated.jsonl`, and
`.unchanged.jsonl` are not selected.

## Strict validation criteria

A strict run succeeds only when:

- all five required snapshots are selected;
- at least one row is read;
- snapshots contain valid JSON objects;
- source values are present and match their selected source family;
- every row has a usable source-observation identity;
- no generated ID maps to conflicting descriptors;
- no generated ID is shared by different source families;
- repeated generation is deterministic.

Duplicate observations and legacy `doc_id` cross-source collisions remain
reported diagnostics and do not fail v0.1 by themselves.

## Non-goals

This slice does not:

- add `source_observation_id` to `NormalizedDocument`;
- rewrite normalized snapshots;
- change `doc_id` generation;
- change reconciliation or `canonical_id`;
- alter PostgreSQL tables or foreign keys;
- alter the PostgreSQL exporter;
- rebuild retrieval, Qdrant, API, UI, or artifact layers.

## Follow-up gate

A PostgreSQL materialization implementation may start only after the full strict
validator is green and the report confirms:

```text
missing_identity_count = 0
identity_conflict_count = 0
source_observation_id_cross_source_collision_count = 0
determinism_failure_count = 0
```

The follow-up slice will decide how the proven identity is represented in
`source_documents` and `canonical_source_links`, first on a candidate database.
