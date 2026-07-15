from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import scripts.validation.check_citation_graph_live_smoke as live_smoke


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_graph_fixture(graph_root: Path) -> Path:
    _write_jsonl(
        graph_root / "nodes.jsonl",
        [
            {
                "node_id": "paper:source-node",
                "node_type": "paper",
                "canonical_id": "source/canonical:id",
                "title": "Source Paper",
            },
            {
                "node_id": "paper:target-node",
                "node_type": "paper",
                "canonical_id": "target-canonical-id",
                "title": "Target Paper",
            },
            {
                "node_id": "external_reference:doi:10.9999/example/value",
                "node_type": "external_reference",
                "reference_key": "doi:10.9999/example/value",
            },
        ],
    )
    _write_jsonl(
        graph_root / "edges.jsonl",
        [
            {
                "edge_id": "edge:paper",
                "edge_type": "paper_references_paper",
                "source_node_id": "paper:source-node",
                "target_node_id": "paper:target-node",
            },
            {
                "edge_id": "edge:external",
                "edge_type": "paper_references_external",
                "source_node_id": "paper:source-node",
                "target_node_id": "external_reference:doi:10.9999/example/value",
            },
        ],
    )
    return graph_root


def _args(tmp_path: Path, graph_root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        base_url="http://127.0.0.1:8000",
        graph_root=graph_root,
        reports_dir=tmp_path / "reports",
        limit=5,
        invalid_limit=101,
        timeout_sec=2.0,
        strict=True,
    )


def _ok_result(
    path: str,
    payload: dict[str, Any],
    *,
    status_code: int = 200,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "path": path,
        "params": params or {},
        "url": f"http://127.0.0.1:8000{path}",
        "status_code": status_code,
        "ok": 200 <= status_code < 300,
        "json": payload,
        "error": None,
    }


def _fake_request_json(
    base_url: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout_sec: float,
) -> dict[str, Any]:
    del base_url, timeout_sec

    if path == "/health":
        return _ok_result(
            path,
            {"status": "ok", "backend_mode": "file", "ready": True},
            params=params,
        )
    if path == "/info":
        return _ok_result(
            path,
            {"backend_mode": "file", "build_id": "test-build"},
            params=params,
        )
    if path == "/runtime":
        return _ok_result(
            path,
            {"backend_mode": "file", "ready": True},
            params=params,
        )
    if path == "/citation-graph/status":
        return _ok_result(
            path,
            {
                "graph": {
                    "name": "citation_reference_graph",
                    "version": "v0.1",
                    "runtime_enabled": True,
                    "manual_review_required": True,
                    "publication_ready": False,
                    "reference_resolution_ratio": 0.00869,
                },
                "availability": {
                    "available": True,
                    "safe_to_serve_locally": True,
                    "runtime_loader_implemented": False,
                },
                "caveats": sorted(live_smoke.COMMON_CAVEATS),
            },
            params=params,
        )

    if "__citation_graph_live_smoke_missing_paper__" in path:
        return _ok_result(
            path,
            {"error_code": "canonical_id_not_found"},
            status_code=404,
            params=params,
        )
    if "__citation_graph_live_smoke_missing_external__" in path:
        return _ok_result(
            path,
            {"error_code": "external_reference_not_found"},
            status_code=404,
            params=params,
        )
    if params and params.get("limit") == 101:
        return _ok_result(
            path,
            {"error_code": "graph_result_limit_exceeded"},
            status_code=400,
            params=params,
        )

    common_graph = {
        "name": "citation_reference_graph",
        "version": "v0.1",
    }
    common_page = {
        "limit": 5,
        "offset": 0,
        "returned": 1,
        "total_estimate": 1,
    }

    if path.endswith("/references"):
        return _ok_result(
            path,
            {
                "graph": common_graph,
                "query": {"canonical_id": "source/canonical:id"},
                "items": [{"edge_id": "edge:paper"}],
                "page": common_page,
                "caveats": sorted(live_smoke.COMMON_CAVEATS),
            },
            params=params,
        )
    if path.endswith("/citations"):
        return _ok_result(
            path,
            {
                "graph": common_graph,
                "query": {"canonical_id": "target-canonical-id"},
                "items": [{"edge_id": "edge:paper"}],
                "page": common_page,
                "caveats": sorted(live_smoke.COMMON_CAVEATS),
            },
            params=params,
        )
    if path.startswith("/citation-graph/external-references/"):
        return _ok_result(
            path,
            {
                "graph": common_graph,
                "query": {"reference_id": "external"},
                "items": [{"edge_id": "edge:external"}],
                "page": common_page,
                "caveats": sorted(live_smoke.COMMON_CAVEATS),
            },
            params=params,
        )
    if path == "/citation-graph/source-families":
        items = [{"source_family": "openalex"}]
        caveats = [*live_smoke.COMMON_CAVEATS, "not_source_coverage_metric"]
    elif path == "/citation-graph/top-referenced-papers":
        items = [{"canonical_id": "target-canonical-id"}]
        caveats = [*live_smoke.COMMON_CAVEATS, "not_global_citation_metric"]
    elif path == "/citation-graph/top-external-references":
        items = [{"external_reference_id": "external"}]
        caveats = [
            *live_smoke.COMMON_CAVEATS,
            "not_publication_grade_reference_entity",
        ]
    else:
        raise AssertionError(f"Unexpected live smoke path: {path}")

    return _ok_result(
        path,
        {
            "graph": common_graph,
            "query": {},
            "items": items,
            "page": common_page,
            "caveats": caveats,
        },
        params=params,
    )


def test_live_smoke_report_green_with_fake_http(tmp_path, monkeypatch):
    graph_root = _write_graph_fixture(tmp_path / "graph")
    monkeypatch.setattr(live_smoke, "request_json", _fake_request_json)

    report = live_smoke.build_report(_args(tmp_path, graph_root))

    assert report["schema_version"] == "citation_graph_live_smoke_v1"
    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["summary"]["routes_count"] == 7
    assert report["summary"]["traversal_routes_count"] == 6
    assert report["verdict"]["live_smoke_ready"] is True
    assert report["verdict"]["dod_gate_required"] is False
    assert report["verdict"]["runtime_loader_implemented"] is False
    assert report["verdict"]["manual_review_required"] is True
    assert report["verdict"]["publication_ready"] is False
    assert report["checks"]["general_runtime_remains_healthy"] is True


def test_live_smoke_detects_general_runtime_regression(tmp_path, monkeypatch):
    graph_root = _write_graph_fixture(tmp_path / "graph")
    health_calls = 0

    def failing_health_after_graph(
        base_url: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout_sec: float,
    ) -> dict[str, Any]:
        nonlocal health_calls
        if path == "/health":
            health_calls += 1
            if health_calls == 2:
                return _ok_result(
                    path,
                    {"status": "error", "backend_mode": "file", "ready": False},
                    status_code=503,
                    params=params,
                )
        return _fake_request_json(
            base_url,
            path,
            params=params,
            timeout_sec=timeout_sec,
        )

    monkeypatch.setattr(live_smoke, "request_json", failing_health_after_graph)
    report = live_smoke.build_report(_args(tmp_path, graph_root))

    assert report["summary"]["ok"] is False
    assert "health_after_graph_status_200" in report["summary"][
        "required_failed_checks"
    ]
    assert report["checks"]["general_runtime_remains_healthy"] is False


def test_sample_resolution_and_path_encoding(tmp_path):
    graph_root = _write_graph_fixture(tmp_path / "graph")

    samples = live_smoke.resolve_smoke_samples(graph_root)

    assert samples.references_canonical_id == "source/canonical:id"
    assert samples.citations_canonical_id == "target-canonical-id"
    assert samples.external_reference_id == (
        "external_reference:doi:10.9999/example/value"
    )
    assert live_smoke.encode_path_segment(samples.references_canonical_id) == (
        "source%2Fcanonical%3Aid"
    )
    assert live_smoke.encode_path_segment(samples.external_reference_id) == (
        "external_reference%3Adoi%3A10.9999%2Fexample%2Fvalue"
    )
