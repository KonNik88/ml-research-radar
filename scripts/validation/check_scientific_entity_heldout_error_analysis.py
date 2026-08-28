from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from radar_core.entities.scientific_entity_heldout_error_analysis import load_config, load_json, load_jsonl, sha256_file
from scripts.entities.analyze_scientific_entity_heldout_errors import REQUIRED_OUTPUT_FILES, analyze_heldout_errors

ROOT = Path(__file__).resolve().parents[2]


def _check(name: str, ok: bool, details: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "ok": bool(ok)}
    if details:
        row["details"] = details
    return row


def _checksum_map(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, name = line.split("  ", 1)
        result[name] = digest
    return result


def validate_heldout_error_analysis(*, analysis_dir: Path, strict: bool = False, write_reports: bool = False) -> dict[str, Any]:
    del write_reports
    analysis_dir = analysis_dir.resolve()
    checks: list[dict[str, Any]] = []
    checks.append(_check("analysis_dir_exists", analysis_dir.is_dir()))
    if not analysis_dir.is_dir():
        return {"report": "scientific_entity_heldout_error_analysis", "summary": {"ok": False, "required_failed_count": 1}, "checks": checks}
    present = {p.name for p in analysis_dir.iterdir() if p.is_file()}
    checks.append(_check("exact_output_layout", present == set(REQUIRED_OUTPUT_FILES), f"present={sorted(present)}"))
    missing = [name for name in REQUIRED_OUTPUT_FILES if not (analysis_dir / name).is_file()]
    if missing:
        checks.append(_check("required_files_present", False, f"missing={missing}"))
        return _finalize(checks, analysis_dir, strict)
    checks.append(_check("required_files_present", True))
    for name in REQUIRED_OUTPUT_FILES:
        raw = (analysis_dir / name).read_bytes()
        checks.append(_check(f"lf_only::{name}", b"\r\n" not in raw and b"\r" not in raw))
    expected_checksums = _checksum_map(analysis_dir / "checksums.txt")
    for name in REQUIRED_OUTPUT_FILES:
        if name == "checksums.txt":
            continue
        checks.append(_check(f"checksum_matches::{name}", expected_checksums.get(name) == sha256_file(analysis_dir / name)))

    manifest = load_json(analysis_dir / "manifest.json")
    summary = load_json(analysis_dir / "summary.json")
    confusions = load_json(analysis_dir / "type_confusions.json")
    confidence = load_json(analysis_dir / "confidence_analysis.json")
    windowing_audit = load_json(analysis_dir / "gliner_windowing_completeness_audit.json")
    checks.extend([
        _check("analysis_only", manifest.get("analysis_only") is True),
        _check("heldout_consumed_for_future_v02_tuning", manifest.get("heldout_consumed_for_future_v02_tuning") is True),
        _check("model_inference_not_executed", manifest.get("model_inference_executed") is False),
        _check("threshold_tuning_not_executed", manifest.get("threshold_tuning_executed") is False),
        _check("canonical_truth_not_mutated", manifest.get("canonical_truth_mutated") is False),
        _check("not_reconcile_input", manifest.get("may_be_used_as_reconcile_input") is False),
        _check("production_not_selected", manifest.get("production_extractor_selected") is False),
        _check("full_corpus_not_authorized", manifest.get("full_corpus_build_authorized") is False),
        _check("publication_not_ready", manifest.get("publication_ready") is False),
        _check("summary_error_arithmetic", sum(summary.get("error_count_by_kind", {}).values()) == summary.get("error_count")),
        _check("type_mismatch_total_matches", confusions.get("total_type_mismatch_count") == summary.get("error_count_by_kind", {}).get("type_mismatch")),
        _check("confidence_not_probabilities", confidence.get("confidence_scores_reinterpreted_as_probabilities") is False),
        _check("gliner_windowing_audit_available", summary.get("gliner_windowing_completeness_audit_available") is True),
        _check("windowing_runtime_splitter_verified", windowing_audit.get("runtime_splitter_verification", {}).get("verified") is True or windowing_audit.get("runtime_splitter_verification", {}).get("required") is False),
        _check("whole_text_prefix_truncation_not_claimed", windowing_audit.get("adapter_windowing", {}).get("whole_text_prefix_truncation_applied_by_adapter") is False),
        _check("transformer_subword_limit_not_claimed", windowing_audit.get("transformer_subword_truncation_claim_made") is False),
        _check("summary_windowed_text_count_matches", summary.get("gliner_windowed_source_text_count") == windowing_audit.get("source_texts_requiring_multiple_windows_count")),
        _check("summary_inference_window_count_matches", summary.get("gliner_total_inference_window_count") == windowing_audit.get("total_adapter_inference_window_count")),
        _check("summary_uncovered_token_count_matches", summary.get("gliner_uncovered_splitter_token_count") == windowing_audit.get("uncovered_splitter_token_count")),
        _check("summary_wide_reference_count_matches", summary.get("gliner_reference_mentions_exceeding_model_max_width_count") == windowing_audit.get("reference_mentions_exceeding_model_max_width_count")),
        _check("summary_wide_fn_count_matches", summary.get("gliner_false_negative_references_exceeding_model_max_width_count") == windowing_audit.get("false_negative_references_exceeding_model_max_width_count")),
        _check("summary_markup_reference_count_matches", summary.get("gliner_markup_like_reference_mention_count") == windowing_audit.get("markup_like_reference_mention_count")),
    ])
    breakdown = summary.get("error_breakdown_by_type", {})
    breakdown_exact = sum(int(breakdown.get(entity_type, {}).get("exact_match", 0)) for entity_type in ("task", "method", "dataset", "metric", "model", "domain"))
    breakdown_relaxed = sum(int(breakdown.get(entity_type, {}).get("relaxed_only_match", 0)) for entity_type in ("task", "method", "dataset", "metric", "model", "domain"))
    breakdown_boundary = sum(int(breakdown.get(entity_type, {}).get("boundary_mismatch", 0)) for entity_type in ("task", "method", "dataset", "metric", "model", "domain"))
    breakdown_mismatch_ref = sum(int(breakdown.get(entity_type, {}).get("type_mismatch_as_reference", 0)) for entity_type in ("task", "method", "dataset", "metric", "model", "domain"))
    breakdown_mismatch_pred = sum(int(breakdown.get(entity_type, {}).get("type_mismatch_as_prediction", 0)) for entity_type in ("task", "method", "dataset", "metric", "model", "domain"))
    breakdown_fp = sum(int(breakdown.get(entity_type, {}).get("false_positive", 0)) for entity_type in ("task", "method", "dataset", "metric", "model", "domain"))
    breakdown_fn = sum(int(breakdown.get(entity_type, {}).get("false_negative", 0)) for entity_type in ("task", "method", "dataset", "metric", "model", "domain"))
    checks.extend([
        _check("per_type_exact_arithmetic", breakdown_exact == int(summary.get("exact_match_count", -1))),
        _check("per_type_relaxed_only_arithmetic", breakdown_relaxed == int(summary.get("relaxed_only_match_count", -1))),
        _check("per_type_boundary_arithmetic", breakdown_boundary == int(summary.get("error_count_by_kind", {}).get("boundary_mismatch", -1))),
        _check("per_type_type_mismatch_reference_arithmetic", breakdown_mismatch_ref == int(summary.get("error_count_by_kind", {}).get("type_mismatch", -1))),
        _check("per_type_type_mismatch_prediction_arithmetic", breakdown_mismatch_pred == int(summary.get("error_count_by_kind", {}).get("type_mismatch", -1))),
        _check("per_type_false_positive_arithmetic", breakdown_fp == int(summary.get("error_count_by_kind", {}).get("false_positive", -1))),
        _check("per_type_false_negative_arithmetic", breakdown_fn == int(summary.get("error_count_by_kind", {}).get("false_negative", -1))),
    ])


    config = load_config(Path(str(manifest["config_path"])))
    audit_cfg = config["gliner_windowing_audit"]
    checks.extend([
        _check("windowing_model_id_pinned", windowing_audit.get("checkpoint_model_id") == audit_cfg.get("checkpoint_model_id")),
        _check("windowing_revision_pinned", windowing_audit.get("checkpoint_revision") == audit_cfg.get("checkpoint_revision")),
        _check("windowing_model_max_len_pinned", int(windowing_audit.get("model_max_len", -1)) == int(audit_cfg.get("model_max_len", -2))),
        _check("windowing_model_max_width_pinned", int(windowing_audit.get("model_max_width", -1)) == int(audit_cfg.get("model_max_width", -2))),
        _check("windowing_splitter_type_pinned", windowing_audit.get("words_splitter_type") == audit_cfg.get("words_splitter_type")),
        _check("window_size_pinned", int(windowing_audit.get("adapter_windowing", {}).get("window_size_tokens", -1)) == int(audit_cfg.get("window_size_tokens", -2))),
        _check("window_overlap_pinned", int(windowing_audit.get("adapter_windowing", {}).get("window_overlap_tokens", -1)) == int(audit_cfg.get("window_overlap_tokens", -2))),
    ])

    audit_rows = windowing_audit.get("rows", [])
    all_windows = [window for row in audit_rows for window in row.get("windows", [])]
    checks.extend([
        _check("windowing_row_count", int(windowing_audit.get("text_count", -1)) == len(audit_rows)),
        _check("windowed_text_arithmetic", int(windowing_audit.get("source_texts_requiring_multiple_windows_count", -1)) == sum(int(bool(row.get("windowed"))) for row in audit_rows)),
        _check("inference_window_arithmetic", int(windowing_audit.get("total_adapter_inference_window_count", -1)) == len(all_windows)),
        _check("all_windows_within_model_max_len", all(int(window.get("splitter_token_count", -1)) <= int(windowing_audit.get("model_max_len", -2)) for window in all_windows)),
        _check("window_exceeds_model_max_len_zero", int(windowing_audit.get("window_exceeds_model_max_len_count", -1)) == 0),
        _check("all_source_tokens_covered", windowing_audit.get("all_source_splitter_tokens_covered_by_adapter_windows") is True and int(windowing_audit.get("uncovered_splitter_token_count", -1)) == 0),
        _check("wide_reference_arithmetic", int(windowing_audit.get("reference_mentions_exceeding_model_max_width_count", -1)) == len(windowing_audit.get("reference_mentions_exceeding_model_max_width", []))),
        _check("not_contained_reference_arithmetic", int(windowing_audit.get("reference_mentions_not_fully_contained_in_any_adapter_window_count", -1)) == len(windowing_audit.get("reference_mentions_not_fully_contained_in_any_adapter_window", []))),
        _check("markup_reference_arithmetic", int(windowing_audit.get("markup_like_reference_mention_count", -1)) == len(windowing_audit.get("markup_like_reference_mentions", []))),
    ])

    inputs = manifest.get("inputs", {})
    for label, info in inputs.items():
        path = Path(str(info["path"]))
        checks.append(_check(f"input_exists::{label}", path.is_file(), str(path)))
        if path.is_file():
            checks.append(_check(f"input_sha256::{label}", sha256_file(path) == info["sha256"]))

    examples = load_jsonl(analysis_dir / "error_examples.jsonl")
    documents_path = Path(str(inputs["documents"]["path"]))
    if documents_path.is_file():
        documents = {str(row["canonical_id"]): row for row in load_jsonl(documents_path)}
        for index, row in enumerate(examples):
            doc = documents.get(str(row.get("canonical_id")))
            field = str(row.get("source_field"))
            text = doc.get(field) if isinstance(doc, dict) else None
            for prefix in ("reference", "prediction"):
                start = row.get(f"{prefix}_char_start")
                end = row.get(f"{prefix}_char_end")
                surface = row.get(f"{prefix}_surface")
                if start is None or end is None:
                    checks.append(_check(f"example_surface_absent_without_span::{index}:{prefix}", surface is None))
                else:
                    expected_surface = text[int(start):int(end)] if isinstance(text, str) else None
                    checks.append(_check(f"example_surface_matches_source::{index}:{prefix}", surface == expected_surface))

    if bool(audit_cfg.get("runtime_splitter_verification_required", False)) and documents_path.is_file():
        try:
            from gliner.data_processing.tokenizer import WordsSplitter  # type: ignore
            runtime_splitter = WordsSplitter(str(audit_cfg["words_splitter_type"]))
            audit_by_key = {(str(row["canonical_id"]), str(row["source_field"])): row for row in audit_rows}
            runtime_ok = True
            runtime_checked = 0
            for doc in load_jsonl(documents_path):
                canonical_id = str(doc["canonical_id"])
                for field in ("title", "abstract"):
                    text = doc.get(field)
                    if not isinstance(text, str):
                        continue
                    token_count = len(list(runtime_splitter(text)))
                    row = audit_by_key.get((canonical_id, field))
                    if row is None or int(row.get("splitter_token_count", -1)) != token_count:
                        runtime_ok = False
                    runtime_checked += 1
            checks.append(_check("independent_gliner_runtime_splitter_counts", runtime_ok, f"checked={runtime_checked}"))
        except Exception as exc:
            checks.append(_check("independent_gliner_runtime_splitter_counts", False, str(exc)))

    matches_path = Path(str(inputs["matches"]["path"]))
    errors_path = Path(str(inputs["errors"]["path"]))
    if matches_path.is_file():
        match_kind_counts: dict[str, int] = {}
        for row in load_jsonl(matches_path):
            kind = str(row.get("match_kind"))
            match_kind_counts[kind] = match_kind_counts.get(kind, 0) + 1
        checks.extend([
            _check("input_exact_match_count", match_kind_counts.get("exact", 0) == int(summary.get("exact_match_count", -1))),
            _check("input_relaxed_match_count", match_kind_counts.get("relaxed", 0) == int(summary.get("relaxed_only_match_count", -1))),
            _check("input_match_kinds_known", set(match_kind_counts).issubset({"exact", "relaxed"}), str(sorted(match_kind_counts))),
        ])
    if errors_path.is_file():
        input_error_counts: dict[str, int] = {}
        for row in load_jsonl(errors_path):
            kind = str(row.get("error_kind"))
            input_error_counts[kind] = input_error_counts.get(kind, 0) + 1
        for kind in ("boundary_mismatch", "type_mismatch", "false_positive", "false_negative"):
            checks.append(_check(f"input_error_count::{kind}", input_error_counts.get(kind, 0) == int(summary.get("error_count_by_kind", {}).get(kind, -1))))

    evaluation_dir = Path(str(inputs["evaluation_manifest"]["path"])).parent
    with tempfile.TemporaryDirectory(prefix="scientific_entity_error_analysis_validate_") as tmp:
        temp_root = Path(tmp)
        recomputed_id = str(manifest["analysis_id"])
        report = analyze_heldout_errors(
            evaluation_dir=evaluation_dir,
            project_root=ROOT,
            config_path=Path(str(manifest["config_path"])),
            output_root=temp_root,
            analysis_id=recomputed_id,
            execute=True,
        )
        rebuilt = Path(str(report["output_dir"]))
        semantic_names = ("summary.json", "type_confusions.json", "confidence_analysis.json", "gliner_windowing_completeness_audit.json", "error_examples.jsonl")
        for name in semantic_names:
            checks.append(_check(f"deterministic_recomputation::{name}", (analysis_dir / name).read_bytes() == (rebuilt / name).read_bytes()))
    return _finalize(checks, analysis_dir, strict)


def _finalize(checks: list[dict[str, Any]], analysis_dir: Path, strict: bool) -> dict[str, Any]:
    failed = [row["name"] for row in checks if not row["ok"]]
    manifest = load_json(analysis_dir / "manifest.json") if (analysis_dir / "manifest.json").is_file() else {}
    summary = load_json(analysis_dir / "summary.json") if (analysis_dir / "summary.json").is_file() else {}
    report = {
        "report": "scientific_entity_heldout_error_analysis",
        "strict": bool(strict),
        "summary": {
            "ok": not failed,
            "total_checks": len(checks),
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "analysis_id": manifest.get("analysis_id"),
            "evaluation_id": manifest.get("evaluation_id"),
            "error_count": summary.get("error_count"),
            "type_mismatch_count": summary.get("error_count_by_kind", {}).get("type_mismatch"),
        },
        "checks": checks,
        "verdict": {
            "analysis_only": True,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "publication_ready": False,
            "next_slice": "review_error_analysis_then_freeze_one_v02_hypothesis",
        },
    }
    if strict and failed:
        raise SystemExit(1)
    return report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate immutable Scientific Entity held-out error analysis output.")
    p.add_argument("--analysis-dir", type=Path, required=True)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--no-write-reports", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = validate_heldout_error_analysis(
        analysis_dir=args.analysis_dir,
        strict=False,
        write_reports=not args.no_write_reports,
    )
    print(f"[OK] report={report['report']}")
    print(f"[OK] total_checks={report['summary']['total_checks']}")
    print(f"[OK] required_failed_count={report['summary']['required_failed_count']}")
    print(f"[OK] analysis_id={report['summary']['analysis_id']}")
    print(f"[OK] evaluation_id={report['summary']['evaluation_id']}")
    print(f"[OK] error_count={report['summary']['error_count']}")
    print(f"[OK] type_mismatch_count={report['summary']['type_mismatch_count']}")
    print("[OK] next_slice=review_error_analysis_then_freeze_one_v02_hypothesis")
    if args.strict and not report["summary"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
