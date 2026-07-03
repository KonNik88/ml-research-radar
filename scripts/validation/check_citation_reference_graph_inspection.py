from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path("configs/citation_reference_graph.yaml")
DEFAULT_GRAPH_DIR = Path("data/graphs/citation_reference_graph/v0.1")
REPORT_SCHEMA_VERSION = "citation_reference_graph_inspection_report_v1"
REPORT_BASENAME = "citation_reference_graph_inspection"

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
REFERENCE_EDGE_TYPES = {"paper_references_paper", "paper_references_external"}
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _add_check(checks: list[CheckResult], name: str, ok: bool, details: str | None = None, required: bool = True) -> None:
    checks.append(CheckResult(name=name, ok=bool(ok), details=details, required=required))


def _write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _format_top(items: list[dict[str, Any]], label_key: str, value_key: str = "count") -> list[str]:
    if not items:
        return ["No entries."]
    return [f"- `{row.get(label_key)}`: {row.get(value_key)}" for row in items]


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = _as_dict(report.get("summary"))
    inspection = _as_dict(report.get("inspection"))
    top_referenced = inspection.get("top_referenced_papers") if isinstance(inspection.get("top_referenced_papers"), list) else []
    top_external = inspection.get("top_external_references") if isinstance(inspection.get("top_external_references"), list) else []
    failed = [c for c in report.get("checks", []) if c.get("required") and not c.get("ok")]

    lines = [
        "# Citation / Reference Graph Inspection",
        "",
        "```text",
        f"ok={summary.get('ok')}",
        f"required_failed_count={summary.get('required_failed_count')}",
        f"warning_count={summary.get('warning_count')}",
        f"total_checks={summary.get('total_checks')}",
        f"nodes_count={summary.get('nodes_count')}",
        f"edges_count={summary.get('edges_count')}",
        f"resolved_reference_edges_count={inspection.get('resolved_reference_edges_count')}",
        f"unresolved_reference_edges_count={inspection.get('unresolved_reference_edges_count')}",
        f"reference_resolution_ratio={inspection.get('reference_resolution_ratio')}",
        "```",
        "",
        "## Failed required checks",
    ]
    if failed:
        lines.extend(f"- `{c.get('name')}`: {c.get('details') or ''}" for c in failed)
    else:
        lines.append("No failed required checks.")

    lines.extend([
        "",
        "## Coverage",
        "",
        "```text",
        f"paper_nodes_count={summary.get('paper_nodes_count')}",
        f"papers_with_outgoing_reference_edges_count={inspection.get('papers_with_outgoing_reference_edges_count')}",
        f"papers_with_internal_reference_edges_count={inspection.get('papers_with_internal_reference_edges_count')}",
        f"papers_with_external_reference_edges_count={inspection.get('papers_with_external_reference_edges_count')}",
        f"papers_with_reference_source_family_edges_count={inspection.get('papers_with_reference_source_family_edges_count')}",
        f"papers_without_outgoing_reference_edges_count={inspection.get('papers_without_outgoing_reference_edges_count')}",
        "```",
        "",
        "## Top referenced canonical papers",
        "",
    ])
    lines.extend(_format_top(top_referenced, "canonical_id"))
    lines.extend(["", "## Top external references", ""])
    lines.extend(_format_top(top_external, "reference_key"))
    lines.extend([
        "",
        "## Boundary",
        "",
        "This inspection layer is read-only. It does not rebuild graph output, publish anything, change canonical truth, run reconcile, change DB/API/UI/retrieval/Qdrant/ranking behavior, or require NetworkX/Neo4j/GraphRAG runtime.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _default_graph_dir_from_config(config: dict[str, Any]) -> Path:
    outputs = _as_dict(config.get("outputs"))
    raw = outputs.get("expected_future_output_dir") or str(DEFAULT_GRAPH_DIR)
    return Path(str(raw))


def _top_counter(counter: Counter[str], limit: int, key_name: str) -> list[dict[str, Any]]:
    return [{key_name: key, "count": count} for key, count in counter.most_common(limit)]


def inspect_graph(
    *,
    config_path: Path = CONFIG_PATH,
    graph_dir: Path | None = None,
    strict: bool = False,
    write_reports: bool = True,
    report_dir: Path | None = None,
    sample_limit: int = 10,
    top_k: int = 20,
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    checks: list[CheckResult] = []

    try:
        config = _read_yaml(config_path)
        _add_check(checks, "config_readable", True)
    except Exception as exc:
        _add_check(checks, "config_readable", False, str(exc))
        config = {}

    graph_dir = graph_dir or _default_graph_dir_from_config(config)

    _add_check(checks, "graph_dir_exists", graph_dir.exists(), str(graph_dir))
    for name in sorted(REQUIRED_FILES):
        _add_check(checks, f"required_file_exists:{name}", (graph_dir / name).exists())

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    schema: dict[str, Any] = {}
    manifest: dict[str, Any] = {}
    data_quality_summary: dict[str, Any] = {}

    try:
        if (graph_dir / "nodes.jsonl").exists():
            nodes = _read_jsonl(graph_dir / "nodes.jsonl")
        if (graph_dir / "edges.jsonl").exists():
            edges = _read_jsonl(graph_dir / "edges.jsonl")
        if (graph_dir / "schema.json").exists():
            schema = _read_json(graph_dir / "schema.json")
        if (graph_dir / "manifest.json").exists():
            manifest = _read_json(graph_dir / "manifest.json")
        if (graph_dir / "data_quality_summary.json").exists():
            data_quality_summary = _read_json(graph_dir / "data_quality_summary.json")
        _add_check(checks, "graph_files_readable", True)
    except Exception as exc:
        _add_check(checks, "graph_files_readable", False, str(exc))

    node_ids = [str(row.get("node_id")) for row in nodes if row.get("node_id")]
    edge_ids = [str(row.get("edge_id")) for row in edges if row.get("edge_id")]
    node_id_set = set(node_ids)
    edge_id_set = set(edge_ids)

    node_type_counts = Counter(str(row.get("node_type")) for row in nodes)
    edge_type_counts = Counter(str(row.get("edge_type")) for row in edges)
    paper_nodes = {str(row.get("node_id")): row for row in nodes if row.get("node_type") == "paper" and row.get("node_id")}
    external_nodes = {str(row.get("node_id")): row for row in nodes if row.get("node_type") == "external_reference" and row.get("node_id")}
    source_family_nodes = {str(row.get("node_id")): row for row in nodes if row.get("node_type") == "source_family" and row.get("node_id")}

    _add_check(checks, "nodes_non_empty", len(nodes) > 0, f"nodes={len(nodes)}")
    _add_check(checks, "edges_non_empty", len(edges) > 0, f"edges={len(edges)}")
    _add_check(checks, "node_ids_unique", len(node_ids) == len(node_id_set), f"node_ids={len(node_ids)} unique={len(node_id_set)}")
    _add_check(checks, "edge_ids_unique", len(edge_ids) == len(edge_id_set), f"edge_ids={len(edge_ids)} unique={len(edge_id_set)}")
    _add_check(checks, "required_node_types_present", REQUIRED_NODE_TYPES.issubset(set(node_type_counts)), str(dict(node_type_counts)))
    _add_check(checks, "required_edge_types_present", REQUIRED_EDGE_TYPES.issubset(set(edge_type_counts)), str(dict(edge_type_counts)))
    _add_check(checks, "paper_nodes_present", len(paper_nodes) > 0, f"paper_nodes={len(paper_nodes)}")
    _add_check(checks, "external_reference_nodes_present", len(external_nodes) > 0, f"external_reference_nodes={len(external_nodes)}")
    _add_check(checks, "source_family_nodes_present", len(source_family_nodes) > 0, f"source_family_nodes={len(source_family_nodes)}")

    dangling_edges = [
        edge.get("edge_id")
        for edge in edges
        if edge.get("source_node_id") not in node_id_set or edge.get("target_node_id") not in node_id_set
    ]
    _add_check(checks, "edge_endpoints_resolve", not dangling_edges, f"dangling_sample={dangling_edges[:5]}")

    invalid_reference_edge_targets: list[str] = []
    for edge in edges:
        edge_type = edge.get("edge_type")
        target_node_id = str(edge.get("target_node_id"))
        if edge_type == "paper_references_paper" and target_node_id not in paper_nodes:
            invalid_reference_edge_targets.append(str(edge.get("edge_id")))
        elif edge_type == "paper_references_external" and target_node_id not in external_nodes:
            invalid_reference_edge_targets.append(str(edge.get("edge_id")))
        elif edge_type == "paper_has_reference_source_family" and target_node_id not in source_family_nodes:
            invalid_reference_edge_targets.append(str(edge.get("edge_id")))
    _add_check(checks, "edge_type_targets_match_node_types", not invalid_reference_edge_targets, f"invalid_sample={invalid_reference_edge_targets[:5]}")

    manifest_safety = _as_dict(manifest.get("safety"))
    unsafe_flags = [name for name in FALSE_SAFETY_FLAGS if manifest_safety.get(name) is not False]
    _add_check(checks, "manifest_safety_flags_false", not unsafe_flags, f"unsafe_flags={unsafe_flags}")
    _add_check(checks, "manifest_file_first_builder", _as_dict(manifest.get("builder")).get("input_mode") == "file")
    _add_check(checks, "manifest_no_live_db_dependency", _as_dict(manifest.get("builder")).get("live_db_dependency") is False)
    _add_check(checks, "data_quality_summary_ok", _as_dict(data_quality_summary.get("summary")).get("ok") is True)

    schema_node_types = set(_as_dict(schema.get("node_types")).keys())
    schema_edge_types = set(_as_dict(schema.get("edge_types")).keys())
    _add_check(checks, "schema_node_types_cover_required", REQUIRED_NODE_TYPES.issubset(schema_node_types), str(sorted(schema_node_types)))
    _add_check(checks, "schema_edge_types_cover_required", REQUIRED_EDGE_TYPES.issubset(schema_edge_types), str(sorted(schema_edge_types)))

    manifest_counts = _as_dict(manifest.get("counts"))
    _add_check(checks, "manifest_nodes_count_matches", manifest_counts.get("nodes_count") == len(nodes), f"manifest={manifest_counts.get('nodes_count')} actual={len(nodes)}")
    _add_check(checks, "manifest_edges_count_matches", manifest_counts.get("edges_count") == len(edges), f"manifest={manifest_counts.get('edges_count')} actual={len(edges)}")
    _add_check(checks, "manifest_paper_count_matches", manifest_counts.get("paper_nodes_count") == len(paper_nodes), f"manifest={manifest_counts.get('paper_nodes_count')} actual={len(paper_nodes)}")

    outgoing_reference_papers: set[str] = set()
    outgoing_internal_papers: set[str] = set()
    outgoing_external_papers: set[str] = set()
    incoming_internal_papers: set[str] = set()
    source_family_papers: set[str] = set()
    reference_type_counts: Counter[str] = Counter()
    reference_field_counts: Counter[str] = Counter()
    source_family_counts: Counter[str] = Counter()
    top_target_papers: Counter[str] = Counter()
    top_external_refs: Counter[str] = Counter()
    sample_paper_to_paper: list[dict[str, Any]] = []
    sample_paper_to_external: list[dict[str, Any]] = []

    canonical_by_node_id = {node_id: str(row.get("canonical_id")) for node_id, row in paper_nodes.items() if row.get("canonical_id")}
    external_key_by_node_id = {node_id: str(row.get("reference_key")) for node_id, row in external_nodes.items() if row.get("reference_key")}

    for edge in edges:
        edge_type = str(edge.get("edge_type"))
        source_node_id = str(edge.get("source_node_id"))
        target_node_id = str(edge.get("target_node_id"))
        if edge_type in REFERENCE_EDGE_TYPES:
            outgoing_reference_papers.add(source_node_id)
            reference_type = _string_or_none(edge.get("reference_type"))
            reference_field = _string_or_none(edge.get("reference_field"))
            if reference_type:
                reference_type_counts[reference_type] += 1
            if reference_field:
                reference_field_counts[reference_field] += 1
        if edge_type == "paper_references_paper":
            outgoing_internal_papers.add(source_node_id)
            incoming_internal_papers.add(target_node_id)
            target_canonical_id = _string_or_none(edge.get("target_canonical_id")) or canonical_by_node_id.get(target_node_id) or target_node_id
            top_target_papers[target_canonical_id] += 1
            if len(sample_paper_to_paper) < sample_limit:
                sample_paper_to_paper.append(
                    {
                        "source_canonical_id": edge.get("source_canonical_id") or canonical_by_node_id.get(source_node_id),
                        "target_canonical_id": target_canonical_id,
                        "reference_type": edge.get("reference_type"),
                        "reference_field": edge.get("reference_field"),
                    }
                )
        elif edge_type == "paper_references_external":
            outgoing_external_papers.add(source_node_id)
            reference_key = _string_or_none(edge.get("target_reference_key")) or external_key_by_node_id.get(target_node_id) or target_node_id
            top_external_refs[reference_key] += 1
            if len(sample_paper_to_external) < sample_limit:
                sample_paper_to_external.append(
                    {
                        "source_canonical_id": edge.get("source_canonical_id") or canonical_by_node_id.get(source_node_id),
                        "target_reference_key": reference_key,
                        "reference_type": edge.get("reference_type"),
                        "reference_field": edge.get("reference_field"),
                    }
                )
        elif edge_type == "paper_has_reference_source_family":
            source_family_papers.add(source_node_id)
            source_family = _string_or_none(edge.get("source_family")) or target_node_id.replace("source_family:", "")
            source_family_counts[source_family] += 1

    resolved_count = edge_type_counts.get("paper_references_paper", 0)
    unresolved_count = edge_type_counts.get("paper_references_external", 0)
    reference_edges_count = resolved_count + unresolved_count
    resolution_ratio = round(resolved_count / reference_edges_count, 6) if reference_edges_count else 0.0
    papers_without_outgoing = max(0, len(paper_nodes) - len(outgoing_reference_papers))

    _add_check(checks, "reference_edges_present", reference_edges_count > 0, f"reference_edges={reference_edges_count}")
    _add_check(checks, "resolved_reference_edges_present", resolved_count > 0, f"resolved={resolved_count}")
    _add_check(checks, "unresolved_reference_edges_present", unresolved_count > 0, f"unresolved={unresolved_count}")
    _add_check(checks, "source_family_reference_edges_present", edge_type_counts.get("paper_has_reference_source_family", 0) > 0, f"source_family_edges={edge_type_counts.get('paper_has_reference_source_family', 0)}")
    _add_check(checks, "inspection_samples_available", bool(sample_paper_to_paper) and bool(sample_paper_to_external), f"paper_to_paper={len(sample_paper_to_paper)} paper_to_external={len(sample_paper_to_external)}")

    inspection = {
        "graph_dir": str(graph_dir),
        "resolved_reference_edges_count": resolved_count,
        "unresolved_reference_edges_count": unresolved_count,
        "reference_edges_count": reference_edges_count,
        "reference_resolution_ratio": resolution_ratio,
        "papers_with_outgoing_reference_edges_count": len(outgoing_reference_papers),
        "papers_with_internal_reference_edges_count": len(outgoing_internal_papers),
        "papers_with_external_reference_edges_count": len(outgoing_external_papers),
        "papers_with_incoming_internal_reference_edges_count": len(incoming_internal_papers),
        "papers_with_reference_source_family_edges_count": len(source_family_papers),
        "papers_without_outgoing_reference_edges_count": papers_without_outgoing,
        "reference_type_distribution": dict(sorted(reference_type_counts.items())),
        "reference_field_distribution": dict(sorted(reference_field_counts.items())),
        "source_family_distribution": dict(sorted(source_family_counts.items())),
        "top_referenced_papers": _top_counter(top_target_papers, top_k, "canonical_id"),
        "top_external_references": _top_counter(top_external_refs, top_k, "reference_key"),
        "sample_paper_to_paper_edges": sample_paper_to_paper,
        "sample_paper_to_external_edges": sample_paper_to_external,
    }

    required_failed = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    ok = not required_failed

    report_dir = report_dir or Path("artifacts/reports/validation")
    run_ts = _now_ts()
    latest_json = report_dir / f"{REPORT_BASENAME}_latest.json"
    latest_md = report_dir / f"{REPORT_BASENAME}_latest.md"
    history_json = report_dir / "history" / f"{REPORT_BASENAME}_{run_ts}.json"
    history_md = report_dir / "history" / f"{REPORT_BASENAME}_{run_ts}.md"

    summary = {
        "ok": ok,
        "strict": strict,
        "required_failed_count": len(required_failed),
        "warning_count": len(warnings),
        "total_checks": len(checks),
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "paper_nodes_count": len(paper_nodes),
        "external_reference_nodes_count": len(external_nodes),
        "source_family_nodes_count": len(source_family_nodes),
        "paper_references_paper_edges_count": resolved_count,
        "paper_references_external_edges_count": unresolved_count,
        "paper_has_reference_source_family_edges_count": edge_type_counts.get("paper_has_reference_source_family", 0),
    }

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "config_path": str(config_path),
        "graph_dir": str(graph_dir),
        "summary": summary,
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "inspection": inspection,
        "checks": [check.__dict__ for check in checks],
        "failed_required_checks": [check.__dict__ for check in required_failed],
        "report_paths": {
            "latest_json": str(latest_json),
            "latest_md": str(latest_md),
            "history_json": str(history_json),
            "history_md": str(history_md),
        },
        "boundaries": {
            "read_only": True,
            "rebuilds_graph_output": False,
            "changes_canonical_truth": False,
            "runs_reconcile": False,
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
        _write_json(latest_json, report)
        _write_json(history_json, report)
        _write_markdown(latest_md, report)
        _write_markdown(history_md, report)

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect local Citation / Reference Graph v0.1 output.")
    parser.add_argument("--config-path", type=Path, default=CONFIG_PATH)
    parser.add_argument("--graph-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args(argv)

    report = inspect_graph(
        config_path=args.config_path,
        graph_dir=args.graph_dir,
        strict=args.strict,
        write_reports=not args.no_write_reports,
        report_dir=args.report_dir,
        sample_limit=max(0, args.sample_limit),
        top_k=max(1, args.top_k),
    )
    summary = report["summary"]
    print(json.dumps({
        "ok": summary["ok"],
        "required_failed_count": summary["required_failed_count"],
        "total_checks": summary["total_checks"],
        "warning_count": summary["warning_count"],
        "nodes_count": summary["nodes_count"],
        "edges_count": summary["edges_count"],
        "resolved_reference_edges_count": report["inspection"]["resolved_reference_edges_count"],
        "unresolved_reference_edges_count": report["inspection"]["unresolved_reference_edges_count"],
        "reference_resolution_ratio": report["inspection"]["reference_resolution_ratio"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
