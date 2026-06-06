# Qdrant / File-Dense Parity Checkpoint v1

## Status

This checkpoint hardens the experimental Qdrant serving path without changing
public search behavior.

- canonical corpus remains the paper-level source of truth;
- file dense remains the public and reference dense backend;
- Qdrant remains an optional derived serving backend;
- public `/search` modes remain `lexical`, `dense`, and `hybrid`;
- no automatic fallback or hidden backend switch is introduced.

Active retrieval build:

- build ID: `20260504T164021Z`
- corpus size: `60,954`
- embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- embedding dimension: `384`
- Qdrant collection: `ml_radar_dense_benchmark_v1`
- distance: `Cosine`

## Why this checkpoint was required

The original Qdrant/file comparison used the default Qdrant HNSW search and
reported one mismatch across the expanded 34-query Golden Set v2:

- mean overlap@20: `0.998529`
- minimum overlap@20: `0.95`
- exact same order: `33/34`
- affected query: `mixture_of_experts_language_models_001`

The mismatch could not safely be treated as a harmless boundary tie before
checking exact search, vector identity, payload mapping, build compatibility,
and repeated-run determinism.

## Reference semantics

The exact file-dense reference is the current public file kernel:

```python
query_vector = model.encode(
    [query],
    convert_to_numpy=True,
    normalize_embeddings=True,
)[0].astype(np.float32)

scores = stored_normalized_embeddings @ query_vector
order = np.argsort(scores)[::-1]
```

Guarantees:

- the query is normalized once by the embedding model;
- the persisted embedding matrix is used as stored;
- dense metadata must declare `normalized=true`;
- scores use float32 matrix-vector multiplication;
- the oracle uses full descending `np.argsort`.

The parity tools no longer use a separately defined approximate file helper as
the source of truth.

## Root-cause investigation

For `mixture of experts language models`, default Qdrant search omitted the
exact file result at rank 10:

- missed canonical ID: `989404213cfbfc6e1d2c5386acf475fa`
- exact file rank: `10`
- replacement canonical ID: `0608d3a69d12ff457ce5cade497afd42`
- replacement exact file rank: `21`

This was not a rank-20/rank-21 near tie.

The following checks passed:

- Qdrant vectors matched the persisted `.npy` vectors;
- `point_id`, `payload.dense_index`, and dense row index were consistent;
- `payload.canonical_id == dense_ids[dense_index]`;
- payload build IDs matched `20260504T164021Z`;
- the collection point count and vector dimension matched the manifest;
- five recorded default-profile runs returned identical order and scores;
- exact Qdrant search returned the same top-20 and ordering as file dense.

Classification:

`approximate_search_recall_difference`

The collection and mapping were correct. The default HNSW traversal did not
visit one exact neighbor for that query.

## Search-profile sweep

All 34 enabled Golden Set v2 queries were compared against exact file dense.

| profile | mean overlap@20 | min overlap@20 | exact order | mismatches | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| default | 0.998529 | 0.95 | 33/34 | 1 | 27.13 | 43.03 |
| ef_128 | 0.998529 | 0.95 | 33/34 | 1 | 29.72 | 44.77 |
| ef_256 | 1.0 | 1.0 | 34/34 | 0 | 31.92 | 47.12 |
| ef_512 | 1.0 | 1.0 | 34/34 | 0 | 38.44 | 47.22 |
| exact | 1.0 | 1.0 | 34/34 | 0 | 46.82 | 48.36 |

`ef_256` is the smallest evaluated ANN search breadth that restored complete
Golden Set parity. `ef_512` and exact search did not improve quality on this set
and had higher median latency.

## Selected contracts

### Selected ANN parity profile

```yaml
name: ef_256
exact: false
hnsw_ef: 256
```

This is the selected evaluation/regression profile for the current build and
Golden Set. It is a candidate for future experimental serving configuration,
not a public API default.

### Exact diagnostic profile

```yaml
name: exact
exact: true
```

Exact Qdrant is the diagnostic control. It must match exact file dense for every
enabled query. An exact-profile mismatch is blocking because it suggests a
vector, mapping, build, distance, or mathematical inconsistency rather than an
expected ANN recall trade-off.

## Comparison v2 guarantees

`qdrant_file_dense_comparison_v2` compares, for every enabled query:

1. exact file dense;
2. selected Qdrant `ef_256`;
3. exact Qdrant.

The report records:

- one shared query-vector fingerprint;
- external top-k and internal diagnostic window;
- ranked IDs and full-precision scores;
- rank and score deltas;
- automatic reference-only and candidate-only IDs;
- mapping and payload audit results;
- repeated-run diagnostics when a mismatch exists;
- explicit mismatch classification and severity;
- latency summaries for file, selected ANN, and exact Qdrant.

Strict validation requires:

- zero execution errors;
- selected profile full match on the current Golden Set;
- exact profile full match;
- zero mapping/payload/build failures;
- zero blocking or unclassified differences;
- valid query-vector metadata and per-query report structure.

## Collection validation v2

The lightweight collection validator now checks:

- collection existence and health;
- point count versus manifest corpus count;
- vector dimension and cosine distance;
- dense IDs and dense metadata compatibility;
- deterministic payload samples against the active build;
- `point_id == dense_index` for this benchmark collection;
- `dense_ids[dense_index] == payload.canonical_id`;
- payload build ID consistency.

Default strict validation uses a deterministic sample. A complete read-only
payload scan is available through:

```bash
python -m scripts.validation.check_qdrant_collection \
  --strict \
  --full-payload-audit
```

## Regression entry points

Lightweight Qdrant serving regression:

```bash
python -m scripts.validation.run_discovery_api_regression \
  --include-qdrant-serving-poc \
  --include-qdrant-api
```

Full five-profile sweep:

```bash
python -m scripts.validation.run_discovery_api_regression \
  --skip-similar-rebuild \
  --include-qdrant-profile-sweep
```

The sweep remains opt-in because it executes five Qdrant profiles over every
enabled golden query.

## Current limitations

- Passing 34 Golden Set queries does not prove equivalence for every possible
  query or a future corpus build.
- `ef_256` must be re-evaluated after changes to the corpus, embedding model,
  Qdrant index configuration, server version, or Golden Set.
- Local latency does not establish a production performance advantage. On the
  current 60k-vector corpus, NumPy file dense remains faster in the measured
  local runs.
- The existing experimental API endpoint has not been promoted or silently
  switched by this checkpoint. Runtime search-profile configuration belongs to
  the later dense-backend abstraction/adoption slice.

## Decision and next slice

This checkpoint removes the integrity blocker for an internal dense backend
abstraction:

```text
DenseSearchBackend
├── FileDenseBackend
└── QdrantDenseBackend
```

The next slice may introduce the internal candidate-retrieval contract and use
it in evaluation and experimental paths. Public dense and hybrid search remain
file-backed until explicit promotion gates, failure semantics, observability,
and regression contracts are completed.
