from __future__ import annotations

import os
from typing import Any, Iterable

import pandas as pd
import requests
import streamlit as st

DEFAULT_API_BASE_URL = os.getenv("ML_RADAR_API_BASE_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT_SECONDS = 30
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


@st.cache_data(ttl=10, show_spinner=False)
def api_get(base_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{_clean_base_url(base_url)}{path}"
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    return _handle_response(response)


@st.cache_data(ttl=5, show_spinner=False)
def api_post(base_url: str, path: str) -> dict[str, Any]:
    url = f"{_clean_base_url(base_url)}{path}"
    response = requests.post(url, timeout=REQUEST_TIMEOUT_SECONDS)
    return _handle_response(response)


@st.cache_data(ttl=10, show_spinner=False)
def fetch_health(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/health")


@st.cache_data(ttl=10, show_spinner=False)
def fetch_info(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/info")


@st.cache_data(ttl=10, show_spinner=False)
def fetch_runtime(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/runtime")


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


def clear_api_caches() -> None:
    api_get.clear()
    api_post.clear()
    fetch_health.clear()
    fetch_info.clear()
    fetch_runtime.clear()
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
        "ranking_payload": None,
        "selected_canonical_id": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    for key in BOOL_FILTER_KEYS:
        st.session_state.setdefault(key, "Profile default")


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


def get_profiles_or_stop(base_url: str) -> dict[str, Any]:
    try:
        return fetch_profiles(base_url)
    except Exception as exc:
        st.error(f"Failed to load discovery profiles: {exc}")
        st.stop()


# --------------------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------------------


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

    for row in results:
        with st.container(border=True):
            st.markdown(f"### {row.get('rank')}. {row.get('title', 'Untitled')}")
            render_badges(row)
            metric_cols = st.columns(5)
            metric_cols[0].metric("Year", dash(row.get("year")))
            metric_cols[1].metric("Semantic", fmt_score(row.get("semantic_similarity"), 4))
            metric_cols[2].metric("Adjusted", fmt_score(row.get("radar_adjusted_similarity"), 4))
            metric_cols[3].metric("Radar", fmt_score(row.get("radar_score")))
            metric_cols[4].metric("Impl", fmt_score(row.get("implementation_readiness_score")))
            st.caption(f"ID: `{compact_id(row.get('canonical_id'))}`")

    with st.expander("Raw similar response", expanded=False):
        st.json(payload)


# --------------------------------------------------------------------------------------
# Main app
# --------------------------------------------------------------------------------------


def main() -> None:
    init_ui_state()

    base_url = st.session_state["api_base_url"]
    profiles_payload = get_profiles_or_stop(base_url)
    render_header(profiles_payload)

    api_base_url, run_clicked = render_sidebar(base_url, profiles_payload)

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
        return

    results = render_ranking(payload)
    if not results:
        with st.expander("Raw ranking response", expanded=False):
            st.json(payload)
        return

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

    if not selected:
        st.warning("No selected paper.")
        return

    detail_tab, similar_tab, raw_tab = st.tabs(["Paper detail", "Similar papers", "Raw ranking"])

    with detail_tab:
        try:
            with st.spinner("Loading paper detail..."):
                detail_payload = fetch_paper_detail(api_base_url, selected)
            render_paper_detail(detail_payload)
        except Exception as exc:
            st.error(str(exc))

    with similar_tab:
        render_similar_papers(api_base_url, selected)

    with raw_tab:
        st.json(payload)


if __name__ == "__main__":
    main()
