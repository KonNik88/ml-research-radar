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
    source_record_id: Optional[str] = None
    source_record_url: Optional[HttpUrl] = None
    canonical_url: Optional[HttpUrl] = None
    fetched_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None


class CanonicalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # identity
    canonical_id: str
    doc_ids: List[str] = Field(default_factory=list)

    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    openalex_id: Optional[str] = None
    source_ids: Dict[str, str] = Field(default_factory=dict)

    # core content
    title: str
    abstract: Optional[str] = None
    authors: List[str] = Field(default_factory=list)

    published_at: Optional[datetime] = None
    publication_date: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    year: Optional[int] = None

    # links / accessibility
    landing_page_url: Optional[HttpUrl] = None
    pdf_url: Optional[HttpUrl] = None
    repo_url: Optional[HttpUrl] = None

    license: Optional[str] = None
    open_access: Optional[bool] = None

    # taxonomy / topics
    primary_category: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # publication metadata
    comment: Optional[str] = None
    journal_ref: Optional[str] = None
    venue: Optional[str] = None
    journal: Optional[str] = None
    conference: Optional[str] = None
    publisher: Optional[str] = None
    publication_type: Optional[str] = None
    language: Optional[str] = None

    # citation / graph-ready metadata
    cited_by_count: Optional[int] = None
    references_count: Optional[int] = None
    referenced_ids: List[str] = Field(default_factory=list)
    referenced_dois: List[str] = Field(default_factory=list)
    referenced_arxiv_ids: List[str] = Field(default_factory=list)
    citation_graph_available: bool = False

    # code / assets
    has_code_link: bool = False
    code_links: List[HttpUrl] = Field(default_factory=list)
    dataset_links: List[HttpUrl] = Field(default_factory=list)
    model_links: List[HttpUrl] = Field(default_factory=list)

    # provenance
    sources: List[SourceLink] = Field(default_factory=list)
    source_count: int = 0

    # quality / bookkeeping
    metadata_completeness_score: Optional[float] = None

    reconciliation_key: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_record_at: datetime = Field(default_factory=utc_now)