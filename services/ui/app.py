from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

DEFAULT_API_BASE_URL = os.getenv("ML_RADAR_API_BASE_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT_SECONDS = 30
MAX_TOP_K = 100

RANKING_SORT_OPTIONS = [
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

SIMILAR_RANK_BY_OPTIONS = ["semantic", "radar_adjusted"]
TRI_STATE_OPTIONS = ["Profile default", "True", "False"]

st.set_page_config(
    page_title="ML Research Radar",
    page_icon="🔎",
    layout="wide",
)


# -----------------------------------------------------------------------------
# API client
# -----------------------------------------------------------------------------


def _clean_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


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


def _handle_response(response: requests.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    is_json = "application/json" in content_type.lower()

    payload: dict[str, Any]
    if is_json:
        raw_payload = response.json()
        payload = raw_payload if isinstance(raw_payload, dict) else {"detail": raw_payload}
    else:
        payload = {"message": response.text}

    if response.ok:
        return payload

    error_code = payload.get("error_code", f"http_{response.status_code}")
    message = payload.get("message")
    details = payload.get("details")

    # Some explicit FastAPI HTTPException responses use {"detail": "..."}.
    if not message and "detail" in payload:
        message = payload["detail"]

    if not message:
        message = "Request failed"

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


@st.cache_data(ttl=60, show_spinner=False)
def fetch_profiles(base_url: str) -> dict[str, Any]:
    return api_get(base_url, "/discovery/profiles")


@st.cache_data(ttl=30, show_spinner=False)
def fetch_ranking(base_url: str, profile_name: str, params: dict[str, Any]) -> dict[str, Any]:
    return api_get(base_url, f"/discovery/ranking/{profile_name}", params=params)


@st.cache_data(ttl=30, show_spinner=False)
def fetch_paper_detail(base_url: str, canonical_id: str) -> dict[str, Any]:
    return api_get(base_url, f"/discovery/papers/{canonical_id}")


@st.cache_data(ttl=30, show_spinner=False)
def fetch_similar_papers(base_url: str, canonical_id: str, params: dict[str, Any]) -> dict[str, Any]:
    return api_get(base_url, f"/discovery/papers/{canonical_id}/similar", params=params)


def clear_api_caches() -> None:
    fetch_health.clear()
    fetch_info.clear()
    fetch_runtime.clear()
    fetch_profiles.clear()
    fetch_ranking.clear()
    fetch_paper_detail.clear()
    fetch_similar_papers.clear()
    api_get.clear()
    api_post.clear()


def trigger_reload(base_url: str) -> dict[str, Any]:
    clear_api_caches()
    return api_post(base_url, "/reload")


# -----------------------------------------------------------------------------
# Small formatting helpers
# -----------------------------------------------------------------------------


def as_bool_param(value: str) -> bool | None:
    if value == "True":
        return True
    if value == "False":
        return False
    return None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_optional_int(raw: str, field_name: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} должен быть целым числом.") from exc


def fmt(value: Any, digits: int = 4) -> str:
    if value in (None, "", [], {}):
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def short_text(text: str | None, limit: int = 900) -> str:
    if not text:
        return "—"
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def render_kv(label: str, value: Any) -> None:
    st.markdown(f"**{label}:** {fmt(value)}")


def render_score_metric(column: Any, label: str, value: Any, digits: int = 3) -> None:
    if isinstance(value, (float, int)):
        column.metric(label, f"{float(value):.{digits}f}")
    else:
        column.metric(label, "—")


def render_badges(row: dict[str, Any]) -> None:
    badges: list[str] = []
    if row.get("has_code_artifact"):
        badges.append("💻 code")
    if row.get("has_dataset_artifact"):
        badges.append("🗂️ dataset")
    if row.get("has_model_artifact"):
        badges.append("🤗 model")
    if row.get("has_demo_artifact"):
        badges.append("🎬 demo")
    if row.get("github_found_repo_count"):
        badges.append(f"GitHub × {row.get('github_found_repo_count')}")
    if row.get("hf_found_count"):
        badges.append(f"HF × {row.get('hf_found_count')}")
    if row.get("source_families"):
        badges.extend([f"source:{source}" for source in row.get("source_families", [])[:3]])

    if badges:
        st.caption(" · ".join(badges))


# -----------------------------------------------------------------------------
# Sidebar/runtime
# -----------------------------------------------------------------------------


def render_sidebar(base_url: str) -> None:
    st.sidebar.title("ML Research Radar")
    st.sidebar.caption("Thin Streamlit client over FastAPI Discovery API")

    st.sidebar.markdown("### Connection")
    st.sidebar.code(base_url)

    col1, col2 = st.sidebar.columns(2)
    if col1.button("Refresh", width="stretch"):
        clear_api_caches()
        st.rerun()

    if col2.button("Reload", width="stretch"):
        try:
            with st.spinner("Reloading API runtime..."):
                payload = trigger_reload(base_url)
            st.sidebar.success(
                f"Reloaded {payload.get('build_id', 'unknown')} | reused={payload.get('model_reused')}"
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


# -----------------------------------------------------------------------------
# Discovery controls
# -----------------------------------------------------------------------------


def render_discovery_controls(base_url: str) -> tuple[str, dict[str, Any], bool]:
    profiles_payload = fetch_profiles(base_url)
    profiles = profiles_payload.get("profiles") or []
    if not profiles:
        st.error("Discovery profiles are empty. Проверь `/discovery/profiles`.")
        st.stop()

    profile_names = [profile.get("name") for profile in profiles if profile.get("name")]
    default_profile = profiles_payload.get("default_profile") or profile_names[0]
    default_index = profile_names.index(default_profile) if default_profile in profile_names else 0

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Discovery ranking")

    with st.sidebar.form("discovery_controls", clear_on_submit=False):
        profile_name = st.selectbox("Profile", profile_names, index=default_index)
        top_k = st.number_input("Top K", min_value=1, max_value=MAX_TOP_K, value=10, step=1)

        query_title = st.text_input("Title contains", value="", placeholder="speech, transformer, rag...")
        source_family = st.text_input("Source family", value="", placeholder="arxiv, acl_anthology...")

        year_col1, year_col2 = st.columns(2)
        with year_col1:
            min_year_raw = st.text_input("Min year", value="2025")
        with year_col2:
            max_year_raw = st.text_input("Max year", value="")

        st.markdown("#### Artifact/source filters")
        bool_cols = st.columns(2)
        with bool_cols[0]:
            has_code_raw = st.selectbox("has_code", TRI_STATE_OPTIONS, index=0)
            has_dataset_raw = st.selectbox("has_dataset", TRI_STATE_OPTIONS, index=0)
            has_model_raw = st.selectbox("has_model", TRI_STATE_OPTIONS, index=0)
            has_demo_raw = st.selectbox("has_demo", TRI_STATE_OPTIONS, index=0)
        with bool_cols[1]:
            has_github_raw = st.selectbox("has_github", TRI_STATE_OPTIONS, index=0)
            has_hf_raw = st.selectbox("has_hf", TRI_STATE_OPTIONS, index=0)
            has_acl_raw = st.selectbox("has_acl", TRI_STATE_OPTIONS, index=0)
            has_doi_raw = st.selectbox("has_doi", TRI_STATE_OPTIONS, index=0)

        st.markdown("#### Sorting")
        sort_by_choice = st.selectbox("Sort by", ["Profile default", *RANKING_SORT_OPTIONS], index=0)
        descending_choice = st.selectbox("Direction", ["Profile default", "Descending", "Ascending"], index=0)

        submitted = st.form_submit_button("Run discovery ranking", width="stretch")

    try:
        min_year = parse_optional_int(min_year_raw, "Min year")
        max_year = parse_optional_int(max_year_raw, "Max year")
    except ValueError as exc:
        st.sidebar.error(str(exc))
        st.stop()

    params: dict[str, Any] = {"top_k": int(top_k)}

    optional_values: dict[str, Any] = {
        "query_title": clean_text(query_title),
        "source_family": clean_text(source_family),
        "min_year": min_year,
        "max_year": max_year,
        "has_code": as_bool_param(has_code_raw),
        "has_dataset": as_bool_param(has_dataset_raw),
        "has_model": as_bool_param(has_model_raw),
        "has_demo": as_bool_param(has_demo_raw),
        "has_github": as_bool_param(has_github_raw),
        "has_hf": as_bool_param(has_hf_raw),
        "has_acl": as_bool_param(has_acl_raw),
        "has_doi": as_bool_param(has_doi_raw),
    }

    for key, value in optional_values.items():
        if value is not None:
            params[key] = value

    if sort_by_choice != "Profile default":
        params["sort_by"] = sort_by_choice

    if descending_choice == "Descending":
        params["descending"] = True
    elif descending_choice == "Ascending":
        params["descending"] = False

    return profile_name, params, submitted


# -----------------------------------------------------------------------------
# Ranking rendering
# -----------------------------------------------------------------------------


def ranking_rows_for_table(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(results, start=1):
        rows.append(
            {
                "rank": idx,
                "canonical_id": row.get("canonical_id"),
                "year": row.get("year"),
                "title": row.get("title"),
                "radar": row.get("radar_score"),
                "impl": row.get("implementation_readiness_score"),
                "artifacts": row.get("trusted_artifact_links_count"),
                "code": row.get("has_code_artifact"),
                "model": row.get("has_model_artifact"),
                "dataset": row.get("has_dataset_artifact"),
                "github": row.get("github_found_repo_count"),
                "hf": row.get("hf_found_count"),
            }
        )
    return rows


def render_ranking_summary(payload: dict[str, Any]) -> None:
    st.markdown("### Ranking summary")
    cols = st.columns(5)
    cols[0].metric("Input rows", payload.get("input_rows_count", 0))
    cols[1].metric("Filtered", payload.get("filtered_rows_count", 0))
    cols[2].metric("Returned", payload.get("returned_rows_count", 0))
    cols[3].metric("Sort by", payload.get("sort_by", "—"))
    cols[4].metric("Descending", str(payload.get("descending", True)))

    with st.expander("Profile and effective filters", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Base profile**")
            st.json(payload.get("profile", {}))
        with col2:
            st.markdown("**Effective filters**")
            st.json(payload.get("filters", {}))


def render_ranking_results(payload: dict[str, Any]) -> str | None:
    results = payload.get("results") or []
    if not results:
        st.warning("По выбранным discovery-фильтрам ничего не найдено.")
        return None

    st.markdown("### Ranking results")
    st.dataframe(ranking_rows_for_table(results), width="stretch", hide_index=True)

    labels = [
        f"{idx}. {row.get('title', 'Untitled')} ({row.get('year') or '—'}) — {row.get('canonical_id')}"
        for idx, row in enumerate(results, start=1)
    ]
    selected_label = st.selectbox("Select paper", labels, index=0)
    selected_idx = labels.index(selected_label)
    selected = results[selected_idx]
    selected_id = selected.get("canonical_id")

    st.markdown("### Selected paper")
    render_ranking_card(selected, selected_idx + 1)

    return selected_id


def render_ranking_card(row: dict[str, Any], rank: int) -> None:
    with st.container(border=True):
        st.markdown(f"#### {rank}. {row.get('title') or 'Untitled'}")
        render_badges(row)

        cols = st.columns(6)
        cols[0].metric("Year", fmt(row.get("year")))
        render_score_metric(cols[1], "Radar", row.get("radar_score"))
        render_score_metric(cols[2], "Impl", row.get("implementation_readiness_score"))
        render_score_metric(cols[3], "Source", row.get("source_confidence_score"))
        cols[4].metric("Artifacts", fmt(row.get("trusted_artifact_links_count")))
        cols[5].metric("Citations", fmt(row.get("citation_count")))

        st.caption(f"canonical_id: `{row.get('canonical_id')}`")


# -----------------------------------------------------------------------------
# Detail rendering
# -----------------------------------------------------------------------------


def render_link(label: str, url: str | None) -> None:
    if url:
        st.markdown(f"[{label}]({url})")


def render_paper_detail(detail_payload: dict[str, Any]) -> None:
    detail = detail_payload.get("detail") or {}
    if not detail or not detail.get("found"):
        st.warning("Paper detail not found.")
        return

    st.markdown("## Paper detail")
    st.markdown(f"### {detail.get('title') or 'Untitled'}")
    st.caption(f"canonical_id: `{detail.get('canonical_id') or detail_payload.get('canonical_id')}`")

    authors = detail.get("authors") or []
    if authors:
        st.markdown(f"**Authors:** {', '.join(authors[:20])}")

    meta_cols = st.columns(5)
    meta_cols[0].metric("Year", fmt(detail.get("year")))
    meta_cols[1].metric("Artifacts", fmt((detail.get("artifact_summary") or {}).get("artifact_detail_rows_count")))
    meta_cols[2].metric("Sources", fmt((detail.get("source_evidence") or {}).get("source_count")))
    meta_cols[3].metric("Canonical", str(detail.get("canonical_found")))
    meta_cols[4].metric("Features", str(detail.get("features_found")))

    scores = detail.get("scores") or {}
    if scores:
        st.markdown("#### Scores")
        score_cols = st.columns(5)
        render_score_metric(score_cols[0], "Radar", scores.get("radar_score"))
        render_score_metric(score_cols[1], "Impl readiness", scores.get("implementation_readiness_score"))
        render_score_metric(score_cols[2], "Source confidence", scores.get("source_confidence_score"))
        render_score_metric(score_cols[3], "Citation signal", scores.get("citation_signal_score"))
        render_score_metric(score_cols[4], "Recency", scores.get("recency_score"))

    links = detail.get("links") or {}
    identifiers = detail.get("identifiers") or {}
    if links or identifiers:
        with st.expander("Identifiers and links", expanded=False):
            if identifiers:
                st.markdown("**Identifiers**")
                st.json(identifiers)
            if links:
                st.markdown("**Links**")
                for key, value in links.items():
                    if isinstance(value, str) and value.startswith("http"):
                        render_link(key, value)
                    else:
                        render_kv(key, value)

    abstract = detail.get("abstract")
    if abstract:
        st.markdown("#### Abstract")
        st.write(short_text(abstract, limit=1800))

    render_artifacts(detail.get("artifacts") or [])

    with st.expander("Source evidence", expanded=False):
        st.json(detail.get("source_evidence") or {})

    with st.expander("Raw detail JSON", expanded=False):
        st.json(detail_payload)


def render_artifacts(artifacts: list[dict[str, Any]]) -> None:
    st.markdown("#### Artifacts")
    if not artifacts:
        st.info("Trusted artifacts are not attached to this paper.")
        return

    for idx, row in enumerate(artifacts, start=1):
        artifact = row.get("artifact") or row
        provider = artifact.get("provider") or row.get("provider") or "—"
        artifact_type = artifact.get("artifact_type") or row.get("artifact_type") or "—"
        relation_type = row.get("relation_type") or artifact.get("relation_type") or "—"
        url = artifact.get("normalized_url") or artifact.get("url") or artifact.get("external_url") or row.get("url")

        with st.container(border=True):
            st.markdown(f"**{idx}. {relation_type} · {provider} · {artifact_type}**")
            if url:
                st.markdown(f"[Open artifact]({url})")

            summary_cols = st.columns(4)
            summary_cols[0].metric("Confidence", fmt(row.get("confidence")))
            summary_cols[1].metric("Stars", fmt(artifact.get("stars") or row.get("stars")))
            summary_cols[2].metric("Forks", fmt(artifact.get("forks") or row.get("forks")))
            summary_cols[3].metric("License", fmt(artifact.get("license") or row.get("license")))

            github_metadata = row.get("github_metadata") or artifact.get("github_metadata")
            huggingface_metadata = row.get("huggingface_metadata") or artifact.get("huggingface_metadata")
            if github_metadata or huggingface_metadata:
                with st.expander("Provider metadata", expanded=False):
                    if github_metadata:
                        st.markdown("**GitHub**")
                        st.json(github_metadata)
                    if huggingface_metadata:
                        st.markdown("**Hugging Face**")
                        st.json(huggingface_metadata)


# -----------------------------------------------------------------------------
# Similar papers rendering
# -----------------------------------------------------------------------------


def render_similar_controls_and_results(base_url: str, canonical_id: str) -> None:
    st.markdown("## Similar papers")
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        top_k = st.number_input("Similar top K", min_value=1, max_value=50, value=10, step=1)
    with col2:
        rank_by = st.selectbox("Rank by", SIMILAR_RANK_BY_OPTIONS, index=0)
    with col3:
        min_similarity_raw = st.text_input("Min semantic similarity", value="", placeholder="optional, e.g. 0.65")

    params: dict[str, Any] = {"top_k": int(top_k), "rank_by": rank_by}
    if min_similarity_raw.strip():
        try:
            params["min_similarity"] = float(min_similarity_raw.strip())
        except ValueError:
            st.error("Min semantic similarity должен быть числом.")
            return

    try:
        with st.spinner("Loading similar papers..."):
            payload = fetch_similar_papers(base_url, canonical_id, params)
    except Exception as exc:
        st.error(str(exc))
        return

    results = payload.get("results") or []
    if not results:
        st.info("Similar papers not found.")
        return

    cols = st.columns(4)
    cols[0].metric("Returned", payload.get("returned_rows_count", len(results)))
    cols[1].metric("Rank by", payload.get("rank_by"))
    cols[2].metric("Input rows", payload.get("input_rows_count"))
    cols[3].metric("Embedding shape", fmt((payload.get("dense_artifacts") or {}).get("embedding_shape")))

    for idx, row in enumerate(results, start=1):
        with st.container(border=True):
            st.markdown(f"#### {idx}. {row.get('title') or 'Untitled'}")
            st.caption(f"canonical_id: `{row.get('canonical_id')}`")
            render_badges(row)
            sim_cols = st.columns(6)
            sim_cols[0].metric("Year", fmt(row.get("year")))
            render_score_metric(sim_cols[1], "Semantic", row.get("semantic_similarity"))
            render_score_metric(sim_cols[2], "Semantic norm", row.get("semantic_similarity_norm"))
            render_score_metric(sim_cols[3], "Adjusted", row.get("radar_adjusted_similarity"))
            render_score_metric(sim_cols[4], "Radar", row.get("radar_score"))
            render_score_metric(sim_cols[5], "Impl", row.get("implementation_readiness_score"))

    with st.expander("Raw similar JSON", expanded=False):
        st.json(payload)


# -----------------------------------------------------------------------------
# Main app
# -----------------------------------------------------------------------------


def render_landing() -> None:
    st.title("🔎 ML Research Radar")
    st.caption(
        "Research discovery UI over FastAPI: profiles → ranking → paper detail → similar papers."
    )
    st.info(
        "Запусти FastAPI отдельно, затем выбери профиль и фильтры слева. "
        "Streamlit здесь является тонким клиентом: бизнес-логика остаётся в API."
    )


def main() -> None:
    st.session_state.setdefault("api_base_url", DEFAULT_API_BASE_URL)
    st.session_state.setdefault("ranking_payload", None)
    st.session_state.setdefault("selected_canonical_id", None)

    with st.sidebar:
        api_base_url = st.text_input(
            "API base URL",
            value=st.session_state["api_base_url"],
            help="Например: http://127.0.0.1:8000",
        ).strip()
        st.session_state["api_base_url"] = api_base_url

    render_sidebar(api_base_url)
    render_landing()

    try:
        profile_name, ranking_params, submitted = render_discovery_controls(api_base_url)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    if submitted or st.session_state.get("ranking_payload") is None:
        try:
            with st.spinner("Loading discovery ranking..."):
                payload = fetch_ranking(api_base_url, profile_name, ranking_params)
            st.session_state["ranking_payload"] = payload
            results = payload.get("results") or []
            st.session_state["selected_canonical_id"] = (
                results[0].get("canonical_id") if results else None
            )
        except Exception as exc:
            st.error(str(exc))
            st.stop()

    ranking_payload = st.session_state.get("ranking_payload") or {}
    render_ranking_summary(ranking_payload)
    selected_id = render_ranking_results(ranking_payload)
    if selected_id:
        st.session_state["selected_canonical_id"] = selected_id

    canonical_id = st.session_state.get("selected_canonical_id")
    if not canonical_id:
        return

    try:
        with st.spinner("Loading paper detail..."):
            detail_payload = fetch_paper_detail(api_base_url, canonical_id)
    except Exception as exc:
        st.error(str(exc))
        return

    tab_detail, tab_similar, tab_raw = st.tabs(["Paper detail", "Similar papers", "Raw ranking"])
    with tab_detail:
        render_paper_detail(detail_payload)
    with tab_similar:
        render_similar_controls_and_results(api_base_url, canonical_id)
    with tab_raw:
        st.json(ranking_payload)


if __name__ == "__main__":
    main()
