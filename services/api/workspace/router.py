from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from services.api.settings import get_settings
from services.api.workspace.schemas import (
    CollectionCreateRequest,
    CollectionDetailResponse,
    CollectionItemResponse,
    CollectionItemUpdateRequest,
    CollectionItemUpsertRequest,
    CollectionListResponse,
    CollectionSummaryResponse,
    CollectionUpdateRequest,
)
from services.api.workspace.service import (
    RuntimePaperCatalog,
    WorkspaceService,
)
from services.api.workspace.store import (
    WorkspacePostgresConfig,
    WorkspaceStore,
)


router = APIRouter(prefix="/collections", tags=["collections"])


@lru_cache(maxsize=1)
def get_workspace_store() -> WorkspaceStore:
    settings = get_settings()
    return WorkspaceStore(
        WorkspacePostgresConfig(
            database_url=settings.workspace_database_url,
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_dbname,
            user=settings.postgres_user,
            password=settings.postgres_password,
            connect_timeout_sec=settings.workspace_connect_timeout_sec,
        )
    )


def get_workspace_service() -> WorkspaceService:
    return WorkspaceService(
        store=get_workspace_store(),
        paper_catalog=RuntimePaperCatalog(),
    )


@router.post(
    "",
    response_model=CollectionSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_collection(
    payload: CollectionCreateRequest,
    service: WorkspaceService = Depends(get_workspace_service),
) -> CollectionSummaryResponse:
    return service.create_collection(
        name=payload.name,
        description=payload.description,
    )


@router.get("", response_model=CollectionListResponse)
def list_collections(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: WorkspaceService = Depends(get_workspace_service),
) -> CollectionListResponse:
    return service.list_collections(limit=limit, offset=offset)


@router.get(
    "/{collection_id}",
    response_model=CollectionDetailResponse,
)
def get_collection(
    collection_id: UUID,
    service: WorkspaceService = Depends(get_workspace_service),
) -> CollectionDetailResponse:
    return service.get_collection(collection_id)


@router.patch(
    "/{collection_id}",
    response_model=CollectionSummaryResponse,
)
def update_collection(
    collection_id: UUID,
    payload: CollectionUpdateRequest,
    service: WorkspaceService = Depends(get_workspace_service),
) -> CollectionSummaryResponse:
    return service.update_collection(
        collection_id,
        name=payload.name,
        name_supplied="name" in payload.model_fields_set,
        description=payload.description,
        description_supplied="description" in payload.model_fields_set,
    )


@router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_collection(
    collection_id: UUID,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    service.delete_collection(collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{collection_id}/items/{canonical_id}",
    response_model=CollectionItemResponse,
)
def upsert_collection_item(
    collection_id: UUID,
    canonical_id: str,
    payload: CollectionItemUpsertRequest | None = None,
    service: WorkspaceService = Depends(get_workspace_service),
) -> CollectionItemResponse:
    request = payload or CollectionItemUpsertRequest()
    return service.upsert_item(
        collection_id,
        canonical_id,
        note=request.note,
        note_supplied="note" in request.model_fields_set,
        reading_status=request.reading_status,
        reading_status_supplied=("reading_status" in request.model_fields_set),
    )


@router.patch(
    "/{collection_id}/items/{canonical_id}",
    response_model=CollectionItemResponse,
)
def update_collection_item(
    collection_id: UUID,
    canonical_id: str,
    payload: CollectionItemUpdateRequest,
    service: WorkspaceService = Depends(get_workspace_service),
) -> CollectionItemResponse:
    return service.update_item(
        collection_id,
        canonical_id,
        note=payload.note,
        note_supplied="note" in payload.model_fields_set,
        reading_status=payload.reading_status,
        reading_status_supplied=("reading_status" in payload.model_fields_set),
    )


@router.delete(
    "/{collection_id}/items/{canonical_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_collection_item(
    collection_id: UUID,
    canonical_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    service.delete_item(collection_id, canonical_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
