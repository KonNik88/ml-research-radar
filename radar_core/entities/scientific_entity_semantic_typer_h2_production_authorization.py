"""Plan, execute, and validate an immutable H2 production candidate-build authorization."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_authorization import (
    H2ProductionAuthorizationConfig,
    H2ProductionAuthorizationManifest,
    H2ProductionAuthorizationRecord,
    canonical_config_sha256,
    load_h2_production_authorization_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_authorization_gate import (
    canonical_config_sha256 as gate_config_sha256,
    load_h2_production_authorization_gate_config,
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANONICAL = PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def _run_gate_validation(**kwargs: Any):
    from radar_core.entities.scientific_entity_semantic_typer_h2_production_authorization_gate import (
        validate_h2_production_authorization_gate,
    )
    return validate_h2_production_authorization_gate(**kwargs)

DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_authorization_v0.3.yaml"
REPORT_NAME = "scientific_entity_semantic_typer_h2_production_authorization_v03"
REQUIRED_FILES = ("README.md", "authorization.json", "manifest.json", "checksums.txt")
CHECKSUM_FILES = REQUIRED_FILES[:-1]


def _resolve(project_root: Path, path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


def _normalized_relative_path(project_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_snapshot(project_root: Path, canonical_path: Path) -> dict[str, Any]:
    canonical_path = _resolve(project_root, canonical_path)
    if not canonical_path.is_file():
        raise FileNotFoundError(f"Canonical snapshot not found: {canonical_path}")
    count = 0
    with canonical_path.open("rb") as handle:
        for raw_line in handle:
            if raw_line.strip():
                count += 1
    if count <= 0:
        raise ValueError("Canonical snapshot contains no non-empty JSONL rows")
    return {
        "path": _normalized_relative_path(project_root, canonical_path),
        "sha256": _sha256_file(canonical_path),
        "document_count": count,
    }


def build_authorization_id(
    config: H2ProductionAuthorizationConfig,
    *,
    canonical_sha256: str,
) -> str:
    return (
        f"{config.execution.authorization_id_prefix}-"
        f"{canonical_sha256[:config.execution.canonical_sha256_prefix_length]}-"
        f"{config.lineage.candidate_fingerprint_sha256[:config.execution.candidate_fingerprint_prefix_length]}"
    )


def _json_bytes(model: Any) -> bytes:
    payload = model.model_dump(mode="json") if hasattr(model, "model_dump") else model
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _checksums(payloads: dict[str, bytes]) -> bytes:
    lines = [f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}" for name in sorted(payloads)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _readme(record: H2ProductionAuthorizationRecord) -> bytes:
    text = f"""# H2 v0.3 production candidate-build authorization

Authorization ID: `{record.authorization_id}`

Candidate: `{record.candidate_id}`

Candidate fingerprint: `{record.candidate_fingerprint_sha256}`

Canonical snapshot: `{record.canonical_path}`

Canonical SHA-256: `{record.canonical_sha256}`

Canonical document count: `{record.canonical_document_count}`

This immutable record authorizes exactly one timestamped full-corpus **candidate** materialization using the frozen H2 bounded semantic typing intervention.

It does **not** authorize production/latest promotion, canonical mutation, overwrite of a trusted latest entity build, or publication. The candidate build must preserve this exact canonical snapshot, candidate fingerprint, and frozen H2 policy, then pass its own validation before a separate promotion decision may be made.
"""
    return text.encode("utf-8")


def _validate_upstream(
    *,
    project_root: Path,
    config_path: Path,
    decision_dir: Path,
    evaluation_dir: Path,
    inference_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
) -> dict[str, Any]:
    config = load_h2_production_authorization_config(config_path)
    gate_path = _resolve(project_root, config.lineage.production_authorization_gate_config_path)
    gate_config = load_h2_production_authorization_gate_config(gate_path)
    gate_sha = gate_config_sha256(gate_config)
    if gate_sha != config.lineage.production_authorization_gate_config_sha256:
        raise ValueError("Production authorization gate config SHA-256 drift")
    if gate_config.acceptance_lineage.candidate_id != config.lineage.candidate_id:
        raise ValueError("Candidate ID drift between production gate and authorization config")
    if gate_config.acceptance_lineage.candidate_fingerprint_sha256 != config.lineage.candidate_fingerprint_sha256:
        raise ValueError("Candidate fingerprint drift between production gate and authorization config")
    if gate_config.acceptance_lineage.acceptance_decision_id != config.lineage.acceptance_decision_id:
        raise ValueError("Acceptance decision ID drift between production gate and authorization config")
    if gate_config.acceptance_lineage.required_acceptance_decision != config.lineage.required_acceptance_decision:
        raise ValueError("Required acceptance decision drift")

    policy = config.bounded_intervention
    gate_policy = gate_config.bounded_intervention
    if (
        policy.baseline_type != gate_policy.baseline_type
        or policy.semantic_typer_type != gate_policy.semantic_typer_type
        or policy.score_field != gate_policy.score_field
        or policy.operator != gate_policy.operator
        or policy.threshold != gate_policy.threshold
        or policy.preserve_baseline_otherwise != gate_policy.preserve_baseline_otherwise
        or policy.source_surface_policy != gate_policy.source_surface_policy
    ):
        raise ValueError("Frozen H2 policy drift between production gate and authorization config")

    gate_checks, gate_summary = _run_gate_validation(
        project_root=project_root,
        config_path=gate_path,
        decision_dir=decision_dir,
        evaluation_dir=evaluation_dir,
        inference_dir=inference_dir,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir,
        canonical_path=canonical_path,
    )
    if gate_summary.get("required_failed_count") != config.lineage.expected_gate_validation_required_failed_count:
        raise ValueError("Production authorization gate strict validation failed")
    if gate_summary.get("total_checks") != config.lineage.expected_gate_validation_total_checks:
        raise ValueError("Production authorization gate validation check count drift")
    if not all(ok for _, ok, _ in gate_checks):
        raise ValueError("At least one production authorization gate check failed")
    if not gate_summary.get("accepted_independent_decision_verified"):
        raise ValueError("Accepted independent H2 decision not verified")
    if gate_summary.get("production_authorization_made"):
        raise ValueError("Production authorization gate unexpectedly reports prior authorization")
    if gate_summary.get("full_corpus_candidate_build_authorized"):
        raise ValueError("Production gate must not itself authorize candidate build")
    if gate_summary.get("production_latest_promotion_authorized"):
        raise ValueError("Production gate must not authorize latest promotion")

    snapshot = _canonical_snapshot(project_root, canonical_path)
    authorization_id = build_authorization_id(config, canonical_sha256=snapshot["sha256"])
    return {
        "config": config,
        "gate_sha": gate_sha,
        "gate_validation_total_checks": gate_summary["total_checks"],
        "snapshot": snapshot,
        "authorization_id": authorization_id,
    }


def _expected_payloads(parent: dict[str, Any]) -> dict[str, bytes]:
    config: H2ProductionAuthorizationConfig = parent["config"]
    snapshot = parent["snapshot"]
    record = H2ProductionAuthorizationRecord(
        authorization_id=parent["authorization_id"],
        authorization_scope=config.authorization_boundary.authorization_scope,
        gate_config_sha256=parent["gate_sha"],
        acceptance_decision_id=config.lineage.acceptance_decision_id,
        candidate_id=config.lineage.candidate_id,
        candidate_fingerprint_sha256=config.lineage.candidate_fingerprint_sha256,
        canonical_path=snapshot["path"],
        canonical_sha256=snapshot["sha256"],
        canonical_document_count=snapshot["document_count"],
    )
    payloads: dict[str, bytes] = {
        "authorization.json": _json_bytes(record),
        "README.md": _readme(record),
    }
    manifest = H2ProductionAuthorizationManifest(
        authorization_id=record.authorization_id,
        authorization_config_sha256=canonical_config_sha256(config),
        gate_config_sha256=record.gate_config_sha256,
        acceptance_decision_id=record.acceptance_decision_id,
        candidate_id=record.candidate_id,
        candidate_fingerprint_sha256=record.candidate_fingerprint_sha256,
        canonical_path=record.canonical_path,
        canonical_sha256=record.canonical_sha256,
        canonical_document_count=record.canonical_document_count,
        gate_validation_total_checks=parent["gate_validation_total_checks"],
        files={name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()},
        next_slice="validate_immutable_h2_production_authorization_record",
    )
    payloads["manifest.json"] = _json_bytes(manifest)
    payloads["checksums.txt"] = _checksums(payloads)
    return payloads


def _write_immutable(output_dir: Path, payloads: dict[str, bytes]) -> None:
    if output_dir.exists():
        raise FileExistsError(f"Immutable authorization package already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in payloads.items():
            (output_dir / name).write_bytes(data)
    except Exception:
        for child in output_dir.iterdir():
            child.unlink()
        output_dir.rmdir()
        raise


def plan_or_execute_h2_production_authorization(
    *,
    project_root: Path,
    config_path: Path,
    decision_dir: Path,
    evaluation_dir: Path,
    inference_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path = DEFAULT_CANONICAL,
    execute: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    parent = _validate_upstream(
        project_root=project_root,
        config_path=config_path,
        decision_dir=decision_dir,
        evaluation_dir=evaluation_dir,
        inference_dir=inference_dir,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir,
        canonical_path=canonical_path,
    )
    config: H2ProductionAuthorizationConfig = parent["config"]
    output_root = _resolve(project_root, config.execution.output_root)
    output_dir = output_root / parent["authorization_id"]
    existed = output_dir.exists()
    if execute and existed:
        raise FileExistsError(f"One-shot H2 production authorization already exists: {output_dir}")

    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": config.lineage.candidate_id,
        "candidate_fingerprint_sha256": config.lineage.candidate_fingerprint_sha256,
        "acceptance_decision_id": config.lineage.acceptance_decision_id,
        "production_authorization_gate_config_sha256": parent["gate_sha"],
        "production_authorization_gate_required_failed_count": 0,
        "production_authorization_gate_total_checks": parent["gate_validation_total_checks"],
        "canonical_path": parent["snapshot"]["path"],
        "canonical_sha256": parent["snapshot"]["sha256"],
        "canonical_document_count": parent["snapshot"]["document_count"],
        "authorization_id": parent["authorization_id"],
        "one_shot_already_executed": existed,
        "plan_writes_output": False,
        "plan_authorizes_candidate_build": False,
        "plan_exposes_quality_metrics": False,
        "authorization_made": False,
        "model_inference_executed_in_this_slice": False,
        "full_corpus_extraction_executed_in_this_slice": False,
        "human_reference_mentions_read_in_this_slice": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "full_corpus_candidate_build_authorized": False,
        "production_latest_promotion_authorized": False,
        "canonical_truth_mutated": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": config.next_steps.after_plan,
    }
    if not execute:
        return report

    payloads = _expected_payloads(parent)
    _write_immutable(output_dir, payloads)
    record = H2ProductionAuthorizationRecord.model_validate(json.loads(payloads["authorization.json"]))
    report.update({
        "phase_complete": True,
        "one_shot_already_executed": True,
        "authorization_made": True,
        "authorization_scope": record.authorization_scope,
        "authorized_candidate_build_count": record.authorized_candidate_build_count,
        "full_corpus_candidate_build_authorized": record.full_corpus_candidate_build_authorized,
        "production_latest_promotion_authorized": record.production_latest_promotion_authorized,
        "canonical_truth_mutated": record.canonical_truth_mutated,
        "next_slice": config.next_steps.after_execute,
    })
    return report


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        if name in result:
            raise ValueError(f"Duplicate checksum filename: {name}")
        result[name] = digest
    return result


def validate_h2_production_authorization(
    *,
    project_root: Path,
    config_path: Path,
    authorization_dir: Path,
    decision_dir: Path,
    evaluation_dir: Path,
    inference_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path = DEFAULT_CANONICAL,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    project_root = project_root.resolve()
    authorization_dir = authorization_dir.resolve()
    add("authorization_directory_exists", authorization_dir.is_dir(), authorization_dir)
    if not authorization_dir.is_dir():
        summary = {"report": REPORT_NAME, "total_checks": len(checks), "required_failed_count": 1, "next_slice": None}
        return checks, summary

    names = sorted(p.name for p in authorization_dir.iterdir() if p.is_file())
    add("exact_file_layout", names == sorted(REQUIRED_FILES), names)
    for name in names:
        try:
            data = (authorization_dir / name).read_bytes()
            data.decode("utf-8")
            add(f"utf8_lf:{name}", b"\r\n" not in data and b"\r" not in data, name)
        except Exception as exc:
            add(f"utf8_lf:{name}", False, exc)

    checksums: dict[str, str] = {}
    try:
        checksums = _parse_checksums(authorization_dir / "checksums.txt")
        add("checksum_set_exact", set(checksums) == set(CHECKSUM_FILES), sorted(checksums))
        for name in CHECKSUM_FILES:
            actual = _sha256_file(authorization_dir / name)
            add(f"checksum:{name}", checksums.get(name) == actual, actual)
    except Exception as exc:
        add("checksums_parse", False, exc)

    record: H2ProductionAuthorizationRecord | None = None
    manifest: H2ProductionAuthorizationManifest | None = None
    try:
        record = H2ProductionAuthorizationRecord.model_validate(_read_json(authorization_dir / "authorization.json"))
        add("authorization_schema_valid", True)
    except Exception as exc:
        add("authorization_schema_valid", False, exc)
    try:
        manifest = H2ProductionAuthorizationManifest.model_validate(_read_json(authorization_dir / "manifest.json"))
        add("manifest_schema_valid", True)
    except Exception as exc:
        add("manifest_schema_valid", False, exc)

    parent: dict[str, Any] | None = None
    try:
        parent = _validate_upstream(
            project_root=project_root,
            config_path=config_path,
            decision_dir=decision_dir,
            evaluation_dir=evaluation_dir,
            inference_dir=inference_dir,
            sample_dir=sample_dir,
            reference_dir=reference_dir,
            development_package_dir=development_package_dir,
            previous_heldout_sample_dir=previous_heldout_sample_dir,
            frozen_candidate_dir=frozen_candidate_dir,
            canonical_path=canonical_path,
        )
        add("upstream_production_authorization_gate_passes", True)
    except Exception as exc:
        add("upstream_production_authorization_gate_passes", False, exc)

    if parent is not None and record is not None and manifest is not None:
        expected = _expected_payloads(parent)
        for name in REQUIRED_FILES:
            add(
                f"independently_recomputed:{name}",
                (authorization_dir / name).read_bytes() == expected[name],
                name,
            )
        add("authorization_id_matches_directory", authorization_dir.name == record.authorization_id, record.authorization_id)
        add("authorization_id_matches_bound_snapshot", record.authorization_id == parent["authorization_id"], parent["authorization_id"])
        add("manifest_matches_authorization_id", manifest.authorization_id == record.authorization_id)
        add("authorization_config_sha_matches", manifest.authorization_config_sha256 == canonical_config_sha256(parent["config"]))
        add("gate_config_sha_matches", record.gate_config_sha256 == parent["gate_sha"] == manifest.gate_config_sha256)
        add("candidate_identity_matches", record.candidate_id == parent["config"].lineage.candidate_id and record.candidate_fingerprint_sha256 == parent["config"].lineage.candidate_fingerprint_sha256)
        snapshot = parent["snapshot"]
        add("canonical_path_matches", record.canonical_path == snapshot["path"] == manifest.canonical_path)
        add("canonical_sha_matches", record.canonical_sha256 == snapshot["sha256"] == manifest.canonical_sha256)
        add("canonical_document_count_matches", record.canonical_document_count == snapshot["document_count"] == manifest.canonical_document_count)
        add("authorization_is_candidate_build_only", record.full_corpus_candidate_build_authorized and not record.production_latest_promotion_authorized and not record.latest_overwrite_allowed)
        add("authorization_preserves_canonical_truth", not record.canonical_truth_mutated)
        add("authorization_requires_validation_and_separate_promotion", record.candidate_validation_required_before_promotion and record.separate_promotion_decision_required)
        add("authorization_forbids_heldout_feedback", not record.reference_labels_allowed_in_build and not record.heldout_feedback_into_policy_allowed)

    failed = sum(not ok for _, ok, _ in checks)
    summary = {
        "report": REPORT_NAME,
        "authorization_id": record.authorization_id if record is not None else None,
        "candidate_id": record.candidate_id if record is not None else None,
        "candidate_fingerprint_sha256": record.candidate_fingerprint_sha256 if record is not None else None,
        "canonical_sha256": record.canonical_sha256 if record is not None else None,
        "canonical_document_count": record.canonical_document_count if record is not None else None,
        "authorization_made": record is not None,
        "full_corpus_candidate_build_authorized": bool(record and record.full_corpus_candidate_build_authorized),
        "production_latest_promotion_authorized": bool(record and record.production_latest_promotion_authorized),
        "canonical_truth_mutated": bool(record and record.canonical_truth_mutated),
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": parent["config"].next_steps.after_validation if failed == 0 and parent is not None else None,
    }
    return checks, summary
