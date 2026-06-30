from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("configs/paper_artifact_graph_builder.yaml")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

REPORT_SCHEMA_VERSION = "paper_artifact_graph_inspection_quality_v1"

REQUIRED_GRAPH_FILES = {
    "nodes_path",
    "edges_path",
    "manifest_path",
    "data_quality_summary_path",
}


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(value: str | Path | None) -> str | None:
    if value is None:
        return None
    return str(value).replace("\\", "/")


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc


def resolve_path(raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def get_outputs_from_config(
    config: dict[str, Any],
    graph_dir_override: Path | None = None,
) -> dict[str, Path]:
    outputs = dict(config.get("outputs", {}))

    if graph_dir_override is not None:
        graph_dir = graph_dir_override
        outputs = {
            "graph_dir": graph_dir,
            "nodes_path": graph_dir / "nodes.jsonl",
            "edges_path": graph_dir / "edges.jsonl",
            "manifest_path": graph_dir / "manifest.json",
            "data_quality_summary_path": graph_dir / "data_quality_summary.json",
        }

    return {
        key: resolve_path(value)
        for key, value in outputs.items()
        if key == "graph_dir" or key.endswith("_path")
    }


def top_counter(counter: Counter[str], *, limit: int = 20) -> list[dict[str, Any]]:
    return [
        {"key": key, "count": count}
        for key, count in counter.most_common(limit)
    ]


def quality_get(quality: dict[str, Any], key: str) -> Any:
    payload = quality.get("quality")
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def node_label(node: dict[str, Any] | None) -> str | None:
    if not isinstance(node, dict):
        return None
    label = node.get("label")
    if label is not None:
        return str(label)
    return None


def node_properties(node: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    props = node.get("properties")
    return props if isinstance(props, dict) else {}


def summarize_graph(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    manifest: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    nodes_by_id = {
        str(node.get("node_id")): node
        for node in nodes
        if isinstance(node, dict) and node.get("node_id")
    }

    node_type_counts = Counter(
        str(node.get("node_type"))
        for node in nodes
        if isinstance(node, dict) and node.get("node_type")
    )
    edge_type_counts = Counter(
        str(edge.get("edge_type"))
        for edge in edges
        if isinstance(edge, dict) and edge.get("edge_type")
    )

    artifact_provider_by_node_id: dict[str, str] = {}
    artifact_label_by_node_id: dict[str, str] = {}

    for node_id, node in nodes_by_id.items():
        if node.get("node_type") != "artifact":
            continue

        props = node_properties(node)
        provider = props.get("provider") or "unknown"
        artifact_provider_by_node_id[node_id] = str(provider)
        artifact_label_by_node_id[node_id] = node_label(node) or node_id

    provider_artifact_counts = Counter(artifact_provider_by_node_id.values())

    paper_has_artifact_edges = [
        edge for edge in edges if edge.get("edge_type") == "paper_has_artifact"
    ]
    source_family_edges = [
        edge for edge in edges if edge.get("edge_type") == "paper_observed_in_source_family"
    ]
    topic_edges = [
        edge for edge in edges if edge.get("edge_type") == "paper_assigned_to_topic_cluster"
    ]

    provider_link_counts: Counter[str] = Counter()
    papers_with_artifacts: set[str] = set()
    artifacts_with_papers: Counter[str] = Counter()
    paper_to_artifact_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for edge in paper_has_artifact_edges:
        paper_node_id = str(edge.get("source_node_id"))
        artifact_node_id = str(edge.get("target_node_id"))
        provider = artifact_provider_by_node_id.get(artifact_node_id, "unknown")

        provider_link_counts[provider] += 1
        papers_with_artifacts.add(paper_node_id)
        artifacts_with_papers[artifact_node_id] += 1
        paper_to_artifact_edges[paper_node_id].append(edge)

    source_family_counts: Counter[str] = Counter()
    for edge in source_family_edges:
        props = edge.get("properties") if isinstance(edge.get("properties"), dict) else {}
        family = props.get("source_family")
        if not family:
            target = str(edge.get("target_node_id") or "")
            family = target.removeprefix("source_family:")
        source_family_counts[str(family or "unknown")] += 1

    topic_to_papers: dict[str, list[str]] = defaultdict(list)
    paper_to_topics: dict[str, list[str]] = defaultdict(list)

    for edge in topic_edges:
        paper_node_id = str(edge.get("source_node_id"))
        topic_node_id = str(edge.get("target_node_id"))
        topic_to_papers[topic_node_id].append(paper_node_id)
        paper_to_topics[paper_node_id].append(topic_node_id)

    topic_artifact_ready_counts: Counter[str] = Counter()
    for topic_node_id, paper_node_ids in topic_to_papers.items():
        for paper_node_id in paper_node_ids:
            if paper_node_id in papers_with_artifacts:
                topic_artifact_ready_counts[topic_node_id] += 1

    sample_paper_artifact_edges: list[dict[str, Any]] = []
    for edge in paper_has_artifact_edges[:20]:
        paper_node_id = str(edge.get("source_node_id"))
        artifact_node_id = str(edge.get("target_node_id"))
        props = edge.get("properties") if isinstance(edge.get("properties"), dict) else {}
        sample_paper_artifact_edges.append(
            {
                "paper_node_id": paper_node_id,
                "paper_label": node_label(nodes_by_id.get(paper_node_id)),
                "artifact_node_id": artifact_node_id,
                "artifact_label": artifact_label_by_node_id.get(artifact_node_id),
                "provider": artifact_provider_by_node_id.get(artifact_node_id, "unknown"),
                "relation_type": props.get("relation_type"),
                "confidence": props.get("confidence"),
            }
        )

    sample_topic_paper_artifact_paths: list[dict[str, Any]] = []
    for topic_node_id, _count in topic_artifact_ready_counts.most_common(10):
        for paper_node_id in topic_to_papers.get(topic_node_id, []):
            artifact_edges = paper_to_artifact_edges.get(paper_node_id) or []
            if not artifact_edges:
                continue

            artifact_edge = artifact_edges[0]
            artifact_node_id = str(artifact_edge.get("target_node_id"))
            edge_props = artifact_edge.get("properties") if isinstance(artifact_edge.get("properties"), dict) else {}

            sample_topic_paper_artifact_paths.append(
                {
                    "topic_cluster_node_id": topic_node_id,
                    "topic_cluster_label": node_label(nodes_by_id.get(topic_node_id)),
                    "paper_node_id": paper_node_id,
                    "paper_label": node_label(nodes_by_id.get(paper_node_id)),
                    "artifact_node_id": artifact_node_id,
                    "artifact_label": artifact_label_by_node_id.get(artifact_node_id),
                    "provider": artifact_provider_by_node_id.get(artifact_node_id, "unknown"),
                    "relation_type": edge_props.get("relation_type"),
                }
            )
            break

    total_papers = int(node_type_counts.get("paper", 0))
    total_artifacts = int(node_type_counts.get("artifact", 0))
    papers_with_artifacts_count = len(papers_with_artifacts)
    artifacts_with_papers_count = len(artifacts_with_papers)

    artifacts_linked_to_multiple_papers = {
        artifact_node_id: count
        for artifact_node_id, count in artifacts_with_papers.items()
        if count > 1
    }

    overview = {
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "papers_count": total_papers,
        "artifacts_count": total_artifacts,
        "papers_with_artifacts_count": papers_with_artifacts_count,
        "papers_without_artifacts_count": max(total_papers - papers_with_artifacts_count, 0),
        "artifacts_with_papers_count": artifacts_with_papers_count,
        "artifacts_without_papers_count": max(total_artifacts - artifacts_with_papers_count, 0),
        "artifacts_linked_to_multiple_papers_count": len(artifacts_linked_to_multiple_papers),
        "topic_clusters_with_artifact_ready_papers_count": len(topic_artifact_ready_counts),
    }

    return {
        "overview": overview,
        "top_providers_by_artifact_nodes": top_counter(provider_artifact_counts),
        "top_providers_by_paper_has_artifact_edges": top_counter(provider_link_counts),
        "top_source_families_by_paper_observations": top_counter(source_family_counts),
        "top_artifacts_by_linked_papers": [
            {
                "artifact_node_id": artifact_node_id,
                "artifact_label": artifact_label_by_node_id.get(artifact_node_id),
                "provider": artifact_provider_by_node_id.get(artifact_node_id, "unknown"),
                "linked_papers_count": count,
            }
            for artifact_node_id, count in artifacts_with_papers.most_common(20)
        ],
        "top_topic_clusters_by_artifact_ready_papers": [
            {
                "topic_cluster_node_id": topic_node_id,
                "topic_cluster_label": node_label(nodes_by_id.get(topic_node_id)),
                "artifact_ready_papers_count": count,
            }
            for topic_node_id, count in topic_artifact_ready_counts.most_common(20)
        ],
        "samples": {
            "paper_artifact_edges": sample_paper_artifact_edges,
            "topic_paper_artifact_paths": sample_topic_paper_artifact_paths,
        },
        "source_manifest_flags": {
            "canonical_truth": manifest.get("canonical_truth"),
            "may_be_used_as_reconcile_input": manifest.get("may_be_used_as_reconcile_input"),
            "publication_ready": manifest.get("publication_ready"),
            "dry_run": manifest.get("dry_run"),
            "builder_input_mode": manifest.get("builder", {}).get("input_mode"),
            "live_db_dependency": manifest.get("builder", {}).get("live_db_dependency"),
            "create_latest_pointer": manifest.get("builder", {}).get("create_latest_pointer"),
        },
        "quality_reference": {
            "ok": quality.get("ok"),
            "nodes_count": quality_get(quality, "nodes_count"),
            "edges_count": quality_get(quality, "edges_count"),
            "trusted_links_used_count": quality_get(quality, "trusted_links_used_count"),
            "topic_edges_count": quality_get(quality, "topic_edges_count"),
        },
    }


def validate_inspection(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    graph_dir: Path | None = None,
) -> dict[str, Any]:
    run_ts = utc_now_ts()
    config = load_yaml(config_path)
    outputs = get_outputs_from_config(config, graph_dir)

    output_file_checks = {
        f"{key}_exists": path.exists()
        for key, path in outputs.items()
        if key in REQUIRED_GRAPH_FILES
    }

    required_files_exist = all(output_file_checks.values()) and REQUIRED_GRAPH_FILES.issubset(set(outputs))

    manifest: dict[str, Any] = {}
    quality: dict[str, Any] = {}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    if required_files_exist:
        manifest = load_json(outputs["manifest_path"])
        quality = load_json(outputs["data_quality_summary_path"])
        nodes = [row for row, _line_no in iter_jsonl(outputs["nodes_path"]) if isinstance(row, dict)]
        edges = [row for row, _line_no in iter_jsonl(outputs["edges_path"]) if isinstance(row, dict)]

    inspection = summarize_graph(
        nodes=nodes,
        edges=edges,
        manifest=manifest,
        quality=quality,
    ) if required_files_exist else {}

    overview = inspection.get("overview", {}) if isinstance(inspection, dict) else {}

    checks = {
        "required_graph_files_exist": required_files_exist,
        **output_file_checks,
        "manifest_not_dry_run": manifest.get("dry_run") is False,
        "manifest_not_canonical_truth": manifest.get("canonical_truth") is False,
        "manifest_not_reconcile_input": manifest.get("may_be_used_as_reconcile_input") is False,
        "manifest_not_publication_ready": manifest.get("publication_ready") is False,
        "manifest_builder_file_mode": manifest.get("builder", {}).get("input_mode") == "file",
        "manifest_no_live_db_dependency": manifest.get("builder", {}).get("live_db_dependency") is False,
        "manifest_no_latest_pointer": manifest.get("builder", {}).get("create_latest_pointer") is False,
        "data_quality_ok_true": quality.get("ok") is True,
        "nodes_non_empty": int(overview.get("nodes_count") or 0) > 0,
        "edges_non_empty": int(overview.get("edges_count") or 0) > 0,
        "paper_has_artifact_edges_present": (
            int(overview.get("papers_with_artifacts_count") or 0) > 0
        ),
        "artifact_provider_distribution_non_empty": (
            len(inspection.get("top_providers_by_artifact_nodes", [])) > 0
        ),
        "source_family_distribution_non_empty": (
            len(inspection.get("top_source_families_by_paper_observations", [])) > 0
        ),
        "topic_clusters_with_artifact_ready_papers_present": (
            int(overview.get("topic_clusters_with_artifact_ready_papers_count") or 0) > 0
        ),
        "sample_paper_artifact_edges_present": (
            len(inspection.get("samples", {}).get("paper_artifact_edges", [])) > 0
        ),
    }

    required_failed = [
        name for name, ok in checks.items() if not ok
    ]

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "config_path": normalize_path(config_path),
        "graph_dir": normalize_path(outputs.get("graph_dir")),
        "checks": checks,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
        "inspection": inspection,
        "summary": {
            "ok": len(required_failed) == 0,
            "required_failed_count": len(required_failed),
            "nodes_count": overview.get("nodes_count"),
            "edges_count": overview.get("edges_count"),
            "papers_with_artifacts_count": overview.get("papers_with_artifacts_count"),
            "artifacts_linked_to_multiple_papers_count": overview.get(
                "artifacts_linked_to_multiple_papers_count"
            ),
            "topic_clusters_with_artifact_ready_papers_count": overview.get(
                "topic_clusters_with_artifact_ready_papers_count"
            ),
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    inspection = report.get("inspection", {}) if isinstance(report.get("inspection"), dict) else {}
    overview = inspection.get("overview", {}) if isinstance(inspection.get("overview"), dict) else {}
    samples = inspection.get("samples", {}) if isinstance(inspection.get("samples"), dict) else {}

    lines: list[str] = []
    lines.append("# Paper-Artifact Graph Inspection")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Config: `{report['config_path']}`")
    lines.append(f"- Graph dir: `{report['graph_dir']}`")
    lines.append(f"- OK: **{report['ok']}**")
    lines.append(f"- Required failed count: `{report['required_failed_count']}`")
    lines.append("")

    lines.append("## Overview")
    lines.append("")
    for key in [
        "nodes_count",
        "edges_count",
        "papers_count",
        "artifacts_count",
        "papers_with_artifacts_count",
        "papers_without_artifacts_count",
        "artifacts_with_papers_count",
        "artifacts_without_papers_count",
        "artifacts_linked_to_multiple_papers_count",
        "topic_clusters_with_artifact_ready_papers_count",
    ]:
        lines.append(f"- {key}: `{overview.get(key)}`")
    lines.append("")

    lines.append("## Required checks")
    lines.append("")
    lines.append("| Check | OK |")
    lines.append("|---|---:|")
    for name, ok in report.get("checks", {}).items():
        lines.append(f"| `{name}` | {ok} |")
    lines.append("")

    if report.get("required_failed_checks"):
        lines.append("## Required failures")
        lines.append("")
        for name in report["required_failed_checks"]:
            lines.append(f"- `{name}`")
        lines.append("")

    def append_table(title: str, rows: list[dict[str, Any]], key_name: str = "key") -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not rows:
            lines.append("_No rows._")
            lines.append("")
            return
        lines.append("| Item | Count |")
        lines.append("|---|---:|")
        for row in rows[:20]:
            lines.append(f"| `{row.get(key_name)}` | {row.get('count')} |")
        lines.append("")

    append_table(
        "Top providers by artifact nodes",
        inspection.get("top_providers_by_artifact_nodes", []),
    )
    append_table(
        "Top providers by paper-artifact edges",
        inspection.get("top_providers_by_paper_has_artifact_edges", []),
    )
    append_table(
        "Top source families by paper observations",
        inspection.get("top_source_families_by_paper_observations", []),
    )

    lines.append("## Top artifacts by linked papers")
    lines.append("")
    artifact_rows = inspection.get("top_artifacts_by_linked_papers", [])
    if artifact_rows:
        lines.append("| Artifact | Provider | Linked papers |")
        lines.append("|---|---|---:|")
        for row in artifact_rows[:20]:
            lines.append(
                f"| `{row.get('artifact_label') or row.get('artifact_node_id')}` "
                f"| `{row.get('provider')}` "
                f"| {row.get('linked_papers_count')} |"
            )
    else:
        lines.append("_No rows._")
    lines.append("")

    lines.append("## Top topic clusters by artifact-ready papers")
    lines.append("")
    topic_rows = inspection.get("top_topic_clusters_by_artifact_ready_papers", [])
    if topic_rows:
        lines.append("| Topic cluster | Artifact-ready papers |")
        lines.append("|---|---:|")
        for row in topic_rows[:20]:
            lines.append(
                f"| `{row.get('topic_cluster_label') or row.get('topic_cluster_node_id')}` "
                f"| {row.get('artifact_ready_papers_count')} |"
            )
    else:
        lines.append("_No rows._")
    lines.append("")

    lines.append("## Sample paper-artifact edges")
    lines.append("")
    edge_samples = samples.get("paper_artifact_edges", [])
    if edge_samples:
        lines.append("| Paper | Artifact | Provider | Relation | Confidence |")
        lines.append("|---|---|---|---|---:|")
        for row in edge_samples[:10]:
            lines.append(
                f"| `{row.get('paper_label') or row.get('paper_node_id')}` "
                f"| `{row.get('artifact_label') or row.get('artifact_node_id')}` "
                f"| `{row.get('provider')}` "
                f"| `{row.get('relation_type')}` "
                f"| {row.get('confidence')} |"
            )
    else:
        lines.append("_No samples._")
    lines.append("")

    lines.append("## Sample topic → paper → artifact paths")
    lines.append("")
    path_samples = samples.get("topic_paper_artifact_paths", [])
    if path_samples:
        lines.append("| Topic cluster | Paper | Artifact | Provider |")
        lines.append("|---|---|---|---|")
        for row in path_samples[:10]:
            lines.append(
                f"| `{row.get('topic_cluster_label') or row.get('topic_cluster_node_id')}` "
                f"| `{row.get('paper_label') or row.get('paper_node_id')}` "
                f"| `{row.get('artifact_label') or row.get('artifact_node_id')}` "
                f"| `{row.get('provider')}` |"
            )
    else:
        lines.append("_No samples._")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reports(report: dict[str, Any], reports_dir: Path) -> None:
    history_dir = reports_dir / "history"
    run_ts = report["run_ts"]

    json_latest = reports_dir / "paper_artifact_graph_inspection_latest.json"
    md_latest = reports_dir / "paper_artifact_graph_inspection_latest.md"
    json_history = history_dir / f"paper_artifact_graph_inspection_{run_ts}.json"
    md_history = history_dir / f"paper_artifact_graph_inspection_{run_ts}.md"

    write_json(json_latest, report)
    write_json(json_history, report)
    write_markdown_report(md_latest, report)
    write_markdown_report(md_history, report)

    print(f"[OK] report JSON: {json_latest}")
    print(f"[OK] report MD: {md_latest}")
    print(f"[OK] history JSON: {json_history}")
    print(f"[OK] history MD: {md_history}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--graph-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = validate_inspection(
        config_path=args.config,
        graph_dir=args.graph_dir,
    )

    write_reports(report, args.reports_dir)

    summary = report.get("summary", {})
    print(f"[CHECK] ok={report['ok']}")
    print(f"[CHECK] required_failed_count={report['required_failed_count']}")
    print(f"[CHECK] required_failed_checks={report['required_failed_checks']}")
    print(f"[CHECK] nodes_count={summary.get('nodes_count')}")
    print(f"[CHECK] edges_count={summary.get('edges_count')}")
    print(f"[CHECK] papers_with_artifacts_count={summary.get('papers_with_artifacts_count')}")
    print(
        "[CHECK] topic_clusters_with_artifact_ready_papers_count="
        f"{summary.get('topic_clusters_with_artifact_ready_papers_count')}"
    )

    if args.strict and not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
