from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from radar_core.utils.ids import stable_hash
from scripts.validation.check_field_level_canonical_provenance_contract import (
    FIELD_STRATEGIES,
)


REPORT_NAME = "field_level_canonical_provenance_evidence_check_v01"
SCHEMA_VERSION = "field_level_canonical_provenance_evidence_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "artifacts"
    / "audit"
    / "field_level_canonical_provenance_evidence_v0.1"
)
DEFAULT_LATEST_PATH = DEFAULT_OUTPUT_ROOT / "latest.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"
RUNTIME_DEFAULT_FIELDS = {"created_at", "updated_record_at"}
REQUIRED_FILES = (
    "field_evidence.jsonl",
    "paper_summary.jsonl",
    "data_quality_summary.json",
    "manifest.json",
    "README.md",
    "checksums.txt",
)


class EvidenceValidationError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidenceValidationError(f"Expected JSON object: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise EvidenceValidationError(
                    f"Expected JSON object in {path}:{line_no}"
                )
            rows.append(payload)
    return rows


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]
    lines = [
        "# Field-Level Canonical Provenance Evidence Check v0.1",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Package: `{report['input']['package_root']}`",
        f"- OK: `{verdict['ok']}`",
        "",
        "## Summary",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Required failures"])
    failures = verdict["required_failed_checks"]
    if failures:
        lines.extend(f"- `{name}`" for name in failures)
    else:
        lines.append("- none")
    lines.extend(["", "## Samples"])
    samples = report.get("samples") or {}
    if not samples:
        lines.append("- none")
    else:
        for key, values in samples.items():
            lines.append(f"### {key}")
            for value in values:
                lines.append(f"- `{json.dumps(value, ensure_ascii=False, sort_keys=True)}`")
    return "\n".join(lines) + "\n"


def _resolve_from_latest(latest_path: Path) -> Path:
    payload = load_json(latest_path)
    raw = payload.get("run_dir")
    if not raw:
        raise EvidenceValidationError(f"latest.json has no run_dir: {latest_path}")
    return Path(str(raw))


def resolve_package_root(
    package_path: Path | None,
    latest_path: Path,
) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    path = package_path if package_path is not None else _resolve_from_latest(latest_path)
    path = path.resolve()
    temp: tempfile.TemporaryDirectory[str] | None = None
    if path.is_file() and path.suffix.lower() == ".zip":
        temp = tempfile.TemporaryDirectory(prefix="ml_radar_field_provenance_check_")
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise EvidenceValidationError(f"ZIP integrity failure: {bad}")
            archive.extractall(temp.name)
        path = Path(temp.name)
    if not path.is_dir():
        raise FileNotFoundError(path)
    if (path / "manifest.json").is_file():
        root = path
    else:
        roots = [
            child
            for child in path.iterdir()
            if child.is_dir() and (child / "manifest.json").is_file()
        ]
        if len(roots) != 1:
            raise EvidenceValidationError(
                f"Could not resolve one package directory beneath: {path}"
            )
        root = roots[0]
    return root, temp


def parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = raw.strip()
        if not text:
            continue
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            raise EvidenceValidationError(f"Invalid checksum line {path}:{line_no}")
        digest, filename = parts
        result[filename.strip()] = digest.strip()
    return result


def _sample_append(
    samples: dict[str, list[dict[str, Any]]],
    key: str,
    payload: dict[str, Any],
    sample_limit: int,
) -> None:
    if len(samples[key]) < sample_limit:
        samples[key].append(payload)


def build_report(
    *,
    package_root: Path,
    sample_limit: int = 20,
) -> dict[str, Any]:
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    missing_files = [name for name in REQUIRED_FILES if not (package_root / name).is_file()]
    if missing_files:
        return {
            "report_name": REPORT_NAME,
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": utc_now_iso(),
            "input": {"package_root": normalize_path(package_root)},
            "summary": {
                "required_file_count": len(REQUIRED_FILES),
                "missing_file_count": len(missing_files),
                "field_record_count": 0,
                "paper_count": 0,
                "required_failed_count": len(missing_files),
            },
            "checks": {f"required_file:{name}": name not in missing_files for name in REQUIRED_FILES},
            "samples": {"missing_files": [{"path": name} for name in missing_files]},
            "verdict": {
                "ok": False,
                "required_failed_count": len(missing_files),
                "required_failed_checks": [f"required_file:{name}" for name in missing_files],
            },
        }

    manifest = load_json(package_root / "manifest.json")
    quality = load_json(package_root / "data_quality_summary.json")
    records = load_jsonl(package_root / "field_evidence.jsonl")
    papers = load_jsonl(package_root / "paper_summary.jsonl")
    checksums = parse_checksums(package_root / "checksums.txt")

    paper_by_id: dict[str, dict[str, Any]] = {}
    duplicate_papers = 0
    for row in papers:
        canonical_id = str(row.get("canonical_id") or "")
        if canonical_id in paper_by_id:
            duplicate_papers += 1
            _sample_append(samples, "duplicate_papers", {"canonical_id": canonical_id}, sample_limit)
        paper_by_id[canonical_id] = row

    record_ids: set[str] = set()
    record_keys: set[tuple[str, str]] = set()
    fields_by_paper: dict[str, set[str]] = defaultdict(set)
    duplicate_record_ids = 0
    duplicate_record_keys = 0
    unknown_paper_count = 0
    invalid_record_id_count = 0
    invalid_strategy_count = 0
    foreign_observation_id_count = 0
    invalid_runtime_default_count = 0
    selected_not_field_contributing_count = 0
    candidate_count_mismatch_count = 0
    mismatch_count = 0
    schema_mismatch_count = 0

    for row in records:
        canonical_id = str(row.get("canonical_id") or "")
        field_name = str(row.get("field_name") or "")
        record_id = str(row.get("record_id") or "")
        strategy = str(row.get("strategy_kind") or "")
        key = (canonical_id, field_name)

        if row.get("schema_version") != SCHEMA_VERSION:
            schema_mismatch_count += 1
            _sample_append(samples, "schema_mismatches", {"key": key}, sample_limit)
        if record_id in record_ids:
            duplicate_record_ids += 1
            _sample_append(samples, "duplicate_record_ids", {"record_id": record_id}, sample_limit)
        record_ids.add(record_id)
        if key in record_keys:
            duplicate_record_keys += 1
            _sample_append(samples, "duplicate_record_keys", {"key": key}, sample_limit)
        record_keys.add(key)
        fields_by_paper[canonical_id].add(field_name)

        expected_record_id = stable_hash(
            json.dumps(
                [SCHEMA_VERSION, canonical_id, field_name],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            length=32,
        )
        if record_id != expected_record_id:
            invalid_record_id_count += 1
            _sample_append(
                samples,
                "invalid_record_ids",
                {"key": key, "actual": record_id, "expected": expected_record_id},
                sample_limit,
            )
        expected_strategy = FIELD_STRATEGIES.get(field_name)
        if expected_strategy is None or strategy != expected_strategy:
            invalid_strategy_count += 1
            _sample_append(
                samples,
                "invalid_strategies",
                {"key": key, "actual": strategy, "expected": expected_strategy},
                sample_limit,
            )

        paper = paper_by_id.get(canonical_id)
        if paper is None:
            unknown_paper_count += 1
            allowed_ids: set[str] = set()
            _sample_append(samples, "unknown_papers", {"canonical_id": canonical_id}, sample_limit)
        else:
            allowed_ids = {
                str(value)
                for value in paper.get("contributing_source_observation_ids", [])
            }
        evidence_ids = {
            str(value)
            for field in (
                "selected_source_observation_ids",
                "contributing_source_observation_ids",
            )
            for value in row.get(field, [])
        }
        for candidate in row.get("candidates", []):
            if isinstance(candidate, dict) and candidate.get("source_observation_id"):
                evidence_ids.add(str(candidate["source_observation_id"]))
        for element in row.get("elements", []):
            if not isinstance(element, dict):
                continue
            if element.get("first_source_observation_id"):
                evidence_ids.add(str(element["first_source_observation_id"]))
            evidence_ids.update(
                str(value)
                for value in element.get("contributing_source_observation_ids", [])
            )

        selected_ids = {str(value) for value in row.get("selected_source_observation_ids", [])}
        field_contributing_ids = {
            str(value) for value in row.get("contributing_source_observation_ids", [])
        }
        if not selected_ids <= field_contributing_ids:
            selected_not_field_contributing_count += 1
            _sample_append(
                samples,
                "selected_not_field_contributing",
                {"key": key, "ids": sorted(selected_ids - field_contributing_ids)},
                sample_limit,
            )
        physical_candidate_count = sum(
            bool(candidate.get("eligible"))
            for candidate in row.get("candidates", [])
            if isinstance(candidate, dict)
        )
        if int(row.get("candidate_count") or 0) != physical_candidate_count:
            candidate_count_mismatch_count += 1
            _sample_append(
                samples,
                "candidate_count_mismatches",
                {
                    "key": key,
                    "declared": row.get("candidate_count"),
                    "physical": physical_candidate_count,
                },
                sample_limit,
            )

        foreign_ids = sorted(evidence_ids - allowed_ids)
        if foreign_ids:
            foreign_observation_id_count += len(foreign_ids)
            _sample_append(
                samples,
                "foreign_observation_ids",
                {"key": key, "ids": foreign_ids},
                sample_limit,
            )

        if field_name in RUNTIME_DEFAULT_FIELDS:
            valid_runtime = (
                row.get("comparison_status") == "not_applicable"
                and row.get("reconstructability") == "not_source_reconstructable"
                and not row.get("selected_source_observation_ids")
                and not row.get("contributing_source_observation_ids")
                and not row.get("candidates")
            )
            if not valid_runtime:
                invalid_runtime_default_count += 1
                _sample_append(samples, "invalid_runtime_defaults", {"key": key}, sample_limit)
        elif row.get("comparison_status") != "match" or (
            row.get("canonical_value") != row.get("recomputed_value")
        ):
            mismatch_count += 1
            _sample_append(
                samples,
                "value_mismatches",
                {
                    "key": key,
                    "canonical_value": row.get("canonical_value"),
                    "recomputed_value": row.get("recomputed_value"),
                    "comparison_status": row.get("comparison_status"),
                },
                sample_limit,
            )

    expected_fields = set(FIELD_STRATEGIES)
    paper_field_coverage_failures = 0
    for canonical_id in paper_by_id:
        actual = fields_by_paper.get(canonical_id, set())
        if actual != expected_fields:
            paper_field_coverage_failures += 1
            _sample_append(
                samples,
                "field_coverage_failures",
                {
                    "canonical_id": canonical_id,
                    "missing": sorted(expected_fields - actual),
                    "unexpected": sorted(actual - expected_fields),
                },
                sample_limit,
            )

    checksum_missing_count = 0
    checksum_mismatch_count = 0
    for filename in REQUIRED_FILES:
        if filename == "checksums.txt":
            continue
        expected = checksums.get(filename)
        if expected is None:
            checksum_missing_count += 1
            _sample_append(samples, "missing_checksums", {"filename": filename}, sample_limit)
            continue
        actual = sha256_file(package_root / filename)
        if expected != actual:
            checksum_mismatch_count += 1
            _sample_append(
                samples,
                "checksum_mismatches",
                {"filename": filename, "expected": expected, "actual": actual},
                sample_limit,
            )

    manifest_counts = manifest.get("counts") or {}
    count_checks = {
        "manifest_paper_count_matches": manifest_counts.get("canonical_paper_count") == len(papers),
        "manifest_field_record_count_matches": manifest_counts.get("field_evidence_record_count") == len(records),
        "manifest_field_count_matches_contract": manifest_counts.get("canonical_field_count") == len(FIELD_STRATEGIES),
        "manifest_mismatch_count_matches": manifest_counts.get("comparison_mismatch_count") == mismatch_count,
        "quality_field_record_count_matches": quality.get("field_evidence_record_count") == len(records),
        "quality_paper_count_matches": quality.get("canonical_paper_count") == len(papers),
    }

    checks: dict[str, bool] = {
        **{f"required_file:{name}": True for name in REQUIRED_FILES},
        "manifest_schema_version_exact": manifest.get("schema_version") == SCHEMA_VERSION,
        "manifest_canonical_truth_false": manifest.get("canonical_truth") is False,
        "manifest_not_reconcile_input": manifest.get("may_be_used_as_reconcile_input") is False,
        "manifest_publication_ready_false": manifest.get("publication_ready") is False,
        "manifest_safety_no_mutations": all(
            value is False for value in (manifest.get("safety") or {}).values()
        ),
        "paper_rows_non_empty": bool(papers),
        "field_records_non_empty": bool(records),
        "no_duplicate_papers": duplicate_papers == 0,
        "no_duplicate_record_ids": duplicate_record_ids == 0,
        "no_duplicate_record_keys": duplicate_record_keys == 0,
        "all_record_schema_versions_exact": schema_mismatch_count == 0,
        "all_record_ids_deterministic": invalid_record_id_count == 0,
        "all_field_strategies_match_contract": invalid_strategy_count == 0,
        "all_records_reference_known_papers": unknown_paper_count == 0,
        "all_observation_ids_are_contributing": foreign_observation_id_count == 0,
        "selected_ids_are_field_contributing": selected_not_field_contributing_count == 0,
        "candidate_counts_match_physical_candidates": candidate_count_mismatch_count == 0,
        "all_papers_cover_all_contract_fields": paper_field_coverage_failures == 0,
        "runtime_default_semantics_valid": invalid_runtime_default_count == 0,
        "all_source_reconstructable_values_match": mismatch_count == 0,
        "all_required_checksums_present": checksum_missing_count == 0,
        "all_checksums_match": checksum_mismatch_count == 0,
        **count_checks,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": "read_only_package_validation",
        "input": {"package_root": normalize_path(package_root)},
        "summary": {
            "checks_count": len(checks),
            "passed_checks_count": len(checks) - len(failed),
            "required_failed_count": len(failed),
            "paper_count": len(papers),
            "canonical_field_count": len(FIELD_STRATEGIES),
            "field_record_count": len(records),
            "duplicate_record_id_count": duplicate_record_ids,
            "duplicate_record_key_count": duplicate_record_keys,
            "foreign_observation_id_count": foreign_observation_id_count,
            "selected_not_field_contributing_count": selected_not_field_contributing_count,
            "candidate_count_mismatch_count": candidate_count_mismatch_count,
            "field_coverage_failure_count": paper_field_coverage_failures,
            "value_mismatch_count": mismatch_count,
            "checksum_mismatch_count": checksum_mismatch_count,
        },
        "checks": checks,
        "samples": dict(samples),
        "verdict": {
            "ok": not failed,
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "canonical_truth_mutated": False,
            "postgres_mutated": False,
            "provider_api_called": False,
            "evidence_package_valid": not failed,
        },
    }


def validate_package(
    *,
    package_path: Path | None = None,
    latest_path: Path = DEFAULT_LATEST_PATH,
    output_dir: Path = DEFAULT_REPORT_DIR,
    strict: bool = False,
    sample_limit: int = 20,
    write_reports: bool = True,
) -> dict[str, Any]:
    root, temp = resolve_package_root(package_path, latest_path)
    try:
        report = build_report(package_root=root, sample_limit=sample_limit)
    finally:
        if temp is not None:
            temp.cleanup()

    if write_reports:
        output_dir.mkdir(parents=True, exist_ok=True)
        latest_json = output_dir / "field_level_canonical_provenance_evidence_v01_latest.json"
        latest_md = output_dir / "field_level_canonical_provenance_evidence_v01_latest.md"
        history_dir = output_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = ts_slug()
        history_json = history_dir / f"field_level_canonical_provenance_evidence_v01_{stamp}.json"
        history_md = history_dir / f"field_level_canonical_provenance_evidence_v01_{stamp}.md"
        write_json(latest_json, report)
        write_json(history_json, report)
        markdown = build_markdown(report)
        latest_md.write_text(markdown, encoding="utf-8", newline="\n")
        history_md.write_text(markdown, encoding="utf-8", newline="\n")
        report["report_paths"] = {
            "latest_json": normalize_path(latest_json),
            "latest_md": normalize_path(latest_md),
            "history_json": normalize_path(history_json),
            "history_md": normalize_path(history_md),
        }

    if strict and not report["verdict"]["ok"]:
        raise EvidenceValidationError(
            "Field-level canonical provenance evidence validation failed: "
            + ", ".join(report["verdict"]["required_failed_checks"])
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate field-level canonical provenance evidence package."
    )
    parser.add_argument("--package-path", type=Path, default=None)
    parser.add_argument("--latest-path", type=Path, default=DEFAULT_LATEST_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_package(
            package_path=args.package_path,
            latest_path=args.latest_path,
            output_dir=args.output_dir,
            strict=args.strict,
            sample_limit=args.sample_limit,
        )
    except EvidenceValidationError as exc:
        print(f"[FAIL] {exc}")
        return 1

    summary = report["summary"]
    verdict = report["verdict"]
    print(f"[{'OK' if verdict['ok'] else 'FAIL'}] report_name={REPORT_NAME}")
    print(f"[{'OK' if verdict['ok'] else 'FAIL'}] checks_count={summary['checks_count']}")
    print(f"[{'OK' if verdict['ok'] else 'FAIL'}] passed_checks_count={summary['passed_checks_count']}")
    print(f"[{'OK' if verdict['ok'] else 'FAIL'}] paper_count={summary['paper_count']}")
    print(f"[{'OK' if verdict['ok'] else 'FAIL'}] field_record_count={summary['field_record_count']}")
    print(f"[{'OK' if verdict['ok'] else 'FAIL'}] value_mismatch_count={summary['value_mismatch_count']}")
    print(f"[{'OK' if verdict['ok'] else 'FAIL'}] required_failed_count={summary['required_failed_count']}")
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
