from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import (
    H2ProductionAuditAnnotation,
    H2ProductionAuditCase,
    H2ProductionAuditManifest,
    canonical_config_sha256 as audit_config_canonical_sha256,
    load_h2_production_audit_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_reference import (
    AUDIT_CONFIG_CANONICAL_SHA256,
    AUDIT_CONFIG_FILE_SHA256,
    AUDIT_ID,
    CANDIDATE_BUILD_ID,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    CANONICAL_SHA256,
    H2ProductionAuditReferenceConfig,
    H2ProductionAuditReferenceError,
    H2ProductionAuditReferenceManifest,
    H2ProductionAuditReferenceSummary,
    MANIFEST_SCHEMA_VERSION,
    MATERIALIZATION_FINGERPRINT,
    REFERENCE_ID,
    SUMMARY_SCHEMA_VERSION,
    load_h2_production_audit_reference_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_reference_freeze_v0.3.yaml"
DEFAULT_AUDIT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_v0.3.yaml"
DEFAULT_AUDIT_DIR = PROJECT_ROOT / "data" / "entities" / "scientific_entity_semantic_typer_h2_production_audit" / "v0.3" / AUDIT_ID
DEFAULT_ANNOTATIONS = PROJECT_ROOT / "data" / "entities" / "scientific_entity_semantic_typer_h2_production_audit_annotation_work" / "v0.3" / AUDIT_ID / "annotations_completed.jsonl"
REPORT_NAME = "scientific_entity_semantic_typer_h2_production_audit_reference_v03"
REQUIRED_AUDIT_FILES = ("README.md", "audit_cases.jsonl", "blank_annotations.jsonl", "checksums.txt", "manifest.json", "reviewer.html")
AUDIT_CHECKSUM_FILES = tuple(name for name in REQUIRED_AUDIT_FILES if name != "checksums.txt")
REFERENCE_FILES = ("README.md", "annotation_summary.json", "checksums.txt", "manifest.json", "reference_annotations.jsonl")
REFERENCE_CHECKSUM_FILES = tuple(name for name in REFERENCE_FILES if name != "checksums.txt")
IMMUTABLE_ANNOTATION_FIELDS = (
    "schema_version", "audit_id", "audit_case_id", "canonical_id", "source_field",
    "source_text_sha256", "source_text", "char_start", "char_end", "surface_text",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text_file_lf(path: Path) -> str:
    """Hash a UTF-8 text artifact after normalizing platform line endings to LF."""
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return _sha256_bytes(normalized)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[H2ProductionAuditAnnotation]) -> bytes:
    return "".join(
        json.dumps(row.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise H2ProductionAuditReferenceError(f"Expected JSON object: {path}")
    return payload


def _read_annotations(path: Path, *, expected_count: int = 240) -> list[H2ProductionAuditAnnotation]:
    rows: list[H2ProductionAuditAnnotation] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                raise H2ProductionAuditReferenceError(f"Blank JSONL line: {path}:{line_number}")
            rows.append(H2ProductionAuditAnnotation.model_validate(json.loads(raw)))
            if len(rows) > expected_count:
                raise H2ProductionAuditReferenceError(f"Annotation row count exceeds {expected_count}")
    if len(rows) != expected_count:
        raise H2ProductionAuditReferenceError(f"Expected {expected_count} annotation rows, got {len(rows)}")
    return rows


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = raw.split("  ", 1)
        if len(parts) != 2:
            raise H2ProductionAuditReferenceError(f"Invalid checksum line {line_number}: {path}")
        digest, name = parts
        if name in result:
            raise H2ProductionAuditReferenceError(f"Duplicate checksum filename: {name}")
        result[name] = digest
    return result


def _lf_ok(path: Path) -> bool:
    raw = path.read_bytes()
    return bool(raw) and not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and raw.endswith(b"\n")


def _validate_audit_package(
    *,
    config: H2ProductionAuditReferenceConfig,
    audit_config_path: Path,
    audit_dir: Path,
) -> tuple[H2ProductionAuditManifest, list[H2ProductionAuditAnnotation]]:
    if not audit_dir.is_dir():
        raise H2ProductionAuditReferenceError(f"Audit directory does not exist: {audit_dir}")
    names = sorted(path.name for path in audit_dir.iterdir() if path.is_file())
    if names != sorted(REQUIRED_AUDIT_FILES):
        raise H2ProductionAuditReferenceError(f"Audit package exact file layout drifted: {names}")
    checksums = _parse_checksums(audit_dir / "checksums.txt")
    if sorted(checksums) != sorted(AUDIT_CHECKSUM_FILES):
        raise H2ProductionAuditReferenceError("Audit checksum set drifted")
    for name in AUDIT_CHECKSUM_FILES:
        if checksums[name] != _sha256_file(audit_dir / name):
            raise H2ProductionAuditReferenceError(f"Audit checksum mismatch: {name}")
        # reviewer.html is a non-evidence helper artifact. Preserve exact-byte
        # integrity through its frozen checksum, but do not reject an otherwise
        # identical historical package solely because a Windows tool rewrote
        # HTML line endings. All semantic/reference-bearing parent artifacts
        # remain strict UTF-8 LF.
        if name == "reviewer.html":
            raw = (audit_dir / name).read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                raise H2ProductionAuditReferenceError("Audit reviewer.html must not contain a UTF-8 BOM")
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise H2ProductionAuditReferenceError("Audit reviewer.html must be valid UTF-8") from exc
        elif not _lf_ok(audit_dir / name):
            raise H2ProductionAuditReferenceError(f"Audit file must be UTF-8 LF: {name}")
    if not _lf_ok(audit_dir / "checksums.txt"):
        raise H2ProductionAuditReferenceError("Audit checksums.txt must be UTF-8 LF")

    if _sha256_text_file_lf(audit_config_path) != config.lineage.audit_config_file_sha256:
        raise H2ProductionAuditReferenceError("Audit config file SHA-256 drifted")
    audit_config = load_h2_production_audit_config(audit_config_path)
    canonical_sha = audit_config_canonical_sha256(audit_config)
    if canonical_sha != config.lineage.audit_config_canonical_sha256:
        raise H2ProductionAuditReferenceError("Audit canonical config SHA-256 drifted")

    manifest = H2ProductionAuditManifest.model_validate(_read_json(audit_dir / "manifest.json"))
    expected = {
        "audit_id": config.lineage.audit_id,
        "candidate_build_id": config.lineage.candidate_build_id,
        "candidate_id": config.lineage.candidate_id,
        "candidate_fingerprint_sha256": config.lineage.candidate_fingerprint_sha256,
        "materialization_fingerprint_sha256": config.lineage.materialization_fingerprint_sha256,
        "canonical_sha256": config.lineage.canonical_sha256,
        "canonical_document_count": config.lineage.canonical_document_count,
        "audit_config_sha256": config.lineage.audit_config_canonical_sha256,
        "audit_case_count": config.lineage.expected_audit_case_count,
        "prediction_blind": True,
        "sampled_stratum_exposed_in_cases": False,
        "candidate_prediction_exposed_in_cases": False,
        "semantic_scores_exposed_in_cases": False,
        "production_latest_promotion_authorized": False,
    }
    payload = manifest.model_dump(mode="json")
    for key, value in expected.items():
        if payload[key] != value:
            raise H2ProductionAuditReferenceError(f"Audit manifest lineage/safety mismatch: {key}")

    blanks = _read_annotations(audit_dir / "blank_annotations.jsonl")
    if any(row.annotation_complete for row in blanks):
        raise H2ProductionAuditReferenceError("Blank annotations unexpectedly contain completed rows")
    ids = [row.audit_case_id for row in blanks]
    if len(set(ids)) != len(ids):
        raise H2ProductionAuditReferenceError("Duplicate audit_case_id in blank annotations")

    cases: list[H2ProductionAuditCase] = []
    with (audit_dir / "audit_cases.jsonl").open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                raise H2ProductionAuditReferenceError(f"Blank audit case line: {line_number}")
            cases.append(H2ProductionAuditCase.model_validate(json.loads(raw)))
    if len(cases) != 240:
        raise H2ProductionAuditReferenceError(f"Expected 240 audit cases, got {len(cases)}")
    for index, (case, blank) in enumerate(zip(cases, blanks, strict=True), 1):
        case_payload = case.model_dump(mode="json")
        blank_payload = blank.model_dump(mode="json")
        for field in ("audit_id", "audit_case_id", "canonical_id", "source_field", "source_text_sha256", "source_text", "char_start", "char_end", "surface_text"):
            if case_payload[field] != blank_payload[field]:
                raise H2ProductionAuditReferenceError(f"Audit case/blank alignment drift at row {index}: {field}")
    return manifest, blanks


def _validate_completed(
    *,
    blanks: Sequence[H2ProductionAuditAnnotation],
    annotations_path: Path,
) -> list[H2ProductionAuditAnnotation]:
    completed = _read_annotations(annotations_path)
    ids = [row.audit_case_id for row in completed]
    if len(set(ids)) != len(ids):
        raise H2ProductionAuditReferenceError("Duplicate audit_case_id in completed annotations")
    for index, (blank, row) in enumerate(zip(blanks, completed, strict=True), 1):
        if row.audit_case_id != blank.audit_case_id:
            raise H2ProductionAuditReferenceError(f"Annotation row order/case alignment drift at row {index}")
        blank_payload = blank.model_dump(mode="json")
        row_payload = row.model_dump(mode="json")
        for field in IMMUTABLE_ANNOTATION_FIELDS:
            if row_payload[field] != blank_payload[field]:
                raise H2ProductionAuditReferenceError(f"Immutable annotation field changed at row {index}: {field}")
        if row.annotation_complete is not True:
            raise H2ProductionAuditReferenceError(f"Annotation row is incomplete: {row.audit_case_id}")
        if row.span_status is None or row.annotation_confidence is None:
            raise H2ProductionAuditReferenceError(f"Completed row lacks required human labels: {row.audit_case_id}")
    return completed


def _summary(rows: Sequence[H2ProductionAuditAnnotation]) -> H2ProductionAuditReferenceSummary:
    status = Counter(str(row.span_status) for row in rows)
    types = Counter(row.reference_entity_type.value if row.reference_entity_type is not None else "null" for row in rows)
    conf = Counter(str(row.annotation_confidence) for row in rows)
    n = len(rows)
    uncertain = status["uncertain"]
    not_entity = status["not_an_entity"]
    boundary = status["boundary_issue"]
    valid = status["valid_entity_span"]
    notes = sum(1 for row in rows if row.reviewer_note is not None and row.reviewer_note.strip())
    return H2ProductionAuditReferenceSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        reference_id=REFERENCE_ID,
        audit_id=AUDIT_ID,
        annotation_row_count=240,
        completed_annotation_row_count=240,
        span_status_count=dict(sorted(status.items())),
        reference_type_count=dict(sorted(types.items())),
        confidence_count=dict(sorted(conf.items())),
        reviewer_note_nonempty_count=notes,
        uncertain_count=uncertain,
        not_an_entity_count=not_entity,
        boundary_issue_count=boundary,
        valid_entity_span_count=valid,
        uncertain_rate=uncertain / n,
        not_an_entity_rate=not_entity / n,
        boundary_issue_rate=boundary / n,
        promotion_gates_evaluated=False,
        sampled_strata_reconstructed=False,
        candidate_prediction_files_read=False,
    )


def _compute_reference_package(
    *,
    config_path: Path,
    audit_config_path: Path,
    audit_dir: Path,
    annotations_path: Path,
    annotator_ids: Sequence[str],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    config = load_h2_production_audit_reference_config(config_path)
    normalized_annotators = [value.strip() for value in annotator_ids]
    if not normalized_annotators or any(not value for value in normalized_annotators) or len(set(normalized_annotators)) != len(normalized_annotators):
        raise H2ProductionAuditReferenceError("At least one unique non-empty annotator ID is required")
    manifest_parent, blanks = _validate_audit_package(config=config, audit_config_path=audit_config_path, audit_dir=audit_dir)
    completed = _validate_completed(blanks=blanks, annotations_path=annotations_path)
    summary = _summary(completed)
    reference_bytes = _jsonl_bytes(completed)
    summary_bytes = _json_bytes(summary.model_dump(mode="json"))
    completed_source_sha = _sha256_file(annotations_path)
    manifest = H2ProductionAuditReferenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        reference_id=REFERENCE_ID,
        audit_id=AUDIT_ID,
        candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        audit_config_file_sha256=AUDIT_CONFIG_FILE_SHA256,
        audit_config_canonical_sha256=AUDIT_CONFIG_CANONICAL_SHA256,
        audit_sample_manifest_sha256=_sha256_file(audit_dir / "manifest.json"),
        audit_cases_sha256=_sha256_file(audit_dir / "audit_cases.jsonl"),
        blank_annotations_sha256=_sha256_file(audit_dir / "blank_annotations.jsonl"),
        completed_annotations_source_sha256=completed_source_sha,
        reference_annotations_sha256=_sha256_bytes(reference_bytes),
        annotation_summary_sha256=_sha256_bytes(summary_bytes),
        annotator_ids=normalized_annotators,
        annotation_row_count=240,
        completed_annotation_row_count=240,
        prediction_blind=True,
        reference_frozen=True,
        candidate_prediction_files_read=False,
        sampled_strata_reconstructed=False,
        unblinding_executed=False,
        promotion_gates_evaluated=False,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        production_latest_promotion_authorized=False,
        latest_overwritten=False,
        publication_ready=False,
        next_slice="unblind_and_evaluate_h2_production_audit_promotion_gate",
    )
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    readme = (
        "# H2 v0.3 Production Audit Frozen Reference\n\n"
        f"Reference ID: `{REFERENCE_ID}`\n\n"
        f"Audit ID: `{AUDIT_ID}`\n\n"
        "This immutable package freezes the prediction-blind human decisions for all 240 production-audit spans.\n\n"
        "No candidate prediction file was read by this slice. Hidden audit strata were not reconstructed. "
        "Promotion gates were not evaluated and production promotion remains unauthorized.\n"
    ).encode("utf-8")
    files: dict[str, bytes] = {
        "reference_annotations.jsonl": reference_bytes,
        "annotation_summary.json": summary_bytes,
        "manifest.json": manifest_bytes,
        "README.md": readme,
    }
    files["checksums.txt"] = "".join(
        f"{_sha256_bytes(files[name])}  {name}\n" for name in sorted(files)
    ).encode("utf-8")
    report = {
        "report": REPORT_NAME,
        "reference_id": REFERENCE_ID,
        "audit_id": AUDIT_ID,
        "annotation_row_count": 240,
        "completed_annotation_row_count": 240,
        "completed_annotations_source_sha256": completed_source_sha,
        "span_status_count": summary.span_status_count,
        "reference_type_count": summary.reference_type_count,
        "confidence_count": summary.confidence_count,
        "uncertain_count": summary.uncertain_count,
        "not_an_entity_count": summary.not_an_entity_count,
        "boundary_issue_count": summary.boundary_issue_count,
        "prediction_blind": True,
        "reference_frozen": True,
        "candidate_prediction_files_read": False,
        "sampled_strata_reconstructed": False,
        "unblinding_executed": False,
        "promotion_gates_evaluated": False,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "canonical_truth_mutated": False,
        "production_latest_promotion_authorized": False,
        "next_slice": "unblind_and_evaluate_h2_production_audit_promotion_gate",
    }
    return files, report


def freeze_h2_production_audit_reference(
    *,
    project_root: Path,
    config_path: Path,
    audit_config_path: Path,
    audit_dir: Path,
    annotations_path: Path,
    annotator_ids: Sequence[str],
    output_root: Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    config = load_h2_production_audit_reference_config(config_path.resolve())
    files, report = _compute_reference_package(
        config_path=config_path.resolve(),
        audit_config_path=audit_config_path.resolve(),
        audit_dir=audit_dir.resolve(),
        annotations_path=annotations_path.resolve(),
        annotator_ids=annotator_ids,
    )
    root = (output_root.resolve() if output_root is not None else (project_root.resolve() / config.outputs.frozen_root).resolve())
    output_dir = root / config.outputs.reference_id
    exists = output_dir.exists()
    result = {
        **report,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "reference_frozen": False,
        "reference_already_exists": exists,
        "plan_writes_output": False,
        "output_dir": str(output_dir),
        "next_slice": config.next_steps.after_plan if not execute else config.next_steps.after_execute,
    }
    if not execute:
        return result
    if exists:
        raise H2ProductionAuditReferenceError(f"Immutable reference directory already exists: {output_dir}")
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{config.outputs.reference_id}.tmp-", dir=root))
    try:
        for name, payload in files.items():
            (staging / name).write_bytes(payload)
        staging.rename(output_dir)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    result.update({"phase_complete": True, "reference_frozen": True, "reference_already_exists": True})
    return result


def validate_frozen_h2_production_audit_reference(
    *,
    project_root: Path,
    config_path: Path,
    audit_config_path: Path,
    audit_dir: Path,
    annotations_path: Path,
    reference_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    config = load_h2_production_audit_reference_config(config_path.resolve())
    reference_dir = reference_dir.resolve()
    add("reference_directory_exists", reference_dir.is_dir(), str(reference_dir))
    if not reference_dir.is_dir():
        summary = {"report": REPORT_NAME, "total_checks": len(checks), "required_failed_count": 1}
        return checks, summary
    names = sorted(path.name for path in reference_dir.iterdir() if path.is_file())
    add("exact_file_layout", names == sorted(REFERENCE_FILES), str(names))
    checksum_map = _parse_checksums(reference_dir / "checksums.txt") if (reference_dir / "checksums.txt").exists() else {}
    add("checksum_set_exact", sorted(checksum_map) == sorted(REFERENCE_CHECKSUM_FILES), str(sorted(checksum_map)))
    for name in REFERENCE_CHECKSUM_FILES:
        path = reference_dir / name
        add(f"checksum:{name}", path.is_file() and checksum_map.get(name) == _sha256_file(path), name)
    for name in REFERENCE_FILES:
        path = reference_dir / name
        add(f"lf:{name}", path.is_file() and _lf_ok(path), name)

    try:
        expected_files, expected_report = _compute_reference_package(
            config_path=config_path.resolve(),
            audit_config_path=audit_config_path.resolve(),
            audit_dir=audit_dir.resolve(),
            annotations_path=annotations_path.resolve(),
            annotator_ids=H2ProductionAuditReferenceManifest.model_validate(_read_json(reference_dir / "manifest.json")).annotator_ids,
        )
        manifest = H2ProductionAuditReferenceManifest.model_validate(_read_json(reference_dir / "manifest.json"))
        frozen_summary = H2ProductionAuditReferenceSummary.model_validate(_read_json(reference_dir / "annotation_summary.json"))
        frozen_rows = _read_annotations(reference_dir / "reference_annotations.jsonl")
        add("manifest_schema_and_lineage", manifest.reference_id == config.outputs.reference_id and manifest.audit_id == config.lineage.audit_id)
        add("manifest_safety_flags", manifest.prediction_blind and manifest.reference_frozen and not manifest.candidate_prediction_files_read and not manifest.sampled_strata_reconstructed and not manifest.unblinding_executed and not manifest.promotion_gates_evaluated and not manifest.production_latest_promotion_authorized)
        add("summary_schema_and_counts", frozen_summary.annotation_row_count == 240 and sum(frozen_summary.span_status_count.values()) == 240)
        add("reference_row_count", len(frozen_rows) == 240, str(len(frozen_rows)))
        add("reference_case_ids_unique", len({row.audit_case_id for row in frozen_rows}) == 240)
        add("all_reference_rows_complete", all(row.annotation_complete for row in frozen_rows))
        add("reference_recomputes_exactly", (reference_dir / "reference_annotations.jsonl").read_bytes() == expected_files["reference_annotations.jsonl"])
        add("summary_recomputes_exactly", (reference_dir / "annotation_summary.json").read_bytes() == expected_files["annotation_summary.json"])
        add("manifest_recomputes_exactly", (reference_dir / "manifest.json").read_bytes() == expected_files["manifest.json"])
        add("readme_recomputes_exactly", (reference_dir / "README.md").read_bytes() == expected_files["README.md"])
        add("checksums_recompute_exactly", (reference_dir / "checksums.txt").read_bytes() == expected_files["checksums.txt"])
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, H2ProductionAuditReferenceError) as exc:
        add("independent_recomputation", False, f"{type(exc).__name__}: {exc}")
        expected_report = {
            "annotation_row_count": 0,
            "completed_annotation_row_count": 0,
            "completed_annotations_source_sha256": "",
            "uncertain_count": 0,
            "not_an_entity_count": 0,
            "boundary_issue_count": 0,
            "prediction_blind": False,
            "reference_frozen": False,
            "candidate_prediction_files_read": False,
            "sampled_strata_reconstructed": False,
            "unblinding_executed": False,
            "promotion_gates_evaluated": False,
            "model_inference_executed": False,
            "threshold_tuning_executed": False,
            "policy_revision_executed": False,
            "canonical_truth_mutated": False,
            "production_latest_promotion_authorized": False,
        }

    failed = sum(1 for _, ok, _ in checks if not ok)
    report = {
        "report": REPORT_NAME,
        "reference_id": config.outputs.reference_id,
        "audit_id": config.lineage.audit_id,
        "annotation_row_count": expected_report["annotation_row_count"],
        "completed_annotation_row_count": expected_report["completed_annotation_row_count"],
        "completed_annotations_source_sha256": expected_report["completed_annotations_source_sha256"],
        "uncertain_count": expected_report["uncertain_count"],
        "not_an_entity_count": expected_report["not_an_entity_count"],
        "boundary_issue_count": expected_report["boundary_issue_count"],
        "prediction_blind": expected_report["prediction_blind"],
        "reference_frozen": expected_report["reference_frozen"],
        "candidate_prediction_files_read": expected_report["candidate_prediction_files_read"],
        "sampled_strata_reconstructed": expected_report["sampled_strata_reconstructed"],
        "unblinding_executed": expected_report["unblinding_executed"],
        "promotion_gates_evaluated": expected_report["promotion_gates_evaluated"],
        "model_inference_executed": expected_report["model_inference_executed"],
        "threshold_tuning_executed": expected_report["threshold_tuning_executed"],
        "policy_revision_executed": expected_report["policy_revision_executed"],
        "canonical_truth_mutated": expected_report["canonical_truth_mutated"],
        "production_latest_promotion_authorized": expected_report["production_latest_promotion_authorized"],
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": config.next_steps.after_validation if failed == 0 else "repair_or_rebuild_h2_production_audit_reference",
    }
    return checks, report
