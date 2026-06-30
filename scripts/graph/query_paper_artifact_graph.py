from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("configs/paper_artifact_graph_builder.yaml")


@dataclass(frozen=True)
class GraphPaths:
    graph_dir: Path
    nodes_path: Path
    edges_path: Path
    manifest_path: Path


@dataclass
class GraphIndex:
    nodes_by_id: dict[str, dict[str, Any]]
    outgoing_by_type: dict[str, dict[str, list[dict[str, Any]]]]
    incoming_by_type: dict[str, dict[str, list[dict[str, Any]]]]
    manifest: dict[str, Any]
    paths: GraphPaths


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


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc

            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row must be an object: {path} line={line_no}")
            yield payload


def resolve_path(raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def graph_paths_from_config(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    graph_dir_override: Path | None = None,
) -> GraphPaths:
    if graph_dir_override is not None:
        graph_dir = graph_dir_override
        return GraphPaths(
            graph_dir=graph_dir,
            nodes_path=graph_dir / "nodes.jsonl",
            edges_path=graph_dir / "edges.jsonl",
            manifest_path=graph_dir / "manifest.json",
        )

    config = load_yaml(config_path)
    outputs = config.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError(f"Missing outputs mapping in config: {config_path}")

    graph_dir = resolve_path(outputs.get("graph_dir"))
    nodes_path = resolve_path(outputs.get("nodes_path") or graph_dir / "nodes.jsonl")
    edges_path = resolve_path(outputs.get("edges_path") or graph_dir / "edges.jsonl")
    manifest_path = resolve_path(outputs.get("manifest_path") or graph_dir / "manifest.json")

    return GraphPaths(
        graph_dir=graph_dir,
        nodes_path=nodes_path,
        edges_path=edges_path,
        manifest_path=manifest_path,
    )


def load_graph_index(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    graph_dir: Path | None = None,
) -> GraphIndex:
    paths = graph_paths_from_config(config_path=config_path, graph_dir_override=graph_dir)

    missing = [
        str(path)
        for path in [paths.nodes_path, paths.edges_path, paths.manifest_path]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(f"Missing graph output files: {missing}")

    manifest = load_json(paths.manifest_path)

    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in iter_jsonl(paths.nodes_path):
        node_id = node.get("node_id")
        if not node_id:
            raise ValueError(f"Graph node without node_id in {paths.nodes_path}")
        node_id = str(node_id)
        if node_id in nodes_by_id:
            raise ValueError(f"Duplicate node_id in graph: {node_id}")
        nodes_by_id[node_id] = node

    outgoing_by_type: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    incoming_by_type: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for edge in iter_jsonl(paths.edges_path):
        edge_type = edge.get("edge_type")
        source_node_id = edge.get("source_node_id")
        target_node_id = edge.get("target_node_id")

        if not edge_type or not source_node_id or not target_node_id:
            raise ValueError(f"Graph edge missing edge_type/source_node_id/target_node_id: {edge}")

        edge_type = str(edge_type)
        source_node_id = str(source_node_id)
        target_node_id = str(target_node_id)

        outgoing_by_type[edge_type][source_node_id].append(edge)
        incoming_by_type[edge_type][target_node_id].append(edge)

    return GraphIndex(
        nodes_by_id=nodes_by_id,
        outgoing_by_type=outgoing_by_type,
        incoming_by_type=incoming_by_type,
        manifest=manifest,
        paths=paths,
    )


def node_label(node: dict[str, Any] | None) -> str | None:
    if not isinstance(node, dict):
        return None
    label = node.get("label")
    if label is None:
        return None
    return str(label)


def node_type(node: dict[str, Any] | None) -> str | None:
    if not isinstance(node, dict):
        return None
    value = node.get("node_type")
    if value is None:
        return None
    return str(value)


def node_properties(node: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    properties = node.get("properties")
    return properties if isinstance(properties, dict) else {}


def edge_properties(edge: dict[str, Any]) -> dict[str, Any]:
    properties = edge.get("properties")
    return properties if isinstance(properties, dict) else {}


def strip_node_prefix(node_id: str, prefix: str) -> str:
    if node_id.startswith(prefix):
        return node_id[len(prefix):]
    return node_id


def normalize_paper_node_id(value: str) -> str:
    return value if value.startswith("paper:") else f"paper:{value}"


def normalize_artifact_node_id(value: str) -> str:
    return value if value.startswith("artifact:") else f"artifact:{value}"


def normalize_provider_node_id(value: str) -> str:
    return value if value.startswith("provider:") else f"provider:{value}"


def normalize_topic_cluster_node_id(value: str) -> str:
    return value if value.startswith("topic_cluster:") else f"topic_cluster:{value}"


def compact_node(node_id: str, node: dict[str, Any] | None) -> dict[str, Any]:
    props = node_properties(node)
    return {
        "node_id": node_id,
        "node_type": node_type(node),
        "label": node_label(node),
        "properties": {
            key: props.get(key)
            for key in [
                "canonical_id",
                "artifact_id",
                "provider",
                "artifact_type",
                "source_family",
                "topic_cluster_id",
                "url",
                "external_url",
            ]
            if key in props
        },
    }


def compact_artifact(index: GraphIndex, artifact_node_id: str, edge: dict[str, Any] | None = None) -> dict[str, Any]:
    node = index.nodes_by_id.get(artifact_node_id)
    props = node_properties(node)
    edge_props = edge_properties(edge) if edge else {}

    return {
        "artifact_node_id": artifact_node_id,
        "artifact_id": props.get("artifact_id") or strip_node_prefix(artifact_node_id, "artifact:"),
        "label": node_label(node),
        "provider": props.get("provider"),
        "artifact_type": props.get("artifact_type"),
        "url": props.get("url") or props.get("external_url"),
        "relation_type": edge_props.get("relation_type"),
        "confidence": edge_props.get("confidence"),
    }


def compact_paper(index: GraphIndex, paper_node_id: str, edge: dict[str, Any] | None = None) -> dict[str, Any]:
    node = index.nodes_by_id.get(paper_node_id)
    props = node_properties(node)
    edge_props = edge_properties(edge) if edge else {}

    return {
        "paper_node_id": paper_node_id,
        "canonical_id": props.get("canonical_id") or strip_node_prefix(paper_node_id, "paper:"),
        "label": node_label(node),
        "relation_type": edge_props.get("relation_type"),
        "confidence": edge_props.get("confidence"),
    }


def query_by_paper(index: GraphIndex, paper_id: str, *, top_k: int) -> dict[str, Any]:
    paper_node_id = normalize_paper_node_id(paper_id)
    paper_node = index.nodes_by_id.get(paper_node_id)

    artifact_edges = index.outgoing_by_type["paper_has_artifact"].get(paper_node_id, [])
    topic_edges = index.outgoing_by_type["paper_assigned_to_topic_cluster"].get(paper_node_id, [])
    source_edges = index.outgoing_by_type["paper_observed_in_source_family"].get(paper_node_id, [])

    artifacts = [
        compact_artifact(index, str(edge["target_node_id"]), edge)
        for edge in artifact_edges[:top_k]
    ]

    topics = [
        compact_node(str(edge["target_node_id"]), index.nodes_by_id.get(str(edge["target_node_id"])))
        for edge in topic_edges[:top_k]
    ]

    source_families = [
        compact_node(str(edge["target_node_id"]), index.nodes_by_id.get(str(edge["target_node_id"])))
        for edge in source_edges[:top_k]
    ]

    return {
        "query_type": "paper",
        "paper_id": paper_id,
        "paper_node": compact_node(paper_node_id, paper_node),
        "found": paper_node is not None,
        "counts": {
            "artifacts": len(artifact_edges),
            "topic_clusters": len(topic_edges),
            "source_families": len(source_edges),
        },
        "artifacts": artifacts,
        "topic_clusters": topics,
        "source_families": source_families,
    }


def query_by_artifact(index: GraphIndex, artifact_id: str, *, top_k: int) -> dict[str, Any]:
    artifact_node_id = normalize_artifact_node_id(artifact_id)
    artifact_node = index.nodes_by_id.get(artifact_node_id)

    paper_edges = index.incoming_by_type["paper_has_artifact"].get(artifact_node_id, [])
    provider_edges = index.outgoing_by_type["artifact_from_provider"].get(artifact_node_id, [])

    papers = [
        compact_paper(index, str(edge["source_node_id"]), edge)
        for edge in paper_edges[:top_k]
    ]

    providers = [
        compact_node(str(edge["target_node_id"]), index.nodes_by_id.get(str(edge["target_node_id"])))
        for edge in provider_edges[:top_k]
    ]

    return {
        "query_type": "artifact",
        "artifact_id": artifact_id,
        "artifact_node": compact_node(artifact_node_id, artifact_node),
        "found": artifact_node is not None,
        "counts": {
            "linked_papers": len(paper_edges),
            "providers": len(provider_edges),
        },
        "papers": papers,
        "providers": providers,
    }


def query_by_provider(index: GraphIndex, provider: str, *, top_k: int) -> dict[str, Any]:
    provider_node_id = normalize_provider_node_id(provider)
    provider_node = index.nodes_by_id.get(provider_node_id)

    artifact_edges = index.incoming_by_type["artifact_from_provider"].get(provider_node_id, [])

    rows: list[dict[str, Any]] = []
    total_paper_links = 0

    for edge in artifact_edges:
        artifact_node_id = str(edge["source_node_id"])
        paper_edges = index.incoming_by_type["paper_has_artifact"].get(artifact_node_id, [])
        total_paper_links += len(paper_edges)

        artifact = compact_artifact(index, artifact_node_id)
        artifact["linked_papers_count"] = len(paper_edges)
        rows.append(artifact)

    rows.sort(
        key=lambda row: (
            -int(row.get("linked_papers_count") or 0),
            str(row.get("artifact_node_id") or ""),
        )
    )

    return {
        "query_type": "provider",
        "provider": provider,
        "provider_node": compact_node(provider_node_id, provider_node),
        "found": provider_node is not None,
        "counts": {
            "artifacts": len(artifact_edges),
            "paper_artifact_links": total_paper_links,
        },
        "artifacts": rows[:top_k],
    }


def query_by_topic_cluster(index: GraphIndex, topic_cluster: str, *, top_k: int) -> dict[str, Any]:
    topic_node_id = normalize_topic_cluster_node_id(topic_cluster)
    topic_node = index.nodes_by_id.get(topic_node_id)

    paper_topic_edges = index.incoming_by_type["paper_assigned_to_topic_cluster"].get(topic_node_id, [])

    artifact_ready_rows: list[dict[str, Any]] = []
    total_artifact_edges = 0

    for topic_edge in paper_topic_edges:
        paper_node_id = str(topic_edge["source_node_id"])
        artifact_edges = index.outgoing_by_type["paper_has_artifact"].get(paper_node_id, [])
        if not artifact_edges:
            continue

        total_artifact_edges += len(artifact_edges)
        paper = compact_paper(index, paper_node_id)
        paper["artifacts_count"] = len(artifact_edges)
        paper["artifacts"] = [
            compact_artifact(index, str(edge["target_node_id"]), edge)
            for edge in artifact_edges[:5]
        ]
        artifact_ready_rows.append(paper)

    artifact_ready_rows.sort(
        key=lambda row: (
            -int(row.get("artifacts_count") or 0),
            str(row.get("paper_node_id") or ""),
        )
    )

    return {
        "query_type": "topic_cluster",
        "topic_cluster": topic_cluster,
        "topic_cluster_node": compact_node(topic_node_id, topic_node),
        "found": topic_node is not None,
        "counts": {
            "papers": len(paper_topic_edges),
            "artifact_ready_papers": len(artifact_ready_rows),
            "paper_artifact_links": total_artifact_edges,
        },
        "artifact_ready_papers": artifact_ready_rows[:top_k],
    }


def query_graph(
    index: GraphIndex,
    *,
    paper_id: str | None = None,
    artifact_id: str | None = None,
    provider: str | None = None,
    topic_cluster: str | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    selected = [
        value is not None
        for value in [paper_id, artifact_id, provider, topic_cluster]
    ]
    if sum(selected) != 1:
        raise ValueError("Exactly one query selector is required")

    if top_k <= 0:
        raise ValueError("top_k must be positive")

    if paper_id is not None:
        return query_by_paper(index, paper_id, top_k=top_k)
    if artifact_id is not None:
        return query_by_artifact(index, artifact_id, top_k=top_k)
    if provider is not None:
        return query_by_provider(index, provider, top_k=top_k)
    if topic_cluster is not None:
        return query_by_topic_cluster(index, topic_cluster, top_k=top_k)

    raise ValueError("No query selector provided")


def manifest_safety_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    builder = manifest.get("builder") if isinstance(manifest.get("builder"), dict) else {}
    return {
        "canonical_truth": manifest.get("canonical_truth"),
        "may_be_used_as_reconcile_input": manifest.get("may_be_used_as_reconcile_input"),
        "publication_ready": manifest.get("publication_ready"),
        "dry_run": manifest.get("dry_run"),
        "builder_input_mode": builder.get("input_mode"),
        "live_db_dependency": builder.get("live_db_dependency"),
        "create_latest_pointer": builder.get("create_latest_pointer"),
    }


def attach_meta(result: dict[str, Any], index: GraphIndex) -> dict[str, Any]:
    return {
        "schema_version": "paper_artifact_graph_query_cli_result_v1",
        "graph_dir": str(index.paths.graph_dir).replace("\\", "/"),
        "manifest_safety": manifest_safety_summary(index.manifest),
        "result": result,
    }


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def render_markdown(payload: dict[str, Any]) -> str:
    result = payload["result"]
    lines: list[str] = []

    lines.append("# Paper-Artifact Graph Query")
    lines.append("")
    lines.append(f"- Query type: `{result.get('query_type')}`")
    lines.append(f"- Graph dir: `{payload.get('graph_dir')}`")
    lines.append(f"- Found: `{result.get('found')}`")
    lines.append("")

    lines.append("## Counts")
    lines.append("")
    for key, value in result.get("counts", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    query_type = result.get("query_type")

    if query_type == "paper":
        node = result.get("paper_node", {})
        lines.append("## Paper")
        lines.append("")
        lines.append(f"- Node: `{node.get('node_id')}`")
        lines.append(f"- Label: `{node.get('label')}`")
        lines.append("")
        lines.append("## Artifacts")
        lines.append("")
        for artifact in result.get("artifacts", []):
            lines.append(
                f"- `{artifact.get('label') or artifact.get('artifact_node_id')}` "
                f"provider=`{artifact.get('provider')}` "
                f"relation=`{artifact.get('relation_type')}` "
                f"confidence=`{artifact.get('confidence')}`"
            )

    elif query_type == "artifact":
        node = result.get("artifact_node", {})
        lines.append("## Artifact")
        lines.append("")
        lines.append(f"- Node: `{node.get('node_id')}`")
        lines.append(f"- Label: `{node.get('label')}`")
        lines.append("")
        lines.append("## Papers")
        lines.append("")
        for paper in result.get("papers", []):
            lines.append(
                f"- `{paper.get('label') or paper.get('paper_node_id')}` "
                f"relation=`{paper.get('relation_type')}` "
                f"confidence=`{paper.get('confidence')}`"
            )

    elif query_type == "provider":
        node = result.get("provider_node", {})
        lines.append("## Provider")
        lines.append("")
        lines.append(f"- Node: `{node.get('node_id')}`")
        lines.append(f"- Label: `{node.get('label')}`")
        lines.append("")
        lines.append("## Artifacts")
        lines.append("")
        for artifact in result.get("artifacts", []):
            lines.append(
                f"- `{artifact.get('label') or artifact.get('artifact_node_id')}` "
                f"linked_papers=`{artifact.get('linked_papers_count')}`"
            )

    elif query_type == "topic_cluster":
        node = result.get("topic_cluster_node", {})
        lines.append("## Topic cluster")
        lines.append("")
        lines.append(f"- Node: `{node.get('node_id')}`")
        lines.append(f"- Label: `{node.get('label')}`")
        lines.append("")
        lines.append("## Artifact-ready papers")
        lines.append("")
        for paper in result.get("artifact_ready_papers", []):
            lines.append(
                f"- `{paper.get('label') or paper.get('paper_node_id')}` "
                f"artifacts=`{paper.get('artifacts_count')}`"
            )

    lines.append("")
    lines.append("## Manifest safety")
    lines.append("")
    for key, value in payload.get("manifest_safety", {}).items():
        lines.append(f"- {key}: `{value}`")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the local derived Paper-Artifact Graph output."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--graph-dir", type=Path, default=None)
    parser.add_argument("--paper-id", default=None)
    parser.add_argument("--artifact-id", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--topic-cluster", default=None)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    index = load_graph_index(config_path=args.config, graph_dir=args.graph_dir)
    result = query_graph(
        index,
        paper_id=args.paper_id,
        artifact_id=args.artifact_id,
        provider=args.provider,
        topic_cluster=args.topic_cluster,
        top_k=args.top_k,
    )
    payload = attach_meta(result, index)

    if args.format == "markdown":
        print(render_markdown(payload), end="")
    else:
        print(render_json(payload))


if __name__ == "__main__":
    main()