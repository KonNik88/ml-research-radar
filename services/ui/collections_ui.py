from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from services.ui.workspace_client import WorkspaceClient, WorkspaceClientError


REQUEST_TIMEOUT_SECONDS = 30
COLLECTIONS_PAGE_LIMIT = 100

READING_STATUS_OPTIONS = ["to_read", "reading", "read"]
READING_STATUS_LABELS = {
    "to_read": "To read",
    "reading": "Reading",
    "read": "Read",
}

OpenPaperButton = Callable[..., None]
AddComparisonButton = Callable[..., None]


def init_collections_ui_state() -> None:
    defaults = {
        "collections_payload": None,
        "selected_collection_id": None,
        "selected_collection_detail_payload": None,
        "selected_collection_detail_id": None,
        "collections_flash": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _dash(value: Any) -> Any:
    return value if value not in (None, "", []) else "—"


def _normalize_authors(value: Any, *, limit: int = 8) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return str(value)

    authors: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            authors.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("name") or item.get("display_name")
            if name:
                authors.append(str(name).strip())
    if not authors:
        return "—"
    visible = authors[:limit]
    suffix = f" +{len(authors) - limit}" if len(authors) > limit else ""
    return ", ".join(visible) + suffix


def _markdown_link(label: str, url: Any) -> str:
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return "—"
    return f"[{label}]({url})"


def _client(base_url: str) -> WorkspaceClient:
    return WorkspaceClient(
        base_url,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
    )


def _collection_results(
    payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results") or []
    return [row for row in results if isinstance(row, dict)]


def _render_client_error(error: WorkspaceClientError) -> None:
    st.error(str(error))
    if error.error_code == "workspace_unavailable":
        st.info(
            "Search and Discovery remain available. Start PostgreSQL and apply the "
            "workspace Alembic migration before using Collections."
        )


def _load_collections_state(base_url: str) -> dict[str, Any]:
    payload = _client(base_url).list_collections(
        limit=COLLECTIONS_PAGE_LIMIT,
        offset=0,
    )
    st.session_state["collections_payload"] = payload

    results = _collection_results(payload)
    collection_ids = [str(row.get("collection_id")) for row in results]
    selected_id = st.session_state.get("selected_collection_id")

    if selected_id not in collection_ids:
        st.session_state["selected_collection_id"] = (
            collection_ids[0] if collection_ids else None
        )

    detail_id = st.session_state.get("selected_collection_detail_id")
    if detail_id not in collection_ids:
        st.session_state["selected_collection_detail_payload"] = None
        st.session_state["selected_collection_detail_id"] = None

    return payload


def _load_collection_detail_state(
    base_url: str,
    collection_id: str,
) -> dict[str, Any]:
    payload = _client(base_url).get_collection(collection_id)
    st.session_state["selected_collection_detail_payload"] = payload
    st.session_state["selected_collection_detail_id"] = collection_id
    return payload


def _refresh_collections_state(
    base_url: str,
    *,
    collection_id: str | None = None,
) -> None:
    payload = _load_collections_state(base_url)
    available_ids = {
        str(row.get("collection_id")) for row in _collection_results(payload)
    }
    target_id = collection_id or st.session_state.get("selected_collection_id")

    if target_id and target_id in available_ids:
        if st.session_state.get("selected_collection_id") != target_id:
            st.session_state["selected_collection_id"] = target_id
        _load_collection_detail_state(base_url, target_id)


def _set_flash(message: str, *, level: str = "success") -> None:
    st.session_state["collections_flash"] = {
        "message": message,
        "level": level,
    }


def _render_flash() -> None:
    flash = st.session_state.pop("collections_flash", None)
    if not isinstance(flash, dict):
        return

    message = str(flash.get("message") or "")
    level = str(flash.get("level") or "success")
    if not message:
        return
    if level == "warning":
        st.warning(message)
    elif level == "error":
        st.error(message)
    else:
        st.success(message)


def render_collection_membership_controls(
    base_url: str,
    canonical_id: str | None,
    *,
    key_prefix: str,
) -> None:
    """Render a reusable, on-demand save/remove control for one paper."""

    init_collections_ui_state()
    canonical_id = str(canonical_id or "").strip()
    if not canonical_id:
        return

    with st.popover("Save / remove"):
        st.caption("Manage this paper in a saved research collection.")
        payload = st.session_state.get("collections_payload")

        if payload is None:
            if st.button(
                "Load collections",
                key=f"{key_prefix}_load_collections",
                width="stretch",
            ):
                try:
                    payload = _load_collections_state(base_url)
                except WorkspaceClientError as exc:
                    _render_client_error(exc)

        results = _collection_results(payload)
        if payload is None:
            st.caption("Collections are loaded only on demand.")
            return
        if not results:
            st.info("Create a collection in the Collections tab first.")
            return

        collection_ids = [str(row.get("collection_id")) for row in results]
        labels = {
            str(row.get("collection_id")): (
                f"{row.get('name') or 'Untitled'} ({row.get('item_count', 0)})"
            )
            for row in results
        }
        select_key = f"{key_prefix}_target_collection"
        if st.session_state.get(select_key) not in collection_ids:
            st.session_state[select_key] = collection_ids[0]

        collection_id = st.selectbox(
            "Collection",
            collection_ids,
            format_func=lambda value: labels.get(value, value),
            key=select_key,
        )
        reading_status = st.selectbox(
            "Reading status",
            READING_STATUS_OPTIONS,
            format_func=lambda value: READING_STATUS_LABELS[value],
            key=f"{key_prefix}_reading_status",
        )
        confirm_remove = st.checkbox(
            "Confirm removal from the selected collection",
            key=f"{key_prefix}_confirm_remove_collection_item",
        )

        save_col, remove_col = st.columns(2)
        with save_col:
            if st.button(
                "Save / update",
                key=f"{key_prefix}_save_collection_item",
                type="primary",
                width="stretch",
            ):
                try:
                    _client(base_url).upsert_item(
                        collection_id,
                        canonical_id,
                        reading_status=reading_status,
                    )
                    _refresh_collections_state(
                        base_url,
                        collection_id=collection_id,
                    )
                    st.success("Paper saved to the selected collection.")
                except WorkspaceClientError as exc:
                    _render_client_error(exc)

        with remove_col:
            if st.button(
                "Remove",
                key=f"{key_prefix}_remove_collection_item",
                disabled=not confirm_remove,
                width="stretch",
            ):
                try:
                    _client(base_url).delete_item(
                        collection_id,
                        canonical_id,
                    )
                    _refresh_collections_state(
                        base_url,
                        collection_id=collection_id,
                    )
                    st.success("Paper removed from the selected collection.")
                except WorkspaceClientError as exc:
                    _render_client_error(exc)


def _item_table_row(item: dict[str, Any]) -> dict[str, Any]:
    paper = item.get("paper") if isinstance(item.get("paper"), dict) else {}
    return {
        "status": item.get("reading_status"),
        "year": paper.get("year"),
        "title": paper.get("title") or item.get("canonical_id"),
        "venue": paper.get("venue"),
        "note": item.get("note"),
        "orphaned": bool(item.get("orphaned")),
        "canonical_id": item.get("canonical_id"),
    }


def _render_item_editor(
    base_url: str,
    collection_id: str,
    item: dict[str, Any],
    *,
    rank: int,
    open_paper_button: OpenPaperButton,
    add_to_comparison_button: AddComparisonButton,
) -> None:
    canonical_id = str(item.get("canonical_id") or "").strip()
    if not canonical_id:
        return

    paper = item.get("paper") if isinstance(item.get("paper"), dict) else {}
    orphaned = bool(item.get("orphaned"))
    title = paper.get("title") or canonical_id
    current_status = str(item.get("reading_status") or "to_read")
    if current_status not in READING_STATUS_OPTIONS:
        current_status = "to_read"

    with st.expander(f"{rank}. {title}", expanded=False):
        if orphaned:
            st.warning(
                "This saved item is currently absent from the canonical corpus. "
                "Its note and reading status remain durable."
            )

        metadata_cols = st.columns(4)
        metadata_cols[0].metric("Status", READING_STATUS_LABELS[current_status])
        metadata_cols[1].metric("Year", _dash(paper.get("year")))
        metadata_cols[2].metric("Venue", _dash(paper.get("venue")))
        metadata_cols[3].metric("Orphan", "yes" if orphaned else "no")

        st.caption(f"Authors: {_normalize_authors(paper.get('authors'), limit=8)}")
        st.caption(f"Canonical ID: `{canonical_id}`")

        link_cols = st.columns(2)
        if paper.get("landing_page_url"):
            link_cols[0].markdown(
                _markdown_link("Landing page", paper.get("landing_page_url"))
            )
        if paper.get("pdf_url"):
            link_cols[1].markdown(_markdown_link("PDF", paper.get("pdf_url")))

        if not orphaned:
            open_paper_button(
                canonical_id,
                label="Open saved paper in Paper workspace",
                key=f"open_collection_item_{collection_id}_{canonical_id}",
            )
            add_to_comparison_button(
                canonical_id,
                label="Add saved paper to comparison",
                key=f"compare_collection_item_{collection_id}_{canonical_id}",
            )

        with st.form(f"collection_item_update_{collection_id}_{canonical_id}"):
            status = st.selectbox(
                "Reading status",
                READING_STATUS_OPTIONS,
                index=READING_STATUS_OPTIONS.index(current_status),
                format_func=lambda value: READING_STATUS_LABELS[value],
            )
            note = st.text_area(
                "Note",
                value=str(item.get("note") or ""),
                max_chars=20_000,
                placeholder=(
                    "Why this paper matters, what to verify, or what to read next..."
                ),
            )
            update_clicked = st.form_submit_button(
                "Update note and status",
                type="primary",
                width="stretch",
            )

        if update_clicked:
            try:
                _client(base_url).update_item(
                    collection_id,
                    canonical_id,
                    note=note.strip() or None,
                    reading_status=status,
                )
                _refresh_collections_state(
                    base_url,
                    collection_id=collection_id,
                )
                _set_flash("Saved paper note and reading status updated.")
                st.rerun()
            except WorkspaceClientError as exc:
                _render_client_error(exc)

        confirm_remove = st.checkbox(
            "Confirm removal (the saved note will also be deleted)",
            key=f"confirm_remove_collection_item_{collection_id}_{canonical_id}",
        )
        if st.button(
            "Remove from collection",
            key=f"remove_collection_item_{collection_id}_{canonical_id}",
            disabled=not confirm_remove,
            width="stretch",
        ):
            try:
                _client(base_url).delete_item(collection_id, canonical_id)
                _refresh_collections_state(
                    base_url,
                    collection_id=collection_id,
                )
                _set_flash("Paper removed from the collection.")
                st.rerun()
            except WorkspaceClientError as exc:
                _render_client_error(exc)


def render_collections_tab(
    base_url: str,
    *,
    open_paper_button: OpenPaperButton,
    add_to_comparison_button: AddComparisonButton,
) -> None:
    """Render the dedicated Saved Research Collections workspace."""

    init_collections_ui_state()
    if "collections_pending_selected_id" in st.session_state:
        st.session_state["selected_collection_id"] = st.session_state.pop(
            "collections_pending_selected_id"
        )

    st.subheader("Saved research collections")
    st.caption(
        "Durable single-user workspace for saved papers, notes, and reading status. "
        "Collections survive API/UI restarts and canonical corpus refreshes."
    )
    _render_flash()

    with st.expander("Create collection", expanded=False):
        with st.form("create_research_collection", clear_on_submit=True):
            name = st.text_input(
                "Collection name",
                max_chars=200,
                placeholder="RAG evaluation",
            )
            description = st.text_area(
                "Description (optional)",
                max_chars=2_000,
                placeholder="What belongs in this collection?",
            )
            create_clicked = st.form_submit_button(
                "Create collection",
                type="primary",
                width="stretch",
            )

        if create_clicked:
            if not name.strip():
                st.error("Collection name must not be blank.")
            else:
                try:
                    created = _client(base_url).create_collection(
                        name=name.strip(),
                        description=description.strip() or None,
                    )
                    collection_id = str(created.get("collection_id") or "")
                    st.session_state["selected_collection_id"] = collection_id
                    _refresh_collections_state(
                        base_url,
                        collection_id=collection_id,
                    )
                    _set_flash(
                        f"Collection created: {created.get('name', name)}"
                    )
                    st.rerun()
                except WorkspaceClientError as exc:
                    _render_client_error(exc)

    payload = st.session_state.get("collections_payload")
    load_label = "Refresh collections" if payload is not None else "Load collections"
    if st.button(load_label, key="load_saved_research_collections", width="stretch"):
        try:
            _refresh_collections_state(base_url)
            payload = st.session_state.get("collections_payload")
        except WorkspaceClientError as exc:
            _render_client_error(exc)

    if payload is None:
        st.info(
            "Collections are intentionally lazy-loaded so workspace availability "
            "cannot block Search, Discovery, or Paper Workspace."
        )
        return

    results = _collection_results(payload)
    summary_cols = st.columns(3)
    summary_cols[0].metric("Collections", payload.get("total", len(results)))
    summary_cols[1].metric(
        "Saved papers",
        sum(int(row.get("item_count") or 0) for row in results),
    )
    summary_cols[2].metric("Workspace mode", "PostgreSQL")

    if not results:
        st.info("No saved research collections yet. Create the first one above.")
        return

    collection_ids = [str(row.get("collection_id")) for row in results]
    labels = {
        str(row.get("collection_id")): (
            f"{row.get('name') or 'Untitled'} ({row.get('item_count', 0)} papers)"
        )
        for row in results
    }
    if st.session_state.get("selected_collection_id") not in collection_ids:
        st.session_state["selected_collection_id"] = collection_ids[0]

    selection_cols = st.columns([3, 1])
    with selection_cols[0]:
        selected_id = st.selectbox(
            "Selected collection",
            collection_ids,
            format_func=lambda value: labels.get(value, value),
            key="selected_collection_id",
        )
    with selection_cols[1]:
        open_clicked = st.button(
            "Open / refresh",
            key="open_selected_collection",
            width="stretch",
        )

    if open_clicked:
        try:
            _load_collection_detail_state(base_url, selected_id)
        except WorkspaceClientError as exc:
            _render_client_error(exc)

    detail = st.session_state.get("selected_collection_detail_payload")
    detail_id = st.session_state.get("selected_collection_detail_id")
    if not isinstance(detail, dict) or detail_id != selected_id:
        st.info("Click **Open / refresh** to load the selected collection.")
        return

    st.markdown("---")
    st.markdown(f"### {detail.get('name') or 'Untitled collection'}")
    if detail.get("description"):
        st.write(detail["description"])
    st.caption(
        f"Created: {_dash(detail.get('created_at'))} · "
        f"Updated: {_dash(detail.get('updated_at'))} · "
        f"ID: `{selected_id}`"
    )

    with st.expander("Edit collection", expanded=False):
        with st.form(f"edit_collection_{selected_id}"):
            edited_name = st.text_input(
                "Collection name",
                value=str(detail.get("name") or ""),
                max_chars=200,
            )
            edited_description = st.text_area(
                "Description",
                value=str(detail.get("description") or ""),
                max_chars=2_000,
            )
            edit_clicked = st.form_submit_button(
                "Save collection metadata",
                type="primary",
                width="stretch",
            )

        if edit_clicked:
            if not edited_name.strip():
                st.error("Collection name must not be blank.")
            else:
                try:
                    _client(base_url).update_collection(
                        selected_id,
                        name=edited_name.strip(),
                        description=edited_description.strip() or None,
                    )
                    _refresh_collections_state(
                        base_url,
                        collection_id=selected_id,
                    )
                    _set_flash("Collection metadata updated.")
                    st.rerun()
                except WorkspaceClientError as exc:
                    _render_client_error(exc)

    with st.expander("Delete collection", expanded=False):
        st.warning(
            "Deleting a collection also deletes its saved-paper memberships, "
            "notes, and reading statuses. Canonical papers are not modified."
        )
        confirm_delete = st.checkbox(
            "I understand and want to delete this collection",
            key=f"confirm_delete_collection_{selected_id}",
        )
        if st.button(
            "Delete selected collection",
            key=f"delete_collection_{selected_id}",
            disabled=not confirm_delete,
            width="stretch",
        ):
            try:
                _client(base_url).delete_collection(selected_id)
                remaining_payload = _client(base_url).list_collections(
                    limit=COLLECTIONS_PAGE_LIMIT,
                    offset=0,
                )
                st.session_state["collections_payload"] = remaining_payload
                remaining_results = _collection_results(remaining_payload)
                next_collection_id = (
                    str(remaining_results[0].get("collection_id"))
                    if remaining_results
                    else None
                )
                st.session_state["collections_pending_selected_id"] = (
                    next_collection_id
                )
                st.session_state["selected_collection_detail_payload"] = None
                st.session_state["selected_collection_detail_id"] = None
                _set_flash("Collection deleted.")
                st.rerun()
            except WorkspaceClientError as exc:
                _render_client_error(exc)

    items = [row for row in (detail.get("items") or []) if isinstance(row, dict)]
    st.markdown("#### Saved papers")
    if not items:
        st.info(
            "This collection is empty. Save papers from Discovery, Search, or "
            "Paper Workspace."
        )
        return

    status_filter = st.selectbox(
        "Reading status filter",
        ["all", *READING_STATUS_OPTIONS],
        format_func=lambda value: (
            "All statuses" if value == "all" else READING_STATUS_LABELS[value]
        ),
        key=f"collection_status_filter_{selected_id}",
    )
    filtered_items = [
        item
        for item in items
        if status_filter == "all" or item.get("reading_status") == status_filter
    ]

    if not filtered_items:
        st.info("No saved papers match the selected reading status.")
        return

    st.dataframe(
        pd.DataFrame([_item_table_row(item) for item in filtered_items]),
        hide_index=True,
        width="stretch",
    )

    for rank, item in enumerate(filtered_items, start=1):
        _render_item_editor(
            base_url,
            selected_id,
            item,
            rank=rank,
            open_paper_button=open_paper_button,
            add_to_comparison_button=add_to_comparison_button,
        )