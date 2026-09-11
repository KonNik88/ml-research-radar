# Scientific Entity Fresh Held-Out Immutable Acceptance Decision v0.2

## Purpose

This slice closes the independent v0.2c fresh-heldout experiment by applying the pre-frozen acceptance gate to the already-validated immutable evaluation artifact.

It does **not** rerun inference, reapply policy, recompute evaluation, tune thresholds, change prompts, change the gate, mutate canonical truth, select a production extractor, or authorize a full-corpus build.

## Frozen lineage

```text
candidate_id = scientific-entity-semantic-prompt-raw-floor-extension-v0.2c
sample_id = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z
review_id = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z
policy_build_id = scientific-entity-semantic-prompt-raw-floor-policy-fresh-v0.2c-20260901T130232963026Z
policy_extractor_fingerprint = 77af105871b227daa0d8c9e5501839addf229004795490a63bebe4f02672cf52

documents = 48
references = 944
predictions = 773

evaluation_id = scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z
gate_config_sha256 = 353276e75adacf445146bdc3046fdaedc04e01588b0bbd76a11a5dc2b48a1efe
decision_id = scientific-entity-fresh-heldout-acceptance-decision-v0.2c-20260901T130232963026Z
```

The decision contract additionally pins the semantic evaluation-config SHA and exact SHA-256 values of the immutable evaluation manifest, metrics, errors, and checksum files before decision execution.

## PLAN boundary

PLAN validates exact candidate/sample/review/policy/evaluation/gate lineage, expected counts, immutable evaluation file hashes, strict evaluation validity, and absence of an already-materialized decision.

PLAN does not compute or materialize the decision.

Observed PLAN state before execution:

```text
mode = plan
phase_complete = false
one_shot_already_executed = false
plan_runs_decision = false
decision_materialized = false
evaluation_recomputed = false
model_inference_executed = false
policy_reapplied = false
threshold_tuning_executed = false
gate_changed = false
canonical_truth_mutated = false
production_extractor_selected = false
full_corpus_build_authorized = false
next = execute_immutable_v02c_acceptance_decision_once
```

## EXECUTE semantics

EXECUTE repeats all lineage and safety checks, compares the immutable observed evaluation values with the pre-frozen criteria, and writes exactly one immutable decision artifact.

Overwrite is forbidden. A second EXECUTE fails closed.

Each criterion is materialized machine-readably with:

```text
name
observed
operator
threshold
hard
passed
```

Overall decision rule:

```text
all hard criteria pass -> ACCEPT
any hard criterion fails -> REJECT
```

The desirable relaxed-F1 target is recorded separately and cannot override a hard failure.

## Materialized decision

```text
decision = reject_v02c_independent_acceptance

hard criteria passed = 2 / 6
desirable criteria passed = 1 / 1
```

Criterion outcome:

| criterion | observed | requirement | role | result |
|---|---:|---:|---|---|
| minimum exact F1 | `0.399534` | `>= 0.396882` | hard | PASS |
| maximum model→method count | `70` | `<= 43` | hard | FAIL |
| maximum method→task count | `15` | `<= 25` | hard | PASS |
| maximum total type mismatch count | `166` | `<= 150` | hard | FAIL |
| maximum method semantic sink count | `84` | `<= 74` | hard | FAIL |
| maximum any predicted-type mismatch sink count | `84` | `<= 74` | hard | FAIL |
| desirable minimum relaxed F1 | `0.42516` | `>= 0.414868` | desirable | PASS |

Failed hard criteria:

```text
maximum_model_to_method_count
maximum_total_type_mismatch_count
maximum_method_semantic_sink_count
maximum_any_predicted_type_mismatch_sink_count
```

## Independent strict validation

The materialized decision was independently validated after the one-shot EXECUTE:

```text
decision_materialized = true
decision = reject_v02c_independent_acceptance
criterion_count = 7
hard_criteria_count = 6
hard_criteria_passed_count = 2
desirable_criteria_count = 1
desirable_criteria_passed_count = 1
total_checks = 39
required_failed_count = 0
```

A correct REJECT is intentionally engineering-green. Quality-gate failure and artifact/lineage validation failure are different concepts.

## Scientific interpretation

The v0.2c candidate retained acceptable overall exact-span quality under the frozen F1 floor, and its desirable relaxed-F1 target also passed. However, independent generalization did not preserve the pre-frozen semantic typing constraints.

The dominant signal is semantic type discrimination rather than a simple global span-recall collapse:

```text
model -> method = 70
method sink = 84
total type mismatch = 166
```

Therefore the correct bounded conclusion is:

```text
REJECT scientific-entity v0.2c as an independently accepted candidate
under the pre-frozen fresh-heldout acceptance gate.
```

This does not imply that GLiNER, entity extraction, or the Scientific Entity Evidence line failed as a whole. It means this specific frozen v0.2c candidate is not independently accepted under the gate defined before fresh metrics were revealed.

## Safety outcome

```text
evaluation recomputed = false
model inference executed = false
policy reapplied = false
threshold tuning executed = false
gate changed = false
canonical truth mutated = false
production extractor selected = false
full-corpus build authorized = false
```

## Next research slice

The formal v0.2c experiment is closed. The next bounded research direction is typing-focused diagnostics followed by v0.3 design hardening.

Once the 48 fresh-heldout papers are inspected for error analysis, they become consumed diagnostic/development evidence. They must never again be used as independent acceptance evidence for a candidate influenced by those diagnostics.

Any future v0.3 candidate requires a new disjoint prediction-blind held-out for independent acceptance.
