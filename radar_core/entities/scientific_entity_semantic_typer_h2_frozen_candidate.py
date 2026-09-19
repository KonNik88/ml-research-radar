from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_frozen_candidate import (
    FROZEN_CANDIDATE_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    FrozenH2CandidateDefinition,
    load_h2_frozen_candidate_config,
    semantic_sha256,
)
from radar_core.contracts.scientific_entity_semantic_typer_revision_analysis import SelectedRevisionPolicy


REPORT_NAME = "scientific_entity_semantic_typer_h2_frozen_candidate_v03"
DEFAULT_CONFIG_RELATIVE = Path("configs/scientific_entity_semantic_typer_h2_frozen_candidate_v0.3.yaml")
REQUIRED_REVISION_FILES = (
    "manifest.json",
    "summary.json",
    "selected_policy.json",
    "checksums.txt",
)
REQUIRED_OUTPUT_FILES = (
    "manifest.json",
    "frozen_candidate.json",
    "selected_policy.json",
    "lineage.json",
    "README.md",
    "checksums.txt",
)


class H2FrozenCandidateError(ValueError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise H2FrozenCandidateError(f"Expected JSON object: {path}")
    return payload


def _json_bytes(payload: Any) -> bytes:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _checksums(payloads: dict[str, bytes]) -> bytes:
    return "".join(
        f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n"
        for name in sorted(payloads)
        if name != "checksums.txt"
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


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _validated_inputs(project_root: Path, config_path: Path, revision_analysis_dir: Path):
    config = load_h2_frozen_candidate_config(config_path)
    revision_dir = revision_analysis_dir.resolve()
    if not revision_dir.is_dir():
        raise FileNotFoundError(revision_dir)
    for name in REQUIRED_REVISION_FILES:
        if not (revision_dir / name).is_file():
            raise FileNotFoundError(revision_dir / name)

    revision_manifest = _read_json(revision_dir / "manifest.json")
    revision_summary = _read_json(revision_dir / "summary.json")
    revision_policy_raw = _read_json(revision_dir / "selected_policy.json")
    revision_policy = SelectedRevisionPolicy.model_validate(revision_policy_raw)

    if revision_manifest.get("schema_version") != config.freeze.required_revision_analysis_schema_version:
        raise H2FrozenCandidateError("revision analysis manifest schema drifted")
    if revision_manifest.get("parent_candidate_id") != config.freeze.required_revision_parent_candidate_id:
        raise H2FrozenCandidateError("revision parent candidate drifted")
    if revision_policy.status != config.freeze.required_revision_policy_status:
        raise H2FrozenCandidateError("revision policy is not selected")
    if revision_policy.policy_id != config.candidate.candidate_id:
        raise H2FrozenCandidateError("revision selected policy_id does not match H2 candidate_id")
    expected_policy = config.selected_policy
    comparisons = {
        "baseline_type": revision_policy.baseline_type.value == expected_policy.baseline_type.value,
        "semantic_typer_type": revision_policy.semantic_typer_type.value == expected_policy.semantic_typer_type.value,
        "score_field": revision_policy.score_field == expected_policy.score_field,
        "operator": revision_policy.operator == expected_policy.operator,
        "threshold": revision_policy.threshold == expected_policy.threshold,
        "selection_rule": revision_policy.selection_rule == expected_policy.selection_rule,
        "plateau": revision_policy.plateau_thresholds == expected_policy.expected_plateau_thresholds,
        "summary_threshold": revision_summary.get("selected_threshold") == expected_policy.threshold,
        "summary_plateau": revision_summary.get("selected_plateau_thresholds") == expected_policy.expected_plateau_thresholds,
        "summary_net": (revision_summary.get("selected_policy_metrics") or {}).get("net_corrected_cases") == expected_policy.expected_selected_net_corrected_cases,
        "summary_regression_rate": (revision_summary.get("selected_policy_metrics") or {}).get("regression_rate") == expected_policy.expected_selected_regression_rate,
        "summary_accuracy_delta": (revision_summary.get("selected_policy_metrics") or {}).get("same_span_accuracy_delta") == expected_policy.expected_selected_same_span_accuracy_delta,
        "no_new_inference": revision_summary.get("new_model_inference_executed") is False,
        "not_independent_acceptance": revision_summary.get("independent_acceptance_executed") is False,
    }
    failed = [name for name, ok in comparisons.items() if not ok]
    if failed:
        raise H2FrozenCandidateError("revision selected policy drifted: " + ", ".join(failed))

    parent_config_path = _resolve(project_root, config.candidate.parent_semantic_typer_config_path)
    parent_config = load_semantic_typer_config(parent_config_path)
    if parent_config.candidate.candidate_id != config.candidate.parent_semantic_typer_candidate_id:
        raise H2FrozenCandidateError("parent semantic typer candidate id drifted")
    if parent_config.candidate.upstream_candidate_id != config.candidate.parent_upstream_candidate_id:
        raise H2FrozenCandidateError("parent upstream candidate id drifted")
    parent_config_sha = semantic_typer_config_sha256(parent_config)
    return config, revision_manifest, revision_summary, revision_policy, parent_config_path, parent_config_sha


def _candidate_definition(*, config, revision_analysis_dir: Path, revision_manifest, revision_policy, parent_config_path: Path, parent_config_sha: str) -> FrozenH2CandidateDefinition:
    base = {
        "schema_version": FROZEN_CANDIDATE_SCHEMA_VERSION,
        "candidate_id": config.candidate.candidate_id,
        "candidate_status": config.candidate.status,
        "hypothesis": config.candidate.hypothesis,
        "parent_semantic_typer_candidate_id": config.candidate.parent_semantic_typer_candidate_id,
        "parent_semantic_typer_config_path": config.candidate.parent_semantic_typer_config_path,
        "parent_semantic_typer_config_sha256": parent_config_sha,
        "parent_upstream_candidate_id": config.candidate.parent_upstream_candidate_id,
        "revision_analysis_id": revision_manifest["analysis_id"],
        "revision_analysis_manifest_sha256": _sha256_file(revision_analysis_dir / "manifest.json"),
        "revision_selected_policy_sha256": _sha256_file(revision_analysis_dir / "selected_policy.json"),
        "baseline_type": revision_policy.baseline_type,
        "semantic_typer_type": revision_policy.semantic_typer_type,
        "score_field": revision_policy.score_field,
        "operator": revision_policy.operator,
        "threshold": revision_policy.threshold,
        "preserve_baseline_otherwise": True,
        "selection_rule": revision_policy.selection_rule,
        "plateau_thresholds": revision_policy.plateau_thresholds,
        "development_calibration_only": True,
        "independent_acceptance_executed": False,
        "requires_new_disjoint_prediction_blind_heldout": True,
    }
    fingerprint_payload = {k: v.value if hasattr(v, "value") else v for k, v in base.items() if k != "schema_version"}
    base["candidate_fingerprint_sha256"] = semantic_sha256(fingerprint_payload)
    return FrozenH2CandidateDefinition.model_validate(base)


def plan_or_execute_h2_candidate_freeze(
    *,
    project_root: Path,
    config_path: Path,
    revision_analysis_dir: Path,
    freeze_id: str | None = None,
    output_root: Path | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    config, revision_manifest, revision_summary, revision_policy, parent_config_path, parent_config_sha = _validated_inputs(
        root, config_path.resolve(), revision_analysis_dir.resolve()
    )
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if freeze_id is None:
        freeze_id = config.freeze.freeze_id_prefix + "-" + generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    selected_root = output_root.resolve() if output_root is not None else _resolve(root, config.freeze.output_root)
    output_dir = selected_root / freeze_id
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable H2 frozen candidate already exists: {output_dir}")

    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "freeze_id": freeze_id,
        "candidate_id": config.candidate.candidate_id,
        "revision_analysis_id": revision_manifest.get("analysis_id"),
        "revision_policy_selected": revision_policy.status == "selected",
        "policy_threshold_exposed_in_plan": False,
        "candidate_fingerprint_exposed_in_plan": False,
        "new_model_inference_executed": False,
        "threshold_tuning_executed": False,
        "independent_acceptance_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": "execute_h2_candidate_freeze_once",
    }
    if not execute:
        return report

    definition = _candidate_definition(
        config=config,
        revision_analysis_dir=revision_analysis_dir.resolve(),
        revision_manifest=revision_manifest,
        revision_policy=revision_policy,
        parent_config_path=parent_config_path,
        parent_config_sha=parent_config_sha,
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "freeze_id": freeze_id,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "candidate_id": definition.candidate_id,
        "candidate_fingerprint_sha256": definition.candidate_fingerprint_sha256,
        "revision_analysis_id": definition.revision_analysis_id,
        "revision_analysis_manifest_sha256": definition.revision_analysis_manifest_sha256,
        "revision_selected_policy_sha256": definition.revision_selected_policy_sha256,
        "parent_semantic_typer_config_sha256": definition.parent_semantic_typer_config_sha256,
        "development_evidence_consumed": True,
        "new_model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "independent_acceptance_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "future_candidate_requires_new_independent_heldout": True,
    }
    lineage = {
        "candidate_id": definition.candidate_id,
        "parent_semantic_typer_candidate_id": definition.parent_semantic_typer_candidate_id,
        "parent_upstream_candidate_id": definition.parent_upstream_candidate_id,
        "revision_analysis_id": definition.revision_analysis_id,
        "revision_parent_evaluation_id": revision_summary.get("parent_evaluation_id"),
        "revision_parent_decision": revision_summary.get("parent_decision"),
        "selected_policy_development_calibration_only": True,
        "new_independent_heldout_required_before_acceptance": True,
    }
    selected_policy_payload = revision_policy.model_dump(mode="json")
    readme = (
        "# Scientific Entity Semantic Typer v0.3 — Frozen H2 Candidate\n\n"
        "Immutable freeze of the development-selected H2 selective override policy.\n"
        "No model inference, threshold tuning, independent acceptance, production selection,\n"
        "or full-corpus execution occurs in this package. A new disjoint prediction-blind\n"
        "held-out is required before any acceptance decision.\n"
    ).encode("utf-8")
    payloads = {
        "manifest.json": _json_bytes(manifest),
        "frozen_candidate.json": _json_bytes(definition),
        "selected_policy.json": _json_bytes(selected_policy_payload),
        "lineage.json": _json_bytes(lineage),
        "README.md": readme,
    }
    payloads["checksums.txt"] = _checksums(payloads)
    _write_atomic(output_dir, payloads)
    report.update({
        "phase_complete": True,
        "policy_threshold": definition.threshold,
        "candidate_fingerprint_sha256": definition.candidate_fingerprint_sha256,
        "candidate_frozen": True,
        "next_slice": config.next_steps["after_freeze"],
    })
    return report


def validate_h2_candidate_freeze(
    *,
    project_root: Path,
    config_path: Path,
    revision_analysis_dir: Path,
    frozen_candidate_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    root = project_root.resolve()
    config, revision_manifest, revision_summary, revision_policy, parent_config_path, parent_config_sha = _validated_inputs(
        root, config_path.resolve(), revision_analysis_dir.resolve()
    )
    candidate_dir = frozen_candidate_dir.resolve()
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("candidate_dir_exists", candidate_dir.is_dir(), candidate_dir)
    for name in REQUIRED_OUTPUT_FILES:
        add(f"required_file:{name}", (candidate_dir / name).is_file(), name)
    if not candidate_dir.is_dir() or any(not (candidate_dir / name).is_file() for name in REQUIRED_OUTPUT_FILES):
        return checks, {
            "report": REPORT_NAME,
            "validation_scope": "h2_frozen_candidate",
            "total_checks": len(checks),
            "required_failed_count": sum(not ok for _, ok, _ in checks),
            "next_slice": "fix_h2_candidate_freeze_validation_failures",
        }

    stored_manifest = _read_json(candidate_dir / "manifest.json")
    stored_definition_raw = _read_json(candidate_dir / "frozen_candidate.json")
    stored_definition = FrozenH2CandidateDefinition.model_validate(stored_definition_raw)
    stored_policy = SelectedRevisionPolicy.model_validate(_read_json(candidate_dir / "selected_policy.json"))
    expected_definition = _candidate_definition(
        config=config,
        revision_analysis_dir=revision_analysis_dir.resolve(),
        revision_manifest=revision_manifest,
        revision_policy=revision_policy,
        parent_config_path=parent_config_path,
        parent_config_sha=parent_config_sha,
    )

    add("manifest_schema", stored_manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION, stored_manifest.get("schema_version"))
    add("candidate_id", stored_definition.candidate_id == config.candidate.candidate_id, stored_definition.candidate_id)
    add("candidate_status", stored_definition.candidate_status == "frozen_for_new_independent_acceptance", stored_definition.candidate_status)
    add("definition_exact", stored_definition == expected_definition, stored_definition.candidate_fingerprint_sha256)
    add("policy_exact", stored_policy == revision_policy, stored_policy.threshold)
    add("threshold_frozen", stored_definition.threshold == 0.1, stored_definition.threshold)
    add("preserve_baseline_otherwise", stored_definition.preserve_baseline_otherwise is True, stored_definition.preserve_baseline_otherwise)
    add("fingerprint_manifest_match", stored_manifest.get("candidate_fingerprint_sha256") == stored_definition.candidate_fingerprint_sha256, stored_manifest.get("candidate_fingerprint_sha256"))
    add("revision_analysis_match", stored_manifest.get("revision_analysis_id") == revision_manifest.get("analysis_id"), stored_manifest.get("revision_analysis_id"))
    add("parent_config_sha_match", stored_manifest.get("parent_semantic_typer_config_sha256") == parent_config_sha, stored_manifest.get("parent_semantic_typer_config_sha256"))
    add("no_new_model_inference", stored_manifest.get("new_model_inference_executed") is False, stored_manifest.get("new_model_inference_executed"))
    add("no_threshold_tuning", stored_manifest.get("threshold_tuning_executed") is False, stored_manifest.get("threshold_tuning_executed"))
    add("no_policy_revision", stored_manifest.get("policy_revision_executed") is False, stored_manifest.get("policy_revision_executed"))
    add("not_independent_acceptance", stored_manifest.get("independent_acceptance_executed") is False, stored_manifest.get("independent_acceptance_executed"))
    add("canonical_truth_not_mutated", stored_manifest.get("canonical_truth_mutated") is False, stored_manifest.get("canonical_truth_mutated"))
    add("production_not_selected", stored_manifest.get("production_extractor_selected") is False, stored_manifest.get("production_extractor_selected"))
    add("full_corpus_not_authorized", stored_manifest.get("full_corpus_build_authorized") is False, stored_manifest.get("full_corpus_build_authorized"))
    add("new_heldout_required", stored_manifest.get("future_candidate_requires_new_independent_heldout") is True, stored_manifest.get("future_candidate_requires_new_independent_heldout"))

    parsed_checksums: dict[str, str] = {}
    for line in (candidate_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        parsed_checksums[name] = digest
    for name in REQUIRED_OUTPUT_FILES:
        if name == "checksums.txt":
            continue
        add(f"checksum:{name}", parsed_checksums.get(name) == _sha256_file(candidate_dir / name), name)

    failed = sum(not ok for _, ok, _ in checks)
    return checks, {
        "report": REPORT_NAME,
        "validation_scope": "h2_frozen_candidate",
        "freeze_id": stored_manifest.get("freeze_id"),
        "candidate_id": stored_definition.candidate_id,
        "candidate_fingerprint_sha256": stored_definition.candidate_fingerprint_sha256,
        "policy_threshold": stored_definition.threshold,
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": config.next_steps["after_freeze"] if failed == 0 else "fix_h2_candidate_freeze_validation_failures",
    }


__all__ = [
    "REPORT_NAME",
    "H2FrozenCandidateError",
    "plan_or_execute_h2_candidate_freeze",
    "validate_h2_candidate_freeze",
]
