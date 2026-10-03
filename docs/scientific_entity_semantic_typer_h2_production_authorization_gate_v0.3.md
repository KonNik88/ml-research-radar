# Scientific Entity Semantic Typer H2 v0.3 — Production Authorization Gate

## Purpose

This slice starts only after the immutable independent H2 acceptance decision has been made and strictly validated.
It does **not** execute extraction and it does **not** authorize production by itself.

Its role is to preregister the boundary for the next phase so that the accepted held-out result cannot silently become a full-corpus overwrite.

## Accepted upstream evidence

The gate is bound to:

- candidate: `scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method`
- candidate fingerprint: `6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966`
- immutable decision: `scientific-entity-semantic-typer-h2-independent-acceptance-decision-v0.3-20260927T102527705827Z`
- required decision: `accept_h2_as_independently_validated_bounded_semantic_typing_intervention`
- decision validation: 24 checks, 0 required failures

The accepted H2 intervention remains exactly:

```text
if baseline_type == method
AND semantic_typer_type == model
AND score_margin >= 0.10:
    final_type = model
else:
    final_type = baseline_type
```

No span repair, split/merge, new-span generation, taxonomy changes, threshold tuning, or policy revision are part of this accepted candidate.

## What this gate does not authorize

This slice explicitly does not:

- run model inference;
- run full-corpus Scientific Entity extraction;
- read human held-out reference mentions as production features;
- mutate canonical paper truth;
- overwrite an entity `latest` materialization;
- select a production extractor;
- authorize full-corpus candidate execution;
- authorize promotion of a candidate build to `latest`;
- authorize publication.

## Future production authorization boundary

A later one-shot authorization record may authorize only a **timestamped candidate materialization**.
Before that decision is executed it must bind:

1. the exact accepted H2 fingerprint;
2. the exact frozen H2 policy;
3. the exact canonical input snapshot;
4. canonical input SHA-256 and document count;
5. an immutable build ID/output directory;
6. no use of held-out labels for filtering/tuning;
7. no overwrite of existing trusted entity materialization.

A successful authorization still will **not** promote the candidate build to `latest`.

The intended sequence is:

```text
accepted H2 evidence
→ production authorization gate (this slice)
→ immutable one-shot authorization record
→ timestamped full-corpus candidate entity build
→ strict candidate validation / audit
→ separate promotion decision
→ only then, explicit latest promotion
```

This mirrors the project-wide safety rule:

```text
latest = trusted state
candidate = untrusted until checked
promotion = explicit action
```

## Why the canonical snapshot is bound later

The independent H2 acceptance proves the bounded semantic intervention, not a specific future corpus snapshot.
The actual production authorization must therefore fingerprint the canonical input present at authorization time and bind the candidate build to that exact snapshot.

This gate deliberately does not guess or hard-code a canonical corpus SHA-256.

## Next slice

After strict validation of this preregistration:

`build_h2_production_authorization_record_tooling`

That later slice may create an immutable authorization record, but the present gate remains non-executing and non-authorizing.
