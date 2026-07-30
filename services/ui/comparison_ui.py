from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Callable

import pandas as pd
import streamlit as st

from services.ui.comparison_client import ComparisonClient, ComparisonClientError


MIN_COMPARISON_PAPERS = 2
MAX_COMPARISON_PAPERS = 5
REQUEST_TIMEOUT_SECONDS = 30

COMPARISON_BASKET_KEY = "comparison_canonical_ids"
COMPARISON_PAYLOAD_KEY = "comparison_payload"
COMPARISON_PAYLOAD_IDS_KEY = "comparison_payload_canonical_ids"

OpenPaperButton = Callable[..., None]
CollectionControls = Callable[..., None]


def _state(
    state: MutableMapping[str, Any] | None,
) -> MutableMapping[str, Any]:
    return st.session_state if state is None else state


def _canonical_id(value: Any) -> str:
    return str(value or "").strip()


def _normalized_basket(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        canonical_id = _canonical_id(item)
        if not canonical_id or canonical_id in seen:
            continue
        result.append(canonical_id)
        seen.add(canonical_id)
        if len(result) == MAX_COMPARISON_PAPERS:
            break
    return result


def init_comparison_ui_state(
    state: MutableMapping[str, Any] | None = None,
) -> None:
    target = _state(state)
    target.setdefault(COMPARISON_BASKET_KEY, [])
    target.setdefault(COMPARISON_PAYLOAD_KEY, None)
    target.setdefault(COMPARISON_PAYLOAD_IDS_KEY, None)
    target.setdefault("comparison_manual_canonical_id", "")
    target[COMPARISON_BASKET_KEY] = _normalized_basket(
        target.get(COMPARISON_BASKET_KEY)
    )


def comparison_basket(
    state: MutableMapping[str, Any] | None = None,
) -> list[str]:
    target = _state(state)
    init_comparison_ui_state(target)
    return list(target[COMPARISON_BASKET_KEY])


def _invalidate_comparison_payload(
    state: MutableMapping[str, Any],
) -> None:
    state[COMPARISON_PAYLOAD_KEY] = None
    state[COMPARISON_PAYLOAD_IDS_KEY] = None


def add_to_comparison_basket(
    canonical_id: Any,
    *,
    state: MutableMapping[str, Any] | None = None,
) -> str:
    """Add one ID and return added/already_selected/full/invalid."""

    target = _state(state)
    init_comparison_ui_state(target)
    normalized = _canonical_id(canonical_id)
    if not normalized:
        return "invalid"

    basket = list(target[COMPARISON_BASKET_KEY])
    if normalized in basket:
        return "already_selected"
    if len(basket) >= MAX_COMPARISON_PAPERS:
        return "full"

    basket.append(normalized)
    target[COMPARISON_BASKET_KEY] = basket
    _invalidate_comparison_payload(target)
    return "added"


def remove_from_comparison_basket(
    canonical_id: Any,
    *,
    state: MutableMapping[str, Any] | None = None,
) -> bool:
    target = _state(state)
    init_comparison_ui_state(target)
    normalized = _canonical_id(canonical_id)
    basket = list(target[COMPARISON_BASKET_KEY])
    if normalized not in basket:
        return False

    target[COMPARISON_BASKET_KEY] = [
        value for value in basket if value != normalized
    ]
    _invalidate_comparison_payload(target)
    return True


def clear_comparison_basket(
    *,
    state: MutableMapping[str, Any] | None = None,
) -> bool:
    target = _state(state)
    init_comparison_ui_state(target)
    if not target[COMPARISON_BASKET_KEY]:
        return False

    target[COMPARISON_BASKET_KEY] = []
    _invalidate_comparison_payload(target)
    return True


def render_add_to_comparison_button(
    canonical_id: Any,
    *,
    key: str,
    label: str = "Add to comparison",
) -> None:
    init_comparison_ui_state()
    normalized = _canonical_id(canonical_id)
    basket = comparison_basket()
    selected = bool(normalized and normalized in basket)

    if st.button(
        "In comparison" if selected else label,
        key=key,
        disabled=not normalized or selected,
        width="stretch",
    ):
        status = add_to_comparison_basket(normalized)
        if status == "added":
            st.success(
                f"Added to comparison ({len(comparison_basket())}/"
                f"{MAX_COMPARISON_PAPERS})."
            )
        elif status == "full":
            st.warning(
                "Comparison basket already contains five papers. "
                "Remove one before adding another."
            )
        elif status == "already_selected":
            st.info("This paper is already in the comparison basket.")
        else:
            st.warning("Canonical ID is empty.")


def _dash(value: Any) -> Any:
    return "—" if value in (None, "", [], {}) else value


def _flag(value: Any) -> str:
    if value is None:
        return "unknown"
    return "yes" if value is True else "no" if value is False else str(value)


def _score(value: Any) -> Any:
    if value is None:
        return "—"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return value


def _strings(value: Any, *, limit: int | None = None) -> str:
    if not isinstance(value, list):
        return str(_dash(value))
    rows = [str(item) for item in value if item not in (None, "")]
    if limit is not None and len(rows) > limit:
        return ", ".join(rows[:limit]) + f" +{len(rows) - limit}"
    return ", ".join(rows) if rows else "—"


def _authors(value: Any) -> str:
    return _strings(value, limit=8)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _paper_label(
    canonical_id: Any,
    papers_by_id: dict[str, dict[str, Any]],
) -> str:
    normalized = _canonical_id(canonical_id)
    paper = papers_by_id.get(normalized, {})
    return str(paper.get("title") or normalized or "Unknown paper")


def metadata_score_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, paper in enumerate(payload.get("papers") or [], start=1):
        if not isinstance(paper, dict):
            continue
        scores = _as_dict(paper.get("scores"))
        provenance = _as_dict(paper.get("provenance"))
        rows.append(
            {
                "paper": index,
                "year": _dash(paper.get("year")),
                "title": _dash(paper.get("title")),
                "authors": _authors(paper.get("authors")),
                "venue": _dash(paper.get("venue")),
                "radar": _score(scores.get("radar_score")),
                "implementation": _score(
                    scores.get("implementation_readiness_score")
                ),
                "source confidence": _score(
                    scores.get("source_confidence_score")
                ),
                "citation signal": _score(
                    scores.get("citation_signal_score")
                ),
                "recency": _score(scores.get("recency_score")),
                "sources": _dash(provenance.get("source_count")),
                "canonical_id": paper.get("canonical_id"),
            }
        )
    return rows


def pairwise_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    papers_by_id = {
        str(row.get("canonical_id")): row
        for row in payload.get("papers") or []
        if isinstance(row, dict) and row.get("canonical_id")
    }
    rows: list[dict[str, Any]] = []
    for pair in payload.get("pairwise") or []:
        if not isinstance(pair, dict):
            continue
        semantic = _as_dict(pair.get("semantic"))
        rows.append(
            {
                "left": _paper_label(
                    pair.get("left_canonical_id"),
                    papers_by_id,
                ),
                "right": _paper_label(
                    pair.get("right_canonical_id"),
                    papers_by_id,
                ),
                "semantic similarity": (
                    _score(semantic.get("similarity"))
                    if semantic.get("available") is True
                    else "unavailable"
                ),
                "same cluster": _flag(pair.get("same_cluster")),
                "left references right": _flag(
                    pair.get("left_references_right")
                ),
                "right references left": _flag(
                    pair.get("right_references_left")
                ),
                "semantic caveat": _dash(semantic.get("reason")),
            }
        )
    return rows


def artifact_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for paper in payload.get("papers") or []:
        if not isinstance(paper, dict):
            continue
        evidence = _as_dict(paper.get("artifact_evidence"))
        github = _as_dict(evidence.get("github"))
        huggingface = _as_dict(evidence.get("huggingface"))
        rows.append(
            {
                "paper": _dash(paper.get("title")),
                "code": _flag(evidence.get("has_code_artifact")),
                "dataset": _flag(evidence.get("has_dataset_artifact")),
                "model": _flag(evidence.get("has_model_artifact")),
                "demo": _flag(evidence.get("has_demo_artifact")),
                "trusted links": _dash(
                    evidence.get("trusted_artifact_links_count")
                ),
                "GitHub repos": _dash(github.get("github_repo_count")),
                "GitHub stars max": _dash(github.get("github_stars_max")),
                "HF models": _dash(huggingface.get("hf_model_count")),
                "HF datasets": _dash(huggingface.get("hf_dataset_count")),
                "artifact types": _strings(evidence.get("artifact_types")),
            }
        )
    return rows


def citation_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for paper in payload.get("papers") or []:
        if not isinstance(paper, dict):
            continue
        evidence = _as_dict(paper.get("citation_evidence"))
        graph = _as_dict(evidence.get("graph"))
        rows.append(
            {
                "paper": _dash(paper.get("title")),
                "canonical cited by": _dash(
                    evidence.get("canonical_cited_by_count")
                ),
                "canonical references": _dash(
                    evidence.get("canonical_references_count")
                ),
                "feature citations": _dash(
                    evidence.get("feature_citation_count")
                ),
                "graph status": _dash(graph.get("status")),
                "outgoing": _dash(graph.get("outgoing_reference_count")),
                "resolved outgoing": _dash(
                    graph.get("outgoing_resolved_reference_count")
                ),
                "external outgoing": _dash(
                    graph.get("outgoing_external_reference_count")
                ),
                "incoming": _dash(graph.get("incoming_citation_count")),
            }
        )
    return rows


def cluster_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for paper in payload.get("papers") or []:
        if not isinstance(paper, dict):
            continue
        cluster = _as_dict(paper.get("cluster"))
        rows.append(
            {
                "paper": _dash(paper.get("title")),
                "status": _dash(cluster.get("status")),
                "cluster": _dash(cluster.get("cluster_id")),
                "rank": _dash(cluster.get("rank_within_cluster")),
                "centroid similarity": _score(
                    cluster.get("similarity_to_centroid")
                ),
                "labels": _strings(cluster.get("label_candidates")),
            }
        )
    return rows


def _render_shared_and_pairwise_dimensions(payload: dict[str, Any]) -> None:
    st.markdown("### Taxonomy, sources, and artifact differences")
    summary = _as_dict(payload.get("summary"))
    shared_by_all = _as_dict(summary.get("shared_by_all"))
    dimensions = [
        "categories",
        "concepts",
        "keywords",
        "source_families",
        "artifact_types",
    ]
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "dimension": dimension,
                    "shared by all": _strings(shared_by_all.get(dimension)),
                }
                for dimension in dimensions
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    for index, pair in enumerate(payload.get("pairwise") or [], start=1):
        if not isinstance(pair, dict):
            continue
        left_id = pair.get("left_canonical_id")
        right_id = pair.get("right_canonical_id")
        with st.expander(
            f"Pair {index}: {_canonical_id(left_id)} ↔ "
            f"{_canonical_id(right_id)}",
            expanded=False,
        ):
            pair_dimensions = _as_dict(pair.get("dimensions"))
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "dimension": dimension,
                            "shared": _strings(
                                _as_dict(
                                    pair_dimensions.get(dimension)
                                ).get("shared")
                            ),
                            "left only": _strings(
                                _as_dict(
                                    pair_dimensions.get(dimension)
                                ).get("left_only")
                            ),
                            "right only": _strings(
                                _as_dict(
                                    pair_dimensions.get(dimension)
                                ).get("right_only")
                            ),
                        }
                        for dimension in dimensions
                    ]
                ),
                hide_index=True,
                width="stretch",
            )


def _render_paper_abstracts_and_actions(
    base_url: str,
    payload: dict[str, Any],
    *,
    open_paper_button: OpenPaperButton,
    collection_controls: CollectionControls,
) -> None:
    st.markdown("### Papers, abstracts, and actions")
    for index, paper in enumerate(payload.get("papers") or [], start=1):
        if not isinstance(paper, dict):
            continue
        canonical_id = _canonical_id(paper.get("canonical_id"))
        title = str(paper.get("title") or canonical_id or "Untitled")
        with st.expander(f"{index}. {title}", expanded=False):
            st.caption(f"Authors: {_authors(paper.get('authors'))}")
            st.caption(f"Canonical ID: `{canonical_id}`")
            abstract = paper.get("abstract")
            if abstract:
                st.write(abstract)
            else:
                st.info("Abstract is unavailable.")

            action_cols = st.columns(2)
            with action_cols[0]:
                open_paper_button(
                    canonical_id,
                    label="Open compared paper in Paper workspace",
                    key=f"open_compared_paper_{index}_{canonical_id}",
                )
            with action_cols[1]:
                collection_controls(
                    base_url,
                    canonical_id,
                    key_prefix=f"comparison_collection_{index}_{canonical_id}",
                )


def render_comparison_payload(
    base_url: str,
    payload: dict[str, Any],
    *,
    open_paper_button: OpenPaperButton,
    collection_controls: CollectionControls,
) -> None:
    st.markdown("---")
    st.subheader("Comparison result")

    header_cols = st.columns(4)
    header_cols[0].metric("Papers", payload.get("paper_count", "—"))
    header_cols[1].metric("Pairs", len(payload.get("pairwise") or []))
    header_cols[2].metric(
        "Schema",
        payload.get("schema_version", "—"),
    )
    header_cols[3].metric(
        "Input order",
        "preserved" if payload.get("input_order_preserved") is True else "unknown",
    )

    for warning in payload.get("warnings") or []:
        st.warning(str(warning))

    st.markdown("### Metadata and Radar scores")
    st.dataframe(
        pd.DataFrame(metadata_score_rows(payload)),
        hide_index=True,
        width="stretch",
    )

    st.markdown("### Pairwise semantic and graph evidence")
    st.caption(
        "Unknown graph relationships are shown as unknown, not as false. "
        "Similarity is exact for the active file-first dense build when available."
    )
    st.dataframe(
        pd.DataFrame(pairwise_rows(payload)),
        hide_index=True,
        width="stretch",
    )

    _render_shared_and_pairwise_dimensions(payload)

    st.markdown("### Artifact and implementation evidence")
    st.dataframe(
        pd.DataFrame(artifact_rows(payload)),
        hide_index=True,
        width="stretch",
    )

    st.markdown("### Citation and reference evidence")
    st.caption(
        "Citation/reference graph evidence is bounded, snapshot-dependent, and "
        "not a publication-grade global citation ranking."
    )
    st.dataframe(
        pd.DataFrame(citation_rows(payload)),
        hide_index=True,
        width="stretch",
    )

    st.markdown("### Topic-cluster context")
    st.dataframe(
        pd.DataFrame(cluster_rows(payload)),
        hide_index=True,
        width="stretch",
    )

    _render_paper_abstracts_and_actions(
        base_url,
        payload,
        open_paper_button=open_paper_button,
        collection_controls=collection_controls,
    )

    with st.expander("Comparison capabilities", expanded=False):
        st.json(payload.get("capabilities") or {})
    with st.expander("Raw comparison response", expanded=False):
        st.json(payload)


def _render_add_status(status: str) -> None:
    if status == "added":
        st.success(
            f"Paper added ({len(comparison_basket())}/"
            f"{MAX_COMPARISON_PAPERS})."
        )
    elif status == "already_selected":
        st.info("This paper is already in the comparison basket.")
    elif status == "full":
        st.warning(
            "Comparison basket already contains five papers. "
            "Remove one before adding another."
        )
    else:
        st.warning("Canonical ID is empty.")


def render_comparison_tab(
    base_url: str,
    *,
    open_paper_button: OpenPaperButton,
    collection_controls: CollectionControls,
) -> None:
    init_comparison_ui_state()
    st.subheader("Paper comparison workspace")
    st.caption(
        "Compare two to five canonical papers through one deterministic batch "
        "request. The basket is temporary; Saved Research Collections remain "
        "the durable workspace."
    )

    manual_cols = st.columns([4, 1])
    with manual_cols[0]:
        manual_id = st.text_input(
            "Add canonical ID manually",
            key="comparison_manual_canonical_id",
            placeholder="Paste canonical_id here.",
        )
    with manual_cols[1]:
        if st.button(
            "Add canonical ID",
            key="comparison_add_manual_id",
            width="stretch",
        ):
            _render_add_status(add_to_comparison_basket(manual_id))

    basket = comparison_basket()
    summary_cols = st.columns([1, 3, 1])
    summary_cols[0].metric(
        "Basket",
        f"{len(basket)}/{MAX_COMPARISON_PAPERS}",
    )
    summary_cols[1].caption(
        "Request order is preserved. Duplicate additions are idempotent."
    )
    if summary_cols[2].button(
        "Clear all",
        key="comparison_clear_all",
        disabled=not basket,
        width="stretch",
    ):
        clear_comparison_basket()
        st.rerun()

    if not basket:
        st.info(
            "Add papers from Search, Discovery ranking, Paper workspace, "
            "Collections, or by canonical ID."
        )
    else:
        for index, canonical_id in enumerate(basket, start=1):
            row_cols = st.columns([0.4, 4, 1])
            row_cols[0].markdown(f"**{index}.**")
            row_cols[1].code(canonical_id)
            if row_cols[2].button(
                "Remove",
                key=f"comparison_remove_{index}_{canonical_id}",
                width="stretch",
            ):
                remove_from_comparison_basket(canonical_id)
                st.rerun()

    compare_disabled = len(basket) < MIN_COMPARISON_PAPERS
    if st.button(
        "Compare selected papers",
        key="comparison_run_batch",
        type="primary",
        disabled=compare_disabled,
        width="stretch",
    ):
        try:
            with st.spinner("Building deterministic paper comparison..."):
                payload = ComparisonClient(
                    base_url,
                    timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                ).compare_papers(basket)
            st.session_state[COMPARISON_PAYLOAD_KEY] = payload
            st.session_state[COMPARISON_PAYLOAD_IDS_KEY] = list(basket)
        except ComparisonClientError as exc:
            st.error(str(exc))

    if compare_disabled:
        st.caption("Select at least two papers to enable Compare.")

    payload = st.session_state.get(COMPARISON_PAYLOAD_KEY)
    payload_ids = st.session_state.get(COMPARISON_PAYLOAD_IDS_KEY)
    if payload and payload_ids == basket:
        render_comparison_payload(
            base_url,
            payload,
            open_paper_button=open_paper_button,
            collection_controls=collection_controls,
        )
    elif len(basket) >= MIN_COMPARISON_PAPERS:
        st.info("Click **Compare selected papers** to load one batch response.")
