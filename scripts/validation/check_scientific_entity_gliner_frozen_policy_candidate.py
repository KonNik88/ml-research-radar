from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    build_evidence_id,
    build_extractor_fingerprint,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationProfileName,
    ScientificEntityCalibrationProfiles,
    ScientificEntityCalibrationTrial,
    ScientificEntityGLiNERCalibrationManifest,
)
from radar_core.contracts.scientific_entity_gliner_frozen_policy import (
    ScientificEntityFrozenPolicyEvidenceLineage,
    ScientificEntityGLiNERFrozenPolicyDerivationManifest,
)
from radar_core.entities.scientific_entity_gliner_frozen_policy import (
    ScientificEntityGLiNERFrozenPolicyError,
    build_frozen_policy_extractor_descriptor,
    load_gliner_frozen_policy_config,
    materialize_frozen_policy_mentions,
    validate_frozen_trial,
)
from scripts.entities.build_scientific_entity_gliner_frozen_policy_candidate import (
    CHECKSUM_FILES,
    DEFAULT_CONFIG_PATH,
    QUALITY_SCHEMA_VERSION,
    REQUIRED_FILES,
)


REPORT_BASENAME = "scientific_entity_gliner_frozen_policy_candidate"
REPORT_SCHEMA_VERSION = "scientific_entity_gliner_frozen_policy_validation_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    required: bool = True
    details: str | None = None


def _normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _resolve_project_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"Blank JSONL line: {path}:{line_number}")
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object: {path}:{line_number}")
        rows.append(payload)
    return rows


def _text_is_utf8_lf(path: Path) -> tuple[bool, str | None]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "UTF-8 BOM is forbidden"
    if b"\r" in raw:
        return False, "CR or CRLF line endings are forbidden"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"invalid UTF-8: {exc}"
    if raw and not raw.endswith(b"\n"):
        return False, "text file must end with LF"
    return True, None


def _parse_checksums(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "  " not in line:
            raise ValueError(f"Invalid checksum row: {line_number}")
        digest, filename = line.split("  ", 1)
        if not SHA256_RE.fullmatch(digest):
            raise ValueError(f"Invalid checksum digest: {line_number}")
        if not filename or filename in parsed:
            raise ValueError(f"Invalid or duplicate checksum path: {line_number}")
        parsed[filename] = digest
    return parsed


def _add(
    checks: list[CheckResult],
    name: str,
    ok: bool,
    details: str | None = None,
    *,
    required: bool = True,
) -> None:
    checks.append(CheckResult(name=name, ok=bool(ok), required=required, details=details))


def _build_report(
    *,
    build_dir: Path,
    checks: Sequence[CheckResult],
    manifest: ScientificEntityEvidenceManifest | None,
    derivation: ScientificEntityGLiNERFrozenPolicyDerivationManifest | None,
) -> dict[str, Any]:
    failed = [row for row in checks if row.required and not row.ok]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "read_only_frozen_gliner_policy_candidate_validation",
        "build_dir": _normalize_path(build_dir),
        "summary": {
            "ok": not failed,
            "total_checks": len(checks),
            "passed_checks_count": sum(row.ok for row in checks),
            "required_failed_count": len(failed),
            "build_id": manifest.build_id if manifest else None,
            "parent_build_id": derivation.parent_build_id if derivation else None,
            "calibration_id": derivation.calibration_id if derivation else None,
            "selected_trial_id": derivation.selected_trial_id if derivation else None,
            "mention_count": manifest.mention_count if manifest else None,
        },
        "checks": [asdict(row) for row in checks],
        "verdict": {
            "candidate_valid": not failed,
            "dev_evaluation_reproduction_authorized": not failed,
            "heldout_collection_authorized": False,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "current_dev_set_is_held_out": False,
            "canonical_mutation_allowed": False,
            "reconcile_input_allowed": False,
            "publication_allowed": False,
            "required_failed_checks": [row.name for row in failed],
            "next_slice": (
                "reproduce_frozen_policy_candidate_dev_evaluation_v0.1"
                if not failed
                else None
            ),
        },
    }
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"]["required_failed_count"]
    return report


def _write_reports(report: dict[str, Any], report_dir: Path) -> None:
    history_dir = report_dir / "history"
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    markdown = "\n".join(
        [
            "# Scientific Entity GLiNER frozen-policy candidate validation",
            "",
            f"- status: `{'OK' if report['summary']['ok'] else 'FAILED'}`",
            "- candidate is development-only derived evidence",
            "- no model inference, full-corpus, production, reconcile, or publication authorization",
            "",
        ]
    )
    for path, text in (
        (report_dir / f"{REPORT_BASENAME}_latest.json", json_text),
        (report_dir / f"{REPORT_BASENAME}_latest.md", markdown),
        (history_dir / f"{REPORT_BASENAME}_{slug}.json", json_text),
        (history_dir / f"{REPORT_BASENAME}_{slug}.md", markdown),
    ):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def validate_frozen_policy_candidate(
    *,
    build_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    build_dir = build_dir.resolve()
    config_path = config_path.resolve()
    config = load_gliner_frozen_policy_config(config_path)
    selected_report_dir = report_dir or _resolve_project_path(config.validation.report_dir)
    checks: list[CheckResult] = []
    manifest: ScientificEntityEvidenceManifest | None = None
    derivation: ScientificEntityGLiNERFrozenPolicyDerivationManifest | None = None

    _add(checks, "build_directory_exists", build_dir.is_dir(), _normalize_path(build_dir))
    if not build_dir.is_dir():
        report = _build_report(build_dir=build_dir, checks=checks, manifest=None, derivation=None)
        if write_reports:
            _write_reports(report, selected_report_dir)
        return report

    actual_files = {path.name for path in build_dir.iterdir() if path.is_file()}
    actual_dirs = {path.name for path in build_dir.iterdir() if path.is_dir()}
    _add(checks, "required_output_files_present", set(REQUIRED_FILES) <= actual_files)
    _add(checks, "unexpected_output_files_absent", actual_files == set(REQUIRED_FILES))
    _add(checks, "nested_output_directories_absent", not actual_dirs)
    if not set(REQUIRED_FILES) <= actual_files:
        report = _build_report(build_dir=build_dir, checks=checks, manifest=None, derivation=None)
        if write_reports:
            _write_reports(report, selected_report_dir)
        return report

    for filename in REQUIRED_FILES:
        ok, details = _text_is_utf8_lf(build_dir / filename)
        _add(checks, f"output_utf8_lf:{filename}", ok, details)

    try:
        checksums = _parse_checksums(build_dir / "checksums.txt")
        _add(checks, "checksums_file_valid", True)
    except (OSError, ValueError) as exc:
        checksums = {}
        _add(checks, "checksums_file_valid", False, str(exc))
    _add(checks, "checksums_cover_exact_files", set(checksums) == set(CHECKSUM_FILES))
    for filename in CHECKSUM_FILES:
        _add(
            checks,
            f"checksum_matches:{filename}",
            checksums.get(filename) == _sha256_file(build_dir / filename),
        )

    try:
        manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(build_dir / "manifest.json"))
        derivation = ScientificEntityGLiNERFrozenPolicyDerivationManifest.model_validate(
            _read_json(build_dir / "derivation_manifest.json")
        )
        mentions = tuple(
            ScientificEntityMentionEvidence.model_validate(row)
            for row in _read_jsonl(build_dir / "mentions.jsonl")
        )
        lineage = tuple(
            ScientificEntityFrozenPolicyEvidenceLineage.model_validate(row)
            for row in _read_jsonl(build_dir / "evidence_lineage.jsonl")
        )
        quality = _read_json(build_dir / "data_quality_summary.json")
        schema = _read_json(build_dir / "schema.json")
        _add(checks, "candidate_contracts_parse", True)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        _add(checks, "candidate_contracts_parse", False, f"{type(exc).__name__}: {exc}")
        report = _build_report(
            build_dir=build_dir,
            checks=checks,
            manifest=manifest,
            derivation=derivation,
        )
        if write_reports:
            _write_reports(report, selected_report_dir)
        return report

    assert manifest is not None and derivation is not None
    _add(checks, "build_directory_matches_build_id", build_dir.name == manifest.build_id)
    _add(checks, "derivation_build_id_matches", derivation.build_id == manifest.build_id)
    _add(checks, "manifest_mention_count_matches", manifest.mention_count == len(mentions))
    _add(
        checks,
        "manifest_mentions_sha_matches",
        manifest.mentions_sha256 == _sha256_file(build_dir / "mentions.jsonl"),
    )
    _add(checks, "quality_schema_version_matches", quality.get("schema_version") == QUALITY_SCHEMA_VERSION)
    _add(checks, "quality_selected_count_matches", quality.get("selected_prediction_count") == len(mentions))
    _add(checks, "lineage_count_matches_mentions", len(lineage) == len(mentions) == derivation.lineage_count)
    _add(
        checks,
        "lineage_sha_matches",
        derivation.lineage_sha256 == _sha256_file(build_dir / "evidence_lineage.jsonl"),
    )
    _add(
        checks,
        "schema_declares_derivation_contract",
        schema.get("derivation_manifest_schema_version") == derivation.schema_version,
    )
    _add(
        checks,
        "schema_declares_lineage_contract",
        schema.get("evidence_lineage_schema_version")
        == (lineage[0].schema_version if lineage else None),
    )

    _add(checks, "frozen_parent_build_id_matches_config", derivation.parent_build_id == config.frozen.parent_build_id)
    _add(checks, "frozen_calibration_id_matches_config", derivation.calibration_id == config.frozen.calibration_id)
    _add(checks, "frozen_trial_id_matches_config", derivation.selected_trial_id == config.frozen.selected_trial_id)
    _add(checks, "frozen_policy_matches_config", derivation.policy == config.frozen.policy)
    _add(checks, "frozen_input_threshold_matches", derivation.input_threshold == config.frozen.input_threshold)
    _add(checks, "frozen_threshold_is_inclusive", derivation.threshold_is_inclusive is True)
    _add(checks, "input_count_matches_frozen_decision", derivation.input_prediction_count == config.frozen.expected_input_prediction_count)
    _add(checks, "selected_count_matches_frozen_decision", derivation.selected_prediction_count == config.frozen.expected_selected_prediction_count)
    _add(checks, "rejected_count_matches_frozen_decision", derivation.rejected_prediction_count == config.frozen.expected_rejected_prediction_count)

    parent_manifest_path = _resolve_project_path(derivation.parent_manifest_path)
    parent_mentions_path = _resolve_project_path(derivation.parent_mentions_path)
    calibration_manifest_path = _resolve_project_path(derivation.calibration_manifest_path)
    calibration_trials_path = _resolve_project_path(derivation.calibration_trials_path)
    calibration_profiles_path = _resolve_project_path(derivation.calibration_profiles_path)
    for name, path in (
        ("parent_manifest", parent_manifest_path),
        ("parent_mentions", parent_mentions_path),
        ("calibration_manifest", calibration_manifest_path),
        ("calibration_trials", calibration_trials_path),
        ("calibration_profiles", calibration_profiles_path),
    ):
        _add(checks, f"lineage_input_exists:{name}", path.is_file(), _normalize_path(path))

    if all(
        path.is_file()
        for path in (
            parent_manifest_path,
            parent_mentions_path,
            calibration_manifest_path,
            calibration_trials_path,
            calibration_profiles_path,
        )
    ):
        _add(checks, "parent_manifest_sha_matches", derivation.parent_manifest_sha256 == _sha256_file(parent_manifest_path))
        _add(checks, "parent_mentions_sha_matches", derivation.parent_mentions_sha256 == _sha256_file(parent_mentions_path))
        _add(checks, "calibration_manifest_sha_matches", derivation.calibration_manifest_sha256 == _sha256_file(calibration_manifest_path))
        _add(checks, "calibration_trials_sha_matches", derivation.calibration_trials_sha256 == _sha256_file(calibration_trials_path))
        _add(checks, "calibration_profiles_sha_matches", derivation.calibration_profiles_sha256 == _sha256_file(calibration_profiles_path))

        parent_manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(parent_manifest_path))
        parent_mentions = tuple(
            ScientificEntityMentionEvidence.model_validate(row)
            for row in _read_jsonl(parent_mentions_path)
        )
        calibration_manifest = ScientificEntityGLiNERCalibrationManifest.model_validate(
            _read_json(calibration_manifest_path)
        )
        trials = [
            ScientificEntityCalibrationTrial.model_validate(row)
            for row in _read_jsonl(calibration_trials_path)
        ]
        profiles = ScientificEntityCalibrationProfiles.model_validate(_read_json(calibration_profiles_path))

        _add(checks, "parent_manifest_build_id_matches", parent_manifest.build_id == config.frozen.parent_build_id)
        _add(checks, "parent_extractor_fingerprint_matches_derivation", parent_manifest.extractor_fingerprint == derivation.parent_extractor_fingerprint)
        _add(checks, "calibration_prediction_build_matches_parent", calibration_manifest.inputs.prediction_build_id == parent_manifest.build_id)
        _add(checks, "calibration_prediction_fingerprint_matches_parent", calibration_manifest.inputs.prediction_extractor_fingerprint == parent_manifest.extractor_fingerprint)
        selected_trials = [row for row in trials if row.trial_id == config.frozen.selected_trial_id]
        _add(checks, "selected_trial_exists_once", len(selected_trials) == 1)
        if len(selected_trials) == 1:
            try:
                validate_frozen_trial(config=config, trial=selected_trials[0])
                _add(checks, "selected_trial_matches_frozen_decision", True)
            except ScientificEntityGLiNERFrozenPolicyError as exc:
                _add(checks, "selected_trial_matches_frozen_decision", False, str(exc))
        balanced = [
            row
            for row in profiles.selections
            if row.profile_name == ScientificEntityCalibrationProfileName.BALANCED
        ]
        _add(
            checks,
            "balanced_profile_references_frozen_trial",
            len(balanced) == 1 and balanced[0].trial_id == config.frozen.selected_trial_id,
        )

        descriptor = build_frozen_policy_extractor_descriptor(
            config=config,
            parent_manifest=parent_manifest,
            project_root=PROJECT_ROOT,
        )
        recomputed_fingerprint = build_extractor_fingerprint(descriptor)
        _add(checks, "candidate_fingerprint_recomputed", recomputed_fingerprint == manifest.extractor_fingerprint == derivation.candidate_extractor_fingerprint)
        _add(checks, "candidate_fingerprint_differs_from_parent", recomputed_fingerprint != parent_manifest.extractor_fingerprint)

        try:
            expected_mentions, expected_lineage = materialize_frozen_policy_mentions(
                parent_mentions=parent_mentions,
                config=config,
                build_id=manifest.build_id,
                candidate_extractor_fingerprint=recomputed_fingerprint,
            )
            _add(checks, "deterministic_policy_recomputation_succeeds", True)
        except (ScientificEntityGLiNERFrozenPolicyError, ValueError) as exc:
            expected_mentions, expected_lineage = (), ()
            _add(checks, "deterministic_policy_recomputation_succeeds", False, str(exc))

        _add(
            checks,
            "candidate_mentions_match_deterministic_recomputation",
            [row.model_dump(mode="json") for row in mentions]
            == [row.model_dump(mode="json") for row in expected_mentions],
        )
        _add(
            checks,
            "evidence_lineage_matches_deterministic_recomputation",
            [row.model_dump(mode="json") for row in lineage]
            == [row.model_dump(mode="json") for row in expected_lineage],
        )
        parent_by_mention = {row.mention_id: row for row in parent_mentions}
        lineage_by_mention = {row.mention_id: row for row in lineage}
        semantic_errors: list[str] = []
        for candidate in mentions:
            parent = parent_by_mention.get(candidate.mention_id)
            line = lineage_by_mention.get(candidate.mention_id)
            if parent is None or line is None:
                semantic_errors.append(f"missing parent/lineage for {candidate.mention_id}")
                continue
            if (
                candidate.canonical_id != parent.canonical_id
                or candidate.entity_type != parent.entity_type
                or candidate.source_field != parent.source_field
                or candidate.source_text_sha256 != parent.source_text_sha256
                or candidate.char_start != parent.char_start
                or candidate.char_end != parent.char_end
                or candidate.surface_text != parent.surface_text
                or candidate.confidence_kind != parent.confidence_kind
                or candidate.confidence_score != parent.confidence_score
                or candidate.calibration_id != parent.calibration_id
            ):
                semantic_errors.append(f"parent semantics changed for {candidate.mention_id}")
            expected_evidence_id = build_evidence_id(
                mention_id=candidate.mention_id,
                extractor_fingerprint=manifest.extractor_fingerprint,
            )
            if candidate.evidence_id != expected_evidence_id:
                semantic_errors.append(f"candidate evidence_id mismatch for {candidate.mention_id}")
            if line.parent_evidence_id != parent.evidence_id or line.candidate_evidence_id != candidate.evidence_id:
                semantic_errors.append(f"lineage evidence ids mismatch for {candidate.mention_id}")
        _add(
            checks,
            "parent_semantics_preserved_and_evidence_identity_recomputed",
            not semantic_errors,
            "; ".join(semantic_errors[:5]) or None,
        )

    readme = (build_dir / "README.md").read_text(encoding="utf-8")
    _add(checks, "readme_rejects_canonical_truth", "not canonical paper truth" in readme)
    _add(checks, "readme_rejects_full_corpus", "not a full-corpus build" in readme)
    _add(checks, "readme_rejects_production", "not a production-selected" in readme)
    _add(checks, "readme_rejects_publication", "not publication ready" in readme)
    _add(checks, "readme_states_no_inference", "No GLiNER inference" in readme)

    report = _build_report(
        build_dir=build_dir,
        checks=checks,
        manifest=manifest,
        derivation=derivation,
    )
    if write_reports:
        _write_reports(report, selected_report_dir)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an immutable frozen-policy GLiNER Scientific Entity candidate "
            "and independently recompute threshold selection and evidence lineage."
        )
    )
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_frozen_policy_candidate(
            build_dir=args.build_dir,
            config_path=args.config,
            write_reports=not args.no_write_reports,
            report_dir=args.report_dir,
        )
    except (FileNotFoundError, OSError, ValueError, ValidationError) as exc:
        print(f"[FAILED] report={REPORT_BASENAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    prefix = "OK" if report["summary"]["ok"] else "FAILED"
    summary = report["summary"]
    print(f"[{prefix}] report={REPORT_BASENAME}")
    print(f"[{prefix}] total_checks={summary['total_checks']}")
    print(f"[{prefix}] required_failed_count={summary['required_failed_count']}")
    print(f"[{prefix}] build_id={summary['build_id']}")
    print(f"[{prefix}] parent_build_id={summary['parent_build_id']}")
    print(f"[{prefix}] calibration_id={summary['calibration_id']}")
    print(f"[{prefix}] selected_trial_id={summary['selected_trial_id']}")
    print(f"[{prefix}] mention_count={summary['mention_count']}")
    print(f"[{prefix}] next_slice={report['verdict']['next_slice']}")
    if args.strict and not report["summary"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
