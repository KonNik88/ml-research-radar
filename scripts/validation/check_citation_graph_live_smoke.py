from __future__ import annotations

import argparse
import json
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SCHEMA_VERSION = "citation_graph_live_smoke_v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_GRAPH_ROOT = Path("data/graphs/citation_reference_graph/v0.1")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")
DEFAULT_LIMIT = 5
DEFAULT_INVALID_LIMIT = 101
DEFAULT_TIMEOUT_SEC = 300.0

PAPER_REFERENCES_PAPER = "paper_references_paper"
PAPER_REFERENCES_EXTERNAL = "paper_references_external"

COMMON_CAVEATS = {
    "metadata_reference_fields_only",
    "not_a_complete_citation_index",
    "manual_review_required",
    "publication_ready_false",
}


@dataclass(frozen=True)
class SmokeSamples:
    references_canonical_id: str
    citations_canonical_id: str
    external_reference_id: str
    paper_reference_edge_id: str
    external_reference_edge_id: str


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Bad JSONL row in {path}:{line_no}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Expected JSON object in {path}:{line_no}")
            yield payload


def _required_text(payload: dict[str, Any], field_name: str, *, path: Path) -> str:
    value = payload.get(field_name)
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing {field_name!r} in {path}: {payload}")
    return text


def _canonical_id_from_node_id(node_id: str) -> str:
    prefix = "paper:"
    return node_id[len(prefix):] if node_id.startswith(prefix) else node_id


def resolve_smoke_samples(graph_root: Path) -> SmokeSamples:
    edges_path = graph_root / "edges.jsonl"
    nodes_path = graph_root / "nodes.jsonl"

    if not edges_path.is_file():
        raise FileNotFoundError(f"Citation graph edges file not found: {edges_path}")
    if not nodes_path.is_file():
        raise FileNotFoundError(f"Citation graph nodes file not found: {nodes_path}")

    paper_edge: dict[str, Any] | None = None
    external_edge: dict[str, Any] | None = None

    for edge in _iter_jsonl(edges_path):
        edge_type = str(edge.get("edge_type") or "").strip()
        if edge_type == PAPER_REFERENCES_PAPER and paper_edge is None:
            paper_edge = edge
        elif edge_type == PAPER_REFERENCES_EXTERNAL and external_edge is None:
            external_edge = edge

        if paper_edge is not None and external_edge is not None:
            break

    if paper_edge is None:
        raise ValueError(
            f"No {PAPER_REFERENCES_PAPER!r} edge found in {edges_path}"
        )
    if external_edge is None:
        raise ValueError(
            f"No {PAPER_REFERENCES_EXTERNAL!r} edge found in {edges_path}"
        )

    paper_source_node_id = _required_text(
        paper_edge,
        "source_node_id",
        path=edges_path,
    )
    paper_target_node_id = _required_text(
        paper_edge,
        "target_node_id",
        path=edges_path,
    )
    external_target_node_id = _required_text(
        external_edge,
        "target_node_id",
        path=edges_path,
    )

    needed_paper_nodes = {paper_source_node_id, paper_target_node_id}
    canonical_ids: dict[str, str] = {}

    for node in _iter_jsonl(nodes_path):
        node_id = str(node.get("node_id") or "").strip()
        if node_id not in needed_paper_nodes:
            continue

        canonical_id = str(node.get("canonical_id") or "").strip()
        canonical_ids[node_id] = canonical_id or _canonical_id_from_node_id(node_id)

        if len(canonical_ids) == len(needed_paper_nodes):
            break

    references_canonical_id = canonical_ids.get(
        paper_source_node_id,
        _canonical_id_from_node_id(paper_source_node_id),
    )
    citations_canonical_id = canonical_ids.get(
        paper_target_node_id,
        _canonical_id_from_node_id(paper_target_node_id),
    )

    return SmokeSamples(
        references_canonical_id=references_canonical_id,
        citations_canonical_id=citations_canonical_id,
        external_reference_id=external_target_node_id,
        paper_reference_edge_id=_required_text(
            paper_edge,
            "edge_id",
            path=edges_path,
        ),
        external_reference_edge_id=_required_text(
            external_edge,
            "edge_id",
            path=edges_path,
        ),
    )


def encode_path_segment(value: str) -> str:
    return quote(value, safe="")


def _decode_json_bytes(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def request_json(
    base_url: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    query = urlencode(params or {}, doseq=True)
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"

    request = Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout_sec) as response:
            body = response.read()
            status_code = int(response.status)
            payload = _decode_json_bytes(body)
            return {
                "path": path,
                "params": params or {},
                "url": url,
                "status_code": status_code,
                "ok": 200 <= status_code < 300,
                "json": payload,
                "error": None,
            }
    except HTTPError as exc:
        body = exc.read()
        return {
            "path": path,
            "params": params or {},
            "url": url,
            "status_code": int(exc.code),
            "ok": False,
            "json": _decode_json_bytes(body),
            "error": str(exc),
        }
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        return {
            "path": path,
            "params": params or {},
            "url": url,
            "status_code": None,
            "ok": False,
            "json": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _payload(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("json")
    return value if isinstance(value, dict) else {}


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("items")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _caveats(payload: dict[str, Any]) -> set[str]:
    value = payload.get("caveats")
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value}


def _endpoint_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "json"}


def _status_code_is(result: dict[str, Any], expected: int) -> bool:
    return result.get("status_code") == expected


def _error_code_is(result: dict[str, Any], expected: str) -> bool:
    return _payload(result).get("error_code") == expected


def _request(
    base_url: str,
    path: str,
    *,
    params: dict[str, Any] | None,
    timeout_sec: float,
) -> dict[str, Any]:
    return request_json(
        base_url,
        path,
        params=params,
        timeout_sec=timeout_sec,
    )


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Citation Graph live smoke",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- run_ts: `{report['run_ts']}`",
        f"- strict: `{report['strict']}`",
        "",
        "## Inputs",
        "",
    ]

    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Samples", ""])
    for key, value in report["samples"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Summary", ""])
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Checks", ""])
    for name, value in report["checks"].items():
        marker = "OK" if value else "FAIL"
        lines.append(f"- {marker}: `{name}` = `{value}`")

    lines.extend(["", "## Endpoints", ""])
    for name, meta in report["endpoints"].items():
        lines.append(f"### {name}")
        for key, value in meta.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    lines.extend(["## Observations", ""])
    for key, value in report["observations"].items():
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            rendered = value
        lines.append(f"- {key}: `{rendered}`")

    lines.extend(["", "## Verdict", ""])
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")

    return "\n".join(lines) + "\n"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    run_ts = utc_now_ts()
    base_url = str(args.base_url).rstrip("/")
    graph_root = Path(args.graph_root)
    limit = int(args.limit)
    invalid_limit = int(args.invalid_limit)
    timeout_sec = float(args.timeout_sec)

    samples = resolve_smoke_samples(graph_root)

    references_path = (
        "/citation-graph/papers/"
        f"{encode_path_segment(samples.references_canonical_id)}/references"
    )
    citations_path = (
        "/citation-graph/papers/"
        f"{encode_path_segment(samples.citations_canonical_id)}/citations"
    )
    external_path = (
        "/citation-graph/external-references/"
        f"{encode_path_segment(samples.external_reference_id)}/papers"
    )
    unknown_paper_path = (
        "/citation-graph/papers/"
        f"{encode_path_segment('__citation_graph_live_smoke_missing_paper__')}"
        "/references"
    )
    unknown_external_path = (
        "/citation-graph/external-references/"
        f"{encode_path_segment('__citation_graph_live_smoke_missing_external__')}"
        "/papers"
    )

    endpoints: dict[str, dict[str, Any]] = {}

    def call(
        name: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = _request(
            base_url,
            path,
            params=params,
            timeout_sec=timeout_sec,
        )
        endpoints[name] = _endpoint_meta(result)
        return result

    health = call("health", "/health")
    info = call("info", "/info")
    runtime = call("runtime", "/runtime")
    status = call("citation_graph_status", "/citation-graph/status")
    references = call("references", references_path, {"limit": limit, "offset": 0})
    citations = call("citations", citations_path, {"limit": limit, "offset": 0})
    external = call(
        "external_reference_papers",
        external_path,
        {"limit": limit, "offset": 0},
    )
    source_families = call(
        "source_families",
        "/citation-graph/source-families",
        {"limit": limit, "offset": 0},
    )
    top_referenced = call(
        "top_referenced_papers",
        "/citation-graph/top-referenced-papers",
        {"limit": limit, "offset": 0},
    )
    top_external = call(
        "top_external_references",
        "/citation-graph/top-external-references",
        {"limit": limit, "offset": 0},
    )
    unknown_paper = call("unknown_paper", unknown_paper_path)
    unknown_external = call("unknown_external_reference", unknown_external_path)
    invalid_limit_result = call(
        "limit_guard",
        references_path,
        {"limit": invalid_limit},
    )
    health_after_graph = call("health_after_graph", "/health")

    health_payload = _payload(health)
    info_payload = _payload(info)
    runtime_payload = _payload(runtime)
    status_payload = _payload(status)
    status_graph = status_payload.get("graph")
    status_graph = status_graph if isinstance(status_graph, dict) else {}
    availability = status_payload.get("availability")
    availability = availability if isinstance(availability, dict) else {}

    references_payload = _payload(references)
    citations_payload = _payload(citations)
    external_payload = _payload(external)
    source_families_payload = _payload(source_families)
    top_referenced_payload = _payload(top_referenced)
    top_external_payload = _payload(top_external)
    health_after_payload = _payload(health_after_graph)

    checks = {
        "health_status_200": _status_code_is(health, 200),
        "health_ready_true": health_payload.get("ready") is True,
        "info_status_200": _status_code_is(info, 200),
        "info_backend_file": info_payload.get("backend_mode") == "file",
        "runtime_status_200": _status_code_is(runtime, 200),
        "runtime_ready_true": runtime_payload.get("ready") is True,
        "status_endpoint_200": _status_code_is(status, 200),
        "status_runtime_enabled": status_graph.get("runtime_enabled") is True,
        "status_available": availability.get("available") is True,
        "status_safe_to_serve_locally": (
            availability.get("safe_to_serve_locally") is True
        ),
        "status_runtime_loader_not_implemented": (
            availability.get("runtime_loader_implemented") is False
        ),
        "status_manual_review_required": (
            status_graph.get("manual_review_required") is True
        ),
        "status_publication_ready_false": (
            status_graph.get("publication_ready") is False
        ),
        "status_common_caveats_present": COMMON_CAVEATS.issubset(
            _caveats(status_payload)
        ),
        "references_endpoint_200": _status_code_is(references, 200),
        "references_sample_matches": (
            references_payload.get("query", {}).get("canonical_id")
            == samples.references_canonical_id
        ),
        "references_items_non_empty": bool(_items(references_payload)),
        "citations_endpoint_200": _status_code_is(citations, 200),
        "citations_sample_matches": (
            citations_payload.get("query", {}).get("canonical_id")
            == samples.citations_canonical_id
        ),
        "citations_items_non_empty": bool(_items(citations_payload)),
        "external_reference_endpoint_200": _status_code_is(external, 200),
        "external_reference_items_non_empty": bool(_items(external_payload)),
        "source_families_endpoint_200": _status_code_is(source_families, 200),
        "source_families_items_non_empty": bool(_items(source_families_payload)),
        "top_referenced_endpoint_200": _status_code_is(top_referenced, 200),
        "top_referenced_items_non_empty": bool(_items(top_referenced_payload)),
        "top_external_endpoint_200": _status_code_is(top_external, 200),
        "top_external_items_non_empty": bool(_items(top_external_payload)),
        "unknown_paper_returns_404": _status_code_is(unknown_paper, 404),
        "unknown_paper_error_code": _error_code_is(
            unknown_paper,
            "canonical_id_not_found",
        ),
        "unknown_external_returns_404": _status_code_is(unknown_external, 404),
        "unknown_external_error_code": _error_code_is(
            unknown_external,
            "external_reference_not_found",
        ),
        "limit_guard_returns_400": _status_code_is(invalid_limit_result, 400),
        "limit_guard_error_code": _error_code_is(
            invalid_limit_result,
            "graph_result_limit_exceeded",
        ),
        "health_after_graph_status_200": _status_code_is(health_after_graph, 200),
        "health_after_graph_ready_true": health_after_payload.get("ready") is True,
        "general_runtime_remains_healthy": (
            health_payload.get("ready") is True
            and health_after_payload.get("ready") is True
            and runtime_payload.get("ready") is True
        ),
    }

    required_failed_checks = [
        name for name, value in checks.items() if value is not True
    ]

    observations = {
        "graph_name": status_graph.get("name"),
        "graph_version": status_graph.get("version"),
        "reference_resolution_ratio": status_graph.get("reference_resolution_ratio"),
        "references_returned": len(_items(references_payload)),
        "citations_returned": len(_items(citations_payload)),
        "external_reference_papers_returned": len(_items(external_payload)),
        "source_families_returned": len(_items(source_families_payload)),
        "top_referenced_papers_returned": len(_items(top_referenced_payload)),
        "top_external_references_returned": len(_items(top_external_payload)),
        "status_caveats": sorted(_caveats(status_payload)),
        "top_referenced_caveats": sorted(_caveats(top_referenced_payload)),
        "top_external_caveats": sorted(_caveats(top_external_payload)),
    }

    summary = {
        "ok": not required_failed_checks,
        "required_failed_count": len(required_failed_checks),
        "required_failed_checks": required_failed_checks,
        "checks_count": len(checks),
        "endpoints_count": len(endpoints),
        "routes_count": 7,
        "traversal_routes_count": 6,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "base_url": base_url,
            "graph_root": normalize_path(graph_root),
            "reports_dir": normalize_path(args.reports_dir),
            "limit": limit,
            "invalid_limit": invalid_limit,
            "timeout_sec": timeout_sec,
        },
        "samples": asdict(samples),
        "summary": summary,
        "checks": checks,
        "endpoints": endpoints,
        "observations": observations,
        "verdict": {
            "ok": not required_failed_checks,
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
            "live_smoke_ready": not required_failed_checks,
            "operator_facing_evidence": True,
            "dod_gate_required": False,
            "runtime_loader_implemented": False,
            "manual_review_required": True,
            "publication_ready": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an operator-facing live HTTP smoke over the enabled local "
            "Citation Graph API. The API process must already be running with "
            "ML_RADAR_SEARCH_BACKEND=file and "
            "ML_RADAR_CITATION_GRAPH_API_ENABLED=true."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--graph-root", type=Path, default=DEFAULT_GRAPH_ROOT)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--invalid-limit", type=int, default=DEFAULT_INVALID_LIMIT)
    parser.add_argument("--timeout-sec", type=float, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.limit < 1:
        raise SystemExit("--limit must be >= 1")
    if args.invalid_limit <= args.limit:
        raise SystemExit("--invalid-limit must be greater than --limit")
    if args.timeout_sec <= 0:
        raise SystemExit("--timeout-sec must be > 0")

    try:
        report = build_report(args)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"[error] {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    output_dir = Path(args.reports_dir)
    run_ts = str(report["run_ts"])

    latest_json = output_dir / "citation_graph_live_smoke_latest.json"
    latest_md = output_dir / "citation_graph_live_smoke_latest.md"
    history_json = (
        output_dir
        / "history"
        / f"citation_graph_live_smoke_{run_ts}.json"
    )
    history_md = (
        output_dir
        / "history"
        / f"citation_graph_live_smoke_{run_ts}.md"
    )

    markdown = build_markdown(report)
    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)

    print(
        json.dumps(
            report["summary"],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    print(f"[report] {latest_json}")
    print(f"[report] {latest_md}")

    if args.strict and not report["verdict"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
