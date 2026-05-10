from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


DEFAULT_REPORTS_DIR = Path("artifacts/reports/api")
DEFAULT_PROFILE_NAME = "huggingface_ready"
DEFAULT_TOP_K = 5
DEFAULT_BACKEND_MODE = "file"
OVERRIDE_RANKING_PROFILE = "recent_artifact_ready"
OVERRIDE_MIN_YEAR = 2025
OVERRIDE_HAS_CODE = True

REQUIRED_PROFILE_NAMES = {
    "recent_artifact_ready",
    "huggingface_ready",
    "acl_radar",
}


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Discovery API quality check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Endpoints")
    for name, payload in report["endpoints"].items():
        lines.append(f"### {name}")
        lines.append(f"- path: `{payload.get('path')}`")
        lines.append(f"- status_code: `{payload.get('status_code')}`")
        lines.append(f"- ok: `{payload.get('ok')}`")
        if payload.get("error"):
            lines.append(f"- error: `{payload.get('error')}`")
        lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    return "\n".join(lines)


def request_json(
    client: TestClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.get(path, params=params)

    payload: Any
    try:
        payload = response.json()
    except Exception:
        payload = None

    return {
        "path": path,
        "params": params or {},
        "status_code": response.status_code,
        "ok": 200 <= response.status_code < 300,
        "json": payload,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Discovery API endpoints."
    )
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--profile", type=str, default=DEFAULT_PROFILE_NAME)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--canonical-id", type=str, default=None)
    parser.add_argument(
        "--backend-mode",
        choices=["file", "db"],
        default=DEFAULT_BACKEND_MODE,
        help=(
            "Backend mode used by API startup. Discovery API itself is file-first, "
            "but app startup still follows ML_RADAR_SEARCH_BACKEND semantics."
        ),
    )
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    os.environ["ML_RADAR_SEARCH_BACKEND"] = args.backend_mode

    # Import after env setup, because services.api.app initializes settings/runtime.
    from services.api.settings import get_settings  # noqa: WPS433

    get_settings.cache_clear()

    from services.api.app import app  # noqa: WPS433

    endpoints: dict[str, dict[str, Any]] = {}

    with TestClient(app) as client:
        profiles = request_json(client, "/discovery/profiles")
        endpoints["profiles"] = {
            key: value for key, value in profiles.items() if key != "json"
        }

        profiles_payload = profiles.get("json") if isinstance(profiles.get("json"), dict) else {}
        profile_names = {
            item.get("name")
            for item in profiles_payload.get("profiles", [])
            if isinstance(item, dict) and item.get("name")
        }

        ranking = request_json(
            client,
            f"/discovery/ranking/{args.profile}",
            params={"top_k": args.top_k},
        )
        endpoints["ranking"] = {
            key: value for key, value in ranking.items() if key != "json"
        }

        ranking_payload = ranking.get("json") if isinstance(ranking.get("json"), dict) else {}
        ranking_results = ranking_payload.get("results") or []
        ranking_overrides = request_json(
            client,
            f"/discovery/ranking/{OVERRIDE_RANKING_PROFILE}",
            params={
                "top_k": args.top_k,
                "min_year": OVERRIDE_MIN_YEAR,
                "has_code": str(OVERRIDE_HAS_CODE).lower(),
            },
        )
        endpoints["ranking_overrides"] = {
            key: value for key, value in ranking_overrides.items() if key != "json"
        }

        canonical_id = args.canonical_id
        if not canonical_id and ranking_results:
            canonical_id = ranking_results[0].get("canonical_id")

        detail = {}
        similar_semantic = {}
        similar_radar_adjusted = {}

        if canonical_id:
            detail = request_json(client, f"/discovery/papers/{canonical_id}")
            endpoints["paper_detail"] = {
                key: value for key, value in detail.items() if key != "json"
            }

            similar_semantic = request_json(
                client,
                f"/discovery/papers/{canonical_id}/similar",
                params={"top_k": args.top_k, "rank_by": "semantic"},
            )
            endpoints["similar_semantic"] = {
                key: value for key, value in similar_semantic.items() if key != "json"
            }

            similar_radar_adjusted = request_json(
                client,
                f"/discovery/papers/{canonical_id}/similar",
                params={"top_k": args.top_k, "rank_by": "radar_adjusted"},
            )
            endpoints["similar_radar_adjusted"] = {
                key: value
                for key, value in similar_radar_adjusted.items()
                if key != "json"
            }

    detail_payload = detail.get("json") if isinstance(detail.get("json"), dict) else {}
    ranking_overrides_payload = (
        ranking_overrides.get("json")
        if isinstance(ranking_overrides.get("json"), dict)
        else {}
    )
    ranking_overrides_results = ranking_overrides_payload.get("results") or []
    ranking_overrides_filters = (
        ranking_overrides_payload.get("filters")
        if isinstance(ranking_overrides_payload.get("filters"), dict)
        else {}
    )
    detail_body = detail_payload.get("detail") if isinstance(detail_payload.get("detail"), dict) else {}

    similar_payload = (
        similar_semantic.get("json")
        if isinstance(similar_semantic.get("json"), dict)
        else {}
    )
    similar_results = similar_payload.get("results") or []
    similar_ids = [
        row.get("canonical_id")
        for row in similar_results
        if isinstance(row, dict) and row.get("canonical_id")
    ]

    adjusted_payload = (
        similar_radar_adjusted.get("json")
        if isinstance(similar_radar_adjusted.get("json"), dict)
        else {}
    )
    adjusted_results = adjusted_payload.get("results") or []
    adjusted_scores = [
        row.get("radar_adjusted_similarity")
        for row in adjusted_results
        if isinstance(row, dict)
    ]
    adjusted_scores_numeric = [
        float(value)
        for value in adjusted_scores
        if isinstance(value, int | float)
    ]

    missing_required_profiles = sorted(REQUIRED_PROFILE_NAMES - profile_names)

    ranking_overrides_results_match_filters = (
        len(ranking_overrides_results) > 0
        and all(
            isinstance(row, dict)
            and int(row.get("year") or 0) >= OVERRIDE_MIN_YEAR
            and bool(row.get("has_code_artifact")) is True
            for row in ranking_overrides_results
        )
    )

    checks = {
        "profiles_endpoint_ok": bool(profiles.get("ok")),
        "profiles_non_empty": int(profiles_payload.get("profile_count") or 0) > 0,
        "required_profiles_present": len(missing_required_profiles) == 0,
        "ranking_endpoint_ok": bool(ranking.get("ok")),
        "ranking_results_non_empty": len(ranking_results) > 0,
        "ranking_overrides_endpoint_ok": bool(ranking_overrides.get("ok")),
        "ranking_overrides_results_non_empty": len(ranking_overrides_results) > 0,
        "ranking_overrides_min_year_filter_echoed": (
                ranking_overrides_filters.get("min_year") == OVERRIDE_MIN_YEAR
        ),
        "ranking_overrides_has_code_filter_echoed": (
                ranking_overrides_filters.get("has_code") is True
        ),
        "ranking_overrides_results_match_filters": ranking_overrides_results_match_filters,
        "canonical_id_resolved": bool(canonical_id),
        "detail_endpoint_ok": bool(detail.get("ok")),
        "detail_found": bool(detail_payload.get("found")),
        "detail_canonical_id_match": (
            detail_payload.get("canonical_id") == canonical_id if canonical_id else False
        ),
        "detail_features_found": bool(detail_body.get("features_found")),
        "similar_semantic_endpoint_ok": bool(similar_semantic.get("ok")),
        "similar_semantic_results_non_empty": len(similar_results) > 0,
        "similar_semantic_self_not_in_results": (
            canonical_id not in similar_ids if canonical_id else False
        ),
        "similar_radar_adjusted_endpoint_ok": bool(similar_radar_adjusted.get("ok")),
        "similar_radar_adjusted_results_non_empty": len(adjusted_results) > 0,
        "similar_radar_adjusted_sorted": (
            adjusted_scores_numeric == sorted(adjusted_scores_numeric, reverse=True)
            and len(adjusted_scores_numeric) == len(adjusted_results)
        ),
    }

    required_failed_checks = [name for name, ok in checks.items() if not ok]

    report = {
        "report_name": "discovery_api_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "reports_dir": normalize_path(args.reports_dir),
            "backend_mode": args.backend_mode,
            "profile": args.profile,
            "top_k": args.top_k,
            "canonical_id_arg": args.canonical_id,
            "required_profile_names": sorted(REQUIRED_PROFILE_NAMES),
        },
        "summary": {
            "profile_count": profiles_payload.get("profile_count"),
            "profile_names": sorted(profile_names),
            "missing_required_profiles": missing_required_profiles,
            "ranking_profile": args.profile,
            "ranking_results_count": len(ranking_results),
            "ranking_overrides_profile": OVERRIDE_RANKING_PROFILE,
            "ranking_overrides_min_year": OVERRIDE_MIN_YEAR,
            "ranking_overrides_has_code": OVERRIDE_HAS_CODE,
            "ranking_overrides_results_count": len(ranking_overrides_results),
            "canonical_id": canonical_id,
            "detail_title": detail_body.get("title"),
            "similar_semantic_results_count": len(similar_results),
            "similar_radar_adjusted_results_count": len(adjusted_results),
        },
        "checks": checks,
        "endpoints": endpoints,
        "verdict": {
            "ok": len(required_failed_checks) == 0,
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
        },
    }

    latest_json = args.reports_dir / "discovery_api_quality_latest.json"
    latest_md = args.reports_dir / "discovery_api_quality_latest.md"
    history_json = args.reports_dir / "history" / f"discovery_api_quality_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"discovery_api_quality_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    for key, value in report["summary"].items():
        print(f"[OK] {key}={value}")

    for key, value in checks.items():
        print(f"[OK] {key}={value}")

    print(f"[OK] ok={report['verdict']['ok']}")
    print(f"[OK] required_failed_count={report['verdict']['required_failed_count']}")
    print(f"[OK] required_failed_checks={report['verdict']['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if args.strict and not report["verdict"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()