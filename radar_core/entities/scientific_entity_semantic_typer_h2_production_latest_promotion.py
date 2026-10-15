from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_promotion_decision import (
    H2ProductionPromotionDecisionManifest,
    H2ProductionPromotionDecisionRecord,
    canonical_config_sha256 as decision_config_sha256,
    load_h2_production_promotion_decision_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_latest_promotion import (
    CANDIDATE_BUILD_ID,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    CANONICAL_SHA256,
    DECISION_ID,
    MATERIALIZATION_FINGERPRINT,
    PROMOTION_ID,
    ROLLBACK_ID,
    H2ProductionLatestPostValidation,
    H2ProductionLatestPromotionConfig,
    H2ProductionLatestPromotionError,
    H2ProductionLatestPromotionManifest,
    H2ProductionLatestPromotionRecord,
    H2ProductionLatestRollbackRecord,
    PreviousLatestState,
    ScientificEntityProductionLatestPointer,
    canonical_config_sha256,
    load_h2_production_latest_promotion_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_latest_promotion_v0.3.yaml"
REPORT_NAME = "scientific_entity_semantic_typer_h2_production_latest_promotion_v03"
ROLLBACK_REPORT_NAME = "scientific_entity_semantic_typer_h2_production_latest_rollback_v03"
OUTPUT_FILES = (
    "README.md",
    "installed_latest.json",
    "post_validation.json",
    "previous_latest_state.json",
    "promotion.json",
    "manifest.json",
    "checksums.txt",
)
CHECKSUM_FILES = tuple(name for name in OUTPUT_FILES if name != "checksums.txt")
DECISION_FILES = ("README.md", "checksums.txt", "decision.json", "manifest.json")
CANDIDATE_METADATA_FILES = ("README.md", "checksums.txt", "manifest.json", "summary.json", "final_mentions.jsonl")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
            raise H2ProductionLatestPromotionError(f"Duplicate checksum entry: {name}")
        result[name] = digest
    return result


def _lf_ok(path: Path) -> bool:
    return b"\r" not in path.read_bytes()


def _line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def _resolve(root: Path, value: str | Path) -> Path:
    p = Path(value)
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def _relative_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _require_exact_files(directory: Path, expected: Sequence[str], label: str) -> None:
    if not directory.is_dir():
        raise H2ProductionLatestPromotionError(f"{label} directory does not exist: {directory}")
    actual = sorted(path.name for path in directory.iterdir() if path.is_file())
    if actual != sorted(expected):
        raise H2ProductionLatestPromotionError(f"{label} exact file layout drifted: {actual}")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _validate_decision_static(
    *, config: H2ProductionLatestPromotionConfig, decision_config_path: Path, decision_dir: Path
) -> tuple[H2ProductionPromotionDecisionRecord, H2ProductionPromotionDecisionManifest]:
    _require_exact_files(decision_dir, DECISION_FILES, "Promotion decision")
    checksums = _parse_checksums(decision_dir / "checksums.txt")
    if set(checksums) != {"README.md", "decision.json", "manifest.json"}:
        raise H2ProductionLatestPromotionError("Promotion-decision checksum set drifted")
    for name, digest in checksums.items():
        if _sha256_file(decision_dir / name) != digest:
            raise H2ProductionLatestPromotionError(f"Promotion-decision checksum mismatch: {name}")
    decision_cfg = load_h2_production_promotion_decision_config(decision_config_path)
    if decision_config_sha256(decision_cfg) != config.lineage.decision_config_canonical_sha256:
        raise H2ProductionLatestPromotionError("Promotion-decision config canonical SHA-256 drifted")
    decision = H2ProductionPromotionDecisionRecord.model_validate(
        json.loads((decision_dir / "decision.json").read_text(encoding="utf-8"))
    )
    manifest = H2ProductionPromotionDecisionManifest.model_validate(
        json.loads((decision_dir / "manifest.json").read_text(encoding="utf-8"))
    )
    if decision.decision_id != DECISION_ID or manifest.decision_id != DECISION_ID:
        raise H2ProductionLatestPromotionError("Promotion-decision identity mismatch")
    if not decision.promotion_decision_made or not decision.production_latest_promotion_authorized:
        raise H2ProductionLatestPromotionError("Production latest promotion is not authorized")
    if decision.authorized_promotion_count != 1:
        raise H2ProductionLatestPromotionError("Promotion decision must authorize exactly one promotion")
    if not (decision.backup_previous_trusted_latest_required and decision.rollback_path_required and decision.post_promotion_validation_required):
        raise H2ProductionLatestPromotionError("Promotion decision does not require backup/rollback/postvalidation")
    if decision.candidate_build_id != CANDIDATE_BUILD_ID or manifest.candidate_build_id != CANDIDATE_BUILD_ID:
        raise H2ProductionLatestPromotionError("Promotion decision candidate build mismatch")
    if decision.candidate_final_mentions_sha256 != config.lineage.candidate_final_mentions_sha256:
        raise H2ProductionLatestPromotionError("Promotion decision final_mentions SHA mismatch")
    if manifest.candidate_final_mentions_sha256 != config.lineage.candidate_final_mentions_sha256:
        raise H2ProductionLatestPromotionError("Promotion-decision manifest final_mentions SHA mismatch")
    if decision.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT or manifest.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT:
        raise H2ProductionLatestPromotionError("Promotion-decision candidate fingerprint mismatch")
    if decision.materialization_fingerprint_sha256 != MATERIALIZATION_FINGERPRINT or manifest.materialization_fingerprint_sha256 != MATERIALIZATION_FINGERPRINT:
        raise H2ProductionLatestPromotionError("Promotion-decision materialization fingerprint mismatch")
    if decision.canonical_sha256 != CANONICAL_SHA256 or manifest.canonical_sha256 != CANONICAL_SHA256:
        raise H2ProductionLatestPromotionError("Promotion-decision canonical snapshot mismatch")
    if decision.promotion_executed or decision.latest_overwritten or decision.canonical_truth_mutated or decision.candidate_mutated:
        raise H2ProductionLatestPromotionError("Promotion-decision artifact contains forbidden side effects")
    return decision, manifest


def _validate_candidate_static(
    *, config: H2ProductionLatestPromotionConfig, candidate_dir: Path, rehash_final_mentions: bool
) -> tuple[dict[str, Any], dict[str, Any], str, int]:
    missing = [name for name in CANDIDATE_METADATA_FILES if not (candidate_dir / name).is_file()]
    if missing:
        raise H2ProductionLatestPromotionError(f"Candidate missing files: {missing}")
    checksums = _parse_checksums(candidate_dir / "checksums.txt")
    for name in ("README.md", "manifest.json", "summary.json"):
        if checksums.get(name) != _sha256_file(candidate_dir / name):
            raise H2ProductionLatestPromotionError(f"Candidate metadata checksum mismatch: {name}")
    ledger_sha = checksums.get("final_mentions.jsonl")
    if ledger_sha != config.lineage.candidate_final_mentions_sha256:
        raise H2ProductionLatestPromotionError("Candidate checksum ledger does not bind authorized final_mentions SHA")
    manifest = json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((candidate_dir / "summary.json").read_text(encoding="utf-8"))
    expected_pairs = {
        "build_id": CANDIDATE_BUILD_ID,
        "candidate_id": CANDIDATE_ID,
        "candidate_fingerprint_sha256": CANDIDATE_FINGERPRINT,
        "materialization_fingerprint_sha256": MATERIALIZATION_FINGERPRINT,
        "canonical_sha256": CANONICAL_SHA256,
        "canonical_document_count": 61075,
    }
    for key, expected in expected_pairs.items():
        if manifest.get(key) != expected:
            raise H2ProductionLatestPromotionError(f"Candidate manifest {key} mismatch")
    if summary.get("build_id") != CANDIDATE_BUILD_ID:
        raise H2ProductionLatestPromotionError("Candidate summary build ID mismatch")
    if summary.get("final_mention_count") != config.lineage.final_mention_count:
        raise H2ProductionLatestPromotionError("Candidate final mention count mismatch")
    if summary.get("h2_override_count") != config.lineage.h2_override_count:
        raise H2ProductionLatestPromotionError("Candidate H2 override count mismatch")
    if manifest.get("files", {}).get("final_mentions.jsonl") != ledger_sha:
        raise H2ProductionLatestPromotionError("Candidate manifest does not bind final_mentions checksum")
    forbidden_true = (
        "reference_labels_used",
        "threshold_tuning_executed",
        "policy_revision_executed",
        "span_mutated",
        "canonical_truth_mutated",
        "production_latest_promotion_authorized",
        "latest_overwrite_allowed",
        "publication_ready",
    )
    if any(bool(manifest.get(key)) for key in forbidden_true):
        raise H2ProductionLatestPromotionError("Candidate safety flags are not promotion clean")
    actual_sha = ledger_sha
    actual_lines = config.lineage.final_mention_count
    if rehash_final_mentions:
        target = candidate_dir / "final_mentions.jsonl"
        actual_sha = _sha256_file(target)
        if actual_sha != config.lineage.candidate_final_mentions_sha256:
            raise H2ProductionLatestPromotionError("Actual candidate final_mentions SHA-256 does not match authorization")
        actual_lines = _line_count(target)
        if actual_lines != config.lineage.final_mention_count:
            raise H2ProductionLatestPromotionError(
                f"Actual candidate final_mentions line count mismatch: {actual_lines} != {config.lineage.final_mention_count}"
            )
    return manifest, summary, actual_sha, actual_lines


def _read_previous_latest(pointer_path: Path) -> tuple[PreviousLatestState, ScientificEntityProductionLatestPointer | None, bytes | None]:
    if not pointer_path.exists():
        state = PreviousLatestState(previous_latest_exists=False, rollback_action="remove_latest_pointer")
        return state, None, None
    raw = pointer_path.read_bytes()
    try:
        pointer = ScientificEntityProductionLatestPointer.model_validate(json.loads(raw.decode("utf-8")))
    except Exception as exc:
        raise H2ProductionLatestPromotionError(f"Existing trusted latest pointer is invalid: {type(exc).__name__}: {exc}") from exc
    state = PreviousLatestState(
        previous_latest_exists=True,
        previous_latest_sha256=_sha256_bytes(raw),
        previous_latest_bytes_base64=base64.b64encode(raw).decode("ascii"),
        rollback_action="restore_previous_latest_pointer",
    )
    return state, pointer, raw


def _build_latest_pointer(
    *, project_root: Path, config: H2ProductionLatestPromotionConfig, candidate_dir: Path, promotion_dir: Path
) -> ScientificEntityProductionLatestPointer:
    artifact_path = _relative_posix(project_root, candidate_dir / "final_mentions.jsonl")
    promotion_record_path = _relative_posix(project_root, promotion_dir)
    return ScientificEntityProductionLatestPointer(
        promotion_id=PROMOTION_ID,
        decision_id=DECISION_ID,
        candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        candidate_final_mentions_sha256=config.lineage.candidate_final_mentions_sha256,
        final_mention_count=config.lineage.final_mention_count,
        h2_override_count=config.lineage.h2_override_count,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        artifact_path=artifact_path,
        promotion_record_path=promotion_record_path,
        artifact_is_immutable_candidate=True,
        artifact_retention_required=True,
        post_promotion_validation_required=True,
        publication_authorized=False,
    )


def _postcheck_latest(
    *, project_root: Path, pointer_path: Path, expected_pointer_bytes: bytes, config: H2ProductionLatestPromotionConfig
) -> H2ProductionLatestPostValidation:
    if not pointer_path.is_file():
        raise H2ProductionLatestPromotionError("Trusted latest pointer missing after promotion")
    actual_pointer_bytes = pointer_path.read_bytes()
    if actual_pointer_bytes != expected_pointer_bytes:
        raise H2ProductionLatestPromotionError("Installed trusted latest pointer differs from expected pointer")
    pointer = ScientificEntityProductionLatestPointer.model_validate(json.loads(actual_pointer_bytes.decode("utf-8")))
    target = _resolve(project_root, pointer.artifact_path)
    if not target.is_file():
        raise H2ProductionLatestPromotionError(f"Promoted target artifact does not exist: {target}")
    actual_sha = _sha256_file(target)
    if actual_sha != config.lineage.candidate_final_mentions_sha256:
        raise H2ProductionLatestPromotionError("Promoted target artifact SHA mismatch")
    actual_lines = _line_count(target)
    if actual_lines != config.lineage.final_mention_count:
        raise H2ProductionLatestPromotionError("Promoted target line count mismatch")
    return H2ProductionLatestPostValidation(
        promotion_id=PROMOTION_ID,
        latest_pointer_exists=True,
        latest_pointer_matches_expected=True,
        target_artifact_exists=True,
        target_sha256_matches_authorized=True,
        target_line_count_matches_expected=True,
        target_sha256=actual_sha,
        target_line_count=actual_lines,
        post_promotion_validation_passed=True,
    )


def _promotion_files(
    *, config: H2ProductionLatestPromotionConfig, pointer: ScientificEntityProductionLatestPointer,
    previous_state: PreviousLatestState, post_validation: H2ProductionLatestPostValidation,
    latest_pointer_path: Path,
) -> dict[str, bytes]:
    pointer_bytes = _json_bytes(pointer)
    previous_bytes = _json_bytes(previous_state)
    rollback_cmd = "python -m scripts.entities.rollback_scientific_entity_semantic_typer_h2_production_latest --execute"
    record = H2ProductionLatestPromotionRecord(
        promotion_id=PROMOTION_ID,
        decision_id=DECISION_ID,
        candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_final_mentions_sha256=config.lineage.candidate_final_mentions_sha256,
        final_mention_count=config.lineage.final_mention_count,
        h2_override_count=config.lineage.h2_override_count,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        promotion_decision_validated=True,
        production_latest_promotion_authorized=True,
        previous_latest_exists=previous_state.previous_latest_exists,
        previous_latest_state_snapshotted=True,
        promotion_executed=True,
        trusted_latest_pointer_updated=True,
        post_promotion_validation_passed=True,
        exact_candidate_sha_verified_immediately_before_mutation=True,
        rollback_path_ready=True,
        rollback_command=rollback_cmd,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        publication_authorized=False,
        next_slice="validate_h2_production_latest_promotion",
    )
    readme = (
        "# H2 v0.3 Controlled Production-Latest Promotion\n\n"
        f"Promotion ID: `{PROMOTION_ID}`\n\n"
        f"Trusted latest pointer: `{latest_pointer_path.as_posix()}`\n\n"
        f"Candidate build: `{CANDIDATE_BUILD_ID}`\n\n"
        f"Authorized final_mentions SHA-256: `{config.lineage.candidate_final_mentions_sha256}`\n\n"
        "The trusted state is a pointer to the immutable candidate artifact; candidate bytes and canonical truth were not mutated. "
        "The previous trusted pointer state is preserved in `previous_latest_state.json`, and rollback tooling is available before promotion.\n"
    ).encode("utf-8")
    files: dict[str, bytes] = {
        "README.md": readme,
        "installed_latest.json": pointer_bytes,
        "post_validation.json": _json_bytes(post_validation),
        "previous_latest_state.json": previous_bytes,
        "promotion.json": _json_bytes(record),
    }
    manifest = H2ProductionLatestPromotionManifest(
        promotion_id=PROMOTION_ID,
        promotion_config_sha256=canonical_config_sha256(config),
        decision_id=DECISION_ID,
        candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_final_mentions_sha256=config.lineage.candidate_final_mentions_sha256,
        final_mention_count=config.lineage.final_mention_count,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        latest_pointer_path=latest_pointer_path.as_posix(),
        latest_pointer_sha256=_sha256_bytes(pointer_bytes),
        previous_latest_exists=previous_state.previous_latest_exists,
        previous_latest_state_sha256=_sha256_bytes(previous_bytes),
        promotion_executed=True,
        trusted_latest_pointer_updated=True,
        post_promotion_validation_passed=True,
        rollback_path_ready=True,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        publication_authorized=False,
        files={name: _sha256_bytes(payload) for name, payload in sorted(files.items())},
        next_slice="validate_h2_production_latest_promotion",
    )
    files["manifest.json"] = _json_bytes(manifest)
    files["checksums.txt"] = "".join(
        f"{_sha256_bytes(files[name])}  {name}\n" for name in sorted(files)
    ).encode("utf-8")
    return files


def _preflight(
    *, project_root: Path, config_path: Path, decision_config_path: Path, decision_dir: Path, candidate_dir: Path,
    trusted_root: Path, promotion_root: Path,
) -> dict[str, Any]:
    config = load_h2_production_latest_promotion_config(config_path)
    decision, decision_manifest = _validate_decision_static(
        config=config, decision_config_path=decision_config_path, decision_dir=decision_dir
    )
    _, _, actual_sha, actual_lines = _validate_candidate_static(
        config=config, candidate_dir=candidate_dir, rehash_final_mentions=True
    )
    pointer_path = trusted_root / config.trusted_latest.pointer_name
    previous_state, previous_pointer, _ = _read_previous_latest(pointer_path)
    promotion_dir = promotion_root / config.execution.promotion_id
    return {
        "config": config,
        "decision": decision,
        "decision_manifest": decision_manifest,
        "candidate_actual_sha256": actual_sha,
        "candidate_actual_line_count": actual_lines,
        "pointer_path": pointer_path,
        "previous_state": previous_state,
        "previous_pointer": previous_pointer,
        "promotion_dir": promotion_dir,
    }


def plan_or_execute_h2_production_latest_promotion(
    *, project_root: Path, config_path: Path, decision_config_path: Path, decision_dir: Path,
    candidate_dir: Path, trusted_root: Path | None = None, promotion_root: Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    config = load_h2_production_latest_promotion_config(config_path.resolve())
    resolved_trusted_root = trusted_root.resolve() if trusted_root is not None else _resolve(project_root, config.trusted_latest.root)
    resolved_promotion_root = promotion_root.resolve() if promotion_root is not None else _resolve(project_root, config.execution.output_root)
    parent = _preflight(
        project_root=project_root.resolve(),
        config_path=config_path.resolve(),
        decision_config_path=decision_config_path.resolve(),
        decision_dir=decision_dir.resolve(),
        candidate_dir=candidate_dir.resolve(),
        trusted_root=resolved_trusted_root,
        promotion_root=resolved_promotion_root,
    )
    pointer_path: Path = parent["pointer_path"]
    promotion_dir: Path = parent["promotion_dir"]
    previous_state: PreviousLatestState = parent["previous_state"]
    if not execute:
        return {
            "report": REPORT_NAME,
            "mode": "plan",
            "phase_complete": False,
            "promotion_id": PROMOTION_ID,
            "decision_id": DECISION_ID,
            "candidate_build_id": CANDIDATE_BUILD_ID,
            "candidate_final_mentions_sha256": parent["candidate_actual_sha256"],
            "candidate_final_mention_count": parent["candidate_actual_line_count"],
            "promotion_decision_validated": True,
            "production_latest_promotion_authorized": True,
            "exact_candidate_sha_verified_in_plan": True,
            "previous_latest_exists": previous_state.previous_latest_exists,
            "first_trusted_latest_bootstrap": not previous_state.previous_latest_exists,
            "previous_latest_state_snapshot_will_be_created": True,
            "rollback_action": previous_state.rollback_action,
            "rollback_tooling_ready": True,
            "promotion_executed": False,
            "trusted_latest_pointer_updated": False,
            "canonical_truth_mutated": False,
            "candidate_mutated": False,
            "promotion_record_already_exists": promotion_dir.exists(),
            "plan_writes_output": False,
            "latest_pointer_path": str(pointer_path),
            "promotion_record_dir": str(promotion_dir),
            "next_slice": config.next_steps.after_plan,
        }
    if promotion_dir.exists():
        raise H2ProductionLatestPromotionError(f"Immutable promotion record already exists: {promotion_dir}")
    # Required second SHA/count check immediately before trusted-state mutation.
    _validate_candidate_static(config=config, candidate_dir=candidate_dir.resolve(), rehash_final_mentions=True)
    previous_state, _, previous_raw = _read_previous_latest(pointer_path)
    pointer = _build_latest_pointer(
        project_root=project_root.resolve(), config=config, candidate_dir=candidate_dir.resolve(), promotion_dir=promotion_dir
    )
    pointer_bytes = _json_bytes(pointer)
    pointer_mutated = False
    staging: Path | None = None
    try:
        _atomic_write(pointer_path, pointer_bytes)
        pointer_mutated = True
        post_validation = _postcheck_latest(
            project_root=project_root.resolve(), pointer_path=pointer_path,
            expected_pointer_bytes=pointer_bytes, config=config,
        )
        files = _promotion_files(
            config=config, pointer=pointer, previous_state=previous_state,
            post_validation=post_validation, latest_pointer_path=pointer_path,
        )
        resolved_promotion_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{PROMOTION_ID}.tmp-", dir=resolved_promotion_root))
        for name, payload in files.items():
            (staging / name).write_bytes(payload)
        staging.rename(promotion_dir)
    except BaseException:
        if pointer_mutated:
            if previous_raw is None:
                if pointer_path.exists():
                    pointer_path.unlink()
            else:
                _atomic_write(pointer_path, previous_raw)
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        raise
    return {
        "report": REPORT_NAME,
        "mode": "execute",
        "phase_complete": True,
        "promotion_id": PROMOTION_ID,
        "decision_id": DECISION_ID,
        "candidate_build_id": CANDIDATE_BUILD_ID,
        "candidate_final_mentions_sha256": config.lineage.candidate_final_mentions_sha256,
        "candidate_final_mention_count": config.lineage.final_mention_count,
        "promotion_decision_validated": True,
        "production_latest_promotion_authorized": True,
        "exact_candidate_sha_verified_immediately_before_mutation": True,
        "previous_latest_exists": previous_state.previous_latest_exists,
        "previous_latest_state_snapshotted": True,
        "rollback_action": previous_state.rollback_action,
        "rollback_tooling_ready": True,
        "promotion_executed": True,
        "trusted_latest_pointer_updated": True,
        "post_promotion_validation_passed": True,
        "canonical_truth_mutated": False,
        "candidate_mutated": False,
        "promotion_record_already_exists": True,
        "latest_pointer_path": str(pointer_path),
        "promotion_record_dir": str(promotion_dir),
        "next_slice": config.next_steps.after_execute,
    }


def validate_h2_production_latest_promotion(
    *, project_root: Path, config_path: Path, decision_config_path: Path, decision_dir: Path,
    candidate_dir: Path, trusted_root: Path, promotion_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    try:
        config = load_h2_production_latest_promotion_config(config_path.resolve())
        _validate_decision_static(config=config, decision_config_path=decision_config_path.resolve(), decision_dir=decision_dir.resolve())
        add("promotion_decision_still_valid", True)
        _, _, candidate_sha, candidate_lines = _validate_candidate_static(
            config=config, candidate_dir=candidate_dir.resolve(), rehash_final_mentions=True
        )
        add("candidate_exact_sha_still_matches", candidate_sha == config.lineage.candidate_final_mentions_sha256, candidate_sha)
        add("candidate_exact_line_count_still_matches", candidate_lines == config.lineage.final_mention_count, candidate_lines)
    except Exception as exc:
        config = None
        add("promotion_inputs_revalidate", False, f"{type(exc).__name__}: {exc}")

    promotion_dir = promotion_dir.resolve()
    add("promotion_directory_exists", promotion_dir.is_dir(), promotion_dir)
    if not promotion_dir.is_dir() or config is None:
        failed = sum(1 for _, ok, _ in checks if not ok)
        return checks, {
            "report": REPORT_NAME,
            "promotion_id": PROMOTION_ID,
            "promotion_validated": False,
            "production_latest_active": False,
            "required_failed_count": failed,
            "total_checks": len(checks),
            "next_slice": "rollback_or_fix_h2_production_latest_promotion",
        }
    actual = sorted(path.name for path in promotion_dir.iterdir() if path.is_file())
    add("exact_file_layout", actual == sorted(OUTPUT_FILES), actual)
    checksum_map = _parse_checksums(promotion_dir / "checksums.txt") if (promotion_dir / "checksums.txt").is_file() else {}
    add("checksum_set_exact", set(checksum_map) == set(CHECKSUM_FILES), sorted(checksum_map))
    for name in CHECKSUM_FILES:
        path = promotion_dir / name
        add(f"checksum:{name}", path.is_file() and checksum_map.get(name) == _sha256_file(path), name)
    for name in OUTPUT_FILES:
        path = promotion_dir / name
        add(f"lf:{name}", path.is_file() and _lf_ok(path), name)
    pointer_path = trusted_root.resolve() / config.trusted_latest.pointer_name
    try:
        pointer = ScientificEntityProductionLatestPointer.model_validate(json.loads((promotion_dir / "installed_latest.json").read_text(encoding="utf-8")))
        previous = PreviousLatestState.model_validate(json.loads((promotion_dir / "previous_latest_state.json").read_text(encoding="utf-8")))
        record = H2ProductionLatestPromotionRecord.model_validate(json.loads((promotion_dir / "promotion.json").read_text(encoding="utf-8")))
        post = H2ProductionLatestPostValidation.model_validate(json.loads((promotion_dir / "post_validation.json").read_text(encoding="utf-8")))
        manifest = H2ProductionLatestPromotionManifest.model_validate(json.loads((promotion_dir / "manifest.json").read_text(encoding="utf-8")))
        add("promotion_record_schema_and_flags", record.promotion_executed and record.post_promotion_validation_passed and record.rollback_path_ready)
        add("previous_latest_state_snapshot_valid", record.previous_latest_exists == previous.previous_latest_exists)
        installed_bytes = (promotion_dir / "installed_latest.json").read_bytes()
        add("manifest_latest_pointer_sha", manifest.latest_pointer_sha256 == _sha256_bytes(installed_bytes))
        add("manifest_previous_state_sha", manifest.previous_latest_state_sha256 == _sha256_file(promotion_dir / "previous_latest_state.json"))
        add("trusted_latest_pointer_exists", pointer_path.is_file(), pointer_path)
        add("trusted_latest_pointer_matches_installed", pointer_path.is_file() and pointer_path.read_bytes() == installed_bytes)
        target = _resolve(project_root.resolve(), pointer.artifact_path)
        add("trusted_target_exists", target.is_file(), target)
        target_sha = _sha256_file(target) if target.is_file() else ""
        add("trusted_target_sha_exact", target_sha == config.lineage.candidate_final_mentions_sha256, target_sha)
        target_lines = _line_count(target) if target.is_file() else -1
        add("trusted_target_line_count_exact", target_lines == config.lineage.final_mention_count, target_lines)
        add("post_validation_recomputes", post.target_sha256 == target_sha and post.target_line_count == target_lines and post.post_promotion_validation_passed)
        add("trusted_pointer_lineage_exact", pointer.candidate_build_id == CANDIDATE_BUILD_ID and pointer.canonical_sha256 == CANONICAL_SHA256 and pointer.promotion_id == PROMOTION_ID)
        add("no_candidate_or_canonical_mutation", not record.candidate_mutated and not record.canonical_truth_mutated and not manifest.candidate_mutated and not manifest.canonical_truth_mutated)
        add("rollback_path_ready", previous.rollback_action in {"remove_latest_pointer", "restore_previous_latest_pointer"} and record.rollback_path_ready)
    except Exception as exc:
        add("promotion_record_recompute", False, f"{type(exc).__name__}: {exc}")
    failed = sum(1 for _, ok, _ in checks if not ok)
    return checks, {
        "report": REPORT_NAME,
        "promotion_id": PROMOTION_ID,
        "promotion_validated": failed == 0,
        "production_latest_active": failed == 0,
        "promotion_executed": failed == 0,
        "trusted_latest_pointer_updated": failed == 0,
        "post_promotion_validation_passed": failed == 0,
        "rollback_path_ready": failed == 0,
        "canonical_truth_mutated": False,
        "candidate_mutated": False,
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": config.next_steps.after_validation_pass if failed == 0 else config.next_steps.after_validation_fail,
    }


def plan_or_execute_h2_production_latest_rollback(
    *, project_root: Path, config_path: Path, promotion_dir: Path, trusted_root: Path,
    rollback_root: Path | None = None, execute: bool = False,
) -> dict[str, Any]:
    config = load_h2_production_latest_promotion_config(config_path.resolve())
    promotion_dir = promotion_dir.resolve()
    _require_exact_files(promotion_dir, OUTPUT_FILES, "Promotion record")
    installed = (promotion_dir / "installed_latest.json").read_bytes()
    previous = PreviousLatestState.model_validate(json.loads((promotion_dir / "previous_latest_state.json").read_text(encoding="utf-8")))
    pointer_path = trusted_root.resolve() / config.trusted_latest.pointer_name
    if not pointer_path.is_file() or pointer_path.read_bytes() != installed:
        raise H2ProductionLatestPromotionError("Rollback refused: current trusted latest is not the exact promoted pointer")
    resolved_rollback_root = rollback_root.resolve() if rollback_root is not None else _resolve(project_root, config.execution.rollback_output_root)
    rollback_dir = resolved_rollback_root / config.execution.rollback_id
    if not execute:
        return {
            "report": ROLLBACK_REPORT_NAME,
            "mode": "plan",
            "phase_complete": False,
            "rollback_id": ROLLBACK_ID,
            "promotion_id": PROMOTION_ID,
            "previous_latest_exists": previous.previous_latest_exists,
            "rollback_action": previous.rollback_action,
            "current_promoted_pointer_verified_before_rollback": True,
            "rollback_executed": False,
            "rollback_record_already_exists": rollback_dir.exists(),
            "plan_writes_output": False,
        }
    if rollback_dir.exists():
        raise H2ProductionLatestPromotionError(f"Immutable rollback record already exists: {rollback_dir}")
    if previous.previous_latest_exists:
        raw = base64.b64decode(previous.previous_latest_bytes_base64.encode("ascii"), validate=True)
        _atomic_write(pointer_path, raw)
        after_exists = True
        post_ok = pointer_path.read_bytes() == raw
    else:
        pointer_path.unlink()
        after_exists = False
        post_ok = not pointer_path.exists()
    if not post_ok:
        _atomic_write(pointer_path, installed)
        raise H2ProductionLatestPromotionError("Rollback postcheck failed; promoted pointer restored")
    record = H2ProductionLatestRollbackRecord(
        rollback_id=ROLLBACK_ID,
        promotion_id=PROMOTION_ID,
        previous_latest_exists=previous.previous_latest_exists,
        rollback_action=previous.rollback_action,
        current_promoted_pointer_verified_before_rollback=True,
        rollback_executed=True,
        rollback_postcheck_passed=True,
        trusted_latest_exists_after_rollback=after_exists,
        canonical_truth_mutated=False,
        candidate_mutated=False,
    )
    files = {
        "README.md": (
            "# H2 v0.3 Production-Latest Rollback\n\n"
            f"Rollback ID: `{ROLLBACK_ID}`\n\n"
            f"Promotion ID: `{PROMOTION_ID}`\n\n"
            f"Action: `{previous.rollback_action}`\n"
        ).encode("utf-8"),
        "rollback.json": _json_bytes(record),
    }
    files["checksums.txt"] = "".join(
        f"{_sha256_bytes(files[name])}  {name}\n" for name in sorted(files)
    ).encode("utf-8")
    resolved_rollback_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{ROLLBACK_ID}.tmp-", dir=resolved_rollback_root))
    try:
        for name, payload in files.items():
            (staging / name).write_bytes(payload)
        staging.rename(rollback_dir)
    except BaseException:
        # Restore promoted pointer if the rollback record cannot be finalized.
        _atomic_write(pointer_path, installed)
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {
        "report": ROLLBACK_REPORT_NAME,
        "mode": "execute",
        "phase_complete": True,
        "rollback_id": ROLLBACK_ID,
        "promotion_id": PROMOTION_ID,
        "previous_latest_exists": previous.previous_latest_exists,
        "rollback_action": previous.rollback_action,
        "current_promoted_pointer_verified_before_rollback": True,
        "rollback_executed": True,
        "rollback_postcheck_passed": True,
        "trusted_latest_exists_after_rollback": after_exists,
        "canonical_truth_mutated": False,
        "candidate_mutated": False,
        "rollback_record_already_exists": True,
        "rollback_record_dir": str(rollback_dir),
    }
