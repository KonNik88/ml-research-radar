from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlparse


TRUSTED_LINK_POLICY_VERSION = "artifact_trusted_links_policy_v1"


PROVIDER_SPECIFIC_TRUSTED_TYPES = {
    "github_repository",
    "gitlab_repository",
    "bitbucket_repository",
    "codeberg_repository",
    "huggingface_model",
    "huggingface_dataset",
    "huggingface_space",
    "figshare_artifact",
    "zenodo_artifact",
    "youtube_video",
    "kaggle_dataset",
}


TRUSTED_GENERIC_FIELDS = {
    "comment",
    "code_links",
    "dataset_links",
    "model_links",
    "repo_url",
}


TECHNICAL_NOISE_DOMAINS = {
    "w3.org",
    "www.w3.org",
}


BIBLIOGRAPHIC_OR_RESOLVER_DOMAINS = {
    "arxiv.org",
    "www.arxiv.org",
    "doi.org",
    "www.doi.org",
    "dx.doi.org",
    "openalex.org",
    "www.openalex.org",
    "semanticscholar.org",
    "www.semanticscholar.org",
    "api.semanticscholar.org",
    "crossref.org",
    "www.crossref.org",
    "ncbi.nlm.nih.gov",
    "www.ncbi.nlm.nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "aclanthology.org",
    "www.aclanthology.org",
    "openreview.net",
    "www.openreview.net",
    "api.openreview.net",
    "api2.openreview.net",
    "portal.acm.org",
    "dl.acm.org",
    "acm.org",
    "www.acm.org",
    "springerlink.com",
    "www.springerlink.com",
    "link.springer.com",
    "ieeexplore.ieee.org",
    "proceedings.neurips.cc",
    "papers.nips.cc",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "hdl.handle.net",
    "nbn-resolving.de",
    "imstat.org",
    "www.imstat.org",
}


def stable_hash(*parts: Any, length: int = 32) -> str:
    text = "\n".join("" if p is None else str(p) for p in parts)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]


def normalize_host(host: str | None) -> str:
    host = (host or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def url_host(url: str | None) -> str:
    if not url:
        return ""
    try:
        return normalize_host(urlparse(url).netloc)
    except Exception:
        return ""


def domain_matches(host: str, domains: set[str]) -> bool:
    host = normalize_host(host)

    for domain in domains:
        domain = normalize_host(domain)
        if host == domain or host.endswith("." + domain):
            return True

    return False


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_trusted_observation(obs: dict[str, Any]) -> bool:
    artifact_type = obs.get("artifact_type")
    provider = obs.get("provider")
    relation_type = obs.get("relation_type")
    source_field = obs.get("source_field")
    confidence = safe_float(obs.get("confidence"), 0.0)
    host = url_host(obs.get("normalized_url"))

    if not obs.get("canonical_id"):
        return False

    if not obs.get("artifact_id"):
        return False

    if relation_type == "unknown":
        return False

    if domain_matches(host, TECHNICAL_NOISE_DOMAINS):
        return False

    if artifact_type in PROVIDER_SPECIFIC_TRUSTED_TYPES:
        return confidence >= 0.65

    if provider == "generic":
        if confidence < 0.9:
            return False

        if source_field not in TRUSTED_GENERIC_FIELDS:
            return False

        if domain_matches(host, BIBLIOGRAPHIC_OR_RESOLVER_DOMAINS):
            return False

        return True

    return False


def trusted_link_key(obs: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(obs.get("canonical_id")),
        str(obs.get("artifact_id")),
        str(obs.get("relation_type")),
    )


def build_trusted_link_rows(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trusted = [obs for obs in observations if is_trusted_observation(obs)]

    # One public/materialized paper-artifact link should represent:
    # canonical paper + artifact entity + relation type.
    #
    # Multiple trusted observations from comment/repo_url/code_links/source/canonical
    # are evidence for the same link and should be preserved in metadata, not create
    # duplicate paper_artifact_links rows.
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    for obs in trusted:
        canonical_id = str(obs.get("canonical_id"))
        artifact_id = str(obs.get("artifact_id"))
        relation_type = str(obs.get("relation_type"))
        source_field = str(obs.get("source_field"))
        evidence_source = f"{obs.get('source_layer') or 'unknown'}:{obs.get('source_name') or 'unknown'}"
        confidence = safe_float(obs.get("confidence"), 0.0)

        key = (
            canonical_id,
            artifact_id,
            relation_type,
        )

        evidence_item = {
            "observation_id": obs.get("observation_id"),
            "source_layer": obs.get("source_layer"),
            "source_name": obs.get("source_name"),
            "source_doc_id": obs.get("source_doc_id"),
            "source_field": source_field,
            "evidence_source": evidence_source,
            "raw_url": obs.get("raw_url"),
            "normalized_url": obs.get("normalized_url"),
            "confidence": confidence,
            "provider": obs.get("provider"),
            "artifact_type": obs.get("artifact_type"),
        }

        if key not in by_key:
            by_key[key] = {
                "link_id": stable_hash(
                    "paper_artifact_link",
                    canonical_id,
                    artifact_id,
                    relation_type,
                ),
                "canonical_id": canonical_id,
                "artifact_id": artifact_id,
                "relation_type": relation_type,
                "confidence": confidence,
                "evidence_source": evidence_source,
                "evidence_url": obs.get("normalized_url"),
                "source_field": source_field,
                "source_doc_id": obs.get("source_doc_id"),
                "metadata": {
                    "observation_ids": [obs.get("observation_id")],
                    "evidence": [evidence_item],
                    "provider": obs.get("provider"),
                    "artifact_type": obs.get("artifact_type"),
                    "extraction_stage": "internal_artifact_extraction_v1",
                    "trusted_link_policy_version": TRUSTED_LINK_POLICY_VERSION,
                },
            }
            continue

        existing = by_key[key]
        existing["metadata"].setdefault("observation_ids", [])
        existing["metadata"].setdefault("evidence", [])

        existing["metadata"]["observation_ids"].append(obs.get("observation_id"))
        existing["metadata"]["evidence"].append(evidence_item)

        # Keep the strongest representative evidence on top-level columns.
        if confidence > safe_float(existing.get("confidence"), 0.0):
            existing["confidence"] = confidence
            existing["evidence_source"] = evidence_source
            existing["evidence_url"] = obs.get("normalized_url")
            existing["source_field"] = source_field
            existing["source_doc_id"] = obs.get("source_doc_id")

    return list(by_key.values())
