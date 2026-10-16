from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_closure import (
    CANDIDATE_BUILD_ID,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    CANONICAL_SHA256,
    CLOSURE_ID,
    DECISION_ID,
    MATERIALIZATION_FINGERPRINT,
    PROMOTION_ID,
    H2ProductionClosureConfig,
    H2ProductionClosureError,
    H2ProductionClosureManifest,
    H2ProductionClosureRecord,
    canonical_config_sha256,
    load_h2_production_closure_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_promotion_decision import (
    H2ProductionPromotionDecisionManifest,
    H2ProductionPromotionDecisionRecord,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_latest_promotion import (
    H2ProductionLatestPostValidation,
    H2ProductionLatestPromotionManifest,
    H2ProductionLatestPromotionRecord,
    PreviousLatestState,
    ScientificEntityProductionLatestPointer,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_closure_v0.3.yaml"
REPORT_NAME = "scientific_entity_semantic_typer_h2_production_closure_v03"
OUTPUT_FILES = ("README.md", "checksums.txt", "closure.json", "manifest.json")
CHECKSUM_FILES = ("README.md", "closure.json", "manifest.json")
DECISION_FILES = ("README.md", "checksums.txt", "decision.json", "manifest.json")
PROMOTION_FILES = (
    "README.md", "checksums.txt", "installed_latest.json", "manifest.json",
    "post_validation.json", "previous_latest_state.json", "promotion.json",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def _json_bytes(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        if name in result:
            raise H2ProductionClosureError(f"Duplicate checksum entry: {name}")
        result[name] = digest
    return result


def _lf_ok(path: Path) -> bool:
    return b"\r" not in path.read_bytes()


def _require_exact_files(directory: Path, expected: Sequence[str], label: str) -> None:
    if not directory.is_dir():
        raise H2ProductionClosureError(f"{label} directory does not exist: {directory}")
    actual = sorted(path.name for path in directory.iterdir() if path.is_file())
    if actual != sorted(expected):
        raise H2ProductionClosureError(f"{label} exact file layout drifted: {actual}")


def _resolve(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def _validate_decision(config: H2ProductionClosureConfig, decision_dir: Path) -> tuple[H2ProductionPromotionDecisionRecord, H2ProductionPromotionDecisionManifest]:
    _require_exact_files(decision_dir, DECISION_FILES, "Promotion decision")
    checksums = _parse_checksums(decision_dir / "checksums.txt")
    if set(checksums) != {"README.md", "decision.json", "manifest.json"}:
        raise H2ProductionClosureError("Promotion decision checksum set drifted")
    for name, digest in checksums.items():
        if _sha256_file(decision_dir / name) != digest:
            raise H2ProductionClosureError(f"Promotion decision checksum mismatch: {name}")
    if _sha256_file(decision_dir / "decision.json") != config.lineage.decision_sha256:
        raise H2ProductionClosureError("Promotion decision record SHA drifted")
    if _sha256_file(decision_dir / "manifest.json") != config.lineage.decision_manifest_sha256:
        raise H2ProductionClosureError("Promotion decision manifest SHA drifted")
    if _sha256_file(decision_dir / "checksums.txt") != config.lineage.decision_checksums_sha256:
        raise H2ProductionClosureError("Promotion decision checksum-ledger SHA drifted")
    decision = H2ProductionPromotionDecisionRecord.model_validate(json.loads((decision_dir / "decision.json").read_text(encoding="utf-8")))
    manifest = H2ProductionPromotionDecisionManifest.model_validate(json.loads((decision_dir / "manifest.json").read_text(encoding="utf-8")))
    if decision.decision_id != DECISION_ID or manifest.decision_id != DECISION_ID:
        raise H2ProductionClosureError("Promotion decision identity mismatch")
    if not decision.promotion_decision_made or not decision.production_latest_promotion_authorized:
        raise H2ProductionClosureError("Promotion decision is not authorization-clean")
    if decision.authorized_promotion_count != 1:
        raise H2ProductionClosureError("Promotion decision must authorize exactly one promotion")
    if decision.promotion_executed or decision.latest_overwritten:
        raise H2ProductionClosureError("Promotion decision artifact itself must have no promotion side effects")
    if manifest.parent_lineage_verified is not True or manifest.production_latest_promotion_authorized is not True:
        raise H2ProductionClosureError("Promotion decision manifest lineage is not verified")
    return decision, manifest


def _validate_promotion(config: H2ProductionClosureConfig, promotion_dir: Path) -> tuple[
    H2ProductionLatestPromotionRecord, H2ProductionLatestPromotionManifest,
    H2ProductionLatestPostValidation, PreviousLatestState, ScientificEntityProductionLatestPointer,
]:
    _require_exact_files(promotion_dir, PROMOTION_FILES, "Production latest promotion")
    checksums = _parse_checksums(promotion_dir / "checksums.txt")
    expected = set(PROMOTION_FILES) - {"checksums.txt"}
    if set(checksums) != expected:
        raise H2ProductionClosureError("Production promotion checksum set drifted")
    for name, digest in checksums.items():
        if _sha256_file(promotion_dir / name) != digest:
            raise H2ProductionClosureError(f"Production promotion checksum mismatch: {name}")
    exact = {
        "promotion.json": config.lineage.promotion_record_sha256,
        "manifest.json": config.lineage.promotion_manifest_sha256,
        "post_validation.json": config.lineage.promotion_post_validation_sha256,
    }
    for name, expected_sha in exact.items():
        if _sha256_file(promotion_dir / name) != expected_sha:
            raise H2ProductionClosureError(f"Production promotion {name} SHA drifted")
    if _sha256_file(promotion_dir / "checksums.txt") != config.lineage.promotion_checksums_sha256:
        raise H2ProductionClosureError("Production promotion checksum-ledger SHA drifted")
    record = H2ProductionLatestPromotionRecord.model_validate(json.loads((promotion_dir / "promotion.json").read_text(encoding="utf-8")))
    manifest = H2ProductionLatestPromotionManifest.model_validate(json.loads((promotion_dir / "manifest.json").read_text(encoding="utf-8")))
    post = H2ProductionLatestPostValidation.model_validate(json.loads((promotion_dir / "post_validation.json").read_text(encoding="utf-8")))
    previous = PreviousLatestState.model_validate(json.loads((promotion_dir / "previous_latest_state.json").read_text(encoding="utf-8")))
    installed = ScientificEntityProductionLatestPointer.model_validate(json.loads((promotion_dir / "installed_latest.json").read_text(encoding="utf-8")))
    if record.promotion_id != PROMOTION_ID or manifest.promotion_id != PROMOTION_ID or post.promotion_id != PROMOTION_ID:
        raise H2ProductionClosureError("Promotion identity mismatch")
    if not (record.promotion_executed and record.trusted_latest_pointer_updated and record.post_promotion_validation_passed and record.rollback_path_ready):
        raise H2ProductionClosureError("Promotion record is not closure-ready")
    if not (manifest.promotion_executed and manifest.trusted_latest_pointer_updated and manifest.post_promotion_validation_passed and manifest.rollback_path_ready):
        raise H2ProductionClosureError("Promotion manifest is not closure-ready")
    if not post.post_promotion_validation_passed:
        raise H2ProductionClosureError("Post-promotion validation did not pass")
    if record.candidate_mutated or record.canonical_truth_mutated or manifest.candidate_mutated or manifest.canonical_truth_mutated:
        raise H2ProductionClosureError("Parent promotion reports forbidden mutation")
    return record, manifest, post, previous, installed


def _validate_trusted_latest(
    *, project_root: Path, config: H2ProductionClosureConfig, trusted_latest_path: Path,
    installed: ScientificEntityProductionLatestPointer,
) -> tuple[str, int]:
    if not trusted_latest_path.is_file():
        raise H2ProductionClosureError(f"Trusted latest pointer does not exist: {trusted_latest_path}")
    raw = trusted_latest_path.read_bytes()
    if _sha256_bytes(raw) != config.lineage.trusted_latest_pointer_sha256:
        raise H2ProductionClosureError("Trusted latest pointer SHA drifted")
    if raw != _json_bytes(installed):
        raise H2ProductionClosureError("Trusted latest pointer differs from installed promotion pointer")
    pointer = ScientificEntityProductionLatestPointer.model_validate(json.loads(raw.decode("utf-8")))
    if pointer.state != "trusted_latest" or pointer.promotion_id != PROMOTION_ID or pointer.decision_id != DECISION_ID:
        raise H2ProductionClosureError("Trusted latest pointer lineage mismatch")
    if pointer.candidate_build_id != CANDIDATE_BUILD_ID or pointer.candidate_id != CANDIDATE_ID:
        raise H2ProductionClosureError("Trusted latest candidate identity mismatch")
    if pointer.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT or pointer.materialization_fingerprint_sha256 != MATERIALIZATION_FINGERPRINT:
        raise H2ProductionClosureError("Trusted latest candidate fingerprint mismatch")
    if pointer.candidate_final_mentions_sha256 != config.lineage.candidate_final_mentions_sha256:
        raise H2ProductionClosureError("Trusted latest authorized target SHA mismatch")
    if pointer.final_mention_count != 846264 or pointer.h2_override_count != 33469:
        raise H2ProductionClosureError("Trusted latest production counts mismatch")
    if pointer.canonical_sha256 != CANONICAL_SHA256 or pointer.canonical_document_count != 61075:
        raise H2ProductionClosureError("Trusted latest canonical lineage mismatch")
    target = _resolve(project_root, pointer.artifact_path)
    if not target.is_file():
        raise H2ProductionClosureError(f"Trusted target artifact missing: {target}")
    actual_sha = _sha256_file(target)
    if actual_sha != config.lineage.candidate_final_mentions_sha256:
        raise H2ProductionClosureError("Trusted target SHA-256 drifted")
    actual_lines = _line_count(target)
    if actual_lines != config.lineage.final_mention_count:
        raise H2ProductionClosureError(f"Trusted target line count drifted: {actual_lines}")
    return actual_sha, actual_lines


def _build_files(config: H2ProductionClosureConfig, trusted_sha: str, trusted_lines: int) -> dict[str, bytes]:
    closure = H2ProductionClosureRecord(
        closure_id=CLOSURE_ID,
        lifecycle_status="closed_as_trusted_production_baseline",
        decision_id=DECISION_ID,
        promotion_id=PROMOTION_ID,
        candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        candidate_final_mentions_sha256=trusted_sha,
        final_mention_count=trusted_lines,
        h2_override_count=config.lineage.h2_override_count,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        promotion_decision_validated=True,
        promotion_executed=True,
        promotion_validated=True,
        production_latest_active=True,
        trusted_target_revalidated_at_closure=True,
        rollback_path_ready=True,
        trusted_production_baseline_established=True,
        h2_v03_lifecycle_closed=True,
        future_h2_v03_tuning_allowed=False,
        historical_production_audit_reference_reuse_for_tuning_allowed=False,
        future_quality_work_requires_new_version=True,
        future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample=True,
        full_ner_coverage_audit_started=False,
        trusted_latest_mutated_in_this_slice=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        publication_authorized=False,
        next_slice="plan_prediction_blind_full_ner_coverage_audit",
    )
    readme = (
        "# H2 v0.3 Production Closure\n\n"
        f"Closure ID: `{CLOSURE_ID}`\n\n"
        f"Trusted candidate build: `{CANDIDATE_BUILD_ID}`\n\n"
        f"Trusted final_mentions SHA-256: `{trusted_sha}`\n\n"
        f"Trusted mention count: `{trusted_lines}`; H2 overrides: `{config.lineage.h2_override_count}`.\n\n"
        "H2 v0.3 is closed as the trusted Scientific Entity production baseline. No model inference, tuning, policy revision, candidate mutation, canonical mutation, or trusted-latest mutation occurred in this closure slice. Historical production-audit labels remain evidence only and are not tuning data. The next quality stage requires a fresh prediction-blind full-NER coverage sample.\n"
    ).encode("utf-8")
    closure_b = _json_bytes(closure)
    files = {"README.md": _sha256_bytes(readme), "closure.json": _sha256_bytes(closure_b)}
    manifest = H2ProductionClosureManifest(
        closure_id=CLOSURE_ID,
        closure_config_sha256=canonical_config_sha256(config),
        decision_id=DECISION_ID,
        decision_sha256=config.lineage.decision_sha256,
        decision_manifest_sha256=config.lineage.decision_manifest_sha256,
        decision_checksums_sha256=config.lineage.decision_checksums_sha256,
        promotion_id=PROMOTION_ID,
        promotion_record_sha256=config.lineage.promotion_record_sha256,
        promotion_manifest_sha256=config.lineage.promotion_manifest_sha256,
        promotion_post_validation_sha256=config.lineage.promotion_post_validation_sha256,
        promotion_checksums_sha256=config.lineage.promotion_checksums_sha256,
        trusted_latest_pointer_sha256=config.lineage.trusted_latest_pointer_sha256,
        trusted_target_sha256=trusted_sha,
        trusted_target_line_count=trusted_lines,
        parent_lineage_verified=True,
        trusted_target_revalidated_at_closure=True,
        production_latest_active=True,
        rollback_path_ready=True,
        h2_v03_lifecycle_closed=True,
        trusted_latest_mutated_in_this_slice=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        publication_authorized=False,
        files=files,
        next_slice="validate_immutable_h2_v03_production_closure",
    )
    manifest_b = _json_bytes(manifest)
    checks = {**files, "manifest.json": _sha256_bytes(manifest_b)}
    checksums_b = "".join(f"{digest}  {name}\n" for name, digest in sorted(checks.items())).encode("utf-8")
    return {"README.md": readme, "closure.json": closure_b, "manifest.json": manifest_b, "checksums.txt": checksums_b}


def _atomic_write_files(output_dir: Path, payloads: dict[str, bytes]) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise H2ProductionClosureError(f"Closure record already exists: {output_dir}")
    with tempfile.TemporaryDirectory(dir=output_dir.parent, prefix=f".{output_dir.name}.") as temp_name:
        temp_dir = Path(temp_name)
        for name, payload in payloads.items():
            (temp_dir / name).write_bytes(payload)
        temp_dir.replace(output_dir)


def plan_or_execute_h2_production_closure(
    *, project_root: Path = PROJECT_ROOT, config_path: Path = DEFAULT_CONFIG,
    decision_dir: Path | None = None, promotion_dir: Path | None = None,
    trusted_latest_path: Path | None = None, output_root: Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    config = load_h2_production_closure_config(config_path)
    decision_root = decision_dir or _resolve(project_root, config.inputs.decision_root) / DECISION_ID
    promotion_root = promotion_dir or _resolve(project_root, config.inputs.promotion_root) / PROMOTION_ID
    latest_path = trusted_latest_path or _resolve(project_root, config.inputs.trusted_latest_path)
    closure_root = output_root or _resolve(project_root, config.execution.output_root)
    closure_dir = closure_root / CLOSURE_ID

    _validate_decision(config, decision_root)
    _, _, _, _, installed = _validate_promotion(config, promotion_root)
    trusted_sha, trusted_lines = _validate_trusted_latest(
        project_root=project_root, config=config, trusted_latest_path=latest_path, installed=installed,
    )
    exists = closure_dir.exists()
    if execute:
        if exists:
            raise H2ProductionClosureError(f"Closure record already exists: {closure_dir}")
        _atomic_write_files(closure_dir, _build_files(config, trusted_sha, trusted_lines))
        exists = True

    return {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": bool(execute),
        "closure_id": CLOSURE_ID,
        "decision_id": DECISION_ID,
        "promotion_id": PROMOTION_ID,
        "candidate_build_id": CANDIDATE_BUILD_ID,
        "candidate_final_mentions_sha256": trusted_sha,
        "candidate_final_mention_count": trusted_lines,
        "h2_override_count": config.lineage.h2_override_count,
        "parent_lineage_verified": True,
        "trusted_target_revalidated_at_closure": True,
        "production_latest_active": True,
        "rollback_path_ready": True,
        "h2_v03_lifecycle_closed": bool(execute),
        "future_h2_v03_tuning_allowed": False,
        "historical_production_audit_reference_reuse_for_tuning_allowed": False,
        "future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample": True,
        "full_ner_coverage_audit_started": False,
        "trusted_latest_mutated_in_this_slice": False,
        "candidate_mutated": False,
        "canonical_truth_mutated": False,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "publication_authorized": False,
        "closure_record_already_exists": exists,
        "plan_writes_output": False,
        "output_dir": str(closure_dir),
        "next_slice": config.next_steps.after_execute if execute else config.next_steps.after_plan,
    }


def validate_h2_production_closure(
    *, project_root: Path = PROJECT_ROOT, config_path: Path = DEFAULT_CONFIG,
    decision_dir: Path | None = None, promotion_dir: Path | None = None,
    trusted_latest_path: Path | None = None, closure_dir: Path | None = None,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    config = load_h2_production_closure_config(config_path)
    decision_root = decision_dir or _resolve(project_root, config.inputs.decision_root) / DECISION_ID
    promotion_root = promotion_dir or _resolve(project_root, config.inputs.promotion_root) / PROMOTION_ID
    latest_path = trusted_latest_path or _resolve(project_root, config.inputs.trusted_latest_path)
    target_closure = closure_dir or _resolve(project_root, config.execution.output_root) / CLOSURE_ID
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    try:
        _validate_decision(config, decision_root)
        add("promotion_decision_still_valid", True)
    except Exception as exc:
        add("promotion_decision_still_valid", False, str(exc))
    try:
        _, _, _, _, installed = _validate_promotion(config, promotion_root)
        trusted_sha, trusted_lines = _validate_trusted_latest(
            project_root=project_root, config=config, trusted_latest_path=latest_path, installed=installed,
        )
        add("production_promotion_and_latest_still_valid", True)
    except Exception as exc:
        trusted_sha, trusted_lines = "", -1
        add("production_promotion_and_latest_still_valid", False, str(exc))

    add("closure_directory_exists", target_closure.is_dir(), str(target_closure))
    if target_closure.is_dir():
        actual = sorted(p.name for p in target_closure.iterdir() if p.is_file())
        add("exact_file_layout", actual == sorted(OUTPUT_FILES), str(actual))
        checksums_path = target_closure / "checksums.txt"
        try:
            ledger = _parse_checksums(checksums_path)
            add("checksum_set_exact", set(ledger) == set(CHECKSUM_FILES), str(sorted(ledger)))
            for name in CHECKSUM_FILES:
                add(f"checksum:{name}", ledger.get(name) == _sha256_file(target_closure / name), name)
        except Exception as exc:
            add("checksum_set_exact", False, str(exc))
        for name in OUTPUT_FILES:
            if (target_closure / name).is_file():
                add(f"lf:{name}", _lf_ok(target_closure / name), name)
        try:
            closure = H2ProductionClosureRecord.model_validate(json.loads((target_closure / "closure.json").read_text(encoding="utf-8")))
            manifest = H2ProductionClosureManifest.model_validate(json.loads((target_closure / "manifest.json").read_text(encoding="utf-8")))
            add("closure_schema_and_identity", closure.closure_id == CLOSURE_ID and manifest.closure_id == CLOSURE_ID)
            add("closure_marks_trusted_baseline_closed", closure.h2_v03_lifecycle_closed and closure.production_latest_active and not closure.future_h2_v03_tuning_allowed)
            add("closure_requires_fresh_future_audit", closure.future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample and not closure.historical_production_audit_reference_reuse_for_tuning_allowed)
            add("closure_has_no_side_effects", not any((closure.trusted_latest_mutated_in_this_slice, closure.candidate_mutated, closure.canonical_truth_mutated, closure.model_inference_executed, closure.threshold_tuning_executed, closure.policy_revision_executed)))
            add("manifest_parent_lineage_verified", manifest.parent_lineage_verified and manifest.production_latest_active and manifest.rollback_path_ready)
            add("manifest_trusted_target_exact", manifest.trusted_target_sha256 == trusted_sha and manifest.trusted_target_line_count == trusted_lines)
            expected = _build_files(config, trusted_sha, trusted_lines)
            for name in OUTPUT_FILES:
                add(f"recompute_exact:{name}", (target_closure / name).read_bytes() == expected[name], name)
        except Exception as exc:
            add("closure_schema_and_identity", False, str(exc))

    failed = sum(1 for _, ok, _ in checks if not ok)
    summary = {
        "report": REPORT_NAME,
        "closure_id": CLOSURE_ID,
        "closure_validated": failed == 0,
        "production_latest_active": failed == 0,
        "h2_v03_lifecycle_closed": failed == 0,
        "rollback_path_ready": failed == 0,
        "future_h2_v03_tuning_allowed": False,
        "historical_production_audit_reference_reuse_for_tuning_allowed": False,
        "future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample": True,
        "trusted_latest_mutated_in_this_slice": False,
        "candidate_mutated": False,
        "canonical_truth_mutated": False,
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": "plan_prediction_blind_full_ner_coverage_audit" if failed == 0 else "repair_h2_v03_production_closure",
    }
    return checks, summary
