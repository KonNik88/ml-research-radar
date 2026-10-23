"""9D: fail-closed unblind of existing trusted predictions and frozen 9C evaluation.

PLAN is strictly metadata-only; EXECUTE/STRICT stream the existing full-corpus
prediction artifact and never invoke an inference model or modify parents.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import shutil
import tempfile
from typing import Any

import yaml
from scipy.optimize import linear_sum_assignment

from radar_core.contracts.scientific_entity_full_ner_coverage_audit import FullNerCoverageAnnotationRow
from radar_core.contracts.scientific_entity_full_ner_coverage_scoring_policy import ScoringPolicyRecord
from radar_core.contracts.scientific_entity_full_ner_coverage_unblind_evaluation import (
    FullNerUnblindManifest, FullNerUnblindPrediction, FullNerUnblindSummary,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import H2FullCorpusFinalMention
from radar_core.entities.scientific_entity_full_ner_coverage_scoring_policy import validate_scoring_policy


class FullNerUnblindError(RuntimeError):
    """A frozen parent, trusted production artifact, or evaluation contract drifted."""


PANELS = ("span_only_exact", "span_only_relaxed", "typed_exact", "typed_relaxed")
TYPES = ("task", "method", "dataset", "metric", "model", "domain")
EXPECTED = {
    "audit_id": "scientific-entity-full-ner-coverage-audit-v0.1-3cc6e3c779fee351",
    "reference_id": "scientific-entity-full-ner-coverage-reference-v0.1-3cc6e3c779fee351",
    "policy_id": "scientific-entity-full-ner-coverage-scoring-policy-v0.1-3cc6e3c779fee351",
    "expected_candidate_build_id": "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z",
    "expected_production_sha256": "518f3984d3dcd2aa5e2a84c96eec2fadce8b6dc6b49eef0d7a908533145394c1",
    "expected_production_mention_count": 846264,
    "expected_reference_sha256": "95e231b4187de26fa57d9c71b3ec74c4d5303ce3c22c5a96560059c948235c75",
    "expected_reference_fields": 120,
    "expected_reference_mentions": 972,
    "expected_uncertain_mentions": 68,
    "primary_panel": "typed_exact",
    "expected_relaxed_iou_threshold": 0.5,
    "plan_may_read_production_predictions": False,
    "execute_may_read_existing_predictions": True,
    "model_inference_allowed": False,
    "production_mutation_allowed": False,
    "reference_mutation_allowed": False,
    "policy_mutation_allowed": False,
    "threshold_tuning_allowed": False,
    "publication_authorized": False,
    "quality_acceptance_thresholds_precommitted": False,
}


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _file_sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_json_bytes(row) for row in rows)


def _project_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise FullNerUnblindError("Missing configured project-relative path")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise FullNerUnblindError(f"Path escapes repository: {value}")
    return path


def load_unblind_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or cfg.get("schema_version") != "scientific_entity_full_ner_coverage_unblind_evaluation_config_v0.1":
        raise FullNerUnblindError("Invalid 9D configuration schema")
    for k, value in EXPECTED.items():
        if type(cfg.get(k)) is not type(value) or cfg.get(k) != value:
            raise FullNerUnblindError(f"Frozen 9D configuration invariant drift: {k}")
    if cfg.get("evaluation_id") != "scientific-entity-full-ner-coverage-unblind-evaluation-v0.1-3cc6e3c779fee351":
        raise FullNerUnblindError("Evaluation ID changed")
    for k in ("policy_config_path", "policy_dir", "reference_dir", "trusted_latest_pointer_path", "output_dir"):
        if not isinstance(cfg.get(k), str) or not cfg[k]:
            raise FullNerUnblindError(f"Invalid path: {k}")
    return cfg


def _read_annotations(path: Path) -> list[FullNerCoverageAnnotationRow]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise FullNerUnblindError("Frozen annotations require LF termination")
    return [FullNerCoverageAnnotationRow.model_validate_json(line) for line in raw.splitlines()]


def _preflight(config_path: Path, root: Path) -> dict[str, Any]:
    cfg = load_unblind_config(config_path)
    policy_cfg = _project_path(root, cfg["policy_config_path"])
    policy_result = validate_scoring_policy(policy_cfg, root)
    if not policy_result.get("policy_validated") or policy_result.get("required_failed_count"):
        raise FullNerUnblindError(f"9C preregistration not valid: {policy_result.get('error')}")
    policy_dir = _project_path(root, cfg["policy_dir"])
    reference_dir = _project_path(root, cfg["reference_dir"])
    policy = ScoringPolicyRecord.model_validate_json((policy_dir / "policy.json").read_bytes())
    if (policy.policy_id != cfg["policy_id"] or policy.reference_id != cfg["reference_id"] or
        policy.audit_id != cfg["audit_id"] or policy.scoring_rules.get("primary_panel") != "typed_exact" or
        policy.scoring_rules.get("relaxed_iou_threshold") != 0.5):
        raise FullNerUnblindError("Frozen 9C scoring policy mismatch")
    ref_annotations_path = reference_dir / "annotations.jsonl"
    if _file_sha(ref_annotations_path) != cfg["expected_reference_sha256"]:
        raise FullNerUnblindError("Frozen 9B annotation SHA mismatch")
    rows = _read_annotations(ref_annotations_path)
    if (len(rows) != 120 or sum(len(r.mentions) for r in rows) != 972 or
        sum(m.uncertain for r in rows for m in r.mentions) != 68 or
        sum(r.source_field == "title" for r in rows) != 60 or
        sum(r.source_field == "abstract" for r in rows) != 60):
        raise FullNerUnblindError("Frozen reference dimensions mismatch")
    keys = [(r.canonical_id, r.source_field) for r in rows]
    if len(set(keys)) != len(keys) or len({r.audit_case_id for r in rows}) != len(rows):
        raise FullNerUnblindError("Duplicate frozen field identity")
    pointer_path = _project_path(root, cfg["trusted_latest_pointer_path"])
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if (pointer.get("state") != "trusted_latest" or
        pointer.get("candidate_build_id") != cfg["expected_candidate_build_id"] or
        pointer.get("candidate_final_mentions_sha256") != cfg["expected_production_sha256"] or
        pointer.get("final_mention_count") != cfg["expected_production_mention_count"] or
        pointer.get("artifact_is_immutable_candidate") is not True or
        pointer.get("artifact_retention_required") is not True):
        raise FullNerUnblindError("Trusted H2 production pointer drift")
    candidate_path = _project_path(root, pointer["artifact_path"])
    if candidate_path.name != "final_mentions.jsonl" or not candidate_path.is_file():
        raise FullNerUnblindError("Trusted final_mentions source missing")
    return {
        "cfg": cfg, "rows": rows, "candidate_path": candidate_path,
        "config_sha": _file_sha(config_path),
        "reference_manifest_sha": _file_sha(reference_dir / "manifest.json"),
        "reference_annotation_sha": _file_sha(ref_annotations_path),
        "policy_manifest_sha": _file_sha(policy_dir / "manifest.json"),
        "policy_record_sha": _file_sha(policy_dir / "policy.json"),
        "pointer_sha": _file_sha(pointer_path),
    }


def _iou(a: Any, b: Any) -> float:
    intersection = max(0, min(a.char_end, b.char_end) - max(a.char_start, b.char_start))
    if intersection == 0:
        return 0.0
    union = max(a.char_end, b.char_end) - min(a.char_start, b.char_start)
    return intersection / union


def _overlap(a: Any, b: Any) -> bool:
    return min(a.char_end, b.char_end) > max(a.char_start, b.char_start)


def _mention_key(item: Any) -> tuple[Any, ...]:
    return (item.char_start, item.char_end, str(getattr(item, "entity_type")),
            getattr(item, "surface_text", ""), getattr(item, "final_mention_id", ""))


def _match(gold: list[Any], predictions: list[Any], panel: str, *, relaxed_threshold: float = 0.5) -> list[tuple[int, int]]:
    """Max cardinality, then total IoU, with deterministic canonical-order tie-break.

    The square assignment has dummy rows and columns, allowing unmatched elements.
    Every eligible edge receives a fixed cardinality bonus larger than the combined
    IoU/tie bonus of *all* other possible edges.
    """
    if panel not in PANELS or not gold or not predictions:
        return []
    ng, n_pred = len(gold), len(predictions)
    size = ng + n_pred
    # Any additional match outweighs the total IoU of all other possible
    # matches, while floating-point IoUs retain their original precision.
    max_pairs = min(ng, n_pred)
    cardinality = max_pairs + 2.0
    import numpy as np
    reward = np.zeros((size, size), dtype=np.float64)
    allowed: set[tuple[int, int]] = set()
    for i, a in enumerate(gold):
        for j, b in enumerate(predictions):
            iou = _iou(a, b)
            eligible = ((a.char_start, a.char_end) == (b.char_start, b.char_end)
                        if panel.endswith("exact") else iou >= relaxed_threshold)
            if panel.startswith("typed_"):
                eligible = eligible and str(a.entity_type) == str(b.entity_type)
            if eligible:
                allowed.add((i, j))
                # IoU scaled first; small deterministic preference for earlier
                # canonical pairs does not affect cardinality or rounded IoU.
                tie = ((ng - i) * (n_pred - j)) / ((ng + 1) * (n_pred + 1))
                reward[i, j] = cardinality + iou + tie * 1e-10
    if not allowed:
        return []
    ridx, cidx = linear_sum_assignment(-reward)
    return sorted((int(i), int(j)) for i, j in zip(ridx, cidx, strict=True) if (int(i), int(j)) in allowed)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _stats(tp: int, fp: int, fn: int) -> dict[str, Any]:
    return {"tp": tp, "fp": fp, "fn": fn, "reference_support": tp + fn,
            "prediction_count": tp + fp, "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn), "f1": _ratio(2 * tp, 2 * tp + fp + fn)}


def _primary_partition(row: FullNerCoverageAnnotationRow, predictions: list[FullNerUnblindPrediction]) -> tuple[list[Any], list[Any], int]:
    certain = sorted((m for m in row.mentions if not m.uncertain), key=_mention_key)
    uncertain = [m for m in row.mentions if m.uncertain]
    kept = []
    ignored = 0
    for prediction in sorted(predictions, key=_mention_key):
        if any(_overlap(prediction, u) for u in uncertain) and not any(_overlap(prediction, c) for c in certain):
            ignored += 1
        else:
            kept.append(prediction)
    return certain, kept, ignored


def _panel_counts(gold: list[Any], predictions: list[Any], panel: str) -> tuple[dict[str, Any], list[tuple[int, int]]]:
    matches = _match(gold, predictions, panel)
    return _stats(len(matches), len(predictions) - len(matches), len(gold) - len(matches)), matches


def _collect_predictions(path: Path, rows: list[FullNerCoverageAnnotationRow], *, expected_hash: str, expected_count: int,
                         expected_build: str) -> tuple[dict[tuple[str, str], list[FullNerUnblindPrediction]], int]:
    """Read every original line once for SHA/count; validate only selected rows.

    No outputs are written until the entire trusted source has passed checksum and
    count validation. Avoids reconstructing 846k Pydantic objects unnecessarily.
    """
    fields = {(r.canonical_id, r.source_field): r for r in rows}
    selected: dict[tuple[str, str], list[FullNerUnblindPrediction]] = {key: [] for key in fields}
    wanted_ids = {key[0] for key in fields}
    id_regex = re.compile(rb'"canonical_id"\s*:\s*"([^"\\]+)"')
    seen_ids: dict[str, tuple[str, str, str, int, int, str]] = {}
    digest = sha256()
    line_count = 0
    with path.open("rb") as reader:
        for raw in reader:
            digest.update(raw)
            line_count += 1
            if not raw.endswith(b"\n") or b"\r" in raw or not raw.strip():
                raise FullNerUnblindError("Malformed LF production mention input")
            # Scan the canonical_id key without deserializing ~846k records.
            # Compact candidate records contain ASCII canonical identifiers.
            id_match = id_regex.search(raw)
            if id_match is None:
                raise FullNerUnblindError("Production mention missing valid canonical_id property")
            if id_match.group(1).decode("utf-8") not in wanted_ids:
                continue
            try:
                obj = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FullNerUnblindError("Invalid selected production JSONL row") from exc
            key = (str(obj.get("canonical_id")), str(obj.get("source_field")))
            if key not in fields:
                continue
            record = H2FullCorpusFinalMention.model_validate(obj)
            if record.build_id != expected_build:
                raise FullNerUnblindError("Selected production row references unexpected H2 build")
            reference = fields[key]
            if record.source_text_sha256 != reference.source_text_sha256:
                raise FullNerUnblindError(f"Source text drift at case={reference.audit_case_id}")
            if (record.char_end > len(reference.source_text) or
                reference.source_text[record.char_start:record.char_end] != record.surface_text):
                raise FullNerUnblindError(f"Invalid prediction boundaries/surface at case={reference.audit_case_id}")
            # 9C expressly preserves duplicate prediction *rows*: one matching
            # gold mention can use only one row, so any surplus copy is FP.
            # The stable final_mention_id identifies a semantic span, NOT a
            # unique row/event in the full-corpus candidate JSONL.
            identity = (
                record.canonical_id, record.source_field.value,
                record.source_text_sha256, record.char_start, record.char_end,
                record.final_entity_type.value,
            )
            prior_identity = seen_ids.setdefault(record.final_mention_id, identity)
            if prior_identity != identity:
                raise FullNerUnblindError(
                    "Conflicting identities share a selected final_mention_id"
                )
            selected[key].append(FullNerUnblindPrediction(
                schema_version="scientific_entity_full_ner_coverage_unblind_prediction_v0.1",
                audit_case_id=reference.audit_case_id, canonical_id=reference.canonical_id,
                source_field=reference.source_field, final_mention_id=record.final_mention_id,
                char_start=record.char_start, char_end=record.char_end,
                surface_text=record.surface_text, entity_type=record.final_entity_type.value,
                source_text_sha256=record.source_text_sha256,
            ))
    if line_count != expected_count or digest.hexdigest() != expected_hash:
        raise FullNerUnblindError(
            f"Trusted production SHA/count mismatch: SHA={digest.hexdigest()}, count={line_count}"
        )
    for predictions in selected.values():
        predictions.sort(key=_mention_key)
    return selected, line_count


def _diagnostics(gold: list[Any], preds: list[Any], typed_matches: list[tuple[int, int]]) -> dict[str, Any]:
    gmatched = {i for i, _ in typed_matches}
    pmatched = {j for _, j in typed_matches}
    remaining_g = [g for i, g in enumerate(gold) if i not in gmatched]
    remaining_p = [p for j, p in enumerate(preds) if j not in pmatched]
    unmatched_g_before = len(remaining_g)
    unmatched_p_before = len(remaining_p)
    diagnostics: list[dict[str, Any]] = []
    # Descriptive only: prioritize exact boundary type confusions, then
    # overlapping correct-type boundary shifts, then boundary-and-type.
    for name, predicate in (
        ("type_only_exact_span", lambda a, b: a.char_start == b.char_start and a.char_end == b.char_end and str(a.entity_type) != str(b.entity_type)),
        ("boundary_only_same_type", lambda a, b: (a.char_start, a.char_end) != (b.char_start, b.char_end) and str(a.entity_type) == str(b.entity_type) and _iou(a, b) >= 0.5),
        ("boundary_and_type", lambda a, b: (a.char_start, a.char_end) != (b.char_start, b.char_end) and str(a.entity_type) != str(b.entity_type) and _iou(a, b) >= 0.5),
    ):
        edges = [(i, j, _iou(a, b)) for i, a in enumerate(remaining_g) for j, b in enumerate(remaining_p) if predicate(a, b)]
        if not edges:
            continue
        # Prevent one error example being assigned twice (deterministic greedy
        # diagnostics, not part of preregistered matching/metrics).
        edges.sort(key=lambda v: (-v[2], _mention_key(remaining_g[v[0]]), _mention_key(remaining_p[v[1]])))
        used_g: set[int] = set()
        used_p: set[int] = set()
        for i, j, score in edges:
            if i in used_g or j in used_p:
                continue
            a, b = remaining_g[i], remaining_p[j]
            diagnostics.append({"category": name, "reference_start": a.char_start, "reference_end": a.char_end,
                                "reference_surface": a.surface_text, "reference_type": str(a.entity_type),
                                "prediction_start": b.char_start, "prediction_end": b.char_end,
                                "prediction_surface": b.surface_text, "prediction_type": str(b.entity_type),
                                "prediction_id": b.final_mention_id, "iou": score})
            used_g.add(i)
            used_p.add(j)
        remaining_g = [a for i, a in enumerate(remaining_g) if i not in used_g]
        remaining_p = [b for j, b in enumerate(remaining_p) if j not in used_p]
    nested_count = sum(_overlap(a, b) for i, a in enumerate(gold) for b in gold[i+1:])
    return {"diagnosed": diagnostics, "unmatched_gold_after_diagnosis": [
                {"start": g.char_start, "end": g.char_end, "surface": g.surface_text, "type": str(g.entity_type)} for g in remaining_g],
            "unmatched_prediction_after_diagnosis": [
                {"start": p.char_start, "end": p.char_end, "surface": p.surface_text, "type": str(p.entity_type), "id": p.final_mention_id} for p in remaining_p],
            "unmatched_reference": unmatched_g_before, "unmatched_prediction": unmatched_p_before,
            "nested_overlap": nested_count}


def _metrics(rows: list[FullNerCoverageAnnotationRow], selected: dict[tuple[str, str], list[FullNerUnblindPrediction]], *,
             sensitivity: bool) -> tuple[dict[str, Any], list[dict[str, Any]], Counter[str], int]:
    aggregate: dict[str, dict[str, dict[str, Any]]] = {scope: {panel: {"tp": 0, "fp": 0, "fn": 0} for panel in PANELS}
                                                       for scope in ("balanced", "title", "abstract")}
    type_counts = {scope: {panel: {typ: {"tp": 0, "fp": 0, "fn": 0} for typ in TYPES}
                                  for panel in ("typed_exact", "typed_relaxed")}
                   for scope in ("balanced", "title", "abstract")}
    diag_counts: Counter[str] = Counter()
    cases: list[dict[str, Any]] = []
    ignored_total = 0
    for row in rows:
        original = selected[(row.canonical_id, row.source_field)]
        if sensitivity:
            gold, preds, ignored = sorted(row.mentions, key=_mention_key), list(original), 0
        else:
            gold, preds, ignored = _primary_partition(row, original)
        ignored_total += ignored
        field_panels: dict[str, Any] = {}
        for panel in PANELS:
            counts, matches = _panel_counts(gold, preds, panel)
            field_panels[panel] = counts
            for scope in ("balanced", row.source_field):
                for key in ("tp", "fp", "fn"):
                    aggregate[scope][panel][key] += counts[key]
                if panel.startswith("typed_"):
                    matched_g = {i for i, _ in matches}
                    matched_p = {j for _, j in matches}
                    for typ in TYPES:
                        tpg = sum(str(gold[i].entity_type) == typ for i, _ in matches)
                        fpg = sum(str(pred.entity_type) == typ for j, pred in enumerate(preds) if j not in matched_p)
                        fng = sum(str(g.entity_type) == typ for i, g in enumerate(gold) if i not in matched_g)
                        type_counts[scope][panel][typ]["tp"] += tpg
                        type_counts[scope][panel][typ]["fp"] += fpg
                        type_counts[scope][panel][typ]["fn"] += fng
        primary_matches = _match(gold, preds, "typed_exact")
        diag = _diagnostics(gold, preds, primary_matches)
        for d in diag["diagnosed"]:
            diag_counts[d["category"]] += 1
        diag_counts["unmatched_reference"] += diag["unmatched_reference"]
        diag_counts["unmatched_prediction"] += diag["unmatched_prediction"]
        diag_counts["nested_overlap"] += diag["nested_overlap"]
        if not sensitivity:
            cases.append({"audit_case_id": row.audit_case_id, "canonical_id": row.canonical_id,
                          "source_field": row.source_field, "source_text_sha256": row.source_text_sha256,
                          "certain_reference_count": len(gold),
                          "uncertain_reference_count": sum(m.uncertain for m in row.mentions),
                          "prediction_count": len(original), "ignored_uncertain_only_prediction_count": ignored,
                          "scored_prediction_count": len(preds), "panels": field_panels,
                          "diagnostics": diag})
    metrics = {}
    for scope in ("balanced", "title", "abstract"):
        metrics[scope] = {}
        for panel in PANELS:
            counts = aggregate[scope][panel]
            panel_data: dict[str, Any] = _stats(counts["tp"], counts["fp"], counts["fn"])
            if panel.startswith("typed_"):
                per_type = {typ: _stats(**type_counts[scope][panel][typ]) for typ in TYPES}
                supported = [per_type[typ]["f1"] for typ in TYPES if per_type[typ]["reference_support"] > 0]
                panel_data["per_type"] = per_type
                panel_data["macro_f1_reference_supported_types"] = (sum(supported) / len(supported)) if supported else None
            metrics[scope][panel] = panel_data
    return metrics, cases, diag_counts, ignored_total


def _content(prep: dict[str, Any]) -> dict[str, bytes]:
    cfg = prep["cfg"]
    selected, count = _collect_predictions(prep["candidate_path"], prep["rows"],
        expected_hash=cfg["expected_production_sha256"], expected_count=cfg["expected_production_mention_count"],
        expected_build=cfg["expected_candidate_build_id"])
    predictions = [pred.model_dump(mode="json") for r in prep["rows"] for pred in selected[(r.canonical_id, r.source_field)]]
    primary, cases, diagnostics, ignored = _metrics(prep["rows"], selected, sensitivity=False)
    alternative, _, _, _ = _metrics(prep["rows"], selected, sensitivity=True)
    summary = FullNerUnblindSummary(
        schema_version="scientific_entity_full_ner_coverage_unblind_summary_v0.1",
        evaluation_id=cfg["evaluation_id"], audit_id=cfg["audit_id"], reference_id=cfg["reference_id"], policy_id=cfg["policy_id"],
        field_count=120, title_field_count=60, abstract_field_count=60,
        frozen_mention_count=972, certain_reference_count=904, uncertain_mention_count=68,
        production_prediction_count_scanned=count, selected_prediction_count=len(predictions), ignored_prediction_count=ignored,
        primary_panel="typed_exact", primary_micro=primary["balanced"]["typed_exact"], metrics=primary,
        sensitivity_include_uncertain_as_gold=alternative, diagnostic_counts=dict(sorted(diagnostics.items())),
        balanced_sample_not_corpus_population_weighted=True, numerical_quality_pass_fail_decision_made=False,
        model_inference_executed=False, production_mutated=False, reference_mutated=False, policy_mutated=False,
        threshold_tuning_executed=False, publication_authorized=False,
    )
    readme = (
        "# 9D — Immutable Full NER Coverage Unblind & Evaluation\n\n"
        f"Evaluation ID: `{cfg['evaluation_id']}`\n\n"
        f"Trusted final_mentions SHA256: `{cfg['expected_production_sha256']}`\n\n"
        "Frozen 9B reference and preregistered 9C rules. No model inference, threshold tuning, "
        "reference mutation, or production update. The 60-title/60-abstract pooled figures are "
        "balanced-field audit metrics, NOT corpus-weighted estimates.\n\n"
        "The primary result is balanced typed_exact; see summary.json for four panels, separate "
        "title/abstract reports, per-type scores, uncertainty sensitivity, and diagnostics.\n"
    ).encode("utf-8")
    files = {"README.md": readme, "selected_predictions.jsonl": _jsonl(predictions),
             "cases.jsonl": _jsonl(cases), "summary.json": _json_bytes(summary.model_dump(mode="json"))}
    manifest = FullNerUnblindManifest(
        schema_version="scientific_entity_full_ner_coverage_unblind_manifest_v0.1",
        evaluation_id=cfg["evaluation_id"], audit_id=cfg["audit_id"], reference_id=cfg["reference_id"], policy_id=cfg["policy_id"],
        evaluation_config_sha256=prep["config_sha"], reference_manifest_sha256=prep["reference_manifest_sha"],
        reference_annotations_sha256=prep["reference_annotation_sha"], policy_manifest_sha256=prep["policy_manifest_sha"],
        policy_record_sha256=prep["policy_record_sha"], latest_pointer_sha256=prep["pointer_sha"],
        production_candidate_build_id=cfg["expected_candidate_build_id"],
        production_final_mentions_sha256=cfg["expected_production_sha256"], production_final_mention_count=count,
        selected_prediction_count=len(predictions), primary_panel="typed_exact", metrics_are_balanced_sample_only=True,
        evaluation_executed=True, model_inference_executed=False, production_mutated=False, reference_mutated=False,
        policy_mutated=False, publication_authorized=False,
        next_slice="review_full_ner_coverage_results_and_plan_v04_diagnostics",
        files={name:_sha(data) for name,data in files.items()},
    )
    files["manifest.json"] = _json_bytes(manifest.model_dump(mode="json"))
    files["checksums.txt"] = "".join(f"{_sha(files[name])}  {name}\n" for name in sorted(files)).encode("utf-8")
    return files


def _revalidate_inputs(prep: dict[str, Any], config_path: Path, root: Path) -> None:
    cfg=prep["cfg"]
    checks = (
        (config_path, prep["config_sha"]),
        (_project_path(root, cfg["reference_dir"]) / "manifest.json", prep["reference_manifest_sha"]),
        (_project_path(root, cfg["reference_dir"]) / "annotations.jsonl", prep["reference_annotation_sha"]),
        (_project_path(root, cfg["policy_dir"]) / "manifest.json", prep["policy_manifest_sha"]),
        (_project_path(root, cfg["policy_dir"]) / "policy.json", prep["policy_record_sha"]),
        (_project_path(root, cfg["trusted_latest_pointer_path"]), prep["pointer_sha"]),
    )
    if any(_file_sha(p) != expected for p, expected in checks):
        raise FullNerUnblindError("Frozen lineage changed since evaluation preflight")


def plan_unblind_evaluation(config_path: Path, root: Path) -> dict[str, Any]:
    prep = _preflight(config_path, root)
    cfg = prep["cfg"]
    out = _project_path(root, cfg["output_dir"])
    return {
        "report":"scientific_entity_full_ner_coverage_unblind_evaluation_v01", "mode":"plan", "phase_complete":False,
        "evaluation_id":cfg["evaluation_id"], "policy_id":cfg["policy_id"], "reference_id":cfg["reference_id"],
        "frozen_reference_validated":True, "scoring_policy_strict_validated":True,
        "trusted_latest_metadata_verified":True,"trusted_final_mentions_exists":True,
        "expected_trusted_final_mentions_sha256":cfg["expected_production_sha256"],
        "frozen_field_count":120,"certain_mention_count":904,"uncertain_mention_count":68,
        "primary_panel":"typed_exact","relaxed_iou_threshold":0.5,
        "production_prediction_file_read":False,"unblind_executed":False,"model_inference_executed":False,
        "reference_mutated":False,"policy_mutated":False,"production_mutated":False,
        "evaluation_record_already_exists":out.exists(),"plan_writes_output":False,
        "output_dir":str(out),"next_slice":"commit_full_ner_unblind_evaluation_tooling_before_execute",
    }


def execute_unblind_evaluation(config_path: Path, root: Path) -> dict[str, Any]:
    cfg = load_unblind_config(config_path)
    out = _project_path(root, cfg["output_dir"])
    if out.exists():
        raise FullNerUnblindError(f"Immutable 9D evaluation already exists: {out}")
    prep = _preflight(config_path, root)
    files = _content(prep)
    _revalidate_inputs(prep,config_path,root)
    if out.exists():
        raise FullNerUnblindError("Immutable output destination appeared during evaluation")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".full_ner_9d_staging_", dir=out.parent))
    try:
        for name, data in files.items():
            (staging/name).write_bytes(data)
        if any((staging/name).read_bytes() != data for name,data in files.items()):
            raise FullNerUnblindError("Staged immutable evaluation data changed")
        if out.exists():
            raise FullNerUnblindError("Another process created evaluation record")
        os.replace(staging,out)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    summary = FullNerUnblindSummary.model_validate_json(files["summary.json"])
    return {
        "report":"scientific_entity_full_ner_coverage_unblind_evaluation_v01", "mode":"execute", "phase_complete":True,
        "evaluation_id":cfg["evaluation_id"], "evaluation_executed":True, "strict_parent_lineage_verified":True,
        "trusted_production_sha256_verified":True,"production_input_full_file_scanned":True,
        "production_prediction_count_scanned":846264,"sample_field_count":120,
        "selected_prediction_count":summary.selected_prediction_count,"ignored_uncertain_only_prediction_count":summary.ignored_prediction_count,
        "primary_typed_exact_precision":summary.primary_micro["precision"],
        "primary_typed_exact_recall":summary.primary_micro["recall"],
        "primary_typed_exact_f1":summary.primary_micro["f1"],
        "model_inference_executed":False,"reference_mutated":False,"policy_mutated":False,"production_mutated":False,
        "publication_authorized":False,"output_dir":str(out),
        "next_slice":"validate_immutable_full_ner_unblind_evaluation",
    }


def validate_unblind_evaluation(config_path: Path, root: Path) -> dict[str, Any]:
    cfg = load_unblind_config(config_path)
    out = _project_path(root,cfg["output_dir"])
    expected = {"README.md", "selected_predictions.jsonl", "cases.jsonl", "summary.json", "manifest.json", "checksums.txt"}
    checks: list[tuple[str,bool]] = [("evaluation_directory_exists",out.is_dir()),
                                  ("exact_file_layout",out.is_dir() and {x.name for x in out.iterdir()} == expected)]
    error = None
    try:
        prep = _preflight(config_path,root)
        checks.append(("frozen_reference_policy_and_pointer_still_valid",True))
        if not out.is_dir():
            raise FullNerUnblindError("9D immutable evaluation output missing")
        actual = {name:(out/name).read_bytes() for name in sorted(expected)}
        for name, raw in sorted(actual.items()):
            checks.append((f"lf:{name}", (raw.endswith(b"\n") or (name == "selected_predictions.jsonl" and not raw)) and b"\r" not in raw))
        expected_data = _content(prep)
        _revalidate_inputs(prep,config_path,root)
        for name in sorted(expected):
            checks.append((f"recompute_exact:{name}",actual[name]==expected_data[name]))
        ledger = actual["checksums.txt"].decode("utf-8").splitlines()
        checks.append(("checksum_ledger_exact",ledger == [f"{_sha(actual[name])}  {name}" for name in sorted(expected-{"checksums.txt"})]))
        manifest = FullNerUnblindManifest.model_validate_json(actual["manifest.json"])
        summary = FullNerUnblindSummary.model_validate_json(actual["summary.json"])
        preds = [FullNerUnblindPrediction.model_validate_json(raw) for raw in actual["selected_predictions.jsonl"].splitlines()]
        case_rows = [json.loads(raw) for raw in actual["cases.jsonl"].splitlines()]
        checks.append(("manifest_identity_and_lineage",manifest.evaluation_id==summary.evaluation_id==cfg["evaluation_id"] and
                      manifest.reference_annotations_sha256==cfg["expected_reference_sha256"] and
                      manifest.production_final_mentions_sha256==cfg["expected_production_sha256"] and
                      manifest.production_final_mention_count==cfg["expected_production_mention_count"]))
        checks.append(("manifest_file_hashes",manifest.files=={name:_sha(actual[name]) for name in sorted(expected-{"checksums.txt","manifest.json"})}))
        checks.append(("selected_predictions_count_exact",len(preds)==manifest.selected_prediction_count==summary.selected_prediction_count))
        checks.append(("case_count_and_order_exact",len(case_rows)==120 and
                       [case["audit_case_id"] for case in case_rows]==[row.audit_case_id for row in prep["rows"]]))
        checks.append(("primary_metric_panel_exact",summary.primary_micro==summary.metrics["balanced"]["typed_exact"]))
        checks.append(("no_mutation_inference_or_publication",not manifest.model_inference_executed and not manifest.production_mutated and
                       not manifest.reference_mutated and not manifest.policy_mutated and not manifest.publication_authorized and
                       not summary.threshold_tuning_executed and not summary.numerical_quality_pass_fail_decision_made))
    except (OSError,KeyError,TypeError,ValueError,FullNerUnblindError) as exc:
        error=str(exc)
        checks.append(("evaluation_recompute_and_schema",False))
    failed = [name for name, passed in checks if not passed]
    return {
        "report":"scientific_entity_full_ner_coverage_unblind_evaluation_v01",
        "evaluation_id":cfg["evaluation_id"], "checks":[{"name":name,"passed":ok} for name,ok in checks],
        "evaluation_validated":not failed,"evaluation_executed":not failed,
        "production_latest_unchanged":not failed,"reference_unchanged":not failed,"policy_unchanged":not failed,
        "model_inference_executed":False,"total_checks":len(checks),"required_failed_count":len(failed),"error":error,
        "next_slice":"review_full_ner_coverage_results_and_plan_v04_diagnostics" if not failed else "investigate_full_ner_evaluation",
    }
