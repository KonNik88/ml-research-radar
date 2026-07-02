"""Validate the local Paper-Artifact Graph line checkpoint.

This is a read-only aggregate gate over the completed local graph line:
contract -> builder -> output validation -> inspection -> query CLI -> release
candidate -> package. It reads existing generated artifacts and validation
reports; it does not rebuild graph output, create packages, or mutate runtime
layers.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "paper_artifact_graph_line_checkpoint_v1"
CONFIG_SCHEMA_VERSION = "paper_artifact_graph_line_checkpoint_config_v1"
DEFAULT_CONFIG_PATH = Path("configs/paper_artifact_graph_line_checkpoint.yaml")
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


def make_check(name: str, ok: bool, required: bool, message: str, details: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(name=name, ok=ok, required=required, message=message, details=details)


def report_is_green(path: Path) -> tuple[bool, dict[str, Any]]:
    if not path.exists():
        return False, {"path": normalize_path(path), "exists": False}
    try:
        report = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return False, {"path": normalize_path(path), "exists": True, "read_error": str(exc)}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    verdict = report.get("verdict") if isinstance(report.get("verdict"), dict) else {}
    ok = summary.get("ok") is True and summary.get("required_failed_count") == 0
    return ok, {
        "path": normalize_path(path),
        "schema_version": report.get("schema_version"),
        "summary_ok": summary.get("ok"),
        "required_failed_count": summary.get("required_failed_count"),
        "warning_count": summary.get("warning_count"),
        "verdict": verdict,
    }


def graph_counts_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    quality = manifest.get("quality_summary") if isinstance(manifest.get("quality_summary"), dict) else {}
    node_counts = quality.get("node_type_counts") if isinstance(quality.get("node_type_counts"), dict) else {}
    edge_counts = quality.get("edge_type_counts") if isinstance(quality.get("edge_type_counts"), dict) else {}
    return {
        "nodes_count": quality.get("nodes_count"),
        "edges_count": quality.get("edges_count"),
        "node_paper_count": node_counts.get("paper"),
        "node_artifact_count": node_counts.get("artifact"),
        "node_provider_count": node_counts.get("provider"),
        "node_source_family_count": node_counts.get("source_family"),
        "node_topic_cluster_count": node_counts.get("topic_cluster"),
        "edge_paper_has_artifact_count": edge_counts.get("paper_has_artifact"),
        "edge_artifact_from_provider_count": edge_counts.get("artifact_from_provider"),
        "edge_paper_observed_in_source_family_count": edge_counts.get("paper_observed_in_source_family"),
        "edge_paper_assigned_to_topic_cluster_count": edge_counts.get("paper_assigned_to_topic_cluster"),
        "trusted_links_used_count": quality.get("trusted_links_used_count"),
        "topic_edges_count": quality.get("topic_edges_count"),
    }


def graph_manifest_safety(manifest: dict[str, Any]) -> dict[str, Any]:
    builder = manifest.get("builder") if isinstance(manifest.get("builder"), dict) else {}
    graph = manifest.get("graph") if isinstance(manifest.get("graph"), dict) else {}
    return {
        "builder_input_mode": builder.get("input_mode"),
        "builder_live_db_dependency": builder.get("live_db_dependency"),
        "builder_create_latest_pointer": builder.get("create_latest_pointer"),
        "graph_canonical_truth": graph.get("canonical_truth"),
        "graph_may_be_used_as_reconcile_input": graph.get("may_be_used_as_reconcile_input"),
        "graph_publication_ready": graph.get("publication_ready"),
        "manifest_canonical_truth": manifest.get("canonical_truth"),
        "manifest_may_be_used_as_reconcile_input": manifest.get("may_be_used_as_reconcile_input"),
        "manifest_publication_ready": manifest.get("publication_ready"),
        "dry_run": manifest.get("dry_run"),
    }


def package_manifest_safety(manifest: dict[str, Any]) -> dict[str, Any]:
    package = manifest.get("package") if isinstance(manifest.get("package"), dict) else {}
    boundaries = manifest.get("boundaries") if isinstance(manifest.get("boundaries"), dict) else {}
    release = manifest.get("release_candidate") if isinstance(manifest.get("release_candidate"), dict) else {}
    return {
        "package_publication_ready": package.get("publication_ready"),
        "package_manual_review_required": package.get("manual_review_required"),
        "package_may_be_used_as_reconcile_input": package.get("may_be_used_as_reconcile_input"),
        "boundary_local_package_candidate": boundaries.get("local_package_candidate"),
        "boundary_generated_output": boundaries.get("generated_output"),
        "boundary_read_only_graph_input": boundaries.get("read_only_graph_input"),
        "boundary_rebuilds_graph": boundaries.get("rebuilds_graph"),
        "boundary_mutates_canonical_truth": boundaries.get("mutates_canonical_truth"),
        "boundary_may_be_used_as_reconcile_input": boundaries.get("may_be_used_as_reconcile_input"),
        "boundary_changes_postgres": boundaries.get("changes_postgres"),
        "boundary_changes_qdrant": boundaries.get("changes_qdrant"),
        "boundary_changes_retrieval": boundaries.get("changes_retrieval"),
        "boundary_changes_ranking": boundaries.get("changes_ranking"),
        "boundary_changes_api": boundaries.get("changes_api"),
        "boundary_changes_ui": boundaries.get("changes_ui"),
        "boundary_publishes_dataset": boundaries.get("publishes_dataset"),
        "release_summary_ok": release.get("summary_ok"),
        "release_required_failed_count": release.get("required_failed_count"),
        "release_technical_graph_candidate_ready": release.get("technical_graph_candidate_ready"),
        "release_manual_review_required": release.get("manual_review_required"),
        "release_publication_ready": release.get("publication_ready"),
    }


def validate_line_checkpoint(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    report_dir: Path | None = None,
    strict: bool = False,
    write_reports: bool = True,
) -> dict[str, Any]:
    checks: list[CheckResult] = []
    config = load_yaml(config_path)
    checks.append(make_check(
        "config_schema",
        config.get("schema_version") == CONFIG_SCHEMA_VERSION,
        True,
        "Line checkpoint config schema is correct" if config.get("schema_version") == CONFIG_SCHEMA_VERSION else "Line checkpoint config schema is incorrect",
        {"schema_version": config.get("schema_version")},
    ))

    report_dir = report_dir or resolve_path((config.get("validation") or {}).get("report_dir", DEFAULT_REPORT_DIR))

    required_tracked_files = [resolve_path(path) for path in config.get("required_tracked_files", [])]
    missing_tracked = [normalize_path(path) for path in required_tracked_files if not path.exists()]
    checks.append(make_check(
        "required_tracked_files_present",
        not missing_tracked,
        True,
        "Required graph-line tracked files are present" if not missing_tracked else "Required graph-line tracked files are missing",
        {"missing_files": missing_tracked},
    ))

    inputs = config.get("inputs", {})
    graph_dir = resolve_path(inputs["graph_dir"])
    package_dir = resolve_path(inputs["package_dir"])

    missing_graph = [name for name in config.get("required_graph_files", []) if not (graph_dir / str(name)).exists()]
    checks.append(make_check(
        "graph_output_files_present",
        not missing_graph,
        True,
        "Required graph output files are present" if not missing_graph else "Required graph output files are missing",
        {"graph_dir": normalize_path(graph_dir), "missing_files": missing_graph},
    ))

    graph_manifest: dict[str, Any] = {}
    graph_manifest_path = graph_dir / "manifest.json"
    if graph_manifest_path.exists():
        try:
            graph_manifest = load_json(graph_manifest_path)
            checks.append(make_check("graph_manifest_readable", True, True, "Graph manifest is readable"))
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("graph_manifest_readable", False, True, f"Graph manifest is not readable: {exc}"))

    if graph_manifest:
        safety = graph_manifest_safety(graph_manifest)
        safety_ok = (
            safety["builder_input_mode"] == "file"
            and safety["builder_live_db_dependency"] is False
            and safety["builder_create_latest_pointer"] is False
            and safety["graph_canonical_truth"] is False
            and safety["graph_may_be_used_as_reconcile_input"] is False
            and safety["graph_publication_ready"] is False
            and safety["manifest_canonical_truth"] is False
            and safety["manifest_may_be_used_as_reconcile_input"] is False
            and safety["manifest_publication_ready"] is False
            and safety["dry_run"] is False
        )
        checks.append(make_check(
            "graph_manifest_safety",
            safety_ok,
            True,
            "Graph manifest safety flags preserve derived-layer boundaries" if safety_ok else "Graph manifest safety flags do not preserve derived-layer boundaries",
            safety,
        ))

        expected_counts = {str(key): int(value) for key, value in (config.get("expected_counts") or {}).items()}
        actual_counts = graph_counts_from_manifest(graph_manifest)
        mismatches = {
            key: {"expected": expected, "actual": actual_counts.get(key)}
            for key, expected in expected_counts.items()
            if actual_counts.get(key) != expected
        }
        checks.append(make_check(
            "graph_counts_match_checkpoint",
            not mismatches,
            True,
            "Graph counters match accepted checkpoint baseline" if not mismatches else "Graph counters differ from accepted checkpoint baseline",
            {"mismatches": mismatches, "actual_counts": actual_counts},
        ))

    for report_key, check_name in [
        ("inspection_report", "inspection_report_green"),
        ("release_candidate_report", "release_candidate_report_green"),
        ("package_report", "package_report_green"),
    ]:
        path = resolve_path(inputs[report_key])
        ok, details = report_is_green(path)
        checks.append(make_check(check_name, ok, True, f"{report_key} is green" if ok else f"{report_key} is not green", details))

    missing_package = [name for name in config.get("required_package_files", []) if not (package_dir / str(name)).exists()]
    checks.append(make_check(
        "package_files_present",
        not missing_package,
        True,
        "Required package files are present" if not missing_package else "Required package files are missing",
        {"package_dir": normalize_path(package_dir), "missing_files": missing_package},
    ))

    package_manifest: dict[str, Any] = {}
    package_manifest_path = package_dir / "package_manifest.json"
    if package_manifest_path.exists():
        try:
            package_manifest = load_json(package_manifest_path)
            checks.append(make_check("package_manifest_readable", True, True, "Package manifest is readable"))
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("package_manifest_readable", False, True, f"Package manifest is not readable: {exc}"))

    if package_manifest:
        safety = package_manifest_safety(package_manifest)
        safety_ok = (
            safety["package_publication_ready"] is False
            and safety["package_manual_review_required"] is True
            and safety["package_may_be_used_as_reconcile_input"] is False
            and safety["boundary_local_package_candidate"] is True
            and safety["boundary_generated_output"] is True
            and safety["boundary_read_only_graph_input"] is True
            and safety["boundary_rebuilds_graph"] is False
            and safety["boundary_mutates_canonical_truth"] is False
            and safety["boundary_may_be_used_as_reconcile_input"] is False
            and safety["boundary_changes_postgres"] is False
            and safety["boundary_changes_qdrant"] is False
            and safety["boundary_changes_retrieval"] is False
            and safety["boundary_changes_ranking"] is False
            and safety["boundary_changes_api"] is False
            and safety["boundary_changes_ui"] is False
            and safety["boundary_publishes_dataset"] is False
            and safety["release_summary_ok"] is True
            and safety["release_required_failed_count"] == 0
            and safety["release_technical_graph_candidate_ready"] is True
            and safety["release_manual_review_required"] is True
            and safety["release_publication_ready"] is False
        )
        checks.append(make_check(
            "package_manifest_safety",
            safety_ok,
            True,
            "Package manifest safety flags preserve checkpoint boundaries" if safety_ok else "Package manifest safety flags do not preserve checkpoint boundaries",
            safety,
        ))

    zip_path = package_dir / "paper_artifact_graph_v0.1.zip"
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path, mode="r") as archive:
                bad_member = archive.testzip()
                names = archive.namelist()
            zip_ok = bad_member is None and len(names) > 0
            checks.append(make_check(
                "package_zip_readable",
                zip_ok,
                True,
                "Package zip is readable" if zip_ok else "Package zip is corrupt or empty",
                {"bad_member": bad_member, "members_count": len(names)},
            ))
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("package_zip_readable", False, True, f"Package zip is not readable: {exc}"))

    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    safety_expected = {
        "read_only_checkpoint": True,
        "rebuild_graph": False,
        "mutate_canonical_documents": False,
        "mutate_artifact_inputs": False,
        "mutate_topic_inputs": False,
        "mutate_retrieval_artifacts": False,
        "mutate_qdrant": False,
        "mutate_postgres": False,
        "mutate_api": False,
        "mutate_ui": False,
        "mutate_ranking": False,
        "publish_dataset": False,
        "create_latest_pointer": False,
        "create_graph_runtime": False,
    }
    safety_mismatches = {key: {"expected": expected, "actual": safety.get(key)} for key, expected in safety_expected.items() if safety.get(key) is not expected}
    checks.append(make_check(
        "checkpoint_safety_config",
        not safety_mismatches,
        True,
        "Checkpoint config safety flags preserve project boundaries" if not safety_mismatches else "Checkpoint config safety flags do not preserve project boundaries",
        {"mismatches": safety_mismatches},
    ))

    required_failed = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    ok = not required_failed

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": normalize_path(config_path),
        "summary": {
            "ok": ok,
            "strict": strict,
            "required_failed_count": len(required_failed),
            "warning_count": len(warnings),
            "total_checks": len(checks),
        },
        "line_components": dict(config.get("line_components", {})),
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
            "paper_artifact_graph_line_complete": ok,
            "local_checkpoint_ready": ok,
            "manual_review_required_before_publication": True,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "required_failed_checks": [check.name for check in required_failed],
            "warning_checks": [check.name for check in warnings],
        },
        "boundaries": {
            "read_only_checkpoint": True,
            "derived_graph_only": True,
            "rebuilds_graph": False,
            "mutates_canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "changes_postgres": False,
            "changes_qdrant": False,
            "changes_retrieval": False,
            "changes_ranking": False,
            "changes_api": False,
            "changes_ui": False,
            "publishes_dataset": False,
            "creates_graph_runtime": False,
        },
    }

    if write_reports:
        write_validation_reports(result, report_dir)

    return result


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    verdict = result["verdict"]
    lines = [
        "# Paper-Artifact Graph Line Checkpoint",
        "",
        f"- schema_version: `{result['schema_version']}`",
        f"- generated_at: `{result['generated_at']}`",
        f"- config_path: `{result['config_path']}`",
        f"- ok: `{summary['ok']}`",
        f"- strict: `{summary['strict']}`",
        f"- required_failed_count: `{summary['required_failed_count']}`",
        f"- warning_count: `{summary['warning_count']}`",
        "",
        "## Verdict",
        "",
        f"- paper_artifact_graph_line_complete: `{verdict['paper_artifact_graph_line_complete']}`",
        f"- local_checkpoint_ready: `{verdict['local_checkpoint_ready']}`",
        f"- manual_review_required_before_publication: `{verdict['manual_review_required_before_publication']}`",
        f"- publication_ready: `{verdict['publication_ready']}`",
        f"- publication_block_reason: `{verdict['publication_block_reason']}`",
        "",
        "## Line components",
        "",
    ]
    for key, value in result.get("line_components", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Checks", "", "| Check | Required | Status | Message |", "|---|---:|---|---|"])
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
    latest_json = report_dir / "paper_artifact_graph_line_checkpoint_latest.json"
    latest_md = report_dir / "paper_artifact_graph_line_checkpoint_latest.md"
    history_json = history_dir / f"paper_artifact_graph_line_checkpoint_{run_ts}.json"
    history_md = history_dir / f"paper_artifact_graph_line_checkpoint_{run_ts}.md"
    json_text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    md_text = render_markdown(result)
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(md_text, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the local Paper-Artifact Graph line checkpoint.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = validate_line_checkpoint(
        config_path=args.config,
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
