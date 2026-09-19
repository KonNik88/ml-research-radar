# Scientific Entity Semantic Typer v0.3 — Frozen H2 Candidate

## Purpose

Freeze the development-selected H2 selective override policy before creating or inspecting any new independent held-out.

The frozen candidate is:

- parent semantic typer: H1 target-focused six-label semantic rescoring;
- baseline default: frozen v0.2c type;
- only permitted override: `baseline=method` and semantic typer=`model`;
- override threshold: `score_margin >= 0.10`;
- otherwise preserve the baseline type.

## Provenance

H1 unconditional retyping was rejected. A deterministic revision analysis over already-consumed development evidence selected the H2 threshold from the first stable three-point gate-passing plateau `[0.05, 0.10, 0.15]`.

The freeze consumes the immutable revision-analysis package and the frozen H1 semantic-typer config. It records cryptographic hashes and a semantic candidate fingerprint.

## What this slice does not do

It performs no:

- model inference;
- threshold tuning;
- policy revision;
- span mutation;
- taxonomy change;
- canonical truth mutation;
- production selection;
- full-corpus extraction;
- independent acceptance evaluation.

## Required next step

After the candidate freeze validates, create a **new disjoint prediction-blind held-out**. The frozen H2 policy, including the `0.10` threshold, must not be changed in response to that held-out. Any change would define another candidate and require another independent held-out.
