from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    SemanticTyperDevelopmentCase,
    SemanticTyperPrediction,
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.contracts.scientific_entity_semantic_typer_evaluation import (
    PREDICTION_PACKAGE_SCHEMA_VERSION,
    PREDICTION_SUMMARY_SCHEMA_VERSION,
)
from radar_core.entities.scientific_entity_gliner import (
    GLiNERBackend,
    load_gliner_config,
    load_native_gliner_backend,
    normalized_text_sha256,
)
from radar_core.entities.scientific_entity_semantic_typer import (
    semantic_typer_fingerprint,
    type_development_case,
)


REPORT_NAME = "scientific_entity_semantic_typer_candidate_inference_v03"
REQUIRED_FILES = (
    "manifest.json",
    "predictions.jsonl",
    "summary.json",
    "README.md",
    "checksums.txt",
)


class ScientificEntitySemanticTyperCandidateInferenceError(ValueError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScientificEntitySemanticTyperCandidateInferenceError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScientificEntitySemanticTyperCandidateInferenceError(f"Expected JSON object: {path}")
    return payload


def _read_cases(path: Path) -> tuple[SemanticTyperDevelopmentCase, ...]:
    rows: list[SemanticTyperDevelopmentCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                raise ScientificEntitySemanticTyperCandidateInferenceError(f"Blank JSONL line: {path}:{line_number}")
            rows.append(SemanticTyperDevelopmentCase.model_validate(json.loads(raw)))
    if len({row.case_id for row in rows}) != len(rows):
        raise ScientificEntitySemanticTyperCandidateInferenceError("Duplicate development case_id")
    return tuple(rows)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _prediction_bytes(rows: Sequence[SemanticTyperPrediction]) -> bytes:
    return "".join(
        json.dumps(row.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    ).encode("utf-8")


def _write_atomic(output_dir: Path, payloads: dict[str, bytes]) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, data in payloads.items():
            (temp / name).write_bytes(data)
        temp.rename(output_dir)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _checksums(payloads: dict[str, bytes]) -> bytes:
    names = sorted(name for name in payloads if name != "checksums.txt")
    return "".join(f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n" for name in names).encode("utf-8")


def _validate_development_package(*, package_dir: Path, config, config_path: Path) -> tuple[dict[str, Any], tuple[SemanticTyperDevelopmentCase, ...]]:
    manifest = _read_json(package_dir / "manifest.json")
    cases_path = package_dir / "development_cases.jsonl"
    cases = _read_cases(cases_path)
    if manifest.get("semantic_typer_candidate_id") != config.candidate.candidate_id:
        raise ScientificEntitySemanticTyperCandidateInferenceError("Development candidate_id drifted")
    if manifest.get("semantic_typer_config_sha256") != semantic_typer_config_sha256(config):
        raise ScientificEntitySemanticTyperCandidateInferenceError("Development semantic typer config hash drifted")
    if manifest.get("semantic_typer_fingerprint") != semantic_typer_fingerprint(config):
        raise ScientificEntitySemanticTyperCandidateInferenceError("Development semantic typer fingerprint drifted")
    if manifest.get("development_case_count") != len(cases):
        raise ScientificEntitySemanticTyperCandidateInferenceError("Development case count drifted")
    if manifest.get("development_cases_sha256") != _sha256_file(cases_path):
        raise ScientificEntitySemanticTyperCandidateInferenceError("Development cases SHA-256 drifted")
    if manifest.get("model_inference_executed") is not False:
        raise ScientificEntitySemanticTyperCandidateInferenceError("Development package must predate model inference")
    return manifest, cases


def plan_or_execute_semantic_typer_candidate_inference(
    *,
    project_root: Path,
    config_path: Path,
    package_dir: Path,
    prediction_id: str | None = None,
    output_root: Path | None = None,
    execute: bool = False,
    allow_model_download: bool = False,
    model_cache_dir: Path | None = None,
    backend: GLiNERBackend | None = None,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    config_path = config_path.resolve()
    package_dir = package_dir.resolve()
    config = load_semantic_typer_config(config_path)
    dev_manifest, cases = _validate_development_package(package_dir=package_dir, config=config, config_path=config_path)

    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at):
        raise ScientificEntitySemanticTyperCandidateInferenceError("generated_at_utc must be timezone-aware UTC")
    if prediction_id is None:
        prediction_id = "scientific-entity-semantic-typer-predictions-v0.3-" + generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    selected_root = output_root.resolve() if output_root is not None else (root / "data/entities/scientific_entity_semantic_typer_predictions/v0.3").resolve()
    output_dir = selected_root / prediction_id
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable semantic typer prediction output already exists: {output_dir}")

    report: dict[str, Any] = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "prediction_id": prediction_id,
        "package_id": dev_manifest.get("package_id"),
        "candidate_id": config.candidate.candidate_id,
        "case_count": len(cases),
        "primary_metric_eligible_count": sum(row.primary_metric_eligible for row in cases),
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "baseline_type_used_as_model_feature": False,
        "root_cause_used_as_model_feature": False,
        "span_mutated": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": "execute_bounded_semantic_typer_candidate_inference_once",
    }
    if not execute:
        return report

    selected_backend = backend
    runtime: dict[str, Any] = {"backend_injected_for_test": backend is not None}
    if selected_backend is None:
        upstream_path = (root / config.candidate.upstream_runtime_config_path).resolve()
        upstream = load_gliner_config(upstream_path)
        loaded = load_native_gliner_backend(
            config=upstream,
            allow_model_download=allow_model_download,
            cache_dir=model_cache_dir,
        )
        selected_backend = loaded.backend
        environment_lock = (root / upstream.extractor.environment_lock_path).resolve()
        runtime.update({
            "upstream_runtime_config_path": config.candidate.upstream_runtime_config_path,
            "upstream_runtime_config_sha256": normalized_text_sha256(upstream_path),
            "environment_lock_path": upstream.extractor.environment_lock_path,
            "environment_lock_sha256": normalized_text_sha256(environment_lock),
            "model_repository": upstream.model.repository,
            "model_revision": upstream.model.revision,
            "model_artifact_sha256": upstream.model.artifact_sha256,
            "model_artifact_verified": loaded.model_artifact_verified,
            "backbone_config_verified": loaded.backbone_config_verified,
            "model_weights_downloaded": loaded.model_weights_downloaded,
            "backbone_config_downloaded": loaded.backbone_config_downloaded,
        })

    predictions = tuple(type_development_case(config=config, case=case, backend=selected_backend) for case in cases)
    if [row.case_id for row in predictions] != [row.case_id for row in cases]:
        raise ScientificEntitySemanticTyperCandidateInferenceError("Prediction case order drifted")
    prediction_bytes = _prediction_bytes(predictions)
    fallback_count = sum(row.used_baseline_fallback for row in predictions)
    trimmed_count = sum(row.context_trimmed for row in predictions)
    summary = {
        "schema_version": PREDICTION_SUMMARY_SCHEMA_VERSION,
        "prediction_id": prediction_id,
        "package_id": dev_manifest.get("package_id"),
        "candidate_id": config.candidate.candidate_id,
        "case_count": len(predictions),
        "scored_case_count": len(predictions) - fallback_count,
        "fallback_count": fallback_count,
        "typer_coverage": round((len(predictions) - fallback_count) / len(predictions), 6) if predictions else 0.0,
        "context_trimmed_count": trimmed_count,
        "semantic_typer_fingerprint": semantic_typer_fingerprint(config),
        "model_inference_executed": True,
        "threshold_tuning_executed": False,
        "baseline_type_used_as_model_feature": False,
        "root_cause_used_as_model_feature": False,
        "span_mutated": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "future_candidate_requires_new_independent_heldout": True,
        "next_slice": "validate_and_evaluate_semantic_typer_candidate_predictions",
    }
    manifest = {
        "schema_version": PREDICTION_PACKAGE_SCHEMA_VERSION,
        "prediction_id": prediction_id,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "package_id": dev_manifest.get("package_id"),
        "development_manifest_sha256": _sha256_file(package_dir / "manifest.json"),
        "development_cases_sha256": _sha256_file(package_dir / "development_cases.jsonl"),
        "candidate_id": config.candidate.candidate_id,
        "semantic_typer_config_sha256": semantic_typer_config_sha256(config),
        "semantic_typer_fingerprint": semantic_typer_fingerprint(config),
        "predictions_file": "predictions.jsonl",
        "prediction_count": len(predictions),
        "predictions_sha256": hashlib.sha256(prediction_bytes).hexdigest(),
        "runtime": runtime,
        "model_inference_executed": True,
        "threshold_tuning_executed": False,
        "baseline_type_used_as_model_feature": False,
        "root_cause_used_as_model_feature": False,
        "span_mutated": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "future_candidate_requires_new_independent_heldout": True,
    }
    readme = (
        "# Scientific Entity Semantic Typer Candidate Predictions v0.3\n\n"
        "Bounded development-only second-stage semantic typing predictions over the immutable same-span development package.\n"
        "No span mutation, threshold tuning, production selection, or independent acceptance occurs here.\n"
    ).encode("utf-8")
    payloads = {
        "manifest.json": _json_bytes(manifest),
        "predictions.jsonl": prediction_bytes,
        "summary.json": _json_bytes(summary),
        "README.md": readme,
    }
    payloads["checksums.txt"] = _checksums(payloads)
    _write_atomic(output_dir, payloads)
    report.update({
        "phase_complete": True,
        "scored_case_count": summary["scored_case_count"],
        "fallback_count": fallback_count,
        "typer_coverage": summary["typer_coverage"],
        "model_inference_executed": True,
        "next_slice": "validate_and_evaluate_semantic_typer_candidate_predictions",
    })
    return report


def validate_semantic_typer_candidate_predictions(
    *,
    project_root: Path,
    config_path: Path,
    package_dir: Path,
    prediction_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    config = load_semantic_typer_config(config_path.resolve())
    dev_manifest, cases = _validate_development_package(package_dir=package_dir.resolve(), config=config, config_path=config_path.resolve())
    prediction_dir = prediction_dir.resolve()
    checks: list[tuple[str, bool, str]] = []
    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("prediction_dir_exists", prediction_dir.is_dir(), prediction_dir)
    for name in REQUIRED_FILES:
        add(f"required_file:{name}", (prediction_dir / name).is_file(), name)
    if not prediction_dir.is_dir():
        summary = {"report": REPORT_NAME, "validation_scope": "prediction_package", "total_checks": len(checks), "required_failed_count": sum(not row[1] for row in checks), "next_slice": "fix_prediction_package_validation_failures"}
        return checks, summary

    manifest = _read_json(prediction_dir / "manifest.json")
    summary_payload = _read_json(prediction_dir / "summary.json")
    predictions: list[SemanticTyperPrediction] = []
    with (prediction_dir / "predictions.jsonl").open("r", encoding="utf-8") as handle:
        for raw in handle:
            if raw.strip():
                predictions.append(SemanticTyperPrediction.model_validate(json.loads(raw)))
    add("schema_version", manifest.get("schema_version") == PREDICTION_PACKAGE_SCHEMA_VERSION)
    add("candidate_id", manifest.get("candidate_id") == config.candidate.candidate_id)
    add("package_id", manifest.get("package_id") == dev_manifest.get("package_id"))
    add("config_sha256", manifest.get("semantic_typer_config_sha256") == semantic_typer_config_sha256(config))
    add("typer_fingerprint", manifest.get("semantic_typer_fingerprint") == semantic_typer_fingerprint(config))
    add("development_manifest_sha256", manifest.get("development_manifest_sha256") == _sha256_file(package_dir / "manifest.json"))
    add("development_cases_sha256", manifest.get("development_cases_sha256") == _sha256_file(package_dir / "development_cases.jsonl"))
    add("prediction_count", manifest.get("prediction_count") == len(cases) == len(predictions))
    add("prediction_sha256", manifest.get("predictions_sha256") == _sha256_file(prediction_dir / "predictions.jsonl"))
    add("case_order", [row.case_id for row in predictions] == [row.case_id for row in cases])
    add("unique_case_ids", len({row.case_id for row in predictions}) == len(predictions))
    add("summary_count", summary_payload.get("case_count") == len(predictions))
    fallback_count = sum(row.used_baseline_fallback for row in predictions)
    expected_coverage = round((len(predictions) - fallback_count) / len(predictions), 6) if predictions else 0.0
    add("summary_fallback_count", summary_payload.get("fallback_count") == fallback_count)
    add("summary_coverage", summary_payload.get("typer_coverage") == expected_coverage)
    add("model_inference_true", manifest.get("model_inference_executed") is True and summary_payload.get("model_inference_executed") is True)
    add("threshold_tuning_false", manifest.get("threshold_tuning_executed") is False and summary_payload.get("threshold_tuning_executed") is False)
    add("baseline_not_feature", manifest.get("baseline_type_used_as_model_feature") is False and summary_payload.get("baseline_type_used_as_model_feature") is False)
    add("root_cause_not_feature", manifest.get("root_cause_used_as_model_feature") is False and summary_payload.get("root_cause_used_as_model_feature") is False)
    add("span_not_mutated", manifest.get("span_mutated") is False and summary_payload.get("span_mutated") is False)
    add("canonical_not_mutated", manifest.get("canonical_truth_mutated") is False and summary_payload.get("canonical_truth_mutated") is False)
    add("production_not_selected", manifest.get("production_extractor_selected") is False and summary_payload.get("production_extractor_selected") is False)
    add("full_corpus_false", manifest.get("full_corpus_build_authorized") is False and summary_payload.get("full_corpus_build_authorized") is False)
    checksums_text = (prediction_dir / "checksums.txt").read_text(encoding="utf-8")
    for name in REQUIRED_FILES:
        if name == "checksums.txt":
            continue
        add(f"checksum:{name}", f"{_sha256_file(prediction_dir / name)}  {name}" in checksums_text, name)

    failed = [row for row in checks if not row[1]]
    validation_summary = {
        "report": REPORT_NAME,
        "validation_scope": "prediction_package",
        "prediction_id": manifest.get("prediction_id"),
        "package_id": manifest.get("package_id"),
        "case_count": len(predictions),
        "fallback_count": fallback_count,
        "typer_coverage": expected_coverage,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": "evaluate_semantic_typer_candidate_against_frozen_baseline" if not failed else "fix_prediction_package_validation_failures",
    }
    return checks, validation_summary


__all__ = [
    "REPORT_NAME",
    "REQUIRED_FILES",
    "ScientificEntitySemanticTyperCandidateInferenceError",
    "plan_or_execute_semantic_typer_candidate_inference",
    "validate_semantic_typer_candidate_predictions",
]
