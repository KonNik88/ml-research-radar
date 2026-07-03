from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path("configs/paper_artifact_graph_analytics.yaml")
SCHEMA_VERSION = "paper_artifact_graph_analytics_v1"
CONFIG_SCHEMA_VERSION = "paper_artifact_graph_analytics_config_v1"
REPORT_BASENAME = "paper_artifact_graph_analytics"

REQUIRED_NODE_TYPES = {"paper", "artifact", "provider", "source_family", "topic_cluster"}
REQUIRED_EDGE_TYPES = {
    "paper_has_artifact",
    "artifact_from_provider",
    "paper_observed_in_source_family",
    "paper_assigned_to_topic_cluster",
}
ALLOWED_FALSE_SAFETY_FLAGS = {
    "rebuild_graph",
    "rebuild_package",
    "mutate_canonical_documents",
    "mutate_artifact_inputs",
    "mutate_topic_inputs",
    "mutate_retrieval_artifacts",
    "mutate_qdrant",
    "mutate_postgres",
    "mutate_api",
    "mutate_ui",
    "mutate_ranking",
    "publish_dataset",
    "create_latest_pointer",
    "create_graph_runtime",
    "may_be_used_as_reconcile_input",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool = True
    details: str | None = None


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be an object: {path}:{line_no}")
            rows.append(row)
    return rows


def _resolve_path(path: str | Path, *, config_path: Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    # Config files live under configs/. Relative paths are repo-root-relative in this project.
    return (config_path.parent.parent / p).resolve()


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _manifest_flag(manifest: dict[str, Any], key: str) -> Any:
    if key in manifest:
        return manifest.get(key)
    graph = manifest.get("graph")
    if isinstance(graph, dict) and key in graph:
        return graph.get(key)
    package = manifest.get("package")
    if isinstance(package, dict) and key in package:
        return package.get(key)
    return None


def _row_properties(row: dict[str, Any]) -> dict[str, Any]:
    props = row.get("properties")
    return props if isinstance(props, dict) else {}


def _provider_from_artifact_node(row: dict[str, Any]) -> str:
    props = _row_properties(row)
    provider = props.get("provider") or row.get("provider")
    if provider is None:
        return "unknown"
    text = str(provider).strip().lower()
    return text or "unknown"


def _source_family_from_node_id(node_id: str) -> str:
    prefix = "source_family:"
    return node_id[len(prefix):] if node_id.startswith(prefix) else node_id


def _topic_from_node_id(node_id: str) -> str:
    prefix = "topic_cluster:"
    return node_id[len(prefix):] if node_id.startswith(prefix) else node_id


def _compute_graph_analytics(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    nodes_by_id = {str(row.get("node_id")): row for row in nodes if row.get("node_id")}
    node_type_counts = Counter(str(row.get("node_type")) for row in nodes)
    edge_type_counts = Counter(str(row.get("edge_type")) for row in edges)

    artifact_provider: dict[str, str] = {}
    for row in nodes:
        if row.get("node_type") == "artifact":
            artifact_provider[str(row.get("node_id"))] = _provider_from_artifact_node(row)

    paper_artifact_edges = [row for row in edges if row.get("edge_type") == "paper_has_artifact"]
    topic_edges = [row for row in edges if row.get("edge_type") == "paper_assigned_to_topic_cluster"]
    source_family_edges = [row for row in edges if row.get("edge_type") == "paper_observed_in_source_family"]

    paper_to_artifacts: dict[str, set[str]] = defaultdict(set)
    artifact_to_papers: dict[str, set[str]] = defaultdict(set)
    provider_link_counts: Counter[str] = Counter()
    for edge in paper_artifact_edges:
        paper = str(edge.get("source_node_id"))
        artifact = str(edge.get("target_node_id"))
        paper_to_artifacts[paper].add(artifact)
        artifact_to_papers[artifact].add(paper)
        provider_link_counts[artifact_provider.get(artifact, "unknown")] += 1

    provider_artifact_counts: Counter[str] = Counter(artifact_provider.values())

    paper_to_topics: dict[str, set[str]] = defaultdict(set)
    topic_to_papers: dict[str, set[str]] = defaultdict(set)
    for edge in topic_edges:
        paper = str(edge.get("source_node_id"))
        topic = _topic_from_node_id(str(edge.get("target_node_id")))
        paper_to_topics[paper].add(topic)
        topic_to_papers[topic].add(paper)

    source_family_counts: Counter[str] = Counter()
    for edge in source_family_edges:
        source_family_counts[_source_family_from_node_id(str(edge.get("target_node_id")))] += 1

    papers_with_artifacts = set(paper_to_artifacts)
    topic_rows = []
    for topic, papers in topic_to_papers.items():
        ready_papers = papers & papers_with_artifacts
        ready_artifacts = set()
        ready_links = 0
        for paper in ready_papers:
            paper_artifacts = paper_to_artifacts.get(paper, set())
            ready_artifacts.update(paper_artifacts)
            ready_links += len(paper_artifacts)
        topic_rows.append(
            {
                "topic_cluster": topic,
                "papers_count": len(papers),
                "artifact_ready_papers_count": len(ready_papers),
                "artifacts_count": len(ready_artifacts),
                "paper_artifact_links_count": ready_links,
                "artifact_ready_ratio": round(len(ready_papers) / len(papers), 6) if papers else 0.0,
            }
        )
    topic_rows.sort(key=lambda r: (-r["artifact_ready_papers_count"], str(r["topic_cluster"])))

    multi_paper_artifacts = [
        {"artifact_node_id": artifact, "linked_papers_count": len(papers), "provider": artifact_provider.get(artifact, "unknown")}
        for artifact, papers in artifact_to_papers.items()
        if len(papers) > 1
    ]
    multi_paper_artifacts.sort(key=lambda r: (-r["linked_papers_count"], r["artifact_node_id"]))

    isolated_artifacts_count = max(0, node_type_counts.get("artifact", 0) - len(artifact_to_papers))

    return {
        "counts": {
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "node_type_counts": dict(sorted(node_type_counts.items())),
            "edge_type_counts": dict(sorted(edge_type_counts.items())),
            "papers_with_artifacts_count": len(papers_with_artifacts),
            "artifacts_with_linked_papers_count": len(artifact_to_papers),
            "multi_paper_artifacts_count": len(multi_paper_artifacts),
            "isolated_artifacts_count": isolated_artifacts_count,
            "topic_clusters_count": len(topic_to_papers),
            "topic_clusters_with_artifact_ready_papers_count": sum(1 for row in topic_rows if row["artifact_ready_papers_count"] > 0),
            "provider_count": len(provider_artifact_counts),
            "source_family_count": len(source_family_counts),
        },
        "provider_distribution": {
            "artifact_nodes": dict(provider_artifact_counts.most_common()),
            "paper_artifact_links": dict(provider_link_counts.most_common()),
        },
        "source_family_distribution": dict(source_family_counts.most_common()),
        "topic_cluster_artifact_coverage": topic_rows,
        "top_multi_paper_artifacts": multi_paper_artifacts[:25],
        "samples": {
            "paper_with_artifacts": sorted(papers_with_artifacts)[:10],
            "artifact_with_papers": sorted(artifact_to_papers)[:10],
            "topic_clusters_with_artifacts": [row["topic_cluster"] for row in topic_rows if row["artifact_ready_papers_count"] > 0][:10],
        },
        "node_ids_seen": set(nodes_by_id),  # internal convenience; removed before serialization
    }


def _check_expected_counts(analytics: dict[str, Any], expected_counts: dict[str, Any]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    counts = analytics["counts"]
    node_counts = counts["node_type_counts"]
    edge_counts = counts["edge_type_counts"]
    mapping = {
        "nodes_count": counts.get("nodes_count"),
        "edges_count": counts.get("edges_count"),
        "node_paper_count": node_counts.get("paper", 0),
        "node_artifact_count": node_counts.get("artifact", 0),
        "node_provider_count": node_counts.get("provider", 0),
        "node_source_family_count": node_counts.get("source_family", 0),
        "node_topic_cluster_count": node_counts.get("topic_cluster", 0),
        "edge_paper_has_artifact_count": edge_counts.get("paper_has_artifact", 0),
        "edge_artifact_from_provider_count": edge_counts.get("artifact_from_provider", 0),
        "edge_paper_observed_in_source_family_count": edge_counts.get("paper_observed_in_source_family", 0),
        "edge_paper_assigned_to_topic_cluster_count": edge_counts.get("paper_assigned_to_topic_cluster", 0),
    }
    for key, expected in sorted(expected_counts.items()):
        if key not in mapping:
            continue
        actual = mapping[key]
        checks.append(
            CheckResult(
                name=f"expected_{key}_matches",
                ok=actual == expected,
                details=f"expected={expected}; actual={actual}",
            )
        )
    return checks


def _check_expected_analytics(analytics: dict[str, Any], expected: dict[str, Any]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    counts = analytics["counts"]
    min_mapping = {
        "min_papers_with_artifacts_count": counts.get("papers_with_artifacts_count", 0),
        "min_artifacts_with_linked_papers_count": counts.get("artifacts_with_linked_papers_count", 0),
        "min_provider_count": counts.get("provider_count", 0),
        "min_topic_clusters_with_artifact_ready_papers_count": counts.get("topic_clusters_with_artifact_ready_papers_count", 0),
    }
    for key, actual in min_mapping.items():
        if key not in expected:
            continue
        minimum = int(expected[key])
        checks.append(CheckResult(name=key, ok=actual >= minimum, details=f"minimum={minimum}; actual={actual}"))

    smoke = expected.get("required_provider_smoke")
    if isinstance(smoke, dict):
        provider = str(smoke.get("provider", "")).lower()
        artifacts = analytics["provider_distribution"]["artifact_nodes"].get(provider, 0)
        links = analytics["provider_distribution"]["paper_artifact_links"].get(provider, 0)
        min_artifacts = int(smoke.get("min_artifacts", 1))
        min_links = int(smoke.get("min_paper_artifact_links", 1))
        checks.append(
            CheckResult(
                name="provider_smoke_artifacts_minimum",
                ok=artifacts >= min_artifacts,
                details=f"provider={provider}; minimum={min_artifacts}; actual={artifacts}",
            )
        )
        checks.append(
            CheckResult(
                name="provider_smoke_links_minimum",
                ok=links >= min_links,
                details=f"provider={provider}; minimum={min_links}; actual={links}",
            )
        )
    return checks


def _report_from_checks(*, config: dict[str, Any], config_path: Path, checks: list[CheckResult], analytics: dict[str, Any], strict: bool) -> dict[str, Any]:
    required_failed = [check.name for check in checks if check.required and not check.ok]
    warnings = [check.name for check in checks if not check.required and not check.ok]
    run_ts = _now_ts()
    serializable_analytics = dict(analytics)
    serializable_analytics.pop("node_ids_seen", None)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_ts": run_ts,
        "config_path": str(config_path),
        "summary": {
            "ok": not required_failed,
            "required_failed_count": len(required_failed),
            "warning_count": len(warnings),
            "total_checks": len(checks),
            "strict": strict,
        },
        "verdict": {
            "paper_artifact_graph_analytics_ready": not required_failed,
            "manual_review_support": True,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "required_failed_checks": required_failed,
            "warning_checks": warnings,
        },
        "analytics": serializable_analytics,
        "checks": [check.__dict__ for check in checks],
        "boundaries": {
            "read_only_analytics": True,
            "rebuilds_graph": False,
            "rebuilds_package": False,
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
        "config_summary": {
            "analytics": config.get("analytics", {}),
            "inputs": config.get("inputs", {}),
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    verdict = report["verdict"]
    counts = report["analytics"]["counts"]
    provider_links = report["analytics"]["provider_distribution"]["paper_artifact_links"]
    top_topics = report["analytics"]["topic_cluster_artifact_coverage"][:10]
    lines = [
        "# Paper-Artifact Graph Analytics v0.1",
        "",
        f"- ok: `{summary['ok']}`",
        f"- required_failed_count: `{summary['required_failed_count']}`",
        f"- warning_count: `{summary['warning_count']}`",
        f"- publication_ready: `{verdict['publication_ready']}`",
        f"- publication_block_reason: `{verdict['publication_block_reason']}`",
        "",
        "## Core counts",
        "",
        f"- nodes: `{counts['nodes_count']}`",
        f"- edges: `{counts['edges_count']}`",
        f"- papers with artifacts: `{counts['papers_with_artifacts_count']}`",
        f"- artifacts with linked papers: `{counts['artifacts_with_linked_papers_count']}`",
        f"- multi-paper artifacts: `{counts['multi_paper_artifacts_count']}`",
        f"- topic clusters with artifact-ready papers: `{counts['topic_clusters_with_artifact_ready_papers_count']}`",
        "",
        "## Provider paper-artifact links",
        "",
    ]
    if provider_links:
        for provider, count in list(provider_links.items())[:15]:
            lines.append(f"- `{provider}`: `{count}`")
    else:
        lines.append("No provider link counts found.")
    lines.extend(["", "## Top topic clusters by artifact-ready papers", ""])
    if top_topics:
        for row in top_topics:
            lines.append(
                "- `topic_cluster={}`: papers=`{}`, artifact_ready_papers=`{}`, links=`{}`, ratio=`{}`".format(
                    row["topic_cluster"],
                    row["papers_count"],
                    row["artifact_ready_papers_count"],
                    row["paper_artifact_links_count"],
                    row["artifact_ready_ratio"],
                )
            )
    else:
        lines.append("No topic coverage rows found.")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "This report is read-only operational evidence. It does not publish the graph, rebuild graph/package outputs, change canonical truth, or create runtime/API/UI behavior.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def validate_graph_analytics(
    *,
    config_path: Path = CONFIG_PATH,
    strict: bool = False,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = _read_yaml(config_path)
    checks: list[CheckResult] = []
    checks.append(CheckResult("config_schema_version", config.get("schema_version") == CONFIG_SCHEMA_VERSION))

    analytics_meta = config.get("analytics") if isinstance(config.get("analytics"), dict) else {}
    checks.append(CheckResult("analytics_status_read_only", analytics_meta.get("status") == "local_read_only_analytics"))
    checks.append(CheckResult("analytics_not_publication_ready", analytics_meta.get("publication_ready") is False))
    checks.append(CheckResult("analytics_not_reconcile_input", analytics_meta.get("may_be_used_as_reconcile_input") is False))

    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    checks.append(CheckResult("safety_read_only_analytics_true", safety.get("read_only_analytics") is True))
    unsafe_flags = [flag for flag in sorted(ALLOWED_FALSE_SAFETY_FLAGS) if safety.get(flag) is not False]
    checks.append(CheckResult("safety_flags_all_false", not unsafe_flags, details=", ".join(unsafe_flags) or None))

    inputs = config.get("inputs") if isinstance(config.get("inputs"), dict) else {}
    graph_dir = _resolve_path(inputs.get("graph_dir", "data/graphs/paper_artifact_graph/v0.1"), config_path=config_path)
    nodes_path = _resolve_path(inputs.get("nodes_path", graph_dir / "nodes.jsonl"), config_path=config_path)
    edges_path = _resolve_path(inputs.get("edges_path", graph_dir / "edges.jsonl"), config_path=config_path)
    manifest_path = _resolve_path(inputs.get("manifest_path", graph_dir / "manifest.json"), config_path=config_path)
    quality_path = _resolve_path(inputs.get("data_quality_summary_path", graph_dir / "data_quality_summary.json"), config_path=config_path)

    paths = {
        "graph_dir_exists": graph_dir,
        "nodes_path_exists": nodes_path,
        "edges_path_exists": edges_path,
        "manifest_path_exists": manifest_path,
        "data_quality_summary_path_exists": quality_path,
    }
    for name, path in paths.items():
        checks.append(CheckResult(name, path.exists(), details=str(path)))

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {}
    quality: dict[str, Any] = {}
    analytics: dict[str, Any] = {
        "counts": {
            "nodes_count": 0,
            "edges_count": 0,
            "node_type_counts": {},
            "edge_type_counts": {},
            "papers_with_artifacts_count": 0,
            "artifacts_with_linked_papers_count": 0,
            "multi_paper_artifacts_count": 0,
            "isolated_artifacts_count": 0,
            "topic_clusters_count": 0,
            "topic_clusters_with_artifact_ready_papers_count": 0,
            "provider_count": 0,
            "source_family_count": 0,
        },
        "provider_distribution": {"artifact_nodes": {}, "paper_artifact_links": {}},
        "source_family_distribution": {},
        "topic_cluster_artifact_coverage": [],
        "top_multi_paper_artifacts": [],
        "samples": {},
    }

    if nodes_path.exists() and edges_path.exists():
        try:
            nodes = _read_jsonl(nodes_path)
            edges = _read_jsonl(edges_path)
            analytics = _compute_graph_analytics(nodes, edges)
            checks.append(CheckResult("graph_jsonl_readable", True))
        except Exception as exc:  # pragma: no cover - defensive error payload
            checks.append(CheckResult("graph_jsonl_readable", False, details=str(exc)))

    if manifest_path.exists():
        try:
            manifest = _read_json(manifest_path)
            checks.append(CheckResult("manifest_readable", True))
        except Exception as exc:  # pragma: no cover
            checks.append(CheckResult("manifest_readable", False, details=str(exc)))
    if quality_path.exists():
        try:
            quality = _read_json(quality_path)
            checks.append(CheckResult("data_quality_summary_readable", True))
        except Exception as exc:  # pragma: no cover
            checks.append(CheckResult("data_quality_summary_readable", False, details=str(exc)))

    if manifest:
        manifest_safe = (
            _as_bool(_manifest_flag(manifest, "canonical_truth")) is False
            and _as_bool(_manifest_flag(manifest, "may_be_used_as_reconcile_input")) is False
            and _as_bool(_manifest_flag(manifest, "publication_ready")) is False
        )
        checks.append(CheckResult("manifest_safety_flags", manifest_safe))
        builder = manifest.get("builder") if isinstance(manifest.get("builder"), dict) else {}
        checks.append(CheckResult("manifest_builder_file_input", builder.get("input_mode") in (None, "file")))
        checks.append(CheckResult("manifest_no_live_db_dependency", builder.get("live_db_dependency") in (None, False)))
    if quality:
        checks.append(CheckResult("data_quality_summary_ok", quality.get("ok") in (None, True)))

    node_types = set(analytics["counts"]["node_type_counts"])
    edge_types = set(analytics["counts"]["edge_type_counts"])
    checks.append(CheckResult("required_node_types_present", REQUIRED_NODE_TYPES.issubset(node_types), details=str(sorted(REQUIRED_NODE_TYPES - node_types))))
    checks.append(CheckResult("required_edge_types_present", REQUIRED_EDGE_TYPES.issubset(edge_types), details=str(sorted(REQUIRED_EDGE_TYPES - edge_types))))
    checks.append(CheckResult("paper_has_artifact_edges_present", analytics["counts"].get("papers_with_artifacts_count", 0) > 0))
    checks.append(CheckResult("provider_coverage_present", bool(analytics["provider_distribution"]["artifact_nodes"])))
    checks.append(CheckResult("topic_cluster_artifact_coverage_present", analytics["counts"].get("topic_clusters_with_artifact_ready_papers_count", 0) > 0))

    expected_counts = config.get("expected_counts") if isinstance(config.get("expected_counts"), dict) else {}
    checks.extend(_check_expected_counts(analytics, expected_counts))
    expected_analytics = config.get("expected_analytics") if isinstance(config.get("expected_analytics"), dict) else {}
    checks.extend(_check_expected_analytics(analytics, expected_analytics))

    report = _report_from_checks(config=config, config_path=config_path, checks=checks, analytics=analytics, strict=strict)

    if write_reports:
        validation = config.get("validation") if isinstance(config.get("validation"), dict) else {}
        base_report_dir = report_dir or _resolve_path(validation.get("report_dir", "artifacts/reports/validation"), config_path=config_path)
        latest_json = base_report_dir / f"{REPORT_BASENAME}_latest.json"
        latest_md = base_report_dir / f"{REPORT_BASENAME}_latest.md"
        history_dir = base_report_dir / "history"
        run_ts = report["run_ts"]
        history_json = history_dir / f"{REPORT_BASENAME}_{run_ts}.json"
        history_md = history_dir / f"{REPORT_BASENAME}_{run_ts}.md"
        _write_json(latest_json, report)
        _write_json(history_json, report)
        _write_markdown(latest_md, report)
        _write_markdown(history_md, report)
        report["report_paths"] = {
            "latest_json": str(latest_json),
            "latest_md": str(latest_md),
            "history_json": str(history_json),
            "history_md": str(history_md),
        }

    # Keep top-level summary shape consistent with neighboring validators.
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"]["required_failed_count"]
    report["warning_count"] = report["summary"]["warning_count"]
    report["strict"] = strict
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate/read Paper-Artifact Graph analytics v0.1.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to analytics config YAML.")
    parser.add_argument("--strict", action="store_true", help="Use strict validation semantics.")
    parser.add_argument("--no-write-reports", action="store_true", help="Do not write latest/history JSON/Markdown reports.")
    parser.add_argument("--report-dir", default=None, help="Override validation report directory.")
    args = parser.parse_args(argv)

    report = validate_graph_analytics(
        config_path=Path(args.config),
        strict=args.strict,
        write_reports=not args.no_write_reports,
        report_dir=Path(args.report_dir) if args.report_dir else None,
    )
    print(
        json.dumps(
            {
                "ok": report["summary"]["ok"],
                "required_failed_count": report["summary"]["required_failed_count"],
                "strict": report["summary"]["strict"],
                "total_checks": report["summary"]["total_checks"],
                "warning_count": report["summary"]["warning_count"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
