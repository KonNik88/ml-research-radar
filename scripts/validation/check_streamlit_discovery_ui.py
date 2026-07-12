from __future__ import annotations

import argparse
import importlib.util
import json
import os
import py_compile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_APP_PATH = Path("services/ui/app.py")
DEFAULT_API_BASE_URL = os.getenv("ML_RADAR_API_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_TIMEOUT_SECONDS = 30

REPORT_DIR = Path("artifacts/reports/ui")
HISTORY_DIR = REPORT_DIR / "history"

LATEST_JSON_PATH = REPORT_DIR / "streamlit_discovery_ui_quality_latest.json"
LATEST_MD_PATH = REPORT_DIR / "streamlit_discovery_ui_quality_latest.md"

TEST_CANONICAL_ID = "bd3c9332f17370fa801e6ac9542f125a"

TOPIC_CLUSTER_SORT_VALUES = [
    "size_desc",
    "cluster_id_asc",
    "mean_radar_desc",
    "artifact_ready_desc",
]

TOPIC_CLUSTER_DETAIL_SORT_VALUES = [
    "rank",
    "similarity_desc",
    "radar_score",
    "implementation_readiness_score",
    "citation_signal_score",
    "year_desc",
]

REQUIRED_UI_SNIPPETS = [
    "st.set_page_config",
    "ML Research Radar",
    "Discovery ranking",
    "Run discovery ranking",
    "Reset discovery filters",
    "fetch_profiles",
    "fetch_ranking",
    "fetch_paper_detail",
    "fetch_similar_papers",
    "render_similar_papers",
]

DISCOVERY_ENDPOINT_STRINGS = [
    "/discovery/profiles",
    "/discovery/ranking/",
    "/discovery/papers/",
    "/discovery/papers/{canonical_id}/similar",
]

SIMILAR_MODE_SNIPPETS = [
    "SIMILAR_RANK_BY_OPTIONS",
    "semantic",
    "radar_adjusted",
]

SEARCH_UI_SNIPPETS = [
    "Search",
    "SEARCH_MODE_OPTIONS",
    "SEARCH_SORT_OPTIONS",
    "fetch_search",
    "build_search_params",
    "render_search_tab",
    "render_search_results",
    "search_query",
    "search_mode",
    "search_payload",
    "Run search",
    "Open search result in Paper workspace",
    "/search",
]

QDRANT_EXPERIMENTAL_UI_SNIPPETS = [
    "Experimental Qdrant dense search",
    "fetch_qdrant_experimental_search",
    "build_qdrant_experimental_search_params",
    "render_qdrant_experimental_search_block",
    "render_qdrant_search_results",
    "qdrant_search_query",
    "qdrant_search_top_k",
    "qdrant_search_payload",
    "Run experimental Qdrant search",
    "Open Qdrant result in Paper workspace",
    "/experimental/search/qdrant",
    "dense_qdrant",
]

QDRANT_RUNTIME_STATUS_UI_SNIPPETS = [
    "Qdrant runtime",
    "render_qdrant_runtime_status",
    "Qdrant diagnostics are unavailable in the runtime snapshot.",
    "Qdrant: OK",
    "Qdrant: unavailable",
    "Qdrant diagnostic error",
    "Qdrant runtime details",
    "points_match_corpus",
    "expected_corpus_doc_count",
    "collection_name",
]

CITATION_GRAPH_STATUS_UI_SNIPPETS = [
    "Citation graph status",
    "fetch_citation_graph_status",
    "render_citation_graph_status_panel",
    "/citation-graph/status",
    "citation_graph_status_payload",
    "Load citation graph status",
    "Runtime enabled",
    "Safe locally",
    "Runtime loader",
    "publication-ready",
]

TOPIC_CLUSTER_UI_SNIPPETS = [
    "Topic clusters",
    "fetch_topic_clusters",
    "fetch_topic_cluster_detail",
    "fetch_paper_topic_cluster",
    "/discovery/clusters",
    "/discovery/papers/{canonical_id}/cluster",
    "CLUSTER_SORT_OPTIONS",
    "CLUSTER_SORT_LABELS",
    "size_desc",
    "cluster_id_asc",
    "mean_radar_desc",
    "artifact_ready_desc",
    "Load topic clusters",
    "Cluster sort by",
    "Cluster detail top K",
    "Selected paper topic cluster",
    "Topic map",
    "fetch_topic_cluster_map",
    "render_topic_map",
    "/discovery/clusters/map",
    "Load topic map",
    "Show paper points",
    "Topic map projection",
    "CLUSTER_PAPER_SORT_OPTIONS",
    "CLUSTER_PAPER_SORT_LABELS",
    "Cluster paper sort by",
    "Mapped cluster paper sort by",
    "similarity_desc",
    "citation_signal_score",
    "year_desc",
]

CLUSTER_DETAIL_FILTER_UI_SNIPPETS = [
    "Cluster detail filters",
    "cluster_detail_min_year",
    "cluster_detail_max_year",
    "cluster_detail_has_code",
    "cluster_detail_has_github",
    "cluster_detail_min_radar_score",
    "cluster_detail_min_implementation_readiness_score",
    "cluster_detail_min_citation_signal_score",
    "build_cluster_detail_params",
    "filtered_papers_count",
    "Effective cluster detail filters",
    "Reset cluster detail filters",
]

ARTIFACT_EXPLORER_UI_SNIPPETS = [
    "Artifact explorer",
    "fetch_artifacts",
    "build_artifact_params",
    "render_artifact_explorer",
    "artifact_provider",
    "artifact_relation_type",
    "artifact_min_stars",
    "artifact_github_status",
    "artifact_has_github_metadata",
    "/artifacts",
    "Load artifacts",
    "fetch_artifact_detail",
    "fetch_artifact_linked_papers",
    "build_artifact_linked_papers_params",
    "render_artifact_detail_panel",
    "render_artifact_linked_papers",
    "selected_artifact_id",
    "artifact_detail_payload",
    "artifact_linked_papers_payload",
    "artifact_linked_papers_limit",
    "artifact_linked_papers_sort_by",
    "Load artifact detail",
    "/papers",
    "pushed_desc",
    "updated_desc",
    "artifact_pushed_after",
    "artifact_pushed_before",
    "artifact_updated_after",
    "artifact_updated_before",
    "pushed_after",
    "pushed_before",
    "updated_after",
    "updated_before",
]

ARTIFACT_LINKED_PAPER_NAVIGATION_SNIPPETS = [
    "render_artifact_linked_papers",
    "Open this paper in Paper workspace",
    "select_paper(canonical_id)",
    "Selected paper updated. Open the Paper workspace tab.",
    "artifact_linked_papers_payload",
]

PAPER_WORKSPACE_UI_SNIPPETS = [
    "Paper workspace",
    "selected_paper_canonical_id",
    "selected_paper_detail_payload",
    "selected_paper_similar_payload",
    "selected_paper_cluster_payload",
    "selected_paper_similar_top_k",
    "selected_paper_similar_rank_by",
    "reset_selected_paper_payloads",
    "select_paper",
    "clear_selected_paper",
    "render_paper_workspace",
    "Load selected paper detail",
    "Load selected paper similar papers",
    "Load selected paper topic cluster",
    "Clear selected paper",
    "Open in Paper workspace",
]

PAPER_NAVIGATION_POLISH_UI_SNIPPETS = [
    "select_paper_from_ui",
    "render_open_paper_workspace_button",
    "Selected paper updated. Open the Paper workspace tab.",
    "Open search result in Paper workspace",
    "Open Qdrant result in Paper workspace",
    "Open similar paper in Paper workspace",
    "Open selected paper in Paper workspace",
    "Open this paper in Paper workspace",
]

PAPER_WORKSPACE_ARTIFACT_UI_SNIPPETS = [
    "Selected paper artifacts",
    "selected_paper_selected_artifact_id",
    "selected_paper_artifact_detail_payload",
    "selected_paper_artifact_linked_papers_payload",
    "selected_paper_artifact_linked_papers_limit",
    "selected_paper_artifact_linked_papers_offset",
    "selected_paper_artifact_linked_papers_relation_type",
    "selected_paper_artifact_linked_papers_min_confidence",
    "selected_paper_artifact_linked_papers_sort_by",
    "reset_selected_paper_artifact_navigation",
    "build_selected_paper_artifact_linked_papers_params",
    "render_selected_paper_artifacts",
    "Load selected paper artifact detail",
    "Load selected paper artifact linked papers",
    "Other papers linked to this artifact",
]

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def utc_stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def clean_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )


def render_markdown_report(report: dict[str, Any]) -> str:
    checks = report.get("checks") or {}
    extracted = report.get("extracted_values") or {}
    errors = report.get("errors") or {}

    lines: list[str] = [
        "# Streamlit Discovery UI quality report",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- ok: `{report.get('ok')}`",
        f"- required_failed_count: `{report.get('required_failed_count')}`",
        f"- required_failed_checks: `{report.get('required_failed_checks')}`",
        "",
        "## Extracted values",
        "",
    ]

    for key, value in extracted.items():
        if isinstance(value, (dict, list)):
            pretty = json.dumps(value, ensure_ascii=False, sort_keys=False)
            lines.append(f"- {key}: `{pretty}`")
        else:
            lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Checks", ""])

    for key, value in checks.items():
        lines.append(f"- {key}: `{value}`")

    if errors:
        lines.extend(["", "## Errors / diagnostics", ""])
        for key, value in errors.items():
            lines.append(f"- {key}: `{value}`")

    lines.append("")
    return "\n".join(lines)


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(render_markdown_report(report), encoding="utf-8")


def read_text(path: Path) -> tuple[bool, str, str | None]:
    try:
        return True, path.read_text(encoding="utf-8"), None
    except Exception as exc:
        return False, "", repr(exc)


def py_compile_file(path: Path) -> tuple[bool, str | None]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, None
    except Exception as exc:
        return False, repr(exc)


def module_import_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def missing_snippets(text: str, snippets: list[str]) -> list[str]:
    return [snippet for snippet in snippets if snippet not in text]


def request_json(
    *,
    base_url: str,
    path: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bool, dict[str, Any], str | None]:
    url = f"{clean_base_url(base_url)}{path}"
    try:
        response = requests.get(url, params=params, timeout=timeout_seconds)
    except Exception as exc:
        return False, {}, repr(exc)

    if not response.ok:
        text = response.text
        if len(text) > 800:
            text = text[:800] + "..."
        return False, {}, f"HTTP {response.status_code}: {text}"

    try:
        payload = response.json()
    except Exception as exc:
        return False, {}, f"JSON parse error: {exc!r}"

    if not isinstance(payload, dict):
        return False, {}, f"Expected JSON object, got {type(payload).__name__}"

    return True, payload, None


def result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("results") or payload.get("papers") or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def first_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = result_rows(payload)
    return rows[0] if rows else None


def coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def run_api_checks(
    *,
    base_url: str,
    timeout_seconds: int,
    checks: dict[str, bool],
    extracted_values: dict[str, Any],
    errors: dict[str, Any],
) -> None:
    base_url = clean_base_url(base_url)
    extracted_values["api_base_url"] = base_url

    health_ok, health_payload, health_error = request_json(
        base_url=base_url,
        path="/health",
        timeout_seconds=timeout_seconds,
    )
    checks["api_health_endpoint_ok"] = health_ok
    checks["api_health_ready"] = bool(
        health_payload.get("ready") is True
        or str(health_payload.get("status", "")).lower() in {"ok", "ready", "healthy"}
    )
    extracted_values["api_health_status"] = health_payload.get("status")
    extracted_values["api_health_backend"] = health_payload.get("backend_mode")
    extracted_values["api_health_build_id"] = health_payload.get("build_id")
    if health_error:
        errors["api_health_error"] = health_error

    profiles_ok, profiles_payload, profiles_error = request_json(
        base_url=base_url,
        path="/discovery/profiles",
        timeout_seconds=timeout_seconds,
    )
    profiles = profiles_payload.get("profiles") or []
    checks["api_profiles_endpoint_ok"] = profiles_ok
    checks["api_profiles_non_empty"] = bool(profiles)
    extracted_values["api_profile_count"] = profiles_payload.get("profile_count", len(profiles) if isinstance(profiles, list) else None)
    extracted_values["api_profile_names"] = [
        row.get("name") for row in profiles if isinstance(row, dict) and row.get("name")
    ] if isinstance(profiles, list) else []
    if profiles_error:
        errors["api_profiles_error"] = profiles_error

    ranking_ok, ranking_payload, ranking_error = request_json(
        base_url=base_url,
        path="/discovery/ranking/recent_artifact_ready",
        params={
            "top_k": 1,
            "min_year": 2025,
            "has_code": "true",
        },
        timeout_seconds=timeout_seconds,
    )
    ranking_rows = result_rows(ranking_payload)
    filters = ranking_payload.get("filters") or {}

    min_year_echoed = filters.get("min_year") == 2025
    has_code_echoed = coerce_bool(filters.get("has_code")) is True

    checks["api_ranking_override_endpoint_ok"] = ranking_ok
    checks["api_ranking_override_results_non_empty"] = bool(ranking_rows)
    checks["api_ranking_override_filters_echoed"] = bool(min_year_echoed and has_code_echoed)
    extracted_values["api_ranking_override_results_count"] = len(ranking_rows)
    extracted_values["api_ranking_override_filters"] = filters
    if ranking_error:
        errors["api_ranking_override_error"] = ranking_error

    search_ok, search_payload, search_error = request_json(
        base_url=base_url,
        path="/search",
        params={
            "query": "graph neural networks",
            "mode": "lexical",
            "top_k": 3,
        },
        timeout_seconds=timeout_seconds,
    )
    search_rows = result_rows(search_payload)

    checks["api_search_endpoint_ok"] = search_ok
    checks["api_search_results_non_empty"] = bool(search_rows)
    checks["api_search_rows_have_documents"] = (
        bool(search_rows)
        and all(
            isinstance(row, dict)
            and isinstance(row.get("document"), dict)
            and bool(row["document"].get("canonical_id"))
            and bool(row["document"].get("title"))
            for row in search_rows
        )
    )

    extracted_values["api_search_query"] = search_payload.get("query")
    extracted_values["api_search_mode"] = search_payload.get("mode")
    extracted_values["api_search_results_count"] = len(search_rows)

    if search_error:
        errors["api_search_error"] = search_error

    clusters_ok, clusters_payload, clusters_error = request_json(
        base_url=base_url,
        path="/discovery/clusters",
        params={"limit": 1},
        timeout_seconds=timeout_seconds,
    )
    cluster_rows = result_rows(clusters_payload)
    first_cluster = first_result(clusters_payload) or {}

    checks["api_topic_clusters_endpoint_ok"] = clusters_ok
    checks["api_topic_clusters_results_non_empty"] = bool(cluster_rows)
    checks["api_topic_clusters_cluster_id_present"] = first_cluster.get("cluster_id") is not None
    checks["api_topic_clusters_label_candidates_present"] = bool(first_cluster.get("label_candidates"))

    extracted_values["api_topic_cluster_count"] = (
        clusters_payload.get("cluster_count")
        or clusters_payload.get("total_cluster_count")
    )
    extracted_values["api_topic_clusters_returned_count"] = (
        clusters_payload.get("returned_count")
        or len(cluster_rows)
    )
    extracted_values["api_topic_cluster_id"] = first_cluster.get("cluster_id")

    if clusters_error:
        errors["api_topic_clusters_error"] = clusters_error

    topic_map_ok, topic_map_payload, topic_map_error = request_json(
        base_url=base_url,
        path="/discovery/clusters/map",
        timeout_seconds=timeout_seconds,
    )
    topic_map_points = topic_map_payload.get("points") or []
    first_topic_map_point = (
        topic_map_points[0]
        if topic_map_points and isinstance(topic_map_points[0], dict)
        else {}
    )

    checks["api_topic_map_endpoint_ok"] = topic_map_ok
    checks["api_topic_map_results_non_empty"] = bool(topic_map_points)
    checks["api_topic_map_projection_build_id_present"] = bool(
        topic_map_payload.get("projection_build_id")
    )
    checks["api_topic_map_algorithm_present"] = bool(
        topic_map_payload.get("projection_algorithm")
    )
    checks["api_topic_map_points_have_xy"] = (
        bool(topic_map_points)
        and all(
            isinstance(row, dict)
            and row.get("cluster_id") is not None
            and isinstance(row.get("x"), int | float)
            and isinstance(row.get("y"), int | float)
            for row in topic_map_points
        )
    )
    checks["api_topic_map_default_centroids_only"] = (
        bool(topic_map_points)
        and topic_map_payload.get("include_papers") is False
        and all(
            isinstance(row, dict) and row.get("point_type") == "centroid"
            for row in topic_map_points
        )
    )

    extracted_values["api_topic_map_projection_build_id"] = topic_map_payload.get(
        "projection_build_id"
    )
    extracted_values["api_topic_map_projection_algorithm"] = topic_map_payload.get(
        "projection_algorithm"
    )
    extracted_values["api_topic_map_point_count"] = topic_map_payload.get("point_count")
    extracted_values["api_topic_map_returned_points_count"] = (
        topic_map_payload.get("returned_points_count") or len(topic_map_points)
    )
    extracted_values["api_topic_map_first_cluster_id"] = first_topic_map_point.get(
        "cluster_id"
    )

    if topic_map_error:
        errors["api_topic_map_error"] = topic_map_error

    artifacts_ok, artifacts_payload, artifacts_error = request_json(
        base_url=base_url,
        path="/artifacts",
        params={
            "limit": 3,
            "provider": "github",
            "has_paper_links": "true",
            "has_github_metadata": "true",
            "sort_by": "stars_desc",
        },
        timeout_seconds=timeout_seconds,
    )
    artifact_rows = result_rows(artifacts_payload)
    first_artifact = artifact_rows[0] if artifact_rows else {}
    artifact_id = (
        str(first_artifact.get("artifact_id"))
        if isinstance(first_artifact, dict) and first_artifact.get("artifact_id")
        else None
    )

    if artifact_id:
        (
            artifact_detail_ok,
            artifact_detail_payload,
            artifact_detail_error,
        ) = request_json(
            base_url=base_url,
            path=f"/artifacts/{artifact_id}",
            timeout_seconds=timeout_seconds,
        )

        (
            artifact_linked_papers_ok,
            artifact_linked_papers_payload,
            artifact_linked_papers_error,
        ) = request_json(
            base_url=base_url,
            path=f"/artifacts/{artifact_id}/papers",
            params={
                "limit": 3,
                "sort_by": "confidence_desc",
            },
            timeout_seconds=timeout_seconds,
        )
    else:
        artifact_detail_ok, artifact_detail_payload, artifact_detail_error = (
            False,
            {},
            "No artifact_id available from /artifacts",
        )
        (
            artifact_linked_papers_ok,
            artifact_linked_papers_payload,
            artifact_linked_papers_error,
        ) = (
            False,
            {},
            "No artifact_id available from /artifacts",
        )

    checks["api_artifacts_endpoint_ok"] = artifacts_ok
    checks["api_artifacts_results_non_empty"] = bool(artifact_rows)
    checks["api_artifacts_total_present"] = artifacts_payload.get("total") is not None
    checks["api_artifacts_sort_echoed"] = artifacts_payload.get("sort_by") == "stars_desc"

    extracted_values["api_artifacts_total"] = artifacts_payload.get("total")
    extracted_values["api_artifacts_results_count"] = len(artifact_rows)

    if artifacts_error:
        errors["api_artifacts_error"] = artifacts_error

    artifact_detail_body = (
        artifact_detail_payload.get("artifact")
        if isinstance(artifact_detail_payload.get("artifact"), dict)
        else {}
    )
    artifact_linked_paper_rows = result_rows(artifact_linked_papers_payload)

    checks["api_artifact_detail_endpoint_ok"] = artifact_detail_ok
    checks["api_artifact_detail_found"] = (
        artifact_detail_payload.get("found") is True
        and artifact_detail_payload.get("artifact_id") == artifact_id
        and artifact_detail_body.get("artifact_id") == artifact_id
    )
    checks["api_artifact_linked_papers_endpoint_ok"] = artifact_linked_papers_ok
    checks["api_artifact_linked_papers_results_non_empty"] = bool(
        artifact_linked_paper_rows
    )
    checks["api_artifact_linked_papers_counts_valid"] = (
        int(artifact_linked_papers_payload.get("total") or 0)
        >= len(artifact_linked_paper_rows)
        > 0
    )
    checks["api_artifact_linked_papers_rows_match"] = (
        bool(artifact_linked_paper_rows)
        and all(
            isinstance(row, dict)
            and row.get("artifact_id") == artifact_id
            and bool(row.get("canonical_id"))
            and bool(row.get("relation_type"))
            and isinstance(row.get("paper"), dict)
            and row["paper"].get("canonical_id") == row.get("canonical_id")
            and bool(row["paper"].get("title"))
            for row in artifact_linked_paper_rows
        )
    )

    extracted_values["api_artifact_detail_artifact_id"] = artifact_id
    extracted_values["api_artifact_detail_provider"] = artifact_detail_body.get("provider")
    extracted_values["api_artifact_detail_type"] = artifact_detail_body.get("artifact_type")
    extracted_values["api_artifact_detail_linked_papers_count"] = (
        artifact_detail_body.get("linked_papers_count")
    )
    extracted_values["api_artifact_linked_papers_total"] = (
        artifact_linked_papers_payload.get("total")
    )
    extracted_values["api_artifact_linked_papers_results_count"] = len(
        artifact_linked_paper_rows
    )

    if artifact_detail_error:
        errors["api_artifact_detail_error"] = artifact_detail_error

    if artifact_linked_papers_error:
        errors["api_artifact_linked_papers_error"] = artifact_linked_papers_error

    sort_smoke: dict[str, dict[str, Any]] = {}
    sorted_size_payload: dict[str, Any] = {}
    artifact_ready_payload: dict[str, Any] = {}

    for sort_value in TOPIC_CLUSTER_SORT_VALUES:
        sort_ok, sort_payload, sort_error = request_json(
            base_url=base_url,
            path="/discovery/clusters",
            params={
                "limit": 1,
                "min_size": 1,
                "sort_by": sort_value,
            },
            timeout_seconds=timeout_seconds,
        )
        sort_rows = result_rows(sort_payload)
        sort_smoke[sort_value] = {
            "ok": sort_ok,
            "results_count": len(sort_rows),
            "error": sort_error,
        }
        checks[f"api_topic_clusters_sort_{sort_value}_ok"] = sort_ok
        checks[f"api_topic_clusters_sort_{sort_value}_non_empty"] = bool(sort_rows)

        if sort_value == "size_desc" and sort_ok:
            sorted_size_payload = sort_payload
        if sort_value == "artifact_ready_desc" and sort_ok:
            artifact_ready_payload = sort_payload

    size_desc_rows = result_rows(sorted_size_payload)
    size_desc_first = first_result(sorted_size_payload) or {}

    checks["api_topic_clusters_sorted_endpoint_ok"] = bool(sort_smoke.get("size_desc", {}).get("ok"))
    checks["api_topic_clusters_sorted_results_non_empty"] = bool(size_desc_rows)
    checks["api_topic_clusters_sorted_cluster_id_present"] = size_desc_first.get("cluster_id") is not None
    checks["api_topic_clusters_supported_sort_values_ok"] = all(
        bool(sort_smoke.get(sort_value, {}).get("ok")) for sort_value in TOPIC_CLUSTER_SORT_VALUES
    )

    extracted_values["api_topic_clusters_sort_smoke"] = sort_smoke
    extracted_values["api_topic_clusters_supported_sort_values"] = TOPIC_CLUSTER_SORT_VALUES

    cluster_id = (
        size_desc_first.get("cluster_id")
        if size_desc_first.get("cluster_id") is not None
        else first_cluster.get("cluster_id")
    )

    artifact_ready_first = first_result(artifact_ready_payload) or {}
    cluster_detail_filter_id = (
        artifact_ready_first.get("cluster_id")
        if artifact_ready_first.get("cluster_id") is not None
        else cluster_id
    )

    if cluster_id is not None:
        cluster_detail_ok, cluster_detail_payload, cluster_detail_error = request_json(
            base_url=base_url,
            path=f"/discovery/clusters/{cluster_id}",
            params={"top_k": 1},
            timeout_seconds=timeout_seconds,
        )
    else:
        cluster_detail_ok, cluster_detail_payload, cluster_detail_error = (
            False,
            {},
            "No cluster_id available from /discovery/clusters",
        )

    if cluster_detail_filter_id is not None:
        (
            cluster_detail_filter_ok,
            cluster_detail_filter_payload,
            cluster_detail_filter_error,
        ) = request_json(
            base_url=base_url,
            path=f"/discovery/clusters/{cluster_detail_filter_id}",
            params={
                "top_k": 3,
                "min_year": 2020,
                "has_code": "true",
                "sort_by": "radar_score",
            },
            timeout_seconds=timeout_seconds,
        )
    else:
        (
            cluster_detail_filter_ok,
            cluster_detail_filter_payload,
            cluster_detail_filter_error,
        ) = (
            False,
            {},
            "No cluster_id available for cluster detail filter smoke",
        )

    cluster_detail_sort_smoke: dict[str, dict[str, Any]] = {}

    if cluster_id is not None:
        for sort_value in TOPIC_CLUSTER_DETAIL_SORT_VALUES:
            sort_ok, sort_payload, sort_error = request_json(
                base_url=base_url,
                path=f"/discovery/clusters/{cluster_id}",
                params={"top_k": 3, "sort_by": sort_value},
                timeout_seconds=timeout_seconds,
            )
            sort_rows = result_rows(sort_payload)
            cluster_detail_sort_smoke[sort_value] = {
                "ok": sort_ok,
                "results_count": len(sort_rows),
                "sort_by_echoed": sort_payload.get("sort_by") == sort_value,
                "error": sort_error,
            }
            checks[f"api_topic_cluster_detail_sort_{sort_value}_ok"] = sort_ok
            checks[f"api_topic_cluster_detail_sort_{sort_value}_non_empty"] = bool(sort_rows)
            checks[f"api_topic_cluster_detail_sort_{sort_value}_echoed"] = (
                sort_payload.get("sort_by") == sort_value
            )
    else:
        for sort_value in TOPIC_CLUSTER_DETAIL_SORT_VALUES:
            cluster_detail_sort_smoke[sort_value] = {
                "ok": False,
                "results_count": 0,
                "sort_by_echoed": False,
                "error": "No cluster_id available",
            }
            checks[f"api_topic_cluster_detail_sort_{sort_value}_ok"] = False
            checks[f"api_topic_cluster_detail_sort_{sort_value}_non_empty"] = False
            checks[f"api_topic_cluster_detail_sort_{sort_value}_echoed"] = False

    cluster_detail_rows = result_rows(cluster_detail_payload)
    cluster_detail_summary = (
        cluster_detail_payload.get("summary")
        or cluster_detail_payload.get("cluster")
        or {}
    )

    cluster_detail_filter_rows = result_rows(cluster_detail_filter_payload)
    cluster_detail_filter_effective = (
        cluster_detail_filter_payload.get("filters")
        if isinstance(cluster_detail_filter_payload.get("filters"), dict)
        else {}
    )

    checks["api_topic_cluster_detail_supported_sort_values_ok"] = all(
        bool(cluster_detail_sort_smoke.get(sort_value, {}).get("ok"))
        for sort_value in TOPIC_CLUSTER_DETAIL_SORT_VALUES
    )
    checks["api_topic_cluster_detail_sort_results_non_empty"] = all(
        bool(cluster_detail_sort_smoke.get(sort_value, {}).get("results_count"))
        for sort_value in TOPIC_CLUSTER_DETAIL_SORT_VALUES
    )
    checks["api_topic_cluster_detail_sort_values_echoed"] = all(
        bool(cluster_detail_sort_smoke.get(sort_value, {}).get("sort_by_echoed"))
        for sort_value in TOPIC_CLUSTER_DETAIL_SORT_VALUES
    )

    extracted_values["api_topic_cluster_detail_supported_sort_values"] = (
        TOPIC_CLUSTER_DETAIL_SORT_VALUES
    )
    extracted_values["api_topic_cluster_detail_sort_smoke"] = cluster_detail_sort_smoke

    checks["api_topic_cluster_detail_endpoint_ok"] = cluster_detail_ok
    checks["api_topic_cluster_detail_papers_non_empty"] = bool(cluster_detail_rows)
    checks["api_topic_cluster_detail_label_candidates_present"] = bool(
        cluster_detail_summary.get("label_candidates")
        or cluster_detail_payload.get("label_candidates")
    )
    extracted_values["api_topic_cluster_detail_cluster_id"] = cluster_id
    extracted_values["api_topic_cluster_detail_returned_papers_count"] = (
        cluster_detail_payload.get("returned_papers_count")
        or len(cluster_detail_rows)
    )
    if cluster_detail_error:
        errors["api_topic_cluster_detail_error"] = cluster_detail_error

    checks["api_topic_cluster_detail_filter_endpoint_ok"] = cluster_detail_filter_ok
    checks["api_topic_cluster_detail_filter_results_non_empty"] = bool(
        cluster_detail_filter_rows
    )
    checks["api_topic_cluster_detail_filter_filters_echoed"] = (
        cluster_detail_filter_effective.get("min_year") == 2020
        and coerce_bool(cluster_detail_filter_effective.get("has_code")) is True
    )
    checks["api_topic_cluster_detail_filter_counts_valid"] = (
        int(cluster_detail_filter_payload.get("total_papers") or 0)
        >= int(cluster_detail_filter_payload.get("filtered_papers_count") or 0)
        >= int(cluster_detail_filter_payload.get("returned_papers_count") or 0)
        == len(cluster_detail_filter_rows)
    )
    checks["api_topic_cluster_detail_filter_rows_match"] = (
        bool(cluster_detail_filter_rows)
        and all(
            isinstance(row, dict)
            and int(row.get("year") or 0) >= 2020
            and bool(row.get("has_code_artifact")) is True
            for row in cluster_detail_filter_rows
        )
    )

    extracted_values["api_topic_cluster_detail_filter_cluster_id"] = (
        cluster_detail_filter_id
    )
    extracted_values["api_topic_cluster_detail_filter_filters"] = (
        cluster_detail_filter_effective
    )
    extracted_values["api_topic_cluster_detail_filter_total_papers"] = (
        cluster_detail_filter_payload.get("total_papers")
    )
    extracted_values["api_topic_cluster_detail_filter_filtered_papers_count"] = (
        cluster_detail_filter_payload.get("filtered_papers_count")
    )
    extracted_values["api_topic_cluster_detail_filter_returned_papers_count"] = (
        len(cluster_detail_filter_rows)
    )

    if cluster_detail_filter_error:
        errors["api_topic_cluster_detail_filter_error"] = cluster_detail_filter_error

    paper_cluster_ok, paper_cluster_payload, paper_cluster_error = request_json(
        base_url=base_url,
        path=f"/discovery/papers/{TEST_CANONICAL_ID}/cluster",
        timeout_seconds=timeout_seconds,
    )

    paper_assignment = paper_cluster_payload.get("assignment") or {}
    paper_cluster = paper_cluster_payload.get("cluster") or {}

    checks["api_paper_topic_cluster_endpoint_ok"] = paper_cluster_ok
    checks["api_paper_topic_cluster_assignment_present"] = bool(
        isinstance(paper_assignment, dict) and paper_assignment.get("cluster_id") is not None
    )
    checks["api_paper_topic_cluster_cluster_present"] = bool(
        isinstance(paper_cluster, dict) and paper_cluster.get("cluster_id") is not None
    )
    extracted_values["api_paper_topic_cluster_canonical_id"] = TEST_CANONICAL_ID
    extracted_values["api_paper_topic_cluster_cluster_id"] = paper_assignment.get("cluster_id")

    if paper_cluster_error:
        errors["api_paper_topic_cluster_error"] = paper_cluster_error


def build_report(
    *,
    app_path: Path,
    check_api: bool,
    api_base_url: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    extracted_values: dict[str, Any] = {}
    errors: dict[str, Any] = {}

    extracted_values["app_path"] = str(app_path)
    extracted_values["check_api"] = check_api

    checks["app_exists"] = app_path.exists()
    checks["app_non_empty"] = app_path.exists() and app_path.stat().st_size > 0

    if app_path.exists():
        compile_ok, compile_error = py_compile_file(app_path)
    else:
        compile_ok, compile_error = False, "App path does not exist"

    checks["py_compile_ok"] = compile_ok
    if compile_error:
        errors["py_compile_error"] = compile_error

    app_read_ok, app_text, read_error = read_text(app_path) if app_path.exists() else (False, "", "App path does not exist")
    checks["app_read_ok"] = app_read_ok
    if read_error:
        errors["app_read_error"] = read_error

    checks["streamlit_import_ok"] = module_import_available("streamlit")
    checks["requests_import_ok"] = module_import_available("requests")

    missing_required = missing_snippets(app_text, REQUIRED_UI_SNIPPETS)
    missing_discovery = missing_snippets(app_text, DISCOVERY_ENDPOINT_STRINGS)
    missing_similar = missing_snippets(app_text, SIMILAR_MODE_SNIPPETS)
    missing_search = missing_snippets(app_text, SEARCH_UI_SNIPPETS)
    missing_qdrant_experimental = missing_snippets(
        app_text,
        QDRANT_EXPERIMENTAL_UI_SNIPPETS,
    )
    missing_qdrant_runtime_status = missing_snippets(
        app_text,
        QDRANT_RUNTIME_STATUS_UI_SNIPPETS,
    )
    missing_citation_graph_status = missing_snippets(
        app_text,
        CITATION_GRAPH_STATUS_UI_SNIPPETS,
    )
    missing_topic = missing_snippets(app_text, TOPIC_CLUSTER_UI_SNIPPETS)
    missing_cluster_detail_filters = missing_snippets(
        app_text,
        CLUSTER_DETAIL_FILTER_UI_SNIPPETS,
    )
    missing_artifact_explorer = missing_snippets(
        app_text,
        ARTIFACT_EXPLORER_UI_SNIPPETS,
    )

    missing_artifact_linked_paper_navigation = missing_snippets(
        app_text,
        ARTIFACT_LINKED_PAPER_NAVIGATION_SNIPPETS,
    )

    missing_paper_workspace = missing_snippets(
        app_text,
        PAPER_WORKSPACE_UI_SNIPPETS,
    )

    missing_paper_navigation_polish = missing_snippets(
        app_text,
        PAPER_NAVIGATION_POLISH_UI_SNIPPETS,
    )

    missing_paper_workspace_artifact = missing_snippets(
        app_text,
        PAPER_WORKSPACE_ARTIFACT_UI_SNIPPETS,
    )

    checks["required_ui_snippets_present"] = not missing_required
    checks["discovery_endpoint_strings_present"] = not missing_discovery
    checks["similar_modes_present"] = not missing_similar
    checks["search_tab_ui_snippets_present"] = not missing_search
    checks["qdrant_experimental_ui_snippets_present"] = (
        not missing_qdrant_experimental
    )
    checks["qdrant_runtime_status_ui_snippets_present"] = (
        not missing_qdrant_runtime_status
    )
    checks["citation_graph_status_ui_snippets_present"] = (
        not missing_citation_graph_status
    )
    checks["topic_cluster_ui_snippets_present"] = not missing_topic
    checks["cluster_detail_filter_ui_snippets_present"] = (
        not missing_cluster_detail_filters
    )
    checks["reset_button_present"] = "Reset discovery filters" in app_text
    checks["no_deprecated_use_container_width"] = "use_container_width" not in app_text
    checks["legacy_search_endpoint_absent"] = (
            "render_legacy_search" not in app_text
            and "legacy_search_payload" not in app_text
    )
    checks["artifact_explorer_ui_snippets_present"] = not missing_artifact_explorer
    checks["artifact_linked_paper_navigation_snippets_present"] = (
        not missing_artifact_linked_paper_navigation
    )
    checks["paper_workspace_ui_snippets_present"] = not missing_paper_workspace
    checks["paper_navigation_polish_ui_snippets_present"] = (
        not missing_paper_navigation_polish
    )
    checks["paper_workspace_artifact_ui_snippets_present"] = (
        not missing_paper_workspace_artifact
    )

    extracted_values["missing_required_ui_snippets"] = missing_required
    extracted_values["missing_discovery_endpoint_strings"] = missing_discovery
    extracted_values["missing_similar_mode_snippets"] = missing_similar
    extracted_values["missing_search_ui_snippets"] = missing_search
    extracted_values["missing_qdrant_experimental_ui_snippets"] = (
        missing_qdrant_experimental
    )
    extracted_values["missing_qdrant_runtime_status_ui_snippets"] = (
        missing_qdrant_runtime_status
    )
    extracted_values["missing_citation_graph_status_ui_snippets"] = (
        missing_citation_graph_status
    )
    extracted_values["missing_topic_cluster_ui_snippets"] = missing_topic
    extracted_values["missing_cluster_detail_filter_ui_snippets"] = (
        missing_cluster_detail_filters
    )
    extracted_values["missing_artifact_explorer_ui_snippets"] = missing_artifact_explorer
    extracted_values["missing_artifact_linked_paper_navigation_snippets"] = (
        missing_artifact_linked_paper_navigation
    )
    extracted_values["missing_paper_workspace_ui_snippets"] = missing_paper_workspace
    extracted_values["missing_paper_navigation_polish_ui_snippets"] = (
        missing_paper_navigation_polish
    )
    extracted_values["missing_paper_workspace_artifact_ui_snippets"] = (
        missing_paper_workspace_artifact
    )

    if check_api:
        run_api_checks(
            base_url=api_base_url,
            timeout_seconds=timeout_seconds,
            checks=checks,
            extracted_values=extracted_values,
            errors=errors,
        )

    required_checks = [
        "app_exists",
        "app_non_empty",
        "py_compile_ok",
        "app_read_ok",
        "streamlit_import_ok",
        "requests_import_ok",
        "required_ui_snippets_present",
        "discovery_endpoint_strings_present",
        "similar_modes_present",
        "search_tab_ui_snippets_present",
        "qdrant_experimental_ui_snippets_present",
        "qdrant_runtime_status_ui_snippets_present",
        "citation_graph_status_ui_snippets_present",
        "topic_cluster_ui_snippets_present",
        "cluster_detail_filter_ui_snippets_present",
        "reset_button_present",
        "no_deprecated_use_container_width",
        "legacy_search_endpoint_absent",
        "artifact_explorer_ui_snippets_present",
        "artifact_linked_paper_navigation_snippets_present",
        "paper_workspace_ui_snippets_present",
        "paper_navigation_polish_ui_snippets_present",
        "paper_workspace_artifact_ui_snippets_present",
    ]

    if check_api:
        required_checks.extend(
            [
                "api_health_endpoint_ok",
                "api_health_ready",
                "api_profiles_endpoint_ok",
                "api_profiles_non_empty",
                "api_ranking_override_endpoint_ok",
                "api_ranking_override_results_non_empty",
                "api_ranking_override_filters_echoed",
                "api_search_endpoint_ok",
                "api_search_results_non_empty",
                "api_search_rows_have_documents",
                "api_topic_clusters_endpoint_ok",
                "api_topic_clusters_results_non_empty",
                "api_topic_clusters_cluster_id_present",
                "api_topic_clusters_label_candidates_present",
                "api_topic_map_endpoint_ok",
                "api_topic_map_results_non_empty",
                "api_topic_map_projection_build_id_present",
                "api_topic_map_algorithm_present",
                "api_topic_map_points_have_xy",
                "api_topic_map_default_centroids_only",
                "api_topic_clusters_sorted_endpoint_ok",
                "api_topic_clusters_sorted_results_non_empty",
                "api_topic_clusters_sorted_cluster_id_present",
                "api_topic_clusters_supported_sort_values_ok",
                "api_topic_cluster_detail_endpoint_ok",
                "api_topic_cluster_detail_papers_non_empty",
                "api_topic_cluster_detail_label_candidates_present",
                "api_topic_cluster_detail_supported_sort_values_ok",
                "api_topic_cluster_detail_filter_endpoint_ok",
                "api_topic_cluster_detail_filter_results_non_empty",
                "api_topic_cluster_detail_filter_filters_echoed",
                "api_topic_cluster_detail_filter_counts_valid",
                "api_topic_cluster_detail_filter_rows_match",
                "api_topic_cluster_detail_sort_results_non_empty",
                "api_topic_cluster_detail_sort_values_echoed",
                "api_paper_topic_cluster_endpoint_ok",
                "api_paper_topic_cluster_assignment_present",
                "api_paper_topic_cluster_cluster_present",
                "api_artifacts_endpoint_ok",
                "api_artifacts_results_non_empty",
                "api_artifacts_total_present",
                "api_artifacts_sort_echoed",
                "api_artifact_detail_endpoint_ok",
                "api_artifact_detail_found",
                "api_artifact_linked_papers_endpoint_ok",
                "api_artifact_linked_papers_results_non_empty",
                "api_artifact_linked_papers_counts_valid",
                "api_artifact_linked_papers_rows_match",
            ]
        )

    required_failed_checks = [
        name for name in required_checks if checks.get(name) is not True
    ]

    return {
        "generated_at_utc": utc_now_iso(),
        "ok": len(required_failed_checks) == 0,
        "required_failed_count": len(required_failed_checks),
        "required_failed_checks": required_failed_checks,
        "strict_required_checks": required_checks,
        "checks": checks,
        "extracted_values": extracted_values,
        "errors": errors,
    }


def print_report_summary(report: dict[str, Any]) -> None:
    checks = report.get("checks") or {}
    extracted = report.get("extracted_values") or {}

    for key, value in checks.items():
        prefix = "OK" if value is True else "FAIL"
        print(f"[{prefix}] {key}={value}")

    print(f"[OK] app_path={extracted.get('app_path')}")
    print(f"[OK] check_api={extracted.get('check_api')}")
    print(f"[{'OK' if report.get('ok') else 'FAIL'}] ok={report.get('ok')}")
    print(f"[{'OK' if report.get('required_failed_count') == 0 else 'FAIL'}] required_failed_count={report.get('required_failed_count')}")
    print(f"[{'OK' if report.get('required_failed_count') == 0 else 'FAIL'}] required_failed_checks={report.get('required_failed_checks')}")
    print(f"[OK] latest JSON: {LATEST_JSON_PATH.as_posix()}")
    print(f"[OK] latest Markdown: {LATEST_MD_PATH.as_posix()}")

    history_json = extracted.get("history_json_path")
    history_md = extracted.get("history_md_path")
    if history_json:
        print(f"[OK] history JSON: {history_json}")
    if history_md:
        print(f"[OK] history Markdown: {history_md}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Streamlit Discovery UI wiring and optional API smoke checks."
    )
    parser.add_argument(
        "--app-path",
        default=str(DEFAULT_APP_PATH),
        help="Path to Streamlit app file.",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="FastAPI base URL for --check-api mode.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout for --check-api requests.",
    )
    parser.add_argument(
        "--check-api",
        action="store_true",
        help="Also call live FastAPI endpoints.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status if required checks fail.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    app_path = Path(args.app_path)

    report = build_report(
        app_path=app_path,
        check_api=bool(args.check_api),
        api_base_url=str(args.api_base_url),
        timeout_seconds=int(args.timeout_seconds),
    )

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    stamp = utc_stamp()
    history_json_path = HISTORY_DIR / f"streamlit_discovery_ui_quality_{stamp}.json"
    history_md_path = HISTORY_DIR / f"streamlit_discovery_ui_quality_{stamp}.md"

    report["extracted_values"]["history_json_path"] = history_json_path.as_posix()
    report["extracted_values"]["history_md_path"] = history_md_path.as_posix()

    write_json(LATEST_JSON_PATH, report)
    write_markdown(LATEST_MD_PATH, report)
    write_json(history_json_path, report)
    write_markdown(history_md_path, report)

    print_report_summary(report)

    if args.strict and not report.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()