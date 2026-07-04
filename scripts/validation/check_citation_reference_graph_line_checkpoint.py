"""Validate the local Citation / Reference Graph line checkpoint.

This validator is intentionally read-only. It aggregates evidence from the
already generated graph output, release-candidate gate, local package candidate,
and validation reports to determine whether the local Citation / Reference Graph
v0.1 line is internally complete as a non-public checkpoint.

It does not rebuild graph output, rebuild package output, mutate canonical truth,
touch Postgres/Qdrant/retrieval/ranking/API/UI, parse full text, create a graph
runtime, or publish anything.
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


SCHEMA_VERSION = "citation_reference_graph_line_checkpoint_validation_v1"
CONFIG_SCHEMA_VERSION = "citation_reference_graph_line_checkpoint_config_v1"
PACKAGE_MANIFEST_SCHEMA_VERSION = "citation_reference_graph_package_manifest_v1"
GRAPH_MANIFEST_SCHEMA_VERSION = "citation_reference_graph_manifest_v1"
DEFAULT_CONFIG_PATH = Path("configs/citation_reference_graph_line_checkpoint.yaml")
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def make_check(name: str, ok: bool, required: bool, message: str, details: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(name=name, ok=bool(ok), required=required, message=message, details=details)


def expected_paths_from_config(config: dict[str, Any]) -> dict[str, Any]:
    inputs = config.get("inputs", {})
    validation = config.get("validation", {})
    return {
        "graph_dir": resolve_path(inputs["graph_dir"]),
        "package_dir": resolve_path(inputs["package_dir"]),
        "output_report_json": resolve_path(inputs["output_report_json"]),
        "inspection_report_json": resolve_path(inputs["inspection_report_json"]),
        "release_candidate_report_json": resolve_path(inputs["release_candidate_report_json"]),
        "package_report_json": resolve_path(inputs["package_report_json"]),
        "package_manifest_path": resolve_path(inputs["package_manifest_path"]),
        "report_dir": resolve_path(validation.get("report_dir", DEFAULT_REPORT_DIR)),
        "tracked_files": [resolve_path(path) for path in config.get("tracked_files", [])],
        "required_graph_files": [str(name) for name in config.get("required_graph_files", [])],
        "required_package_files": [str(name) for name in config.get("required_package_files", [])],
    }


def expected_graph_counts_from_config(config: dict[str, Any]) -> dict[str, int]:
    return {str(key): int(value) for key, value in (config.get("expected_counts") or {}).items()}


def actual_graph_counts_from_graph_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    counts = _as_dict(manifest.get("counts"))
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


def actual_graph_counts_from_package_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    counts = _as_dict(_as_dict(manifest.get("graph")).get("counts"))
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


def _required_failed_count(report: dict[str, Any]) -> int | None:
    summary = _as_dict(report.get("summary"))
    if isinstance(summary.get("required_failed_count"), int):
        return summary.get("required_failed_count")
    if isinstance(report.get("required_failed_count"), int):
        return report.get("required_failed_count")
    return None


def _report_summary_ok(report: dict[str, Any]) -> bool:
    summary = _as_dict(report.get("summary"))
    return report.get("ok") is True or summary.get("ok") is True


def report_is_green(report: dict[str, Any]) -> bool:
    required_failed_count = _required_failed_count(report)
    return _report_summary_ok(report) and required_failed_count == 0


def release_candidate_report_is_green(report: dict[str, Any]) -> bool:
    verdict = _as_dict(report.get("verdict"))
    return (
        report_is_green(report)
        and verdict.get("technical_graph_candidate_ready") is True
        and verdict.get("manual_review_required") is True
        and verdict.get("manual_review_complete") is False
        and verdict.get("publication_ready") is False
    )


def package_report_is_green(report: dict[str, Any]) -> bool:
    verdict = _as_dict(report.get("verdict"))
    return (
        report_is_green(report)
        and verdict.get("package_candidate_ready") is True
        and verdict.get("manual_review_required") is True
        and verdict.get("manual_review_complete") is False
        and verdict.get("publication_ready") is False
    )


def validate_safety_config(config: dict[str, Any]) -> dict[str, Any]:
    safety = _as_dict(config.get("safety"))
    expected_true = {
        "read_only_checkpoint": True,
        "read_existing_graph_output": True,
        "read_existing_package_output": True,
    }
    expected_false = {
        "rebuild_graph": False,
        "rebuild_package": False,
        "mutate_canonical_documents": False,
        "mutate_retrieval_artifacts": False,
        "mutate_qdrant": False,
        "mutate_postgres": False,
        "mutate_db_schema": False,
        "mutate_api": False,
        "mutate_ui": False,
        "mutate_ranking": False,
        "publish_dataset": False,
        "publish_graph": False,
        "create_latest_pointer": False,
        "create_graph_runtime": False,
        "require_networkx_runtime": False,
        "require_neo4j_runtime": False,
        "require_graphrag_runtime": False,
        "parse_full_text": False,
        "parse_pdfs": False,
        "parse_bibliography_sections": False,
    }
    mismatches = {
        key: {"expected": expected, "actual": safety.get(key)}
        for key, expected in {**expected_true, **expected_false}.items()
        if safety.get(key) is not expected
    }
    return {"ok": not mismatches, "mismatches": mismatches, "safety": safety}


def validate_graph_manifest_safety(manifest: dict[str, Any]) -> dict[str, Any]:
    safety = _as_dict(manifest.get("safety"))
    builder = _as_dict(manifest.get("builder"))
    expected_false = (
        "may_overwrite_operational_latest",
        "may_be_used_as_reconcile_input",
        "may_change_db_schema",
        "may_change_api_behavior",
        "may_change_streamlit_behavior",
        "may_change_retrieval_behavior",
        "may_change_qdrant_behavior",
        "may_change_ranking_behavior",
        "may_require_graph_runtime",
        "may_publish_without_manual_review",
    )
    mismatches: dict[str, Any] = {}
    for key in expected_false:
        if safety.get(key) is not False:
            mismatches[key] = safety.get(key)
    if safety.get("canonical_truth_impact") != "none":
        mismatches["canonical_truth_impact"] = safety.get("canonical_truth_impact")
    if builder.get("input_mode") != "file":
        mismatches["builder.input_mode"] = builder.get("input_mode")
    if builder.get("live_db_dependency") is not False:
        mismatches["builder.live_db_dependency"] = builder.get("live_db_dependency")
    return {"ok": not mismatches, "mismatches": mismatches, "safety": safety, "builder": builder}


def validate_package_manifest_safety(manifest: dict[str, Any]) -> dict[str, Any]:
    package = _as_dict(manifest.get("package"))
    boundaries = _as_dict(manifest.get("boundaries"))
    package_flags_ok = (
        package.get("publication_ready") is False
        and package.get("manual_review_required") is True
        and package.get("may_be_used_as_reconcile_input") is False
    )
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
    return {
        "ok": package_flags_ok and not boundary_mismatches,
        "package_flags_ok": package_flags_ok,
        "package": package,
        "boundary_mismatches": boundary_mismatches,
        "boundaries": boundaries,
    }


def check_line_checkpoint(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    report_dir: Path | None = None,
    strict: bool = False,
    write_reports: bool = True,
) -> dict[str, Any]:
    config = load_yaml(config_path)
    paths = expected_paths_from_config(config)
    report_dir = report_dir or paths["report_dir"]
    checks: list[CheckResult] = []

    checks.append(
        make_check(
            "config_schema",
            config.get("schema_version") == CONFIG_SCHEMA_VERSION,
            True,
            "Line checkpoint config schema is correct"
            if config.get("schema_version") == CONFIG_SCHEMA_VERSION
            else "Line checkpoint config schema is incorrect",
            {"schema_version": config.get("schema_version")},
        )
    )

    checkpoint = _as_dict(config.get("checkpoint"))
    checkpoint_flags_ok = (
        checkpoint.get("name") == "citation_reference_graph_line_checkpoint"
        and checkpoint.get("version") == "v0.1"
        and checkpoint.get("status") == "local_line_checkpoint"
        and checkpoint.get("publication_ready") is False
        and checkpoint.get("manual_review_required") is True
        and checkpoint.get("manual_review_complete") is False
        and checkpoint.get("may_be_used_as_reconcile_input") is False
    )
    checks.append(
        make_check(
            "checkpoint_identity_and_flags",
            checkpoint_flags_ok,
            True,
            "Checkpoint identity and publication/reconcile flags are safe"
            if checkpoint_flags_ok
            else "Checkpoint identity or publication/reconcile flags are unsafe",
            checkpoint,
        )
    )

    accepted_components = _as_dict(config.get("accepted_components"))
    missing_or_empty_components = {
        key: value for key, value in accepted_components.items() if not isinstance(value, str) or not value.startswith("accepted")
    }
    required_component_names = {
        "contract",
        "builder",
        "output_validator",
        "reference_normalization_fix",
        "inspection",
        "query_cli",
        "docs_counter_refresh",
        "release_candidate",
        "package",
    }
    missing_component_names = sorted(required_component_names - set(accepted_components))
    components_ok = not missing_or_empty_components and not missing_component_names
    checks.append(
        make_check(
            "accepted_line_components",
            components_ok,
            True,
            "All expected line components are marked accepted"
            if components_ok
            else "Some expected line components are missing or not accepted",
            {"missing_component_names": missing_component_names, "invalid_components": missing_or_empty_components},
        )
    )

    safety_config = validate_safety_config(config)
    checks.append(
        make_check(
            "checkpoint_safety_config",
            safety_config["ok"],
            True,
            "Checkpoint config safety flags preserve project boundaries"
            if safety_config["ok"]
            else "Checkpoint config safety flags do not preserve project boundaries",
            safety_config,
        )
    )

    missing_tracked_files = [normalize_path(path) for path in paths["tracked_files"] if not path.exists()]
    checks.append(
        make_check(
            "tracked_files_present",
            not missing_tracked_files,
            True,
            "Required tracked line-checkpoint files are present"
            if not missing_tracked_files
            else "Required tracked line-checkpoint files are missing",
            {"missing_files": missing_tracked_files},
        )
    )

    missing_graph_files = [
        normalize_path(paths["graph_dir"] / name) for name in paths["required_graph_files"] if not (paths["graph_dir"] / name).exists()
    ]
    checks.append(
        make_check(
            "required_graph_output_files_present",
            not missing_graph_files,
            True,
            "Required graph output files are present" if not missing_graph_files else "Required graph output files are missing",
            {"missing_files": missing_graph_files},
        )
    )

    graph_manifest: dict[str, Any] = {}
    if not missing_graph_files:
        try:
            graph_manifest = load_json(paths["graph_dir"] / "manifest.json")
            checks.append(make_check("graph_manifest_readable", True, True, "Graph manifest is readable"))
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("graph_manifest_readable", False, True, f"Graph manifest is not readable: {exc}"))

    if graph_manifest:
        graph_identity = _as_dict(graph_manifest.get("graph"))
        identity_ok = (
            graph_manifest.get("schema_version") == GRAPH_MANIFEST_SCHEMA_VERSION
            and graph_identity.get("name") == "citation_reference_graph"
            and graph_identity.get("version") == "v0.1"
        )
        checks.append(
            make_check(
                "graph_manifest_identity",
                identity_ok,
                True,
                "Graph manifest identity matches Citation / Reference Graph v0.1"
                if identity_ok
                else "Graph manifest identity is not Citation / Reference Graph v0.1",
                {"schema_version": graph_manifest.get("schema_version"), "graph": graph_identity},
            )
        )

        graph_safety = validate_graph_manifest_safety(graph_manifest)
        checks.append(
            make_check(
                "graph_manifest_safety",
                graph_safety["ok"],
                True,
                "Graph manifest safety flags preserve derived-layer boundaries"
                if graph_safety["ok"]
                else "Graph manifest safety flags do not preserve derived-layer boundaries",
                graph_safety,
            )
        )

        expected_counts = expected_graph_counts_from_config(config)
        actual_counts = actual_graph_counts_from_graph_manifest(graph_manifest)
        graph_count_mismatches = {
            key: {"expected": expected, "actual": actual_counts.get(key)}
            for key, expected in expected_counts.items()
            if actual_counts.get(key) != expected
        }
        checks.append(
            make_check(
                "accepted_graph_counts",
                not graph_count_mismatches,
                True,
                "Graph counters match accepted post-normalization baseline"
                if not graph_count_mismatches
                else "Graph counters differ from accepted post-normalization baseline",
                {"mismatches": graph_count_mismatches, "actual_counts": actual_counts},
            )
        )

    report_inputs = [
        ("output_validator_report_green", paths["output_report_json"], report_is_green, "Output validator report is green"),
        ("inspection_report_green", paths["inspection_report_json"], report_is_green, "Inspection report is green"),
        (
            "release_candidate_report_green",
            paths["release_candidate_report_json"],
            release_candidate_report_is_green,
            "Release-candidate report is green",
        ),
        ("package_report_green", paths["package_report_json"], package_report_is_green, "Package report is green"),
    ]
    for check_name, report_path, predicate, success_message in report_inputs:
        if not report_path.exists():
            checks.append(
                make_check(
                    check_name,
                    False,
                    True,
                    f"{success_message} report is missing",
                    {"path": normalize_path(report_path)},
                )
            )
            continue
        try:
            report = load_json(report_path)
            report_ok = predicate(report)
            checks.append(
                make_check(
                    check_name,
                    report_ok,
                    True,
                    success_message if report_ok else f"{success_message} check failed",
                    {
                        "path": normalize_path(report_path),
                        "summary_ok": _report_summary_ok(report),
                        "required_failed_count": _required_failed_count(report),
                        "verdict": _as_dict(report.get("verdict")),
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                make_check(check_name, False, True, f"Failed to read report {normalize_path(report_path)}: {exc}")
            )

    missing_package_files = [
        normalize_path(paths["package_dir"] / name)
        for name in paths["required_package_files"]
        if not (paths["package_dir"] / name).exists()
    ]
    checks.append(
        make_check(
            "required_package_files_present",
            not missing_package_files,
            True,
            "Required package files are present" if not missing_package_files else "Required package files are missing",
            {"missing_files": missing_package_files},
        )
    )

    package_manifest: dict[str, Any] = {}
    if paths["package_manifest_path"].exists():
        try:
            package_manifest = load_json(paths["package_manifest_path"])
            checks.append(make_check("package_manifest_readable", True, True, "Package manifest is readable"))
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("package_manifest_readable", False, True, f"Package manifest is not readable: {exc}"))
    else:
        checks.append(
            make_check(
                "package_manifest_readable",
                False,
                True,
                "Package manifest is missing",
                {"path": normalize_path(paths["package_manifest_path"])},
            )
        )

    if package_manifest:
        package_schema_ok = package_manifest.get("schema_version") == PACKAGE_MANIFEST_SCHEMA_VERSION
        checks.append(
            make_check(
                "package_manifest_schema",
                package_schema_ok,
                True,
                "Package manifest schema is correct" if package_schema_ok else "Package manifest schema is incorrect",
                {"schema_version": package_manifest.get("schema_version")},
            )
        )

        package_safety = validate_package_manifest_safety(package_manifest)
        checks.append(
            make_check(
                "package_manifest_safety",
                package_safety["ok"],
                True,
                "Package manifest safety flags preserve checkpoint boundaries"
                if package_safety["ok"]
                else "Package manifest safety flags do not preserve checkpoint boundaries",
                package_safety,
            )
        )

        expected_counts = expected_graph_counts_from_config(config)
        package_actual_counts = actual_graph_counts_from_package_manifest(package_manifest)
        package_count_mismatches = {
            key: {"expected": expected, "actual": package_actual_counts.get(key)}
            for key, expected in expected_counts.items()
            if package_actual_counts.get(key) != expected
        }
        checks.append(
            make_check(
                "package_graph_counts",
                not package_count_mismatches,
                True,
                "Package manifest graph counters match accepted baseline"
                if not package_count_mismatches
                else "Package manifest graph counters differ from accepted baseline",
                {"mismatches": package_count_mismatches, "actual_counts": package_actual_counts},
            )
        )

    zip_path = paths["package_dir"] / "citation_reference_graph_v0.1.zip"
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path, mode="r") as archive:
                bad_member = archive.testzip()
            checks.append(
                make_check(
                    "package_zip_readable",
                    bad_member is None,
                    True,
                    "Package zip is readable" if bad_member is None else "Package zip has a corrupt member",
                    {"bad_member": bad_member},
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("package_zip_readable", False, True, f"Failed to inspect package zip: {exc}"))
    else:
        checks.append(
            make_check(
                "package_zip_readable",
                False,
                True,
                "Package zip is missing",
                {"path": normalize_path(zip_path)},
            )
        )

    required_failed = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    ok = not required_failed

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": normalize_path(config_path),
        "graph_dir": normalize_path(paths["graph_dir"]),
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
            "citation_reference_graph_line_complete": ok,
            "line_checkpoint_ready": ok,
            "manual_review_required": True,
            "manual_review_complete": False,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "required_failed_checks": [check.name for check in required_failed],
            "warning_checks": [check.name for check in warnings],
        },
        "boundaries": {
            "read_only_checkpoint": True,
            "rebuilds_graph": False,
            "rebuilds_package": False,
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
        "# Citation / Reference Graph Line Checkpoint",
        "",
        f"- schema_version: `{result['schema_version']}`",
        f"- generated_at: `{result['generated_at']}`",
        f"- config_path: `{result['config_path']}`",
        f"- graph_dir: `{result['graph_dir']}`",
        f"- package_dir: `{result['package_dir']}`",
        f"- ok: `{summary['ok']}`",
        f"- strict: `{summary['strict']}`",
        f"- required_failed_count: `{summary['required_failed_count']}`",
        f"- warning_count: `{summary['warning_count']}`",
        "",
        "## Verdict",
        "",
        f"- citation_reference_graph_line_complete: `{verdict['citation_reference_graph_line_complete']}`",
        f"- line_checkpoint_ready: `{verdict['line_checkpoint_ready']}`",
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
    latest_json = report_dir / "citation_reference_graph_line_checkpoint_latest.json"
    latest_md = report_dir / "citation_reference_graph_line_checkpoint_latest.md"
    history_json = history_dir / f"citation_reference_graph_line_checkpoint_{run_ts}.json"
    history_md = history_dir / f"citation_reference_graph_line_checkpoint_{run_ts}.md"

    json_text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    md_text = render_markdown(result)

    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(md_text, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Citation / Reference Graph line checkpoint.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = check_line_checkpoint(
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
