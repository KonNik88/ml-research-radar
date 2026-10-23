# 9C — Full-field Scientific NER v0.1: preregistered scoring policy

## Purpose and state

This slice **freezes the scoring rules before looking at production predictions**. It binds
9A's 120 prediction-blind fields to the completed, immutable 9B reference and to the H2
v0.3 trusted production pointer **by metadata only**. No prediction files, inference,
source mutations, threshold tuning, or evaluation are allowed in 9C.

## Sampling interpretation

The sample contains **60 title fields and 60 abstract fields**, sampled in separate
strata. Pooling them gives the balanced-field audit metric, **not** a corpus-prevalence-
weighted estimate of whole-corpus precision/recall. Report each stratum separately.
In addition, do not treat a sampled field as an independent paper-level outcome.

## Gold and unresolved annotations

- Gold reference: every frozen mention with `uncertain=false`.
- Uncertain: every frozen mention with `uncertain=true` (68 total): retain unchanged,
  **exclude from all primary TP/FN reference denominators**.
- Before matching, remove from primary scoring only those prediction mentions that
  overlap (positive character intersection) one or more uncertain reference spans
  **and do not overlap any certain reference span**. Report the ignored count.
- If a prediction touches both a certain and an uncertain reference, KEEP it in scoring
  (certain-reference precedence). This avoids hiding known negatives near certain labels.
- An uncertain reference is not necessarily false or true: never assume either.
- Sensitivity panel (separate, clearly secondary): include all uncertain references as
  provisional gold and recompute metrics; never call this the primary score.
- Neither uncertainty panel authorizes adjudication/tuning against model output.

## Span matching — preregistered

1. Field identity is `(audit_case_id, canonical_id, source_field)`; never match across
   fields or against different source text. Verify source-text identity at unblind.
2. `exact`: `(start,end)` boundaries equal, end-exclusive. `relaxed`: character-span
   IoU = overlap / union >= **0.50**, with positive overlap; record exact and relaxed.
3. Span-only panels ignore type when deciding a match. Typed panels require exactly
   the same one of `task/method/dataset/metric/model/domain`.
4. One-to-one within each field; maximize **number of matched pairs** first, total
   overlap/IoU second, and apply a deterministic stable tie-break. A matching must not
   be sensitive to input order. No reference or prediction can be used twice in a panel.
5. Every gold span, including meaningful nested overlaps, is a distinct annotation.
   Never collapse nested references. Duplicate identical predictions remain duplicates;
   unmatched copies count toward FP.
6. Independently match per panel: `span_only_exact`, `span_only_relaxed`, `typed_exact`
   (primary), and `typed_relaxed`.

For each panel `TP` is matched pairs, `FP` is scored predictions minus TP, `FN` is
certain reference mentions minus TP. Compute precision/recall/F1 from aggregated
counts (`micro`), not by averaging field-level ratios. Report `title`, `abstract`, and
pooled balanced fields separately. Report P/R/F1 and counts by entity type for typed
panels; F1 macro mean includes only reference-supported types, and type support must
be shown. Undefined ratios use `null`, not fabricated zero.

## Error diagnostics (descriptive only)

After primary matching, run a **separate deterministic, one-to-one** type-agnostic
pairing for diagnoses; categories need not sum to metric errors:
- `type_only_exact_span`: exact boundaries but different type;
- `boundary_only_same_type`: relaxed overlap, same type, non-exact boundaries;
- `boundary_and_type`: relaxed overlap, differing type/boundary;
- unmatched reference (potential FN);
- unmatched prediction (potential FP);
- nested/intersecting mention contexts.

Report examples with `(audit_case_id, offsets, surface, reference/predicted type)`;
do not change reference after seeing predictions. Stricter/looser IoU thresholds, if
explored later, are **post hoc** sensitivity analyses and must be labeled as such.

## Limitations and gates

This policy sets no numerical quality acceptance threshold: the first full-field audit
is diagnostic. The current 9C only authorizes immutable rule preregistration. **9D must
separately validate this frozen package before unblinding**. No re-running 61,075-paper
model inference is needed: use the existing trusted `final_mentions.jsonl`.

## Workflow

- PLAN: validate 9B strict package, frozen annotation/summary counts, trusted pointer
  metadata, and the exact declared policy. Zero writes, zero prediction reads.
- EXECUTE, once after code merge: immutable `policy.json`, `manifest.json`, `README.md`,
  `checksums.txt` with hashes; no latest update.
- STRICT: recompute all four files byte for byte, hashes/line endings, upstream lineage,
  and verify 9D has not run in this slice.
