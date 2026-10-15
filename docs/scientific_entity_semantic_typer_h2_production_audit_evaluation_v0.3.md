# Scientific Entity H2 v0.3 — Production Audit Unblind / Evaluation

## Scope

This slice is the first step allowed to unblind the H2 production audit. It consumes only already frozen/validated artifacts:

- the immutable prediction-blind 240-case audit sample;
- the immutable frozen human reference;
- the already built and strictly validated H2 full-corpus candidate.

It does **not** run model inference, retune H2, revise the policy, mutate the candidate, mutate canonical truth, make the separate promotion decision, or overwrite production `latest`.

## PLAN versus EXECUTE

PLAN is intentionally still non-unblinding. It validates the parent identities and frozen reference, but does not read `final_mentions.jsonl`, reconstruct sampled strata, expose quality metrics, or write output.

EXECUTE is one-shot. Only after the frozen reference is verified does it read `final_mentions.jsonl`, reconstruct the exact deterministic sample under the frozen 8D-A seeds, prove that the resulting 240 `audit_case_id` values equal the immutable blind sample, join the frozen human labels, and evaluate the preregistered gates.

## Frozen strata

The deterministic sample must reconstruct exactly:

- 100 `override` cases (`method -> model`);
- 100 `preserved_method` non-fallback cases;
- 40 `fallback_method` cases.

Any mismatch is a hard evaluation error.

## Denominators

The 8D-A preregistration fixed the numerical gates before annotation, but its prose did not explicitly name the denominator for the per-type model/method rates. This evaluator removes that implementation ambiguity without changing any threshold:

- `usable` = `valid_entity_span` or `boundary_issue`;
- override/preserved model/method reference rates use **usable cases only** as denominator;
- overall `uncertain` and `not_an_entity` rates use all 240 audit cases;
- fallback (`uncertain` + `not_an_entity`) rate uses all 40 fallback cases;
- boundary issues remain diagnostic-only and stay usable for semantic typing because a reference type is present.

## Preregistered hard gates

Exactly the 8D-A thresholds are evaluated:

- overall uncertain rate <= 10%;
- overall `not_an_entity` rate <= 15%;
- override: usable >= 80, model rate >= 45%, method rate <= 30%, model-minus-method >= 15 percentage points;
- preserved method: usable >= 80, method rate >= 50%, model rate <= 30%;
- fallback: usable >= 30, (`uncertain` + `not_an_entity`) rate <= 25%.

There are 11 hard gates. No threshold may be changed after annotation.

## Outputs

The immutable package contains:

- `case_evaluations.jsonl` — unblinded case-level lineage, human reference, H2 decision and descriptive correctness;
- `summary.json` — overall and per-stratum metrics;
- `gate_results.json` — exact 11 frozen gate results and PASS/FAIL gate verdict;
- `manifest.json` — lineage, safety flags and parent hashes;
- `README.md`;
- `checksums.txt`.

A PASS here is **evaluation evidence**, not production authorization. A separate immutable promotion decision slice must consume the validated evaluation next.

## Safety

Always preserve:

```text
model_inference_executed = false
threshold_tuning_executed = false
policy_revision_executed = false
candidate_mutated = false
canonical_truth_mutated = false
promotion_decision_made = false
production_latest_promotion_authorized = false
latest_overwritten = false
```

If the semantic gates fail, the evaluation artifact is still structurally valid evidence. The candidate must not be tuned on these 240 consumed cases and re-tested as if independent.
