# Scientific Entity Typing Diagnostics v0.3

## Purpose

This slice prepares deterministic, reviewable semantic-typing diagnostics from the formally rejected fresh v0.2c held-out evidence.

It is an **analysis-only preparation layer**. It does not assign root causes automatically and does not select or tune a v0.3 model.

The slice consumes the fresh held-out only after the immutable acceptance decision explicitly marked it as consumed development evidence and required any future influenced candidate to use a new independent held-out.

## Frozen lineage

```text
evaluation_id = scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z
decision_id = scientific-entity-fresh-heldout-acceptance-decision-v0.2c-20260901T130232963026Z
decision = reject_v02c_independent_acceptance
analysis_id = scientific-entity-typing-diagnostics-v0.3-20260912T122700872330Z

documents = 48
references = 944
predictions = 773

evaluation_manifest_sha256 = 59209b0897aeaea07c71209f5031f4f136ff097af0e42ea31c3c79c07d92b00b
evaluation_errors_sha256 = 8bc7c726a70b3d6ecd4605270bbaa7c902d9f260c7b30c238268dbef5268cca7
```

The preparation also verifies the exact sample, reference-mention, and prediction-mention files against the hashes recorded by the immutable evaluation lineage.

## PLAN boundary

PLAN validates the pinned rejected decision, immutable evaluation hashes, exact source artifacts, and expected counts. It computes diagnostics in memory but writes no output package.

Observed PLAN:

```text
mode = plan
phase_complete = false
analysis_id = scientific-entity-typing-diagnostics-v0.3-20260912T122700872330Z
type_mismatch_count = 166
same_span_type_mismatch_count = 131
same_span_type_mismatch_share = 0.789157
model_to_method_count = 70
method_to_task_count = 15
method_sink_count = 84
maximum_sink_type = method
maximum_sink_count = 84
high_confidence_at_0_8_count = 85
high_confidence_at_0_9_count = 51
root_causes_assigned = false

model_inference_executed = false
threshold_tuning_executed = false
policy_reapplied = false
evaluation_recomputed = false
canonical_truth_mutated = false
production_extractor_selected = false
full_corpus_build_authorized = false

next = execute_typing_diagnostics_preparation_once
```

The planned output directory was confirmed absent before EXECUTE.

## One-shot EXECUTE

EXECUTE materialized exactly one immutable diagnostic-preparation package:

```text
data/entities/scientific_entity_typing_diagnostics/v0.3/
└── scientific-entity-typing-diagnostics-v0.3-20260912T122700872330Z/
    ├── manifest.json
    ├── summary.json
    ├── confusion_matrix.json
    ├── typing_cases.jsonl
    ├── review_template.jsonl
    ├── README.md
    └── checksums.txt
```

The builder fails closed if the target analysis directory already exists.

Observed EXECUTE:

```text
mode = execute
phase_complete = true
analysis_id = scientific-entity-typing-diagnostics-v0.3-20260912T122700872330Z
type_mismatch_count = 166
same_span_type_mismatch_count = 131
same_span_type_mismatch_share = 0.789157
model_to_method_count = 70
method_to_task_count = 15
method_sink_count = 84
maximum_sink_type = method
maximum_sink_count = 84
high_confidence_at_0_8_count = 85
high_confidence_at_0_9_count = 51
root_causes_assigned = false
next = review_typing_cases_and_assign_root_causes
```

## Diagnostic result

```text
type mismatches = 166
same-span type mismatches = 131
same-span share = 0.789157
model -> method = 70
method -> task = 15
method sink = 84
maximum predicted-type sink = method:84
confidence >= 0.8 = 85
confidence >= 0.9 = 51
root causes assigned = false
```

The strongest immediate signal is that most type mismatches are not primarily boundary mismatches: `131 / 166` use exactly the same reference and prediction span.

High-confidence semantic errors are also material. This makes another threshold-only adjustment an insufficient default explanation, but it does **not** by itself prove which v0.3 architecture should be selected.

## Human-review template

`review_template.jsonl` preserves factual evidence for every diagnostic case and leaves interpretation fields empty.

Prepared factual fields include:

```text
diagnostic_case_id
error_id
confusion_pair
reference_surface
prediction_surface
source_excerpt
reference_entity_type
prediction_entity_type
prediction_confidence_score
```

Human-review fields begin unassigned:

```text
review_status = pending
root_cause = null
reference_type_confirmed = null
prediction_type_plausible = null
ambiguity_level = null
recommended_action = null
review_notes = null
```

Allowed root-cause labels are frozen in config:

```text
clear_semantic_mistyping
taxonomy_boundary_ambiguity
annotation_reference_issue
compound_or_nested_entity
insufficient_context
other
```

Allowed recommended-action labels are:

```text
prompt_or_label_definition
second_stage_typer
ambiguity_rejection
annotation_guideline
span_handling
no_change
other
```

These labels are a review vocabulary, not automatically inferred conclusions.

## Independent strict validation

The materialized package passed strict validation:

```text
analysis_id = scientific-entity-typing-diagnostics-v0.3-20260912T122700872330Z
type_mismatch_count = 166
same_span_type_mismatch_count = 131
model_to_method_count = 70
method_to_task_count = 15
method_sink_count = 84
root_causes_assigned = false
strict validation = 33 / 33
required_failed_count = 0
next = review_typing_cases_and_assign_root_causes
```

## Safety outcome

```text
analysis_only = true
model inference executed = false
threshold tuning executed = false
policy reapplied = false
evaluation recomputed = false
canonical truth mutated = false
production extractor selected = false
full-corpus build authorized = false
```

No public runtime behavior changes.

## Scientific interpretation

The preparation strengthens the earlier diagnosis that semantic typing is the immediate bottleneck:

- `model -> method = 70` remains the dominant named confusion;
- `method` remains the largest predicted-type mismatch sink at `84`;
- `131 / 166` mismatches are exact same-span type disagreements;
- `85` mismatches have confidence at least `0.8`, and `51` at least `0.9`.

However, **root causes assigned = false** is an intentional boundary. The preparation does not decide whether the correct intervention is prompt/label redesign, a second-stage typer, ambiguity rejection, annotation-guideline repair, span handling, an alternative extractor, or no change for a specific case.

That decision belongs after explicit human review.

## Next slice

```text
next = review_typing_cases_and_assign_root_causes
after review = design_one_bounded_v03_typing_hypothesis
```

The next slice must review all prepared cases under a fixed contract and summarize the root-cause/action distribution before any new model or threshold experiment is selected.

The 48-paper fresh held-out is now consumed diagnostic/development evidence. Any v0.3 candidate influenced by this evidence requires a **new disjoint prediction-blind held-out** for independent acceptance.
