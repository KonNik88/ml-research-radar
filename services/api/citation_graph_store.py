from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


GRAPH_NAME = "citation_reference_graph"
GRAPH_VERSION = "v0.1"
DEFAULT_GRAPH_DIR = Path("data/graphs/citation_reference_graph/v0.1")
DEFAULT_LIMIT = 50
MAX_LIMIT = 100

PAPER_REFERENCES_PAPER = "paper_references_paper"
PAPER_REFERENCES_EXTERNAL = "paper_references_external"
PAPER_HAS_REFERENCE_SOURCE_FAMILY = "paper_has_reference_source_family"


@dataclass(frozen=True)
class CitationGraphPaths:
    graph_dir: Path
    nodes_path: Path
    edges_path: Path
    manifest_path: Path
    data_quality_summary_path: Path


@dataclass(frozen=True)
class CitationGraphPage:
    limit: int
    offset: int
    returned: int
    total_estimate: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "offset": self.offset,
            "returned": self.returned,
            "total_estimate": self.total_estimate,
        }


@dataclass(frozen=True)
class CitationGraphQueryResult:
    found: bool
    query: dict[str, Any]
    items: list[dict[str, Any]]
    page: CitationGraphPage

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "query": self.query,
            "items": self.items,
            "page": self.page.to_dict(),
        }


@dataclass(frozen=True)
class CitationGraphStore:
    """Small read-only query store for validated citation/reference graph files.

    This class is intentionally file-backed and side-effect free. It is meant to
    support fixture-backed query semantics before exposing traversal endpoints.
    It must not rebuild graph outputs, write reports, mutate runtime state, or
    require NetworkX/Neo4j/GraphRAG.
    """

    paths: CitationGraphPaths
    manifest: dict[str, Any]
    data_quality_summary: dict[str, Any]
    nodes_by_id: dict[str, dict[str, Any]]
    edges_by_id: dict[str, dict[str, Any]]
    paper_node_by_canonical_id: dict[str, str]
    external_node_by_reference_key: dict[str, str]
    external_node_by_normalized_value: dict[str, list[str]]
    source_family_node_by_family: dict[str, str]
    outgoing_by_type: dict[str, dict[str, list[dict[str, Any]]]]
    incoming_by_type: dict[str, dict[str, list[dict[str, Any]]]]

    @classmethod
    def load(cls, graph_dir: str | Path = DEFAULT_GRAPH_DIR) -> "CitationGraphStore":
        paths = _graph_paths(Path(graph_dir))
        _require_paths(
            paths.nodes_path,
            paths.edges_path,
            paths.manifest_path,
            paths.data_quality_summary_path,
        )

        manifest = _read_json_object(paths.manifest_path)
        data_quality_summary = _read_json_object(paths.data_quality_summary_path)
        nodes = _read_jsonl_objects(paths.nodes_path)
        edges = _read_jsonl_objects(paths.edges_path)

        nodes_by_id: dict[str, dict[str, Any]] = {}
        paper_node_by_canonical_id: dict[str, str] = {}
        external_node_by_reference_key: dict[str, str] = {}
        external_node_by_normalized_value: dict[str, list[str]] = defaultdict(list)
        source_family_node_by_family: dict[str, str] = {}

        for node in nodes:
            node_id = _required_string(node, "node_id", path=paths.nodes_path)
            if node_id in nodes_by_id:
                raise ValueError(f"Duplicate citation graph node_id: {node_id}")

            node_type = _required_string(node, "node_type", path=paths.nodes_path)
            nodes_by_id[node_id] = node

            if node_type == "paper":
                canonical_id = _string_or_none(node.get("canonical_id")) or _strip_prefix(
                    node_id,
                    "paper:",
                )
                paper_node_by_canonical_id[canonical_id] = node_id
                paper_node_by_canonical_id[node_id] = node_id
            elif node_type == "external_reference":
                reference_key = _string_or_none(node.get("reference_key"))
                normalized_value = _string_or_none(node.get("normalized_value"))
                if reference_key:
                    external_node_by_reference_key[reference_key] = node_id
                if normalized_value:
                    external_node_by_normalized_value[normalized_value].append(node_id)
            elif node_type == "source_family":
                source_family = _normalize_source_family(
                    _string_or_none(node.get("source_family"))
                    or _strip_prefix(node_id, "source_family:"),
                )
                if source_family:
                    source_family_node_by_family[source_family] = node_id

        edges_by_id: dict[str, dict[str, Any]] = {}
        outgoing_by_type: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        incoming_by_type: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for edge in edges:
            edge_id = _required_string(edge, "edge_id", path=paths.edges_path)
            if edge_id in edges_by_id:
                raise ValueError(f"Duplicate citation graph edge_id: {edge_id}")

            edge_type = _required_string(edge, "edge_type", path=paths.edges_path)
            source_node_id = _required_string(edge, "source_node_id", path=paths.edges_path)
            target_node_id = _required_string(edge, "target_node_id", path=paths.edges_path)

            if source_node_id not in nodes_by_id:
                raise ValueError(
                    "Citation graph edge references missing source node: "
                    f"edge_id={edge_id!r} source_node_id={source_node_id!r}"
                )
            if target_node_id not in nodes_by_id:
                raise ValueError(
                    "Citation graph edge references missing target node: "
                    f"edge_id={edge_id!r} target_node_id={target_node_id!r}"
                )

            edges_by_id[edge_id] = edge
            outgoing_by_type[edge_type][source_node_id].append(edge)
            incoming_by_type[edge_type][target_node_id].append(edge)

        return cls(
            paths=paths,
            manifest=manifest,
            data_quality_summary=data_quality_summary,
            nodes_by_id=nodes_by_id,
            edges_by_id=edges_by_id,
            paper_node_by_canonical_id=dict(paper_node_by_canonical_id),
            external_node_by_reference_key=dict(external_node_by_reference_key),
            external_node_by_normalized_value={
                key: sorted(set(value))
                for key, value in external_node_by_normalized_value.items()
            },
            source_family_node_by_family=dict(source_family_node_by_family),
            outgoing_by_type=_freeze_nested_edge_index(outgoing_by_type),
            incoming_by_type=_freeze_nested_edge_index(incoming_by_type),
        )

    def graph_summary(self) -> dict[str, Any]:
        counts = self.manifest.get("counts")
        if not isinstance(counts, dict):
            counts = {}

        return {
            "name": str(self.manifest.get("graph_name") or GRAPH_NAME),
            "version": str(self.manifest.get("graph_version") or GRAPH_VERSION),
            "nodes_count": _safe_int(counts.get("nodes_count"), len(self.nodes_by_id)),
            "edges_count": _safe_int(counts.get("edges_count"), len(self.edges_by_id)),
            "paper_nodes": _safe_int(
                counts.get("paper_nodes_count") or counts.get("paper_nodes"),
                _count_nodes_by_type(self.nodes_by_id.values(), "paper"),
            ),
            "external_reference_nodes": _safe_int(
                counts.get("external_reference_nodes_count")
                or counts.get("external_reference_nodes"),
                _count_nodes_by_type(self.nodes_by_id.values(), "external_reference"),
            ),
            "source_family_nodes": _safe_int(
                counts.get("source_family_nodes_count")
                or counts.get("source_family_nodes"),
                _count_nodes_by_type(self.nodes_by_id.values(), "source_family"),
            ),
            "paper_references_paper_edges": _safe_int(
                counts.get("paper_references_paper_edges_count")
                or counts.get("paper_references_paper_edges"),
                len(self._all_edges(PAPER_REFERENCES_PAPER)),
            ),
            "paper_references_external_edges": _safe_int(
                counts.get("paper_references_external_edges_count")
                or counts.get("paper_references_external_edges"),
                len(self._all_edges(PAPER_REFERENCES_EXTERNAL)),
            ),
            "paper_has_reference_source_family_edges": _safe_int(
                counts.get("paper_has_reference_source_family_edges_count")
                or counts.get("paper_has_reference_source_family_edges"),
                len(self._all_edges(PAPER_HAS_REFERENCE_SOURCE_FAMILY)),
            ),
            "resolved_reference_edges": len(self._all_edges(PAPER_REFERENCES_PAPER)),
            "unresolved_reference_edges": len(self._all_edges(PAPER_REFERENCES_EXTERNAL)),
            "reference_resolution_ratio": self.reference_resolution_ratio(),
            "metadata_reference_fields_only": True,
            "full_text_parsed": False,
            "pdfs_parsed": False,
            "bibliography_sections_parsed": False,
            "manual_review_required": True,
            "manual_review_complete": False,
            "publication_ready": False,
            "may_be_used_as_reconcile_input": False,
            "not_a_complete_citation_index": True,
        }

    def reference_resolution_ratio(self) -> float | None:
        resolved = len(self._all_edges(PAPER_REFERENCES_PAPER))
        unresolved = len(self._all_edges(PAPER_REFERENCES_EXTERNAL))
        total = resolved + unresolved
        if total <= 0:
            return None
        return round(resolved / total, 6)

    def outgoing_references(
        self,
        canonical_id: str,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> CitationGraphQueryResult:
        limit, offset = _normalize_page_params(limit=limit, offset=offset)
        node_id = self._resolve_paper_node_id(canonical_id)
        query = {
            "endpoint": "/citation-graph/papers/{canonical_id}/references",
            "canonical_id": canonical_id,
            "limit": limit,
            "offset": offset,
            "reference_type": None,
            "resolved": None,
            "source_family": None,
        }

        if node_id is None:
            return _empty_result(found=False, query=query, limit=limit, offset=offset)

        internal_edges = self.outgoing_by_type.get(PAPER_REFERENCES_PAPER, {}).get(
            node_id,
            [],
        )
        external_edges = self.outgoing_by_type.get(PAPER_REFERENCES_EXTERNAL, {}).get(
            node_id,
            [],
        )

        items = [
            self._paper_reference_item(edge)
            for edge in internal_edges
        ] + [
            self._external_reference_item(edge)
            for edge in external_edges
        ]
        items = _sort_items_by_edge_id(items)
        page_items, page = _page_items(items, limit=limit, offset=offset)
        return CitationGraphQueryResult(found=True, query=query, items=page_items, page=page)

    def incoming_citations(
        self,
        canonical_id: str,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> CitationGraphQueryResult:
        limit, offset = _normalize_page_params(limit=limit, offset=offset)
        node_id = self._resolve_paper_node_id(canonical_id)
        query = {
            "endpoint": "/citation-graph/papers/{canonical_id}/citations",
            "canonical_id": canonical_id,
            "limit": limit,
            "offset": offset,
            "source_family": None,
        }

        if node_id is None:
            return _empty_result(found=False, query=query, limit=limit, offset=offset)

        edges = self.incoming_by_type.get(PAPER_REFERENCES_PAPER, {}).get(node_id, [])
        items = _sort_items_by_edge_id([
            self._incoming_citation_item(edge)
            for edge in edges
        ])
        page_items, page = _page_items(items, limit=limit, offset=offset)
        return CitationGraphQueryResult(found=True, query=query, items=page_items, page=page)

    def external_reference_papers(
        self,
        reference_id: str,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> CitationGraphQueryResult:
        limit, offset = _normalize_page_params(limit=limit, offset=offset)
        node_ids = self._resolve_external_reference_node_ids(reference_id)
        query = {
            "endpoint": "/citation-graph/external-references/{reference_id}/papers",
            "external_reference_id": reference_id,
            "limit": limit,
            "offset": offset,
        }

        if not node_ids:
            return _empty_result(found=False, query=query, limit=limit, offset=offset)

        items: list[dict[str, Any]] = []
        for node_id in node_ids:
            edges = self.incoming_by_type.get(PAPER_REFERENCES_EXTERNAL, {}).get(
                node_id,
                [],
            )
            items.extend(self._external_reference_paper_item(edge) for edge in edges)

        items = _sort_items_by_edge_id(items)
        page_items, page = _page_items(items, limit=limit, offset=offset)
        return CitationGraphQueryResult(found=True, query=query, items=page_items, page=page)

    def source_family_diagnostics(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> CitationGraphQueryResult:
        limit, offset = _normalize_page_params(limit=limit, offset=offset)
        rows: list[dict[str, Any]] = []

        for source_family, node_id in sorted(self.source_family_node_by_family.items()):
            source_edges = self.incoming_by_type.get(
                PAPER_HAS_REFERENCE_SOURCE_FAMILY,
                {},
            ).get(node_id, [])
            paper_node_ids = {
                str(edge.get("source_node_id"))
                for edge in source_edges
                if edge.get("source_node_id")
            }
            resolved_count = sum(
                len(self.outgoing_by_type.get(PAPER_REFERENCES_PAPER, {}).get(paper_id, []))
                for paper_id in paper_node_ids
            )
            external_count = sum(
                len(self.outgoing_by_type.get(PAPER_REFERENCES_EXTERNAL, {}).get(paper_id, []))
                for paper_id in paper_node_ids
            )
            rows.append(
                {
                    "source_family": source_family,
                    "paper_count_with_reference_evidence": len(paper_node_ids),
                    "reference_edge_count": resolved_count + external_count,
                    "resolved_edge_count": resolved_count,
                    "external_edge_count": external_count,
                }
            )

        page_items, page = _page_items(rows, limit=limit, offset=offset)
        return CitationGraphQueryResult(
            found=bool(rows),
            query={"endpoint": "/citation-graph/source-families"},
            items=page_items,
            page=page,
        )

    def top_referenced_papers(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> CitationGraphQueryResult:
        limit, offset = _normalize_page_params(limit=limit, offset=offset)
        counter: Counter[str] = Counter()
        source_families: dict[str, set[str]] = defaultdict(set)

        for target_node_id, edges in self.incoming_by_type.get(PAPER_REFERENCES_PAPER, {}).items():
            counter[target_node_id] += len(edges)
            for edge in edges:
                source_families[target_node_id].update(_edge_source_families(edge))

        items: list[dict[str, Any]] = []
        for target_node_id, count in counter.most_common():
            node = self.nodes_by_id.get(target_node_id, {})
            items.append(
                {
                    "canonical_id": _paper_canonical_id(node, target_node_id),
                    "title": node.get("title"),
                    "year": node.get("year"),
                    "incoming_resolved_reference_count": count,
                    "source_families": sorted(source_families.get(target_node_id, set())),
                }
            )

        page_items, page = _page_items(items, limit=limit, offset=offset)
        return CitationGraphQueryResult(
            found=bool(items),
            query={
                "endpoint": "/citation-graph/top-referenced-papers",
                "limit": limit,
                "offset": offset,
                "year_from": None,
                "year_to": None,
                "source_family": None,
            },
            items=page_items,
            page=page,
        )

    def top_external_references(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> CitationGraphQueryResult:
        limit, offset = _normalize_page_params(limit=limit, offset=offset)
        counter: Counter[str] = Counter()
        source_families: dict[str, set[str]] = defaultdict(set)

        for target_node_id, edges in self.incoming_by_type.get(PAPER_REFERENCES_EXTERNAL, {}).items():
            counter[target_node_id] += len(edges)
            for edge in edges:
                source_families[target_node_id].update(_edge_source_families(edge))

        items: list[dict[str, Any]] = []
        for target_node_id, count in counter.most_common():
            node = self.nodes_by_id.get(target_node_id, {})
            items.append(
                {
                    "external_reference_id": target_node_id,
                    "reference_type": node.get("reference_type"),
                    "normalized_reference": node.get("normalized_value"),
                    "referencing_paper_count": count,
                    "source_families": sorted(source_families.get(target_node_id, set())),
                }
            )

        page_items, page = _page_items(items, limit=limit, offset=offset)
        return CitationGraphQueryResult(
            found=bool(items),
            query={
                "endpoint": "/citation-graph/top-external-references",
                "limit": limit,
                "offset": offset,
                "reference_type": None,
                "source_family": None,
            },
            items=page_items,
            page=page,
        )

    def _all_edges(self, edge_type: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for edges in self.outgoing_by_type.get(edge_type, {}).values():
            rows.extend(edges)
        return rows

    def _resolve_paper_node_id(self, canonical_id: str) -> str | None:
        text = str(canonical_id).strip()
        if not text:
            return None
        if text in self.nodes_by_id and self.nodes_by_id[text].get("node_type") == "paper":
            return text
        return self.paper_node_by_canonical_id.get(text)

    def _resolve_external_reference_node_ids(self, reference_id: str) -> list[str]:
        text = str(reference_id).strip()
        if not text:
            return []
        if text in self.nodes_by_id and self.nodes_by_id[text].get("node_type") == "external_reference":
            return [text]
        if text in self.external_node_by_reference_key:
            return [self.external_node_by_reference_key[text]]
        if text in self.external_node_by_normalized_value:
            return self.external_node_by_normalized_value[text]
        return []

    def _paper_reference_item(self, edge: dict[str, Any]) -> dict[str, Any]:
        source_node = self.nodes_by_id.get(str(edge.get("source_node_id")), {})
        target_node = self.nodes_by_id.get(str(edge.get("target_node_id")), {})
        return {
            "edge_id": edge.get("edge_id"),
            "edge_type": PAPER_REFERENCES_PAPER,
            "source_canonical_id": _paper_canonical_id(source_node, str(edge.get("source_node_id"))),
            "target_canonical_id": _paper_canonical_id(target_node, str(edge.get("target_node_id"))),
            "target_title": target_node.get("title"),
            "target_year": target_node.get("year"),
            "reference_type": edge.get("reference_type"),
            "normalized_reference": _edge_normalized_reference(edge, target_node),
            "source_families": _edge_source_families(edge),
            "evidence_count": _safe_int(edge.get("evidence_count"), 1),
            "resolved": True,
        }

    def _external_reference_item(self, edge: dict[str, Any]) -> dict[str, Any]:
        source_node = self.nodes_by_id.get(str(edge.get("source_node_id")), {})
        target_node_id = str(edge.get("target_node_id"))
        target_node = self.nodes_by_id.get(target_node_id, {})
        return {
            "edge_id": edge.get("edge_id"),
            "edge_type": PAPER_REFERENCES_EXTERNAL,
            "source_canonical_id": _paper_canonical_id(source_node, str(edge.get("source_node_id"))),
            "external_reference_id": target_node_id,
            "reference_type": edge.get("reference_type") or target_node.get("reference_type"),
            "normalized_reference": _edge_normalized_reference(edge, target_node),
            "source_families": _edge_source_families(edge),
            "evidence_count": _safe_int(edge.get("evidence_count"), 1),
            "resolved": False,
        }

    def _incoming_citation_item(self, edge: dict[str, Any]) -> dict[str, Any]:
        source_node_id = str(edge.get("source_node_id"))
        target_node_id = str(edge.get("target_node_id"))
        source_node = self.nodes_by_id.get(source_node_id, {})
        target_node = self.nodes_by_id.get(target_node_id, {})
        return {
            "edge_id": edge.get("edge_id"),
            "edge_type": PAPER_REFERENCES_PAPER,
            "source_canonical_id": _paper_canonical_id(source_node, source_node_id),
            "source_title": source_node.get("title"),
            "source_year": source_node.get("year"),
            "target_canonical_id": _paper_canonical_id(target_node, target_node_id),
            "reference_type": edge.get("reference_type"),
            "normalized_reference": _edge_normalized_reference(edge, target_node),
            "source_families": _edge_source_families(edge),
            "evidence_count": _safe_int(edge.get("evidence_count"), 1),
        }

    def _external_reference_paper_item(self, edge: dict[str, Any]) -> dict[str, Any]:
        source_node_id = str(edge.get("source_node_id"))
        target_node_id = str(edge.get("target_node_id"))
        source_node = self.nodes_by_id.get(source_node_id, {})
        target_node = self.nodes_by_id.get(target_node_id, {})
        return {
            "edge_id": edge.get("edge_id"),
            "source_canonical_id": _paper_canonical_id(source_node, source_node_id),
            "source_title": source_node.get("title"),
            "source_year": source_node.get("year"),
            "external_reference_id": target_node_id,
            "reference_type": edge.get("reference_type") or target_node.get("reference_type"),
            "normalized_reference": _edge_normalized_reference(edge, target_node),
            "source_families": _edge_source_families(edge),
            "evidence_count": _safe_int(edge.get("evidence_count"), 1),
        }


def _graph_paths(graph_dir: Path) -> CitationGraphPaths:
    return CitationGraphPaths(
        graph_dir=graph_dir,
        nodes_path=graph_dir / "nodes.jsonl",
        edges_path=graph_dir / "edges.jsonl",
        manifest_path=graph_dir / "manifest.json",
        data_quality_summary_path=graph_dir / "data_quality_summary.json",
    )


def _require_paths(*paths: Path) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing citation/reference graph fixture files: " + ", ".join(missing)
        )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL row in {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Expected JSON object in {path}:{line_no}")
            rows.append(row)
    return rows


def _required_string(row: dict[str, Any], key: str, *, path: Path) -> str:
    value = _string_or_none(row.get(key))
    if value is None:
        raise ValueError(f"Missing required field {key!r} in {path}: {row}")
    return value


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def _normalize_source_family(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower().replace(" ", "_")
    return _strip_prefix(text, "source_family:") if text else None


def _freeze_nested_edge_index(
    index: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        edge_type: {
            node_id: list(edges)
            for node_id, edges in by_node.items()
        }
        for edge_type, by_node in index.items()
    }


def _count_nodes_by_type(nodes: Iterable[dict[str, Any]], node_type: str) -> int:
    return sum(1 for node in nodes if node.get("node_type") == node_type)


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_page_params(*, limit: int, offset: int) -> tuple[int, int]:
    try:
        resolved_limit = int(limit)
        resolved_offset = int(offset)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be integers") from exc

    if resolved_limit < 1:
        raise ValueError("limit must be >= 1")
    if resolved_limit > MAX_LIMIT:
        raise ValueError(f"limit must be <= {MAX_LIMIT}")
    if resolved_offset < 0:
        raise ValueError("offset must be >= 0")

    return resolved_limit, resolved_offset


def _page_items(
    items: list[dict[str, Any]],
    *,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], CitationGraphPage]:
    page_items = items[offset : offset + limit]
    return page_items, CitationGraphPage(
        limit=limit,
        offset=offset,
        returned=len(page_items),
        total_estimate=len(items),
    )


def _empty_result(
    *,
    found: bool,
    query: dict[str, Any],
    limit: int,
    offset: int,
) -> CitationGraphQueryResult:
    return CitationGraphQueryResult(
        found=found,
        query=query,
        items=[],
        page=CitationGraphPage(
            limit=limit,
            offset=offset,
            returned=0,
            total_estimate=0,
        ),
    )


def _paper_canonical_id(node: dict[str, Any], node_id: str) -> str:
    return str(node.get("canonical_id") or _strip_prefix(node_id, "paper:"))


def _edge_normalized_reference(
    edge: dict[str, Any],
    target_node: dict[str, Any],
) -> str | None:
    return _string_or_none(
        edge.get("normalized_reference")
        or edge.get("reference_value")
        or target_node.get("normalized_value")
        or target_node.get("doi")
        or target_node.get("arxiv_id")
        or target_node.get("openalex_id")
    )


def _edge_source_families(edge: dict[str, Any]) -> list[str]:
    value = edge.get("source_families")
    if isinstance(value, list):
        families = [_normalize_source_family(str(item)) for item in value]
    else:
        families = [_normalize_source_family(_string_or_none(edge.get("source_family")))]
    return sorted({family for family in families if family})


def _sort_items_by_edge_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get("edge_id") or ""))
