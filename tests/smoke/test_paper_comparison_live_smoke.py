from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import scripts.validation.check_paper_comparison_live_smoke as live_smoke


SAMPLE_IDS = [f"paper:{index}" for index in range(1, 6)]


def _args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        base_url="http://127.0.0.1:8000",
        profile="recent_artifact_ready",
        sample_count=5,
        timeout_sec=2.0,
        reports_dir=tmp_path / "reports",
        strict=True,
    )


def _result(
    path: str,
    payload: dict[str, Any],
    *,
    status_code: int = 200,
    method: str = "GET",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "path": path,
        "method": method,
        "params": params or {},
        "json_body": None,
        "url": f"http://127.0.0.1:8000{path}",
        "status_code": status_code,
        "ok": 200 <= status_code < 300,
        "json": payload,
        "error": None,
    }


def _comparison_payload(canonical_ids: list[str]) -> dict[str, Any]:
    pairwise = []
    for left_index, left_id in enumerate(canonical_ids):
        for right_id in canonical_ids[left_index + 1 :]:
            pairwise.append(
                {
                    "left_canonical_id": left_id,
                    "right_canonical_id": right_id,
                    "semantic": {
                        "available": True,
                        "similarity": 0.75,
                        "reason": None,
                    },
                }
            )

    return {
        "schema_version": "paper_comparison_v0.1",
        "mode": "paper_comparison",
        "canonical_ids": canonical_ids,
        "paper_count": len(canonical_ids),
        "input_order_preserved": True,
        "papers": [
            {"canonical_id": canonical_id, "title": canonical_id}
            for canonical_id in canonical_ids
        ],
        "pairwise": pairwise,
        "summary": {
            "shared_by_all": {
                "artifact_types": [],
                "categories": [],
                "concepts": [],
                "keywords": [],
                "source_families": [],
            }
        },
        "capabilities": {
            "artifact_details": {"available": True, "reason": None},
            "citation_graph": {
                "available": False,
                "reason": "disabled in fixture",
            },
            "semantic_similarity": {"available": True, "reason": None},
            "topic_clusters": {"available": True, "reason": None},
        },
        "warnings": ["citation graph disabled in fixture"],
    }


def _fake_request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_sec: float,
) -> dict[str, Any]:
    del base_url, timeout_sec

    if path == "/health":
        return _result(
            path,
            {"status": "ok", "backend_mode": "file", "ready": True},
            params=params,
        )
    if path == "/info":
        return _result(
            path,
            {"backend_mode": "file", "build_id": "fixture-build"},
            params=params,
        )
    if path == "/runtime":
        return _result(
            path,
            {"backend_mode": "file", "ready": True},
            params=params,
        )
    if path == "/discovery/ranking/recent_artifact_ready":
        return _result(
            path,
            {
                "mode": "ranking",
                "profile": {"name": "recent_artifact_ready"},
                "returned_rows_count": 5,
                "results": [
                    {"canonical_id": canonical_id}
                    for canonical_id in SAMPLE_IDS
                ],
            },
            params=params,
        )
    if path != "/discovery/papers/compare":
        raise AssertionError(f"Unexpected path: {path}")

    canonical_ids = list((json_body or {}).get("canonical_ids") or [])
    if canonical_ids == SAMPLE_IDS[:1]:
        return _result(
            path,
            {"error_code": "validation_error"},
            status_code=422,
            method=method,
        )
    if canonical_ids == [SAMPLE_IDS[0], SAMPLE_IDS[0]]:
        return _result(
            path,
            {"error_code": "validation_error"},
            status_code=422,
            method=method,
        )
    if len(canonical_ids) == 6:
        return _result(
            path,
            {"error_code": "validation_error"},
            status_code=422,
            method=method,
        )
    if any(not str(value).strip() for value in canonical_ids):
        return _result(
            path,
            {"error_code": "validation_error"},
            status_code=422,
            method=method,
        )
    if "__paper_comparison_live_smoke_missing__" in canonical_ids:
        return _result(
            path,
            {
                "detail": {
                    "missing_canonical_ids": [
                        "__paper_comparison_live_smoke_missing__"
                    ]
                }
            },
            status_code=404,
            method=method,
        )
    return _result(
        path,
        _comparison_payload(canonical_ids),
        method=method,
    )


def test_live_smoke_report_green_with_optional_graph_unavailable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(live_smoke, "request_json", _fake_request_json)

    report = live_smoke.build_report(_args(tmp_path))

    assert report["schema_version"] == "paper_comparison_live_smoke_v1"
    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["summary"]["sample_count"] == 5
    assert report["summary"]["compare_request_count"] == 8
    assert report["verdict"]["live_smoke_ready"] is True
    assert report["verdict"]["canonical_truth_mutated"] is False
    assert report["verdict"]["comparison_state_persisted"] is False
    assert report["checks"]["compare_two_repeat_deterministic"] is True
    assert report["checks"]["compare_five_has_ten_pairs"] is True
    assert report["checks"]["general_runtime_remains_healthy"] is True
    assert (
        report["observations"]["compare_two_capabilities"]["citation_graph"][
            "available"
        ]
        is False
    )


def test_live_smoke_detects_order_regression(tmp_path, monkeypatch):
    def wrong_order(
        base_url: str,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout_sec: float,
    ) -> dict[str, Any]:
        result = _fake_request_json(
            base_url,
            path,
            method=method,
            params=params,
            json_body=json_body,
            timeout_sec=timeout_sec,
        )
        if (
            path == "/discovery/papers/compare"
            and result["status_code"] == 200
            and json_body
            and len(json_body["canonical_ids"]) == 2
        ):
            result["json"] = {
                **result["json"],
                "canonical_ids": list(reversed(json_body["canonical_ids"])),
            }
        return result

    monkeypatch.setattr(live_smoke, "request_json", wrong_order)
    report = live_smoke.build_report(_args(tmp_path))

    assert report["summary"]["ok"] is False
    assert report["checks"]["compare_two_order_preserved"] is False
    assert "compare_two_order_preserved" in report["summary"][
        "required_failed_checks"
    ]


def test_live_smoke_detects_semantic_regression(tmp_path, monkeypatch):
    def unavailable_semantic(
        base_url: str,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout_sec: float,
    ) -> dict[str, Any]:
        result = _fake_request_json(
            base_url,
            path,
            method=method,
            params=params,
            json_body=json_body,
            timeout_sec=timeout_sec,
        )
        if path == "/discovery/papers/compare" and result["status_code"] == 200:
            for row in result["json"]["pairwise"]:
                row["semantic"] = {
                    "available": False,
                    "similarity": None,
                    "reason": "missing fixture",
                }
        return result

    monkeypatch.setattr(live_smoke, "request_json", unavailable_semantic)
    report = live_smoke.build_report(_args(tmp_path))

    assert report["summary"]["ok"] is False
    assert report["checks"]["compare_two_semantic_available"] is False
    assert report["checks"]["compare_five_semantic_available"] is False


def test_extract_sample_ids_is_unique_and_ordered():
    payload = {
        "results": [
            {"canonical_id": "paper:b"},
            {"canonical_id": ""},
            {"canonical_id": "paper:a"},
            {"canonical_id": "paper:b"},
            {"canonical_id": "paper:c"},
        ]
    }

    assert live_smoke.extract_sample_ids(payload, count=3) == [
        "paper:b",
        "paper:a",
        "paper:c",
    ]


def test_live_smoke_requires_five_ranking_samples(tmp_path, monkeypatch):
    def short_ranking(
        base_url: str,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout_sec: float,
    ) -> dict[str, Any]:
        result = _fake_request_json(
            base_url,
            path,
            method=method,
            params=params,
            json_body=json_body,
            timeout_sec=timeout_sec,
        )
        if path == "/discovery/ranking/recent_artifact_ready":
            result["json"]["results"] = result["json"]["results"][:4]
        return result

    monkeypatch.setattr(live_smoke, "request_json", short_ranking)

    try:
        live_smoke.build_report(_args(tmp_path))
    except ValueError as exc:
        assert "requires 5 unique ranking papers" in str(exc)
    else:
        raise AssertionError("Expected ValueError for insufficient samples")
