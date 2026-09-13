# Scientific Entity Typing Root-Cause Review v0.3

## Purpose

This slice adds the human-review infrastructure that sits between the completed
fresh-v0.2c typing-diagnostics preparation package and the future v0.3 design
decision.

It does **not** rediscover that semantic typing is the dominant failure mode.
That conclusion was already established earlier. Its job is to turn the 166
materialized fresh-v0.2c type-mismatch cases into a controlled human root-cause
review with immutable factual lineage.

## Parent evidence

Pinned parent:

```text
analysis_id = scientific-entity-typing-diagnostics-v0.3-20260912T122700872330Z
evaluation_id = scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z
decision_id = scientific-entity-fresh-heldout-acceptance-decision-v0.2c-20260901T130232963026Z

type mismatches = 166
same-span type mismatches = 131
model -> method = 70
method -> task = 15
method sink = 84
```

The review tooling pins exact SHA-256 values for the parent diagnostic
`manifest.json`, `summary.json`, `typing_cases.jsonl`, and
`review_template.jsonl`.

The parent 48-paper fresh-heldout is already consumed diagnostic/development
evidence. It is not independent acceptance evidence for any future v0.3
candidate influenced by this review.

## Working-copy semantics

The `prepare` phase validates the parent diagnostic package and creates one
mutable review directory:

```text
working_manifest.json
review_working.jsonl
REVIEW_GUIDE.md
```

`review_working.jsonl` is enriched from `typing_cases.jsonl`, not from the
smaller display-oriented parent template. Therefore every row retains:

```text
diagnostic_case_id
error_id
evaluation_id
canonical_id
source_field
reference_id
prediction_evidence_id
reference/prediction entity types
confusion pair
pair count/rank
reference/prediction offsets
char IoU
same-span flag
reference/prediction surfaces
source excerpt
prediction confidence
high-confidence flags
```

All of those fields are immutable during human review.

The only editable fields are:

```text
review_status
root_cause
reference_type_confirmed
prediction_type_plausible
ambiguity_level
recommended_action
review_notes
```

Partial review is allowed. Pending rows remain valid as long as all structured
review fields remain null.

## Frozen review vocabulary

Root causes:

```text
clear_semantic_mistyping
taxonomy_boundary_ambiguity
annotation_reference_issue
compound_or_nested_entity
insufficient_context
other
```

Ambiguity:

```text
none
low
medium
high
```

Recommended action:

```text
prompt_or_label_definition
second_stage_typer
ambiguity_rejection
annotation_guideline
span_handling
no_change
other
```

These per-case recommended actions are diagnostic labels only. They do not
automatically select the v0.3 architecture.

## Validation semantics

The working-copy validator:

- revalidates the exact parent package;
- checks pinned parent SHA-256 values;
- validates every row against the frozen schema;
- preserves exact row count and row order;
- rejects factual-field mutation;
- permits `0..166` completed rows;
- reports complete and pending counts.

Finalization is fail-closed until all `166 / 166` rows are complete.

## Finalization semantics

After full human review, `finalize` writes one immutable package:

```text
manifest.json
summary.json
reviewed_cases.jsonl
root_cause_breakdown.json
README.md
checksums.txt
```

The final breakdown includes:

- overall root-cause counts;
- recommended-action counts;
- ambiguity-level counts;
- reference types not confirmed;
- plausible prediction-type count;
- root cause by confusion pair;
- root cause by predicted-type sink;
- same-span versus different-span root causes;
- high-confidence root-cause subsets.

The finalizer does not select a model or candidate automatically.

## Safety boundary

```text
human review only = true
model inference = false
threshold tuning = false
policy reapplication = false
evaluation recomputation = false
canonical mutation = false
production extractor selection = false
full-corpus authorization = false
automatic root-cause assignment = false
automatic candidate selection = false
```

## Next

After final human review and strict validation:

```text
inspect root-cause evidence
→ choose exactly one bounded v0.3 typing hypothesis
→ controlled development experiment
→ new disjoint prediction-blind held-out for independent acceptance
```
