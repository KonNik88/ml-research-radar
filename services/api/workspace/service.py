from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID, uuid4

from radar_core.contracts.canonical_document import CanonicalDocument
from services.api.workspace.errors import (
    CollectionItemNotFoundError,
    CollectionNotFoundError,
    PaperNotFoundError,
    WorkspaceValidationError,
)
from services.api.workspace.schemas import (
    CollectionDetailResponse,
    CollectionItemResponse,
    CollectionListResponse,
    CollectionSummaryResponse,
    WorkspacePaperSummary,
)

if TYPE_CHECKING:
    from services.api.runtime import ApiRuntime
    from services.api.workspace.store import WorkspaceStore


def _get_runtime() -> ApiRuntime:
    from services.api.runtime import get_runtime

    return get_runtime()


class PaperCatalog(Protocol):
    def get_papers(
        self,
        canonical_ids: Iterable[str],
    ) -> dict[str, CanonicalDocument | dict[str, Any]]: ...


class RuntimePaperCatalog:
    """Read the current canonical corpus without owning workspace state."""

    def __init__(
        self,
        runtime_provider: Callable[[], ApiRuntime] | None = None,
    ) -> None:
        self._runtime_provider = runtime_provider or _get_runtime

    def get_papers(
        self,
        canonical_ids: Iterable[str],
    ) -> dict[str, CanonicalDocument | dict[str, Any]]:
        runtime = self._runtime_provider()
        if not runtime.is_ready():
            raise RuntimeError("Runtime is not ready")
        return runtime.get_documents_by_ids(canonical_ids)


class WorkspaceService:
    def __init__(
        self,
        *,
        store: WorkspaceStore,
        paper_catalog: PaperCatalog,
    ) -> None:
        self._store = store
        self._paper_catalog = paper_catalog

    def create_collection(
        self,
        *,
        name: str,
        description: str | None,
    ) -> CollectionSummaryResponse:
        normalized_name = self._normalize_name(name)
        row = self._store.create_collection(
            collection_id=uuid4(),
            name=normalized_name,
            description=description,
        )
        return CollectionSummaryResponse(**row)

    def list_collections(
        self,
        *,
        limit: int,
        offset: int,
    ) -> CollectionListResponse:
        rows = self._store.list_collections(limit=limit, offset=offset)
        total = self._store.count_collections()
        return CollectionListResponse(
            total=total,
            offset=offset,
            limit=limit,
            results=[CollectionSummaryResponse(**row) for row in rows],
        )

    def get_collection(
        self,
        collection_id: UUID,
    ) -> CollectionDetailResponse:
        collection = self._require_collection(collection_id)
        items = self._store.list_items(collection_id)
        papers = self._paper_catalog.get_papers(item["canonical_id"] for item in items)
        return CollectionDetailResponse(
            **collection,
            items=[
                self._item_response(item, papers.get(item["canonical_id"]))
                for item in items
            ],
        )

    def update_collection(
        self,
        collection_id: UUID,
        *,
        name: str | None,
        name_supplied: bool,
        description: str | None,
        description_supplied: bool,
    ) -> CollectionSummaryResponse:
        if not name_supplied and not description_supplied:
            raise WorkspaceValidationError(
                "At least one collection field must be supplied"
            )
        if name_supplied:
            if name is None:
                raise WorkspaceValidationError("Collection name cannot be null")
            name = self._normalize_name(name)

        row = self._store.update_collection(
            collection_id,
            name=name,
            name_supplied=name_supplied,
            description=description,
            description_supplied=description_supplied,
        )
        if row is None:
            raise CollectionNotFoundError(collection_id)
        return CollectionSummaryResponse(**row)

    def delete_collection(self, collection_id: UUID) -> None:
        if not self._store.delete_collection(collection_id):
            raise CollectionNotFoundError(collection_id)

    def upsert_item(
        self,
        collection_id: UUID,
        canonical_id: str,
        *,
        note: str | None,
        note_supplied: bool,
        reading_status: str | None,
        reading_status_supplied: bool,
    ) -> CollectionItemResponse:
        normalized_id = self._normalize_canonical_id(canonical_id)
        self._require_collection(collection_id)

        existing = self._store.get_item(collection_id, normalized_id)
        paper: CanonicalDocument | dict[str, Any] | None = None
        if existing is None:
            paper = self._paper_catalog.get_papers([normalized_id]).get(normalized_id)
            if paper is None:
                raise PaperNotFoundError(normalized_id)

        row = self._store.upsert_item(
            collection_id=collection_id,
            canonical_id=normalized_id,
            note=note,
            note_supplied=note_supplied,
            reading_status=reading_status,
            reading_status_supplied=reading_status_supplied,
            touch_collection=existing is None,
        )

        if paper is None:
            paper = self._paper_catalog.get_papers([normalized_id]).get(normalized_id)
        return self._item_response(row, paper)

    def update_item(
        self,
        collection_id: UUID,
        canonical_id: str,
        *,
        note: str | None,
        note_supplied: bool,
        reading_status: str | None,
        reading_status_supplied: bool,
    ) -> CollectionItemResponse:
        normalized_id = self._normalize_canonical_id(canonical_id)
        if not note_supplied and not reading_status_supplied:
            raise WorkspaceValidationError("At least one item field must be supplied")
        self._require_collection(collection_id)

        row = self._store.update_item(
            collection_id=collection_id,
            canonical_id=normalized_id,
            note=note,
            note_supplied=note_supplied,
            reading_status=reading_status,
            reading_status_supplied=reading_status_supplied,
        )
        if row is None:
            raise CollectionItemNotFoundError(
                collection_id,
                normalized_id,
            )

        paper = self._paper_catalog.get_papers([normalized_id]).get(normalized_id)
        return self._item_response(row, paper)

    def delete_item(
        self,
        collection_id: UUID,
        canonical_id: str,
    ) -> None:
        normalized_id = self._normalize_canonical_id(canonical_id)
        self._require_collection(collection_id)
        if not self._store.delete_item(collection_id, normalized_id):
            raise CollectionItemNotFoundError(
                collection_id,
                normalized_id,
            )

    def _require_collection(self, collection_id: UUID) -> dict[str, Any]:
        collection = self._store.get_collection(collection_id)
        if collection is None:
            raise CollectionNotFoundError(collection_id)
        return collection

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise WorkspaceValidationError("Collection name must not be blank")
        if len(normalized) > 200:
            raise WorkspaceValidationError(
                "Collection name must be at most 200 characters"
            )
        return normalized

    @staticmethod
    def _normalize_canonical_id(canonical_id: str) -> str:
        normalized = canonical_id.strip()
        if not normalized:
            raise WorkspaceValidationError("canonical_id must not be blank")
        return normalized

    @staticmethod
    def _item_response(
        row: dict[str, Any],
        paper: CanonicalDocument | dict[str, Any] | None,
    ) -> CollectionItemResponse:
        summary = WorkspaceService._paper_summary(paper)
        return CollectionItemResponse(
            **row,
            orphaned=summary is None,
            paper=summary,
        )

    @staticmethod
    def _paper_summary(
        paper: CanonicalDocument | dict[str, Any] | None,
    ) -> WorkspacePaperSummary | None:
        if paper is None:
            return None

        if isinstance(paper, CanonicalDocument):
            return WorkspacePaperSummary(
                canonical_id=paper.canonical_id,
                title=paper.title,
                authors=list(paper.authors or []),
                year=paper.year,
                venue=paper.venue,
                landing_page_url=(
                    str(paper.landing_page_url)
                    if paper.landing_page_url is not None
                    else None
                ),
                pdf_url=(str(paper.pdf_url) if paper.pdf_url is not None else None),
            )

        return WorkspacePaperSummary(
            canonical_id=str(paper["canonical_id"]),
            title=str(paper["title"]),
            authors=[str(author) for author in paper.get("authors") or []],
            year=paper.get("year"),
            venue=paper.get("venue"),
            landing_page_url=WorkspaceService._optional_string(
                paper.get("landing_page_url")
            ),
            pdf_url=WorkspaceService._optional_string(paper.get("pdf_url")),
        )

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
