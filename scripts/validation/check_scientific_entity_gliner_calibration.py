from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityType,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationDiagnostics,
    ScientificEntityCalibrationParetoFrontier,
    ScientificEntityCalibrationProfiles,
    ScientificEntityCalibrationStatus,
    ScientificEntityCalibrationTrial,
    ScientificEntityCalibrationTrialStage,
    ScientificEntityGLiNERCalibrationManifest,
)
from radar_core.entities.scientific_entity_gliner_calibration import (
    gliner_calibration_config_sha256,
    load_gliner_calibration_config,
)
from scripts.entities.calibrate_scientific_entity_gliner import (
    CHECKSUM_FILES,
    DEFAULT_CONFIG_PATH,
    REQUIRED_FILES,
    calibrate_gliner_predictions,
)


REPORT_BASENAME = "scientific_entity_gliner_calibration"
REPORT_SCHEMA_VERSION = "scientific_entity_gliner_calibration_validation_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
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
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
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
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
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
    checks.append(
        CheckResult(
            name=name,
            ok=bool(ok),
            required=required,
            details=details,
        )
    )


def _build_report(
    *,
    calibration_dir: Path,
    config_path: Path,
    checks: Sequence[CheckResult],
    manifest: ScientificEntityGLiNERCalibrationManifest | None,
) -> dict[str, Any]:
    failed = [row for row in checks if row.required and not row.ok]
    if manifest is not None and (
        manifest.status == ScientificEntityCalibrationStatus.FIXTURE
    ):
        success_next_slice = (
            "execute_existing_24_paper_gliner_dev_calibration_v0.1"
        )
    else:
        success_next_slice = "review_and_freeze_one_gliner_dev_policy_v0.1"
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "read_only_bounded_gliner_calibration_validation",
        "calibration_dir": _normalize_path(calibration_dir),
        "config_path": _normalize_path(config_path),
        "summary": {
            "ok": not failed,
            "total_checks": len(checks),
            "passed_checks_count": sum(row.ok for row in checks),
            "required_failed_count": len(failed),
            "calibration_id": manifest.calibration_id if manifest else None,
            "calibration_status": manifest.status.value if manifest else None,
            "document_count": manifest.inputs.document_count if manifest else None,
            "trial_count": (
                manifest.search_space_trial_count if manifest else None
            ),
        },
        "checks": [asdict(row) for row in checks],
        "verdict": {
            "calibration_valid": not failed,
            "dev_policy_review_authorized": not failed,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "current_dev_set_is_held_out": False,
            "canonical_mutation_allowed": False,
            "reconcile_input_allowed": False,
            "publication_allowed": False,
            "required_failed_checks": [row.name for row in failed],
            "next_slice": success_next_slice if not failed else None,
        },
    }
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"][
        "required_failed_count"
    ]
    return report


def _write_reports(report: dict[str, Any], report_dir: Path) -> None:
    history_dir = report_dir / "history"
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    markdown = "\n".join(
        [
            "# Scientific Entity GLiNER calibration validation",
            "",
            f"- status: `{'OK' if report['summary']['ok'] else 'FAILED'}`",
            "- calibration is development-only threshold-policy evidence",
            "- no production, full-corpus, reconcile, or publication authorization",
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


def _input_hash_checks(
    checks: list[CheckResult],
    manifest: ScientificEntityGLiNERCalibrationManifest,
) -> None:
    inputs = manifest.inputs
    declared = {
        "documents": (inputs.documents_path, inputs.documents_sha256),
        "review_manifest": (
            inputs.review_manifest_path,
            inputs.review_manifest_sha256,
        ),
        "reference_mentions": (
            inputs.reference_mentions_path,
            inputs.reference_mentions_sha256,
        ),
        "prediction_manifest": (
            inputs.prediction_manifest_path,
            inputs.prediction_manifest_sha256,
        ),
        "prediction_mentions": (
            inputs.prediction_mentions_path,
            inputs.prediction_mentions_sha256,
        ),
        "prediction_quality": (
            inputs.prediction_quality_path,
            inputs.prediction_quality_sha256,
        ),
        "baseline_manifest": (
            inputs.baseline_evaluation_manifest_path,
            inputs.baseline_evaluation_manifest_sha256,
        ),
        "baseline_metrics": (
            inputs.baseline_metrics_path,
            inputs.baseline_metrics_sha256,
        ),
    }
    for name, (path_value, expected_sha) in declared.items():
        path = _resolve_project_path(path_value)
        exists = path.is_file()
        _add(checks, f"input_{name}_exists", exists, _normalize_path(path))
        _add(
            checks,
            f"input_{name}_sha256_matches",
            exists and _sha256_file(path) == expected_sha,
            expected_sha,
        )
    _add(
        checks,
        "current_canonical_input_forbidden",
        _resolve_project_path(inputs.documents_path)
        != CURRENT_CANONICAL_PATH.resolve(),
    )


def _recompute_and_compare(
    *,
    calibration_dir: Path,
    config_path: Path,
    manifest: ScientificEntityGLiNERCalibrationManifest,
) -> tuple[bool, str | None]:
    inputs = manifest.inputs
    try:
        with tempfile.TemporaryDirectory(
            prefix="scientific-entity-gliner-calibration-validation-"
        ) as temporary_root:
            report = calibrate_gliner_predictions(
                config_path=config_path,
                documents_path=Path(inputs.documents_path),
                review_manifest_path=Path(inputs.review_manifest_path),
                reference_mentions_path=Path(inputs.reference_mentions_path),
                prediction_build_dir=Path(inputs.prediction_manifest_path).parent,
                baseline_evaluation_dir=Path(
                    inputs.baseline_evaluation_manifest_path
                ).parent,
                output_root=Path(temporary_root),
                calibration_id=manifest.calibration_id,
                status=manifest.status,
                max_documents=inputs.document_count,
                execute=True,
                generated_at_utc=manifest.generated_at_utc,
            )
            rebuilt_dir = Path(report["output_dir"])
            mismatches = [
                filename
                for filename in REQUIRED_FILES
                if (calibration_dir / filename).read_bytes()
                != (rebuilt_dir / filename).read_bytes()
            ]
            if mismatches:
                return False, f"deterministic byte mismatch: {mismatches}"
    except Exception as exc:  # fail closed on any recomputation issue
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def validate_gliner_calibration(
    *,
    calibration_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    calibration_dir = calibration_dir.resolve()
    config_path = config_path.resolve()
    config = load_gliner_calibration_config(config_path)
    selected_report_dir = report_dir or _resolve_project_path(
        config.validation.report_dir
    )
    checks: list[CheckResult] = []
    manifest: ScientificEntityGLiNERCalibrationManifest | None = None

    _add(
        checks,
        "calibration_directory_exists",
        calibration_dir.is_dir(),
        _normalize_path(calibration_dir),
    )
    if not calibration_dir.is_dir():
        report = _build_report(
            calibration_dir=calibration_dir,
            config_path=config_path,
            checks=checks,
            manifest=None,
        )
        if write_reports:
            _write_reports(report, selected_report_dir)
        return report

    actual_files = {path.name for path in calibration_dir.iterdir() if path.is_file()}
    actual_dirs = {path.name for path in calibration_dir.iterdir() if path.is_dir()}
    _add(checks, "required_files_exact", actual_files == set(REQUIRED_FILES))
    _add(checks, "nested_directories_absent", not actual_dirs)
    if actual_files != set(REQUIRED_FILES):
        report = _build_report(
            calibration_dir=calibration_dir,
            config_path=config_path,
            checks=checks,
            manifest=None,
        )
        if write_reports:
            _write_reports(report, selected_report_dir)
        return report

    for filename in REQUIRED_FILES:
        ok, details = _text_is_utf8_lf(calibration_dir / filename)
        _add(checks, f"utf8_lf::{filename}", ok, details)

    try:
        checksum_rows = _parse_checksums(calibration_dir / "checksums.txt")
        _add(
            checks,
            "checksum_file_set_exact",
            set(checksum_rows) == set(CHECKSUM_FILES),
        )
        for filename in CHECKSUM_FILES:
            _add(
                checks,
                f"checksum_matches::{filename}",
                checksum_rows.get(filename) == _sha256_file(
                    calibration_dir / filename
                ),
            )

        manifest = ScientificEntityGLiNERCalibrationManifest.model_validate(
            _read_json(calibration_dir / "manifest.json")
        )
        trials = [
            ScientificEntityCalibrationTrial.model_validate(row)
            for row in _read_jsonl(calibration_dir / "trials.jsonl")
        ]
        pareto = ScientificEntityCalibrationParetoFrontier.model_validate(
            _read_json(calibration_dir / "pareto_frontier.json")
        )
        profiles = ScientificEntityCalibrationProfiles.model_validate(
            _read_json(calibration_dir / "recommended_profiles.json")
        )
        diagnostics = ScientificEntityCalibrationDiagnostics.model_validate(
            _read_json(calibration_dir / "diagnostics.json")
        )
        _add(checks, "output_contracts_parse", True)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        _add(checks, "output_contracts_parse", False, f"{type(exc).__name__}: {exc}")
        report = _build_report(
            calibration_dir=calibration_dir,
            config_path=config_path,
            checks=checks,
            manifest=manifest,
        )
        if write_reports:
            _write_reports(report, selected_report_dir)
        return report

    _add(
        checks,
        "config_sha256_matches",
        manifest.config_sha256 == gliner_calibration_config_sha256(config),
    )
    _add(
        checks,
        "config_path_matches",
        _resolve_project_path(manifest.config_path) == config_path,
    )
    _add(
        checks,
        "calibration_directory_matches_calibration_id",
        calibration_dir.name == manifest.calibration_id,
    )
    _add(
        checks,
        "manifest_trials_sha256_matches",
        manifest.trials_sha256 == _sha256_file(calibration_dir / manifest.trials_file),
    )
    _add(
        checks,
        "manifest_pareto_sha256_matches",
        manifest.pareto_sha256 == _sha256_file(calibration_dir / manifest.pareto_file),
    )
    _add(
        checks,
        "manifest_profiles_sha256_matches",
        manifest.profiles_sha256
        == _sha256_file(calibration_dir / manifest.profiles_file),
    )
    _add(
        checks,
        "manifest_diagnostics_sha256_matches",
        manifest.diagnostics_sha256
        == _sha256_file(calibration_dir / manifest.diagnostics_file),
    )

    trial_ids = {row.trial_id for row in trials}
    trial_by_id = {row.trial_id: row for row in trials}
    stage_counts = {
        stage: sum(row.stage == stage for row in trials)
        for stage in ScientificEntityCalibrationTrialStage
    }
    expected_stage_counts = {
        ScientificEntityCalibrationTrialStage.BASELINE: 1,
        ScientificEntityCalibrationTrialStage.GLOBAL: len(
            config.search.global_thresholds
        ),
        ScientificEntityCalibrationTrialStage.SOURCE_PAIR: (
            len(config.search.title_thresholds)
            * len(config.search.abstract_thresholds)
        ),
        ScientificEntityCalibrationTrialStage.TYPE_PROBE: (
            len(ScientificEntityType) * len(config.search.type_probe_thresholds)
        ),
    }
    _add(
        checks,
        "trial_count_matches_config",
        len(trials) == config.search.declared_trial_count,
    )
    _add(checks, "trial_ids_unique", len(trial_ids) == len(trials))
    _add(
        checks,
        "trial_stage_counts_match_config",
        stage_counts == expected_stage_counts,
    )
    _add(
        checks,
        "manifest_trial_count_matches",
        manifest.search_space_trial_count == len(trials),
    )
    _add(
        checks,
        "manifest_eligible_count_matches",
        manifest.eligible_trial_count
        == sum(row.eligible_for_profile_selection for row in trials),
    )
    _add(
        checks,
        "calibration_ids_match",
        all(row.calibration_id == manifest.calibration_id for row in trials)
        and pareto.calibration_id == manifest.calibration_id
        and profiles.calibration_id == manifest.calibration_id
        and diagnostics.calibration_id == manifest.calibration_id,
    )
    _add(
        checks,
        "profile_trials_exist_and_are_eligible",
        all(
            row.trial_id in trial_by_id
            and trial_by_id[row.trial_id].eligible_for_profile_selection
            for row in profiles.selections
        ),
    )
    _add(
        checks,
        "pareto_trials_exist_and_are_eligible",
        all(
            trial_id in trial_by_id
            and trial_by_id[trial_id].eligible_for_profile_selection
            and trial_by_id[trial_id].stage
            != ScientificEntityCalibrationTrialStage.TYPE_PROBE
            for trial_id in pareto.trial_ids
        ),
    )
    _add(
        checks,
        "type_probes_are_diagnostic_only",
        all(
            row.stage != ScientificEntityCalibrationTrialStage.TYPE_PROBE
            or not row.eligible_for_profile_selection
            for row in trials
        )
        and diagnostics.combined_type_specific_policy_selected is False,
    )
    _add(
        checks,
        "diagnostic_trials_exist",
        diagnostics.source_pair_base_trial_id in trial_by_id
        and all(
            row.best_trial_id in trial_by_id
            for row in diagnostics.type_probe_rows
        ),
    )

    _input_hash_checks(checks, manifest)
    recomputed, recompute_details = _recompute_and_compare(
        calibration_dir=calibration_dir,
        config_path=config_path,
        manifest=manifest,
    )
    _add(
        checks,
        "deterministic_recomputation_matches_all_outputs",
        recomputed,
        recompute_details,
    )

    report = _build_report(
        calibration_dir=calibration_dir,
        config_path=config_path,
        checks=checks,
        manifest=manifest,
    )
    if write_reports:
        _write_reports(report, selected_report_dir)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an immutable Scientific Entity GLiNER Dev Calibration v0.1 "
            "directory and independently rebuild its deterministic outputs."
        )
    )
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_gliner_calibration(
            calibration_dir=args.calibration_dir,
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
    print(f"[{prefix}] calibration_id={summary['calibration_id']}")
    print(f"[{prefix}] document_count={summary['document_count']}")
    print(f"[{prefix}] trial_count={summary['trial_count']}")
    print(f"[{prefix}] next_slice={report['verdict']['next_slice']}")
    if not report["summary"]["ok"]:
        print(f"[{prefix}] required_failed_checks:")
        for name in report["verdict"]["required_failed_checks"]:
            print(f"- {name}")
    if args.strict and not report["summary"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
