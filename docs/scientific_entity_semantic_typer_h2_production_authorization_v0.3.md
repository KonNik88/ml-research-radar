# Scientific Entity Semantic Typer H2 v0.3 — Production Candidate-Build Authorization

## Purpose

This slice records one immutable, content-bound authorization to build a **timestamped full-corpus candidate** using the independently accepted H2 bounded semantic typing intervention.

It is deliberately narrower than production promotion.

## Preconditions

The authorization requires:

- the accepted H2 candidate and exact fingerprint;
- the validated immutable independent acceptance decision;
- the validated production-authorization preregistration gate;
- the frozen H2 intervention policy unchanged;
- an explicit current canonical JSONL snapshot;
- the exact canonical SHA-256 and document count computed before authorization.

The authorization ID is deterministic from the canonical snapshot SHA-256 prefix plus the accepted candidate fingerprint prefix. A changed canonical snapshot therefore requires a different authorization record.

## Authorized action

Exactly one future materialization may be authorized:

```text
exact bound canonical snapshot
+ accepted frozen H2 candidate
-> one timestamped derived full-corpus candidate build
```

The future builder must re-check the authorization record and refuse to run if the canonical SHA-256, candidate fingerprint, or frozen H2 policy differs.

## Not authorized

This slice does not:

- run semantic-typer inference;
- perform full-corpus extraction;
- read held-out human reference mentions;
- tune the H2 threshold;
- revise the H2 policy;
- mutate canonical truth;
- overwrite any trusted latest entity build;
- promote a candidate to production latest;
- authorize publication.

## Execution discipline

1. Run PLAN on merged tooling.
2. Confirm the current canonical path, SHA-256, document count, candidate fingerprint, and green upstream gate.
3. Commit/merge tooling before execute.
4. Execute the authorization exactly once.
5. Strictly validate the immutable authorization package.
6. Only then implement the separate full-corpus candidate materialization slice.

## Output

The immutable package contains:

- `authorization.json`
- `manifest.json`
- `README.md`
- `checksums.txt`

The authorization itself permits candidate materialization only. Candidate validation and a separate production promotion decision remain mandatory.
