from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


ReadingStatus = Literal["to_read", "reading", "read"]


class WorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CollectionCreateRequest(WorkspaceRequest):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Collection name must not be blank")
        return normalized


class CollectionUpdateRequest(WorkspaceRequest):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Collection name must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_patch(self) -> CollectionUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one collection field must be supplied")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Collection name cannot be null")
        return self


class CollectionItemUpsertRequest(WorkspaceRequest):
    note: str | None = Field(default=None, max_length=20000)
    reading_status: ReadingStatus | None = None

    @model_validator(mode="after")
    def validate_explicit_status(self) -> CollectionItemUpsertRequest:
        if "reading_status" in self.model_fields_set and self.reading_status is None:
            raise ValueError("reading_status cannot be null")
        return self


class CollectionItemUpdateRequest(CollectionItemUpsertRequest):
    @model_validator(mode="after")
    def validate_patch(self) -> CollectionItemUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one item field must be supplied")
        return self


class WorkspacePaperSummary(BaseModel):
    canonical_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    landing_page_url: str | None = None
    pdf_url: str | None = None


class CollectionItemResponse(BaseModel):
    collection_id: UUID
    canonical_id: str
    note: str | None = None
    reading_status: ReadingStatus
    added_at: datetime
    updated_at: datetime
    orphaned: bool
    paper: WorkspacePaperSummary | None = None


class CollectionSummaryResponse(BaseModel):
    collection_id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    item_count: int = Field(default=0, ge=0)


class CollectionDetailResponse(CollectionSummaryResponse):
    items: list[CollectionItemResponse] = Field(default_factory=list)


class CollectionListResponse(BaseModel):
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    results: list[CollectionSummaryResponse] = Field(default_factory=list)
