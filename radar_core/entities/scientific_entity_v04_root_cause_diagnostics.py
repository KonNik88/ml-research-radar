"""Deterministic historical 9D error review queue; NEVER for model selection.

Input files are read-only: frozen reference annotations and immutable 9D evaluation.
No full production file is accessed. PLAN does not write anything.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


class RootCauseReviewError(ValueError):
    """The supplied historical evidence or the output workspace is invalid."""


BUCKETS = (
    "zero_prediction_title", "residual_fn", "residual_fp",
    "type_only_exact_span", "boundary_only_same_type", "boundary_and_type",
)
TYPES = frozenset(("task", "method", "model", "dataset", "metric", "domain"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha(path.read_bytes())


def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError, TypeError) as exc:
        raise RootCauseReviewError(f"Cannot parse {path}: {exc}") from exc


def _within_root(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise RootCauseReviewError("Path escapes repository root")
    return path


def _load(config_path: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or cfg.get("schema_version") != "scientific_entity_v04_root_cause_diagnostics_config_v0.1":
        raise RootCauseReviewError("Wrong review configuration schema")
    for required_false in ("model_inference_allowed", "production_prediction_file_read_allowed", "threshold_tuning_allowed", "publication_authorized"):
        if cfg.get(required_false) is not False:
            raise RootCauseReviewError(f"Safety guard must remain false: {required_false}")
    if cfg.get("historical_evaluation_only") is not True:
        raise RootCauseReviewError("Historical-only review guard not enabled")
    quotas = cfg.get("quotas", {})
    if set(quotas) != set(BUCKETS) or any(type(quotas[k]) is not int or quotas[k] < 0 for k in BUCKETS):
        raise RootCauseReviewError("Invalid quotas")
    if type(cfg.get("max_review_items_per_field")) is not int or cfg["max_review_items_per_field"] < 1:
        raise RootCauseReviewError("Invalid per-field cap")
    e = _within_root(root, cfg["evaluation_dir"])
    r = _within_root(root, cfg["reference_annotations_path"])
    # Integrity of the complete immutable 9D package, including its own manifest.
    names = {"README.md", "cases.jsonl", "manifest.json", "selected_predictions.jsonl", "summary.json"}
    ledger: dict[str, str] = {}
    for line in (e / "checksums.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64 or parts[1] in ledger:
            raise RootCauseReviewError("Invalid or duplicated 9D checksum ledger entry")
        ledger[parts[1]] = parts[0]
    if set(ledger) != names:
        raise RootCauseReviewError("9D checksum ledger has unexpected file layout")
    for name, expected_sha in ledger.items():
        if _file_sha(e / name) != expected_sha:
            raise RootCauseReviewError(f"9D checksum mismatch: {name}")
    manifest = json.loads((e / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("evaluation_id") != cfg["evaluation_id"] or manifest.get("reference_id") != cfg["reference_id"]:
        raise RootCauseReviewError("Evaluation/reference lineage mismatch")
    if not manifest.get("evaluation_executed") or manifest.get("model_inference_executed") is not False or manifest.get("production_mutated") is not False:
        raise RootCauseReviewError("Evaluation is not a validated non-mutating execution")
    expected = manifest.get("files", {})
    for name in ("README.md", "cases.jsonl", "selected_predictions.jsonl", "summary.json"):
        if _file_sha(e / name) != expected.get(name):
            raise RootCauseReviewError(f"9D file has changed: {name}")
    if _file_sha(r) != cfg["expected_reference_annotations_sha256"]:
        raise RootCauseReviewError("Frozen reference annotations SHA mismatch")
    cases = _rows(e / "cases.jsonl")
    preds = _rows(e / "selected_predictions.jsonl")
    annotations = _rows(r)
    if len(cases) != cfg["expected_evaluation_cases"] or len(preds) != cfg["expected_evaluation_predictions"]:
        raise RootCauseReviewError("9D input counts disagree with config")
    if len(annotations) != len(cases):
        raise RootCauseReviewError("Reference and 9D field counts differ")
    ann_by = {a["audit_case_id"]: a for a in annotations}
    if len(ann_by) != len(annotations):
        raise RootCauseReviewError("Duplicate case IDs in frozen reference")
    if len({c["audit_case_id"] for c in cases}) != len(cases):
        raise RootCauseReviewError("Duplicate 9D case IDs")
    pred_by = Counter(p["audit_case_id"] for p in preds)
    for case in cases:
        cid = case["audit_case_id"]
        ann = ann_by.get(cid)
        if ann is None:
            raise RootCauseReviewError(f"Missing frozen reference for {cid}")
        for k in ("canonical_id", "source_field", "source_text_sha256"):
            if case[k] != ann[k]:
                raise RootCauseReviewError(f"Case/reference mismatch for {cid}: {k}")
        if pred_by[cid] != case["prediction_count"]:
            raise RootCauseReviewError(f"Prediction count mismatch for {cid}")
        if not ann.get("annotation_complete"):
            raise RootCauseReviewError(f"Incomplete frozen reference at {cid}")
    if len(pred_by.keys() - ann_by.keys()):
        raise RootCauseReviewError("Predictions with unknown 9D case ID")
    return cfg, manifest, cases, ann_by


def _candidate(bucket: str, case: dict[str, Any], ann: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    reference = None
    prediction = None
    if bucket in ("residual_fn", "zero_prediction_title"):
        reference = {k: evidence[k] for k in ("start", "end", "surface", "type")}
    elif bucket == "residual_fp":
        prediction = {k: evidence[k] for k in ("start", "end", "surface", "type", "id")}
    else:
        reference = {"start": evidence["reference_start"], "end": evidence["reference_end"],
                     "surface": evidence["reference_surface"], "type": evidence["reference_type"]}
        prediction = {"start": evidence["prediction_start"], "end": evidence["prediction_end"],
                      "surface": evidence["prediction_surface"], "type": evidence["prediction_type"],
                      "id": evidence["prediction_id"]}
    source = ann["source_text"]
    for kind, entity in (("reference", reference), ("prediction", prediction)):
        if entity is None:
            continue
        if entity["type"] not in TYPES or not (0 <= entity["start"] < entity["end"] <= len(source)):
            raise RootCauseReviewError(f"Invalid {kind} span in {case['audit_case_id']}")
        if source[entity["start"]:entity["end"]] != entity["surface"]:
            raise RootCauseReviewError(f"Non-exact {kind} surface in {case['audit_case_id']}")
    kind_type = (reference or prediction)["type"]
    parts = [case["audit_case_id"], bucket, json.dumps(reference, sort_keys=True), json.dumps(prediction, sort_keys=True)]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return {
        "review_id": "v04-review:" + digest,
        "evidence_bucket": bucket,
        "audit_case_id": case["audit_case_id"],
        "canonical_id": case["canonical_id"],
        "source_field": case["source_field"],
        "source_text_sha256": case["source_text_sha256"],
        "source_text": source,
        "reference": reference,
        "prediction": prediction,
        "stratification_type": kind_type,
        "review_status": "pending",
        "root_cause": None,
        "annotation_guideline_question": None,
        "reviewer_notes": "",
        "suggested_hypothesis": "",
    }


def _pool(cases: list[dict[str, Any]], annotations: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    pool: dict[str, list[dict[str, Any]]] = {k: [] for k in BUCKETS}
    for case in cases:
        ann = annotations[case["audit_case_id"]]
        diagnostics = case["diagnostics"]
        for e in diagnostics["unmatched_gold_after_diagnosis"]:
            pool["residual_fn"].append(_candidate("residual_fn", case, ann, e))
            if case["source_field"] == "title" and case["prediction_count"] == 0:
                pool["zero_prediction_title"].append(_candidate("zero_prediction_title", case, ann, e))
        for e in diagnostics["unmatched_prediction_after_diagnosis"]:
            pool["residual_fp"].append(_candidate("residual_fp", case, ann, e))
        for e in diagnostics["diagnosed"]:
            b = e["category"]
            if b in pool:
                pool[b].append(_candidate(b, case, ann, e))
    for b in BUCKETS:
        ids = [item["review_id"] for item in pool[b]]
        if len(ids) != len(set(ids)):
            raise RootCauseReviewError(f"Duplicate review candidate identities: {b}")
    return pool


def _choose(pool: dict[str, list[dict[str, Any]]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    counts = Counter()
    selected_evidence: set[tuple[str, str, str]] = set()
    selected: list[dict[str, Any]] = []
    for b in BUCKETS:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for candidate in pool[b]:
            groups[(candidate["source_field"], candidate["stratification_type"])].append(candidate)
        for key, values in groups.items():
            values.sort(key=lambda c: hashlib.sha256((cfg["sampling_seed"] + c["review_id"]).encode()).hexdigest())
        # Cycle deterministically across (field, entity type) strata, allowing repeated
        # selection from strata while respecting the per-field review cap.
        active = sorted(groups, key=lambda k: (k[0] != "title", k[1]))
        picked = 0
        while active and picked < cfg["quotas"][b]:
            remaining = []
            changed = False
            for key in active:
                group = groups[key]
                while group and (
                    counts[group[0]["audit_case_id"]] >= cfg["max_review_items_per_field"]
                    or (
                        group[0]["audit_case_id"],
                        json.dumps(group[0]["reference"], sort_keys=True),
                        json.dumps(group[0]["prediction"], sort_keys=True),
                    ) in selected_evidence
                ):
                    group.pop(0)
                if group and picked < cfg["quotas"][b]:
                    item = group.pop(0)
                    selected.append(item)
                    selected_evidence.add((
                        item["audit_case_id"],
                        json.dumps(item["reference"], sort_keys=True),
                        json.dumps(item["prediction"], sort_keys=True),
                    ))
                    counts[item["audit_case_id"]] += 1
                    picked += 1
                    changed = True
                if group:
                    remaining.append(key)
            active = remaining
            if not changed:
                break
        if picked != cfg["quotas"][b]:
            raise RootCauseReviewError(f"Quota {b} impossible under field cap: requested={cfg['quotas'][b]}, selected={picked}")
    return selected


def _prepare(config_path: Path, repo_root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], Path]:
    cfg, manifest, cases, anns = _load(config_path, repo_root)
    output = _within_root(repo_root, cfg["output_dir"])
    pool = _pool(cases, anns)
    selection = _choose(pool, cfg)
    if len({x["review_id"] for x in selection}) != len(selection):
        raise RootCauseReviewError("Review IDs not unique")
    totals = Counter(x["evidence_bucket"] for x in selection)
    details = {
        "review_id": cfg["review_id"],
        "evaluation_id": cfg["evaluation_id"],
        "reference_id": cfg["reference_id"],
        "historical_evaluation_only": True,
        "candidate_pool_by_bucket": {k: len(pool[k]) for k in BUCKETS},
        "selected_by_bucket": {k: totals[k] for k in BUCKETS},
        "selected_by_field": dict(sorted(Counter(x["source_field"] for x in selection).items())),
        "selected_review_item_count": len(selection),
        "selected_distinct_case_count": len({x["audit_case_id"] for x in selection}),
        "source_9d_manifest_sha256": _file_sha(_within_root(repo_root, cfg["evaluation_dir"]) / "manifest.json"),
        "frozen_annotations_sha256": cfg["expected_reference_annotations_sha256"],
        "model_inference_executed": False,
        "full_production_predictions_read": False,
        "tuning_authorized": False,
    }
    return cfg, details, selection, output


def plan_root_cause_review(config_path: Path, repo_root: Path) -> dict[str, Any]:
    _, summary, _, output = _prepare(config_path, repo_root)
    return {
        "report": "scientific_entity_v04_root_cause_review_v01",
        "mode": "plan",
        "phase_complete": False,
        **summary,
        "output_already_exists": output.exists(),
        "plan_writes_output": False,
        "output_dir": str(output),
        "next_slice": "review_plan_and_commit_tooling_before_execute",
    }


def execute_root_cause_review(config_path: Path, repo_root: Path) -> dict[str, Any]:
    _, summary, selection, output = _prepare(config_path, repo_root)
    if output.exists():
        raise RootCauseReviewError("Review workspace already exists; no overwrite allowed")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".root_cause_review_", dir=output.parent))
    try:
        (temp / "review_items.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in selection), encoding="utf-8", newline="\n"
        )
        (temp / "sampling_manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        (temp / "README.md").write_text(
            "# Historical v0.4 root-cause review workspace\n\n"
            "Human diagnosis only; **NOT dev/training or an independent heldout**.\n"
            "Do not change gold spans/types, predictions, frozen 9D or H2 production artifacts.\n"
            "Complete `review_status`, `root_cause`, `annotation_guideline_question`, "
            "`reviewer_notes`, and `suggested_hypothesis` in a copy of `review_items.jsonl`.\n"
            "Do not publish or commit full field source texts by default.\n", encoding="utf-8", newline="\n"
        )
        # rename rather than replacing an existing directory
        if output.exists():
            raise RootCauseReviewError("Output appeared during preparation")
        os.rename(temp, output)
    finally:
        if temp.exists():
            for p in temp.iterdir():
                p.unlink()
            temp.rmdir()
    return {
        "report": "scientific_entity_v04_root_cause_review_v01",
        "mode": "execute",
        "phase_complete": True,
        **summary,
        "output_dir": str(output),
        "next_slice": "manual_review_historical_errors_then_fresh_dev_sampling",
    }
