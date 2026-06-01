from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

DEFAULT_OUTPUT_DIR = Path("artifacts/reports/api")
DEFAULT_QUERY = "protein language models"
DEFAULT_TOP_K = 5


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def bool_check(value: Any) -> bool:
    return bool(value)


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Experimental Qdrant API quality report",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- strict: `{report['strict']}`",
        f"- endpoint: `{report['endpoint']}`",
        f"- query: `{report['query']}`",
        f"- top_k: `{report['top_k']}`",
        f"- status_code: `{report['summary'].get('status_code')}`",
        f"- result_count: `{report['summary'].get('result_count')}`",
        f"- required_failed_count: `{report['verdict']['required_failed_count']}`",
        "",
        "## Checks",
        "",
    ]

    for name, value in report["checks"].items():
        marker = "OK" if value else "FAIL"
        lines.append(f"- {marker}: `{name}` = `{value}`")

    failed = report["verdict"].get("required_failed_checks") or []
    if failed:
        lines.extend(["", "## Failed required checks", ""])
        for name in failed:
            lines.append(f"- `{name}`")

    return "\n".join(lines) + "\n"


def run_check(*, strict: bool, output_dir: Path, query: str, top_k: int) -> dict[str, Any]:
    os.environ["ML_RADAR_SEARCH_BACKEND"] = "file"

    from services.api.app import app
    from services.api.runtime import get_runtime
    from services.api.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    runtime = get_runtime()
    runtime.load()

    client = TestClient(app)
    endpoint = "/experimental/search/qdrant"

    response = client.get(endpoint, params={"query": query, "top_k": top_k})

    payload: dict[str, Any] | None = None
    response_json_ok = False
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            payload = response.json()
            response_json_ok = isinstance(payload, dict)
        except Exception:
            payload = None

    results = []
    if isinstance(payload, dict):
        results = payload.get("results") or []

    first_result = results[0] if results else {}
    expected_collection_name = settings.qdrant_collection_name

    summary = {
        "status_code": response.status_code,
        "response_json_ok": response_json_ok,
        "query": query,
        "top_k": top_k,
        "mode": payload.get("mode") if isinstance(payload, dict) else None,
        "build_id": payload.get("build_id") if isinstance(payload, dict) else None,
        "collection_name": payload.get("collection_name") if isinstance(payload, dict) else None,
        "expected_collection_name": expected_collection_name,
        "result_count": len(results),
        "first_canonical_id": (
            first_result.get("document", {}).get("canonical_id")
            if isinstance(first_result, dict)
            else None
        ),
        "first_title": (
            first_result.get("document", {}).get("title")
            if isinstance(first_result, dict)
            else None
        ),
        "first_score": (
            first_result.get("retrieval", {}).get("score")
            if isinstance(first_result, dict)
            else None
        ),
    }

    checks = {
        "status_code_ok": response.status_code == 200,
        "response_json_ok": response_json_ok,
        "mode_dense_qdrant": summary["mode"] == "dense_qdrant",
        "collection_name_expected": summary["collection_name"] == summary["expected_collection_name"],
        "result_count_positive": summary["result_count"] > 0,
        "result_count_le_top_k": summary["result_count"] <= top_k,
        "first_result_has_canonical_id": bool(summary["first_canonical_id"]),
        "first_result_has_title": bool(summary["first_title"]),
        "first_result_has_score": isinstance(summary["first_score"], (int, float)),
        "all_results_have_rank": all(
            isinstance(item.get("rank"), int)
            for item in results
            if isinstance(item, dict)
        ),
        "all_results_have_document": all(
            isinstance(item.get("document"), dict)
            and bool(item["document"].get("canonical_id"))
            and bool(item["document"].get("title"))
            for item in results
            if isinstance(item, dict)
        ),
        "all_results_have_score": all(
            isinstance((item.get("retrieval") or {}).get("score"), (int, float))
            for item in results
            if isinstance(item, dict)
        ),
    }

    required_check_names = [
        "status_code_ok",
        "response_json_ok",
        "mode_dense_qdrant",
        "collection_name_expected",
        "result_count_positive",
        "result_count_le_top_k",
        "first_result_has_canonical_id",
        "first_result_has_title",
        "first_result_has_score",
        "all_results_have_rank",
        "all_results_have_document",
        "all_results_have_score",
    ]

    required_failed_checks = [
        name for name in required_check_names if not checks.get(name, False)
    ]

    report = {
        "schema_version": "qdrant_api_experimental_quality_v1",
        "generated_at_utc": utc_now_iso(),
        "strict": strict,
        "endpoint": endpoint,
        "query": query,
        "top_k": top_k,
        "summary": summary,
        "checks": checks,
        "required_check_names": required_check_names,
        "verdict": {
            "ok": len(required_failed_checks) == 0,
            "strict": strict,
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
        },
        "response_sample": payload,
    }

    latest_json = output_dir / "qdrant_api_experimental_quality_latest.json"
    latest_md = output_dir / "qdrant_api_experimental_quality_latest.md"

    history_dir = output_dir / "history"
    run_ts = utc_now_ts()
    history_json = history_dir / f"qdrant_api_experimental_quality_{run_ts}.json"
    history_md = history_dir / f"qdrant_api_experimental_quality_{run_ts}.md"

    markdown = build_markdown(report)

    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)

    print(f"[OK] report_path={latest_json}")
    print(f"[OK] schema_version={report['schema_version']}")
    print(f"[OK] strict={strict}")
    print(f"[OK] endpoint={endpoint}")
    print(f"[OK] status_code={summary['status_code']}")
    print(f"[OK] mode={summary['mode']}")
    print(f"[OK] collection_name={summary['collection_name']}")
    print(f"[OK] result_count={summary['result_count']}")
    print(f"[OK] required_failed_count={report['verdict']['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if strict and required_failed_checks:
        raise SystemExit(1)

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate experimental Qdrant API endpoint."
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_check(
        strict=bool(args.strict),
        output_dir=args.output_dir,
        query=args.query,
        top_k=int(args.top_k),
    )


if __name__ == "__main__":
    main()