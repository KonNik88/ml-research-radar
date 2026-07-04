"""Validate the local Citation / Reference Graph package output.

This validator checks package-level integrity after
scripts.export.package_citation_reference_graph has created the local package.
It is a read-only validation/report layer over package files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "citation_reference_graph_package_validation_v1"
MANIFEST_SCHEMA_VERSION = "citation_reference_graph_package_manifest_v1"
DEFAULT_CONFIG_PATH = Path("configs/citation_reference_graph_package.yaml")
DEFAULT_REPORT_DIR = Path("artifacts/reports/validation")


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool
    message: str
    details: dict[str, Any] | None = None

    @property
    def status(self) -> str:
        if self.ok:
            return "passed"
        if self.required:
            return "failed"
        return "warning"


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def resolve_path(raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def parse_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if is_sha256(parts[0]):
            checksums[parts[1].lstrip("*").replace("\\", "/")] = parts[0].lower()
        elif is_sha256(parts[-1]):
            checksums[parts[0].lstrip("*").replace("\\", "/")] = parts[-1].lower()
    return checksums


def make_check(name: str, ok: bool, required: bool, message: str, details: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(name=name, ok=bool(ok), required=required, message=message, details=details)


def expected_paths_from_config(config: dict[str, Any], package_dir_override: Path | None = None) -> dict[str, Path]:
    outputs = config.get("outputs", {})
    if package_dir_override is None:
        return {
            "package_dir": resolve_path(outputs["package_dir"]),
            "zip_path": resolve_path(outputs["zip_path"]),
            "manifest_path": resolve_path(outputs["manifest_path"]),
            "readme_path": resolve_path(outputs["readme_path"]),
            "checksums_path": resolve_path(outputs["checksums_path"]),
        }

    package_dir = package_dir_override
    return {
        "package_dir": package_dir,
        "zip_path": package_dir / Path(str(outputs["zip_path"])).name,
        "manifest_path": package_dir / Path(str(outputs["manifest_path"])).name,
        "readme_path": package_dir / Path(str(outputs["readme_path"])).name,
        "checksums_path": package_dir / Path(str(outputs["checksums_path"])).name,
    }


def expected_graph_counts_from_config(config: dict[str, Any]) -> dict[str, int]:
    return {str(key): int(value) for key, value in (config.get("expected_counts") or {}).items()}


def actual_graph_counts_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    counts = manifest.get("graph", {}).get("counts", {})
    return {
        "nodes_count": counts.get("nodes_count"),
        "edges_count": counts.get("edges_count"),
        "node_paper_count": counts.get("paper_nodes_count"),
        "node_external_reference_count": counts.get("external_reference_nodes_count"),
        "node_source_family_count": counts.get("source_family_nodes_count"),
        "edge_paper_references_paper_count": counts.get("paper_references_paper_edges_count"),
        "edge_paper_references_external_count": counts.get("paper_references_external_edges_count"),
        "edge_paper_has_reference_source_family_count": counts.get("paper_has_reference_source_family_edges_count"),
    }


def validate_package(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    package_dir: Path | None = None,
    report_dir: Path | None = None,
    strict: bool = False,
    write_reports: bool = True,
) -> dict[str, Any]:
    config = load_yaml(config_path)
    paths = expected_paths_from_config(config, package_dir)
    report_dir = report_dir or resolve_path((config.get("validation") or {}).get("report_dir", DEFAULT_REPORT_DIR))

    checks: list[CheckResult] = []

    required_files = [paths["zip_path"], paths["manifest_path"], paths["readme_path"], paths["checksums_path"]]
    missing_files = [normalize_path(path) for path in required_files if not path.exists()]
    checks.append(
        make_check(
            "package_files_exist",
            not missing_files,
            True,
            "Required package files are present" if not missing_files else "Required package files are missing",
            {"missing_files": missing_files},
        )
    )

    manifest: dict[str, Any] = {}
    if not missing_files:
        try:
            manifest = load_json(paths["manifest_path"])
            checks.append(make_check("package_manifest_readable", True, True, "Package manifest is readable"))
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("package_manifest_readable", False, True, f"Package manifest is not readable: {exc}"))

    if manifest:
        checks.append(
            make_check(
                "package_manifest_schema",
                manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION,
                True,
                "Package manifest schema is correct"
                if manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION
                else "Package manifest schema is incorrect",
                {"schema_version": manifest.get("schema_version")},
            )
        )

        package = manifest.get("package") if isinstance(manifest.get("package"), dict) else {}
        package_flags = {
            "publication_ready": package.get("publication_ready"),
            "manual_review_required": package.get("manual_review_required"),
            "may_be_used_as_reconcile_input": package.get("may_be_used_as_reconcile_input"),
        }
        package_flags_ok = (
            package_flags["publication_ready"] is False
            and package_flags["manual_review_required"] is True
            and package_flags["may_be_used_as_reconcile_input"] is False
        )
        checks.append(
            make_check(
                "package_safety_flags",
                package_flags_ok,
                True,
                "Package safety flags preserve candidate boundaries"
                if package_flags_ok
                else "Package safety flags do not preserve candidate boundaries",
                package_flags,
            )
        )

        boundaries = manifest.get("boundaries") if isinstance(manifest.get("boundaries"), dict) else {}
        boundary_expected = {
            "local_package_candidate": True,
            "generated_output": True,
            "read_only_graph_input": True,
            "rebuilds_graph": False,
            "mutates_canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "changes_postgres": False,
            "changes_db_schema": False,
            "changes_qdrant": False,
            "changes_retrieval": False,
            "changes_ranking": False,
            "changes_api": False,
            "changes_ui": False,
            "parses_full_text": False,
            "parses_pdfs": False,
            "parses_bibliography_sections": False,
            "requires_networkx_runtime": False,
            "requires_neo4j_runtime": False,
            "requires_graphrag_runtime": False,
            "publishes_graph": False,
            "publishes_dataset": False,
        }
        boundary_mismatches = {
            key: {"expected": expected, "actual": boundaries.get(key)}
            for key, expected in boundary_expected.items()
            if boundaries.get(key) is not expected
        }
        checks.append(
            make_check(
                "package_boundaries",
                not boundary_mismatches,
                True,
                "Package boundaries preserve project invariants"
                if not boundary_mismatches
                else "Package boundaries do not preserve project invariants",
                {"mismatches": boundary_mismatches},
            )
        )

        release = manifest.get("release_candidate") if isinstance(manifest.get("release_candidate"), dict) else {}
        release_ok = (
            release.get("summary_ok") is True
            and release.get("required_failed_count") == 0
            and release.get("technical_graph_candidate_ready") is True
            and release.get("manual_review_required") is True
            and release.get("manual_review_complete") is False
            and release.get("publication_ready") is False
        )
        checks.append(
            make_check(
                "release_candidate_green",
                release_ok,
                True,
                "Embedded release-candidate summary is green"
                if release_ok
                else "Embedded release-candidate summary is not green",
                release,
            )
        )

        expected_counts = expected_graph_counts_from_config(config)
        actual_counts = actual_graph_counts_from_manifest(manifest)
        count_mismatches = {
            key: {"expected": expected, "actual": actual_counts.get(key)}
            for key, expected in expected_counts.items()
            if actual_counts.get(key) != expected
        }
        checks.append(
            make_check(
                "accepted_graph_counts",
                not count_mismatches,
                True,
                "Packaged graph counters match accepted v0.1 baseline"
                if not count_mismatches
                else "Packaged graph counters differ from accepted v0.1 baseline",
                {"mismatches": count_mismatches, "actual_counts": actual_counts},
            )
        )

    if not missing_files:
        try:
            expected_checksums = parse_checksums(paths["checksums_path"])
            checksum_mismatches = {}
            for path in [paths["zip_path"], paths["manifest_path"], paths["readme_path"]]:
                expected_checksum = expected_checksums.get(path.name)
                actual_checksum = sha256_file(path)
                if expected_checksum != actual_checksum:
                    checksum_mismatches[path.name] = {
                        "expected": expected_checksum,
                        "actual": actual_checksum,
                    }
            checks.append(
                make_check(
                    "package_checksums_match",
                    not checksum_mismatches,
                    True,
                    "Package checksums match" if not checksum_mismatches else "Package checksum mismatches found",
                    {"mismatches": checksum_mismatches},
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("package_checksums_match", False, True, f"Failed to validate package checksums: {exc}"))

    if manifest and paths["zip_path"].exists():
        try:
            with zipfile.ZipFile(paths["zip_path"], mode="r") as archive:
                zip_names = set(archive.namelist())
                test_result = archive.testzip()

            included_files = manifest.get("included_files") if isinstance(manifest.get("included_files"), list) else []
            expected_archive_paths = {item.get("archive_path") for item in included_files if isinstance(item, dict)}
            missing_archive_paths = sorted(str(path) for path in expected_archive_paths if path not in zip_names)
            checks.append(
                make_check(
                    "zip_readable",
                    test_result is None,
                    True,
                    "Zip archive is readable" if test_result is None else "Zip archive has a corrupt member",
                    {"bad_member": test_result},
                )
            )
            checks.append(
                make_check(
                    "zip_contains_manifest_included_files",
                    not missing_archive_paths,
                    True,
                    "Zip contains all manifest-listed included files"
                    if not missing_archive_paths
                    else "Zip is missing manifest-listed included files",
                    {"missing_archive_paths": missing_archive_paths},
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("zip_readable", False, True, f"Failed to inspect zip archive: {exc}"))

    required_failed = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    ok = not required_failed

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": normalize_path(config_path),
        "package_dir": normalize_path(paths["package_dir"]),
        "summary": {
            "ok": ok,
            "strict": strict,
            "required_failed_count": len(required_failed),
            "warning_count": len(warnings),
            "total_checks": len(checks),
        },
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "ok": check.ok,
                "required": check.required,
                "message": check.message,
                "details": check.details or {},
            }
            for check in checks
        ],
        "verdict": {
            "package_candidate_ready": ok,
            "manual_review_required": True,
            "manual_review_complete": False,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "required_failed_checks": [check.name for check in required_failed],
            "warning_checks": [check.name for check in warnings],
        },
        "boundaries": {
            "read_only_validator": True,
            "rebuilds_graph": False,
            "mutates_canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "changes_postgres": False,
            "changes_db_schema": False,
            "changes_qdrant": False,
            "changes_retrieval": False,
            "changes_ranking": False,
            "changes_api": False,
            "changes_ui": False,
            "parses_full_text": False,
            "parses_pdfs": False,
            "parses_bibliography_sections": False,
            "requires_networkx_runtime": False,
            "requires_neo4j_runtime": False,
            "requires_graphrag_runtime": False,
            "publishes_graph": False,
            "publishes_dataset": False,
        },
    }

    if write_reports:
        write_validation_reports(result, report_dir)

    return result


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    verdict = result["verdict"]

    lines = [
        "# Citation / Reference Graph Package Check",
        "",
        f"- schema_version: `{result['schema_version']}`",
        f"- generated_at: `{result['generated_at']}`",
        f"- config_path: `{result['config_path']}`",
        f"- package_dir: `{result['package_dir']}`",
        f"- ok: `{summary['ok']}`",
        f"- strict: `{summary['strict']}`",
        f"- required_failed_count: `{summary['required_failed_count']}`",
        f"- warning_count: `{summary['warning_count']}`",
        "",
        "## Verdict",
        "",
        f"- package_candidate_ready: `{verdict['package_candidate_ready']}`",
        f"- manual_review_required: `{verdict['manual_review_required']}`",
        f"- manual_review_complete: `{verdict['manual_review_complete']}`",
        f"- publication_ready: `{verdict['publication_ready']}`",
        f"- publication_block_reason: `{verdict['publication_block_reason']}`",
        "",
        "## Checks",
        "",
        "| Check | Required | Status | Message |",
        "|---|---:|---|---|",
    ]
    for check in result["checks"]:
        message = str(check["message"]).replace("|", "\\|")
        lines.append(f"| `{check['name']}` | `{check['required']}` | `{check['status']}` | {message} |")

    lines.extend(["", "## Boundaries", ""])
    for key, value in result["boundaries"].items():
        lines.append(f"- {key}: `{value}`")

    lines.append("")
    return "\n".join(lines)


def write_validation_reports(result: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir = report_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    run_ts = utc_now_compact()
    latest_json = report_dir / "citation_reference_graph_package_latest.json"
    latest_md = report_dir / "citation_reference_graph_package_latest.md"
    history_json = history_dir / f"citation_reference_graph_package_{run_ts}.json"
    history_md = history_dir / f"citation_reference_graph_package_{run_ts}.md"

    json_text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    md_text = render_markdown(result)

    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(md_text, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate local Citation / Reference Graph package output.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--package-dir", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = validate_package(
        config_path=args.config,
        package_dir=args.package_dir,
        report_dir=args.report_dir,
        strict=args.strict,
        write_reports=not args.no_write_reports,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    if not result["summary"]["ok"]:
        print("required_failed_checks:", ", ".join(result["verdict"]["required_failed_checks"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
