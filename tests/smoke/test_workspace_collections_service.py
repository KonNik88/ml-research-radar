from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from services.api.workspace.errors import (
    CollectionItemNotFoundError,
    PaperNotFoundError,
)
from services.api.workspace.schemas import (
    CollectionItemUpdateRequest,
    CollectionUpdateRequest,
)
from services.api.workspace.service import WorkspaceService
from services.api.workspace.store import WorkspacePostgresConfig


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryWorkspaceStore:
    def __init__(self) -> None:
        self.collections: dict[UUID, dict[str, Any]] = {}
        self.items: dict[tuple[UUID, str], dict[str, Any]] = {}
        self.touch_count = 0

    def create_collection(
        self,
        *,
        collection_id: UUID,
        name: str,
        description: str | None,
    ) -> dict[str, Any]:
        timestamp = _now()
        row = {
            "collection_id": collection_id,
            "name": name,
            "description": description,
            "created_at": timestamp,
            "updated_at": timestamp,
            "item_count": 0,
        }
        self.collections[collection_id] = row
        return dict(row)

    def list_collections(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        rows = list(self.collections.values())
        return [dict(row) for row in rows[offset : offset + limit]]

    def count_collections(self) -> int:
        return len(self.collections)

    def get_collection(
        self,
        collection_id: UUID,
    ) -> dict[str, Any] | None:
        row = self.collections.get(collection_id)
        if row is None:
            return None
        out = dict(row)
        out["item_count"] = sum(key[0] == collection_id for key in self.items)
        return out

    def update_collection(
        self,
        collection_id: UUID,
        *,
        name: str | None,
        name_supplied: bool,
        description: str | None,
        description_supplied: bool,
    ) -> dict[str, Any] | None:
        row = self.collections.get(collection_id)
        if row is None:
            return None
        if name_supplied:
            row["name"] = name
        if description_supplied:
            row["description"] = description
        row["updated_at"] = _now()
        return self.get_collection(collection_id)

    def delete_collection(self, collection_id: UUID) -> bool:
        if collection_id not in self.collections:
            return False
        del self.collections[collection_id]
        self.items = {
            key: value for key, value in self.items.items() if key[0] != collection_id
        }
        return True

    def list_items(self, collection_id: UUID) -> list[dict[str, Any]]:
        return [
            dict(row)
            for (owner_id, _), row in self.items.items()
            if owner_id == collection_id
        ]

    def get_item(
        self,
        collection_id: UUID,
        canonical_id: str,
    ) -> dict[str, Any] | None:
        row = self.items.get((collection_id, canonical_id))
        return dict(row) if row is not None else None

    def upsert_item(
        self,
        *,
        collection_id: UUID,
        canonical_id: str,
        note: str | None,
        note_supplied: bool,
        reading_status: str | None,
        reading_status_supplied: bool,
        touch_collection: bool,
    ) -> dict[str, Any]:
        key = (collection_id, canonical_id)
        row = self.items.get(key)
        if row is None:
            timestamp = _now()
            row = {
                "collection_id": collection_id,
                "canonical_id": canonical_id,
                "note": note if note_supplied else None,
                "reading_status": (
                    reading_status if reading_status_supplied else "to_read"
                ),
                "added_at": timestamp,
                "updated_at": timestamp,
            }
            self.items[key] = row
        else:
            changed = False
            if note_supplied:
                row["note"] = note
                changed = True
            if reading_status_supplied:
                row["reading_status"] = reading_status
                changed = True
            if changed:
                row["updated_at"] = _now()
        if touch_collection:
            self.touch_collection(collection_id)
        return dict(row)

    def update_item(
        self,
        *,
        collection_id: UUID,
        canonical_id: str,
        note: str | None,
        note_supplied: bool,
        reading_status: str | None,
        reading_status_supplied: bool,
    ) -> dict[str, Any] | None:
        row = self.items.get((collection_id, canonical_id))
        if row is None:
            return None
        if note_supplied:
            row["note"] = note
        if reading_status_supplied:
            row["reading_status"] = reading_status
        row["updated_at"] = _now()
        return dict(row)

    def touch_collection(self, collection_id: UUID) -> None:
        self.collections[collection_id]["updated_at"] = _now()
        self.touch_count += 1

    def delete_item(
        self,
        collection_id: UUID,
        canonical_id: str,
    ) -> bool:
        key = (collection_id, canonical_id)
        if key not in self.items:
            return False
        del self.items[key]
        self.touch_collection(collection_id)
        return True


class MemoryPaperCatalog:
    def __init__(self) -> None:
        self.papers: dict[str, dict[str, Any]] = {
            "paper-1": {
                "canonical_id": "paper-1",
                "title": "Reliable RAG Evaluation",
                "authors": ["Ada Example"],
                "year": 2026,
                "venue": "ML Radar",
            }
        }

    def get_papers(
        self,
        canonical_ids,
    ) -> dict[str, dict[str, Any]]:
        return {
            canonical_id: self.papers[canonical_id]
            for canonical_id in canonical_ids
            if canonical_id in self.papers
        }


@pytest.fixture
def workspace() -> tuple[
    WorkspaceService,
    MemoryWorkspaceStore,
    MemoryPaperCatalog,
]:
    store = MemoryWorkspaceStore()
    catalog = MemoryPaperCatalog()
    service = WorkspaceService(
        store=store,
        paper_catalog=catalog,
    )
    return service, store, catalog


def test_collection_and_item_workflow_is_idempotent(workspace) -> None:
    service, store, _ = workspace

    collection = service.create_collection(
        name="  RAG reading  ",
        description="Evaluation papers",
    )
    assert collection.name == "RAG reading"
    assert collection.item_count == 0

    first = service.upsert_item(
        collection.collection_id,
        "paper-1",
        note="Read the benchmark section",
        note_supplied=True,
        reading_status="reading",
        reading_status_supplied=True,
    )
    original_added_at = first.added_at

    repeated = service.upsert_item(
        collection.collection_id,
        "paper-1",
        note=None,
        note_supplied=False,
        reading_status=None,
        reading_status_supplied=False,
    )

    assert repeated.added_at == original_added_at
    assert repeated.note == "Read the benchmark section"
    assert repeated.reading_status == "reading"
    assert store.touch_count == 1

    detail = service.get_collection(collection.collection_id)
    assert detail.item_count == 1
    assert len(detail.items) == 1
    assert detail.items[0].orphaned is False
    assert detail.items[0].paper is not None
    assert detail.items[0].paper.title == "Reliable RAG Evaluation"


def test_new_unknown_paper_is_rejected(workspace) -> None:
    service, _, _ = workspace
    collection = service.create_collection(
        name="Unknown papers",
        description=None,
    )

    with pytest.raises(PaperNotFoundError):
        service.upsert_item(
            collection.collection_id,
            "missing-paper",
            note=None,
            note_supplied=False,
            reading_status=None,
            reading_status_supplied=False,
        )


def test_saved_orphan_remains_editable_and_visible(workspace) -> None:
    service, _, catalog = workspace
    collection = service.create_collection(
        name="Durable papers",
        description=None,
    )
    saved = service.upsert_item(
        collection.collection_id,
        "paper-1",
        note="Original note",
        note_supplied=True,
        reading_status=None,
        reading_status_supplied=False,
    )

    del catalog.papers["paper-1"]

    updated = service.update_item(
        collection.collection_id,
        "paper-1",
        note=None,
        note_supplied=True,
        reading_status="read",
        reading_status_supplied=True,
    )

    assert updated.added_at == saved.added_at
    assert updated.note is None
    assert updated.reading_status == "read"
    assert updated.orphaned is True
    assert updated.paper is None

    detail = service.get_collection(collection.collection_id)
    assert detail.items[0].canonical_id == "paper-1"
    assert detail.items[0].orphaned is True


def test_missing_collection_item_has_domain_error(workspace) -> None:
    service, _, _ = workspace
    collection = service.create_collection(
        name="Empty",
        description=None,
    )

    with pytest.raises(CollectionItemNotFoundError):
        service.update_item(
            collection.collection_id,
            "paper-1",
            note="No item exists yet",
            note_supplied=True,
            reading_status=None,
            reading_status_supplied=False,
        )


def test_patch_models_reject_empty_or_null_required_changes() -> None:
    with pytest.raises(ValidationError):
        CollectionUpdateRequest()

    with pytest.raises(ValidationError):
        CollectionUpdateRequest(name=None)

    with pytest.raises(ValidationError):
        CollectionItemUpdateRequest()

    with pytest.raises(ValidationError):
        CollectionItemUpdateRequest(reading_status=None)


def test_workspace_database_url_is_psycopg_compatible() -> None:
    config = WorkspacePostgresConfig(
        database_url=(
            "postgresql+psycopg://user:password@localhost:5432/"
            "ml_radar_collections_test"
        )
    )

    assert config.psycopg_conninfo() == (
        "postgresql://user:password@localhost:5432/ml_radar_collections_test"
    )
