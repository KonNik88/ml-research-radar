# Full NER Coverage Audit v0.1 — Annotation Guide

## Purpose

This is a **prediction-blind full-field audit** of the trusted Scientific Entity production baseline.

You annotate the complete `source_text` of each sampled `title` or `abstract` and mark **all explicit scientific entities** belonging to the frozen taxonomy:

- `task`
- `method`
- `dataset`
- `metric`
- `model`
- `domain`

Do **not** inspect production predictions, prior audit labels, or model outputs while annotating. Do not search the web for the paper. If the text itself is insufficient to decide, use `uncertain=true` and explain briefly in `reviewer_note`.

## Annotation unit

One JSONL row = one complete canonical field (`title` or `abstract`).

For each row:

1. read the full `source_text`;
2. add every qualifying entity mention to `mentions`;
3. use exact Python-style character offsets: `source_text[char_start:char_end]` must equal `surface_text`;
4. set `annotation_complete=true` only after the whole field has been reviewed;
5. if there are no entities, leave `mentions=[]` and still set `annotation_complete=true`.

## Frozen taxonomy

### `task`
A problem, objective, or operation that a method/model is intended to solve.

Typical examples:
- image classification
- semantic segmentation
- machine translation
- named entity recognition
- document retrieval
- joint segmentation and classification

Prefer the full task phrase when modifiers are needed to define the task.

### `method`
An algorithmic procedure, training/inference strategy, optimization technique, transformation, loss, decomposition, or other methodological mechanism.

Typical examples:
- contrastive learning
- data augmentation
- fine-tuning
- beam search
- graph propagation
- orthogonal Tucker3 tensor decomposition

Use `method` for a procedure/mechanism, not for a learned model/system entity.

### `model`
A named or clearly instantiated learned model, model family, architecture, controller/system used as a model, or concrete predictive/generative architecture.

Typical examples:
- BERT
- ResNet
- Vision Transformer
- convolutional neural network
- VAE-SSL

Rule of thumb: if the phrase denotes the learned architecture/system itself, prefer `model`; if it denotes how something is trained/computed/applied, prefer `method`.

### `dataset`
A named dataset, corpus, benchmark dataset, or explicitly named data collection used for training/evaluation.

Typical examples:
- ImageNet
- CIFAR-10
- SQuAD
- MS COCO

Do not label a generic phrase such as “our dataset” unless it is clearly functioning as a named/identifiable dataset entity in the text.

### `metric`
A quantitative evaluation metric or named score.

Typical examples:
- accuracy
- F1 score
- BLEU
- AUROC
- mean average precision

Do not annotate a bare numeric result such as `94.8%` without the metric name.

### `domain`
A scientific/application area, data modality, or problem context that is not itself the target task.

Typical examples:
- medical imaging
- fundus images
- autonomous driving
- computational biology
- speech processing

Do not use `domain` for an operation that is better represented as `task`.

## Span-boundary rules

Use the **smallest semantically complete surface span**.

- Exclude articles/determiners unless they are part of an official name.
- Include modifiers that are necessary to identify the entity.
- Do not include surrounding verbs or descriptive clauses.
- Preserve punctuation/hyphenation exactly as written when it belongs to the mention.
- Repeated explicit mentions are annotated separately.
- A full name and an acronym are separate explicit mentions if both appear in the text.
- Overlapping/nested mentions are allowed only when both are independently meaningful entities. Do not create redundant nested duplicates merely because a subphrase could also be interpreted generically.
- For a coordinated phrase that functions as one named/combined task, annotate the complete coordinated phrase (for example, `Joint segmentation and classification`).

## Ambiguity policy

Use `uncertain=true` when any of the following remains genuinely unresolved from the text:

- entity vs non-entity;
- type assignment;
- span boundary;
- acronym interpretation.

Then add a concise `reviewer_note` describing the uncertainty.

Do not force a confident label merely to avoid uncertainty.

## Important exclusions

Do not annotate:

- author names;
- institutions;
- venues/journals/conferences;
- generic software/hardware names unless they clearly function as one of the six frozen entity types;
- generic scientific nouns with no entity-like role;
- inferred concepts that are not explicitly present in the text.

## Working JSONL shape

```json
{
  "schema_version": "scientific_entity_full_ner_coverage_annotation_working_v0.1",
  "audit_id": "...",
  "audit_case_id": "...",
  "canonical_id": "...",
  "source_field": "abstract",
  "source_text": "...",
  "source_text_sha256": "...",
  "mentions": [
    {
      "entity_type": "model",
      "char_start": 10,
      "char_end": 14,
      "surface_text": "BERT",
      "uncertain": false,
      "reviewer_note": null
    }
  ],
  "annotation_complete": true,
  "reviewer_note": null
}
```

## Completion rule

A row is complete only when the **entire field** has been reviewed for all six entity types.

The goal is full coverage, not confirmation of a preselected span.
