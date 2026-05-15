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
CLUSTER_LIST_LIMIT = 5
TOPIC_CLUSTER_MAP_MAX_POINTS = 500

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
        lines.append(f"- params: `{payload.get('params')}`")
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


def endpoint_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "json"}


def is_non_empty_dict(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


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
        endpoints["profiles"] = endpoint_meta(profiles)

        profiles_payload = (
            profiles.get("json") if isinstance(profiles.get("json"), dict) else {}
        )
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
        endpoints["ranking"] = endpoint_meta(ranking)

        ranking_payload = (
            ranking.get("json") if isinstance(ranking.get("json"), dict) else {}
        )
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
        endpoints["ranking_overrides"] = endpoint_meta(ranking_overrides)

        topic_clusters = request_json(
            client,
            "/discovery/clusters",
            params={"limit": CLUSTER_LIST_LIMIT},
        )
        endpoints["topic_clusters"] = endpoint_meta(topic_clusters)
        topic_cluster_map = request_json(
            client,
            "/discovery/clusters/map",
        )
        endpoints["topic_cluster_map"] = endpoint_meta(topic_cluster_map)

        topic_cluster_map_with_papers = request_json(
            client,
            "/discovery/clusters/map",
            params={
                "include_papers": "true",
                "max_points": TOPIC_CLUSTER_MAP_MAX_POINTS,
            },
        )
        endpoints["topic_cluster_map_with_papers"] = endpoint_meta(
            topic_cluster_map_with_papers
        )

        topic_clusters_payload = (
            topic_clusters.get("json")
            if isinstance(topic_clusters.get("json"), dict)
            else {}
        )
        topic_cluster_results = topic_clusters_payload.get("results") or []
        topic_cluster_id = None
        if topic_cluster_results and isinstance(topic_cluster_results[0], dict):
            topic_cluster_id = topic_cluster_results[0].get("cluster_id")

        topic_cluster_detail: dict[str, Any] = {}
        if topic_cluster_id is not None:
            topic_cluster_detail = request_json(
                client,
                f"/discovery/clusters/{topic_cluster_id}",
                params={"top_k": args.top_k},
            )
            endpoints["topic_cluster_detail"] = endpoint_meta(topic_cluster_detail)

        canonical_id = args.canonical_id
        if not canonical_id and ranking_results:
            canonical_id = ranking_results[0].get("canonical_id")

        detail: dict[str, Any] = {}
        similar_semantic: dict[str, Any] = {}
        similar_radar_adjusted: dict[str, Any] = {}
        paper_topic_cluster: dict[str, Any] = {}

        if canonical_id:
            detail = request_json(client, f"/discovery/papers/{canonical_id}")
            endpoints["paper_detail"] = endpoint_meta(detail)

            similar_semantic = request_json(
                client,
                f"/discovery/papers/{canonical_id}/similar",
                params={"top_k": args.top_k, "rank_by": "semantic"},
            )
            endpoints["similar_semantic"] = endpoint_meta(similar_semantic)

            similar_radar_adjusted = request_json(
                client,
                f"/discovery/papers/{canonical_id}/similar",
                params={"top_k": args.top_k, "rank_by": "radar_adjusted"},
            )
            endpoints["similar_radar_adjusted"] = endpoint_meta(similar_radar_adjusted)

            paper_topic_cluster = request_json(
                client,
                f"/discovery/papers/{canonical_id}/cluster",
            )
            endpoints["paper_topic_cluster"] = endpoint_meta(paper_topic_cluster)

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
    detail_body = (
        detail_payload.get("detail")
        if isinstance(detail_payload.get("detail"), dict)
        else {}
    )

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

    topic_cluster_detail_payload = (
        topic_cluster_detail.get("json")
        if isinstance(topic_cluster_detail.get("json"), dict)
        else {}
    )
    topic_cluster_detail_summary = (
        topic_cluster_detail_payload.get("summary")
        if isinstance(topic_cluster_detail_payload.get("summary"), dict)
        else {}
    )
    topic_cluster_detail_papers = topic_cluster_detail_payload.get("papers") or []

    topic_cluster_map_payload = (
        topic_cluster_map.get("json")
        if isinstance(topic_cluster_map.get("json"), dict)
        else {}
    )
    topic_cluster_map_points = topic_cluster_map_payload.get("points") or []

    topic_cluster_map_with_papers_payload = (
        topic_cluster_map_with_papers.get("json")
        if isinstance(topic_cluster_map_with_papers.get("json"), dict)
        else {}
    )
    topic_cluster_map_with_papers_points = (
        topic_cluster_map_with_papers_payload.get("points") or []
    )

    paper_topic_cluster_payload = (
        paper_topic_cluster.get("json")
        if isinstance(paper_topic_cluster.get("json"), dict)
        else {}
    )
    paper_topic_cluster_assignment = paper_topic_cluster_payload.get("assignment")
    paper_topic_cluster_cluster = paper_topic_cluster_payload.get("cluster")

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

    topic_clusters_label_candidates_present = (
        len(topic_cluster_results) > 0
        and all(
            isinstance(row, dict)
            and is_non_empty_list(row.get("label_candidates"))
            for row in topic_cluster_results
        )
    )
    topic_clusters_cluster_ids_present = (
        len(topic_cluster_results) > 0
        and all(
            isinstance(row, dict) and isinstance(row.get("cluster_id"), int)
            for row in topic_cluster_results
        )
    )
    topic_clusters_returned_count_matches = (
        topic_clusters_payload.get("returned_count") == len(topic_cluster_results)
        and len(topic_cluster_results) > 0
    )
    topic_cluster_detail_found = (
        topic_cluster_detail_payload.get("found") is True
        and topic_cluster_detail_payload.get("cluster_id") == topic_cluster_id
    )
    paper_topic_cluster_found = (
        paper_topic_cluster_payload.get("found") is True
        and paper_topic_cluster_payload.get("canonical_id") == canonical_id
    )
    paper_topic_cluster_id_match = (
        is_non_empty_dict(paper_topic_cluster_assignment)
        and is_non_empty_dict(paper_topic_cluster_cluster)
        and paper_topic_cluster_assignment.get("cluster_id")
        == paper_topic_cluster_cluster.get("cluster_id")
    )

    topic_cluster_map_projection_build_id_present = bool(
        topic_cluster_map_payload.get("projection_build_id")
    )
    topic_cluster_map_cluster_build_id_present = bool(
        topic_cluster_map_payload.get("cluster_build_id")
    )
    topic_cluster_map_retrieval_build_id_present = bool(
        topic_cluster_map_payload.get("retrieval_build_id")
    )
    topic_cluster_map_algorithm_present = bool(
        topic_cluster_map_payload.get("projection_algorithm")
    )
    topic_cluster_map_counts_present = (
        int(topic_cluster_map_payload.get("point_count") or 0) > 0
        and int(topic_cluster_map_payload.get("centroid_count") or 0) > 0
        and int(topic_cluster_map_payload.get("representative_count") or 0) > 0
        and int(topic_cluster_map_payload.get("sampled_count") or 0) > 0
    )

    topic_cluster_map_points_have_xy = (
        len(topic_cluster_map_points) > 0
        and all(
            isinstance(row, dict)
            and isinstance(row.get("cluster_id"), int)
            and isinstance(row.get("x"), int | float)
            and isinstance(row.get("y"), int | float)
            for row in topic_cluster_map_points
        )
    )
    topic_cluster_map_centroid_points_present = any(
        isinstance(row, dict) and row.get("point_type") == "centroid"
        for row in topic_cluster_map_points
    )
    topic_cluster_map_default_centroids_only = (
        len(topic_cluster_map_points) > 0
        and topic_cluster_map_payload.get("include_papers") is False
        and all(
            isinstance(row, dict) and row.get("point_type") == "centroid"
            for row in topic_cluster_map_points
        )
    )
    topic_cluster_map_returned_count_matches = (
        topic_cluster_map_payload.get("returned_points_count")
        == len(topic_cluster_map_points)
        and len(topic_cluster_map_points) > 0
    )

    topic_cluster_map_with_papers_points_have_xy = (
        len(topic_cluster_map_with_papers_points) > 0
        and all(
            isinstance(row, dict)
            and isinstance(row.get("cluster_id"), int)
            and isinstance(row.get("x"), int | float)
            and isinstance(row.get("y"), int | float)
            for row in topic_cluster_map_with_papers_points
        )
    )
    topic_cluster_map_with_papers_limit_respected = (
        len(topic_cluster_map_with_papers_points) > 0
        and len(topic_cluster_map_with_papers_points) <= TOPIC_CLUSTER_MAP_MAX_POINTS
        and topic_cluster_map_with_papers_payload.get("returned_points_count")
        == len(topic_cluster_map_with_papers_points)
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
        "topic_clusters_endpoint_ok": bool(topic_clusters.get("ok")),
        "topic_clusters_results_non_empty": len(topic_cluster_results) > 0,
        "topic_clusters_returned_count_matches": topic_clusters_returned_count_matches,
        "topic_clusters_cluster_ids_present": topic_clusters_cluster_ids_present,
        "topic_clusters_label_candidates_present": topic_clusters_label_candidates_present,
        "topic_cluster_id_resolved": topic_cluster_id is not None,
        "topic_cluster_map_endpoint_ok": bool(topic_cluster_map.get("ok")),
        "topic_cluster_map_results_non_empty": len(topic_cluster_map_points) > 0,
        "topic_cluster_map_projection_build_id_present": (
            topic_cluster_map_projection_build_id_present
        ),
        "topic_cluster_map_cluster_build_id_present": (
            topic_cluster_map_cluster_build_id_present
        ),
        "topic_cluster_map_retrieval_build_id_present": (
            topic_cluster_map_retrieval_build_id_present
        ),
        "topic_cluster_map_algorithm_present": topic_cluster_map_algorithm_present,
        "topic_cluster_map_counts_present": topic_cluster_map_counts_present,
        "topic_cluster_map_points_have_xy": topic_cluster_map_points_have_xy,
        "topic_cluster_map_centroid_points_present": (
            topic_cluster_map_centroid_points_present
        ),
        "topic_cluster_map_default_centroids_only": (
            topic_cluster_map_default_centroids_only
        ),
        "topic_cluster_map_returned_count_matches": (
            topic_cluster_map_returned_count_matches
        ),
        "topic_cluster_map_with_papers_endpoint_ok": bool(
            topic_cluster_map_with_papers.get("ok")
        ),
        "topic_cluster_map_with_papers_results_non_empty": (
                len(topic_cluster_map_with_papers_points) > 0
        ),
        "topic_cluster_map_with_papers_points_have_xy": (
            topic_cluster_map_with_papers_points_have_xy
        ),
        "topic_cluster_map_with_papers_limit_respected": (
            topic_cluster_map_with_papers_limit_respected
        ),
        "topic_cluster_detail_endpoint_ok": bool(topic_cluster_detail.get("ok")),
        "topic_cluster_detail_found": topic_cluster_detail_found,
        "topic_cluster_detail_label_candidates_present": is_non_empty_list(
            topic_cluster_detail_summary.get("label_candidates")
        ),
        "topic_cluster_detail_papers_non_empty": len(topic_cluster_detail_papers) > 0,
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
        "paper_topic_cluster_endpoint_ok": bool(paper_topic_cluster.get("ok")),
        "paper_topic_cluster_found": paper_topic_cluster_found,
        "paper_topic_cluster_assignment_present": is_non_empty_dict(
            paper_topic_cluster_assignment
        ),
        "paper_topic_cluster_cluster_present": is_non_empty_dict(
            paper_topic_cluster_cluster
        ),
        "paper_topic_cluster_id_match": paper_topic_cluster_id_match,
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
            "cluster_list_limit": CLUSTER_LIST_LIMIT,
            "topic_cluster_map_max_points": TOPIC_CLUSTER_MAP_MAX_POINTS,
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
            "topic_cluster_count": (
                topic_clusters_payload.get("cluster_count")
                or topic_clusters_payload.get("total_cluster_count")
            ),
            "topic_clusters_returned_count": len(topic_cluster_results),
            "topic_cluster_id": topic_cluster_id,
            "topic_cluster_map_projection_build_id": topic_cluster_map_payload.get(
                "projection_build_id"
            ),
            "topic_cluster_map_projection_algorithm": topic_cluster_map_payload.get(
                "projection_algorithm"
            ),
            "topic_cluster_map_point_count": topic_cluster_map_payload.get("point_count"),
            "topic_cluster_map_centroid_count": topic_cluster_map_payload.get(
                "centroid_count"
            ),
            "topic_cluster_map_representative_count": topic_cluster_map_payload.get(
                "representative_count"
            ),
            "topic_cluster_map_sampled_count": topic_cluster_map_payload.get(
                "sampled_count"
            ),
            "topic_cluster_map_returned_points_count": len(topic_cluster_map_points),
            "topic_cluster_map_with_papers_returned_points_count": len(
                topic_cluster_map_with_papers_points
            ),
            "topic_cluster_detail_total_papers": topic_cluster_detail_payload.get(
                "total_papers"
            ),
            "topic_cluster_detail_returned_papers_count": len(
                topic_cluster_detail_papers
            ),
            "canonical_id": canonical_id,
            "detail_title": detail_body.get("title"),
            "similar_semantic_results_count": len(similar_results),
            "similar_radar_adjusted_results_count": len(adjusted_results),
            "paper_topic_cluster_cluster_id": (
                paper_topic_cluster_assignment.get("cluster_id")
                if isinstance(paper_topic_cluster_assignment, dict)
                else None
            ),
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
