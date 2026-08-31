# Scientific Entity Fresh v0.2 Held-Out Gate

## Status

```text
status = design frozen
candidate = semantic-prompt raw-floor v0.2c development freeze
sample selected = false
fresh held-out consumed = false
model inference executed = false
evaluation executed = false
production extractor selected = false
full-corpus build authorized = false
next = materialize prediction-blind fresh held-out sample v0.2
```

## Purpose

This contract freezes the independent acceptance gate for the already-frozen
Scientific Entity v0.2c development candidate **before** a new held-out sample
is selected, annotated, or scored.

The current 72-paper development pool is consumed evidence for v0.2 because it
contains both the original 24-paper DEV set and the former 48-paper v0.1 held-out
set that was subsequently used for v0.2 error analysis and design.

The new held-out must therefore be disjoint from all 72 papers.

## Candidate under test

The candidate is immutable:

```text
candidate_id = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
raw floor = 0.40
title threshold = 0.45
abstract threshold = 0.625
entity-type overrides = none

development comparison =
scientific-entity-semantic-prompt-raw-floor-comparison-v0.2c-20260830T110628936475Z

development policy build =
scientific-entity-semantic-prompt-raw-floor-policy-v0.2c-20260830T105318817514Z
```

Prompts, pinned GLiNER model/revision/artifact, adapter windowing, six entity
types, matching semantics, and policy thresholds are frozen. No candidate choice
may be revisited after the new held-out is viewed.

## Sampling contract

Reuse the existing prediction-blind held-out sampling design rather than invent
a second framework:

```text
documents = 48
uniform = 24
type-enriched = 24
type-enriched per entity type = 4
source fields = title + abstract
annotation rows = 96
candidate pool per stratum = 512
```

Selection uses a new deterministic v0.2 seed and excludes all canonical IDs from
the immutable 72-paper development package.

The six lexical enrichment strata remain:

- task
- method
- dataset
- metric
- model
- domain

Candidate predictions are forbidden during sampling and annotation.

## Reference-freeze contract

The blank annotation package must be materialized before candidate inference.

Manual review remains prediction-blind and uses the existing
`scientific_entity_annotation_guidelines_v0.1` semantics.

Before any model run, the reference package must prove:

```text
document count = 48
annotation rows = 96
development overlap = 0
all annotation rows complete = true
unresolved uncertain mentions = 0
minimum reference mentions per type = 20
prediction blind = true
exact sample identity frozen = true
```

If the frozen sample is not reference-adequate, candidate inference still must
not run. Any remediation must follow a separately explicit, prediction-blind
rule rather than selecting papers based on model behavior.

## Frozen acceptance gate

Hard quality floor:

```text
exact F1 >= 0.396882
```

This is the exact F1 from the original independent v0.1 held-out gate and is
already the historical independent quality floor used during v0.2 development.

Relaxed F1:

```text
desirable relaxed F1 >= 0.414868
```

It remains a desirable diagnostic rather than a newly introduced hard gate.

Hard semantic guardrails on the same 48-paper scale:

```text
model -> method <= 43
method -> task <= 25
total type mismatches <= 150
method semantic sink <= 74
maximum any predicted-type mismatch sink <= 74
```

Acceptance requires sample adequacy, the exact-F1 floor, and all semantic
guardrails.

No per-type F1 floor is introduced because the existing v0.1 evidence shows
material type heterogeneity, especially for `metric` and `domain`.

## Decision semantics

If every hard gate passes:

```text
decision = accept_as_independently_validated_bounded_extractor_v0.2
```

This still does **not** select a production extractor or authorize a full-corpus
build. Those remain separate future decisions.

If any hard gate fails:

```text
decision = reject_v02c_independent_acceptance
```

The new held-out then becomes consumed development/error-analysis evidence.
v0.2c must not be tuned on it and re-declared accepted on the same sample.
Any future candidate would require another new independent held-out for
acceptance.

## Frozen execution order

```text
contract freeze
-> materialize deterministic 48-paper sample
-> validate zero overlap / blank prediction-blind package
-> manual annotation
-> freeze immutable references
-> run frozen v0.2c raw inference exactly once
-> validate raw build
-> apply frozen .45/.625 policy without tuning
-> validate policy build
-> evaluate once
-> immutable ACCEPT / REJECT decision
```

## Safety boundary

This design slice performs no sample selection, candidate inference, evaluation,
canonical mutation, production promotion, or full-corpus materialization.
