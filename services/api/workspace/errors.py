from __future__ import annotations

from typing import Any
from uuid import UUID


class WorkspaceError(Exception):
    """Base exception for the durable workspace API."""

    error_code = "workspace_error"
    status_code = 500

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class WorkspaceValidationError(WorkspaceError):
    error_code = "validation_error"
    status_code = 422


class WorkspaceUnavailableError(WorkspaceError):
    error_code = "workspace_unavailable"
    status_code = 503

    def __init__(self) -> None:
        super().__init__(
            "Workspace storage is unavailable; check PostgreSQL connectivity "
            "and apply the workspace Alembic migrations."
        )


class CollectionNotFoundError(WorkspaceError):
    error_code = "collection_not_found"
    status_code = 404

    def __init__(self, collection_id: UUID) -> None:
        super().__init__(
            f"Collection not found: {collection_id}",
            details={"collection_id": str(collection_id)},
        )


class CollectionNameConflictError(WorkspaceError):
    error_code = "collection_name_conflict"
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(
            f"A collection with the normalized name already exists: {name}",
            details={"name": name},
        )


class PaperNotFoundError(WorkspaceError):
    error_code = "paper_not_found"
    status_code = 404

    def __init__(self, canonical_id: str) -> None:
        super().__init__(
            f"Paper not found in the current canonical corpus: {canonical_id}",
            details={"canonical_id": canonical_id},
        )


class CollectionItemNotFoundError(WorkspaceError):
    error_code = "collection_item_not_found"
    status_code = 404

    def __init__(self, collection_id: UUID, canonical_id: str) -> None:
        super().__init__(
            "Collection item not found: "
            f"collection_id={collection_id}, canonical_id={canonical_id}",
            details={
                "collection_id": str(collection_id),
                "canonical_id": canonical_id,
            },
        )
