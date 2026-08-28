from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_core.entities.scientific_entity_heldout_error_analysis import (
    _gliner_whitespace_split,
    compute_error_analysis,
    load_config,
)
from scripts.entities.analyze_scientific_entity_heldout_errors import analyze_heldout_errors, main
from scripts.validation.check_scientific_entity_heldout_error_analysis import validate_heldout_error_analysis

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_heldout_error_analysis_v0.1.yaml"
FIXED_TIME = datetime(2026, 8, 28, 10, 0, 0, tzinfo=timezone.utc)
FIXED_ID = "scientific-entity-heldout-error-analysis-fixture-v0.1"


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8", newline="\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> Path:
    docs = [
        {"canonical_id": "p1", "title": "Model A for task B", "abstract": "Model A uses Method C and Metric D."},
        {"canonical_id": "p2", "title": "Dataset Z", "abstract": "Method M solves Task T."},
        {"canonical_id": "p3", "title": "Vision domain", "abstract": "Domain evidence."},
    ]
    refs = [
        {"reference_id": "r1", "mention_id": "m1", "canonical_id": "p1", "source_field": "title", "surface": "Model A", "entity_type": "model", "char_start": 0, "char_end": 7},
        {"reference_id": "r2", "mention_id": "m2", "canonical_id": "p1", "source_field": "abstract", "surface": "Method C", "entity_type": "method", "char_start": 13, "char_end": 21},
        {"reference_id": "r3", "mention_id": "m3", "canonical_id": "p2", "source_field": "abstract", "surface": "Task T", "entity_type": "task", "char_start": 16, "char_end": 22},
        {"reference_id": "r4", "mention_id": "m4r", "canonical_id": "p3", "source_field": "title", "surface": "Vision", "entity_type": "domain", "char_start": 0, "char_end": 6},
    ]
    preds = [
        {"evidence_id": "e1", "mention_id": "m1x", "canonical_id": "p1", "source_field": "title", "surface": "Model A", "entity_type": "method", "char_start": 0, "char_end": 7, "confidence_score": 0.91},
        {"evidence_id": "e2", "mention_id": "m2", "canonical_id": "p1", "source_field": "abstract", "surface": "Method C", "entity_type": "method", "char_start": 13, "char_end": 21, "confidence_score": 0.88},
        {"evidence_id": "e3", "mention_id": "m4", "canonical_id": "p2", "source_field": "abstract", "surface": "Method M", "entity_type": "method", "char_start": 0, "char_end": 8, "confidence_score": 0.67},
        {"evidence_id": "e4", "mention_id": "m4p", "canonical_id": "p3", "source_field": "title", "surface": "Vision domain", "entity_type": "domain", "char_start": 0, "char_end": 13, "confidence_score": 0.8},
    ]
    matches = [
        {"evaluation_id": "fixture-eval", "match_id": "x1", "match_kind": "exact", "reference_id": "r2", "prediction_evidence_id": "e2", "canonical_id": "p1", "source_field": "abstract", "entity_type": "method"},
        {"evaluation_id": "fixture-eval", "match_id": "x2", "match_kind": "relaxed", "reference_id": "r4", "prediction_evidence_id": "e4", "canonical_id": "p3", "source_field": "title", "entity_type": "domain"},
    ]
    errors = [
        {"evaluation_id": "fixture-eval", "error_id": "z1", "error_kind": "type_mismatch", "canonical_id": "p1", "source_field": "title", "reference_id": "r1", "prediction_evidence_id": "e1", "reference_entity_type": "model", "prediction_entity_type": "method", "reference_char_start": 0, "reference_char_end": 7, "prediction_char_start": 0, "prediction_char_end": 7, "char_iou": 1.0},
        {"evaluation_id": "fixture-eval", "error_id": "z2", "error_kind": "false_positive", "canonical_id": "p2", "source_field": "abstract", "reference_id": None, "prediction_evidence_id": "e3", "reference_entity_type": None, "prediction_entity_type": "method", "reference_char_start": None, "reference_char_end": None, "prediction_char_start": 0, "prediction_char_end": 8, "char_iou": None},
        {"evaluation_id": "fixture-eval", "error_id": "z3", "error_kind": "false_negative", "canonical_id": "p2", "source_field": "abstract", "reference_id": "r3", "prediction_evidence_id": None, "reference_entity_type": "task", "prediction_entity_type": None, "reference_char_start": 16, "reference_char_end": 22, "prediction_char_start": None, "prediction_char_end": None, "char_iou": None},
    ]
    metrics = {
        "evaluation_id": "fixture-eval", "document_count": 3, "reference_mention_count": 4, "prediction_mention_count": 4,
        "exact_match_count": 1, "relaxed_only_match_count": 1,
        "error_count_by_kind": {"boundary_mismatch": 0, "type_mismatch": 1, "false_positive": 1, "false_negative": 1},
    }
    per_type_rows = []
    for entity_type in ("task", "method", "dataset", "metric", "model", "domain"):
        per_type_rows.append({"entity_type": entity_type, "metrics": {"exact": {"f1": 0.0, "precision": 0.0, "recall": 0.0}}})
    per_type = {"evaluation_id": "fixture-eval", "rows": per_type_rows}

    data = tmp_path / "data"
    documents = data / "docs.jsonl"; _jsonl(documents, docs)
    references = data / "refs.jsonl"; _jsonl(references, refs)
    predictions = data / "preds.jsonl"; _jsonl(predictions, preds)
    eval_dir = data / "evaluation"; eval_dir.mkdir()
    for name, payload in (("metrics.json", metrics), ("per_type_metrics.json", per_type)):
        _json(eval_dir / name, payload)
    _jsonl(eval_dir / "matches.jsonl", matches); _jsonl(eval_dir / "errors.jsonl", errors)
    manifest = {
        "evaluation_id": "fixture-eval",
        "canonical_input": {"path": str(documents), "sha256": _sha(documents), "document_count": 3},
        "review": {"review_id": "fixture-review", "reference_mentions_path": str(references), "reference_mentions_sha256": _sha(references), "reference_mention_count": 4},
        "prediction": {"build_id": "fixture-build", "mentions_path": str(predictions), "mentions_sha256": _sha(predictions), "mention_count": 4},
        "metrics_file": "metrics.json", "metrics_sha256": _sha(eval_dir / "metrics.json"),
        "per_type_metrics_file": "per_type_metrics.json", "per_type_metrics_sha256": _sha(eval_dir / "per_type_metrics.json"),
        "matches_file": "matches.jsonl", "matches_sha256": _sha(eval_dir / "matches.jsonl"),
        "errors_file": "errors.jsonl", "errors_sha256": _sha(eval_dir / "errors.jsonl"),
    }
    _json(eval_dir / "manifest.json", manifest)
    return eval_dir


def _fixture_config(tmp_path: Path) -> Path:
    text = CONFIG.read_text(encoding="utf-8")
    text = text.replace("scientific-entity-evaluation-v0.1-20260827T113112815887Z", "fixture-eval")
    text = text.replace("scientific-entity-heldout-review-v0.1-20260827T092900455472Z", "fixture-review")
    text = text.replace("scientific-entity-gliner-small-v2.5-heldout-frozen-policy-v0.1-20260827T112658493807Z", "fixture-build")
    replacements = {"document_count: 48": "document_count: 3", "reference_mention_count: 881": "reference_mention_count: 4", "prediction_mention_count: 787": "prediction_mention_count: 4", "exact_match_count: 331": "exact_match_count: 1", "relaxed_only_match_count: 15": "relaxed_only_match_count: 1", "error_count: 808": "error_count: 3", "boundary_mismatch: 22": "boundary_mismatch: 0", "type_mismatch: 176": "type_mismatch: 1", "false_positive: 258": "false_positive: 1", "false_negative: 352": "false_negative: 1"}
    for old, new in replacements.items(): text = text.replace(old, new)
    text = text.replace("runtime_splitter_verification_required: true", "runtime_splitter_verification_required: false")
    path = tmp_path / "config.yaml"; path.write_text(text, encoding="utf-8", newline="\n")
    return path


def test_config_is_analysis_only_and_fail_closed() -> None:
    config = load_config(CONFIG)
    assert config["safety"]["analysis_only"] is True
    assert config["safety"]["model_inference_allowed"] is False
    assert config["safety"]["threshold_tuning_allowed"] is False
    assert config["safety"]["full_corpus_build_authorized"] is False


def test_plan_is_non_writing_and_computes_confusion(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path)
    output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, generated_at_utc=FIXED_TIME)
    assert report["mode"] == "plan"
    assert report["model_to_method_count"] == 1
    assert report["method_to_task_count"] == 0
    assert report["model_inference_executed"] is False
    assert not output_root.exists()


def test_execute_writes_immutable_eight_file_artifact(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path); output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)
    output = Path(report["output_dir"])
    assert {p.name for p in output.iterdir()} == {"manifest.json", "summary.json", "type_confusions.json", "confidence_analysis.json", "gliner_windowing_completeness_audit.json", "error_examples.jsonl", "README.md", "checksums.txt"}
    with pytest.raises(FileExistsError):
        analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)


def test_confidence_analysis_separates_correct_and_semantic_errors(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path); output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)
    confidence = json.loads((Path(report["output_dir"]) / "confidence_analysis.json").read_text(encoding="utf-8"))
    assert confidence["groups"]["exact"]["median"] == 0.88
    assert confidence["groups"]["type_mismatch"]["median"] == 0.91
    assert confidence["groups"]["false_positive"]["median"] == 0.67


def test_relaxed_match_kind_is_counted_in_per_type_breakdown(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path); output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)
    summary = json.loads((Path(report["output_dir"]) / "summary.json").read_text(encoding="utf-8"))
    assert summary["relaxed_only_match_count"] == 1
    assert summary["error_breakdown_by_type"]["domain"]["relaxed_only_match"] == 1
    assert sum(row["relaxed_only_match"] for row in summary["error_breakdown_by_type"].values()) == 1



def test_representative_examples_are_grouped_by_actionable_family(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path); output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)
    rows = [json.loads(line) for line in (Path(report["output_dir"]) / "error_examples.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    families = {row["family"] for row in rows}
    assert "type_mismatch:model->method" in families
    assert "false_positive:method" in families
    assert "false_negative:task" in families

def test_representative_examples_materialize_exact_surfaces_from_source(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path); output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)
    rows = [json.loads(line) for line in (Path(report["output_dir"]) / "error_examples.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    mismatch = next(row for row in rows if row["family"] == "type_mismatch:model->method")
    assert mismatch["reference_surface"] == "Model A"
    assert mismatch["prediction_surface"] == "Model A"
    fn = next(row for row in rows if row["family"] == "false_negative:task")
    assert fn["reference_surface"] == "Task T"
    assert fn["prediction_surface"] is None


def test_gliner_whitespace_split_matches_documented_punctuation_semantics() -> None:
    assert [token for token, _, _ in _gliner_whitespace_split("Acme, Inc.")] == ["Acme", ",", "Inc", "."]
    assert [token for token, _, _ in _gliner_whitespace_split("long-term model_v2")] == ["long-term", "model_v2"]


def test_windowing_audit_covers_long_text_without_whole_text_prefix_truncation(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path)
    # Make the adapter windows deliberately small while preserving max-width overlap.
    cfg = config.read_text(encoding="utf-8")
    cfg = cfg.replace("model_max_len: 768", "model_max_len: 16")
    cfg = cfg.replace("model_max_width: 12", "model_max_width: 4")
    cfg = cfg.replace("window_size_tokens: 320", "window_size_tokens: 8")
    cfg = cfg.replace("window_overlap_tokens: 64", "window_overlap_tokens: 4")
    config.write_text(cfg, encoding="utf-8", newline="\n")
    output_root = tmp_path / "out"
    report = analyze_heldout_errors(
        evaluation_dir=eval_dir,
        project_root=ROOT,
        config_path=config,
        output_root=output_root,
        analysis_id=FIXED_ID,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    audit = json.loads(
        (Path(report["output_dir"]) / "gliner_windowing_completeness_audit.json").read_text(encoding="utf-8")
    )
    assert audit["adapter_windowing"]["whole_text_prefix_truncation_applied_by_adapter"] is False
    assert audit["source_texts_requiring_multiple_windows_count"] >= 1
    assert audit["total_adapter_inference_window_count"] > audit["text_count"]
    assert audit["window_exceeds_model_max_len_count"] == 0
    assert audit["uncovered_splitter_token_count"] == 0
    assert audit["all_source_splitter_tokens_covered_by_adapter_windows"] is True
    assert audit["transformer_subword_truncation_claim_made"] is False


def test_windowing_audit_flags_reference_span_wider_than_model_max_width(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path)
    refs_path = tmp_path / "data" / "refs.jsonl"
    refs = [json.loads(line) for line in refs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Expand r3 to a markup-like span containing more splitter tokens than a tiny max_width.
    abstract = "Method M solves Task T."
    refs[2]["char_start"] = 0
    refs[2]["char_end"] = len(abstract)
    refs[2]["surface"] = abstract
    _jsonl(refs_path, refs)
    errors_path = eval_dir / "errors.jsonl"
    errors = [json.loads(line) for line in errors_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    z3 = next(row for row in errors if row["error_id"] == "z3")
    z3["reference_char_start"] = 0
    z3["reference_char_end"] = len(abstract)
    _jsonl(errors_path, errors)
    manifest_path = eval_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["review"]["reference_mentions_sha256"] = _sha(refs_path)
    manifest["errors_sha256"] = _sha(errors_path)
    _json(manifest_path, manifest)
    cfg = config.read_text(encoding="utf-8").replace("model_max_width: 12", "model_max_width: 3")
    config.write_text(cfg, encoding="utf-8", newline="\n")
    output_root = tmp_path / "out"
    report = analyze_heldout_errors(
        evaluation_dir=eval_dir,
        project_root=ROOT,
        config_path=config,
        output_root=output_root,
        analysis_id=FIXED_ID,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    audit = json.loads(
        (Path(report["output_dir"]) / "gliner_windowing_completeness_audit.json").read_text(encoding="utf-8")
    )
    assert audit["reference_mentions_exceeding_model_max_width_count"] >= 1
    wide = next(row for row in audit["reference_mentions_exceeding_model_max_width"] if row["reference_id"] == "r3")
    assert wide["splitter_token_width"] > 3
    assert wide["is_false_negative"] is True


def test_validator_accepts_and_recomputes_valid_artifact(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path); output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)
    checked = validate_heldout_error_analysis(analysis_dir=Path(report["output_dir"]), write_reports=False)
    assert checked["summary"]["ok"] is True
    assert checked["summary"]["required_failed_count"] == 0


def test_validator_detects_relaxed_breakdown_arithmetic_even_with_updated_checksum(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path); output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)
    output = Path(report["output_dir"]); summary_path = output / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["error_breakdown_by_type"]["domain"]["relaxed_only_match"] = 0
    _json(summary_path, summary)
    checksums_path = output / "checksums.txt"
    lines = []
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name == "summary.json":
            digest = _sha(summary_path)
        lines.append(f"{digest}  {name}\n")
    checksums_path.write_text("".join(lines), encoding="utf-8", newline="\n")
    checked = validate_heldout_error_analysis(analysis_dir=output, write_reports=False)
    assert checked["summary"]["ok"] is False
    assert "per_type_relaxed_only_arithmetic" in checked["summary"]["required_failed_checks"]


def test_validator_detects_tampering(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path); output_root = tmp_path / "out"
    report = analyze_heldout_errors(evaluation_dir=eval_dir, project_root=ROOT, config_path=config, output_root=output_root, analysis_id=FIXED_ID, execute=True, generated_at_utc=FIXED_TIME)
    output = Path(report["output_dir"]); summary = output / "summary.json"
    summary.write_text(summary.read_text(encoding="utf-8") + " ", encoding="utf-8", newline="\n")
    checked = validate_heldout_error_analysis(analysis_dir=output, write_reports=False)
    assert checked["summary"]["ok"] is False
    assert "checksum_matches::summary.json" in checked["summary"]["required_failed_checks"]


def test_cli_entrypoint_uses_config_dest_correctly(tmp_path: Path) -> None:
    eval_dir = _fixture(tmp_path); config = _fixture_config(tmp_path)
    assert main(["--evaluation-dir", str(eval_dir), "--config", str(config), "--output-root", str(tmp_path / "out"), "--analysis-id", FIXED_ID]) == 0
