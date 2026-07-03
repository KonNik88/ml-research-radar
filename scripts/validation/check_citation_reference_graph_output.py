from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path("configs/citation_reference_graph.yaml")
DEFAULT_OUTPUT_DIR = Path("data/graphs/citation_reference_graph/v0.1")
REPORT_SCHEMA_VERSION = "citation_reference_graph_output_quality_v1"
REPORT_BASENAME = "citation_reference_graph_output"

REQUIRED_FILES = {
    "nodes.jsonl",
    "edges.jsonl",
    "schema.json",
    "manifest.json",
    "data_quality_summary.json",
    "README.md",
    "checksums.txt",
}
REQUIRED_NODE_TYPES = {"paper", "external_reference", "source_family"}
REQUIRED_EDGE_TYPES = {
    "paper_references_paper",
    "paper_references_external",
    "paper_has_reference_source_family",
}
COMMON_EDGE_FIELDS = {
    "edge_id",
    "edge_type",
    "source_node_id",
    "target_node_id",
    "provenance_kind",
    "source_layer",
    "confidence",
}
FALSE_SAFETY_FLAGS = {
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
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool = True
    details: str | None = None


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be an object at {path}:{line_no}")
            rows.append(row)
    return rows


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _add_check(checks: list[CheckResult], name: str, ok: bool, details: str | None = None, required: bool = True) -> None:
    checks.append(CheckResult(name=name, ok=bool(ok), details=details, required=required))


def _load_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        checksums[parts[-1]] = parts[0]
    return checksums


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary", {})
    checks = report.get("checks", [])
    failed = [c for c in checks if c.get("required") and not c.get("ok")]
    lines = [
        "# Citation / Reference Graph Output Check",
        "",
        "```text",
        f"ok={summary.get('ok')}",
        f"required_failed_count={summary.get('required_failed_count')}",
        f"warning_count={summary.get('warning_count')}",
        f"total_checks={summary.get('total_checks')}",
        "```",
        "",
        "## Failed required checks",
    ]
    if failed:
        lines.extend(f"- `{c.get('name')}`: {c.get('details') or ''}" for c in failed)
    else:
        lines.append("No failed required checks.")
    lines.extend(["", "## Boundary", "", "This output validator is read-only and does not change canonical truth, DB, API, UI, retrieval, Qdrant, ranking, or runtime behavior.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _expected_output_dir(config: dict[str, Any]) -> Path:
    outputs = _as_dict(config.get("outputs"))
    raw = outputs.get("expected_future_output_dir") or str(DEFAULT_OUTPUT_DIR)
    return Path(str(raw))


def validate_output(
    *,
    config_path: Path = CONFIG_PATH,
    output_dir: Path | None = None,
    strict: bool = False,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    config = _read_yaml(config_path)
    source_checkpoint = _as_dict(config.get("source_checkpoint"))
    output_dir = output_dir or _expected_output_dir(config)

    checks: list[CheckResult] = []

    _add_check(checks, "config_exists", config_path.exists())
    _add_check(checks, "output_dir_exists", output_dir.exists())

    for name in sorted(REQUIRED_FILES):
        _add_check(checks, f"required_file_exists:{name}", (output_dir / name).exists())

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    schema: dict[str, Any] = {}
    manifest: dict[str, Any] = {}
    data_quality_summary: dict[str, Any] = {}
    checksums: dict[str, str] = {}

    try:
        if (output_dir / "nodes.jsonl").exists():
            nodes = _read_jsonl(output_dir / "nodes.jsonl")
        if (output_dir / "edges.jsonl").exists():
            edges = _read_jsonl(output_dir / "edges.jsonl")
        if (output_dir / "schema.json").exists():
            schema = _read_json(output_dir / "schema.json")
        if (output_dir / "manifest.json").exists():
            manifest = _read_json(output_dir / "manifest.json")
        if (output_dir / "data_quality_summary.json").exists():
            data_quality_summary = _read_json(output_dir / "data_quality_summary.json")
        if (output_dir / "checksums.txt").exists():
            checksums = _load_checksums(output_dir / "checksums.txt")
        _add_check(checks, "graph_files_readable", True)
    except Exception as exc:
        _add_check(checks, "graph_files_readable", False, str(exc))

    node_ids = [str(row.get("node_id")) for row in nodes if row.get("node_id")]
    edge_ids = [str(row.get("edge_id")) for row in edges if row.get("edge_id")]
    node_id_set = set(node_ids)
    node_type_counts = {kind: sum(1 for row in nodes if row.get("node_type") == kind) for kind in REQUIRED_NODE_TYPES}
    edge_type_counts = {kind: sum(1 for row in edges if row.get("edge_type") == kind) for kind in REQUIRED_EDGE_TYPES}

    _add_check(checks, "nodes_non_empty", len(nodes) > 0, f"nodes={len(nodes)}")
    _add_check(checks, "edges_non_empty", len(edges) > 0, f"edges={len(edges)}")
    _add_check(checks, "node_ids_unique", len(node_ids) == len(node_id_set), f"nodes={len(nodes)} unique_node_ids={len(node_id_set)}")
    _add_check(checks, "edge_ids_unique", len(edge_ids) == len(set(edge_ids)), f"edges={len(edges)} unique_edge_ids={len(set(edge_ids))}")

    missing_node_types = sorted(kind for kind in REQUIRED_NODE_TYPES if node_type_counts.get(kind, 0) <= 0)
    _add_check(checks, "required_node_types_present", not missing_node_types, ", ".join(missing_node_types) or None)

    missing_edge_types = sorted(kind for kind in REQUIRED_EDGE_TYPES if edge_type_counts.get(kind, 0) <= 0)
    _add_check(checks, "required_edge_types_present", not missing_edge_types, ", ".join(missing_edge_types) or None)

    missing_edge_fields = []
    dangling_edges = []
    invalid_confidence = []
    for edge in edges:
        missing = sorted(field for field in COMMON_EDGE_FIELDS if field not in edge)
        if missing:
            missing_edge_fields.append(f"{edge.get('edge_id')}:{','.join(missing)}")
        source_node_id = edge.get("source_node_id")
        target_node_id = edge.get("target_node_id")
        if source_node_id not in node_id_set or target_node_id not in node_id_set:
            dangling_edges.append(str(edge.get("edge_id")))
        try:
            confidence = float(edge.get("confidence"))
            if not 0.0 <= confidence <= 1.0:
                invalid_confidence.append(str(edge.get("edge_id")))
        except Exception:
            invalid_confidence.append(str(edge.get("edge_id")))
    _add_check(checks, "edge_common_fields_present", not missing_edge_fields, "; ".join(missing_edge_fields[:5]) or None)
    _add_check(checks, "edges_reference_existing_nodes", not dangling_edges, ", ".join(dangling_edges[:10]) or None)
    _add_check(checks, "edge_confidence_range_ok", not invalid_confidence, ", ".join(invalid_confidence[:10]) or None)

    schema_graph = _as_dict(schema.get("graph"))
    manifest_graph = _as_dict(manifest.get("graph"))
    manifest_counts = _as_dict(manifest.get("counts"))
    manifest_safety = _as_dict(manifest.get("safety"))
    manifest_builder = _as_dict(manifest.get("builder"))
    dqs_summary = _as_dict(data_quality_summary.get("summary"))

    _add_check(checks, "schema_version_ok", schema.get("schema_version") == "citation_reference_graph_schema_v1")
    _add_check(checks, "schema_graph_identity_ok", schema_graph.get("name") == "citation_reference_graph" and schema_graph.get("version") == "v0.1")
    _add_check(checks, "manifest_schema_version_ok", manifest.get("schema_version") == "citation_reference_graph_manifest_v1")
    _add_check(checks, "manifest_graph_identity_ok", manifest_graph.get("name") == "citation_reference_graph" and manifest_graph.get("version") == "v0.1")
    _add_check(checks, "manifest_input_mode_file", manifest_builder.get("input_mode") == "file")
    _add_check(checks, "manifest_no_live_db_dependency", manifest_builder.get("live_db_dependency") is False)
    _add_check(checks, "data_quality_schema_version_ok", data_quality_summary.get("schema_version") == "citation_reference_graph_data_quality_summary_v1")
    _add_check(checks, "data_quality_summary_ok", dqs_summary.get("ok") is True)

    bad_safety = [key for key in sorted(FALSE_SAFETY_FLAGS) if manifest_safety.get(key) is not False]
    _add_check(checks, "manifest_safety_flags_false", not bad_safety, ", ".join(bad_safety) or None)
    _add_check(checks, "manifest_canonical_truth_impact_none", manifest_safety.get("canonical_truth_impact") == "none")

    expected_count = source_checkpoint.get("expected_canonical_doc_count")
    expected_count_int = int(expected_count) if expected_count is not None else None
    manifest_limit = manifest_builder.get("limit")
    if expected_count_int is not None and manifest_limit is None:
        _add_check(checks, "paper_nodes_match_expected_canonical_count", node_type_counts.get("paper", 0) == expected_count_int, f"paper_nodes={node_type_counts.get('paper', 0)} expected={expected_count_int}")
    else:
        _add_check(checks, "paper_nodes_match_expected_canonical_count", True, "skipped because expected count is absent or builder limit is set", required=False)

    _add_check(checks, "manifest_nodes_count_matches", int(manifest_counts.get("nodes_count", -1)) == len(nodes), f"manifest={manifest_counts.get('nodes_count')} actual={len(nodes)}")
    _add_check(checks, "manifest_edges_count_matches", int(manifest_counts.get("edges_count", -1)) == len(edges), f"manifest={manifest_counts.get('edges_count')} actual={len(edges)}")
    _add_check(checks, "dqs_nodes_count_matches", int(dqs_summary.get("nodes_count", -1)) == len(nodes), f"dqs={dqs_summary.get('nodes_count')} actual={len(nodes)}")
    _add_check(checks, "dqs_edges_count_matches", int(dqs_summary.get("edges_count", -1)) == len(edges), f"dqs={dqs_summary.get('edges_count')} actual={len(edges)}")

    checksum_missing = sorted(name for name in REQUIRED_FILES - {"checksums.txt"} if name not in checksums)
    checksum_bad = []
    for name, expected in checksums.items():
        path = output_dir / name
        if not path.exists():
            checksum_bad.append(name)
            continue
        actual = _sha256_file(path)
        if actual != expected:
            checksum_bad.append(name)
    _add_check(checks, "checksums_cover_required_files", not checksum_missing, ", ".join(checksum_missing) or None)
    _add_check(checks, "checksums_match", not checksum_bad, ", ".join(checksum_bad) or None)

    required_failed = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "config_path": str(config_path),
        "output_dir": str(output_dir),
        "strict": strict,
        "summary": {
            "ok": len(required_failed) == 0,
            "required_failed_count": len(required_failed),
            "warning_count": len(warnings),
            "total_checks": len(checks),
        },
        "counts": {
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "node_type_counts": node_type_counts,
            "edge_type_counts": edge_type_counts,
        },
        "checks": [check.__dict__ for check in checks],
        "required_failed_checks": [check.name for check in required_failed],
        "warning_checks": [check.name for check in warnings],
        "verdict": {
            "technical_graph_output_ready": len(required_failed) == 0,
            "manual_review_required": True,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
        },
        "boundaries": {
            "read_only_validator": True,
            "graph_is_canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "changes_db_schema": False,
            "changes_api_behavior": False,
            "changes_streamlit_behavior": False,
            "changes_retrieval_behavior": False,
            "changes_qdrant_behavior": False,
            "changes_ranking_behavior": False,
            "requires_graph_runtime": False,
            "publishes_graph": False,
        },
    }

    if write_reports:
        report_dir = report_dir or Path("artifacts/reports/validation")
        history_dir = report_dir / "history"
        run_ts = _now_ts()
        _write_report(report_dir / f"{REPORT_BASENAME}_latest.json", report)
        _write_markdown(report_dir / f"{REPORT_BASENAME}_latest.md", report)
        _write_report(history_dir / f"{REPORT_BASENAME}_{run_ts}.json", report)
        _write_markdown(history_dir / f"{REPORT_BASENAME}_{run_ts}.md", report)

    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local derived Citation / Reference Graph v0.1 output.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to citation/reference graph config.")
    parser.add_argument("--output-dir", default=None, help="Override graph output directory.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when required checks fail.")
    parser.add_argument("--no-write-reports", action="store_true", help="Do not write latest/history report files.")
    parser.add_argument("--report-dir", default=None, help="Override report directory.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = validate_output(
        config_path=Path(args.config),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        strict=args.strict,
        write_reports=not args.no_write_reports,
        report_dir=Path(args.report_dir) if args.report_dir else None,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    if args.strict and not report["summary"].get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
