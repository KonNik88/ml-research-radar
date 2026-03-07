from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, ConfigDict


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

    # identity
    doc_id: str
    canonical_url: HttpUrl
    content_hash: str
    document_type: DocumentType = DocumentType.PAPER

    # source
    source: str
    source_id: Optional[str] = None
    source_record_url: Optional[HttpUrl] = None

    # core bibliographic fields
    title: str
    abstract: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    updated_source_at: Optional[datetime] = None
    year: Optional[int] = None

    # links / identifiers
    pdf_url: Optional[HttpUrl] = None
    repo_url: Optional[HttpUrl] = None
    doi: Optional[str] = None
    external_ids: Dict[str, str] = Field(default_factory=dict)

    # source metadata
    primary_category: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    comment: Optional[str] = None
    journal_ref: Optional[str] = None
    license: Optional[str] = None
    language: Optional[str] = None

    # lightweight flags
    has_pdf: bool = False
    is_withdrawn: bool = False

    # generic tags
    tags: List[str] = Field(default_factory=list)

    # lineage / bookkeeping
    raw_artifact_path: Optional[str] = None
    pipeline_version: str = "0.1.0"
    stages: List[ProcessingStageRecord] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)