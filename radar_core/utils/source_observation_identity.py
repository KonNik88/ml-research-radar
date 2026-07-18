from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from radar_core.utils.ids import canonicalize_url, normalize_text, stable_hash


SOURCE_OBSERVATION_ID_NAMESPACE = "source_observation_v1"
SOURCE_OBSERVATION_ID_LENGTH = 32

_SOURCE_ALIASES = {
    "openalex_alignment": "openalex",
    "semantic_scholar_alignment": "semantic_scholar",
    "crossref_alignment": "crossref",
    "acl": "acl_anthology",
}

_SOURCE_SEPARATORS_RE = re.compile(r"[\s-]+")
_DOI_PREFIX_RE = re.compile(
    r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
    flags=re.IGNORECASE,
)
_OPENALEX_ID_RE = re.compile(r"(?:https?://openalex\.org/)?(W\d+)$", re.IGNORECASE)
_SEMANTIC_SCHOLAR_ID_RE = re.compile(
    r"(?:https?://(?:www\.)?semanticscholar\.org/(?:paper/)?|"
    r"https?://api\.semanticscholar\.org/graph/v1/paper/)?([^/?#]+)$",
    re.IGNORECASE,
)
_ARXIV_PREFIX_RE = re.compile(
    r"^(?:https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/|arxiv:\s*)",
    flags=re.IGNORECASE,
)
_ACL_PREFIX_RE = re.compile(
    r"^https?://(?:www\.)?aclanthology\.org/",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceObservationIdentity:
    """Deterministic identity for one normalized record from one source family."""

    source_observation_id: str
    normalized_source: str
    identity_basis: str
    normalized_identity_value: str

    def descriptor(self) -> tuple[str, str, str]:
        return (
            self.normalized_source,
            self.identity_basis,
            self.normalized_identity_value,
        )


def normalize_source_name(value: Any) -> str:
    text = normalize_text(None if value is None else str(value)).lower()
    text = _SOURCE_SEPARATORS_RE.sub("_", text).strip("_")
    text = _SOURCE_ALIASES.get(text, text)
    if not text:
        raise ValueError("source is required for source observation identity")
    return text


def normalize_doi_identity(value: Any) -> str:
    text = normalize_text(None if value is None else str(value)).lower()
    text = _DOI_PREFIX_RE.sub("", text).strip().strip("/")
    return text


def normalize_openalex_identity(value: Any) -> str:
    text = normalize_text(None if value is None else str(value)).rstrip("/")
    match = _OPENALEX_ID_RE.search(text)
    if match:
        return f"https://openalex.org/{match.group(1).upper()}"
    return text


def normalize_semantic_scholar_identity(value: Any) -> str:
    text = normalize_text(None if value is None else str(value)).rstrip("/")
    match = _SEMANTIC_SCHOLAR_ID_RE.search(text)
    if match:
        return match.group(1).lower()
    return text.lower()


def normalize_arxiv_identity(value: Any) -> str:
    text = normalize_text(None if value is None else str(value)).lower()
    text = _ARXIV_PREFIX_RE.sub("", text)
    text = text.split("?", 1)[0].split("#", 1)[0]
    if text.endswith(".pdf"):
        text = text[:-4]
    return text.strip().strip("/")


def normalize_acl_identity(value: Any) -> str:
    text = normalize_text(None if value is None else str(value)).lower()
    text = _ACL_PREFIX_RE.sub("", text)
    return text.strip().strip("/")


def normalize_url_identity(value: Any) -> str:
    text = normalize_text(None if value is None else str(value))
    if not text:
        return ""
    return canonicalize_url(text)


def normalize_provider_identity(
    *,
    source: str,
    basis: str,
    value: Any,
) -> str:
    """Normalize an identity value without converting paper identity into source identity."""

    if basis in {"source_record_url", "source_api_url", "canonical_url"}:
        return normalize_url_identity(value)

    if basis == "legacy_doc_id":
        return normalize_text(None if value is None else str(value)).lower()

    if source == "crossref":
        return normalize_doi_identity(value)
    if source == "openalex":
        return normalize_openalex_identity(value)
    if source == "semantic_scholar":
        return normalize_semantic_scholar_identity(value)
    if source == "arxiv":
        return normalize_arxiv_identity(value)
    if source == "acl_anthology":
        return normalize_acl_identity(value)

    return normalize_text(None if value is None else str(value))


def build_source_observation_identity(
    *,
    source: Any,
    source_record_id: Any = None,
    source_id: Any = None,
    source_record_url: Any = None,
    source_api_url: Any = None,
    legacy_doc_id: Any = None,
    canonical_url: Any = None,
) -> SourceObservationIdentity:
    """
    Build a stable source-observation identity.

    The source family is always part of the hash input. Therefore records from
    different providers cannot collapse merely because they share a DOI-backed
    canonical URL or the same legacy ``doc_id``.
    """

    normalized_source = normalize_source_name(source)
    candidates = (
        ("source_record_id", source_record_id),
        ("source_id", source_id),
        ("source_record_url", source_record_url),
        ("source_api_url", source_api_url),
        ("legacy_doc_id", legacy_doc_id),
        ("canonical_url", canonical_url),
    )

    identity_basis: str | None = None
    normalized_identity_value: str | None = None

    for basis, raw_value in candidates:
        if raw_value is None:
            continue
        normalized_value = normalize_provider_identity(
            source=normalized_source,
            basis=basis,
            value=raw_value,
        )
        if normalized_value:
            identity_basis = basis
            normalized_identity_value = normalized_value
            break

    if identity_basis is None or normalized_identity_value is None:
        raise ValueError(
            "source observation identity requires at least one non-empty identity field"
        )

    hash_payload = json.dumps(
        [
            SOURCE_OBSERVATION_ID_NAMESPACE,
            normalized_source,
            identity_basis,
            normalized_identity_value,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    source_observation_id = stable_hash(
        hash_payload,
        length=SOURCE_OBSERVATION_ID_LENGTH,
    )

    return SourceObservationIdentity(
        source_observation_id=source_observation_id,
        normalized_source=normalized_source,
        identity_basis=identity_basis,
        normalized_identity_value=normalized_identity_value,
    )


def build_source_observation_identity_from_mapping(
    row: Mapping[str, Any],
) -> SourceObservationIdentity:
    return build_source_observation_identity(
        source=row.get("source"),
        source_record_id=row.get("source_record_id"),
        source_id=row.get("source_id"),
        source_record_url=row.get("source_record_url"),
        source_api_url=row.get("source_api_url"),
        legacy_doc_id=row.get("doc_id"),
        canonical_url=row.get("canonical_url"),
    )
