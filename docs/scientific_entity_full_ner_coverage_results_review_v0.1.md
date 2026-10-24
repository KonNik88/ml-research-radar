# ML Research Radar — 9E Full NER Coverage Results Review v0.1

**Status:** diagnostic review of immutable 9D artifacts; no production changes or tuning.  
**Evaluation ID:** `scientific-entity-full-ner-coverage-unblind-evaluation-v0.1-3cc6e3c779fee351`  
**Trusted production baseline:** H2 v0.3, `final_mentions.jsonl` SHA256 `518f3984d3dcd2aa5e2a84c96eec2fadce8b6dc6b49eef0d7a908533145394c1`.

## 1. Input verification

All four supplied artifact files (`manifest.json`, `summary.json`, `cases.jsonl`, `selected_predictions.jsonl`) match the SHA256 values in the supplied `checksums.txt`. Parsed JSONL counts: **120 cases**, **851 selected predictions**. 9D strict validation previously reported **22/22 PASS**, and the manifest states no new inference or production mutation.

The sampled fields are **60 titles and 60 abstracts**, not an empirical corpus-frequency-weighted field distribution. The frozen reference has **972 annotations** of which **68 were uncertain**. Primary evaluation uses **904 certain references**. From **851 selected predictions**, **34 were ignored under the preregistered uncertain-only rule**, leaving **817 scored predictions**. This was a controlled unblind on an existing production artifact, not an independent estimate of corpus-wide quality.

## 2. Primary and secondary matching metrics

| Panel | Precision | Recall | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| Typed exact **(primary)** | 40.88% | 36.95% | **38.81%** | 334 | 483 | 570 |
| Span-only exact | 54.83% | 49.56% | **52.06%** | 448 | 369 | 456 |
| Typed relaxed (IoU ≥ 0.5) | 44.43% | 40.15% | **42.18%** | 363 | 454 | 541 |
| Span-only relaxed (IoU ≥ 0.5) | 59.12% | 53.43% | **56.13%** | 483 | 334 | 421 |

The difference of **114 exact-span matches** between span-only exact TP (448) and typed exact TP (334) quantifies wrong entity type at an otherwise exact match. Relaxed boundaries add **29** typed TPs, raising typed F1 by **3.37 percentage points**. Even span-only relaxed recall remains **53.43%**, showing substantial end-to-end coverage/matching losses beyond typing and boundary precision.

### Diagnostic partition of unmatched typed-exact pairs

Across 120 cases, the 9D `diagnosed` records contain:

| Diagnostic category | Matched error pairs |
|---|---:|
| Exact span, wrong type | **114** |
| Boundary difference, same type | **26** |
| Both boundary and type differ | **9** |
| Remaining unmatched reference mentions after diagnostic matching | **421** |
| Remaining unmatched scored predictions after diagnostic matching | **334** |

These reconcile exactly to the primary panel: `114 + 26 + 9 + 421 = 570 FN` and `114 + 26 + 9 + 334 = 483 FP`. The **421** residual references are *not automatically 421 entirely undetected concepts*: they can include small/partial overlaps below matching rules or cases for which the diagnostic matcher found no allowable pair. Review the underlying text before attributing all residuals to pure detection failure.

The `nested_overlap` diagnostic reports **5**. Nesting is permitted by the frozen annotation policy and is not inherently a labeling error.

## 3. Per-type performance (primary typed-exact)

| Entity type | Gold support | Scored predictions | Precision | Recall | F1 | TP |
|---|---:|---:|---:|---:|---:|---:|
| model | 213 | 249 | 50.20% | 58.69% | **54.11%** | 125 |
| method | 292 | 252 | 43.25% | 37.33% | **40.07%** | 109 |
| metric | 75 | 68 | 35.29% | 32.00% | **33.57%** | 24 |
| task | 188 | 143 | 37.76% | 28.72% | **32.63%** | 54 |
| dataset | 28 | 72 | 15.28% | 39.29% | **22.00%** | 11 |
| domain | 108 | 33 | 33.33% | 10.19% | **15.60%** | 11 |

**Priority signals:**
- `domain`: very low recall (11/108); production predicts the class infrequently (33 predictions).
- `dataset`: gross overprediction compared with sample gold prevalence (72 predictions vs 28 references; only 11 exact typed TPs). The small reference support (28) also limits precise extrapolation.
- `task`: 134/188 gold annotations not matched correctly at typed exact; missed spans/low extraction coverage deserve review.
- `model` is relatively strongest, but still misses 88/213 exact-typed reference mentions.

## 4. Title vs abstract

| Primary panel | Titles (60) | Abstracts (60) |
|---|---:|---:|
| Gold mentions | 133 | 771 |
| Scored predictions | 91 | 726 |
| TP | 44 | 290 |
| Precision | 48.35% | 39.94% |
| Recall | 33.08% | 37.61% |
| F1 | **39.29%** | **38.74%** |

The near-equal F1 hides different error profiles: titles have higher precision and lower recall. Of the **60 title fields, 13 have zero predictions even though each has at least one certain reference**. **26/60 titles have zero typed-exact TPs**. Among the 60 abstracts, 1 has zero predictions and 7 have zero typed-exact TPs.

Because 60/60 is a designed field balance, these numbers should not be interpreted as natural corpus prevalence or weighted paper-level performance.

## 5. Major observed type confusions (exactly matching spans)

| Frozen reference → production prediction | Occurrences | Example |
|---|---:|---|
| model → method | **29** | `Gaussian process` |
| method → task | **20** | `soft interventions` |
| task → method | **12** | `OMS` |
| domain → method | **9** | `theoretical machine learning` |
| domain → dataset | **8** | `image data` |
| method → model | **8** | `machine learning algorithms` |
| model → task | **7** | `GPG` |
| domain → task | **6** | `agile engineering` |

These are counts in **120 frozen fields**, not percentages of all corpus mentions. Labels are the frozen human annotations, which can contain guideline-sensitive semantic ambiguities; they should not be rewritten after unblinding. The historical v0.3 intervention `method → model` cannot fix all these confusion directions.

## 6. Illustrative residual FN and FP (not a random sample)

**Reference mentions still unmatched after diagnosis** include `Image-to-Image Translation` (task, title), `Document-Level Event Extraction` (task, title), `Histogram Features` (method, title), `PASCAL VOC` (dataset, abstract), `AUPRC` (metric, abstract), `Faster R-CNN` (model, abstract), `LLMs` (model, abstract), `synthetic data` (domain, abstract), `database management systems` (domain, abstract).

**Unmatched predictions** include generic or ambiguous text such as `datasets`, `data`, `pixels` classified as dataset; `model`, `classifier`, `machine learning` classified as model; `evaluation metrics`, `score-based` classified as metric; `algorithm`, `algorithms` classified as method. These entries are *mismatches under the frozen reference policy*. Some are candidates for generic-phrase false positive suppression; others can reflect scope or boundary disagreements and require qualitative inspection in full field context.

A single duplicate production identity appears in the 851 selected prediction rows: two occurrences of `IconqSched` as a `model` with identical document/field/span/type. The registered no-dedup rule keeps both, as it should. It is not evidence for mass duplicate-driven metric inflation.

## 7. Uncertain sensitivity

The sensitivity panel treating all uncertain annotations as gold reports **typed-exact F1 = 37.41%** versus the primary **38.81%** (difference **−1.40 percentage points**). This quantifies one sensitivity of the registered uncertainty treatment, without justifying post-unblind changes to the frozen policy.

## 8. Interpretation and bounded next steps

**Observed**: the full extractor has simultaneous span coverage/matching, typing, and generic-phrase precision problems. Exact typed F1 is 38.81%; the generous span-only relaxed ceiling *under this matching rule* is 56.13% F1. Pure boundary refinements are not sufficient, nor is another narrow model/method type flip policy.

**Hypotheses to test next (not yet validated)**:
1. Extractor candidate generation under-recalls `task`, `domain`, and some named `model`/`dataset` entities, particularly in titles.
2. Broad generic-phrase candidates inflate `model`, `method`, `metric` and `dataset` false positives.
3. Taxonomy-specific ambiguity (`model/method`, `method/task`, `domain/dataset`) remains after the H2 intervention.
4. Boundary/compound/nested behavior accounts for a smaller but observable loss.

**Recommended work plan**:
- **9E**: archive this immutable-results review and selected qualitative examples; do not rewrite 9D, frozen reference or scoring policy.
- **v0.4-A: read-only error diagnostics**: manually inspect a stratified subset of false negatives and false positives (both titles and abstracts), categorize recall vs generic false positives vs taxonomy/boundaries, document testable hypotheses. Use existing artifacts for initial evidence, but do not tune on this historical evaluation set.
- **v0.4-B: independent development data**: sample and annotate fresh disjoint title/abstract fields, create a development/diagnostic reference with an explicit annotation guide. A **separate fresh heldout** is needed for subsequent independent acceptance testing, especially now that 9D labels/predictions were unblinded and inspected.
- **v0.4-C: bounded candidate experiments**: assess candidate generation, generic-phrase filtering, and type confusion repair separately; score on development data, not 9D evaluation data. Register criteria before each new heldout test.
- **v0.4-D: production consideration**: only after independent acceptance, consider controlled full-corpus candidate build and promotion. **No new full-corpus inference is authorized or necessary for the present review.** Warn explicitly before any future high-cost build.

## 9. Integrity/interpretation notes

The 9D manifest declares: `evaluation_executed=true`, `model_inference_executed=false`, `production_mutated=false`, `reference_mutated=false`, `policy_mutated=false`, `metrics_are_balanced_sample_only=true`, `publication_authorized=false`. The earlier strict validator reported 22 required checks passed, zero failures.

Primary diagnostic error categories are post-matching classifications, not interchangeable with true semantic causes established by adjudicators. Results from 120 sampled fields are useful for bounded quality diagnosis, but are not a statistically representative population estimate without assumptions/weighting and confidence-interval analysis.
