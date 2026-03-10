from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

DEFAULT_API_BASE_URL = os.getenv("ML_RADAR_API_BASE_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT_SECONDS = 30
MODE_OPTIONS = ["lexical", "dense", "hybrid"]
SORT_OPTIONS = ["relevance", "year_desc", "year_asc"]
MAX_TOP_K = 100

st.set_page_config(
    page_title="ML Research Radar",
    page_icon="🔎",
    layout="wide",
)


@st.cache_data(ttl=10, show_spinner=False)
def api_get(base_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    return _handle_response(response)


@st.cache_data(ttl=5, show_spinner=False)
def api_post(base_url: str, path: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    response = requests.post(url, timeout=REQUEST_TIMEOUT_SECONDS)
    return _handle_response(response)


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
def fetch_health(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/health")


@st.cache_data(ttl=10, show_spinner=False)
def fetch_info(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/info")


@st.cache_data(ttl=10, show_spinner=False)
def fetch_runtime(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/runtime")


def trigger_reload(base_url: str) -> dict[str, Any]:
    fetch_health.clear()
    fetch_info.clear()
    fetch_runtime.clear()
    api_get.clear()
    return api_post(base_url, "/reload")


def run_search(
    *,
    base_url: str,
    query: str,
    mode: str,
    top_k: int,
    rank: bool,
    year_from: int | None,
    year_to: int | None,
    category: str | None,
    source: str | None,
    offset: int,
    sort_by: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "query": query,
        "mode": mode,
        "top_k": top_k,
        "rank": str(rank).lower(),
        "offset": offset,
        "sort_by": sort_by,
    }

    if year_from is not None:
        params["year_from"] = year_from
    if year_to is not None:
        params["year_to"] = year_to
    if category:
        params["category"] = category
    if source:
        params["source"] = source

    return api_get(base_url, "/search", params=params)


def render_kv(label: str, value: Any) -> None:
    pretty = value if value not in (None, "", [], {}) else "—"
    st.markdown(f"**{label}:** {pretty}")


def render_sidebar(base_url: str) -> None:
    st.sidebar.title("ML Research Radar")
    st.sidebar.caption("Thin Streamlit client over FastAPI")

    st.sidebar.markdown("### Connection")
    st.sidebar.code(base_url)

    refresh = st.sidebar.button("Refresh runtime info", use_container_width=True)
    if refresh:
        fetch_health.clear()
        fetch_info.clear()
        fetch_runtime.clear()
        st.rerun()

    reload_clicked = st.sidebar.button("Reload API runtime", use_container_width=True)
    if reload_clicked:
        try:
            with st.spinner("Reloading runtime..."):
                payload = trigger_reload(base_url)
            st.sidebar.success(
                f"Reloaded build {payload.get('build_id', 'unknown')} | model reused={payload.get('model_reused')}"
            )
        except Exception as exc:
            st.sidebar.error(str(exc))

    st.sidebar.markdown("---")
    st.sidebar.markdown("### API status")

    try:
        health = fetch_health(base_url)
        info = fetch_info(base_url)
        runtime = fetch_runtime(base_url)

        st.sidebar.success("API is reachable")
        render_kv("Status", health.get("status"))
        render_kv("Build ID", health.get("build_id"))
        render_kv("Corpus docs", health.get("corpus_doc_count"))
        render_kv("Embedding model", health.get("embedding_model_name"))
        render_kv("API version", info.get("api_version"))
        render_kv("Artifacts root", info.get("artifacts_root"))

        st.sidebar.markdown("### Runtime")
        render_kv("Ready", runtime.get("ready"))
        render_kv("Last loaded", runtime.get("last_loaded_at"))
        render_kv("Last reload", runtime.get("last_reload_at"))
        render_kv("Model reused", runtime.get("model_reused"))

        with st.sidebar.expander("Loaded components", expanded=False):
            st.json(runtime.get("loaded_components", {}))

        if runtime.get("last_load_error"):
            st.sidebar.error(runtime["last_load_error"])
    except Exception as exc:
        st.sidebar.error(f"API unavailable: {exc}")


def render_search_controls() -> tuple[
    str, str, int, bool, int | None, int | None, str | None, str | None, int, str, bool
]:
    st.title("🔎 ML Research Radar")
    st.caption("Поиск ML-статей через FastAPI backend: lexical, dense и hybrid retrieval.")

    with st.form("search_form", clear_on_submit=False):
        query = st.text_input(
            "Search query",
            value=st.session_state.get("last_query", "graph neural networks"),
            placeholder="Например: retrieval augmented generation for scientific literature",
        )

        row1_col1, row1_col2, row1_col3 = st.columns(3)
        with row1_col1:
            mode = st.selectbox("Mode", MODE_OPTIONS, index=2)
        with row1_col2:
            top_k = st.number_input("Top K", min_value=1, max_value=MAX_TOP_K, value=10, step=1)
        with row1_col3:
            rank = st.checkbox("Apply ranking", value=True)

        row2_col1, row2_col2, row2_col3 = st.columns(3)
        with row2_col1:
            year_from_raw = st.text_input("Year from", value="")
        with row2_col2:
            year_to_raw = st.text_input("Year to", value="")
        with row2_col3:
            sort_by = st.selectbox("Sort by", SORT_OPTIONS, index=0)

        row3_col1, row3_col2, row3_col3 = st.columns(3)
        with row3_col1:
            category = st.text_input("Category", value="", placeholder="Например: cs.LG")
        with row3_col2:
            source = st.text_input("Source", value="", placeholder="Например: arxiv")
        with row3_col3:
            offset = st.number_input("Offset", min_value=0, max_value=10000, value=0, step=1)

        submitted = st.form_submit_button("Search", use_container_width=True)

    year_from = int(year_from_raw) if year_from_raw.strip() else None
    year_to = int(year_to_raw) if year_to_raw.strip() else None
    category = category.strip() or None
    source = source.strip() or None

    return (
        query,
        mode,
        int(top_k),
        rank,
        year_from,
        year_to,
        category,
        source,
        int(offset),
        sort_by,
        submitted,
    )


def render_meta(meta: dict[str, Any] | None) -> None:
    if not meta:
        st.info("Debug meta отсутствует в ответе API.")
        return

    st.markdown("### Search meta")

    row1 = st.columns(4)
    row1[0].metric("Build ID", meta.get("build_id", "—"))
    row1[1].metric("Result count", meta.get("result_count", 0))
    row1[2].metric("Returned count", meta.get("returned_count", 0))
    row1[3].metric("Rank applied", str(meta.get("rank_applied", False)))

    row2 = st.columns(4)
    row2[0].metric("Offset", meta.get("offset", 0))
    row2[1].metric("Sort by", meta.get("sort_by", "—"))
    row2[2].metric(
        "Retrieved before filters",
        meta.get("retrieved_candidates_before_filters", "—"),
    )
    row2[3].metric(
        "Retrieved after filters",
        meta.get("retrieved_candidates_after_filters", "—"),
    )

    applied_filters = meta.get("applied_filters")
    if applied_filters:
        with st.expander("Applied filters", expanded=False):
            st.json(applied_filters)

    timing = meta.get("timing_ms", {}) or {}
    if timing:
        st.markdown("#### Timing (ms)")
        keys = list(timing.keys())
        timing_cols = st.columns(min(4, max(1, len(keys))))
        for idx, (key, value) in enumerate(timing.items()):
            timing_cols[idx % len(timing_cols)].metric(key, value)

        with st.expander("Timing JSON", expanded=False):
            st.json(timing)


def render_document(item: dict[str, Any], index: int) -> None:
    document = item.get("document", {})
    retrieval = item.get("retrieval", {}) or {}
    ranking = item.get("ranking")

    title = document.get("title") or "Untitled"
    year = document.get("year")
    authors = document.get("authors") or []
    doi = document.get("doi")
    categories = document.get("categories") or []
    primary_category = document.get("primary_category")
    tags = document.get("tags") or []
    source_count = document.get("source_count", 0)
    abstract = document.get("abstract") or ""
    canonical_id = document.get("canonical_id")

    with st.container(border=True):
        st.markdown(f"### {index}. {title}")

        meta_cols = st.columns([2, 1, 1, 1])
        meta_cols[0].markdown(f"**Authors:** {', '.join(authors) if authors else '—'}")
        meta_cols[1].markdown(f"**Year:** {year if year is not None else '—'}")
        meta_cols[2].markdown(f"**Sources:** {source_count}")
        meta_cols[3].markdown(f"**ID:** {canonical_id or '—'}")

        if doi:
            st.markdown(f"**DOI:** `{doi}`")
        else:
            st.markdown("**DOI:** —")

        if primary_category:
            st.markdown(f"**Primary category:** {primary_category}")
        if categories:
            st.markdown(f"**Categories:** {', '.join(categories[:8])}")
        if tags:
            st.markdown(f"**Tags:** {', '.join(tags[:8])}")

        if abstract:
            preview = abstract if len(abstract) <= 1200 else abstract[:1200].rstrip() + "..."
            st.markdown("**Abstract preview**")
            st.write(preview)
        else:
            st.markdown("**Abstract preview:** —")

        score_cols = st.columns(4)
        score_cols[0].metric("score", retrieval.get("score"))
        score_cols[1].metric("lexical_score", retrieval.get("lexical_score"))
        score_cols[2].metric("dense_score", retrieval.get("dense_score"))
        score_cols[3].metric("hybrid_score", retrieval.get("hybrid_score"))

        if ranking:
            st.markdown("#### Ranking breakdown")
            rank_cols = st.columns(5)
            rank_cols[0].metric("final_score", ranking.get("final_score"))
            rank_cols[1].metric("retrieval_score", ranking.get("retrieval_score"))
            rank_cols[2].metric("recency_score", ranking.get("recency_score"))
            rank_cols[3].metric("source_support_score", ranking.get("source_support_score"))
            rank_cols[4].metric("metadata_quality_score", ranking.get("metadata_quality_score"))

            with st.expander("Ranking JSON", expanded=False):
                st.json(ranking)


def render_results(payload: dict[str, Any]) -> None:
    st.markdown("---")
    st.subheader("Results")

    info_cols = st.columns(5)
    info_cols[0].metric("Mode", payload.get("mode", "—"))
    info_cols[1].metric("Top K", payload.get("top_k", 0))
    info_cols[2].metric("Rank applied", str(payload.get("rank_applied", False)))
    info_cols[3].metric("Build ID", payload.get("build_id", "—"))
    info_cols[4].metric("Returned", len(payload.get("results", [])))

    render_meta(payload.get("meta"))

    results = payload.get("results", []) or []
    if not results:
        st.warning("Ничего не найдено.")
        return

    for index, item in enumerate(results, start=1):
        render_document(item, index)

    with st.expander("Raw response JSON", expanded=False):
        st.json(payload)


def main() -> None:
    st.session_state.setdefault("api_base_url", DEFAULT_API_BASE_URL)

    with st.sidebar:
        api_base_url = st.text_input(
            "API base URL",
            value=st.session_state["api_base_url"],
            help="Например: http://127.0.0.1:8000",
        ).strip()
        st.session_state["api_base_url"] = api_base_url

    render_sidebar(api_base_url)

    try:
        (
            query,
            mode,
            top_k,
            rank,
            year_from,
            year_to,
            category,
            source,
            offset,
            sort_by,
            submitted,
        ) = render_search_controls()
    except ValueError:
        st.error("Year from / Year to должны быть целыми числами.")
        st.stop()

    if submitted:
        st.session_state["last_query"] = query
        try:
            with st.spinner("Searching..."):
                payload = run_search(
                    base_url=api_base_url,
                    query=query,
                    mode=mode,
                    top_k=top_k,
                    rank=rank,
                    year_from=year_from,
                    year_to=year_to,
                    category=category,
                    source=source,
                    offset=offset,
                    sort_by=sort_by,
                )
            render_results(payload)
        except Exception as exc:
            st.error(str(exc))
            st.stop()
    else:
        st.info("Введите запрос, при необходимости задайте фильтры и нажмите Search.")


if __name__ == "__main__":
    main()