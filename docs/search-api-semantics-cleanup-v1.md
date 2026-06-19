# Search API Semantics Cleanup v1

## Document status

```text
status: proposed documentation-only checkpoint
scope: API/search/runtime/Qdrant/ranking/validation documentation sync
public behavior change: none
runtime behavior change: none
Qdrant promotion: not performed
fallback: absent
```

This slice updates documentation after the accepted retrieval-serving and
ranking checkpoints.

It does not change application code. Its purpose is to make the public API
documentation reflect the current accepted behavior.

---

## 1. Why this slice exists

Several retrieval-serving layers are already completed:

```text
Dense Search Backend Abstraction v1
Qdrant Failure Contract v1
Qdrant Runtime Observability v1
Qdrant Serving Performance v1
Qdrant Hybrid Evaluation v1
Ranking Evaluation and Hardening v1
Retrieval Serving Checkpoint v1
```

The project therefore needs documentation that clearly separates:

```text
public search behavior
from
experimental Qdrant behavior
from
optional ranking behavior
from
future deployment/promotion work
```

This avoids repeating already completed dense/Qdrant/runtime work and prevents
accidental public semantic drift.

---

## 2. Current public API semantics

Public `/search` modes:

```text
lexical
dense
hybrid
```

Current behavior:

```text
/search?mode=lexical -> file lexical / DB lexical depending on runtime
/search?mode=dense   -> exact file dense
/search?mode=hybrid  -> file lexical + exact file dense hybrid
```

Experimental Qdrant endpoint:

```text
/experimental/search/qdrant -> explicit Qdrant dense search
```

Qdrant remains:

```text
optional
derived
experimental
not canonical truth
not /health dependency
not fallback provider
not public dense/hybrid default
```

---

## 3. Ranking semantics

Current accepted search ranking semantics:

```text
rank=false -> default and reference behavior
rank=true  -> explicit optional/experimental heuristic reranking
```

Accepted ranking decision:

```text
recommended_outcome = reject_heuristic_reranking
reference_behavior = unranked hybrid
public_behavior_change = false
```

The current heuristic reranking is not promoted as a default relevance strategy.

---

## 4. Runtime semantics

`/health` is backend-aware and Qdrant-independent.

`/runtime` exposes Qdrant diagnostics and operational state, including:

```text
configured endpoint
transport
collection compatibility
points/corpus match
selected profile
cache probe state
request/success/failure counters
last failure information
last timing map
requested/effective vector backend
fallback_applied
```

If Qdrant is down while file runtime is ready:

```text
/health -> 200 OK
/runtime -> 200 OK with qdrant.ok=false
/experimental/search/qdrant -> structured 503
/search?mode=dense -> file dense remains available
```

---

## 5. Validation semantics

Recommended lightweight gate:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint
```

Extended local gate:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint ^
  --include-serving-performance-evidence ^
  --include-qdrant-collection-live ^
  --include-api-smoke
```

The gate:

- validates accepted evidence;
- composes existing validators;
- does not rerun heavy benchmark jobs by default;
- does not rebuild retrieval artifacts;
- does not require Qdrant for `/health`;
- does not promote Qdrant.

---

## 6. Files updated by this slice

Recommended files:

```text
README.md
docs/api_reference.md
docs/architecture.md
docs/roadmap.md
docs/retrieval-serving-checkpoint-v1.md
docs/search-api-semantics-cleanup-v1.md
```

No production code changes are required.

---

## 7. Non-goals

This slice does not include:

```text
Qdrant promotion
ML_RADAR_VECTOR_BACKEND implementation
public vector_backend parameter
Qdrant-backed public hybrid
similar-paper migration
ranking formula change
retrieval rebuild
embedding model change
new benchmark run
generated report commit
```

---

## 8. Acceptance checklist

- [ ] API reference states current public `/search` behavior.
- [ ] API reference states `/experimental/search/qdrant` is explicit and experimental.
- [ ] API reference documents Qdrant typed error mappings.
- [ ] API reference documents current `/runtime` Qdrant diagnostics.
- [ ] API reference documents `rank=false` as reference.
- [ ] API reference documents `rank=true` as explicit optional behavior.
- [ ] README, architecture, and roadmap agree on current Qdrant status.
- [ ] Retrieval-serving checkpoint doc records the implemented gate.
- [ ] No code behavior changes are made.
- [ ] No generated reports are committed.

Suggested validation:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint --dry-run
```

Optional full local validation:

```bat
python -m scripts.validation.check_retrieval_serving_checkpoint ^
  --include-serving-performance-evidence ^
  --include-qdrant-collection-live ^
  --include-api-smoke
```

---

## 9. Operational interpretation

This slice closes documentation drift after several successful retrieval-serving
PRs.

The accepted interpretation after this slice should be:

```text
Public /search is stable and file-backed.
Qdrant is experimentally validated but not promoted.
Optional rank=true is not the default and current heuristic ranking is rejected
as a promoted relevance strategy.
The retrieval-serving checkpoint gate is the current lightweight regression
entrypoint for accepted serving evidence.
```
