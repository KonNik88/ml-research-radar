from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from radar_core.contracts.scientific_entity_fresh_heldout_frozen_inference import (
    ScientificEntityFreshHeldoutFrozenInferenceConfig,
    ScientificEntityFreshHeldoutFrozenInferenceError,
    load_scientific_entity_fresh_heldout_frozen_inference_config,
)

REPORT_NAME = "scientific_entity_fresh_heldout_frozen_inference_v02"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_fresh_heldout_frozen_inference_v0.2.yaml"
DEFAULT_CANONICAL = PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def _resolve(project_root: Path, path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


def _validate_runtime_config(
    *, project_root: Path, contract: ScientificEntityFreshHeldoutFrozenInferenceConfig
) -> dict[str, Any]:
    from radar_core.entities.scientific_entity_gliner import (
        gliner_config_sha256,
        load_gliner_config,
    )

    runtime_path = _resolve(project_root, contract.candidate.runtime_config_path)
    if not runtime_path.is_file():
        raise FileNotFoundError(runtime_path)
    runtime = load_gliner_config(runtime_path)
    runtime_sha = gliner_config_sha256(runtime)
    if runtime_sha != contract.candidate.runtime_config_sha256:
        raise ScientificEntityFreshHeldoutFrozenInferenceError(
            "Frozen v0.2c runtime config SHA-256 drifted"
        )
    checks = {
        "extractor_name": runtime.extractor.name == contract.candidate.extractor_name,
        "extractor_version": runtime.extractor.version == contract.candidate.extractor_version,
        "model_repository": runtime.model.repository == contract.candidate.model_repository,
        "model_revision": runtime.model.revision == contract.candidate.model_revision,
        "model_artifact_sha256": runtime.model.artifact_sha256 == contract.candidate.model_artifact_sha256,
        "raw_inference_floor": runtime.inference.threshold == contract.candidate.raw_inference_floor,
        "window_size_tokens": runtime.inference.window_size_tokens == contract.candidate.window_size_tokens,
        "window_overlap_tokens": runtime.inference.window_overlap_tokens == contract.candidate.window_overlap_tokens,
        "source_fields": [x.value for x in runtime.inference.source_fields] == contract.candidate.source_fields,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ScientificEntityFreshHeldoutFrozenInferenceError(
            "Frozen v0.2c runtime semantics drifted: " + ", ".join(failed)
        )
    labels = [item.entity_type.value for item in runtime.inference.labels]
    if labels != contract.candidate.entity_types:
        raise ScientificEntityFreshHeldoutFrozenInferenceError(
            "Frozen v0.2c entity taxonomy drifted"
        )
    return {"runtime_path": runtime_path, "runtime_sha256": runtime_sha}


def _validate_reference(
    *,
    project_root: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
) -> dict[str, Any]:
    from radar_core.entities.scientific_entity_fresh_heldout_reference import (
        validate_frozen_reference_evidence,
    )

    checks, summary = validate_frozen_reference_evidence(
        project_root=project_root,
        config_path=project_root / "configs" / "scientific_entity_fresh_heldout_reference_freeze_v0.2.yaml",
        sample_dir=sample_dir,
        canonical_path=canonical_path,
        development_package_dir=development_package_dir,
        reference_dir=reference_dir,
    )
    if any(not ok for _, ok, _ in checks) or summary["required_failed_count"] != 0:
        raise ScientificEntityFreshHeldoutFrozenInferenceError(
            "Frozen fresh-v0.2 reference evidence failed strict pre-inference validation"
        )
    return summary


def _assert_reference_matches_contract(
    summary: dict[str, Any],
    contract: ScientificEntityFreshHeldoutFrozenInferenceConfig,
) -> None:
    expected = contract.fresh_heldout
    facts = {
        "sample_id": summary.get("sample_id") == expected.sample_id,
        "review_id": summary.get("review_id") == expected.review_id,
        "document_count": summary.get("document_count") == expected.expected_document_count,
        "annotation_row_count": summary.get("annotation_row_count") == expected.expected_annotation_row_count,
        "reference_mention_count": summary.get("reference_mention_count") == expected.expected_reference_mention_count,
        "uncertain_reference_mention_count": summary.get("uncertain_reference_mention_count") == expected.expected_uncertain_reference_mention_count,
        "reference_count_by_type": summary.get("reference_count_by_type") == expected.expected_reference_count_by_type,
        "reference_adequacy_passed": summary.get("reference_adequacy_passed") is True,
        "prediction_blind": summary.get("prediction_blind") is True,
        "model_inference_executed": summary.get("model_inference_executed") is False,
        "evaluation_executed": summary.get("evaluation_executed") is False,
    }
    failed = [name for name, ok in facts.items() if not ok]
    if failed:
        raise ScientificEntityFreshHeldoutFrozenInferenceError(
            "Frozen reference lineage does not match inference contract: " + ", ".join(failed)
        )


def _run_existing_builder(**kwargs):
    from scripts.entities.build_scientific_entity_evidence_gliner import build_gliner_candidate
    return build_gliner_candidate(**kwargs)


def plan_or_execute_frozen_inference(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
    model_cache_dir: Path | None = None,
    allow_model_download: bool = False,
    execute: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    contract = load_scientific_entity_fresh_heldout_frozen_inference_config(config_path.resolve())
    runtime_info = _validate_runtime_config(project_root=project_root, contract=contract)

    sample_dir = sample_dir.resolve()
    reference_dir = reference_dir.resolve()
    development_package_dir = development_package_dir.resolve()
    canonical_path = canonical_path.resolve()
    sample_input = sample_dir / contract.execution.input_filename
    if not sample_input.is_file():
        raise FileNotFoundError(sample_input)

    reference_summary = _validate_reference(
        project_root=project_root,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        canonical_path=canonical_path,
    )
    _assert_reference_matches_contract(reference_summary, contract)

    output_root = _resolve(project_root, contract.execution.raw_output_root)
    output_dir = output_root / contract.execution.build_id
    already_executed = output_dir.exists()
    if execute and already_executed:
        raise FileExistsError(
            f"Frozen v0.2c fresh-heldout raw inference is one-shot and already exists: {output_dir}"
        )

    report: dict[str, Any] = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": contract.candidate.candidate_id,
        "runtime_config_sha256": runtime_info["runtime_sha256"],
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "reference_mention_count": contract.fresh_heldout.expected_reference_mention_count,
        "reference_validation_required_failed_count": reference_summary["required_failed_count"],
        "input_document_count": contract.fresh_heldout.expected_document_count,
        "build_id": contract.execution.build_id,
        "output_dir": str(output_dir).replace("\\", "/"),
        "one_shot_already_executed": already_executed,
        "plan_runs_model_inference": False,
        "model_inference_executed": False,
        "policy_applied": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "next_slice": contract.next_steps.after_plan,
    }
    if not execute:
        return report

    builder_report = _run_existing_builder(
        config_path=runtime_info["runtime_path"],
        input_path=sample_input,
        output_root=output_root,
        build_id=contract.execution.build_id,
        status=contract.execution.build_status,
        max_documents=contract.execution.max_documents,
        execute=True,
        allow_model_download=allow_model_download,
        model_cache_dir=model_cache_dir,
    )
    if builder_report.get("build_id") != contract.execution.build_id:
        raise ScientificEntityFreshHeldoutFrozenInferenceError("Existing builder returned unexpected build_id")
    if builder_report.get("input_document_count") != contract.execution.max_documents:
        raise ScientificEntityFreshHeldoutFrozenInferenceError("Existing builder processed unexpected document count")
    if builder_report.get("config_sha256") != contract.candidate.runtime_config_sha256:
        raise ScientificEntityFreshHeldoutFrozenInferenceError("Existing builder used unexpected runtime config")

    report.update(
        {
            "phase_complete": True,
            "one_shot_already_executed": True,
            "model_inference_executed": True,
            "raw_mention_count": builder_report.get("mention_count"),
            "extractor_fingerprint": builder_report.get("extractor_fingerprint"),
            "model_artifact_verified": builder_report.get("model_artifact_verified"),
            "backbone_config_verified": builder_report.get("backbone_config_verified"),
            "runtime_device_name": builder_report.get("runtime_device_name"),
            "inference_duration_seconds": builder_report.get("inference_duration_seconds"),
            "peak_cuda_memory_bytes": builder_report.get("peak_cuda_memory_bytes"),
            "next_slice": contract.next_steps.after_execute,
        }
    )
    return report


def _validate_existing_build(*, build_dir: Path, runtime_config_path: Path, model_cache_dir: Path | None):
    from scripts.validation.check_scientific_entity_gliner_build import validate_gliner_build
    return validate_gliner_build(
        build_dir=build_dir,
        config_path=runtime_config_path,
        model_cache_dir=model_cache_dir,
        write_reports=False,
    )


def validate_frozen_inference(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
    model_cache_dir: Path | None = None,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    project_root = project_root.resolve()
    contract = load_scientific_entity_fresh_heldout_frozen_inference_config(config_path.resolve())
    runtime_info = _validate_runtime_config(project_root=project_root, contract=contract)
    reference_summary = _validate_reference(
        project_root=project_root,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    _assert_reference_matches_contract(reference_summary, contract)

    output_root = _resolve(project_root, contract.execution.raw_output_root)
    build_dir = output_root / contract.execution.build_id
    raw_report = _validate_existing_build(
        build_dir=build_dir,
        runtime_config_path=runtime_info["runtime_path"],
        model_cache_dir=model_cache_dir,
    )
    checks: list[tuple[str, bool, str]] = []
    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("reference_validation_passed", reference_summary["required_failed_count"] == 0, reference_summary["required_failed_count"])
    add("raw_build_validation_passed", raw_report.get("required_failed_count") == 0, raw_report.get("required_failed_count"))
    add("raw_build_directory_exists", build_dir.is_dir(), build_dir)

    manifest = {}
    quality = {}
    if build_dir.is_dir():
        try:
            manifest = json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))
            quality = json.loads((build_dir / "data_quality_summary.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            add("raw_metadata_readable", False, exc)
        else:
            add("raw_metadata_readable", True, "")

    canonical_input = manifest.get("canonical_input") or {}
    extractor = manifest.get("extractor") or {}
    add("build_id_exact", manifest.get("build_id") == contract.execution.build_id, manifest.get("build_id"))
    add("candidate_status", manifest.get("status") == contract.execution.build_status, manifest.get("status"))
    add("input_document_count_48", canonical_input.get("document_count") == 48, canonical_input.get("document_count"))
    expected_input = (sample_dir.resolve() / contract.execution.input_filename).resolve()
    actual_input = _resolve(project_root, canonical_input.get("path", "")) if canonical_input.get("path") else Path()
    add("input_is_exact_fresh_sample", actual_input == expected_input, actual_input)
    add("runtime_config_sha_exact", extractor.get("config_sha256") == contract.candidate.runtime_config_sha256, extractor.get("config_sha256"))
    add("model_repository_exact", extractor.get("model_name") == contract.candidate.model_repository, extractor.get("model_name"))
    add("model_revision_exact", extractor.get("model_revision") == contract.candidate.model_revision, extractor.get("model_revision"))
    add("model_artifact_sha_exact", extractor.get("model_artifact_sha256") == contract.candidate.model_artifact_sha256, extractor.get("model_artifact_sha256"))
    add("raw_floor_exact", quality.get("threshold") == contract.candidate.raw_inference_floor, quality.get("threshold"))
    add("window_size_exact", quality.get("window_size_tokens") == 320, quality.get("window_size_tokens"))
    add("window_overlap_exact", quality.get("window_overlap_tokens") == 64, quality.get("window_overlap_tokens"))
    add("raw_mentions_present", isinstance(manifest.get("mention_count"), int) and manifest.get("mention_count", 0) > 0, manifest.get("mention_count"))
    add("no_policy_application_yet", True, "raw build only")
    add("no_evaluation_yet", True, "raw build only")
    add("no_acceptance_decision_yet", True, "raw build only")
    add("canonical_truth_not_mutated", manifest.get("canonical_truth_mutated") is False, manifest.get("canonical_truth_mutated"))
    add("production_not_selected", contract.safety.production_extractor_selected is False, "")
    add("full_corpus_not_authorized", contract.safety.full_corpus_build_authorized is False, "")

    failed = [name for name, ok, _ in checks if not ok]
    summary = {
        "report": REPORT_NAME,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "build_id": contract.execution.build_id,
        "input_document_count": canonical_input.get("document_count"),
        "raw_mention_count": manifest.get("mention_count"),
        "reference_mention_count": reference_summary["reference_mention_count"],
        "reference_validation_required_failed_count": reference_summary["required_failed_count"],
        "raw_build_validation_required_failed_count": raw_report.get("required_failed_count"),
        "model_inference_executed": build_dir.is_dir(),
        "policy_applied": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": contract.next_steps.after_validation,
    }
    return checks, summary
