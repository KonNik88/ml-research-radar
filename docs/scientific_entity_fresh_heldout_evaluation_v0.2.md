# Scientific Entity Fresh Held-Out Independent Evaluation v0.2

## Purpose

This slice performs the first and only quality evaluation of the frozen v0.2c candidate on the prediction-blind fresh held-out.

Frozen evidence entering the slice:

```text
sample = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z
review = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z
documents = 48
references = 944

policy build = scientific-entity-semantic-prompt-raw-floor-policy-fresh-v0.2c-20260901T130232963026Z
selected predictions = 773
policy extractor fingerprint = 77af105871b227daa0d8c9e5501839addf229004795490a63bebe4f02672cf52

title threshold = 0.45
abstract threshold = 0.625
entity-type overrides = none
```

The frozen acceptance design remains external input evidence. This slice computes evaluation evidence but does not emit the final ACCEPT/REJECT decision.

## PLAN semantics

PLAN validates all frozen lineage before held-out quality is revealed:

- fresh-heldout gate semantic SHA and exact gate values;
- immutable 944-reference package and its strict validation;
- immutable 773-prediction frozen-policy build and its strict validation;
- base Scientific Entity Evaluation Harness v0.1 semantic SHA;
- fixed one-shot evaluation ID and absence/presence of its output directory.

PLAN **must not call the evaluator** and therefore does not expose exact/relaxed metrics or semantic confusion counts.

## EXECUTE semantics

EXECUTE invokes the existing Scientific Entity Evaluation Harness v0.1 exactly once with:

```text
documents = <sample_dir>/canonical_documents.sample.jsonl
references = <reference_dir>/reference_mentions.jsonl
predictions = <policy_build>/mentions.jsonl
status = candidate
max_documents = 48
```

The existing harness produces deterministic exact and relaxed matching, per-type metrics, matches and structural errors. Its independent validator then recomputes the artifact before the wrapper reports any quality values.

The wrapper additionally derives, from immutable `errors.jsonl`, the pre-frozen semantic guardrail inputs:

```text
model -> method count
method -> task count
total type mismatch count
method predicted-type mismatch sink
maximum predicted-type mismatch sink
```

These are evaluation measurements only. No threshold, prompt, model, taxonomy or sample change is allowed after they become visible.

## Frozen gate snapshot

```text
hard exact F1 floor = 0.396882
model -> method <= 43
method -> task <= 25
total type mismatch <= 150
method semantic sink <= 74
maximum predicted-type mismatch sink <= 74

relaxed F1 >= 0.414868 = desirable, not hard
```

No gate decision is made in this slice. The next slice consumes only this immutable evaluation artifact plus the already-frozen gate and emits the deterministic decision without tuning.

## Executed evaluation result

The fresh-heldout evaluation was executed exactly once after the PLAN boundary
confirmed that no quality metric had yet been exposed.

```text
evaluation_id = scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z

documents = 48
references = 944
predictions = 773

exact precision = 0.443726
exact recall = 0.363347
exact F1 = 0.399534

relaxed precision = 0.472186
relaxed recall = 0.386653
relaxed F1 = 0.42516

model -> method = 70
method -> task = 15
total type mismatch = 166
method predicted-type mismatch sink = 84
maximum predicted-type mismatch sink = method:84

base evaluation validation = 69 / 69
wrapper strict validation = 19 / 19
required failures = 0

evaluation executed = true
acceptance decision made = false
threshold tuning executed = false
model inference executed = false
canonical truth mutated = false
production extractor selected = false
full-corpus build authorized = false
```

For reference, the already-frozen gate values are:

```text
exact F1 >= 0.396882
model -> method <= 43
method -> task <= 25
total type mismatch <= 150
method semantic sink <= 74
maximum predicted-type mismatch sink <= 74

relaxed F1 >= 0.414868 = desirable, not hard
```

This evaluation evidence itself does not emit the final decision. The next slice
must consume these immutable measurements and the frozen gate exactly as written,
without any post-heldout tuning.

## Safety boundary

```text
new model inference = false
threshold tuning = false
reference labels used for evaluation = true
reference labels used for filtering = false
acceptance decision = false
canonical mutation = false
production extractor selection = false
full-corpus authorization = false
```

## Next slice

Strict evaluation validation is complete. The next bounded slice is:

```text
next = make_immutable_v02c_acceptance_decision_without_tuning
```

## Successor immutable acceptance decision

This evaluation slice remains historically unchanged: it computed evidence and did not itself make the acceptance decision.

The subsequent bounded acceptance-decision slice consumed this immutable evaluation artifact plus the already-frozen gate and materialized exactly one decision:

```text
decision_id = scientific-entity-fresh-heldout-acceptance-decision-v0.2c-20260901T130232963026Z
decision = reject_v02c_independent_acceptance

hard criteria passed = 2 / 6
desirable criteria passed = 1 / 1

failed hard criteria =
- maximum_model_to_method_count
- maximum_total_type_mismatch_count
- maximum_method_semantic_sink_count
- maximum_any_predicted_type_mismatch_sink_count

strict decision validation = 39 / 39
required_failed_count = 0
```

The exact-F1 hard floor and method→task hard cap passed. The relaxed-F1 target also passed, but it is desirable rather than hard. The candidate was rejected because four pre-frozen semantic typing hard constraints failed. A valid REJECT is a scientific outcome, not an engineering validator failure.

No evaluation recomputation, model inference, policy reapplication, threshold tuning, gate change, canonical mutation, production selection, or full-corpus authorization occurred during decision materialization.

Current follow-on:

```text
next = typing_focused_diagnostics_and_v03_design_hardening
```

If the fresh 48-paper errors are inspected for future candidate design, this held-out becomes consumed diagnostic/development evidence and cannot be reused as independent v0.3 acceptance evidence.
