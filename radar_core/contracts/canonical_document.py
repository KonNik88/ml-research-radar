from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    source_id: Optional[str] = None
    source_record_url: Optional[HttpUrl] = None
    canonical_url: Optional[HttpUrl] = None


class CanonicalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    doc_ids: List[str] = Field(default_factory=list)

    title: str
    abstract: Optional[str] = None
    authors: List[str] = Field(default_factory=list)

    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    year: Optional[int] = None

    doi: Optional[str] = None
    pdf_url: Optional[HttpUrl] = None

    primary_category: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    language: Optional[str] = None

    sources: List[SourceLink] = Field(default_factory=list)
    source_count: int = 0

    reconciliation_key: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_record_at: datetime = Field(default_factory=utc_now)