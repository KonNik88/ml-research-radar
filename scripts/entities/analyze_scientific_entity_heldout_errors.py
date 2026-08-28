from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.entities.scientific_entity_heldout_error_analysis import (
    compute_error_analysis,
    load_config,
    load_json,
    load_jsonl,
    resolve_project_path,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_heldout_error_analysis_v0.1.yaml"
REQUIRED_OUTPUT_FILES = (
    "manifest.json",
    "summary.json",
    "type_confusions.json",
    "confidence_analysis.json",
    "gliner_windowing_completeness_audit.json",
    "error_examples.jsonl",
    "README.md",
    "checksums.txt",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _analysis_id(now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-heldout-error-analysis-v0.1-{stamp}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _verify_file(path: Path, expected_sha: str | None, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if expected_sha and sha256_file(path) != expected_sha:
        raise ValueError(f"SHA256 mismatch for {label}: {path}")


def _resolve_inputs(project_root: Path, evaluation_dir: Path) -> dict[str, Path]:
    manifest_path = evaluation_dir / "manifest.json"
    manifest = load_json(manifest_path)
    canonical = manifest["canonical_input"]
    review = manifest["review"]
    prediction = manifest["prediction"]
    files = {
        "evaluation_manifest": manifest_path,
        "metrics": evaluation_dir / str(manifest["metrics_file"]),
        "per_type_metrics": evaluation_dir / str(manifest["per_type_metrics_file"]),
        "matches": evaluation_dir / str(manifest["matches_file"]),
        "errors": evaluation_dir / str(manifest["errors_file"]),
        "documents": resolve_project_path(project_root, str(canonical["path"])),
        "references": resolve_project_path(project_root, str(review["reference_mentions_path"])),
        "predictions": resolve_project_path(project_root, str(prediction["mentions_path"])),
    }
    checks = (
        (files["metrics"], str(manifest["metrics_sha256"]), "metrics"),
        (files["per_type_metrics"], str(manifest["per_type_metrics_sha256"]), "per_type_metrics"),
        (files["matches"], str(manifest["matches_sha256"]), "matches"),
        (files["errors"], str(manifest["errors_sha256"]), "errors"),
        (files["documents"], str(canonical["sha256"]), "canonical sample"),
        (files["references"], str(review["reference_mentions_sha256"]), "reference mentions"),
        (files["predictions"], str(prediction["mentions_sha256"]), "prediction mentions"),
    )
    for path, expected_sha, label in checks:
        _verify_file(path, expected_sha, label)
    return files


def analyze_heldout_errors(
    *,
    evaluation_dir: Path,
    project_root: Path = ROOT,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path | None = None,
    analysis_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    evaluation_dir = evaluation_dir.resolve()
    config = load_config(config_path)
    inputs = _resolve_inputs(project_root, evaluation_dir)
    evaluation_manifest = load_json(inputs["evaluation_manifest"])
    expected = config["expected"]
    if evaluation_manifest.get("evaluation_id") != expected["evaluation_id"]:
        raise ValueError("Configured evaluation_id does not match evaluation manifest")
    if evaluation_manifest["review"].get("review_id") != expected["heldout_review_id"]:
        raise ValueError("Configured heldout_review_id does not match evaluation manifest")
    if evaluation_manifest["prediction"].get("build_id") != expected["prediction_build_id"]:
        raise ValueError("Configured prediction_build_id does not match evaluation manifest")

    analysis = compute_error_analysis(
        metrics=load_json(inputs["metrics"]),
        per_type_metrics=load_json(inputs["per_type_metrics"]),
        matches=load_jsonl(inputs["matches"]),
        errors=load_jsonl(inputs["errors"]),
        predictions=load_jsonl(inputs["predictions"]),
        references=load_jsonl(inputs["references"]),
        documents=load_jsonl(inputs["documents"]),
        config=config,
    )
    now = generated_at_utc or _utc_now()
    resolved_id = analysis_id or _analysis_id(now)
    configured_root = resolve_project_path(project_root, str(config["output"]["root"]))
    output_root = (output_root or configured_root).resolve()
    output_dir = output_root / resolved_id

    manifest = {
        "schema_version": "scientific_entity_heldout_error_analysis_manifest_v0.1",
        "analysis_id": resolved_id,
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "evaluation_id": evaluation_manifest["evaluation_id"],
        "heldout_review_id": evaluation_manifest["review"]["review_id"],
        "prediction_build_id": evaluation_manifest["prediction"]["build_id"],
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "inputs": {
            key: {"path": str(path), "sha256": sha256_file(path)}
            for key, path in inputs.items()
        },
        "output_files": list(REQUIRED_OUTPUT_FILES[:-1]),
        "analysis_only": True,
        "heldout_consumed_for_future_v02_tuning": True,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "model_or_tokenizer_downloaded": False,
        "provider_api_called": False,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
    }

    report = {
        "report": "scientific_entity_heldout_error_analysis_v01",
        "mode": "execute" if execute else "plan",
        "phase_complete": bool(execute),
        "analysis_id": resolved_id,
        "evaluation_id": analysis["summary"]["evaluation_id"],
        "document_count": analysis["summary"]["document_count"],
        "reference_mention_count": analysis["summary"]["reference_mention_count"],
        "prediction_mention_count": analysis["summary"]["prediction_mention_count"],
        "exact_match_count": analysis["summary"]["exact_match_count"],
        "relaxed_only_match_count": analysis["summary"]["relaxed_only_match_count"],
        "error_count": analysis["summary"]["error_count"],
        "type_mismatch_count": analysis["summary"]["error_count_by_kind"]["type_mismatch"],
        "false_positive_count": analysis["summary"]["error_count_by_kind"]["false_positive"],
        "false_negative_count": analysis["summary"]["error_count_by_kind"]["false_negative"],
        "boundary_mismatch_count": analysis["summary"]["error_count_by_kind"]["boundary_mismatch"],
        "model_to_method_count": next((r["count"] for r in analysis["type_confusions"]["rows"] if r["reference_entity_type"] == "model" and r["prediction_entity_type"] == "method"), 0),
        "method_to_task_count": next((r["count"] for r in analysis["type_confusions"]["rows"] if r["reference_entity_type"] == "method" and r["prediction_entity_type"] == "task"), 0),
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "gliner_windowed_source_text_count": analysis["gliner_windowing_audit"]["source_texts_requiring_multiple_windows_count"],
        "gliner_total_inference_window_count": analysis["gliner_windowing_audit"]["total_adapter_inference_window_count"],
        "gliner_uncovered_splitter_token_count": analysis["gliner_windowing_audit"]["uncovered_splitter_token_count"],
        "gliner_reference_mentions_exceeding_model_max_width_count": analysis["gliner_windowing_audit"]["reference_mentions_exceeding_model_max_width_count"],
        "gliner_false_negative_references_exceeding_model_max_width_count": analysis["gliner_windowing_audit"]["false_negative_references_exceeding_model_max_width_count"],
        "gliner_markup_like_reference_mention_count": analysis["gliner_windowing_audit"]["markup_like_reference_mention_count"],
        "gliner_splitter_runtime_verified": analysis["gliner_windowing_audit"]["runtime_splitter_verification"]["verified"],
        "output_dir": str(output_dir),
        "next_slice": "review_error_analysis_then_freeze_one_v02_hypothesis",
    }
    if not execute:
        return report
    if output_dir.exists():
        raise FileExistsError(f"Output exists; overwrite is forbidden: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "summary.json", analysis["summary"])
    _write_json(output_dir / "type_confusions.json", analysis["type_confusions"])
    _write_json(output_dir / "confidence_analysis.json", analysis["confidence_analysis"])
    _write_json(output_dir / "gliner_windowing_completeness_audit.json", analysis["gliner_windowing_audit"])
    _write_jsonl(output_dir / "error_examples.jsonl", analysis["error_examples"])
    readme = f"""# Scientific Entity Held-Out Error Analysis v0.1\n\nAnalysis ID: `{resolved_id}`\n\nThis immutable local artifact analyzes the already-consumed v0.1 held-out evaluation.\nIt performs no model inference, threshold tuning, canonical mutation, production selection, full-corpus build, or publication.\n\nKey counts:\n\n- documents: {report['document_count']}\n- references: {report['reference_mention_count']}\n- predictions: {report['prediction_mention_count']}\n- exact matches: {report['exact_match_count']}\n- relaxed-only matches: {report['relaxed_only_match_count']}\n- errors: {report['error_count']}\n- type mismatches: {report['type_mismatch_count']}\n- model -> method: {report['model_to_method_count']}\n- method -> task: {report['method_to_task_count']}\n\nThe 48-paper sample remains valid independent held-out evidence for v0.1, but after this diagnostic analysis it is development/error-analysis evidence for any future v0.2 candidate.\n"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    checksum_targets = [name for name in REQUIRED_OUTPUT_FILES if name != "checksums.txt"]
    checksum_text = "".join(f"{sha256_file(output_dir / name)}  {name}\n" for name in checksum_targets)
    (output_dir / "checksums.txt").write_text(checksum_text, encoding="utf-8", newline="\n")
    return report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Analyze frozen Scientific Entity held-out evaluation errors without inference or tuning.")
    p.add_argument("--evaluation-dir", type=Path, required=True)
    p.add_argument("--project-root", type=Path, default=ROOT)
    p.add_argument("--config", dest="config_path", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--output-root", type=Path)
    p.add_argument("--analysis-id")
    p.add_argument("--execute", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    report = analyze_heldout_errors(**vars(parser().parse_args(argv)))
    for key, value in report.items():
        print(f"[OK] {key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
