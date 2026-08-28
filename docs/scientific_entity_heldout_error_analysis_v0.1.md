# Scientific Entity Held-Out Error Analysis v0.1

Status: **completed / strict validation green / v0.2 hypothesis selected**

Purpose:

```text
accepted bounded GLiNER v0.1 baseline
→ immutable 48-paper held-out evaluation
→ deterministic structured error analysis
→ exact source-surface reconstruction
→ audit the actual GLiNER adapter windowing contract
→ isolate dominant failure families and bounded source-text anomalies
→ freeze exactly one next v0.2 design hypothesis
```

Current accepted analysis:

```text
analysis_id = scientific-entity-heldout-error-analysis-v0.1-20260828T121239202063Z
source_evaluation_id = scientific-entity-evaluation-v0.1-20260827T113112815887Z
documents = 48
reference_mentions = 881
prediction_mentions = 787
exact_matches = 331
relaxed_only_matches = 15
errors = 808
strict_validator = 398 / 398 required checks
model_inference_executed = false
threshold_tuning_executed = false
canonical_truth_mutated = false
```

The analyzer reads the existing held-out evaluation manifest and follows its
hash-pinned canonical sample, reference-mention, and frozen prediction-mention
paths. It does not run GLiNER, download a model, or retune thresholds.

## Outputs

```text
data/entities/scientific_entity_heldout_error_analysis/v0.1/<analysis_id>/
├── manifest.json
├── summary.json
├── type_confusions.json
├── confidence_analysis.json
├── gliner_windowing_completeness_audit.json
├── error_examples.jsonl
├── README.md
└── checksums.txt
```

## Held-out quality context

The source held-out evaluation remains unchanged:

```text
exact = TP 331 / FP 456 / FN 550 / precision 0.420584 / recall 0.375709 / F1 0.396882
relaxed = TP 346 / FP 441 / FN 535 / precision 0.439644 / recall 0.392736 / F1 0.414868

boundary_mismatch = 22
type_mismatch = 176
pure_false_positive = 258
pure_false_negative = 352
```

The v0.1 generalization gate remains passed only in the bounded sense:

```text
candidate_decision = accept_as_bounded_working_extractor_v0.1
production_extractor_selected = false
full_corpus_build_authorized = false
publication_ready = false
```

## Dominant error diagnosis

The strongest actionable failure is semantic type disambiguation, not a global
confidence-threshold problem.

Key type-confusion evidence:

```text
model -> method = 55
method -> task = 28
domain -> method = 14
task -> method = 11
dataset -> method = 9
method_semantic_sink = 94 / 176 type mismatches = 0.534091
```

The dominant errors are often high-score predictions rather than near-threshold
border cases:

```text
all exact matches median model_score = 0.850098
all type mismatches median model_score = 0.815674

model -> method:
count = 55
median = 0.869141
mean = 0.845179

method -> task:
count = 28
median = 0.802490
mean = 0.785313
```

Representative exact-span confusions include:

```text
Recurrent Neural Networks:
reference = model
prediction = method
model_score = 0.97412109

domain adaptation:
reference = method
prediction = task
model_score = 0.92236328

population-based training:
reference = method
prediction = task
model_score = 0.90722656
```

This evidence does not justify another global threshold retune as the first
v0.2 action. Raising thresholds enough to remove high-score semantic confusion
would also discard many correct predictions.

## Per-type interpretation

The weakest exact held-out types remain:

```text
metric:
precision = 0.250000
recall = 0.180851
F1 = 0.209877

domain:
precision = 0.280000
recall = 0.308824
F1 = 0.293707

task:
precision = 0.519231
recall = 0.308571
F1 = 0.387097
```

Representative false negatives show why the current GLiNER-facing prompts need
stronger semantic separation:

```text
metric examples:
- ruggedness
- problem size

task examples:
- link prediction problem
```

The current v0.1 extractor already uses semantic prompt text rather than bare
one-word labels. Therefore the selected next hypothesis is not "add semantic
labels"; it is to redesign the existing GLiNER-facing prompts so the six
canonical classes are more discriminative from one another.

## Adapter windowing audit

The final diagnostic audit mirrors the actual v0.1 adapter contract:

```text
adapter window size = 320 GLiNER WordsSplitter tokens
adapter overlap = 64 tokens
window step = 256 tokens
model.config.max_len = 768
model.config.max_width = 12
words_splitter_type = whitespace
installed GLiNER splitter verification = true
installed GLiNER version = 0.2.28
```

Observed held-out windowing:

```text
source_texts_requiring_multiple_windows_count = 3
total_adapter_inference_window_count = 101
max_observed_window_token_count = 320
window_exceeds_model_max_len_count = 0
uncovered_splitter_token_count = 0
all_source_splitter_tokens_covered_by_adapter_windows = true
```

Therefore long-document prefix truncation is **not** a material failure mode for
this held-out run. The adapter covers every source token through overlapping
windows before shifting prediction offsets back into source coordinates.

### Superseded diagnostic interpretation

An earlier local diagnostic iteration incorrectly treated
`model.config.max_len=768` as a whole-document prefix cutoff. That interpretation
does not match the real v0.1 adapter and is superseded by
`gliner_windowing_completeness_audit.json`.

The held-out prediction/evaluation artifacts themselves were never invalidated;
only that intermediate diagnostic interpretation was wrong.

## Bounded source-text / span-width corner case

The corrected audit found a small, separate source-representation issue:

```text
reference_mentions_exceeding_model_max_width_count = 5
false_negative_references_exceeding_model_max_width_count = 5
markup_like_reference_mention_count = 5
markup_like_false_negative_reference_count = 5

wide_reference_set == markup_like_reference_set = true

reference_mentions_not_fully_contained_in_any_adapter_window_count = 2
false_negative_references_not_fully_contained_in_any_adapter_window_count = 2
not_contained_set is a subset of the same five wide markup-like references = true
```

These spans contain embedded scholarly markup such as XML/JATS/MathML-style
material. The markup can make one logical entity span much wider than the
pinned `model_max_width=12`.

This is a real but bounded corner case:

```text
5 / 352 pure false negatives ≈ 1.42%
```

It does not explain the dominant semantic confusion or overall recall.

No canonical cleanup is authorized by this result. If markup-heavy spans become
material at broader scale, evaluate a separate deterministic NER-facing
plain-text representation with explicit source-offset mapping rather than
mutating canonical paper truth.

## Decision

The accepted v0.1 diagnosis is:

```text
primary actionable failure:
semantic type disambiguation

secondary:
ordinary false positives and false negatives

minor:
boundary errors

bounded structural/source-text corner case:
markup-expanded spans wider than model_max_width

not a material held-out failure mode:
long-document adapter coverage / whole-text truncation
```

Selected first v0.2 hypothesis:

```text
Scientific Entity Semantic Prompt Candidate v0.2a

same pinned GLiNER small-v2.5 model
same model weights and runtime boundaries
same six canonical entity types
same source texts for development comparison
same frozen title >= 0.55 / abstract >= 0.65 thresholds for the first controlled comparison
same evaluation semantics

only intended first experimental change:
more discriminative GLiNER-facing semantic prompt wording
```

The exact six v0.2a prompts must be frozen **before** candidate inference. They
must map back to the unchanged canonical types:

```text
task
method
dataset
metric
model
domain
```

Initial design focus, without yet freezing exact wording:

```text
model vs method:
named model / neural-network / architecture
vs algorithm / training procedure / computational technique

method vs task:
procedure used to solve
vs prediction problem / learning objective being solved

metric:
must cover quantitative scores, measured properties, and efficiency measures,
not only classic benchmark metrics

domain:
must distinguish research/application/data domains from methods and tasks
```

## Evidence-use boundary for v0.2

The 48-paper package remains honest independent held-out evidence for the already
frozen v0.1 candidate.

Because its errors have now been inspected and used to choose the v0.2a
hypothesis:

```text
48-paper package = development/error-analysis evidence for v0.2
future v0.2 independent acceptance = requires a new disjoint held-out sample
```

No future v0.2 acceptance claim may reuse these same 48 papers as independent
held-out evidence.

## Safety boundary

```text
analysis only
no new model inference
no model/tokenizer download
no threshold tuning
no provider API calls
no canonical mutation
no reconcile input
no production extractor selection
no full-corpus extraction
no normalization/product/graph integration
no publication
```
