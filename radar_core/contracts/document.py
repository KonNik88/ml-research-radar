from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStage(str, Enum):
    FOUND = "FOUND"
    FETCHED = "FETCHED"
    PARSED = "PARSED"
    EMBEDDED = "EMBEDDED"
    ENRICHED = "ENRICHED"
    INDEXED = "INDEXED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class DocumentType(str, Enum):
    PAPER = "paper"
    REPOSITORY = "repository"
    DATASET = "dataset"
    UNKNOWN = "unknown"


class ProcessingStageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: PipelineStage
    status: StageStatus = StageStatus.PENDING
    timestamp: datetime = Field(default_factory=utc_now)
    pipeline_version: str = "0.1.0"
    error: Optional[str] = None
    artifact_refs: List[str] = Field(default_factory=list)


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    source_id: Optional[str] = None
    source_url: Optional[HttpUrl] = None
    fetched_at: datetime = Field(default_factory=utc_now)

    # backward-compatible enrichment fields
    source_record_id: Optional[str] = None
    source_record_url: Optional[HttpUrl] = None
    source_api_url: Optional[HttpUrl] = None
    source_updated_at: Optional[datetime] = None
    raw_source_name: Optional[str] = None
    run_ts: Optional[str] = None


class RawDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    doc_id: str
    canonical_url: HttpUrl
    content_hash: Optional[str] = None
    document_type: DocumentType = DocumentType.PAPER
    source_info: SourceInfo
    pipeline_version: str = "0.1.0"
    stages: List[ProcessingStageRecord] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class NormalizedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ===== identity =====
    doc_id: str
    canonical_url: HttpUrl
    content_hash: str
    document_type: DocumentType = DocumentType.PAPER

    # ===== source identity / provenance =====
    source: str
    source_id: Optional[str] = None
    source_record_id: Optional[str] = None
    source_record_url: Optional[HttpUrl] = None

    # richer provenance without breaking current code
    source_ids: Dict[str, str] = Field(default_factory=dict)
    source_api_url: Optional[HttpUrl] = None

    external_ids: Dict[str, str] = Field(default_factory=dict)

    # ===== stable identifiers =====
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    openalex_id: Optional[str] = None

    # additional ids for future enrichment / storage / analytics
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    dblp_id: Optional[str] = None
    mag_id: Optional[str] = None

    # ===== core bibliographic fields =====
    title: str
    abstract: Optional[str] = None
    authors: List[str] = Field(default_factory=list)

    published_at: Optional[datetime] = None
    publication_date: Optional[datetime] = None
    updated_source_at: Optional[datetime] = None
    year: Optional[int] = None

    # ===== links / accessibility =====
    landing_page_url: Optional[HttpUrl] = None
    pdf_url: Optional[HttpUrl] = None
    repo_url: Optional[HttpUrl] = None

    license: Optional[str] = None
    open_access: Optional[bool] = None

    # ===== taxonomy / topical metadata =====
    primary_category: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # ===== publication metadata =====
    comment: Optional[str] = None
    journal_ref: Optional[str] = None
    venue: Optional[str] = None
    journal: Optional[str] = None
    conference: Optional[str] = None
    publisher: Optional[str] = None
    publication_type: Optional[str] = None
    language: Optional[str] = None

    # ===== citation / graph-ready metadata =====
    cited_by_count: Optional[int] = None
    references_count: Optional[int] = None
    referenced_ids: List[str] = Field(default_factory=list)
    referenced_dois: List[str] = Field(default_factory=list)
    referenced_arxiv_ids: List[str] = Field(default_factory=list)
    citation_graph_available: bool = False

    # ===== code / assets =====
    has_code_link: bool = False
    code_links: List[HttpUrl] = Field(default_factory=list)
    dataset_links: List[HttpUrl] = Field(default_factory=list)
    model_links: List[HttpUrl] = Field(default_factory=list)

    # optional convenience flags for future filters/API/UI
    has_dataset_link: bool = False
    has_model_link: bool = False

    # ===== lightweight flags =====
    has_pdf: bool = False
    is_withdrawn: bool = False

    # optional quality / type heuristics
    is_open_access: Optional[bool] = None
    is_preprint: Optional[bool] = None
    is_review: bool = False
    is_survey: bool = False

    # ===== provenance / bookkeeping =====
    raw_artifact_path: Optional[str] = None
    raw_source_name: Optional[str] = None
    ingested_at: datetime = Field(default_factory=utc_now)
    metadata_completeness_score: Optional[float] = None

    pipeline_version: str = "0.1.0"
    stages: List[ProcessingStageRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)