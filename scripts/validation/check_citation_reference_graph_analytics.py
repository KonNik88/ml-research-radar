"""Build a read-only analytics report for Citation / Reference Graph v0.1.

This validator/report layer reads the already generated local citation/reference
graph output and summarizes reference coverage, source-family distribution,
resolved/unresolved references, and top reference targets for manual-review
support.

It does not rebuild graph output, rebuild packages, approve manual review,
mutate canonical truth, touch Postgres/Qdrant/retrieval/ranking/API/UI, create a
runtime graph, parse full text/PDFs/bibliographies, or publish anything.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


CONFIG_PATH = Path("configs/citation_reference_graph_analytics.yaml")
SCHEMA_VERSION = "citation_reference_graph_analytics_v1"
CONFIG_SCHEMA_VERSION = "citation_reference_graph_analytics_config_v1"
REPORT_BASENAME = "citation_reference_graph_analytics"

REQUIRED_NODE_TYPES = {"paper", "external_reference", "source_family"}
REQUIRED_EDGE_TYPES = {
    "paper_references_paper",
    "paper_references_external",
    "paper_has_reference_source_family",
}
REFERENCE_EDGE_TYPES = {"paper_references_paper", "paper_references_external"}
FALSE_MANIFEST_SAFETY_FLAGS = {
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
FALSE_CONFIG_SAFETY_FLAGS = {
    "rebuild_graph",
    "rebuild_package",
    "approve_manual_review",
    "mutate_canonical_documents",
    "mutate_reconcile_inputs",
    "mutate_retrieval_artifacts",
    "mutate_qdrant",
    "mutate_postgres",
    "mutate_db_schema",
    "mutate_api",
    "mutate_streamlit",
    "mutate_ranking",
    "publish_dataset",
    "create_latest_pointer",
    "create_graph_runtime",
    "parse_full_text",
    "parse_pdfs",
    "parse_bibliography_sections",
    "may_be_used_as_reconcile_input",
}


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


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _resolve_path(raw: Any, *, config_path: Path) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return (config_path.parent.parent / path).resolve()


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row must be an object at {path}:{line_no}")
            yield payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _make_check(name: str, ok: bool, required: bool, message: str, details: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(name=name, ok=bool(ok), required=required, message=message, details=details)


def _top_counter(counter: Counter[str], limit: int, key_name: str) -> list[dict[str, Any]]:
    return [{key_name: key, "count": count} for key, count in counter.most_common(limit)]


def _report_green(report: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    summary = _as_dict(report.get("summary"))
    verdict = _as_dict(report.get("verdict"))
    ok = summary.get("ok") is True and summary.get("required_failed_count") == 0
    return ok, {
        "schema_version": report.get("schema_version"),
        "summary_ok": summary.get("ok"),
        "required_failed_count": summary.get("required_failed_count"),
        "warning_count": summary.get("warning_count"),
        "manual_review_required": verdict.get("manual_review_required"),
        "manual_review_complete": verdict.get("manual_review_complete"),
        "publication_ready": verdict.get("publication_ready"),
        "publication_block_reason": verdict.get("publication_block_reason"),
    }


def _data_quality_ok(payload: dict[str, Any]) -> bool:
    return payload.get("ok") is True or _as_dict(payload.get("summary")).get("ok") is True


def _reference_key_for_external(edge: dict[str, Any], external_key_by_node_id: dict[str, str]) -> str:
    return (
        _text(edge.get("target_reference_key"))
        or external_key_by_node_id.get(str(edge.get("target_node_id")))
        or str(edge.get("target_node_id"))
    )


def collect_analytics(nodes_path: Path, edges_path: Path, *, sample_limit: int, top_k: int) -> dict[str, Any]:
    node_type_counts: Counter[str] = Counter()
    paper_node_ids: set[str] = set()
    external_node_ids: set[str] = set()
    source_family_node_ids: set[str] = set()
    canonical_by_node_id: dict[str, str] = {}
    external_key_by_node_id: dict[str, str] = {}

    for node in _iter_jsonl(nodes_path):
        node_type = str(node.get("node_type") or "<missing>")
        node_id = _text(node.get("node_id"))
        node_type_counts[node_type] += 1
        if not node_id:
            continue
        if node_type == "paper":
            paper_node_ids.add(node_id)
            canonical_by_node_id[node_id] = _text(node.get("canonical_id")) or node_id.replace("paper:", "")
        elif node_type == "external_reference":
            external_node_ids.add(node_id)
            external_key_by_node_id[node_id] = _text(node.get("reference_key")) or node_id.replace("external_reference:", "")
        elif node_type == "source_family":
            source_family_node_ids.add(node_id)

    edge_type_counts: Counter[str] = Counter()
    reference_type_counts: Counter[str] = Counter()
    reference_field_counts: Counter[str] = Counter()
    source_family_counts: Counter[str] = Counter()
    top_referenced_papers: Counter[str] = Counter()
    top_external_references: Counter[str] = Counter()

    outgoing_reference_papers: set[str] = set()
    outgoing_internal_papers: set[str] = set()
    outgoing_external_papers: set[str] = set()
    incoming_internal_papers: set[str] = set()
    source_family_papers: set[str] = set()

    sample_paper_to_paper: list[dict[str, Any]] = []
    sample_paper_to_external: list[dict[str, Any]] = []
    sample_reference_source_family_edges: list[dict[str, Any]] = []

    for edge in _iter_jsonl(edges_path):
        edge_type = str(edge.get("edge_type") or "<missing>")
        edge_type_counts[edge_type] += 1
        source_node_id = str(edge.get("source_node_id") or "")
        target_node_id = str(edge.get("target_node_id") or "")

        if edge_type in REFERENCE_EDGE_TYPES:
            outgoing_reference_papers.add(source_node_id)
            reference_type = _text(edge.get("reference_type"))
            reference_field = _text(edge.get("reference_field"))
            if reference_type:
                reference_type_counts[reference_type] += 1
            if reference_field:
                reference_field_counts[reference_field] += 1

        if edge_type == "paper_references_paper":
            outgoing_internal_papers.add(source_node_id)
            incoming_internal_papers.add(target_node_id)
            target_canonical_id = _text(edge.get("target_canonical_id")) or canonical_by_node_id.get(target_node_id) or target_node_id
            top_referenced_papers[target_canonical_id] += 1
            if len(sample_paper_to_paper) < sample_limit:
                sample_paper_to_paper.append(
                    {
                        "source_canonical_id": _text(edge.get("source_canonical_id")) or canonical_by_node_id.get(source_node_id),
                        "target_canonical_id": target_canonical_id,
                        "reference_type": edge.get("reference_type"),
                        "reference_field": edge.get("reference_field"),
                    }
                )
        elif edge_type == "paper_references_external":
            outgoing_external_papers.add(source_node_id)
            reference_key = _reference_key_for_external(edge, external_key_by_node_id)
            top_external_references[reference_key] += 1
            if len(sample_paper_to_external) < sample_limit:
                sample_paper_to_external.append(
                    {
                        "source_canonical_id": _text(edge.get("source_canonical_id")) or canonical_by_node_id.get(source_node_id),
                        "target_reference_key": reference_key,
                        "reference_type": edge.get("reference_type"),
                        "reference_field": edge.get("reference_field"),
                    }
                )
        elif edge_type == "paper_has_reference_source_family":
            source_family_papers.add(source_node_id)
            source_family = _text(edge.get("source_family")) or target_node_id.replace("source_family:", "")
            source_family_counts[source_family] += 1
            if len(sample_reference_source_family_edges) < sample_limit:
                sample_reference_source_family_edges.append(
                    {
                        "source_canonical_id": _text(edge.get("source_canonical_id")) or canonical_by_node_id.get(source_node_id),
                        "source_family": source_family,
                    }
                )

    resolved_count = edge_type_counts.get("paper_references_paper", 0)
    unresolved_count = edge_type_counts.get("paper_references_external", 0)
    reference_edges_count = resolved_count + unresolved_count
    resolution_ratio = round(resolved_count / reference_edges_count, 6) if reference_edges_count else 0.0
    papers_without_outgoing = max(0, len(paper_node_ids) - len(outgoing_reference_papers))

    return {
        "counts": {
            "nodes_count": sum(node_type_counts.values()),
            "edges_count": sum(edge_type_counts.values()),
            "node_type_counts": dict(sorted(node_type_counts.items())),
            "edge_type_counts": dict(sorted(edge_type_counts.items())),
            "paper_nodes_count": len(paper_node_ids),
            "external_reference_nodes_count": len(external_node_ids),
            "source_family_nodes_count": len(source_family_node_ids),
            "reference_edges_count": reference_edges_count,
            "resolved_reference_edges_count": resolved_count,
            "unresolved_reference_edges_count": unresolved_count,
            "paper_has_reference_source_family_edges_count": edge_type_counts.get("paper_has_reference_source_family", 0),
            "papers_with_outgoing_reference_edges_count": len(outgoing_reference_papers),
            "papers_with_internal_reference_edges_count": len(outgoing_internal_papers),
            "papers_with_external_reference_edges_count": len(outgoing_external_papers),
            "papers_with_incoming_internal_reference_edges_count": len(incoming_internal_papers),
            "papers_with_reference_source_family_edges_count": len(source_family_papers),
            "papers_without_outgoing_reference_edges_count": papers_without_outgoing,
            "reference_type_count": len(reference_type_counts),
            "reference_field_count": len(reference_field_counts),
            "source_family_count": len(source_family_counts),
        },
        "reference_resolution_ratio": resolution_ratio,
        "reference_type_distribution": dict(reference_type_counts.most_common()),
        "reference_field_distribution": dict(reference_field_counts.most_common()),
        "source_family_distribution": dict(source_family_counts.most_common()),
        "top_referenced_papers": _top_counter(top_referenced_papers, top_k, "canonical_id"),
        "top_external_references": _top_counter(top_external_references, top_k, "reference_key"),
        "samples": {
            "paper_to_paper_edges": sample_paper_to_paper,
            "paper_to_external_edges": sample_paper_to_external,
            "reference_source_family_edges": sample_reference_source_family_edges,
        },
    }


def _expected_actual_counts(analytics: dict[str, Any]) -> dict[str, Any]:
    counts = _as_dict(analytics.get("counts"))
    node_counts = _as_dict(counts.get("node_type_counts"))
    edge_counts = _as_dict(counts.get("edge_type_counts"))
    return {
        "nodes_count": counts.get("nodes_count"),
        "edges_count": counts.get("edges_count"),
        "node_paper_count": node_counts.get("paper"),
        "node_external_reference_count": node_counts.get("external_reference"),
        "node_source_family_count": node_counts.get("source_family"),
        "edge_paper_references_paper_count": edge_counts.get("paper_references_paper"),
        "edge_paper_references_external_count": edge_counts.get("paper_references_external"),
        "edge_paper_has_reference_source_family_count": edge_counts.get("paper_has_reference_source_family"),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    analytics = report["analytics"]
    caveats = report["manual_review_caveats"]
    lines = [
        "# Citation / Reference Graph Analytics",
        "",
        "```text",
        f"ok={summary['ok']}",
        f"required_failed_count={summary['required_failed_count']}",
        f"warning_count={summary['warning_count']}",
        f"total_checks={summary['total_checks']}",
        f"nodes_count={summary['nodes_count']}",
        f"edges_count={summary['edges_count']}",
        f"resolved_reference_edges_count={summary['resolved_reference_edges_count']}",
        f"unresolved_reference_edges_count={summary['unresolved_reference_edges_count']}",
        f"reference_resolution_ratio={summary['reference_resolution_ratio']}",
        "```",
        "",
        "## Manual-review caveats",
        "",
    ]
    for key, value in caveats.items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Reference type distribution", ""])
    for key, value in analytics.get("reference_type_distribution", {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Source-family distribution", ""])
    for key, value in analytics.get("source_family_distribution", {}).items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Top referenced canonical papers", ""])
    for row in analytics.get("top_referenced_papers", [])[:20]:
        lines.append(f"- `{row.get('canonical_id')}`: {row.get('count')}")
    lines.extend(["", "## Top external references", ""])
    for row in analytics.get("top_external_references", [])[:20]:
        lines.append(f"- `{row.get('reference_key')}`: {row.get('count')}")

    lines.extend(["", "## Checks", "", "| Check | Required | Status | Message |", "|---|---:|---|---|"])
    for check in report["checks"]:
        message = str(check["message"]).replace("|", "\\|")
        lines.append(f"| `{check['name']}` | `{check['required']}` | `{check['status']}` | {message} |")

    lines.extend([
        "",
        "## Boundary",
        "",
        "This analytics layer is read-only. It does not rebuild graph output, rebuild packages, approve manual review, publish anything, change canonical truth, run reconcile, change DB/API/UI/retrieval/Qdrant/ranking behavior, require NetworkX/Neo4j/GraphRAG runtime, or parse full text/PDFs/bibliographies.",
        "",
    ])
    return "\n".join(lines)


def _write_reports(report: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir = report_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    run_ts = _now_ts()
    latest_json = report_dir / f"{REPORT_BASENAME}_latest.json"
    latest_md = report_dir / f"{REPORT_BASENAME}_latest.md"
    history_json = history_dir / f"{REPORT_BASENAME}_{run_ts}.json"
    history_md = history_dir / f"{REPORT_BASENAME}_{run_ts}.md"
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    md_text = _render_markdown(report)
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(md_text, encoding="utf-8")


def validate_graph_analytics(
    *,
    config_path: Path = CONFIG_PATH,
    report_dir: Path | None = None,
    strict: bool = False,
    write_reports: bool = True,
    sample_limit: int = 10,
    top_k: int = 25,
) -> dict[str, Any]:
    config = _read_yaml(config_path)
    checks: list[CheckResult] = []

    checks.append(
        _make_check(
            "config_schema",
            config.get("schema_version") == CONFIG_SCHEMA_VERSION,
            True,
            "Analytics config schema is correct"
            if config.get("schema_version") == CONFIG_SCHEMA_VERSION
            else "Analytics config schema is incorrect",
            {"schema_version": config.get("schema_version")},
        )
    )

    analytics_meta = _as_dict(config.get("analytics"))
    analytics_expected = {
        "name": "citation_reference_graph_analytics",
        "version": "v0.1",
        "status": "local_read_only_analytics",
        "graph_version": "v0.1",
        "publication_ready": False,
        "manual_review_support": True,
        "may_be_used_as_reconcile_input": False,
    }
    metadata_mismatches = {
        key: {"expected": expected, "actual": analytics_meta.get(key)}
        for key, expected in analytics_expected.items()
        if analytics_meta.get(key) is not expected if isinstance(expected, bool)
    }
    for key, expected in analytics_expected.items():
        if isinstance(expected, bool):
            continue
        if analytics_meta.get(key) != expected:
            metadata_mismatches[key] = {"expected": expected, "actual": analytics_meta.get(key)}
    checks.append(
        _make_check(
            "analytics_metadata",
            not metadata_mismatches,
            True,
            "Analytics metadata preserves read-only review-support boundaries"
            if not metadata_mismatches
            else "Analytics metadata is inconsistent",
            {"mismatches": metadata_mismatches},
        )
    )

    safety = _as_dict(config.get("safety"))
    safety_mismatches = {
        key: {"expected": False, "actual": safety.get(key)}
        for key in sorted(FALSE_CONFIG_SAFETY_FLAGS)
        if safety.get(key) is not False
    }
    if safety.get("read_only_analytics") is not True:
        safety_mismatches["read_only_analytics"] = {"expected": True, "actual": safety.get("read_only_analytics")}
    checks.append(
        _make_check(
            "analytics_safety_config",
            not safety_mismatches,
            True,
            "Analytics safety flags preserve project boundaries"
            if not safety_mismatches
            else "Analytics safety flags do not preserve project boundaries",
            {"mismatches": safety_mismatches},
        )
    )

    inputs = _as_dict(config.get("inputs"))
    required_input_keys = ["nodes_path", "edges_path", "manifest_path", "data_quality_summary_path", "manual_review_report"]
    paths: dict[str, Path] = {}
    missing_input_keys = [key for key in required_input_keys if not inputs.get(key)]
    for key in required_input_keys:
        if inputs.get(key):
            paths[key] = _resolve_path(inputs[key], config_path=config_path)
    missing_input_files = [
        _normalize_path(path)
        for path in paths.values()
        if not path.exists()
    ]
    checks.append(
        _make_check(
            "required_inputs_exist",
            not missing_input_keys and not missing_input_files,
            True,
            "Required analytics inputs are configured and present"
            if not missing_input_keys and not missing_input_files
            else "Required analytics inputs are missing",
            {"missing_input_keys": missing_input_keys, "missing_input_files": missing_input_files},
        )
    )

    manifest: dict[str, Any] = {}
    data_quality_summary: dict[str, Any] = {}
    manual_review_report: dict[str, Any] = {}
    analytics: dict[str, Any] = {
        "counts": {},
        "reference_resolution_ratio": 0.0,
        "reference_type_distribution": {},
        "reference_field_distribution": {},
        "source_family_distribution": {},
        "top_referenced_papers": [],
        "top_external_references": [],
        "samples": {},
    }

    if not missing_input_keys and not missing_input_files:
        try:
            manifest = _read_json(paths["manifest_path"])
            data_quality_summary = _read_json(paths["data_quality_summary_path"])
            manual_review_report = _read_json(paths["manual_review_report"])
            analytics = collect_analytics(
                paths["nodes_path"],
                paths["edges_path"],
                sample_limit=max(0, sample_limit),
                top_k=max(1, top_k),
            )
            checks.append(_make_check("analytics_inputs_readable", True, True, "Analytics inputs are readable"))
        except Exception as exc:  # noqa: BLE001
            checks.append(_make_check("analytics_inputs_readable", False, True, f"Failed to read analytics inputs: {exc}"))

    if manifest:
        graph_identity = _as_dict(manifest.get("graph"))
        checks.append(
            _make_check(
                "manifest_identity",
                manifest.get("schema_version") == "citation_reference_graph_manifest_v1"
                and graph_identity.get("name") == "citation_reference_graph"
                and graph_identity.get("version") == "v0.1",
                True,
                "Manifest identity matches Citation / Reference Graph v0.1",
                {"schema_version": manifest.get("schema_version"), "graph": graph_identity},
            )
        )
        manifest_safety = _as_dict(manifest.get("safety"))
        builder = _as_dict(manifest.get("builder"))
        manifest_safety_mismatches = {
            key: {"expected": False, "actual": manifest_safety.get(key)}
            for key in sorted(FALSE_MANIFEST_SAFETY_FLAGS)
            if manifest_safety.get(key) is not False
        }
        if manifest_safety.get("canonical_truth_impact") != "none":
            manifest_safety_mismatches["canonical_truth_impact"] = {
                "expected": "none",
                "actual": manifest_safety.get("canonical_truth_impact"),
            }
        if builder.get("input_mode") != "file":
            manifest_safety_mismatches["builder.input_mode"] = {"expected": "file", "actual": builder.get("input_mode")}
        if builder.get("live_db_dependency") is not False:
            manifest_safety_mismatches["builder.live_db_dependency"] = {
                "expected": False,
                "actual": builder.get("live_db_dependency"),
            }
        checks.append(
            _make_check(
                "manifest_safety_flags",
                not manifest_safety_mismatches,
                True,
                "Manifest safety flags preserve derived-layer boundaries"
                if not manifest_safety_mismatches
                else "Manifest safety flags do not preserve derived-layer boundaries",
                {"mismatches": manifest_safety_mismatches},
            )
        )

    if data_quality_summary:
        checks.append(
            _make_check(
                "data_quality_summary_ok",
                _data_quality_ok(data_quality_summary),
                True,
                "Data quality summary is ok" if _data_quality_ok(data_quality_summary) else "Data quality summary is not ok",
                {"summary": _as_dict(data_quality_summary.get("summary")), "ok": data_quality_summary.get("ok")},
            )
        )

    if manual_review_report:
        report_ok, report_details = _report_green(manual_review_report)
        publication_blocked = report_details.get("manual_review_required") is True and report_details.get("publication_ready") is False
        checks.append(
            _make_check(
                "manual_review_report_green",
                report_ok and publication_blocked,
                True,
                "Manual-review report is green and publication-blocked"
                if report_ok and publication_blocked
                else "Manual-review report is not green or not publication-blocked",
                report_details,
            )
        )

    counts = _as_dict(analytics.get("counts"))
    node_types = set(_as_dict(counts.get("node_type_counts")).keys())
    edge_types = set(_as_dict(counts.get("edge_type_counts")).keys())
    checks.append(
        _make_check(
            "required_node_types_present",
            REQUIRED_NODE_TYPES.issubset(node_types),
            True,
            "Required node types are present" if REQUIRED_NODE_TYPES.issubset(node_types) else "Required node types are missing",
            {"expected": sorted(REQUIRED_NODE_TYPES), "actual": sorted(node_types)},
        )
    )
    checks.append(
        _make_check(
            "required_edge_types_present",
            REQUIRED_EDGE_TYPES.issubset(edge_types),
            True,
            "Required edge types are present" if REQUIRED_EDGE_TYPES.issubset(edge_types) else "Required edge types are missing",
            {"expected": sorted(REQUIRED_EDGE_TYPES), "actual": sorted(edge_types)},
        )
    )

    expected_counts = {str(key): int(value) for key, value in _as_dict(config.get("expected_counts")).items()}
    actual_counts = _expected_actual_counts(analytics)
    count_mismatches = {
        key: {"expected": expected, "actual": actual_counts.get(key)}
        for key, expected in expected_counts.items()
        if actual_counts.get(key) != expected
    }
    checks.append(
        _make_check(
            "accepted_graph_counts",
            not count_mismatches,
            True,
            "Graph counters match accepted post-normalization v0.1 baseline"
            if not count_mismatches
            else "Graph counters differ from accepted post-normalization v0.1 baseline",
            {"mismatches": count_mismatches, "actual_counts": actual_counts},
        )
    )

    expected_analytics = _as_dict(config.get("expected_analytics"))
    expected_ratio = expected_analytics.get("reference_resolution_ratio")
    ratio_matches = expected_ratio is None or abs(float(analytics.get("reference_resolution_ratio") or 0.0) - float(expected_ratio)) < 1e-9
    checks.append(
        _make_check(
            "reference_resolution_ratio_matches",
            ratio_matches,
            True,
            "Reference resolution ratio matches accepted baseline"
            if ratio_matches
            else "Reference resolution ratio differs from accepted baseline",
            {"expected": expected_ratio, "actual": analytics.get("reference_resolution_ratio")},
        )
    )

    analytic_thresholds = {
        "resolved_reference_edges_count": counts.get("resolved_reference_edges_count"),
        "unresolved_reference_edges_count": counts.get("unresolved_reference_edges_count"),
        "papers_with_outgoing_reference_edges_count": counts.get("papers_with_outgoing_reference_edges_count"),
        "papers_with_internal_reference_edges_count": counts.get("papers_with_internal_reference_edges_count"),
        "papers_with_external_reference_edges_count": counts.get("papers_with_external_reference_edges_count"),
        "papers_with_incoming_internal_reference_edges_count": counts.get("papers_with_incoming_internal_reference_edges_count"),
        "reference_type_count": counts.get("reference_type_count"),
        "reference_field_count": counts.get("reference_field_count"),
        "source_family_count": counts.get("source_family_count"),
    }
    minimum_expectations = {
        "min_papers_with_outgoing_reference_edges_count": "papers_with_outgoing_reference_edges_count",
        "min_papers_with_internal_reference_edges_count": "papers_with_internal_reference_edges_count",
        "min_papers_with_external_reference_edges_count": "papers_with_external_reference_edges_count",
        "min_papers_with_incoming_internal_reference_edges_count": "papers_with_incoming_internal_reference_edges_count",
        "min_reference_type_count": "reference_type_count",
        "min_reference_field_count": "reference_field_count",
        "min_source_family_count": "source_family_count",
    }
    threshold_mismatches: dict[str, Any] = {}
    for expected_key, actual_key in minimum_expectations.items():
        expected_min = expected_analytics.get(expected_key)
        if expected_min is None:
            continue
        actual_value = analytic_thresholds.get(actual_key) or 0
        if int(actual_value) < int(expected_min):
            threshold_mismatches[actual_key] = {"expected_min": expected_min, "actual": actual_value}
    for exact_key in ("resolved_reference_edges_count", "unresolved_reference_edges_count"):
        if expected_analytics.get(exact_key) is None:
            continue
        actual_value = analytic_thresholds.get(exact_key)
        if actual_value != expected_analytics.get(exact_key):
            threshold_mismatches[exact_key] = {"expected": expected_analytics.get(exact_key), "actual": actual_value}
    checks.append(
        _make_check(
            "expected_analytics_baseline",
            not threshold_mismatches,
            True,
            "Analytics baseline expectations pass" if not threshold_mismatches else "Analytics baseline expectations failed",
            {"mismatches": threshold_mismatches, "actual": analytic_thresholds},
        )
    )

    reference_type_distribution = _as_dict(analytics.get("reference_type_distribution"))
    required_reference_types = {str(item) for item in _as_list(expected_analytics.get("required_reference_types"))}
    missing_reference_types = sorted(item for item in required_reference_types if reference_type_distribution.get(item, 0) <= 0)
    checks.append(
        _make_check(
            "required_reference_types_present",
            not missing_reference_types,
            True,
            "Required reference types are present" if not missing_reference_types else "Required reference types are missing",
            {"missing": missing_reference_types, "distribution": reference_type_distribution},
        )
    )

    source_family_distribution = _as_dict(analytics.get("source_family_distribution"))
    required_source_families = {str(item) for item in _as_list(expected_analytics.get("required_source_families"))}
    missing_source_families = sorted(item for item in required_source_families if source_family_distribution.get(item, 0) <= 0)
    checks.append(
        _make_check(
            "required_source_families_present",
            not missing_source_families,
            True,
            "Required source families are present" if not missing_source_families else "Required source families are missing",
            {"missing": missing_source_families, "distribution": source_family_distribution},
        )
    )

    samples = _as_dict(analytics.get("samples"))
    samples_ok = bool(samples.get("paper_to_paper_edges")) and bool(samples.get("paper_to_external_edges"))
    checks.append(
        _make_check(
            "inspection_samples_available",
            samples_ok,
            True,
            "Internal and external reference samples are available"
            if samples_ok
            else "Internal or external reference samples are missing",
            {
                "paper_to_paper_sample_count": len(_as_list(samples.get("paper_to_paper_edges"))),
                "paper_to_external_sample_count": len(_as_list(samples.get("paper_to_external_edges"))),
            },
        )
    )

    caveats = _as_dict(config.get("manual_review_caveats"))
    caveat_expected = {
        "metadata_reference_fields_only": True,
        "full_text_parsed": False,
        "pdfs_parsed": False,
        "bibliography_sections_parsed": False,
        "raw_reference_strings_without_identifiers_parsed": False,
        "unresolved_references_preserved_as_external_reference_nodes": True,
        "low_resolution_ratio_expected_in_v0_1": True,
    }
    caveat_mismatches: dict[str, Any] = {
        key: {"expected": expected, "actual": caveats.get(key)}
        for key, expected in caveat_expected.items()
        if caveats.get(key) is not expected
    }
    caveat_ratio = caveats.get("reference_resolution_ratio")
    if caveat_ratio is None or abs(float(caveat_ratio) - float(analytics.get("reference_resolution_ratio") or 0.0)) > 1e-9:
        caveat_mismatches["reference_resolution_ratio"] = {
            "expected": analytics.get("reference_resolution_ratio"),
            "actual": caveat_ratio,
        }
    checks.append(
        _make_check(
            "manual_review_caveats",
            not caveat_mismatches,
            True,
            "Manual-review caveats preserve citation/reference graph limitations"
            if not caveat_mismatches
            else "Manual-review caveats are inconsistent",
            {"mismatches": caveat_mismatches},
        )
    )

    required_failed = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    ok = not required_failed

    report_dir = report_dir or _resolve_path(_as_dict(config.get("validation")).get("report_dir", "artifacts/reports/validation"), config_path=config_path)
    summary = {
        "ok": ok,
        "strict": strict,
        "required_failed_count": len(required_failed),
        "warning_count": len(warnings),
        "total_checks": len(checks),
        "nodes_count": counts.get("nodes_count"),
        "edges_count": counts.get("edges_count"),
        "paper_nodes_count": counts.get("paper_nodes_count"),
        "external_reference_nodes_count": counts.get("external_reference_nodes_count"),
        "source_family_nodes_count": counts.get("source_family_nodes_count"),
        "resolved_reference_edges_count": counts.get("resolved_reference_edges_count"),
        "unresolved_reference_edges_count": counts.get("unresolved_reference_edges_count"),
        "paper_has_reference_source_family_edges_count": counts.get("paper_has_reference_source_family_edges_count"),
        "reference_resolution_ratio": analytics.get("reference_resolution_ratio"),
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "config_path": _normalize_path(config_path),
        "summary": summary,
        "analytics": analytics,
        "manual_review_caveats": caveats,
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
            "analytics_report_valid": ok,
            "manual_review_support": True,
            "manual_review_required": True,
            "manual_review_complete_changed": False,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "required_failed_checks": [check.name for check in required_failed],
            "warning_checks": [check.name for check in warnings],
        },
        "boundaries": {
            "read_only_analytics": True,
            "rebuilds_graph": False,
            "rebuilds_package": False,
            "approves_manual_review": False,
            "mutates_canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "changes_postgres": False,
            "changes_db_schema": False,
            "changes_api": False,
            "changes_streamlit": False,
            "changes_retrieval": False,
            "changes_qdrant": False,
            "changes_ranking": False,
            "publishes_dataset": False,
            "creates_graph_runtime": False,
            "parses_full_text": False,
            "parses_pdfs": False,
            "parses_bibliography_sections": False,
        },
    }

    if write_reports:
        _write_reports(report, report_dir)

    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Citation / Reference Graph analytics report layer.")
    parser.add_argument("--config", "--config-path", dest="config_path", type=Path, default=CONFIG_PATH)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=25)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = validate_graph_analytics(
        config_path=args.config_path,
        report_dir=args.report_dir,
        strict=args.strict,
        write_reports=not args.no_write_reports,
        sample_limit=args.sample_limit,
        top_k=args.top_k,
    )
    summary = report["summary"]
    print(json.dumps(
        {
            "ok": summary["ok"],
            "required_failed_count": summary["required_failed_count"],
            "strict": summary["strict"],
            "total_checks": summary["total_checks"],
            "warning_count": summary["warning_count"],
            "nodes_count": summary["nodes_count"],
            "edges_count": summary["edges_count"],
            "resolved_reference_edges_count": summary["resolved_reference_edges_count"],
            "unresolved_reference_edges_count": summary["unresolved_reference_edges_count"],
            "reference_resolution_ratio": summary["reference_resolution_ratio"],
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    if not summary["ok"]:
        print("required_failed_checks:", ", ".join(report["verdict"]["required_failed_checks"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
