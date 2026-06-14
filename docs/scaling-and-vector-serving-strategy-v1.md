# ML Research Radar — Scaling and Vector-Serving Strategy v1

## Document status

```text
document: architecture and sequencing strategy
version: v1
status: accepted planning baseline
created: 2026-06-14
current stable corpus: 60954 canonical documents
current retrieval build: 20260504T164021Z
current public dense/hybrid backend: file
validated scalable vector backend: Qdrant gRPC, ef_256
public Qdrant promotion: not performed
```

This document defines when and how ML Research Radar should move from the
current representative corpus and exact file-backed vector search toward a
larger corpus, stronger embedding models, Qdrant-based serving, and additional
operational infrastructure.

It is a sequencing document, not an authorization to scale immediately.

---

## 1. Purpose

The project already has working and validated implementations for:

- canonical paper reconciliation;
- lexical, dense, and hybrid retrieval;
- ranking and paper features;
- artifact evidence;
- similar-paper search;
- topic clusters and projection;
- Discovery API and Streamlit UI;
- Postgres serving materialization;
- Qdrant vector serving;
- Golden Set evaluation and strict validators;
- failure, observability, performance, and hybrid-parity evidence.

The remaining strategic question is not whether Qdrant can work. That has been
validated for the active retrieval build.

The strategic question is:

```text
When should the project operationalize Qdrant and expand the corpus without
making iteration, debugging, rebuilds, and model changes unnecessarily costly?
```

---

## 2. Current baseline

### 2.1 Canonical and retrieval state

```text
canonical documents = 60954
canonical multisource documents = 9192
retrieval build_id = 20260504T164021Z
embedding model = sentence-transformers/all-MiniLM-L6-v2
embedding dimension = 384
vectors normalized = true
Golden Set enabled queries = 34
```

### 2.2 Current vector representations

The same retrieval generation is represented in two serving forms.

File reference:

```text
embeddings .npy
canonical dense IDs
exact matrix multiplication
full descending sort
```

Qdrant serving materialization:

```text
collection = ml_radar_dense_benchmark_v1
points = 60954
dimension = 384
distance = Cosine
transport = gRPC
selected profile = ef_256
```

Qdrant does not create different embeddings. It stores and searches the same
build-scoped vectors through a server-side ANN index.

### 2.3 Current role split

```text
FileDenseBackend
= exact reference implementation
= offline evaluation oracle
= rebuildable retrieval artifact path
= rollback target

QdrantDenseBackend
= validated scalable vector-serving implementation
= concurrent server-side ANN search
= future primary serving candidate
```

These roles should remain distinct even after Qdrant becomes the active
serving backend.

---

## 3. What the completed Qdrant work proves

Completed evidence includes:

- strict collection compatibility;
- canonical ID, dense index, point ID, and build mapping;
- exact and ANN profile comparison;
- selected `ef_256` profile;
- explicit gRPC transport;
- repeated concurrency evidence;
- typed errors and explicit no-fallback behavior;
- bounded runtime observability;
- controlled hybrid file-vs-Qdrant evaluation;
- full regression integration.

Hybrid checkpoint:

```text
queries = 34
scenarios = 136
successful = 136
errors = 0
blocking defects = 0
determinism failures = 0
identical final result sets = 136 / 136
identical final order = 134 / 136
exact dense + final parity = 132 / 136
```

This proves scale readiness for the current build.

It does not prove that the current embedding model, corpus, collection, or ANN
profile should be permanent.

---

## 4. Why the current corpus should remain the development baseline

The current corpus is neither toy-sized nor operationally expensive.

It is large enough to reveal real issues in:

- identity resolution;
- source overlap;
- provenance;
- retrieval quality;
- hybrid score composition;
- ANN recall;
- hydration;
- ranking;
- artifact evidence;
- API/UI behavior;
- memory and lifecycle management.

It is small enough to support:

- repeated full rebuilds;
- model experiments;
- manual error inspection;
- complete Golden Set reruns;
- strict validation;
- inexpensive rollback;
- architecture changes without multi-day processing.

Therefore:

```text
60954 documents = representative MVP and architecture-validation corpus
```

It should remain the primary development baseline while major product and
retrieval semantics are still changing.

---

## 5. Why premature large-scale expansion is harmful

Moving immediately to hundreds of thousands or millions of papers would make
nearly every unresolved decision more expensive.

Examples:

```text
canonical schema change
→ large reconcile and migration

identity rule correction
→ large conflict audit

embedding model change
→ large re-encoding and re-indexing

payload contract change
→ Qdrant collection rebuild

ranking feature change
→ longer evaluation and diagnostics

validator change
→ longer evidence cycles
```

The main risk is not that the project cannot store more papers.

The main risk is:

```text
scale begins to dominate iteration before product and semantic contracts are stable
```

This creates infrastructure work without enough product learning.

---

## 6. Why Qdrant should still become the long-term serving backend

Large vector collections change the economics of exact in-process search.

Relevant factors:

```text
corpus size
× embedding dimension
× concurrent queries
× update frequency
× deployment topology
```

Qdrant becomes increasingly useful when:

- vector matrices consume too much API-process RAM;
- exact full scans increase latency;
- concurrent traffic grows;
- vector storage must scale independently from API workers;
- incremental vector additions become routine;
- payload-aware vector filtering is required;
- embedding dimensions grow to 768, 1024, or beyond;
- several embedding profiles or collections coexist;
- the project moves from local MVP to persistent deployment.

Qdrant provides:

- ANN indexing;
- server-side vector storage;
- concurrent search;
- independent service scaling;
- collection lifecycle management;
- payload support;
- clearer separation between retrieval build and request-serving process.

Therefore:

```text
Qdrant is the preferred future scalable vector-serving backend.
```

This conclusion does not require immediate public promotion.

---

## 7. Accepted sequencing

The approved sequence is:

```text
current representative corpus
→ functional MVP completion
→ retrieval/model selection
→ medium-scale rehearsal
→ deployment-level Qdrant selector
→ Qdrant primary vector serving
→ major corpus expansion
→ additional orchestration and distributed infrastructure as justified
```

This sequence avoids both premature infrastructure and late forced migration.

---

## 8. Phase A — complete the functional MVP

Before major scale-up, stabilize the main project semantics.

Candidate work includes:

- graph and relation layers;
- additional paper features;
- ranking and reranking;
- discovery workflows;
- stronger source and artifact evidence;
- refresh and promotion hardening;
- evaluation improvements;
- failure injection;
- API/UI product polish;
- code ownership and architecture review.

The current corpus should remain the reference environment for these slices.

Exit conditions are not "all possible features completed".

The practical exit condition is:

```text
New functionality can be added without repeatedly redefining canonical,
retrieval, serving, and promotion contracts.
```

---

## 9. Phase B — select the next retrieval generation

A stronger scientific embedding model may be desirable before large-scale
encoding.

Potential directions:

- stronger general semantic model;
- scientific-paper embedding model;
- domain-specific fine-tuning;
- multiple retrieval profiles;
- dense + sparse learned retrieval;
- cross-encoder reranking.

Every model change creates a new retrieval generation.

Required evidence lifecycle:

```text
candidate model
→ representative-corpus embeddings
→ exact file reference
→ Golden Set evaluation
→ hybrid evaluation
→ Qdrant collection
→ ANN profile sweep
→ serving benchmark
→ explicit promotion or rejection
```

Do not encode millions of papers with a model that is still likely to be
replaced immediately afterward.

---

## 10. Phase C — medium-scale rehearsal

Before accepting a multi-million-paper corpus, run a larger candidate build.

Suggested ranges:

```text
100000–300000 papers
or
approximately 500000 papers
```

The rehearsal may be isolated from stable latest.

### 10.1 Pipeline measurements

Measure:

- source download and extraction time;
- normalization throughput;
- alignment and reconcile time;
- identity conflicts and merge precision;
- provenance growth;
- Postgres load time and storage;
- paper-feature and graph build time;
- embedding throughput;
- retrieval artifact size;
- Qdrant upload and indexing time;
- full rebuild duration;
- incremental refresh duration.

### 10.2 Serving measurements

Measure:

- exact file-search latency and memory;
- Qdrant p50/p95/p99 latency;
- concurrency behavior;
- cold start;
- hydration and serialization;
- API-worker memory;
- Qdrant storage and memory;
- collection restart and recovery.

### 10.3 Quality measurements

Measure:

- Golden Set stability;
- candidate overlap;
- group-level retrieval quality;
- ANN recall;
- hybrid final-set parity;
- ranking sensitivity;
- source/domain distribution drift.

### 10.4 Operational measurements

Measure:

- validator runtime;
- report size;
- failure recovery;
- rollback time;
- collection promotion;
- rebuild-from-artifacts procedure;
- manual operational burden.

The rehearsal decides which infrastructure is actually necessary.

---

## 11. Phase D — deployment-level Qdrant selector

Preferred future selector:

```text
ML_RADAR_VECTOR_BACKEND=file|qdrant
```

Default initially remains:

```text
file
```

The selector changes only dense candidate generation.

```text
mode=lexical
→ lexical retrieval only

mode=dense
→ selected DenseSearchBackend

mode=hybrid
→ lexical retrieval + selected DenseSearchBackend
→ common hybrid merge
→ common optional ranking
```

### 11.1 Initial scope

Include:

- public dense search;
- public hybrid search;
- configuration validation;
- runtime composition;
- readiness semantics;
- typed failures;
- reload and restart lifecycle;
- rollback proof;
- file and Qdrant regressions.

Do not include:

- public request-level backend selector;
- hidden fallback;
- similar-paper migration;
- DB-native dense search;
- filter pushdown;
- retry and circuit-breaker frameworks;
- removal of the experimental endpoint.

### 11.2 Failure policy

Initial policy:

```text
fallback = absent
```

If a deployment explicitly selects Qdrant and Qdrant is unavailable:

```text
lexical search may remain available
dense/hybrid return structured failures
readiness reflects the configured required dependency
```

A future fallback policy must be explicit and observable.

### 11.3 Rollback

Rollback target:

```text
ML_RADAR_VECTOR_BACKEND=file
```

Rollback must not require:

- canonical corpus changes;
- embedding rebuild;
- Postgres rebuild;
- API schema migration;
- UI migration.

---

## 12. Phase E — large corpus expansion

Major corpus expansion should begin only after:

- canonical contracts are stable;
- source viability rules are established;
- refresh and reconcile are repeatable;
- the next retrieval model is selected;
- retrieval generations are versioned;
- Qdrant serving is operationalized;
- validators and rollback are practical at larger scale.

Target expansion then becomes a controlled lifecycle:

```text
ingest
→ normalize
→ align and reconcile
→ validate candidate corpus
→ build features and graphs
→ encode retrieval generation
→ build candidate Qdrant collection
→ evaluate
→ promote
→ retain rollback generation
```

At that point scale is an operational process rather than an architecture
experiment.

---

## 13. Similar-paper serving

Similar-paper search already uses embeddings, but it is a different contract
from text-query search.

Current flow:

```text
paper embedding
→ file nearest-neighbour search
→ self-exclusion
→ semantic or radar-adjusted ordering
```

Potential future flow:

```text
paper embedding
→ Qdrant nearest-neighbour search
→ self-exclusion
→ existing ordering and enrichment
```

Migration must remain a separate slice because it requires:

- paper-vector input semantics;
- mandatory self-exclusion;
- different evaluation data;
- separate minimum-similarity behavior;
- separate product and latency evidence.

It should be performed only when measured benefits justify it.

---

## 14. Orchestration strategy

Orchestration should be introduced when the pipeline has become a recurring
operational system.

Airflow or another orchestrator is justified when:

- runs are scheduled;
- stages have explicit dependencies;
- retry and resume are needed;
- run history matters;
- manual command sequencing becomes unsafe;
- multiple environments or workers are involved.

Before those triggers:

```text
CLI commands + manifests + validators + explicit promotion
```

remain simpler and more transparent.

Orchestration may be introduced before the final large-scale load if it is
needed to make the scale rehearsal and recurring refresh reproducible.

---

## 15. Kafka strategy

Kafka is not a default requirement for paper ingestion.

It is justified when:

- source updates arrive continuously;
- near-real-time indexing is required;
- several independent consumers need the same events;
- replay is valuable;
- event volume and update frequency exceed comfortable batch operation.

For daily or weekly batch refresh:

```text
scheduled batch pipeline
```

may remain the correct design.

---

## 16. Kubernetes and distributed serving

Kubernetes becomes useful when the deployment contains independently scalable
services such as:

- API workers;
- Qdrant;
- Postgres;
- ingestion workers;
- embedding workers;
- orchestration components;
- monitoring and tracing services.

Practical triggers:

- replicas;
- rolling deployment;
- independent resource limits;
- automated recovery;
- multiple environments;
- stable production-like workload.

Kubernetes should not be introduced merely to make the stack look more
advanced.

---

## 17. Scale gates

### Gate 1 — MVP semantics

Required:

- stable canonical identity;
- stable retrieval and ranking semantics;
- reproducible refresh;
- quality evaluation;
- explicit failure and promotion behavior.

### Gate 2 — retrieval generation

Required:

- selected embedding model;
- exact file reference;
- validated Qdrant collection;
- Golden Set and hybrid evidence.

### Gate 3 — medium-scale rehearsal

Required:

- measured build and serving costs;
- practical validator duration;
- successful rollback;
- known bottlenecks.

### Gate 4 — Qdrant operationalization

Required:

- deployment selector;
- readiness and failures;
- reload/recovery;
- file rollback;
- full regression in both deployment modes.

### Gate 5 — large corpus promotion

Required:

- candidate corpus passes identity and provenance checks;
- retrieval generation passes quality gates;
- serving collection passes compatibility and performance gates;
- promotion and rollback are explicit.

---

## 18. Decision triggers

Do not use one arbitrary paper-count threshold.

Use combined evidence:

```text
vector RAM
exact-search latency
query concurrency
embedding dimension
update frequency
rebuild duration
validator duration
deployment topology
```

Typical triggers for Qdrant primary serving:

- file vectors no longer fit comfortably in each API worker;
- exact search exceeds latency goals;
- concurrent search becomes a bottleneck;
- incremental indexing is required;
- API and vector storage must scale separately;
- vector filtering is needed;
- multiple large embedding generations coexist.

---

## 19. Anti-goals

The strategy explicitly rejects:

- scaling the corpus only to advertise a large number;
- introducing Kafka without event-driven requirements;
- introducing Kubernetes without deployment requirements;
- replacing file reference artifacts entirely;
- hiding Qdrant failure behind silent fallback;
- changing embeddings and scaling the corpus in one unmeasured step;
- mutating accepted stable data during scale experiments;
- bypassing quality gates to accelerate ingestion;
- allowing infrastructure complexity to outrun project ownership.

---

## 20. Immediate decision

The immediate project decision is:

```text
Do not implement the deployment selector in the current heavy dialogue.
Do not begin major corpus expansion yet.
Keep Qdrant as a validated future serving backend.
Continue functional MVP work on the current corpus.
Return to Qdrant operationalization after the next retrieval-generation and
medium-scale planning are clearer, but before large-scale expansion.
```

This decision should be revisited when one or more scale triggers become real.

---

## 21. Guiding principle

```text
First make the system semantically stable and reproducible.
Then rehearse scale.
Then operationalize the scalable serving path.
Then grow the corpus aggressively.
```
