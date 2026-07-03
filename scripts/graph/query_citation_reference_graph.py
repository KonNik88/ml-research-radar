from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_GRAPH_DIR = Path("data/graphs/citation_reference_graph/v0.1")
GRAPH_NAME = "citation_reference_graph"
GRAPH_VERSION = "v0.1"
CAVEAT = (
    "This graph is built from explicit canonical metadata reference fields only. "
    "It does not parse paper full text, PDFs, or bibliography/reference sections. "
    "Unresolved references are preserved as external_reference nodes; low internal "
    "resolution ratio is expected for v0.1."
)


@dataclass(frozen=True)
class GraphPaths:
    graph_dir: Path
    nodes_path: Path
    edges_path: Path
    manifest_path: Path
    data_quality_summary_path: Path


@dataclass
class GraphIndex:
    nodes_by_id: dict[str, dict[str, Any]]
    paper_node_by_canonical_id: dict[str, str]
    external_node_by_reference_key: dict[str, str]
    external_node_by_normalized_value: dict[str, list[str]]
    source_family_node_by_family: dict[str, str]
    outgoing_by_type: dict[str, dict[str, list[dict[str, Any]]]]
    incoming_by_type: dict[str, dict[str, list[dict[str, Any]]]]
    manifest: dict[str, Any]
    data_quality_summary: dict[str, Any]
    paths: GraphPaths


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _graph_paths(graph_dir: Path) -> GraphPaths:
    return GraphPaths(
        graph_dir=graph_dir,
        nodes_path=graph_dir / "nodes.jsonl",
        edges_path=graph_dir / "edges.jsonl",
        manifest_path=graph_dir / "manifest.json",
        data_quality_summary_path=graph_dir / "data_quality_summary.json",
    )


def _node_type(node: dict[str, Any] | None) -> str | None:
    if not isinstance(node, dict):
        return None
    return str(node.get("node_type")) if node.get("node_type") is not None else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def _paper_node_id(value: str) -> str:
    return value if value.startswith("paper:") else f"paper:{value}"


def _source_family_node_id(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    return normalized if normalized.startswith("source_family:") else f"source_family:{normalized}"


def load_graph_index(graph_dir: Path | str = DEFAULT_GRAPH_DIR) -> GraphIndex:
    graph_dir = Path(graph_dir)
    paths = _graph_paths(graph_dir)

    missing = [str(path) for path in [paths.nodes_path, paths.edges_path, paths.manifest_path] if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing citation/reference graph files: " + ", ".join(missing))

    nodes = iter_jsonl(paths.nodes_path)
    edges = iter_jsonl(paths.edges_path)
    manifest = load_json(paths.manifest_path)
    quality = load_json(paths.data_quality_summary_path) if paths.data_quality_summary_path.exists() else {}

    nodes_by_id: dict[str, dict[str, Any]] = {}
    paper_node_by_canonical_id: dict[str, str] = {}
    external_node_by_reference_key: dict[str, str] = {}
    external_node_by_normalized_value: dict[str, list[str]] = defaultdict(list)
    source_family_node_by_family: dict[str, str] = {}

    for node in nodes:
        node_id = _string_or_none(node.get("node_id"))
        if not node_id:
            continue
        nodes_by_id[node_id] = node
        if node.get("node_type") == "paper":
            canonical_id = _string_or_none(node.get("canonical_id")) or _strip_prefix(node_id, "paper:")
            paper_node_by_canonical_id[canonical_id] = node_id
        elif node.get("node_type") == "external_reference":
            reference_key = _string_or_none(node.get("reference_key"))
            normalized_value = _string_or_none(node.get("normalized_value"))
            if reference_key:
                external_node_by_reference_key[reference_key] = node_id
            if normalized_value:
                external_node_by_normalized_value[normalized_value].append(node_id)
        elif node.get("node_type") == "source_family":
            family = _string_or_none(node.get("source_family")) or _strip_prefix(node_id, "source_family:")
            source_family_node_by_family[family] = node_id

    outgoing_by_type: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    incoming_by_type: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for edge in edges:
        edge_type = _string_or_none(edge.get("edge_type"))
        source_node_id = _string_or_none(edge.get("source_node_id"))
        target_node_id = _string_or_none(edge.get("target_node_id"))
        if not edge_type or not source_node_id or not target_node_id:
            continue
        outgoing_by_type[edge_type][source_node_id].append(edge)
        incoming_by_type[edge_type][target_node_id].append(edge)

    return GraphIndex(
        nodes_by_id=nodes_by_id,
        paper_node_by_canonical_id=paper_node_by_canonical_id,
        external_node_by_reference_key=dict(external_node_by_reference_key),
        external_node_by_normalized_value={key: sorted(value) for key, value in external_node_by_normalized_value.items()},
        source_family_node_by_family=source_family_node_by_family,
        outgoing_by_type={key: dict(value) for key, value in outgoing_by_type.items()},
        incoming_by_type={key: dict(value) for key, value in incoming_by_type.items()},
        manifest=manifest,
        data_quality_summary=quality,
        paths=paths,
    )


def node_label(node: dict[str, Any] | None) -> str | None:
    if not node:
        return None
    for key in ["title", "reference_key", "source_family", "canonical_id", "node_id"]:
        value = _string_or_none(node.get(key))
        if value:
            return value
    return None


def compact_paper(index: GraphIndex, node_id: str, edge: dict[str, Any] | None = None) -> dict[str, Any]:
    node = index.nodes_by_id.get(node_id, {})
    row = {
        "paper_node_id": node_id,
        "canonical_id": node.get("canonical_id") or _strip_prefix(node_id, "paper:"),
        "title": node.get("title"),
        "year": node.get("year"),
        "doi": node.get("doi"),
        "arxiv_id": node.get("arxiv_id"),
    }
    if edge:
        row.update(
            {
                "edge_id": edge.get("edge_id"),
                "reference_type": edge.get("reference_type"),
                "reference_value": edge.get("reference_value"),
                "reference_field": edge.get("reference_field"),
                "confidence": edge.get("confidence"),
            }
        )
    return row


def compact_external_reference(index: GraphIndex, node_id: str, edge: dict[str, Any] | None = None) -> dict[str, Any]:
    node = index.nodes_by_id.get(node_id, {})
    row = {
        "external_reference_node_id": node_id,
        "reference_key": node.get("reference_key") or edge.get("target_reference_key") if edge else node.get("reference_key"),
        "reference_type": node.get("reference_type") or edge.get("reference_type") if edge else node.get("reference_type"),
        "normalized_value": node.get("normalized_value"),
        "resolution_status": node.get("resolution_status"),
    }
    if edge:
        row.update(
            {
                "edge_id": edge.get("edge_id"),
                "source_canonical_id": edge.get("source_canonical_id"),
                "reference_field": edge.get("reference_field"),
                "confidence": edge.get("confidence"),
            }
        )
    return row


def _resolve_paper_node(index: GraphIndex, paper_id: str) -> str | None:
    if paper_id in index.nodes_by_id and _node_type(index.nodes_by_id[paper_id]) == "paper":
        return paper_id
    return index.paper_node_by_canonical_id.get(paper_id) or index.paper_node_by_canonical_id.get(_strip_prefix(paper_id, "paper:"))


def _resolve_external_node_ids(index: GraphIndex, external_reference: str) -> list[str]:
    if external_reference in index.nodes_by_id and _node_type(index.nodes_by_id[external_reference]) == "external_reference":
        return [external_reference]
    if external_reference in index.external_node_by_reference_key:
        return [index.external_node_by_reference_key[external_reference]]
    if external_reference in index.external_node_by_normalized_value:
        return index.external_node_by_normalized_value[external_reference]
    # Allow users to pass `doi:10.x/...`, `openalex_id:W...`, etc. and also raw normalized value.
    candidates = []
    for node_id, node in index.nodes_by_id.items():
        if node.get("node_type") != "external_reference":
            continue
        if external_reference in {node.get("reference_key"), node.get("normalized_value"), node_id}:
            candidates.append(node_id)
    return sorted(set(candidates))


def _reference_resolution_ratio(manifest: dict[str, Any]) -> float | None:
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    resolved = counts.get("paper_references_paper_edges_count")
    unresolved = counts.get("paper_references_external_edges_count")
    try:
        total = int(resolved) + int(unresolved)
        return round(int(resolved) / total, 6) if total else None
    except Exception:
        return None


def _top_internal_referenced_papers(index: GraphIndex, top_k: int) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    sample_edges: dict[str, dict[str, Any]] = {}
    for target_node_id, edges in index.incoming_by_type.get("paper_references_paper", {}).items():
        counter[target_node_id] += len(edges)
        if edges:
            sample_edges[target_node_id] = edges[0]
    rows = []
    for node_id, count in counter.most_common(top_k):
        row = compact_paper(index, node_id, sample_edges.get(node_id))
        row["incoming_internal_references_count"] = count
        rows.append(row)
    return rows


def _top_external_references(index: GraphIndex, top_k: int) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    sample_edges: dict[str, dict[str, Any]] = {}
    for target_node_id, edges in index.incoming_by_type.get("paper_references_external", {}).items():
        counter[target_node_id] += len(edges)
        if edges:
            sample_edges[target_node_id] = edges[0]
    rows = []
    for node_id, count in counter.most_common(top_k):
        row = compact_external_reference(index, node_id, sample_edges.get(node_id))
        row["citing_papers_count"] = count
        rows.append(row)
    return rows


def query_graph(
    index: GraphIndex,
    *,
    paper_id: str | None = None,
    cited_paper_id: str | None = None,
    external_reference: str | None = None,
    source_family: str | None = None,
    top_referenced_papers: bool = False,
    top_external_references: bool = False,
    top_k: int = 20,
) -> dict[str, Any]:
    selectors = [
        bool(paper_id),
        bool(cited_paper_id),
        bool(external_reference),
        bool(source_family),
        bool(top_referenced_papers),
        bool(top_external_references),
    ]
    if sum(selectors) != 1:
        raise ValueError("Provide exactly one query selector.")

    if paper_id:
        node_id = _resolve_paper_node(index, paper_id)
        if not node_id:
            return {"query_type": "paper", "found": False, "paper_id": paper_id, "counts": {}}
        internal_edges = index.outgoing_by_type.get("paper_references_paper", {}).get(node_id, [])
        external_edges = index.outgoing_by_type.get("paper_references_external", {}).get(node_id, [])
        source_edges = index.outgoing_by_type.get("paper_has_reference_source_family", {}).get(node_id, [])
        internal = [compact_paper(index, edge["target_node_id"], edge) for edge in internal_edges[:top_k]]
        external = [compact_external_reference(index, edge["target_node_id"], edge) for edge in external_edges[:top_k]]
        source_families = sorted({edge.get("source_family") or _strip_prefix(str(edge.get("target_node_id")), "source_family:") for edge in source_edges})
        return {
            "query_type": "paper",
            "found": True,
            "paper": compact_paper(index, node_id),
            "counts": {
                "internal_references": len(internal_edges),
                "external_references": len(external_edges),
                "source_families": len(source_families),
            },
            "internal_references": internal,
            "external_references": external,
            "source_families": source_families,
        }

    if cited_paper_id:
        node_id = _resolve_paper_node(index, cited_paper_id)
        if not node_id:
            return {"query_type": "cited_paper", "found": False, "paper_id": cited_paper_id, "counts": {}}
        incoming_edges = index.incoming_by_type.get("paper_references_paper", {}).get(node_id, [])
        citing_papers = [compact_paper(index, edge["source_node_id"], edge) for edge in incoming_edges[:top_k]]
        return {
            "query_type": "cited_paper",
            "found": True,
            "paper": compact_paper(index, node_id),
            "counts": {"incoming_internal_references": len(incoming_edges)},
            "citing_papers": citing_papers,
        }

    if external_reference:
        node_ids = _resolve_external_node_ids(index, external_reference)
        if not node_ids:
            return {"query_type": "external_reference", "found": False, "external_reference": external_reference, "counts": {}}
        citing_rows: list[dict[str, Any]] = []
        total_edges = 0
        references: list[dict[str, Any]] = []
        for node_id in node_ids:
            incoming_edges = index.incoming_by_type.get("paper_references_external", {}).get(node_id, [])
            total_edges += len(incoming_edges)
            references.append(compact_external_reference(index, node_id, incoming_edges[0] if incoming_edges else None))
            for edge in incoming_edges:
                citing_rows.append(compact_paper(index, edge["source_node_id"], edge))
        return {
            "query_type": "external_reference",
            "found": True,
            "external_reference_query": external_reference,
            "references": references[:top_k],
            "counts": {"matched_external_reference_nodes": len(node_ids), "citing_papers": total_edges},
            "citing_papers": citing_rows[:top_k],
        }

    if source_family:
        normalized = source_family.strip().lower().replace(" ", "_")
        node_id = index.source_family_node_by_family.get(normalized) or _source_family_node_id(normalized)
        if node_id not in index.nodes_by_id:
            return {"query_type": "source_family", "found": False, "source_family": normalized, "counts": {}}
        incoming_edges = index.incoming_by_type.get("paper_has_reference_source_family", {}).get(node_id, [])
        papers = [compact_paper(index, edge["source_node_id"], edge) for edge in incoming_edges[:top_k]]
        return {
            "query_type": "source_family",
            "found": True,
            "source_family": normalized,
            "counts": {"reference_bearing_papers": len(incoming_edges)},
            "papers": papers,
        }

    if top_referenced_papers:
        rows = _top_internal_referenced_papers(index, top_k)
        return {
            "query_type": "top_referenced_papers",
            "found": bool(rows),
            "counts": {"papers": len(rows)},
            "papers": rows,
        }

    rows = _top_external_references(index, top_k)
    return {
        "query_type": "top_external_references",
        "found": bool(rows),
        "counts": {"external_references": len(rows)},
        "external_references": rows,
    }


def attach_meta(result: dict[str, Any], index: GraphIndex) -> dict[str, Any]:
    counts = index.manifest.get("counts") if isinstance(index.manifest.get("counts"), dict) else {}
    payload = dict(result)
    payload["meta"] = {
        "graph_name": GRAPH_NAME,
        "graph_version": GRAPH_VERSION,
        "graph_dir": str(index.paths.graph_dir),
        "nodes_count": counts.get("nodes_count"),
        "edges_count": counts.get("edges_count"),
        "paper_references_paper_edges_count": counts.get("paper_references_paper_edges_count"),
        "paper_references_external_edges_count": counts.get("paper_references_external_edges_count"),
        "reference_resolution_ratio": _reference_resolution_ratio(index.manifest),
        "caveat": CAVEAT,
        "read_only": True,
    }
    return payload


def _format_rows(rows: list[dict[str, Any]], label_keys: list[str], limit: int = 20) -> list[str]:
    if not rows:
        return ["No rows."]
    out: list[str] = []
    for row in rows[:limit]:
        label = None
        for key in label_keys:
            value = row.get(key)
            if value not in (None, ""):
                label = value
                break
        label = label or row.get("paper_node_id") or row.get("external_reference_node_id") or "row"
        details = []
        for key in [
            "canonical_id",
            "year",
            "reference_key",
            "reference_type",
            "reference_field",
            "incoming_internal_references_count",
            "citing_papers_count",
        ]:
            value = row.get(key)
            if value not in (None, ""):
                details.append(f"{key}={value}")
        suffix = f" — {', '.join(details)}" if details else ""
        out.append(f"- `{label}`{suffix}")
    return out


def render_markdown(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    lines = [
        "# Citation / Reference Graph Query",
        "",
        "```text",
        f"query_type={payload.get('query_type')}",
        f"found={payload.get('found')}",
        f"nodes_count={meta.get('nodes_count')}",
        f"edges_count={meta.get('edges_count')}",
        f"reference_resolution_ratio={meta.get('reference_resolution_ratio')}",
        "```",
        "",
        "## Caveat",
        "",
        str(meta.get("caveat") or CAVEAT),
        "",
        "## Counts",
        "",
        "```text",
    ]
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    if counts:
        lines.extend(f"{key}={value}" for key, value in sorted(counts.items()))
    else:
        lines.append("No counts.")
    lines.extend(["```", ""])

    sections = [
        ("Paper", payload.get("paper"), ["title", "canonical_id"]),
        ("Internal references", payload.get("internal_references"), ["title", "canonical_id"]),
        ("External references", payload.get("external_references"), ["reference_key", "normalized_value"]),
        ("References", payload.get("references"), ["reference_key", "normalized_value"]),
        ("Citing papers", payload.get("citing_papers"), ["title", "canonical_id"]),
        ("Papers", payload.get("papers"), ["title", "canonical_id"]),
    ]
    for title, value, label_keys in sections:
        if not value:
            continue
        lines.extend([f"## {title}", ""])
        if isinstance(value, list):
            lines.extend(_format_rows(value, label_keys))
        elif isinstance(value, dict):
            lines.extend(_format_rows([value], label_keys))
        lines.append("")

    source_families = payload.get("source_families")
    if source_families:
        lines.extend(["## Source families", ""])
        lines.extend(f"- `{item}`" for item in source_families)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only offline queries over Citation / Reference Graph v0.1 output.")
    parser.add_argument("--graph-dir", default=str(DEFAULT_GRAPH_DIR), help="Generated citation/reference graph output directory.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--paper", dest="paper_id", help="Canonical paper ID or paper:<canonical_id>; returns outgoing references.")
    group.add_argument("--cited-paper", dest="cited_paper_id", help="Canonical paper ID or paper:<canonical_id>; returns incoming internal citing papers.")
    group.add_argument("--external-reference", help="External reference node ID, reference_key, or normalized value; returns citing papers.")
    group.add_argument("--source-family", help="Source family; returns papers with reference evidence from that family.")
    group.add_argument("--top-referenced-papers", action="store_true", help="Return most cited internal canonical papers.")
    group.add_argument("--top-external-references", action="store_true", help="Return most cited unresolved external references.")
    parser.add_argument("--top-k", type=int, default=20, help="Maximum rows to print per result section.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    index = load_graph_index(args.graph_dir)
    result = query_graph(
        index,
        paper_id=args.paper_id,
        cited_paper_id=args.cited_paper_id,
        external_reference=args.external_reference,
        source_family=args.source_family,
        top_referenced_papers=args.top_referenced_papers,
        top_external_references=args.top_external_references,
        top_k=args.top_k,
    )
    payload = attach_meta(result, index)
    if args.format == "markdown":
        print(render_markdown(payload), end="")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
