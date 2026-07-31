from __future__ import annotations

import argparse
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCHEMA_VERSION = "paper_comparison_live_smoke_v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_PROFILE = "recent_artifact_ready"
DEFAULT_SAMPLE_COUNT = 5
DEFAULT_TIMEOUT_SEC = 300.0
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

EXPECTED_CAPABILITIES = {
    "artifact_details",
    "citation_graph",
    "semantic_similarity",
    "topic_clusters",
}
EXPECTED_SHARED_DIMENSIONS = {
    "artifact_types",
    "categories",
    "concepts",
    "keywords",
    "source_families",
}


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
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    query = urlencode(params or {}, doseq=True)
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"

    headers = {"Accept": "application/json"}
    data: bytes | None = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")

    request = Request(
        url,
        headers=headers,
        data=data,
        method=method.upper(),
    )

    try:
        with urlopen(request, timeout=timeout_sec) as response:
            body = response.read()
            status_code = int(response.status)
            return {
                "path": path,
                "method": method.upper(),
                "params": params or {},
                "json_body": json_body,
                "url": url,
                "status_code": status_code,
                "ok": 200 <= status_code < 300,
                "json": _decode_json_bytes(body),
                "error": None,
            }
    except HTTPError as exc:
        body = exc.read()
        return {
            "path": path,
            "method": method.upper(),
            "params": params or {},
            "json_body": json_body,
            "url": url,
            "status_code": int(exc.code),
            "ok": False,
            "json": _decode_json_bytes(body),
            "error": str(exc),
        }
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        return {
            "path": path,
            "method": method.upper(),
            "params": params or {},
            "json_body": json_body,
            "url": url,
            "status_code": None,
            "ok": False,
            "json": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _payload(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("json")
    return value if isinstance(value, dict) else {}


def _endpoint_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"json", "json_body"}
    }


def _status_code_is(result: dict[str, Any], expected: int) -> bool:
    return result.get("status_code") == expected


def extract_sample_ids(
    ranking_payload: dict[str, Any],
    *,
    count: int = DEFAULT_SAMPLE_COUNT,
) -> list[str]:
    results = ranking_payload.get("results")
    if not isinstance(results, list):
        return []

    canonical_ids: list[str] = []
    seen: set[str] = set()
    for row in results:
        if not isinstance(row, dict):
            continue
        canonical_id = str(row.get("canonical_id") or "").strip()
        if not canonical_id or canonical_id in seen:
            continue
        canonical_ids.append(canonical_id)
        seen.add(canonical_id)
        if len(canonical_ids) >= count:
            break
    return canonical_ids


def _ordered_paper_ids(payload: dict[str, Any]) -> list[str]:
    rows = payload.get("papers")
    if not isinstance(rows, list):
        return []
    return [
        str(row.get("canonical_id") or "")
        for row in rows
        if isinstance(row, dict)
    ]


def _semantic_rows_are_available(payload: dict[str, Any]) -> bool:
    pairwise = payload.get("pairwise")
    if not isinstance(pairwise, list) or not pairwise:
        return False
    for row in pairwise:
        if not isinstance(row, dict):
            return False
        semantic = row.get("semantic")
        if not isinstance(semantic, dict):
            return False
        if semantic.get("available") is not True:
            return False
        if not isinstance(semantic.get("similarity"), (int, float)):
            return False
    return True


def _missing_ids_from_404(payload: dict[str, Any]) -> list[str]:
    detail = payload.get("detail")
    if not isinstance(detail, dict):
        return []
    values = detail.get("missing_canonical_ids")
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_sec: float,
) -> dict[str, Any]:
    return request_json(
        base_url,
        path,
        method=method,
        params=params,
        json_body=json_body,
        timeout_sec=timeout_sec,
    )


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Comparison live smoke",
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
    for index, canonical_id in enumerate(report["samples"]["canonical_ids"], start=1):
        lines.append(f"- paper_{index}: `{canonical_id}`")

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
    profile = str(args.profile).strip()
    sample_count = int(args.sample_count)
    timeout_sec = float(args.timeout_sec)

    endpoints: dict[str, dict[str, Any]] = {}

    def call(
        name: str,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = _request(
            base_url,
            path,
            method=method,
            params=params,
            json_body=json_body,
            timeout_sec=timeout_sec,
        )
        endpoints[name] = _endpoint_meta(result)
        return result

    health = call("health", "/health")
    info = call("info", "/info")
    runtime = call("runtime", "/runtime")
    ranking = call(
        "sample_ranking",
        f"/discovery/ranking/{profile}",
        params={"top_k": sample_count},
    )

    ranking_payload = _payload(ranking)
    canonical_ids = extract_sample_ids(ranking_payload, count=sample_count)
    if len(canonical_ids) < sample_count:
        raise ValueError(
            "Paper Comparison live smoke requires "
            f"{sample_count} unique ranking papers; found {len(canonical_ids)}"
        )

    two_ids = canonical_ids[:2]
    five_ids = canonical_ids[:5]
    missing_id = "__paper_comparison_live_smoke_missing__"

    compare_two = call(
        "compare_two",
        "/discovery/papers/compare",
        method="POST",
        json_body={"canonical_ids": two_ids},
    )
    compare_two_repeat = call(
        "compare_two_repeat",
        "/discovery/papers/compare",
        method="POST",
        json_body={"canonical_ids": two_ids},
    )
    compare_five = call(
        "compare_five",
        "/discovery/papers/compare",
        method="POST",
        json_body={"canonical_ids": five_ids},
    )
    reject_one = call(
        "reject_one",
        "/discovery/papers/compare",
        method="POST",
        json_body={"canonical_ids": canonical_ids[:1]},
    )
    reject_duplicate = call(
        "reject_duplicate",
        "/discovery/papers/compare",
        method="POST",
        json_body={"canonical_ids": [two_ids[0], two_ids[0]]},
    )
    reject_six = call(
        "reject_six",
        "/discovery/papers/compare",
        method="POST",
        json_body={"canonical_ids": [*five_ids, "sixth-paper-id"]},
    )
    reject_blank = call(
        "reject_blank",
        "/discovery/papers/compare",
        method="POST",
        json_body={"canonical_ids": [two_ids[0], " "]},
    )
    reject_missing = call(
        "reject_missing",
        "/discovery/papers/compare",
        method="POST",
        json_body={"canonical_ids": [two_ids[0], missing_id]},
    )
    health_after = call("health_after_comparison", "/health")

    health_payload = _payload(health)
    info_payload = _payload(info)
    runtime_payload = _payload(runtime)
    compare_two_payload = _payload(compare_two)
    compare_two_repeat_payload = _payload(compare_two_repeat)
    compare_five_payload = _payload(compare_five)
    health_after_payload = _payload(health_after)

    compare_two_capabilities = compare_two_payload.get("capabilities")
    if not isinstance(compare_two_capabilities, dict):
        compare_two_capabilities = {}
    compare_five_summary = compare_five_payload.get("summary")
    if not isinstance(compare_five_summary, dict):
        compare_five_summary = {}
    shared_by_all = compare_five_summary.get("shared_by_all")
    if not isinstance(shared_by_all, dict):
        shared_by_all = {}

    checks = {
        "health_status_200": _status_code_is(health, 200),
        "health_ready_true": health_payload.get("ready") is True,
        "info_status_200": _status_code_is(info, 200),
        "runtime_status_200": _status_code_is(runtime, 200),
        "runtime_ready_true": runtime_payload.get("ready") is True,
        "ranking_status_200": _status_code_is(ranking, 200),
        "ranking_mode_is_ranking": ranking_payload.get("mode") == "ranking",
        "ranking_profile_matches": (
            isinstance(ranking_payload.get("profile"), dict)
            and ranking_payload["profile"].get("name") == profile
        ),
        "five_unique_samples_resolved": (
            len(canonical_ids) == sample_count
            and len(set(canonical_ids)) == sample_count
        ),
        "compare_two_status_200": _status_code_is(compare_two, 200),
        "compare_two_schema_version": (
            compare_two_payload.get("schema_version")
            == "paper_comparison_v0.1"
        ),
        "compare_two_mode": (
            compare_two_payload.get("mode") == "paper_comparison"
        ),
        "compare_two_order_preserved": (
            compare_two_payload.get("canonical_ids") == two_ids
            and _ordered_paper_ids(compare_two_payload) == two_ids
            and compare_two_payload.get("input_order_preserved") is True
        ),
        "compare_two_paper_count": (
            compare_two_payload.get("paper_count") == 2
        ),
        "compare_two_has_one_pair": (
            isinstance(compare_two_payload.get("pairwise"), list)
            and len(compare_two_payload["pairwise"]) == 1
        ),
        "compare_two_capabilities_complete": (
            set(compare_two_capabilities) == EXPECTED_CAPABILITIES
        ),
        "compare_two_semantic_available": (
            _semantic_rows_are_available(compare_two_payload)
        ),
        "compare_two_repeat_status_200": (
            _status_code_is(compare_two_repeat, 200)
        ),
        "compare_two_repeat_deterministic": (
            compare_two_repeat_payload == compare_two_payload
        ),
        "compare_five_status_200": _status_code_is(compare_five, 200),
        "compare_five_order_preserved": (
            compare_five_payload.get("canonical_ids") == five_ids
            and _ordered_paper_ids(compare_five_payload) == five_ids
            and compare_five_payload.get("input_order_preserved") is True
        ),
        "compare_five_paper_count": (
            compare_five_payload.get("paper_count") == 5
        ),
        "compare_five_has_ten_pairs": (
            isinstance(compare_five_payload.get("pairwise"), list)
            and len(compare_five_payload["pairwise"]) == 10
        ),
        "compare_five_semantic_available": (
            _semantic_rows_are_available(compare_five_payload)
        ),
        "compare_five_shared_dimensions_complete": (
            set(shared_by_all) == EXPECTED_SHARED_DIMENSIONS
        ),
        "one_id_rejected_422": _status_code_is(reject_one, 422),
        "duplicate_ids_rejected_422": (
            _status_code_is(reject_duplicate, 422)
        ),
        "six_ids_rejected_422": _status_code_is(reject_six, 422),
        "blank_id_rejected_422": _status_code_is(reject_blank, 422),
        "missing_id_rejected_404": _status_code_is(reject_missing, 404),
        "missing_id_reported": (
            _missing_ids_from_404(_payload(reject_missing)) == [missing_id]
        ),
        "health_after_status_200": _status_code_is(health_after, 200),
        "health_after_ready_true": health_after_payload.get("ready") is True,
        "general_runtime_remains_healthy": (
            health_payload.get("ready") is True
            and runtime_payload.get("ready") is True
            and health_after_payload.get("ready") is True
        ),
    }

    required_failed_checks = [
        name for name, value in checks.items() if value is not True
    ]

    capabilities = {
        name: {
            "available": value.get("available"),
            "reason": value.get("reason"),
        }
        for name, value in compare_two_capabilities.items()
        if isinstance(value, dict)
    }
    observations = {
        "backend_mode": (
            info_payload.get("backend_mode")
            or runtime_payload.get("backend_mode")
            or health_payload.get("backend_mode")
        ),
        "profile": profile,
        "ranking_returned_rows_count": ranking_payload.get(
            "returned_rows_count"
        ),
        "compare_two_capabilities": capabilities,
        "compare_two_warning_count": len(
            compare_two_payload.get("warnings")
            if isinstance(compare_two_payload.get("warnings"), list)
            else []
        ),
        "compare_five_pair_count": len(
            compare_five_payload.get("pairwise")
            if isinstance(compare_five_payload.get("pairwise"), list)
            else []
        ),
        "workspace_postgres_required": False,
        "qdrant_required": False,
        "writes_comparison_state": False,
    }

    summary = {
        "ok": not required_failed_checks,
        "required_failed_count": len(required_failed_checks),
        "required_failed_checks": required_failed_checks,
        "checks_count": len(checks),
        "endpoints_count": len(endpoints),
        "sample_count": len(canonical_ids),
        "compare_request_count": 8,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "base_url": base_url,
            "profile": profile,
            "sample_count": sample_count,
            "timeout_sec": timeout_sec,
            "reports_dir": normalize_path(args.reports_dir),
        },
        "samples": {
            "canonical_ids": canonical_ids,
            "selection_source": (
                f"GET /discovery/ranking/{profile}?top_k={sample_count}"
            ),
        },
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
            "canonical_truth_mutated": False,
            "comparison_state_persisted": False,
            "workspace_postgres_required": False,
            "qdrant_required": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an operator-facing live HTTP smoke over Paper Comparison "
            "Workspace v0.1. The API process must already be running with a "
            "healthy file-first Discovery runtime."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument(
        "--sample-count",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=DEFAULT_TIMEOUT_SEC,
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
    )
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if not str(args.profile).strip():
        raise SystemExit("--profile must be non-empty")
    if int(args.sample_count) != 5:
        raise SystemExit("--sample-count must be 5 for the v0.1 merge gate")
    if float(args.timeout_sec) <= 0:
        raise SystemExit("--timeout-sec must be > 0")

    try:
        report = build_report(args)
    except (OSError, ValueError) as exc:
        print(f"[error] {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    output_dir = Path(args.reports_dir)
    run_ts = str(report["run_ts"])

    latest_json = output_dir / "paper_comparison_live_smoke_latest.json"
    latest_md = output_dir / "paper_comparison_live_smoke_latest.md"
    history_json = (
        output_dir
        / "history"
        / f"paper_comparison_live_smoke_{run_ts}.json"
    )
    history_md = (
        output_dir
        / "history"
        / f"paper_comparison_live_smoke_{run_ts}.md"
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
