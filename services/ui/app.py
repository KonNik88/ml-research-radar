from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

DEFAULT_API_BASE_URL = os.getenv("ML_RADAR_API_BASE_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT_SECONDS = 30
API_STATUS_CACHE_TTL_SECONDS = 30
API_DATA_CACHE_TTL_SECONDS = 10
API_POST_CACHE_TTL_SECONDS = 5
API_PROFILES_CACHE_TTL_SECONDS = 30
MAX_TOP_K = 100

TRISTATE_OPTIONS = ["Profile default", "True", "False"]
BOOL_FILTER_KEYS = [
    "has_code",
    "has_dataset",
    "has_model",
    "has_demo",
    "has_github",
    "has_hf",
    "has_acl",
    "has_doi",
]
BOOL_FILTER_LABELS = {
    "has_code": "Code artifact",
    "has_dataset": "Dataset artifact",
    "has_model": "Model artifact",
    "has_demo": "Demo artifact",
    "has_github": "GitHub found",
    "has_hf": "Hugging Face",
    "has_acl": "ACL source",
    "has_doi": "DOI present",
}
SORT_OPTIONS = [
    "Profile default",
    "radar_score",
    "implementation_readiness_score",
    "source_confidence_score",
    "citation_signal_score",
    "recency_score",
    "year",
    "github_stars_max",
    "github_stars_sum",
    "github_forks_max",
    "github_forks_sum",
    "trusted_artifact_links_count",
    "trusted_code_links_count",
    "trusted_dataset_links_count",
    "trusted_model_links_count",
    "trusted_demo_links_count",
    "hf_downloads_max",
    "hf_likes_max",
]
DIRECTION_OPTIONS = ["Profile default", "Descending", "Ascending"]
SIMILAR_RANK_BY_OPTIONS = ["semantic", "radar_adjusted"]
ARTIFACT_PROVIDER_OPTIONS = [
    "",
    "github",
    "huggingface",
    "zenodo",
    "figshare",
    "kaggle",
    "youtube",
]

ARTIFACT_RELATION_TYPE_OPTIONS = [
    "",
    "code",
    "dataset",
    "model",
    "demo",
    "project",
    "artifact",
]

ARTIFACT_SORT_OPTIONS = [
    "linked_papers_desc",
    "provider_asc",
    "type_asc",
    "owner_asc",
    "last_seen_desc",
    "stars_desc",
    "forks_desc",
    "pushed_desc",
    "updated_desc",
]

ARTIFACT_GITHUB_STATUS_OPTIONS = [
    "",
    "found",
    "not_found",
    "forbidden",
    "rate_limited",
    "error",
    "skipped_invalid_external_id",
]

ARTIFACT_LINKED_PAPERS_SORT_OPTIONS = [
    "confidence_desc",
    "year_desc",
    "title_asc",
]

SEARCH_MODE_OPTIONS = [
    "lexical",
    "dense",
    "hybrid",
]

SEARCH_SORT_OPTIONS = [
    "relevance",
    "year_desc",
    "year_asc",
]

st.set_page_config(
    page_title="ML Research Radar",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------------------------------------------
# API helpers
# --------------------------------------------------------------------------------------


def _clean_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def _handle_response(response: requests.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    is_json = "application/json" in content_type.lower()

    if is_json:
        payload = response.json()
    else:
        payload = {"message": response.text}

    if response.ok:
        return payload

    error_code = payload.get("error_code", f"http_{response.status_code}")
    message = payload.get("message", "Request failed")
    details = payload.get("details")
    detail_text = f"\n\nDetails: {details}" if details else ""
    raise RuntimeError(f"{error_code}: {message}{detail_text}")


@st.cache_data(ttl=API_DATA_CACHE_TTL_SECONDS, show_spinner=False)
def api_get(base_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{_clean_base_url(base_url)}{path}"
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    return _handle_response(response)


@st.cache_data(ttl=API_POST_CACHE_TTL_SECONDS, show_spinner=False)
def api_post(base_url: str, path: str) -> dict[str, Any]:
    url = f"{_clean_base_url(base_url)}{path}"
    response = requests.post(url, timeout=REQUEST_TIMEOUT_SECONDS)
    return _handle_response(response)


@st.cache_data(ttl=API_STATUS_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_health(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/health")


@st.cache_data(ttl=API_STATUS_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_info(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/info")


@st.cache_data(ttl=API_STATUS_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_runtime(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/runtime")


@st.cache_data(ttl=API_STATUS_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_citation_graph_status(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/citation-graph/status")


def fetch_citation_graph_paper_references(
    base_url: str,
    canonical_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return api_get(
        base_url,
        f"/citation-graph/papers/{canonical_id}/references",
        params=params,
    )


def fetch_citation_graph_paper_citations(
    base_url: str,
    canonical_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return api_get(
        base_url,
        f"/citation-graph/papers/{canonical_id}/citations",
        params=params,
    )


def fetch_citation_graph_source_families(
    base_url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return api_get(base_url, "/citation-graph/source-families", params=params)


def fetch_citation_graph_top_referenced_papers(
    base_url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return api_get(base_url, "/citation-graph/top-referenced-papers", params=params)


def fetch_citation_graph_top_external_references(
    base_url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return api_get(base_url, "/citation-graph/top-external-references", params=params)


def fetch_search(base_url: str, params: dict[str, Any]) -> dict[str, Any]:
    return api_get(base_url, "/search", params=params)


def fetch_qdrant_experimental_search(
    base_url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return api_get(base_url, "/experimental/search/qdrant", params=params)

@st.cache_data(ttl=30, show_spinner=False)
def fetch_profiles(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/discovery/profiles")


def fetch_ranking(base_url: str, profile_name: str, params: dict[str, Any]) -> dict[str, Any]:
    return api_get(base_url, f"/discovery/ranking/{profile_name}", params=params)


def fetch_paper_detail(base_url: str, canonical_id: str) -> dict[str, Any]:
    return api_get(base_url, f"/discovery/papers/{canonical_id}")


def fetch_similar_papers(
    base_url: str,
    canonical_id: str,
    *,
    top_k: int,
    rank_by: str,
) -> dict[str, Any]:
    return api_get(
        base_url,
        f"/discovery/papers/{canonical_id}/similar",
        params={"top_k": top_k, "rank_by": rank_by},
    )

def fetch_topic_clusters(base_url: str, params: dict[str, Any]) -> dict[str, Any]:
    return api_get(base_url, "/discovery/clusters", params=params)

def fetch_topic_cluster_map(base_url: str, params: dict[str, Any]) -> dict[str, Any]:
    return api_get(base_url, "/discovery/clusters/map", params=params)

def fetch_topic_cluster_detail(
    base_url: str,
    cluster_id: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    return api_get(
        base_url,
        f"/discovery/clusters/{cluster_id}",
        params=params,
    )

def fetch_artifacts(base_url: str, params: dict[str, Any]) -> dict[str, Any]:
    return api_get(base_url, "/artifacts", params=params)

def fetch_artifact_detail(base_url: str, artifact_id: str) -> dict[str, Any]:
    return api_get(base_url, f"/artifacts/{artifact_id}")

def fetch_artifact_linked_papers(
    base_url: str,
    artifact_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return api_get(base_url, f"/artifacts/{artifact_id}/papers", params=params)

def fetch_paper_topic_cluster(base_url: str, canonical_id: str) -> dict[str, Any]:
    return api_get(base_url, f"/discovery/papers/{canonical_id}/cluster")

def clear_api_caches() -> None:
    api_get.clear()
    api_post.clear()
    fetch_health.clear()
    fetch_info.clear()
    fetch_runtime.clear()
    fetch_citation_graph_status.clear()
    fetch_profiles.clear()


def trigger_reload(base_url: str) -> dict[str, Any]:
    clear_api_caches()
    return api_post(base_url, "/reload")


# --------------------------------------------------------------------------------------
# General helpers
# --------------------------------------------------------------------------------------


def safe_get(mapping: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    return mapping.get(key, default)


def non_empty(value: Any) -> bool:
    return value not in (None, "", [], {})


def dash(value: Any) -> Any:
    return value if non_empty(value) else "—"


def compact_id(value: str | None, *, n: int = 8) -> str:
    if not value:
        return "—"
    if len(value) <= n * 2 + 1:
        return value
    return f"{value[:n]}…{value[-n:]}"


def fmt_score(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def to_int_or_none(value: str) -> int | None:
    stripped = value.strip()
    if not stripped:
        return None
    return int(stripped)

def float_or_none(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    return float(stripped)

def render_kv(label: str, value: Any) -> None:
    st.markdown(f"**{label}:** {dash(value)}")


def render_badges(flags: dict[str, Any]) -> None:
    badges: list[str] = []
    if flags.get("has_code_artifact") or flags.get("has_code"):
        badges.append("✅ code")
    if flags.get("has_dataset_artifact") or flags.get("has_dataset"):
        badges.append("🗂 dataset")
    if flags.get("has_model_artifact") or flags.get("has_model"):
        badges.append("🤖 model")
    if flags.get("has_demo_artifact") or flags.get("has_demo"):
        badges.append("🧪 demo")
    if flags.get("github_found_repo") or flags.get("has_github"):
        badges.append("GitHub")
    if flags.get("huggingface_found") or flags.get("has_hf"):
        badges.append("HF")
    if flags.get("has_acl"):
        badges.append("ACL")
    if flags.get("has_doi"):
        badges.append("DOI")

    if badges:
        st.caption(" · ".join(f"`{badge}`" for badge in badges))
    else:
        st.caption("No prominent artifact/source badges")


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if non_empty(value):
            return value
    return None


def normalize_authors(value: Any, *, limit: int = 8) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        names: list[str] = []
        for item in value[:limit]:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                names.append(str(item.get("name") or item.get("display_name") or item))
            else:
                names.append(str(item))
        suffix = " …" if len(value) > limit else ""
        return ", ".join(names) + suffix if names else "—"
    return str(value)


def summarize_sources(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value[:8]) or "—"
    if isinstance(value, dict):
        return ", ".join(str(k) for k, v in value.items() if v) or "—"
    return str(value) if value else "—"


def maybe_markdown_link(label: str, url: Any) -> str:
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return "—"
    return f"[{label}]({url})"


# --------------------------------------------------------------------------------------
# Session state / controls
# --------------------------------------------------------------------------------------


def init_ui_state() -> None:
    defaults = {
        "api_base_url": DEFAULT_API_BASE_URL,
        "profile_name": None,
        "top_k": 10,
        "query_title": "",
        "source_family": "",
        "min_year": "",
        "max_year": "",
        "sort_by": "Profile default",
        "descending": "Profile default",
        "similar_top_k": 10,
        "similar_rank_by": "semantic",
        "search_query": "",
        "search_mode": "lexical",
        "search_top_k": 10,
        "search_rank": False,
        "search_year_from": "",
        "search_year_to": "",
        "search_category": "",
        "search_source": "",
        "search_publication_type": "",
        "search_venue": "",
        "search_open_access": "Profile default",
        "search_has_code_link": "Profile default",
        "search_offset": 0,
        "search_sort_by": "relevance",
        "search_payload": None,
        "qdrant_search_query": "",
        "qdrant_search_top_k": 10,
        "qdrant_search_payload": None,
        "ranking_payload": None,
        "selected_canonical_id": None,
        "selected_paper_canonical_id": None,
        "selected_paper_detail_payload": None,
        "selected_paper_similar_payload": None,
        "selected_paper_cluster_payload": None,
        "selected_paper_similar_top_k": 10,
        "selected_paper_similar_rank_by": "semantic",
        "selected_paper_selected_artifact_id": None,
        "selected_paper_artifact_detail_payload": None,
        "selected_paper_artifact_linked_papers_payload": None,
        "selected_paper_artifact_linked_papers_limit": 20,
        "selected_paper_artifact_linked_papers_offset": 0,
        "selected_paper_artifact_linked_papers_relation_type": "",
        "selected_paper_artifact_linked_papers_min_confidence": "",
        "selected_paper_artifact_linked_papers_sort_by": "confidence_desc",
        "selected_paper_citation_references_payload": None,
        "selected_paper_citation_citations_payload": None,
        "selected_paper_citation_graph_limit": 20,
        "selected_paper_citation_graph_offset": 0,
        "cluster_limit": 10,
        "cluster_min_size": 1,
        "cluster_sort_by": "size_desc",
        "cluster_payload": None,
        "selected_cluster_id": None,
        "cluster_detail_top_k": 10,
        "cluster_detail_sort_by": "rank",
        "cluster_detail_min_year": "",
        "cluster_detail_max_year": "",
        "cluster_detail_has_code": "Profile default",
        "cluster_detail_has_dataset": "Profile default",
        "cluster_detail_has_model": "Profile default",
        "cluster_detail_has_demo": "Profile default",
        "cluster_detail_has_github": "Profile default",
        "cluster_detail_has_hf": "Profile default",
        "cluster_detail_has_acl": "Profile default",
        "cluster_detail_has_doi": "Profile default",
        "cluster_detail_min_radar_score": "",
        "cluster_detail_min_implementation_readiness_score": "",
        "cluster_detail_min_citation_signal_score": "",
        "topic_map_payload": None,
        "topic_map_include_papers": False,
        "topic_map_max_points": 2000,
        "topic_map_selected_cluster_id": None,
        "topic_map_cluster_detail_sort_by": "rank",
        "artifact_payload": None,
        "artifact_limit": 20,
        "artifact_offset": 0,
        "artifact_provider": "",
        "artifact_type": "",
        "artifact_relation_type": "",
        "artifact_owner": "",
        "artifact_min_confidence": "",
        "artifact_has_paper_links": "Profile default",
        "artifact_min_stars": "",
        "artifact_max_stars": "",
        "artifact_language": "",
        "artifact_license": "",
        "artifact_archived": "Profile default",
        "artifact_github_status": "",
        "artifact_has_github_metadata": "Profile default",
        "artifact_pushed_after": "",
        "artifact_pushed_before": "",
        "artifact_updated_after": "",
        "artifact_updated_before": "",
        "artifact_sort_by": "linked_papers_desc",
        "selected_artifact_id": None,
        "artifact_detail_payload": None,
        "artifact_linked_papers_payload": None,
        "citation_graph_status_payload": None,
        "citation_graph_source_families_payload": None,
        "citation_graph_top_referenced_papers_payload": None,
        "citation_graph_top_external_references_payload": None,
        "citation_graph_diagnostics_limit": 20,
        "citation_graph_diagnostics_offset": 0,
        "artifact_linked_papers_limit": 20,
        "artifact_linked_papers_offset": 0,
        "artifact_linked_papers_relation_type": "",
        "artifact_linked_papers_min_confidence": "",
        "artifact_linked_papers_sort_by": "confidence_desc",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    for key in BOOL_FILTER_KEYS:
        st.session_state.setdefault(key, "Profile default")
        if st.session_state.get("cluster_sort_by") not in CLUSTER_SORT_OPTIONS:
            st.session_state["cluster_sort_by"] = "size_desc"

    if st.session_state.get("cluster_detail_sort_by") not in CLUSTER_PAPER_SORT_OPTIONS:
        st.session_state["cluster_detail_sort_by"] = "rank"

    if st.session_state.get("topic_map_cluster_detail_sort_by") not in CLUSTER_PAPER_SORT_OPTIONS:
        st.session_state["topic_map_cluster_detail_sort_by"] = "rank"


def reset_discovery_filters(default_profile: str | None = None) -> None:
    st.session_state["top_k"] = 10
    st.session_state["query_title"] = ""
    st.session_state["source_family"] = ""
    st.session_state["min_year"] = ""
    st.session_state["max_year"] = ""
    st.session_state["sort_by"] = "Profile default"
    st.session_state["descending"] = "Profile default"
    st.session_state["similar_top_k"] = 10
    st.session_state["similar_rank_by"] = "semantic"
    for key in BOOL_FILTER_KEYS:
        st.session_state[key] = "Profile default"
    if default_profile:
        st.session_state["profile_name"] = default_profile
    st.session_state["ranking_payload"] = None
    st.session_state["selected_canonical_id"] = None

def reset_cluster_detail_filters() -> None:
    st.session_state["cluster_detail_min_year"] = ""
    st.session_state["cluster_detail_max_year"] = ""

    for key in CLUSTER_DETAIL_BOOL_FILTER_KEYS:
        st.session_state[f"cluster_detail_{key}"] = "Profile default"

    st.session_state["cluster_detail_min_radar_score"] = ""
    st.session_state["cluster_detail_min_implementation_readiness_score"] = ""
    st.session_state["cluster_detail_min_citation_signal_score"] = ""

def reset_selected_paper_artifact_navigation() -> None:
    st.session_state["selected_paper_artifact_detail_payload"] = None
    st.session_state["selected_paper_artifact_linked_papers_payload"] = None


def reset_selected_paper_citation_graph_payloads() -> None:
    st.session_state["selected_paper_citation_references_payload"] = None
    st.session_state["selected_paper_citation_citations_payload"] = None


def reset_selected_paper_payloads() -> None:
    st.session_state["selected_paper_detail_payload"] = None
    st.session_state["selected_paper_similar_payload"] = None
    st.session_state["selected_paper_cluster_payload"] = None
    reset_selected_paper_artifact_navigation()
    reset_selected_paper_citation_graph_payloads()

def select_paper(canonical_id: str | None) -> None:
    canonical_id = str(canonical_id or "").strip()
    if not canonical_id:
        return

    previous = st.session_state.get("selected_paper_canonical_id")
    st.session_state["selected_paper_canonical_id"] = canonical_id

    if previous != canonical_id:
        reset_selected_paper_payloads()

def select_paper_from_ui(canonical_id: str | None) -> bool:
    canonical_id = str(canonical_id or "").strip()
    if not canonical_id:
        return False

    select_paper(canonical_id)
    return True


def render_open_paper_workspace_button(
    canonical_id: str | None,
    *,
    label: str,
    key: str,
    rerun: bool = False,
) -> None:
    canonical_id = str(canonical_id or "").strip()
    if not canonical_id:
        return

    if st.button(label, key=key, width="stretch"):
        selected = select_paper_from_ui(canonical_id)
        if selected and rerun:
            st.rerun()
        if selected:
            st.success("Selected paper updated. Open the Paper workspace tab.")

def clear_selected_paper() -> None:
    st.session_state["selected_paper_canonical_id"] = None
    reset_selected_paper_payloads()

def build_ranking_params() -> dict[str, Any]:
    params: dict[str, Any] = {"top_k": int(st.session_state["top_k"])}

    query_title = st.session_state.get("query_title", "").strip()
    source_family = st.session_state.get("source_family", "").strip()
    min_year = to_int_or_none(st.session_state.get("min_year", ""))
    max_year = to_int_or_none(st.session_state.get("max_year", ""))

    if min_year is not None:
        params["min_year"] = min_year
    if max_year is not None:
        params["max_year"] = max_year
    if query_title:
        params["query_title"] = query_title
    if source_family:
        params["source_family"] = source_family

    for key in BOOL_FILTER_KEYS:
        selected = st.session_state.get(key, "Profile default")
        if selected == "True":
            params[key] = "true"
        elif selected == "False":
            params[key] = "false"

    sort_by = st.session_state.get("sort_by", "Profile default")
    if sort_by != "Profile default":
        params["sort_by"] = sort_by

    direction = st.session_state.get("descending", "Profile default")
    if direction == "Descending":
        params["descending"] = "true"
    elif direction == "Ascending":
        params["descending"] = "false"

    return params

def build_search_params() -> dict[str, Any]:
    query = st.session_state.get("search_query", "").strip()
    if not query:
        raise ValueError("Search query is empty.")

    params: dict[str, Any] = {
        "query": query,
        "mode": st.session_state["search_mode"],
        "top_k": int(st.session_state["search_top_k"]),
        "rank": "true" if st.session_state.get("search_rank") else "false",
        "offset": int(st.session_state["search_offset"]),
        "sort_by": st.session_state["search_sort_by"],
    }

    year_from = to_int_or_none(st.session_state.get("search_year_from", ""))
    year_to = to_int_or_none(st.session_state.get("search_year_to", ""))

    if year_from is not None:
        params["year_from"] = year_from
    if year_to is not None:
        params["year_to"] = year_to

    for state_key, param_key in [
        ("search_category", "category"),
        ("search_source", "source"),
        ("search_publication_type", "publication_type"),
        ("search_venue", "venue"),
    ]:
        value = st.session_state.get(state_key, "").strip()
        if value:
            params[param_key] = value

    open_access = st.session_state.get("search_open_access", "Profile default")
    if open_access == "True":
        params["open_access"] = "true"
    elif open_access == "False":
        params["open_access"] = "false"

    has_code_link = st.session_state.get("search_has_code_link", "Profile default")
    if has_code_link == "True":
        params["has_code_link"] = "true"
    elif has_code_link == "False":
        params["has_code_link"] = "false"

    return params

def build_qdrant_experimental_search_params() -> dict[str, Any]:
    query = st.session_state.get("qdrant_search_query", "").strip()
    if not query:
        raise ValueError("Experimental Qdrant search query is empty.")

    return {
        "query": query,
        "top_k": int(st.session_state["qdrant_search_top_k"]),
    }


def build_cluster_detail_params(*, top_k: int, sort_by: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "top_k": int(top_k),
        "sort_by": sort_by,
    }

    min_year = to_int_or_none(st.session_state.get("cluster_detail_min_year", ""))
    max_year = to_int_or_none(st.session_state.get("cluster_detail_max_year", ""))

    if min_year is not None:
        params["min_year"] = min_year
    if max_year is not None:
        params["max_year"] = max_year

    for key in CLUSTER_DETAIL_BOOL_FILTER_KEYS:
        selected = st.session_state.get(f"cluster_detail_{key}", "Profile default")
        if selected == "True":
            params[key] = "true"
        elif selected == "False":
            params[key] = "false"

    score_fields = {
        "cluster_detail_min_radar_score": "min_radar_score",
        "cluster_detail_min_implementation_readiness_score": (
            "min_implementation_readiness_score"
        ),
        "cluster_detail_min_citation_signal_score": "min_citation_signal_score",
    }

    for state_key, param_key in score_fields.items():
        value = float_or_none(st.session_state.get(state_key, ""))
        if value is not None:
            params[param_key] = value

    return params

def build_artifact_params() -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": int(st.session_state["artifact_limit"]),
        "offset": int(st.session_state["artifact_offset"]),
        "sort_by": st.session_state["artifact_sort_by"],
    }

    provider = st.session_state.get("artifact_provider", "").strip()
    artifact_type = st.session_state.get("artifact_type", "").strip()
    relation_type = st.session_state.get("artifact_relation_type", "").strip()
    owner = st.session_state.get("artifact_owner", "").strip()
    language = st.session_state.get("artifact_language", "").strip()
    license_name = st.session_state.get("artifact_license", "").strip()
    pushed_after = st.session_state.get("artifact_pushed_after", "").strip()
    pushed_before = st.session_state.get("artifact_pushed_before", "").strip()
    updated_after = st.session_state.get("artifact_updated_after", "").strip()
    updated_before = st.session_state.get("artifact_updated_before", "").strip()

    if provider:
        params["provider"] = provider
    if artifact_type:
        params["artifact_type"] = artifact_type
    if relation_type:
        params["relation_type"] = relation_type
    if owner:
        params["owner"] = owner
    if language:
        params["language"] = language
    if license_name:
        params["license"] = license_name

    min_confidence = float_or_none(st.session_state.get("artifact_min_confidence", ""))
    if min_confidence is not None:
        params["min_confidence"] = min_confidence

    min_stars = to_int_or_none(st.session_state.get("artifact_min_stars", ""))
    max_stars = to_int_or_none(st.session_state.get("artifact_max_stars", ""))
    if min_stars is not None:
        params["min_stars"] = min_stars
    if max_stars is not None:
        params["max_stars"] = max_stars

    has_paper_links = st.session_state.get("artifact_has_paper_links", "Profile default")
    if has_paper_links == "True":
        params["has_paper_links"] = "true"
    elif has_paper_links == "False":
        params["has_paper_links"] = "false"

    archived = st.session_state.get("artifact_archived", "Profile default")
    if archived == "True":
        params["archived"] = "true"
    elif archived == "False":
        params["archived"] = "false"

    has_github_metadata = st.session_state.get(
        "artifact_has_github_metadata",
        "Profile default",
    )
    if has_github_metadata == "True":
        params["has_github_metadata"] = "true"
    elif has_github_metadata == "False":
        params["has_github_metadata"] = "false"

    github_status = st.session_state.get("artifact_github_status", "").strip()
    if github_status:
        params["github_status"] = github_status
    if pushed_after:
        params["pushed_after"] = pushed_after
    if pushed_before:
        params["pushed_before"] = pushed_before
    if updated_after:
        params["updated_after"] = updated_after
    if updated_before:
        params["updated_before"] = updated_before

    return params

def build_artifact_linked_papers_params() -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": int(st.session_state["artifact_linked_papers_limit"]),
        "offset": int(st.session_state["artifact_linked_papers_offset"]),
        "sort_by": st.session_state["artifact_linked_papers_sort_by"],
    }

    relation_type = st.session_state.get(
        "artifact_linked_papers_relation_type",
        "",
    ).strip()
    if relation_type:
        params["relation_type"] = relation_type

    min_confidence = float_or_none(
        st.session_state.get("artifact_linked_papers_min_confidence", "")
    )
    if min_confidence is not None:
        params["min_confidence"] = min_confidence

    return params

def build_selected_paper_artifact_linked_papers_params() -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": int(st.session_state["selected_paper_artifact_linked_papers_limit"]),
        "offset": int(st.session_state["selected_paper_artifact_linked_papers_offset"]),
        "sort_by": st.session_state["selected_paper_artifact_linked_papers_sort_by"],
    }

    relation_type = st.session_state.get(
        "selected_paper_artifact_linked_papers_relation_type",
        "",
    ).strip()
    if relation_type:
        params["relation_type"] = relation_type

    min_confidence = float_or_none(
        st.session_state.get("selected_paper_artifact_linked_papers_min_confidence", "")
    )
    if min_confidence is not None:
        params["min_confidence"] = min_confidence

    return params

def artifact_row_to_table(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    github = metadata.get("github") if isinstance(metadata, dict) else {}
    if not isinstance(github, dict):
        github = {}

    return {
        "provider": row.get("provider"),
        "type": row.get("artifact_type") or row.get("type"),
        "owner": row.get("owner"),
        "name": row.get("name") or row.get("title"),
        "linked_papers": row.get("linked_papers_count"),
        "confidence": row.get("confidence"),
        "stars": row.get("github_stars") or github.get("stargazers_count"),
        "forks": row.get("github_forks") or github.get("forks_count"),
        "language": row.get("language") or github.get("language"),
        "license": row.get("license") or github.get("license"),
        "archived": row.get("archived") or github.get("archived"),
        "status": row.get("github_status") or github.get("status"),
        "url": row.get("url") or row.get("normalized_url") or row.get("external_url"),
        "artifact_id": row.get("artifact_id"),
    }

def artifact_linked_paper_row_to_table(row: dict[str, Any]) -> dict[str, Any]:
    paper = row.get("paper") or {}
    if not isinstance(paper, dict):
        paper = {}

    return {
        "year": paper.get("year"),
        "title": paper.get("title"),
        "relation": row.get("relation_type"),
        "confidence": row.get("confidence"),
        "canonical_id": row.get("canonical_id"),
        "source": row.get("evidence_source"),
        "source_field": row.get("source_field"),
        "doi": paper.get("doi"),
        "arxiv_id": paper.get("arxiv_id"),
        "venue": paper.get("venue"),
    }

def render_artifact_card(row: dict[str, Any], rank: int) -> None:
    metadata = row.get("metadata") or {}
    github = metadata.get("github") if isinstance(metadata, dict) else {}
    if not isinstance(github, dict):
        github = {}

    title = (
        row.get("name")
        or row.get("title")
        or row.get("normalized_url")
        or row.get("url")
        or "Untitled artifact"
    )

    url = row.get("url") or row.get("normalized_url") or row.get("external_url")

    with st.container(border=True):
        st.markdown(f"### {rank}. {title}")

        cols = st.columns(6)
        cols[0].metric("Provider", dash(row.get("provider")))
        cols[1].metric("Type", dash(row.get("artifact_type") or row.get("type")))
        cols[2].metric("Linked papers", dash(row.get("linked_papers_count")))
        cols[3].metric("Stars", dash(row.get("github_stars") or github.get("stargazers_count")))
        cols[4].metric("Forks", dash(row.get("github_forks") or github.get("forks_count")))
        cols[5].metric("Language", dash(row.get("language") or github.get("language")))

        render_kv("Owner", row.get("owner"))
        render_kv("License", row.get("license") or github.get("license"))
        render_kv("GitHub status", row.get("github_status") or github.get("status"))
        render_kv("Artifact ID", row.get("artifact_id"))

        if url:
            st.markdown(maybe_markdown_link("Open artifact", url))

        with st.expander("Artifact row JSON", expanded=False):
            st.json(row)

def render_artifact_detail_panel(payload: dict[str, Any]) -> None:
    artifact = payload.get("artifact") or {}
    if not isinstance(artifact, dict):
        st.warning("Artifact detail payload does not contain an artifact object.")
        with st.expander("Raw artifact detail response", expanded=False):
            st.json(payload)
        return

    metadata = artifact.get("metadata") or {}
    github = metadata.get("github") if isinstance(metadata, dict) else {}
    if not isinstance(github, dict):
        github = {}

    title = (
        artifact.get("name")
        or artifact.get("title")
        or artifact.get("normalized_url")
        or artifact.get("canonical_url")
        or artifact.get("artifact_id")
        or "Untitled artifact"
    )

    st.markdown(f"### Artifact detail: {title}")

    cols = st.columns(6)
    cols[0].metric("Provider", dash(artifact.get("provider")))
    cols[1].metric("Type", dash(artifact.get("artifact_type")))
    cols[2].metric("Linked papers", dash(artifact.get("linked_papers_count")))
    cols[3].metric("Stars", dash(artifact.get("stars") or github.get("stargazers_count")))
    cols[4].metric("Forks", dash(artifact.get("forks") or github.get("forks_count")))
    cols[5].metric("Language", dash(github.get("language")))

    render_kv("Artifact ID", artifact.get("artifact_id"))
    render_kv("Owner", artifact.get("owner"))
    render_kv("License", artifact.get("license"))
    render_kv("GitHub status", github.get("status"))
    render_kv("Relation types", ", ".join(artifact.get("relation_types") or []))

    url = artifact.get("canonical_url") or artifact.get("normalized_url")
    if url:
        st.markdown(maybe_markdown_link("Open artifact", url))

    description = artifact.get("description")
    if description:
        with st.expander("Artifact description", expanded=False):
            st.write(description)

    with st.expander("Artifact detail JSON", expanded=False):
        st.json(payload)

def render_artifact_linked_papers(payload: dict[str, Any]) -> None:
    rows = payload.get("results") or []

    st.markdown("### Linked papers")

    cols = st.columns(4)
    cols[0].metric("Total linked papers", payload.get("total", "—"))
    cols[1].metric("Returned", len(rows))
    cols[2].metric("Offset", payload.get("offset", "—"))
    cols[3].metric("Sort", payload.get("sort_by", "—"))

    if not rows:
        st.warning("No linked papers matched the current filters.")
        with st.expander("Raw linked papers response", expanded=False):
            st.json(payload)
        return

    st.dataframe(
        pd.DataFrame([artifact_linked_paper_row_to_table(row) for row in rows]),
        hide_index=True,
        width="stretch",
    )

    for idx, row in enumerate(rows, start=1):
        paper = row.get("paper") or {}
        if not isinstance(paper, dict):
            paper = {}

        with st.container(border=True):
            st.markdown(f"### {idx}. {paper.get('title', 'Untitled paper')}")
            cols = st.columns(5)
            cols[0].metric("Year", dash(paper.get("year")))
            cols[1].metric("Relation", dash(row.get("relation_type")))
            cols[2].metric("Confidence", fmt_score(row.get("confidence")))
            cols[3].metric("Source count", dash(paper.get("source_count")))
            cols[4].metric("Citations", dash(paper.get("cited_by_count")))

            render_kv("Canonical ID", row.get("canonical_id"))
            render_kv("Evidence source", row.get("evidence_source"))
            render_kv("Evidence field", row.get("source_field"))

            canonical_id = str(row.get("canonical_id") or "").strip()
            render_open_paper_workspace_button(
                canonical_id,
                label="Open this paper in Paper workspace",
                key=f"open_artifact_linked_paper_workspace_{canonical_id}_{idx}",
                rerun=True,
            )

            evidence_url = row.get("evidence_url")
            if evidence_url:
                st.markdown(maybe_markdown_link("Open evidence", evidence_url))

            abstract = paper.get("abstract")
            if abstract:
                preview = abstract if len(abstract) <= 500 else abstract[:500].rstrip() + "…"
                st.write(preview)

            with st.expander("Linked paper row JSON", expanded=False):
                st.json(row)

    with st.expander("Raw linked papers response", expanded=False):
        st.json(payload)

def render_artifact_explorer(base_url: str) -> None:
    st.subheader("Artifact explorer")
    st.caption(
        "Browse materialized artifact evidence: GitHub repositories, Hugging Face assets, "
        "datasets, models, demos and other linked implementation resources."
    )

    control_cols = st.columns([1, 1, 1, 1])
    with control_cols[0]:
        st.number_input(
            "Artifact limit",
            min_value=1,
            max_value=100,
            step=1,
            key="artifact_limit",
        )
    with control_cols[1]:
        st.number_input(
            "Artifact offset",
            min_value=0,
            max_value=1_000_000,
            step=20,
            key="artifact_offset",
        )
    with control_cols[2]:
        st.selectbox(
            "Artifact provider",
            ARTIFACT_PROVIDER_OPTIONS,
            key="artifact_provider",
            format_func=lambda value: value or "Any provider",
        )
    with control_cols[3]:
        st.selectbox(
            "Artifact sort by",
            ARTIFACT_SORT_OPTIONS,
            key="artifact_sort_by",
        )

    filter_cols = st.columns([1, 1, 1, 1])
    with filter_cols[0]:
        st.text_input(
            "Artifact type",
            key="artifact_type",
            placeholder="github_repository",
        )
    with filter_cols[1]:
        st.selectbox(
            "Relation type",
            ARTIFACT_RELATION_TYPE_OPTIONS,
            key="artifact_relation_type",
            format_func=lambda value: value or "Any relation",
        )
    with filter_cols[2]:
        st.text_input("Owner", key="artifact_owner", placeholder="facebookresearch")
    with filter_cols[3]:
        st.text_input("Min confidence", key="artifact_min_confidence", placeholder="0.7")

    github_cols = st.columns([1, 1, 1, 1])
    with github_cols[0]:
        st.text_input("Min stars", key="artifact_min_stars", placeholder="100")
    with github_cols[1]:
        st.text_input("Max stars", key="artifact_max_stars", placeholder="")
    with github_cols[2]:
        st.text_input("Language", key="artifact_language", placeholder="Python")
    with github_cols[3]:
        st.text_input("License", key="artifact_license", placeholder="mit")

    state_cols = st.columns([1, 1, 1])
    with state_cols[0]:
        st.selectbox(
            "Has paper links",
            TRISTATE_OPTIONS,
            key="artifact_has_paper_links",
        )
    with state_cols[1]:
        st.selectbox(
            "Archived",
            TRISTATE_OPTIONS,
            key="artifact_archived",
        )
    with state_cols[2]:
        st.selectbox(
            "Has GitHub metadata",
            TRISTATE_OPTIONS,
            key="artifact_has_github_metadata",
        )

    st.selectbox(
        "GitHub status",
        ARTIFACT_GITHUB_STATUS_OPTIONS,
        key="artifact_github_status",
        format_func=lambda value: value or "Any status",
    )

    date_cols = st.columns([1, 1, 1, 1])
    with date_cols[0]:
        st.text_input(
            "Pushed after",
            key="artifact_pushed_after",
            placeholder="2024-01-01T00:00:00Z",
        )
    with date_cols[1]:
        st.text_input(
            "Pushed before",
            key="artifact_pushed_before",
            placeholder="2026-01-01T00:00:00Z",
        )
    with date_cols[2]:
        st.text_input(
            "Updated after",
            key="artifact_updated_after",
            placeholder="2024-01-01T00:00:00Z",
        )
    with date_cols[3]:
        st.text_input(
            "Updated before",
            key="artifact_updated_before",
            placeholder="2026-01-01T00:00:00Z",
        )

    st.caption(
        "GitHub date filters are passed through to Artifact API. "
        "Recommended format: ISO-8601, e.g. 2024-01-01T00:00:00Z."
    )

    if st.button("Load artifacts", type="primary", width="stretch"):
        try:
            params = build_artifact_params()
            with st.spinner("Loading artifacts..."):
                payload = fetch_artifacts(base_url, params)
            st.session_state["artifact_payload"] = payload

            rows = payload.get("results") or []
            if rows and isinstance(rows[0], dict):
                st.session_state["selected_artifact_id"] = rows[0].get("artifact_id")

            st.session_state["artifact_detail_payload"] = None
            st.session_state["artifact_linked_papers_payload"] = None
        except ValueError:
            st.error(
                "Artifact numeric filters must be valid numbers. "
                "min_confidence should be 0.0–1.0, stars should be integers."
            )
            return
        except Exception as exc:
            st.error(str(exc))
            st.info(
                "Artifact explorer requires API started with DB backend and Postgres available: "
                "`set ML_RADAR_SEARCH_BACKEND=db`."
            )
            return

    payload = st.session_state.get("artifact_payload")
    if not payload:
        st.info(
            "Start the API with DB backend, choose artifact filters, and click **Load artifacts**."
        )
        return

    rows = payload.get("results") or []

    cols = st.columns(4)
    cols[0].metric("Total artifacts", payload.get("total", "—"))
    cols[1].metric("Returned", len(rows))
    cols[2].metric("Offset", payload.get("offset", "—"))
    cols[3].metric("Sort", payload.get("sort_by", "—"))

    with st.expander("Artifact request response metadata", expanded=False):
        st.json({key: value for key, value in payload.items() if key != "results"})

    if not rows:
        st.warning("No artifacts matched the current filter combination.")
        return

    st.markdown("#### Artifact table")
    st.dataframe(
        pd.DataFrame([artifact_row_to_table(row) for row in rows]),
        hide_index=True,
        width="stretch",
    )

    st.markdown("#### Artifact detail and linked papers")

    artifact_ids = [
        str(row.get("artifact_id"))
        for row in rows
        if isinstance(row, dict) and row.get("artifact_id")
    ]

    artifact_labels = {
        str(row.get("artifact_id")): (
            f"{row.get('provider', '—')} · "
            f"{row.get('owner') or '—'} / {row.get('name') or row.get('title') or row.get('normalized_url') or '—'} · "
            f"papers={row.get('linked_papers_count', '—')}"
        )
        for row in rows
        if isinstance(row, dict) and row.get("artifact_id")
    }

    if artifact_ids:
        if st.session_state.get("selected_artifact_id") not in artifact_ids:
            st.session_state["selected_artifact_id"] = artifact_ids[0]

        selected_artifact_id = st.selectbox(
            "Open artifact detail",
            artifact_ids,
            key="selected_artifact_id",
            format_func=lambda artifact_id: artifact_labels.get(
                artifact_id,
                artifact_id,
            ),
        )

        linked_control_cols = st.columns([1, 1, 1, 1])
        with linked_control_cols[0]:
            st.number_input(
                "Linked papers limit",
                min_value=1,
                max_value=100,
                step=1,
                key="artifact_linked_papers_limit",
            )
        with linked_control_cols[1]:
            st.number_input(
                "Linked papers offset",
                min_value=0,
                max_value=1_000_000,
                step=20,
                key="artifact_linked_papers_offset",
            )
        with linked_control_cols[2]:
            st.selectbox(
                "Linked relation type",
                ARTIFACT_RELATION_TYPE_OPTIONS,
                key="artifact_linked_papers_relation_type",
                format_func=lambda value: value or "Any relation",
            )
        with linked_control_cols[3]:
            st.selectbox(
                "Linked papers sort by",
                ARTIFACT_LINKED_PAPERS_SORT_OPTIONS,
                key="artifact_linked_papers_sort_by",
            )

        st.text_input(
            "Linked papers min confidence",
            key="artifact_linked_papers_min_confidence",
            placeholder="0.7",
        )

        if st.button("Load artifact detail", type="secondary", width="stretch"):
            try:
                params = build_artifact_linked_papers_params()
                with st.spinner("Loading artifact detail and linked papers..."):
                    detail_payload = fetch_artifact_detail(
                        base_url,
                        selected_artifact_id,
                    )
                    linked_payload = fetch_artifact_linked_papers(
                        base_url,
                        selected_artifact_id,
                        params,
                    )

                st.session_state["artifact_detail_payload"] = detail_payload
                st.session_state["artifact_linked_papers_payload"] = linked_payload
            except ValueError:
                st.error(
                    "Linked paper filters must be numeric where applicable. "
                    "min_confidence should be 0.0–1.0."
                )
            except Exception as exc:
                st.error(str(exc))

        detail_payload = st.session_state.get("artifact_detail_payload")
        linked_payload = st.session_state.get("artifact_linked_papers_payload")

        if detail_payload:
            render_artifact_detail_panel(detail_payload)

        if linked_payload:
            render_artifact_linked_papers(linked_payload)

    st.markdown("#### Artifact cards")
    for idx, row in enumerate(rows, start=1):
        render_artifact_card(row, idx)

    with st.expander("Raw artifacts response", expanded=False):
        st.json(payload)

def get_profiles_or_stop(base_url: str) -> dict[str, Any]:
    try:
        return fetch_profiles(base_url)
    except Exception as exc:
        st.error(f"Failed to load discovery profiles: {exc}")
        st.stop()


# --------------------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------------------

def render_qdrant_runtime_status(runtime: dict[str, Any]) -> None:
    qdrant = runtime.get("qdrant")

    st.sidebar.markdown("### Qdrant runtime")

    if not isinstance(qdrant, dict):
        st.sidebar.info("Qdrant diagnostics are unavailable in the runtime snapshot.")
        return

    qdrant_ok = bool(qdrant.get("ok"))
    if qdrant_ok:
        st.sidebar.success("Qdrant: OK")
    else:
        st.sidebar.warning("Qdrant: unavailable")

    render_kv("Collection", qdrant.get("collection_name"))

    points_count = qdrant.get("points_count")
    expected_count = qdrant.get("expected_corpus_doc_count")
    points_text = f"{dash(points_count)} / {dash(expected_count)}"
    render_kv("Points", points_text)

    render_kv("Points match corpus", qdrant.get("points_match_corpus"))
    render_kv("Vector size", qdrant.get("vector_size"))
    render_kv("Distance", qdrant.get("distance"))

    error = qdrant.get("error")
    if error:
        with st.sidebar.expander("Qdrant diagnostic error", expanded=False):
            st.code(str(error))

    with st.sidebar.expander("Qdrant runtime details", expanded=False):
        render_kv("Host", qdrant.get("host"))
        render_kv("Port", qdrant.get("port"))
        render_kv("Timeout sec", qdrant.get("timeout_sec"))
        render_kv("Check compatibility", qdrant.get("check_compatibility"))
        render_kv("Collection exists", qdrant.get("collection_exists"))
        render_kv("Status", qdrant.get("status"))
        render_kv("Optimizer status", qdrant.get("optimizer_status"))


def render_citation_graph_status_panel(base_url: str) -> None:
    st.sidebar.markdown("### Citation graph status")
    st.sidebar.caption(
        "Local citation/reference graph status from `GET /citation-graph/status`. "
        "Read-only, compatibility-gated, and not publication-ready."
    )

    if st.sidebar.button(
        "Load citation graph status",
        key="load_citation_graph_status",
        width="stretch",
    ):
        try:
            with st.spinner("Loading citation graph status..."):
                st.session_state["citation_graph_status_payload"] = (
                    fetch_citation_graph_status(base_url)
                )
        except Exception as exc:
            st.session_state["citation_graph_status_payload"] = {"error": str(exc)}

    payload = st.session_state.get("citation_graph_status_payload")
    if not payload:
        st.sidebar.info("Citation graph status has not been loaded yet.")
        return

    if payload.get("error"):
        st.sidebar.warning("Citation graph status request failed.")
        with st.sidebar.expander("Citation graph status error", expanded=False):
            st.code(str(payload["error"]))
        return

    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    availability = (
        payload.get("availability")
        if isinstance(payload.get("availability"), dict)
        else {}
    )
    compatibility = (
        payload.get("compatibility")
        if isinstance(payload.get("compatibility"), dict)
        else {}
    )
    caveats = payload.get("caveats") if isinstance(payload.get("caveats"), list) else []

    runtime_enabled = availability.get("runtime_enabled", graph.get("runtime_enabled"))
    available = availability.get("available", graph.get("available"))
    safe_to_serve_locally = availability.get("safe_to_serve_locally")
    runtime_loader = availability.get("runtime_loader_implemented")

    status_cols = st.sidebar.columns(2)
    status_cols[0].metric("Runtime enabled", dash(runtime_enabled))
    status_cols[1].metric("Available", dash(available))
    status_cols[0].metric("Safe locally", dash(safe_to_serve_locally))
    status_cols[1].metric("Runtime loader", dash(runtime_loader))

    review_required = first_non_empty(
        graph.get("manual_review_required"),
        compatibility.get("manual_review_required"),
        availability.get("manual_review_required"),
    )
    publication_ready = first_non_empty(
        graph.get("publication_ready"),
        compatibility.get("publication_ready"),
        availability.get("publication_ready"),
    )

    with st.sidebar.expander("Citation graph status details", expanded=False):
        render_kv("Graph", graph.get("name"))
        render_kv("Version", graph.get("version"))
        render_kv("Exposure mode", graph.get("exposure_mode"))
        render_kv("Manual review required", review_required)
        render_kv("Publication ready", publication_ready)

        if caveats:
            st.caption("Caveats: " + " · ".join(f"`{item}`" for item in caveats))

        st.markdown("**Raw status payload**")
        st.json(payload)


def render_status_sidebar(base_url: str) -> None:
    st.sidebar.markdown("### API status")
    try:
        health = fetch_health(base_url)
        info = fetch_info(base_url)
        runtime = fetch_runtime(base_url)

        st.sidebar.success("API is reachable")
        render_kv("Status", health.get("status"))
        render_kv("Backend", health.get("backend_mode"))
        render_kv("Build ID", health.get("build_id"))
        render_kv("Corpus docs", health.get("corpus_doc_count"))
        render_kv("Embedding model", health.get("embedding_model_name"))
        render_kv("API version", info.get("api_version"))

        render_qdrant_runtime_status(runtime)
        render_citation_graph_status_panel(base_url)

        selected_paper_id = st.session_state.get("selected_paper_canonical_id")
        if selected_paper_id:
            st.sidebar.markdown("### Paper workspace")
            render_kv("Selected paper", compact_id(str(selected_paper_id), n=8))

        with st.sidebar.expander("Runtime details", expanded=False):
            render_kv("Ready", runtime.get("ready"))
            render_kv("Last loaded", runtime.get("last_loaded_at"))
            render_kv("Last reload", runtime.get("last_reload_at"))
            render_kv("Model reused", runtime.get("model_reused"))
            st.json(runtime.get("loaded_components", {}))

        if runtime.get("last_load_error"):
            st.sidebar.error(runtime["last_load_error"])
    except Exception as exc:
        st.sidebar.error(f"API unavailable: {exc}")


def render_sidebar(base_url: str, profiles_payload: dict[str, Any]) -> tuple[str, bool]:
    st.sidebar.title("ML Research Radar")
    st.sidebar.caption("Discovery UI · thin client over FastAPI")

    st.sidebar.markdown("### Connection")
    api_base_url = st.sidebar.text_input(
        "API base URL",
        value=base_url,
        help="Например: http://127.0.0.1:8000",
        key="api_base_url_input",
    ).strip()
    st.session_state["api_base_url"] = api_base_url

    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("Refresh", width="stretch"):
        clear_api_caches()
        st.rerun()

    if col_b.button("Reload", width="stretch"):
        try:
            with st.spinner("Reloading API runtime..."):
                payload = trigger_reload(api_base_url)
            st.sidebar.success(
                f"Reloaded build {payload.get('build_id', 'unknown')} | model reused={payload.get('model_reused')}"
            )
        except Exception as exc:
            st.sidebar.error(str(exc))

    render_status_sidebar(api_base_url)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Discovery controls")

    profiles = profiles_payload.get("profiles") or []
    profile_names = [p.get("name") for p in profiles if p.get("name")]
    default_profile = profiles_payload.get("default_profile") or (profile_names[0] if profile_names else None)

    if not profile_names:
        st.sidebar.error("No discovery profiles returned by API.")
        st.stop()

    if st.session_state.get("profile_name") not in profile_names:
        st.session_state["profile_name"] = default_profile

    current_profile_index = profile_names.index(st.session_state["profile_name"])
    st.sidebar.selectbox(
        "Profile",
        profile_names,
        index=current_profile_index,
        key="profile_name",
        help="Base ranking preset. Query controls below override/add filters.",
    )

    st.sidebar.number_input(
        "Top K",
        min_value=1,
        max_value=MAX_TOP_K,
        step=1,
        key="top_k",
    )

    st.sidebar.text_input(
        "Query title",
        key="query_title",
        placeholder="speech, transformer, diffusion...",
    )
    st.sidebar.text_input(
        "Source family",
        key="source_family",
        placeholder="arxiv, acl_anthology...",
    )

    year_cols = st.sidebar.columns(2)
    year_cols[0].text_input("Min year", key="min_year", placeholder="2025")
    year_cols[1].text_input("Max year", key="max_year", placeholder="2026")

    with st.sidebar.expander("Artifact/source filters", expanded=True):
        for key in BOOL_FILTER_KEYS:
            st.selectbox(
                BOOL_FILTER_LABELS[key],
                TRISTATE_OPTIONS,
                key=key,
                help="Profile default means the parameter is not sent to the API.",
            )

    with st.sidebar.expander("Sorting", expanded=False):
        st.selectbox("Sort by", SORT_OPTIONS, key="sort_by")
        st.selectbox("Direction", DIRECTION_OPTIONS, key="descending")

    st.sidebar.button(
        "Reset discovery filters",
        width="stretch",
        on_click=reset_discovery_filters,
        args=(default_profile,),
    )

    run_clicked = st.sidebar.button(
        "Run discovery ranking",
        type="primary",
        width="stretch",
    )
    return api_base_url, run_clicked


# --------------------------------------------------------------------------------------
# Rendering ranking
# --------------------------------------------------------------------------------------

def render_qdrant_search_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    st.markdown("#### Experimental Qdrant results")

    results = payload.get("results") or []
    meta = payload.get("meta") or {}

    cols = st.columns(6)
    cols[0].metric("Query", payload.get("query", "—"))
    cols[1].metric("Mode", payload.get("mode", "—"))
    cols[2].metric("Top K", payload.get("top_k", "—"))
    cols[3].metric("Returned", len(results))
    cols[4].metric("Backend", meta.get("vector_backend", "qdrant"))
    cols[5].metric("Build", compact_id(payload.get("build_id"), n=6))

    if meta:
        with st.expander("Experimental Qdrant search meta", expanded=False):
            st.json(meta)

    if not results:
        st.warning("No experimental Qdrant results returned.")
        with st.expander("Raw experimental Qdrant response", expanded=False):
            st.json(payload)
        return []

    st.dataframe(
        pd.DataFrame(
            [search_result_to_table_row(item, idx) for idx, item in enumerate(results, start=1)]
        ),
        hide_index=True,
        width="stretch",
    )

    for idx, item in enumerate(results, start=1):
        document = item.get("document") or {}
        retrieval = item.get("retrieval") or {}

        if not isinstance(document, dict):
            document = {}
        if not isinstance(retrieval, dict):
            retrieval = {}

        canonical_id = document.get("canonical_id")
        title = document.get("title") or "Untitled"

        with st.container(border=True):
            st.markdown(f"### {idx}. {title}")

            cols = st.columns(5)
            cols[0].metric("Year", dash(document.get("year")))
            cols[1].metric("Sources", dash(document.get("source_count")))
            cols[2].metric("Qdrant score", fmt_score(retrieval.get("score"), 4))
            cols[3].metric("Dense score", fmt_score(retrieval.get("dense_score"), 4))
            cols[4].metric("Point ID", dash(item.get("point_id")))

            st.caption(
                f"ID: `{compact_id(canonical_id)}` · "
                f"arXiv: `{dash(document.get('arxiv_id'))}` · "
                f"dense_index: `{dash(item.get('dense_index'))}`"
            )

            render_open_paper_workspace_button(
                canonical_id,
                label="Open Qdrant result in Paper workspace",
                key=f"open_qdrant_result_workspace_{idx}_{canonical_id}",
            )

            abstract = document.get("abstract")
            if abstract:
                preview = abstract if len(abstract) <= 600 else abstract[:600].rstrip() + "…"
                st.write(preview)

            with st.expander("Experimental Qdrant result JSON", expanded=False):
                st.json(item)

    with st.expander("Raw experimental Qdrant response", expanded=False):
        st.json(payload)

    return results


def render_qdrant_experimental_search_block(base_url: str) -> None:
    st.markdown("---")
    with st.expander("Experimental Qdrant dense search", expanded=False):
        st.caption(
            "Optional vector-serving smoke over `GET /experimental/search/qdrant`. "
            "Expected response mode: `dense_qdrant`. "
            "This does not change the main `/search` tab, `/search` defaults, "
            "or `ML_RADAR_SEARCH_BACKEND`."
        )

        qdrant_cols = st.columns([3, 1])
        with qdrant_cols[0]:
            st.text_input(
                "Qdrant search query",
                key="qdrant_search_query",
                placeholder="protein language models, multimodal retrieval, diffusion models...",
            )
        with qdrant_cols[1]:
            st.number_input(
                "Qdrant top K",
                min_value=1,
                max_value=MAX_TOP_K,
                step=1,
                key="qdrant_search_top_k",
            )

        if st.button(
            "Run experimental Qdrant search",
            type="secondary",
            width="stretch",
        ):
            try:
                params = build_qdrant_experimental_search_params()
                with st.spinner("Running experimental Qdrant search..."):
                    st.session_state["qdrant_search_payload"] = (
                        fetch_qdrant_experimental_search(base_url, params)
                    )
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(str(exc))
                st.info(
                    "Experimental Qdrant search requires the API file runtime and "
                    "a populated Qdrant collection configured via "
                    "`ML_RADAR_QDRANT_COLLECTION_NAME` "
                    "(default: `ml_radar_dense_benchmark_v1`)."
                )

        qdrant_payload = st.session_state.get("qdrant_search_payload")
        if qdrant_payload:
            render_qdrant_search_results(qdrant_payload)
        else:
            st.info(
                "Optional check: run Qdrant dense search after the API and Qdrant "
                "collection are available."
            )


def render_search_tab(base_url: str) -> None:
    st.subheader("Search")
    st.caption(
        "Search over the canonical paper corpus via `/search`. "
        "File backend supports lexical, dense and hybrid modes. "
        "DB backend currently supports lexical mode only."
    )

    st.text_input(
        "Search query",
        key="search_query",
        placeholder="graph neural networks, protein language models, diffusion models...",
    )

    control_cols = st.columns([1, 1, 1, 1])
    with control_cols[0]:
        st.selectbox("Search mode", SEARCH_MODE_OPTIONS, key="search_mode")
    with control_cols[1]:
        st.number_input(
            "Search top K",
            min_value=1,
            max_value=MAX_TOP_K,
            step=1,
            key="search_top_k",
        )
    with control_cols[2]:
        st.checkbox("Apply rank layer", key="search_rank")
    with control_cols[3]:
        st.selectbox("Search sort by", SEARCH_SORT_OPTIONS, key="search_sort_by")

    offset_cols = st.columns([1, 1, 2])
    with offset_cols[0]:
        st.number_input(
            "Search offset",
            min_value=0,
            max_value=1_000_000,
            step=10,
            key="search_offset",
        )
    with offset_cols[1]:
        st.selectbox("Open access", TRISTATE_OPTIONS, key="search_open_access")
    with offset_cols[2]:
        st.selectbox("Has legacy code link", TRISTATE_OPTIONS, key="search_has_code_link")

    with st.expander("Search filters", expanded=False):
        year_cols = st.columns(2)
        year_cols[0].text_input("Search year from", key="search_year_from", placeholder="2020")
        year_cols[1].text_input("Search year to", key="search_year_to", placeholder="2026")

        filter_cols = st.columns(4)
        filter_cols[0].text_input("Search category", key="search_category", placeholder="cs.LG")
        filter_cols[1].text_input("Search source", key="search_source", placeholder="arxiv")
        filter_cols[2].text_input(
            "Search publication type",
            key="search_publication_type",
            placeholder="preprint",
        )
        filter_cols[3].text_input("Search venue", key="search_venue", placeholder="NeurIPS")

    if st.button("Run search", type="primary", width="stretch"):
        try:
            params = build_search_params()
            with st.spinner("Running search..."):
                st.session_state["search_payload"] = fetch_search(base_url, params)
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(str(exc))
            st.info(
                "If you selected dense/hybrid mode, start the API with "
                "`set ML_RADAR_SEARCH_BACKEND=file`. "
                "DB backend currently supports lexical search only."
            )
            return

    render_qdrant_experimental_search_block(base_url)

    payload = st.session_state.get("search_payload")
    if not payload:
        st.info("Enter a query and click **Run search**.")
        st.markdown(
            "Good smoke queries: `protein language models`, `diffusion models`, "
            "`graph neural networks`, `retrieval augmented generation`."
        )
        return

    render_search_results(payload)

def profile_by_name(profiles_payload: dict[str, Any], name: str | None) -> dict[str, Any] | None:
    for profile in profiles_payload.get("profiles") or []:
        if profile.get("name") == name:
            return profile
    return None


def render_header(profiles_payload: dict[str, Any]) -> None:
    st.title("🔎 ML Research Radar")
    st.caption(
        "Paper-centric research discovery UI over FastAPI. "
        "Streamlit is only a thin client; ranking, detail cards and similar papers are served by `/discovery/*`."
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Profiles", profiles_payload.get("profile_count", "—"))
    metric_cols[1].metric("Default profile", profiles_payload.get("default_profile", "—"))
    metric_cols[2].metric("API layer", "Discovery")
    metric_cols[3].metric("UI mode", "Thin client")


def render_effective_filters(payload: dict[str, Any]) -> None:
    profile = payload.get("profile") or {}
    filters = payload.get("filters") or {}

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Base profile")
        render_kv("Name", profile.get("name"))
        render_kv("Description", profile.get("description"))
        render_kv("Base sort", profile.get("sort_by"))
        with st.expander("Base profile JSON", expanded=False):
            st.json(profile)

    with col2:
        st.markdown("#### Effective request")
        render_kv("Sort by", payload.get("sort_by"))
        render_kv("Descending", payload.get("descending"))
        render_kv("Top K", payload.get("top_k"))
        with st.expander("Effective filters", expanded=False):
            st.json(filters)

def search_result_to_table_row(item: dict[str, Any], rank: int) -> dict[str, Any]:
    document = item.get("document") or {}
    retrieval = item.get("retrieval") or {}
    ranking = item.get("ranking") or {}

    if not isinstance(document, dict):
        document = {}
    if not isinstance(retrieval, dict):
        retrieval = {}
    if not isinstance(ranking, dict):
        ranking = {}

    return {
        "rank": rank,
        "year": document.get("year"),
        "title": document.get("title"),
        "source_count": document.get("source_count"),
        "retrieval": first_non_empty(
            retrieval.get("hybrid_score"),
            retrieval.get("dense_score"),
            retrieval.get("lexical_score"),
            retrieval.get("score"),
        ),
        "final_rank": ranking.get("final_score"),
        "doi": document.get("doi"),
        "arxiv_id": document.get("arxiv_id"),
        "canonical_id": document.get("canonical_id"),
    }

def result_to_table_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": row.get("rank") or rank,
        "year": row.get("year"),
        "title": row.get("title"),
        "radar": row.get("radar_score"),
        "impl": row.get("implementation_readiness_score"),
        "source": row.get("source_confidence_score"),
        "code": row.get("has_code_artifact"),
        "dataset": row.get("has_dataset_artifact"),
        "model": row.get("has_model_artifact"),
        "demo": row.get("has_demo_artifact"),
        "github": row.get("github_found_repo"),
        "hf": row.get("huggingface_found"),
        "canonical_id": row.get("canonical_id"),
    }


def render_result_card(row: dict[str, Any], rank: int) -> None:
    title = row.get("title") or "Untitled"
    canonical_id = row.get("canonical_id")
    year = row.get("year")

    with st.container(border=True):
        st.markdown(f"### {rank}. {title}")
        render_badges(row)

        cols = st.columns(6)
        cols[0].metric("Year", dash(year))
        cols[1].metric("Radar", fmt_score(row.get("radar_score")))
        cols[2].metric("Impl", fmt_score(row.get("implementation_readiness_score")))
        cols[3].metric("Source", fmt_score(row.get("source_confidence_score")))
        cols[4].metric("Citations", fmt_score(row.get("citation_signal_score")))
        cols[5].metric("Recency", fmt_score(row.get("recency_score")))

        authors = normalize_authors(row.get("authors"), limit=6)
        source_families = summarize_sources(row.get("source_families"))
        st.caption(f"Authors: {authors}")
        st.caption(f"Sources: {source_families} · ID: `{compact_id(canonical_id)}`")

        if canonical_id:
            st.session_state["selected_canonical_id"] = canonical_id
            render_open_paper_workspace_button(
                canonical_id,
                label="Open in Paper workspace",
                key=f"open_ranking_paper_workspace_{rank}_{canonical_id}",
            )

        abstract = row.get("abstract") or row.get("abstract_preview")
        if abstract:
            preview = abstract if len(abstract) <= 700 else abstract[:700].rstrip() + "…"
            st.write(preview)

        with st.expander("Ranking row JSON", expanded=False):
            st.json(row)


def render_empty_results(payload: dict[str, Any]) -> None:
    st.warning("No papers matched the current filter combination.")
    st.markdown(
        "Try relaxing the filters: clear `has_hf`, `has_model`, `has_demo`, widen the year range, "
        "or switch back to `recent_artifact_ready`."
    )
    with st.expander("Effective filters for empty result", expanded=True):
        st.json(payload.get("filters") or {})

def render_search_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    st.markdown("---")
    st.subheader("Search results")

    results = payload.get("results") or []

    cols = st.columns(6)
    cols[0].metric("Query", payload.get("query", "—"))
    cols[1].metric("Mode", payload.get("mode", "—"))
    cols[2].metric("Top K", payload.get("top_k", "—"))
    cols[3].metric("Returned", len(results))
    cols[4].metric("Rank", str(payload.get("rank_applied")))
    cols[5].metric("Build", compact_id(payload.get("build_id"), n=6))

    meta = payload.get("meta")
    if meta:
        with st.expander("Search meta", expanded=False):
            st.json(meta)

    if not results:
        st.warning("No search results returned.")
        with st.expander("Raw search response", expanded=False):
            st.json(payload)
        return []

    st.markdown("#### Search results table")
    st.dataframe(
        pd.DataFrame(
            [search_result_to_table_row(item, idx) for idx, item in enumerate(results, start=1)]
        ),
        hide_index=True,
        width="stretch",
    )

    st.markdown("#### Search result cards")
    for idx, item in enumerate(results, start=1):
        document = item.get("document") or {}
        retrieval = item.get("retrieval") or {}
        ranking = item.get("ranking") or {}

        if not isinstance(document, dict):
            document = {}
        if not isinstance(retrieval, dict):
            retrieval = {}
        if not isinstance(ranking, dict):
            ranking = {}

        canonical_id = document.get("canonical_id")
        title = document.get("title") or "Untitled"

        with st.container(border=True):
            st.markdown(f"### {idx}. {title}")

            cols = st.columns(5)
            cols[0].metric("Year", dash(document.get("year")))
            cols[1].metric("Sources", dash(document.get("source_count")))
            cols[2].metric(
                "Retrieval",
                fmt_score(
                    first_non_empty(
                        retrieval.get("hybrid_score"),
                        retrieval.get("dense_score"),
                        retrieval.get("lexical_score"),
                        retrieval.get("score"),
                    ),
                    4,
                ),
            )
            cols[3].metric("Final rank", fmt_score(ranking.get("final_score"), 4))
            cols[4].metric("DOI", "yes" if document.get("doi") else "—")

            st.caption(
                f"ID: `{compact_id(canonical_id)}` · "
                f"arXiv: `{dash(document.get('arxiv_id'))}`"
            )

            render_open_paper_workspace_button(
                canonical_id,
                label="Open search result in Paper workspace",
                key=f"open_search_result_workspace_{idx}_{canonical_id}",
            )

            abstract = document.get("abstract")
            if abstract:
                preview = abstract if len(abstract) <= 600 else abstract[:600].rstrip() + "…"
                st.write(preview)

            with st.expander("Search result JSON", expanded=False):
                st.json(item)

    with st.expander("Raw search response", expanded=False):
        st.json(payload)

    return results

def render_ranking(payload: dict[str, Any]) -> list[dict[str, Any]]:
    st.markdown("---")
    st.subheader("Discovery ranking")

    summary_cols = st.columns(5)
    summary_cols[0].metric("Profile", safe_get(payload.get("profile"), "name", "—"))
    summary_cols[1].metric("Input rows", payload.get("input_rows_count", "—"))
    summary_cols[2].metric("Filtered", payload.get("filtered_rows_count", "—"))
    summary_cols[3].metric("Returned", payload.get("returned_rows_count", "—"))
    summary_cols[4].metric("Sort", payload.get("sort_by", "—"))

    render_effective_filters(payload)

    results = payload.get("results") or []
    if not results:
        render_empty_results(payload)
        return []

    table_rows = [result_to_table_row(row, idx) for idx, row in enumerate(results, start=1)]
    st.markdown("#### Results table")
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, width="stretch")

    st.markdown("#### Result cards")
    for idx, row in enumerate(results, start=1):
        render_result_card(row, idx)

    return results


# --------------------------------------------------------------------------------------
# Detail rendering
# --------------------------------------------------------------------------------------


def detail_root(detail_payload: dict[str, Any]) -> dict[str, Any]:
    detail = detail_payload.get("detail")
    return detail if isinstance(detail, dict) else detail_payload


def extract_detail_title(detail: dict[str, Any]) -> str:
    return str(first_non_empty(detail.get("title"), detail.get("paper_title"), "Untitled"))


def extract_scores(detail: dict[str, Any]) -> dict[str, Any]:
    scores = detail.get("scores")
    if isinstance(scores, dict):
        return scores
    return {
        key: detail.get(key)
        for key in [
            "radar_score",
            "implementation_readiness_score",
            "source_confidence_score",
            "citation_signal_score",
            "recency_score",
        ]
        if key in detail
    }


def extract_artifact_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = detail.get("artifacts") or detail.get("artifact_rows") or []
    if not isinstance(artifacts, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        entity = item.get("artifact") or item.get("entity") or item.get("artifact_entity") or item
        if not isinstance(entity, dict):
            entity = item
        rows.append(
            {
                "artifact_id": first_non_empty(
                    item.get("artifact_id"),
                    entity.get("artifact_id"),
                    item.get("id"),
                    entity.get("id"),
                ),
                "provider": first_non_empty(item.get("provider"), entity.get("provider")),
                "type": first_non_empty(
                    item.get("artifact_type"),
                    item.get("type"),
                    entity.get("artifact_type"),
                    entity.get("type"),
                ),
                "relation": first_non_empty(item.get("relation_type"), item.get("relation")),
                "title/name": first_non_empty(entity.get("name"), entity.get("title"), item.get("name")),
                "url": first_non_empty(
                    item.get("url"),
                    item.get("normalized_url"),
                    entity.get("url"),
                    entity.get("normalized_url"),
                    entity.get("external_url"),
                ),
                "stars": first_non_empty(
                    item.get("github_stars"),
                    entity.get("github_stars"),
                    safe_get(entity.get("metadata"), "stargazers_count"),
                ),
                "downloads": first_non_empty(
                    item.get("hf_downloads"),
                    entity.get("hf_downloads"),
                    safe_get(entity.get("metadata"), "downloads"),
                ),
            }
        )
    return rows


def render_links(links: Any) -> None:
    if not links:
        st.info("No links found in detail payload.")
        return

    if isinstance(links, dict):
        rows = []
        for key, value in links.items():
            if isinstance(value, str):
                rows.append({"label": key, "url": value})
            elif isinstance(value, list):
                for item in value:
                    rows.append({"label": key, "url": item})
        if rows:
            for row in rows:
                st.markdown(f"- **{row['label']}**: {maybe_markdown_link(str(row['url']), row['url'])}")
        else:
            st.json(links)
        return

    if isinstance(links, list):
        for item in links:
            if isinstance(item, str):
                st.markdown(f"- {maybe_markdown_link(item, item)}")
            elif isinstance(item, dict):
                label = item.get("label") or item.get("type") or item.get("url") or "link"
                url = item.get("url") or item.get("href")
                st.markdown(f"- **{label}**: {maybe_markdown_link(str(url), url)}")
        return

    st.json(links)


def render_paper_detail(detail_payload: dict[str, Any]) -> None:
    detail = detail_root(detail_payload)
    title = extract_detail_title(detail)
    scores = extract_scores(detail)

    st.markdown(f"## {title}")
    render_badges({**detail, **(detail.get("feature_summary") or {})})

    cols = st.columns(5)
    cols[0].metric("Year", dash(detail.get("year")))
    cols[1].metric("Radar", fmt_score(scores.get("radar_score")))
    cols[2].metric("Impl", fmt_score(scores.get("implementation_readiness_score")))
    cols[3].metric("Source", fmt_score(scores.get("source_confidence_score")))
    cols[4].metric("Recency", fmt_score(scores.get("recency_score")))

    render_kv("Canonical ID", detail.get("canonical_id") or detail_payload.get("canonical_id"))
    render_kv("Authors", normalize_authors(detail.get("authors"), limit=12))

    abstract = detail.get("abstract")
    if abstract:
        st.markdown("### Abstract")
        st.write(abstract)

    tabs = st.tabs(["Overview", "Artifacts", "Links", "Source evidence", "Raw detail"])

    with tabs[0]:
        st.markdown("### Feature summary")
        feature_summary = detail.get("feature_summary") or {}
        if feature_summary:
            st.json(feature_summary)
        else:
            st.info("No feature summary block found.")

        st.markdown("### Identifiers")
        identifiers = detail.get("identifiers") or {}
        if identifiers:
            st.json(identifiers)
        else:
            st.info("No identifiers block found.")

        st.markdown("### Artifact summary")
        artifact_summary = detail.get("artifact_summary") or {}
        if artifact_summary:
            st.json(artifact_summary)
        else:
            st.info("No artifact summary block found.")

    with tabs[1]:
        rows = extract_artifact_rows(detail)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            for row in rows:
                with st.container(border=True):
                    st.markdown(f"**{dash(row.get('provider'))} / {dash(row.get('type'))}**")
                    render_kv("Relation", row.get("relation"))
                    render_kv("Name", row.get("title/name"))
                    if row.get("url"):
                        st.markdown(maybe_markdown_link("Open artifact", row.get("url")))
                    render_kv("Stars", row.get("stars"))
                    render_kv("Downloads", row.get("downloads"))
        else:
            st.info("No artifact rows found in detail payload.")

    with tabs[2]:
        render_links(detail.get("links"))

    with tabs[3]:
        source_evidence = detail.get("source_evidence") or detail.get("sources") or {}
        if source_evidence:
            st.json(source_evidence)
        else:
            st.info("No source evidence block found.")

    with tabs[4]:
        st.json(detail_payload)


# --------------------------------------------------------------------------------------
# Similar papers
# --------------------------------------------------------------------------------------


def similar_row_to_table(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": row.get("rank"),
        "year": row.get("year"),
        "title": row.get("title"),
        "semantic": row.get("semantic_similarity"),
        "adjusted": row.get("radar_adjusted_similarity"),
        "radar": row.get("radar_score"),
        "impl": row.get("implementation_readiness_score"),
        "code": row.get("has_code_artifact"),
        "github": row.get("github_found_repo"),
        "hf": row.get("huggingface_found"),
        "canonical_id": row.get("canonical_id"),
    }


def render_similar_papers(base_url: str, canonical_id: str) -> None:
    control_cols = st.columns([1, 1, 2])
    with control_cols[0]:
        st.number_input(
            "Similar top K",
            min_value=1,
            max_value=50,
            step=1,
            key="similar_top_k",
        )
    with control_cols[1]:
        st.selectbox("Rank by", SIMILAR_RANK_BY_OPTIONS, key="similar_rank_by")

    try:
        with st.spinner("Loading similar papers..."):
            payload = fetch_similar_papers(
                base_url,
                canonical_id,
                top_k=int(st.session_state["similar_top_k"]),
                rank_by=st.session_state["similar_rank_by"],
            )
    except Exception as exc:
        st.error(str(exc))
        return

    results = payload.get("results") or []
    cols = st.columns(5)
    cols[0].metric("Rank by", payload.get("rank_by", "—"))
    cols[1].metric("Returned", payload.get("returned_rows_count", len(results)))
    cols[2].metric("Input rows", payload.get("input_rows_count", "—"))
    cols[3].metric("Target found", str(payload.get("target_found")))
    cols[4].metric("Embedding shape", str(safe_get(payload.get("dense_artifacts"), "embedding_shape", "—")))

    if not results:
        st.warning("No similar papers returned.")
        with st.expander("Raw similar response", expanded=False):
            st.json(payload)
        return

    st.dataframe(pd.DataFrame([similar_row_to_table(row) for row in results]), hide_index=True, width="stretch")

    for idx, row in enumerate(results, start=1):
        with st.container(border=True):
            st.markdown(f"### {row.get('rank')}. {row.get('title', 'Untitled')}")
            render_badges(row)
            metric_cols = st.columns(5)
            metric_cols[0].metric("Year", dash(row.get("year")))
            metric_cols[1].metric("Semantic", fmt_score(row.get("semantic_similarity"), 4))
            metric_cols[2].metric("Adjusted", fmt_score(row.get("radar_adjusted_similarity"), 4))
            metric_cols[3].metric("Radar", fmt_score(row.get("radar_score")))
            metric_cols[4].metric("Impl", fmt_score(row.get("implementation_readiness_score")))

            similar_canonical_id = str(row.get("canonical_id") or "").strip()
            st.caption(f"ID: `{compact_id(similar_canonical_id)}`")

            render_open_paper_workspace_button(
                similar_canonical_id,
                label="Open similar paper in Paper workspace",
                key=f"open_similar_paper_workspace_{idx}_{similar_canonical_id}",
                rerun=True,
            )

    with st.expander("Raw similar response", expanded=False):
        st.json(payload)

def render_similar_papers_payload(payload: dict[str, Any]) -> None:
    st.subheader("Similar papers for linked paper")

    results = payload.get("results") or []

    cols = st.columns(5)
    cols[0].metric("Rank by", payload.get("rank_by", "—"))
    cols[1].metric("Returned", payload.get("returned_rows_count", len(results)))
    cols[2].metric("Input rows", payload.get("input_rows_count", "—"))
    cols[3].metric("Target found", str(payload.get("target_found")))
    cols[4].metric(
        "Embedding shape",
        str(safe_get(payload.get("dense_artifacts"), "embedding_shape", "—")),
    )

    if not results:
        st.warning("No similar papers returned.")
        with st.expander("Raw linked paper similar response", expanded=False):
            st.json(payload)
        return

    st.dataframe(
        pd.DataFrame([similar_row_to_table(row) for row in results]),
        hide_index=True,
        width="stretch",
    )

    for idx, row in enumerate(results, start=1):
        with st.container(border=True):
            st.markdown(f"### {row.get('rank')}. {row.get('title', 'Untitled')}")
            render_badges(row)

            metric_cols = st.columns(5)
            metric_cols[0].metric("Year", dash(row.get("year")))
            metric_cols[1].metric("Semantic", fmt_score(row.get("semantic_similarity"), 4))
            metric_cols[2].metric(
                "Adjusted",
                fmt_score(row.get("radar_adjusted_similarity"), 4),
            )
            metric_cols[3].metric("Radar", fmt_score(row.get("radar_score")))
            metric_cols[4].metric(
                "Impl",
                fmt_score(row.get("implementation_readiness_score")),
            )

            similar_canonical_id = str(row.get("canonical_id") or "").strip()
            st.caption(f"ID: `{compact_id(similar_canonical_id)}`")

            render_open_paper_workspace_button(
                similar_canonical_id,
                label="Open similar paper in Paper workspace",
                key=f"open_selected_similar_paper_workspace_{idx}_{similar_canonical_id}",
                rerun=True,
            )

    with st.expander("Raw linked paper similar response", expanded=False):
        st.json(payload)

# --------------------------------------------------------------------------------------
# Topic clusters
# --------------------------------------------------------------------------------------


CLUSTER_SORT_OPTIONS = [
    "size_desc",
    "cluster_id_asc",
    "mean_radar_desc",
    "artifact_ready_desc",
]

CLUSTER_SORT_LABELS = {
    "size_desc": "Size ↓",
    "cluster_id_asc": "Cluster ID ↑",
    "mean_radar_desc": "Mean radar score ↓",
    "artifact_ready_desc": "Artifact-ready papers ↓",
}

CLUSTER_PAPER_SORT_OPTIONS = [
    "rank",
    "similarity_desc",
    "radar_score",
    "implementation_readiness_score",
    "citation_signal_score",
    "year_desc",
]

CLUSTER_PAPER_SORT_LABELS = {
    "rank": "Cluster rank / centroid order",
    "similarity_desc": "Closest to centroid",
    "radar_score": "Highest radar score",
    "implementation_readiness_score": "Most implementation-ready",
    "citation_signal_score": "Highest citation signal",
    "year_desc": "Newest papers",
}

CLUSTER_DETAIL_BOOL_FILTER_KEYS = [
    "has_code",
    "has_dataset",
    "has_model",
    "has_demo",
    "has_github",
    "has_hf",
    "has_acl",
    "has_doi",
]

CLUSTER_DETAIL_BOOL_FILTER_LABELS = {
    "has_code": "Code artifact",
    "has_dataset": "Dataset artifact",
    "has_model": "Model artifact",
    "has_demo": "Demo artifact",
    "has_github": "GitHub found",
    "has_hf": "Hugging Face",
    "has_acl": "ACL source",
    "has_doi": "DOI present",
}

def cluster_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    labels = row.get("label_candidates") or []
    representative_title = row.get("representative_title")

    if not representative_title:
        representative_papers = row.get("representative_papers") or []
        if representative_papers and isinstance(representative_papers[0], dict):
            representative_title = representative_papers[0].get("title")

    return {
        "cluster_id": row.get("cluster_id"),
        "size": row.get("size"),
        "labels": ", ".join(str(x) for x in labels[:5]),
        "artifact_ready": row.get("artifact_ready_count"),
        "code": row.get("code_artifact_count"),
        "dataset": row.get("dataset_artifact_count"),
        "model": row.get("model_artifact_count"),
        "demo": row.get("demo_artifact_count"),
        "mean_radar": row.get("mean_radar_score"),
        "mean_impl": row.get("mean_implementation_readiness_score"),
        "representative_title": representative_title,
    }


def cluster_paper_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": row.get("rank") or row.get("rank_within_cluster") or rank,
        "year": row.get("year"),
        "title": row.get("title"),
        "radar": row.get("radar_score"),
        "impl": row.get("implementation_readiness_score"),
        "citation": row.get("citation_signal_score"),
        "distance": row.get("distance_to_centroid"),
        "similarity": row.get("similarity_to_centroid"),
        "code": row.get("has_code_artifact"),
        "dataset": row.get("has_dataset_artifact"),
        "model": row.get("has_model_artifact"),
        "demo": row.get("has_demo_artifact"),
        "canonical_id": row.get("canonical_id"),
    }


def render_topic_cluster_metrics(payload: dict[str, Any]) -> None:
    cols = st.columns(5)
    cols[0].metric("Clusters", payload.get("cluster_count") or payload.get("total_cluster_count", "—"))
    cols[1].metric("Returned", payload.get("returned_count", "—"))
    cols[2].metric("Build", compact_id(payload.get("cluster_build_id"), n=6))
    cols[3].metric("Retrieval", compact_id(payload.get("retrieval_build_id"), n=6))
    cols[4].metric("Mode", payload.get("mode", "topic_clusters"))

def topic_map_point_row(row: dict[str, Any]) -> dict[str, Any]:
    labels = row.get("label_candidates") or []
    metadata = row.get("metadata") or {}

    cluster_id = row.get("cluster_id")
    point_type = row.get("point_type")

    title = row.get("title")
    if not title and point_type == "centroid":
        title = f"Cluster {cluster_id}: {', '.join(str(x) for x in labels[:3])}"

    return {
        "cluster_id": cluster_id,
        "point_type": point_type,
        "x": row.get("x"),
        "y": row.get("y"),
        "title": title or "—",
        "year": row.get("year"),
        "labels": ", ".join(str(x) for x in labels[:5]),
        "size": row.get("size") or metadata.get("cluster_size"),
        "radar": row.get("radar_score") or metadata.get("mean_radar_score"),
        "impl": (
            row.get("implementation_readiness_score")
            or metadata.get("mean_implementation_readiness_score")
        ),
        "artifact_ready": row.get("artifact_ready_count"),
        "canonical_id": row.get("canonical_id"),
    }


def render_topic_map_metrics(payload: dict[str, Any]) -> None:
    cols = st.columns(6)
    cols[0].metric("Projection", compact_id(payload.get("projection_build_id"), n=6))
    cols[1].metric("Algorithm", payload.get("projection_algorithm", "—"))
    cols[2].metric("Total points", payload.get("point_count", "—"))
    cols[3].metric("Centroids", payload.get("centroid_count", "—"))
    cols[4].metric("Representatives", payload.get("representative_count", "—"))
    cols[5].metric("Sampled", payload.get("sampled_count", "—"))


def render_topic_map(base_url: str) -> None:
    st.subheader("Topic map")
    st.caption(
        "Lightweight 2D projection over precomputed topic clusters. "
        "By default the UI shows cluster centroids only; paper points are optional."
    )

    control_cols = st.columns([1, 1, 2])
    with control_cols[0]:
        st.checkbox(
            "Show paper points",
            key="topic_map_include_papers",
            help="If disabled, only cluster centroids are loaded from `/discovery/clusters/map`.",
        )
    with control_cols[1]:
        st.number_input(
            "Max map points",
            min_value=80,
            max_value=10000,
            step=100,
            key="topic_map_max_points",
        )
    with control_cols[2]:
        st.caption(
            "Centroids keep the map readable. Paper points add representatives/samples, "
            "but can make the plot denser."
        )

    if st.button("Load topic map", type="primary", width="stretch"):
        try:
            params = {
                "include_papers": "true" if st.session_state["topic_map_include_papers"] else "false",
                "max_points": int(st.session_state["topic_map_max_points"]),
            }
            with st.spinner("Loading topic map projection..."):
                payload = fetch_topic_cluster_map(base_url, params)
            st.session_state["topic_map_payload"] = payload

            points = payload.get("points") or []
            centroid_points = [
                row
                for row in points
                if isinstance(row, dict) and row.get("point_type") == "centroid"
            ]
            if centroid_points:
                st.session_state["topic_map_selected_cluster_id"] = int(
                    centroid_points[0]["cluster_id"]
                )
        except Exception as exc:
            st.error(str(exc))
            return

    payload = st.session_state.get("topic_map_payload")
    if not payload:
        st.info("Click **Load topic map** to render the precomputed topic projection.")
        return

    render_topic_map_metrics(payload)

    points = payload.get("points") or []
    if not points:
        st.warning("Topic map returned no points.")
        with st.expander("Raw topic map response", expanded=False):
            st.json(payload)
        return

    df = pd.DataFrame([topic_map_point_row(row) for row in points])
    if df.empty:
        st.warning("Topic map points could not be converted into a table.")
        return

    # Keep point sizes stable and readable.
    df["plot_size"] = df["size"].fillna(50).astype(float).clip(lower=20, upper=1500)

    st.markdown("#### Research landscape projection")

    try:
        import plotly.express as px

        fig = px.scatter(
            df,
            x="x",
            y="y",
            color="cluster_id",
            symbol="point_type",
            size="plot_size",
            hover_data={
                "cluster_id": True,
                "point_type": True,
                "title": True,
                "year": True,
                "labels": True,
                "size": True,
                "radar": True,
                "impl": True,
                "artifact_ready": True,
                "canonical_id": True,
                "plot_size": False,
                "x": False,
                "y": False,
            },
            title="Topic map projection",
        )
        fig.update_layout(
            height=720,
            legend_title_text="Cluster",
            margin={"l": 10, "r": 10, "t": 50, "b": 10},
        )
        fig.update_traces(marker={"opacity": 0.78})
        st.plotly_chart(fig, width="stretch")
    except Exception as exc:
        st.warning(f"Plotly rendering failed, falling back to Streamlit scatter chart: {exc}")
        st.scatter_chart(
            df,
            x="x",
            y="y",
            color="cluster_id",
            size="plot_size",
        )

    centroid_df = df[df["point_type"] == "centroid"].copy()
    if not centroid_df.empty:
        st.markdown("#### Open cluster from map")
        cluster_ids = sorted(int(x) for x in centroid_df["cluster_id"].dropna().unique())

        labels = {
            int(row["cluster_id"]): (
                f"{int(row['cluster_id'])} · size={row.get('size', '—')} · "
                f"{str(row.get('labels') or '')[:120]}"
            )
            for _, row in centroid_df.iterrows()
            if row.get("cluster_id") is not None
        }

        if st.session_state.get("topic_map_selected_cluster_id") not in cluster_ids:
            st.session_state["topic_map_selected_cluster_id"] = cluster_ids[0]

        selected_cluster_id = st.selectbox(
            "Open mapped cluster detail",
            cluster_ids,
            format_func=lambda cid: labels.get(cid, str(cid)),
            key="topic_map_selected_cluster_id",
        )

        st.selectbox(
            "Mapped cluster paper sort by",
            CLUSTER_PAPER_SORT_OPTIONS,
            key="topic_map_cluster_detail_sort_by",
            format_func=lambda value: CLUSTER_PAPER_SORT_LABELS.get(value, value),
        )

        render_topic_cluster_detail(
            base_url,
            int(selected_cluster_id),
            sort_by=st.session_state["topic_map_cluster_detail_sort_by"],
        )

    with st.expander("Topic map points table", expanded=False):
        st.dataframe(df.drop(columns=["plot_size"]), hide_index=True, width="stretch")

    with st.expander("Raw topic map response", expanded=False):
        st.json(payload)

def render_topic_cluster_detail(
    base_url: str,
    cluster_id: int,
    *,
    sort_by: str = "rank",
) -> None:
    try:
        params = build_cluster_detail_params(
            top_k=int(st.session_state["cluster_detail_top_k"]),
            sort_by=sort_by,
        )
        with st.spinner(f"Loading topic cluster {cluster_id}..."):
            payload = fetch_topic_cluster_detail(
                base_url,
                cluster_id,
                params=params,
            )
    except ValueError:
        st.error(
            "Cluster detail year and score filters must be numeric. "
            "Scores should be in the 0.0–1.0 range."
        )
        return
    except Exception as exc:
        st.error(str(exc))
        return

    summary = payload.get("summary") or payload.get("cluster") or {}
    papers = payload.get("papers") or payload.get("results") or []

    st.markdown(f"### Cluster {cluster_id}")

    labels = summary.get("label_candidates") or payload.get("label_candidates") or []
    if labels:
        st.caption(" · ".join(f"`{label}`" for label in labels[:8]))

    cols = st.columns(6)
    cols[0].metric(
        "Total papers",
        payload.get("total_papers") or summary.get("size", "—"),
    )
    cols[1].metric(
        "After filters",
        payload.get("filtered_papers_count", "—"),
    )
    cols[2].metric(
        "Returned",
        payload.get("returned_papers_count") or len(papers),
    )
    cols[3].metric("Artifact-ready", summary.get("artifact_ready_count", "—"))
    cols[4].metric("Mean radar", fmt_score(summary.get("mean_radar_score")))
    cols[5].metric("Mean impl", fmt_score(summary.get("mean_implementation_readiness_score")))
    st.caption(f"Paper sort: `{payload.get('sort_by') or sort_by}`")
    effective_filters = payload.get("filters") or {}
    if effective_filters:
        st.caption(
            "Active filters: "
            + ", ".join(f"`{key}={value}`" for key, value in effective_filters.items())
        )

    with st.expander("Effective cluster detail filters", expanded=False):
        st.json(effective_filters)

    with st.expander("Cluster summary JSON", expanded=False):
        st.json(summary)

    if papers:
        st.markdown("#### Papers in cluster")
        st.dataframe(
            pd.DataFrame([cluster_paper_row(row, idx) for idx, row in enumerate(papers, start=1)]),
            hide_index=True,
            width="stretch",
        )

        for idx, row in enumerate(papers, start=1):
            with st.container(border=True):
                st.markdown(f"### {idx}. {row.get('title', 'Untitled')}")
                render_badges(row)

                paper_cols = st.columns(5)
                paper_cols[0].metric("Year", dash(row.get("year")))
                paper_cols[1].metric("Radar", fmt_score(row.get("radar_score")))
                paper_cols[2].metric("Impl", fmt_score(row.get("implementation_readiness_score")))
                paper_cols[3].metric("Distance", fmt_score(row.get("distance_to_centroid"), 4))
                paper_cols[4].metric("Similarity", fmt_score(row.get("similarity_to_centroid"), 4))

                st.caption(
                    f"Sources: {summarize_sources(row.get('source_families'))} · "
                    f"ID: `{compact_id(row.get('canonical_id'))}`"
                )
                canonical_id = str(row.get("canonical_id") or "").strip()
                render_open_paper_workspace_button(
                    canonical_id,
                    label="Open in Paper workspace",
                    key=f"open_cluster_paper_workspace_{cluster_id}_{idx}_{canonical_id}",
                    rerun=True,
                )
    else:
        st.warning("No papers returned for this cluster.")

    with st.expander("Raw cluster detail response", expanded=False):
        st.json(payload)


def render_topic_clusters(base_url: str) -> None:
    st.subheader("Topic clusters")
    st.caption(
        "Corpus-level topic navigation over precomputed cluster artifacts. "
        "The UI calls `/discovery/clusters`; it does not run clustering locally."
    )

    control_cols = st.columns([1, 1, 1])
    with control_cols[0]:
        st.number_input(
            "Cluster limit",
            min_value=1,
            max_value=100,
            step=1,
            key="cluster_limit",
        )
    with control_cols[1]:
        st.number_input(
            "Min cluster size",
            min_value=1,
            max_value=100000,
            step=1,
            key="cluster_min_size",
        )
    with control_cols[2]:
        st.selectbox(
            "Cluster sort by",
            CLUSTER_SORT_OPTIONS,
            key="cluster_sort_by",
            format_func=lambda value: CLUSTER_SORT_LABELS.get(value, value),
        )

    detail_control_cols = st.columns([1, 2])
    with detail_control_cols[0]:
        st.number_input(
            "Cluster detail top K",
            min_value=1,
            max_value=100,
            step=1,
            key="cluster_detail_top_k",
        )
    with detail_control_cols[1]:
        st.selectbox(
            "Cluster paper sort by",
            CLUSTER_PAPER_SORT_OPTIONS,
            key="cluster_detail_sort_by",
            format_func=lambda value: CLUSTER_PAPER_SORT_LABELS.get(value, value),
        )

    with st.expander("Cluster detail filters", expanded=False):
        year_cols = st.columns(2)
        year_cols[0].text_input(
            "Detail min year",
            key="cluster_detail_min_year",
            placeholder="2020",
        )
        year_cols[1].text_input(
            "Detail max year",
            key="cluster_detail_max_year",
            placeholder="2026",
        )

        st.caption("Artifact/source filters inside the selected topic cluster")
        bool_cols = st.columns(4)
        for idx, key in enumerate(CLUSTER_DETAIL_BOOL_FILTER_KEYS):
            with bool_cols[idx % 4]:
                st.selectbox(
                    CLUSTER_DETAIL_BOOL_FILTER_LABELS[key],
                    TRISTATE_OPTIONS,
                    key=f"cluster_detail_{key}",
                    help="Profile default means this filter is not sent to the API.",
                )

        score_cols = st.columns(3)
        score_cols[0].text_input(
            "Min radar score",
            key="cluster_detail_min_radar_score",
            placeholder="0.3",
        )
        score_cols[1].text_input(
            "Min implementation readiness",
            key="cluster_detail_min_implementation_readiness_score",
            placeholder="0.2",
        )
        score_cols[2].text_input(
            "Min citation signal",
            key="cluster_detail_min_citation_signal_score",
            placeholder="0.1",
        )

        st.button(
            "Reset cluster detail filters",
            width="stretch",
            on_click=reset_cluster_detail_filters,
        )

    if st.button("Load topic clusters", type="primary", width="stretch"):
        try:
            params = {
                "limit": int(st.session_state["cluster_limit"]),
                "min_size": int(st.session_state["cluster_min_size"]),
                "sort_by": st.session_state["cluster_sort_by"],
            }
            with st.spinner("Loading topic clusters..."):
                payload = fetch_topic_clusters(base_url, params)
            st.session_state["cluster_payload"] = payload

            results = payload.get("results") or []
            if results and isinstance(results[0], dict):
                st.session_state["selected_cluster_id"] = int(results[0]["cluster_id"])
        except Exception as exc:
            st.error(str(exc))
            return

    payload = st.session_state.get("cluster_payload")
    if not payload:
        st.info("Click **Load topic clusters** to browse the topic landscape.")
        return

    render_topic_cluster_metrics(payload)

    results = payload.get("results") or []
    if not results:
        st.warning("No clusters matched the current filters.")
        with st.expander("Raw clusters response", expanded=False):
            st.json(payload)
        return

    table_rows = [cluster_summary_row(row) for row in results]
    st.markdown("#### Cluster list")
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, width="stretch")

    cluster_ids = [int(row["cluster_id"]) for row in results if row.get("cluster_id") is not None]
    labels = {
        int(row["cluster_id"]): (
            f"{row.get('cluster_id')} · size={row.get('size')} · "
            f"{', '.join(str(x) for x in (row.get('label_candidates') or [])[:3])}"
        )
        for row in results
        if row.get("cluster_id") is not None
    }

    if not cluster_ids:
        st.warning("Cluster IDs were not present in the response.")
        return

    if st.session_state.get("selected_cluster_id") not in cluster_ids:
        st.session_state["selected_cluster_id"] = cluster_ids[0]

    selected_cluster_id = st.selectbox(
        "Open cluster detail",
        cluster_ids,
        format_func=lambda cid: labels.get(cid, str(cid)),
        key="selected_cluster_id",
    )

    render_topic_cluster_detail(
        base_url,
        int(selected_cluster_id),
        sort_by=st.session_state["cluster_detail_sort_by"],
    )

    with st.expander("Raw clusters response", expanded=False):
        st.json(payload)


def render_selected_paper_topic_cluster(base_url: str, canonical_id: str) -> None:
    st.subheader("Selected paper topic cluster")

    try:
        with st.spinner("Loading selected paper topic cluster..."):
            payload = fetch_paper_topic_cluster(base_url, canonical_id)
    except Exception as exc:
        st.error(str(exc))
        return

    assignment = payload.get("assignment") or {}
    cluster = payload.get("cluster") or {}

    cols = st.columns(5)
    cols[0].metric("Cluster ID", assignment.get("cluster_id", "—"))
    cols[1].metric("Rank in cluster", assignment.get("rank_within_cluster", "—"))
    cols[2].metric("Distance", fmt_score(assignment.get("distance_to_centroid"), 4))
    cols[3].metric("Similarity", fmt_score(assignment.get("similarity_to_centroid"), 4))
    cols[4].metric("Cluster size", cluster.get("size", "—"))

    labels = cluster.get("label_candidates") or []
    if labels:
        st.caption(" · ".join(f"`{label}`" for label in labels[:8]))

    with st.expander("Paper topic cluster JSON", expanded=False):
        st.json(payload)

def render_paper_topic_cluster_payload(payload: dict[str, Any]) -> None:
    st.subheader("Linked paper topic cluster")

    if not payload.get("found", True):
        st.warning("No topic cluster found for selected linked paper.")
        with st.expander("Paper topic cluster JSON", expanded=False):
            st.json(payload)
        return

    assignment = payload.get("assignment") or {}
    cluster = payload.get("cluster") or {}

    cols = st.columns(5)
    cols[0].metric("Cluster ID", assignment.get("cluster_id", "—"))
    cols[1].metric("Rank in cluster", assignment.get("rank_within_cluster", "—"))
    cols[2].metric("Distance", fmt_score(assignment.get("distance_to_centroid"), 4))
    cols[3].metric("Similarity", fmt_score(assignment.get("similarity_to_centroid"), 4))
    cols[4].metric("Cluster size", cluster.get("size", "—"))

    labels = cluster.get("label_candidates") or []
    if labels:
        st.caption(" · ".join(f"`{label}`" for label in labels[:8]))

    with st.expander("Linked paper topic cluster JSON", expanded=False):
        st.json(payload)

def build_selected_paper_citation_graph_params() -> dict[str, Any]:
    return {
        "limit": int(st.session_state["selected_paper_citation_graph_limit"]),
        "offset": int(st.session_state["selected_paper_citation_graph_offset"]),
    }


def build_citation_graph_diagnostics_params() -> dict[str, Any]:
    return {
        "limit": int(st.session_state["citation_graph_diagnostics_limit"]),
        "offset": int(st.session_state["citation_graph_diagnostics_offset"]),
    }


def _citation_graph_source_families(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value[:8]) or "—"
    return str(value) if value else "—"


def citation_graph_reference_row_to_table(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "edge_type": row.get("edge_type"),
        "resolved": row.get("resolved"),
        "target_canonical_id": row.get("target_canonical_id"),
        "target_title": row.get("target_title"),
        "target_year": row.get("target_year"),
        "external_reference_id": row.get("external_reference_id"),
        "reference_type": row.get("reference_type"),
        "normalized_reference": row.get("normalized_reference"),
        "source_families": _citation_graph_source_families(row.get("source_families")),
        "evidence_count": row.get("evidence_count"),
        "edge_id": row.get("edge_id"),
    }


def citation_graph_citation_row_to_table(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_canonical_id": row.get("source_canonical_id"),
        "source_title": row.get("source_title"),
        "source_year": row.get("source_year"),
        "reference_type": row.get("reference_type"),
        "normalized_reference": row.get("normalized_reference"),
        "source_families": _citation_graph_source_families(row.get("source_families")),
        "evidence_count": row.get("evidence_count"),
        "edge_id": row.get("edge_id"),
    }


def citation_graph_source_family_row_to_table(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_family": row.get("source_family"),
        "paper_count_with_reference_evidence": row.get(
            "paper_count_with_reference_evidence"
        ),
        "reference_edge_count": row.get("reference_edge_count"),
        "resolved_edge_count": row.get("resolved_edge_count"),
        "external_edge_count": row.get("external_edge_count"),
    }


def citation_graph_top_referenced_paper_row_to_table(
    row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "canonical_id": row.get("canonical_id"),
        "year": row.get("year"),
        "title": row.get("title"),
        "incoming_resolved_reference_count": row.get(
            "incoming_resolved_reference_count"
        ),
        "source_families": _citation_graph_source_families(row.get("source_families")),
    }


def citation_graph_top_external_reference_row_to_table(
    row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "external_reference_id": row.get("external_reference_id"),
        "reference_type": row.get("reference_type"),
        "normalized_reference": row.get("normalized_reference"),
        "referencing_paper_count": row.get("referencing_paper_count"),
        "source_families": _citation_graph_source_families(row.get("source_families")),
    }


def render_citation_graph_traversal_payload(
    payload: dict[str, Any],
    *,
    title: str,
    row_mapper: Any,
    raw_expander_label: str,
    open_button_label: str,
    open_button_key_prefix: str,
    canonical_id_field: str,
) -> None:
    rows = payload.get("items") or []
    page = payload.get("page") or {}
    caveats = payload.get("caveats") or []

    st.markdown(f"#### {title}")

    cols = st.columns(4)
    cols[0].metric("Returned", page.get("returned", len(rows)))
    cols[1].metric("Total estimate", dash(page.get("total_estimate")))
    cols[2].metric("Limit", dash(page.get("limit")))
    cols[3].metric("Offset", dash(page.get("offset")))

    if caveats:
        st.caption("Caveats: " + " · ".join(f"`{item}`" for item in caveats))

    if not rows:
        st.info("No citation graph evidence rows returned for this request.")
        with st.expander(raw_expander_label, expanded=False):
            st.json(payload)
        return

    st.dataframe(
        pd.DataFrame([row_mapper(row) for row in rows if isinstance(row, dict)]),
        hide_index=True,
        width="stretch",
    )

    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue

        row_canonical_id = str(row.get(canonical_id_field) or "").strip()
        if row_canonical_id:
            render_open_paper_workspace_button(
                row_canonical_id,
                label=open_button_label,
                key=f"{open_button_key_prefix}_{idx}_{row_canonical_id}",
                rerun=True,
            )

    with st.expander(raw_expander_label, expanded=False):
        st.json(payload)


def render_citation_graph_diagnostics_payload(
    payload: dict[str, Any],
    *,
    title: str,
    row_mapper: Any,
    raw_expander_label: str,
    open_button_label: str | None = None,
    open_button_key_prefix: str | None = None,
    canonical_id_field: str | None = None,
) -> None:
    rows = payload.get("items") or []
    page = payload.get("page") or {}
    caveats = payload.get("caveats") or []

    st.markdown(f"#### {title}")

    cols = st.columns(4)
    cols[0].metric("Returned", page.get("returned", len(rows)))
    cols[1].metric("Total estimate", dash(page.get("total_estimate")))
    cols[2].metric("Limit", dash(page.get("limit")))
    cols[3].metric("Offset", dash(page.get("offset")))

    if caveats:
        st.caption("Caveats: " + " · ".join(f"`{item}`" for item in caveats))

    if not rows:
        st.info("No citation graph diagnostic rows returned for this request.")
        with st.expander(raw_expander_label, expanded=False):
            st.json(payload)
        return

    st.dataframe(
        pd.DataFrame([row_mapper(row) for row in rows if isinstance(row, dict)]),
        hide_index=True,
        width="stretch",
    )

    if canonical_id_field and open_button_label and open_button_key_prefix:
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue

            row_canonical_id = str(row.get(canonical_id_field) or "").strip()
            if row_canonical_id:
                render_open_paper_workspace_button(
                    row_canonical_id,
                    label=open_button_label,
                    key=f"{open_button_key_prefix}_{idx}_{row_canonical_id}",
                    rerun=True,
                )

    with st.expander(raw_expander_label, expanded=False):
        st.json(payload)


def render_citation_graph_diagnostics_panel(base_url: str) -> None:
    st.subheader("Citation graph diagnostics")
    st.caption(
        "Local citation/reference graph diagnostics from the Citation Graph API. "
        "These tables are metadata-derived, read-only, not a complete citation index, "
        "not global citation metrics, and not publication-grade rankings."
    )

    control_cols = st.columns([1, 1])
    with control_cols[0]:
        st.number_input(
            "Citation graph diagnostics limit",
            min_value=1,
            max_value=100,
            step=1,
            key="citation_graph_diagnostics_limit",
        )
    with control_cols[1]:
        st.number_input(
            "Citation graph diagnostics offset",
            min_value=0,
            max_value=1_000_000,
            step=20,
            key="citation_graph_diagnostics_offset",
        )

    params = build_citation_graph_diagnostics_params()
    action_cols = st.columns([1, 1, 1])

    with action_cols[0]:
        if st.button(
            "Load citation graph source families",
            key="load_citation_graph_source_families",
            width="stretch",
        ):
            try:
                with st.spinner("Loading citation graph source-family diagnostics..."):
                    st.session_state["citation_graph_source_families_payload"] = (
                        fetch_citation_graph_source_families(base_url, params)
                    )
            except Exception as exc:
                st.error(str(exc))

    with action_cols[1]:
        if st.button(
            "Load citation graph top referenced papers",
            key="load_citation_graph_top_referenced_papers",
            width="stretch",
        ):
            try:
                with st.spinner("Loading top referenced paper diagnostics..."):
                    st.session_state["citation_graph_top_referenced_papers_payload"] = (
                        fetch_citation_graph_top_referenced_papers(base_url, params)
                    )
            except Exception as exc:
                st.error(str(exc))

    with action_cols[2]:
        if st.button(
            "Load citation graph top external references",
            key="load_citation_graph_top_external_references",
            width="stretch",
        ):
            try:
                with st.spinner("Loading top external reference diagnostics..."):
                    st.session_state["citation_graph_top_external_references_payload"] = (
                        fetch_citation_graph_top_external_references(base_url, params)
                    )
            except Exception as exc:
                st.error(str(exc))

    st.caption(
        "Requires `ML_RADAR_CITATION_GRAPH_API_ENABLED=true`. "
        "Diagnostics are local-inspection evidence only: not global citation metrics, "
        "not publication-grade rankings, and not publication-ready."
    )

    source_families_payload = st.session_state.get(
        "citation_graph_source_families_payload"
    )
    top_referenced_payload = st.session_state.get(
        "citation_graph_top_referenced_papers_payload"
    )
    top_external_payload = st.session_state.get(
        "citation_graph_top_external_references_payload"
    )

    if not any([source_families_payload, top_referenced_payload, top_external_payload]):
        st.info(
            "Load source-family diagnostics, top referenced papers, or top external "
            "references to inspect citation graph diagnostic evidence."
        )
        return

    if source_families_payload:
        render_citation_graph_diagnostics_payload(
            source_families_payload,
            title="Source-family reference diagnostics",
            row_mapper=citation_graph_source_family_row_to_table,
            raw_expander_label="Raw source-family diagnostics payload",
        )

    if top_referenced_payload:
        render_citation_graph_diagnostics_payload(
            top_referenced_payload,
            title="Top referenced papers",
            row_mapper=citation_graph_top_referenced_paper_row_to_table,
            raw_expander_label="Raw top referenced papers payload",
            open_button_label="Open top referenced paper in Paper workspace",
            open_button_key_prefix="open_citation_graph_top_referenced_paper",
            canonical_id_field="canonical_id",
        )

    if top_external_payload:
        render_citation_graph_diagnostics_payload(
            top_external_payload,
            title="Top external references",
            row_mapper=citation_graph_top_external_reference_row_to_table,
            raw_expander_label="Raw top external references payload",
        )


def render_selected_paper_citation_graph_panel(base_url: str, canonical_id: str) -> None:
    st.subheader("Selected paper citation graph evidence")
    st.caption(
        "Local citation/reference evidence from the Citation Graph API. "
        "This is metadata-derived, read-only, not a complete citation index, "
        "and not publication-ready."
    )

    control_cols = st.columns([1, 1])
    with control_cols[0]:
        st.number_input(
            "Citation graph evidence limit",
            min_value=1,
            max_value=100,
            step=1,
            key="selected_paper_citation_graph_limit",
        )
    with control_cols[1]:
        st.number_input(
            "Citation graph evidence offset",
            min_value=0,
            max_value=1_000_000,
            step=20,
            key="selected_paper_citation_graph_offset",
        )

    action_cols = st.columns([1, 1])
    with action_cols[0]:
        if st.button(
            "Load selected paper outgoing references",
            key="load_selected_paper_citation_references",
            width="stretch",
        ):
            try:
                with st.spinner("Loading outgoing citation graph references..."):
                    params = build_selected_paper_citation_graph_params()
                    st.session_state["selected_paper_citation_references_payload"] = (
                        fetch_citation_graph_paper_references(
                            base_url,
                            canonical_id,
                            params,
                        )
                    )
            except Exception as exc:
                st.error(str(exc))

    with action_cols[1]:
        if st.button(
            "Load selected paper incoming citations",
            key="load_selected_paper_citation_citations",
            width="stretch",
        ):
            try:
                with st.spinner("Loading incoming citation graph citations..."):
                    params = build_selected_paper_citation_graph_params()
                    st.session_state["selected_paper_citation_citations_payload"] = (
                        fetch_citation_graph_paper_citations(
                            base_url,
                            canonical_id,
                            params,
                        )
                    )
            except Exception as exc:
                st.error(str(exc))

    st.caption(
        "Requires `ML_RADAR_CITATION_GRAPH_API_ENABLED=true`. "
        "If disabled or incompatible, the API fails closed and the UI shows the error."
    )

    references_payload = st.session_state.get(
        "selected_paper_citation_references_payload"
    )
    citations_payload = st.session_state.get(
        "selected_paper_citation_citations_payload"
    )

    if not references_payload and not citations_payload:
        st.info(
            "Load outgoing references or incoming resolved citations for the selected paper."
        )
        return

    if references_payload:
        render_citation_graph_traversal_payload(
            references_payload,
            title="Outgoing references",
            row_mapper=citation_graph_reference_row_to_table,
            raw_expander_label="Raw outgoing references payload",
            open_button_label="Open referenced paper in Paper workspace",
            open_button_key_prefix="open_citation_graph_reference_target",
            canonical_id_field="target_canonical_id",
        )

    if citations_payload:
        render_citation_graph_traversal_payload(
            citations_payload,
            title="Incoming resolved citations",
            row_mapper=citation_graph_citation_row_to_table,
            raw_expander_label="Raw incoming citations payload",
            open_button_label="Open citing paper in Paper workspace",
            open_button_key_prefix="open_citation_graph_citation_source",
            canonical_id_field="source_canonical_id",
        )


def render_selected_paper_artifacts(base_url: str, detail_payload: dict[str, Any] | None) -> None:
    st.subheader("Selected paper artifacts")

    if not detail_payload:
        st.info("Load selected paper detail first to inspect artifact evidence.")
        return

    detail = detail_root(detail_payload)
    rows = extract_artifact_rows(detail)

    if not rows:
        st.info("No artifact rows found in selected paper detail payload.")
        with st.expander("Selected paper detail payload", expanded=False):
            st.json(detail_payload)
        return

    st.markdown("#### Artifact evidence from paper detail")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    artifact_ids = [
        str(row.get("artifact_id"))
        for row in rows
        if isinstance(row, dict) and row.get("artifact_id")
    ]

    if not artifact_ids:
        st.warning(
            "Artifact rows were found, but artifact_id is missing. "
            "Artifact detail navigation requires artifact_id in the paper detail payload."
        )
        with st.expander("Artifact rows without artifact_id", expanded=False):
            st.json(rows)
        return

    labels = {
        str(row.get("artifact_id")): (
            f"{row.get('provider') or '—'} · "
            f"{row.get('type') or '—'} · "
            f"{row.get('title/name') or row.get('url') or row.get('artifact_id')}"
        )
        for row in rows
        if isinstance(row, dict) and row.get("artifact_id")
    }

    if st.session_state.get("selected_paper_selected_artifact_id") not in artifact_ids:
        st.session_state["selected_paper_selected_artifact_id"] = artifact_ids[0]

    selected_artifact_id = st.selectbox(
        "Open selected paper artifact",
        artifact_ids,
        key="selected_paper_selected_artifact_id",
        format_func=lambda artifact_id: labels.get(artifact_id, artifact_id),
    )

    linked_control_cols = st.columns([1, 1, 1, 1])
    with linked_control_cols[0]:
        st.number_input(
            "Paper artifact linked papers limit",
            min_value=1,
            max_value=100,
            step=1,
            key="selected_paper_artifact_linked_papers_limit",
        )
    with linked_control_cols[1]:
        st.number_input(
            "Paper artifact linked papers offset",
            min_value=0,
            max_value=1_000_000,
            step=20,
            key="selected_paper_artifact_linked_papers_offset",
        )
    with linked_control_cols[2]:
        st.selectbox(
            "Paper artifact linked relation type",
            ARTIFACT_RELATION_TYPE_OPTIONS,
            key="selected_paper_artifact_linked_papers_relation_type",
            format_func=lambda value: value or "Any relation",
        )
    with linked_control_cols[3]:
        st.selectbox(
            "Paper artifact linked papers sort by",
            ARTIFACT_LINKED_PAPERS_SORT_OPTIONS,
            key="selected_paper_artifact_linked_papers_sort_by",
        )

    st.text_input(
        "Paper artifact linked papers min confidence",
        key="selected_paper_artifact_linked_papers_min_confidence",
        placeholder="0.7",
    )

    action_cols = st.columns([1, 1])

    with action_cols[0]:
        if st.button(
            "Load selected paper artifact detail",
            key="load_selected_paper_artifact_detail",
            width="stretch",
        ):
            try:
                with st.spinner("Loading selected paper artifact detail..."):
                    st.session_state["selected_paper_artifact_detail_payload"] = (
                        fetch_artifact_detail(base_url, selected_artifact_id)
                    )
            except Exception as exc:
                st.error(str(exc))

    with action_cols[1]:
        if st.button(
            "Load selected paper artifact linked papers",
            key="load_selected_paper_artifact_linked_papers",
            width="stretch",
        ):
            try:
                params = build_selected_paper_artifact_linked_papers_params()
                with st.spinner("Loading linked papers for selected paper artifact..."):
                    st.session_state["selected_paper_artifact_linked_papers_payload"] = (
                        fetch_artifact_linked_papers(
                            base_url,
                            selected_artifact_id,
                            params,
                        )
                    )
            except ValueError:
                st.error(
                    "Linked paper filters must be numeric where applicable. "
                    "min_confidence should be 0.0–1.0."
                )
            except Exception as exc:
                st.error(str(exc))

    artifact_detail_payload = st.session_state.get(
        "selected_paper_artifact_detail_payload"
    )
    artifact_linked_papers_payload = st.session_state.get(
        "selected_paper_artifact_linked_papers_payload"
    )

    if artifact_detail_payload:
        st.markdown("#### Selected paper artifact detail")
        render_artifact_detail_panel(artifact_detail_payload)

    if artifact_linked_papers_payload:
        st.markdown("#### Other papers linked to this artifact")
        render_artifact_linked_papers(artifact_linked_papers_payload)

def render_paper_workspace(base_url: str) -> None:
    st.subheader("Paper workspace")
    st.caption(
        "Unified paper-centric workspace. Open a paper from ranking, topic clusters, "
        "topic map or artifact linked papers, then inspect its metadata, artifacts, "
        "similar papers and topic context in one place."
    )

    selected_paper_id = st.session_state.get("selected_paper_canonical_id")

    manual_cols = st.columns([3, 1])
    with manual_cols[0]:
        manual_id = st.text_input(
            "Canonical ID",
            value=selected_paper_id or "",
            key="paper_workspace_manual_canonical_id",
            placeholder="Paste canonical_id here or open a paper from another tab.",
        ).strip()
    with manual_cols[1]:
        if st.button("Use canonical ID", key="paper_workspace_use_manual_id", width="stretch"):
            if manual_id:
                select_paper(manual_id)
                st.rerun()
            else:
                st.warning("Canonical ID is empty.")

    selected_paper_id = st.session_state.get("selected_paper_canonical_id")

    if not selected_paper_id:
        st.info(
            "No selected paper yet. Open one from Discovery ranking, Topic clusters, "
            "Topic map, or Artifact explorer."
        )
        return

    st.markdown("### Selected paper")
    render_kv("Canonical ID", selected_paper_id)

    similar_cols = st.columns([1, 1])
    with similar_cols[0]:
        st.number_input(
            "Workspace similar top K",
            min_value=1,
            max_value=50,
            step=1,
            key="selected_paper_similar_top_k",
        )
    with similar_cols[1]:
        st.selectbox(
            "Workspace similar rank by",
            SIMILAR_RANK_BY_OPTIONS,
            key="selected_paper_similar_rank_by",
        )

    action_cols = st.columns([1, 1, 1, 1])

    with action_cols[0]:
        if st.button(
            "Load selected paper detail",
            key="load_selected_paper_detail",
            width="stretch",
        ):
            try:
                with st.spinner("Loading selected paper detail..."):
                    st.session_state["selected_paper_detail_payload"] = fetch_paper_detail(
                        base_url,
                        selected_paper_id,
                    )
                    reset_selected_paper_artifact_navigation()
            except Exception as exc:
                st.error(str(exc))

    with action_cols[1]:
        if st.button(
            "Load selected paper similar papers",
            key="load_selected_paper_similar",
            width="stretch",
        ):
            try:
                with st.spinner("Loading selected paper similar papers..."):
                    st.session_state["selected_paper_similar_payload"] = fetch_similar_papers(
                        base_url,
                        selected_paper_id,
                        top_k=int(st.session_state["selected_paper_similar_top_k"]),
                        rank_by=st.session_state["selected_paper_similar_rank_by"],
                    )
            except Exception as exc:
                st.error(str(exc))

    with action_cols[2]:
        if st.button(
            "Load selected paper topic cluster",
            key="load_selected_paper_cluster",
            width="stretch",
        ):
            try:
                with st.spinner("Loading selected paper topic cluster..."):
                    st.session_state["selected_paper_cluster_payload"] = fetch_paper_topic_cluster(
                        base_url,
                        selected_paper_id,
                    )
            except Exception as exc:
                st.error(str(exc))

    with action_cols[3]:
        if st.button(
            "Clear selected paper",
            key="clear_selected_paper",
            width="stretch",
        ):
            clear_selected_paper()
            st.rerun()

    detail_payload = st.session_state.get("selected_paper_detail_payload")
    similar_payload = st.session_state.get("selected_paper_similar_payload")
    cluster_payload = st.session_state.get("selected_paper_cluster_payload")

    if not any([detail_payload, similar_payload, cluster_payload]):
        st.info(
            "Load detail, similar papers, or topic cluster for the selected paper."
        )

    workspace_tabs = st.tabs(
        [
            "Selected paper detail",
            "Selected paper similar papers",
            "Selected paper topic cluster",
            "Selected paper artifacts",
            "Citation graph evidence",
        ]
    )

    with workspace_tabs[0]:
        if detail_payload:
            render_paper_detail(detail_payload)
        else:
            st.info("Click **Load selected paper detail**.")

    with workspace_tabs[1]:
        if similar_payload:
            render_similar_papers_payload(similar_payload)
        else:
            st.info("Click **Load selected paper similar papers**.")

    with workspace_tabs[2]:
        if cluster_payload:
            render_paper_topic_cluster_payload(cluster_payload)
        else:
            st.info("Click **Load selected paper topic cluster**.")

    with workspace_tabs[3]:
        render_selected_paper_artifacts(base_url, detail_payload)

    with workspace_tabs[4]:
        render_selected_paper_citation_graph_panel(base_url, selected_paper_id)

# --------------------------------------------------------------------------------------
# Main app
# --------------------------------------------------------------------------------------


def main() -> None:
    init_ui_state()

    base_url = st.session_state["api_base_url"]
    profiles_payload = get_profiles_or_stop(base_url)
    render_header(profiles_payload)

    api_base_url, run_clicked = render_sidebar(base_url, profiles_payload)

    (
        ranking_tab,
        search_tab,
        paper_workspace_tab,
        citation_graph_diagnostics_tab,
        clusters_tab,
        topic_map_tab,
        artifacts_tab,
    ) = st.tabs(
        [
            "Discovery ranking",
            "Search",
            "Paper workspace",
            "Citation graph diagnostics",
            "Topic clusters",
            "Topic map",
            "Artifact explorer",
        ]
    )

    with ranking_tab:
        if run_clicked:
            try:
                params = build_ranking_params()
                with st.spinner("Loading discovery ranking..."):
                    payload = fetch_ranking(api_base_url, st.session_state["profile_name"], params)
                st.session_state["ranking_payload"] = payload
                results = payload.get("results") or []
                st.session_state["selected_canonical_id"] = (
                    results[0].get("canonical_id") if results and isinstance(results[0], dict) else None
                )
            except ValueError:
                st.error("Min year / Max year must be integer values.")
                st.stop()
            except Exception as exc:
                st.error(str(exc))
                st.stop()

        payload = st.session_state.get("ranking_payload")
        if not payload:
            st.info("Choose a discovery profile, optionally set overrides, and click **Run discovery ranking**.")
            st.markdown(
                "Recommended first smoke: `recent_artifact_ready` + `min_year=2025` + `Code artifact=True`."
            )
        else:
            results = render_ranking(payload)

            if results:
                st.markdown("---")
                st.subheader("Selected paper")

                options = [row.get("canonical_id") for row in results if row.get("canonical_id")]
                labels = {
                    row.get("canonical_id"): f"{idx}. {row.get('year', '—')} · {row.get('title', 'Untitled')[:100]}"
                    for idx, row in enumerate(results, start=1)
                    if row.get("canonical_id")
                }

                if st.session_state.get("selected_canonical_id") not in options:
                    st.session_state["selected_canonical_id"] = options[0]

                selected = st.selectbox(
                    "Open paper detail",
                    options,
                    format_func=lambda cid: labels.get(cid, cid),
                    key="selected_canonical_id",
                )

                if selected:
                    render_open_paper_workspace_button(
                        selected,
                        label="Open selected paper in Paper workspace",
                        key="open_selected_ranking_paper_workspace",
                    )

                if selected:
                    detail_tab, similar_tab, paper_cluster_tab, raw_tab = st.tabs(
                        ["Paper detail", "Similar papers", "Topic cluster", "Raw ranking"]
                    )

                    with detail_tab:
                        try:
                            with st.spinner("Loading paper detail..."):
                                detail_payload = fetch_paper_detail(api_base_url, selected)
                            render_paper_detail(detail_payload)
                        except Exception as exc:
                            st.error(str(exc))

                    with similar_tab:
                        render_similar_papers(api_base_url, selected)

                    with paper_cluster_tab:
                        render_selected_paper_topic_cluster(api_base_url, selected)

                    with raw_tab:
                        st.json(payload)
            else:
                with st.expander("Raw ranking response", expanded=False):
                    st.json(payload)

    with search_tab:
        render_search_tab(api_base_url)

    with paper_workspace_tab:
        render_paper_workspace(api_base_url)

    with citation_graph_diagnostics_tab:
        render_citation_graph_diagnostics_panel(api_base_url)

    with clusters_tab:
        render_topic_clusters(api_base_url)

    with topic_map_tab:
        render_topic_map(api_base_url)

    with artifacts_tab:
        render_artifact_explorer(api_base_url)


if __name__ == "__main__":
    main()
