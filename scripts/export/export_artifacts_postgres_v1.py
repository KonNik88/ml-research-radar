from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import psycopg as pg_driver


DEFAULT_ENTITIES_PATH = Path("data/enriched/artifact_links/artifact_entities_latest.jsonl")
DEFAULT_LINKS_PATH = Path("data/enriched/artifact_links/artifact_links_latest.jsonl")
DEFAULT_REPORT_DIR = Path("artifacts/reports/export")
DEFAULT_GITHUB_METADATA_PATH = Path("data/enriched/github_artifacts/github_artifact_metadata_latest.jsonl")
DEFAULT_HUGGINGFACE_METADATA_PATH = Path(
    "data/enriched/huggingface_artifacts/huggingface_artifact_metadata_latest.jsonl"
)


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

def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        os.environ.setdefault(key, value)


load_dotenv_file(Path(".env"))
load_dotenv_file(Path("infra/docker/.env"))

def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(*parts: Any, length: int = 32) -> str:
    text = "\n".join("" if p is None else str(p) for p in parts)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [row for row, _ in iter_jsonl(path)]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def jsonb(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)

def parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def load_github_metadata(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"GitHub metadata file not found: {path}")
    return load_jsonl(path)


def index_github_metadata(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_artifact_id: dict[str, dict[str, Any]] = {}
    by_normalized_url: dict[str, dict[str, Any]] = {}

    # Keep the last row for each key. The enrichment output should be unique,
    # but this makes the merge robust to accidental duplicate metadata rows.
    for row in rows:
        if row.get("provider") != "github":
            continue

        artifact_id = row.get("artifact_id")
        normalized_url = row.get("normalized_url")

        if artifact_id:
            by_artifact_id[str(artifact_id)] = row
        if normalized_url:
            by_normalized_url[str(normalized_url).rstrip("/").lower()] = row

    return by_artifact_id, by_normalized_url


def github_metadata_for_entity(
    entity: dict[str, Any],
    by_artifact_id: dict[str, dict[str, Any]],
    by_normalized_url: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    artifact_id = entity.get("artifact_id")
    if artifact_id and str(artifact_id) in by_artifact_id:
        return by_artifact_id[str(artifact_id)]

    normalized_url = entity.get("normalized_url")
    if normalized_url:
        key = str(normalized_url).rstrip("/").lower()
        return by_normalized_url.get(key)

    return None


def github_metadata_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "status": row.get("status"),
        "http_status": row.get("http_status"),
        "github_api_url": row.get("github_api_url"),
        "fetched_at": row.get("fetched_at"),
        "language": row.get("language"),
        "watchers": row.get("watchers"),
        "open_issues": row.get("open_issues"),
        "default_branch": row.get("default_branch"),
        "archived": row.get("archived"),
        "disabled": row.get("disabled"),
        "private": row.get("private"),
        "pushed_at": row.get("pushed_at"),
        "homepage": row.get("homepage"),
        "html_url": row.get("html_url"),
        "error": row.get("error"),
    }

    row_meta = row.get("metadata")
    if isinstance(row_meta, dict):
        payload["rate_limit_remaining"] = row_meta.get("rate_limit_remaining")
        payload["rate_limit_limit"] = row_meta.get("rate_limit_limit")
        payload["rate_limit_reset"] = row_meta.get("rate_limit_reset")
        if row_meta.get("license_raw") is not None:
            payload["license_raw"] = row_meta.get("license_raw")

    return {k: v for k, v in payload.items() if v is not None}


def merge_github_metadata_into_entities(
    entities: list[dict[str, Any]],
    github_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not github_rows:
        return entities, {
            "github_metadata_loaded": False,
            "github_metadata_rows_count": 0,
            "github_metadata_found_count": 0,
            "github_metadata_entities_matched": 0,
            "github_metadata_entities_enriched": 0,
            "github_metadata_applied_count": 0,
            "github_metadata_found_applied_count": 0,
            "github_metadata_not_found_applied_count": 0,
            "github_metadata_missing_entity_count": 0,
            "github_metadata_status_distribution": {},
            "github_metadata_applied_status_distribution": {},
            "github_metadata_missing_status_distribution": {},
        }

    by_artifact_id, by_normalized_url = index_github_metadata(github_rows)
    status_counts = Counter(str(row.get("status") or "unknown") for row in github_rows)

    out: list[dict[str, Any]] = []
    matched = 0
    enriched = 0
    applied_status_counts: Counter[str] = Counter()
    matched_metadata_keys: set[tuple[str, str]] = set()

    for entity in entities:
        entity = dict(entity)
        row = github_metadata_for_entity(entity, by_artifact_id, by_normalized_url)

        if entity.get("provider") != "github" or row is None:
            out.append(entity)
            continue

        matched += 1
        artifact_id = row.get("artifact_id")
        normalized_url = row.get("normalized_url")
        matched_metadata_keys.add(
            (
                str(artifact_id or ""),
                str(normalized_url or "").rstrip("/").lower(),
            )
        )

        status = str(row.get("status") or "unknown")
        applied_status_counts[status] += 1

        metadata = json_object(entity.get("metadata"))
        metadata["github"] = {
            **json_object(metadata.get("github")),
            **github_metadata_payload(row),
        }
        metadata["github"]["enrichment_stage"] = "github_artifact_enrichment_v1"
        entity["metadata"] = metadata

        # Dedicated columns are populated only for successfully fetched repositories.
        # not_found / forbidden / error rows remain represented in metadata.github.
        if status == "found":
            entity["description"] = row.get("description") or entity.get("description")
            entity["license"] = row.get("license") or entity.get("license")
            entity["stars"] = parse_optional_int(row.get("stars"))
            entity["forks"] = parse_optional_int(row.get("forks"))
            entity["topics"] = row.get("topics") or entity.get("topics") or []
            entity["fetched_at"] = row.get("fetched_at") or entity.get("fetched_at")
            entity["created_at"] = row.get("created_at") or entity.get("created_at")
            entity["updated_at"] = row.get("updated_at") or entity.get("updated_at")
            enriched += 1

        out.append(entity)

    missing_status_counts: Counter[str] = Counter()
    for row in github_rows:
        key = (
            str(row.get("artifact_id") or ""),
            str(row.get("normalized_url") or "").rstrip("/").lower(),
        )
        if key not in matched_metadata_keys:
            missing_status_counts[str(row.get("status") or "unknown")] += 1

    missing_count = len(github_rows) - matched

    return out, {
        "github_metadata_loaded": True,
        "github_metadata_rows_count": len(github_rows),
        "github_metadata_found_count": int(status_counts.get("found", 0)),
        # Backward-compatible diagnostic names from the first GitHub metadata export version.
        "github_metadata_entities_matched": matched,
        "github_metadata_entities_enriched": enriched,
        # Explicit operational names used by checks and console diagnostics.
        "github_metadata_applied_count": matched,
        "github_metadata_found_applied_count": int(applied_status_counts.get("found", 0)),
        "github_metadata_not_found_applied_count": int(applied_status_counts.get("not_found", 0)),
        "github_metadata_missing_entity_count": missing_count,
        "github_metadata_status_distribution": dict(sorted(status_counts.items())),
        "github_metadata_applied_status_distribution": dict(sorted(applied_status_counts.items())),
        "github_metadata_missing_status_distribution": dict(sorted(missing_status_counts.items())),
    }


def load_huggingface_metadata(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"Hugging Face metadata file not found: {path}")
    return load_jsonl(path)


def index_huggingface_metadata(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_artifact_id: dict[str, dict[str, Any]] = {}
    by_normalized_url: dict[str, dict[str, Any]] = {}

    # Keep the last row for each key. The validation script checks duplicates by
    # artifact_id, but this also makes export robust to accidental duplicates.
    for row in rows:
        if row.get("provider") != "huggingface":
            continue

        artifact_id = row.get("artifact_id")
        normalized_url = row.get("normalized_url")

        if artifact_id:
            by_artifact_id[str(artifact_id)] = row
        if normalized_url:
            by_normalized_url[str(normalized_url).rstrip("/").lower()] = row

    return by_artifact_id, by_normalized_url


def huggingface_metadata_for_entity(
    entity: dict[str, Any],
    by_artifact_id: dict[str, dict[str, Any]],
    by_normalized_url: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    artifact_id = entity.get("artifact_id")
    if artifact_id and str(artifact_id) in by_artifact_id:
        return by_artifact_id[str(artifact_id)]

    normalized_url = entity.get("normalized_url")
    if normalized_url:
        key = str(normalized_url).rstrip("/").lower()
        return by_normalized_url.get(key)

    return None


def huggingface_metadata_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "status": row.get("status"),
        "http_status": row.get("http_status"),
        "repo_type": row.get("repo_type"),
        "repo_id": row.get("repo_id"),
        "huggingface_api_url": row.get("huggingface_api_url"),
        "fetched_at": row.get("fetched_at"),
        "description": row.get("description"),
        "downloads": row.get("downloads"),
        "likes": row.get("likes"),
        "license": row.get("license"),
        "pipeline_tag": row.get("pipeline_tag"),
        "library_name": row.get("library_name"),
        "private": row.get("private"),
        "gated": row.get("gated"),
        "disabled": row.get("disabled"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "last_modified": row.get("last_modified"),
        "input_normalized_url": row.get("input_normalized_url"),
        "input_external_id": row.get("input_external_id"),
        "error": row.get("error"),
    }

    row_meta = row.get("metadata")
    if isinstance(row_meta, dict):
        payload["rate_limit"] = row_meta.get("rate_limit")
        payload["rate_limit_policy"] = row_meta.get("rate_limit_policy")
        payload["x_request_id"] = row_meta.get("x_request_id")
        if row_meta.get("card_data") is not None:
            payload["card_data"] = row_meta.get("card_data")

    return {k: v for k, v in payload.items() if v is not None}


def merge_huggingface_metadata_into_entities(
    entities: list[dict[str, Any]],
    huggingface_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not huggingface_rows:
        return entities, {
            "huggingface_metadata_loaded": False,
            "huggingface_metadata_rows_count": 0,
            "huggingface_metadata_found_count": 0,
            "huggingface_metadata_entities_matched": 0,
            "huggingface_metadata_entities_enriched": 0,
            "huggingface_metadata_applied_count": 0,
            "huggingface_metadata_found_applied_count": 0,
            "huggingface_metadata_forbidden_applied_count": 0,
            "huggingface_metadata_skipped_invalid_applied_count": 0,
            "huggingface_metadata_missing_entity_count": 0,
            "huggingface_metadata_status_distribution": {},
            "huggingface_metadata_applied_status_distribution": {},
            "huggingface_metadata_missing_status_distribution": {},
        }

    by_artifact_id, by_normalized_url = index_huggingface_metadata(huggingface_rows)
    status_counts = Counter(str(row.get("status") or "unknown") for row in huggingface_rows)

    out: list[dict[str, Any]] = []
    matched = 0
    enriched = 0
    applied_status_counts: Counter[str] = Counter()
    matched_metadata_keys: set[tuple[str, str]] = set()

    for entity in entities:
        entity = dict(entity)
        row = huggingface_metadata_for_entity(entity, by_artifact_id, by_normalized_url)

        if entity.get("provider") != "huggingface" or row is None:
            out.append(entity)
            continue

        matched += 1
        artifact_id = row.get("artifact_id")
        normalized_url = row.get("normalized_url")
        matched_metadata_keys.add(
            (
                str(artifact_id or ""),
                str(normalized_url or "").rstrip("/").lower(),
            )
        )

        status = str(row.get("status") or "unknown")
        applied_status_counts[status] += 1

        metadata = json_object(entity.get("metadata"))
        metadata["huggingface"] = {
            **json_object(metadata.get("huggingface")),
            **huggingface_metadata_payload(row),
        }
        metadata["huggingface"]["enrichment_stage"] = "huggingface_artifact_enrichment_v1"
        entity["metadata"] = metadata

        # Dedicated columns are populated only for successfully fetched HF repos.
        # forbidden / skipped_invalid / not_found rows stay represented in metadata.huggingface.
        if status == "found":
            entity["description"] = row.get("description") or entity.get("description")
            entity["license"] = row.get("license") or entity.get("license")
            downloads = parse_optional_int(row.get("downloads"))
            likes = parse_optional_int(row.get("likes"))
            if downloads is not None:
                entity["downloads"] = downloads
            if likes is not None:
                entity["likes"] = likes
            entity["tags"] = row.get("tags") or entity.get("tags") or []
            entity["fetched_at"] = row.get("fetched_at") or entity.get("fetched_at")
            entity["created_at"] = row.get("created_at") or entity.get("created_at")
            entity["updated_at"] = row.get("updated_at") or entity.get("updated_at")
            enriched += 1

        out.append(entity)

    missing_status_counts: Counter[str] = Counter()
    for row in huggingface_rows:
        key = (
            str(row.get("artifact_id") or ""),
            str(row.get("normalized_url") or "").rstrip("/").lower(),
        )
        if key not in matched_metadata_keys:
            missing_status_counts[str(row.get("status") or "unknown")] += 1

    missing_count = len(huggingface_rows) - matched

    return out, {
        "huggingface_metadata_loaded": True,
        "huggingface_metadata_rows_count": len(huggingface_rows),
        "huggingface_metadata_found_count": int(status_counts.get("found", 0)),
        "huggingface_metadata_entities_matched": matched,
        "huggingface_metadata_entities_enriched": enriched,
        "huggingface_metadata_applied_count": matched,
        "huggingface_metadata_found_applied_count": int(applied_status_counts.get("found", 0)),
        "huggingface_metadata_forbidden_applied_count": int(applied_status_counts.get("forbidden", 0)),
        "huggingface_metadata_skipped_invalid_applied_count": int(
            applied_status_counts.get("skipped_invalid_external_id", 0)
        ),
        "huggingface_metadata_missing_entity_count": missing_count,
        "huggingface_metadata_status_distribution": dict(sorted(status_counts.items())),
        "huggingface_metadata_applied_status_distribution": dict(sorted(applied_status_counts.items())),
        "huggingface_metadata_missing_status_distribution": dict(sorted(missing_status_counts.items())),
    }


def get_db_config() -> dict[str, Any]:
    return {
        "host": os.getenv(
            "ML_RADAR_DB_HOST",
            os.getenv("ML_RADAR_POSTGRES_HOST", os.getenv("POSTGRES_HOST", "127.0.0.1")),
        ),
        "port": int(
            os.getenv(
                "ML_RADAR_DB_PORT",
                os.getenv("ML_RADAR_POSTGRES_PORT", os.getenv("POSTGRES_PORT", "15432")),
            )
        ),
        "dbname": os.getenv(
            "ML_RADAR_DB_NAME",
            os.getenv(
                "ML_RADAR_POSTGRES_DBNAME",
                os.getenv("POSTGRES_DB", "ml_radar"),
            ),
        ),
        "user": os.getenv(
            "ML_RADAR_DB_USER",
            os.getenv("ML_RADAR_POSTGRES_USER", os.getenv("POSTGRES_USER", "ml_radar")),
        ),
        "password": os.getenv(
            "ML_RADAR_DB_PASSWORD",
            os.getenv(
                "ML_RADAR_POSTGRES_PASSWORD",
                os.getenv("POSTGRES_PASSWORD", "ml_radar"),
            ),
        ),
    }


def connect_db():
    cfg = get_db_config()
    return pg_driver.connect(**cfg)


def is_trusted_observation(obs: dict[str, Any]) -> bool:
    artifact_type = obs.get("artifact_type")
    provider = obs.get("provider")
    relation_type = obs.get("relation_type")
    source_field = obs.get("source_field")
    confidence = float(obs.get("confidence") or 0.0)
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


def entity_preference_score(entity: dict[str, Any]) -> tuple[int, int, str]:
    provider = entity.get("provider")
    artifact_type = entity.get("artifact_type") or ""

    provider_score = 1
    if provider != "generic":
        provider_score = 2

    type_score = 1
    if artifact_type in PROVIDER_SPECIFIC_TRUSTED_TYPES:
        type_score = 3
    elif artifact_type.startswith("generic_code"):
        type_score = 2
    elif artifact_type.startswith("generic_dataset"):
        type_score = 2
    elif artifact_type.startswith("generic_model"):
        type_score = 2

    return provider_score, type_score, artifact_type


def dedupe_entities_for_db(
    entities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    by_url: dict[str, dict[str, Any]] = {}
    artifact_id_remap: dict[str, str] = {}
    collisions: list[dict[str, Any]] = []

    for entity in entities:
        normalized_url = entity.get("normalized_url")
        artifact_id = entity.get("artifact_id")

        if not normalized_url or not artifact_id:
            continue

        if normalized_url not in by_url:
            by_url[normalized_url] = entity
            artifact_id_remap[artifact_id] = artifact_id
            continue

        existing = by_url[normalized_url]
        existing_score = entity_preference_score(existing)
        candidate_score = entity_preference_score(entity)

        if candidate_score > existing_score:
            by_url[normalized_url] = entity
            artifact_id_remap[existing["artifact_id"]] = artifact_id
            artifact_id_remap[artifact_id] = artifact_id
            collisions.append(
                {
                    "normalized_url": normalized_url,
                    "kept_artifact_id": artifact_id,
                    "replaced_artifact_id": existing.get("artifact_id"),
                    "reason": "candidate_preferred",
                }
            )
        else:
            artifact_id_remap[artifact_id] = existing["artifact_id"]
            collisions.append(
                {
                    "normalized_url": normalized_url,
                    "kept_artifact_id": existing.get("artifact_id"),
                    "replaced_artifact_id": artifact_id,
                    "reason": "existing_preferred",
                }
            )

    return list(by_url.values()), artifact_id_remap, collisions


def remap_observations(
    observations: list[dict[str, Any]],
    entities_by_id: dict[str, dict[str, Any]],
    artifact_id_remap: dict[str, str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for obs in observations:
        obs = dict(obs)
        old_artifact_id = obs.get("artifact_id")
        new_artifact_id = artifact_id_remap.get(old_artifact_id, old_artifact_id)

        if new_artifact_id != old_artifact_id:
            obs["artifact_id"] = new_artifact_id

            entity = entities_by_id.get(new_artifact_id)
            if entity:
                obs["artifact_type"] = entity.get("artifact_type")
                obs["provider"] = entity.get("provider")
                obs["normalized_url"] = entity.get("normalized_url")

        out.append(obs)

    return out


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
        confidence = float(obs.get("confidence") or 0.0)

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
                "link_id": stable_hash("paper_artifact_link", canonical_id, artifact_id, relation_type),
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
                },
            }
            continue

        existing = by_key[key]
        existing["metadata"].setdefault("observation_ids", [])
        existing["metadata"].setdefault("evidence", [])

        existing["metadata"]["observation_ids"].append(obs.get("observation_id"))
        existing["metadata"]["evidence"].append(evidence_item)

        # Keep the strongest representative evidence on top-level columns.
        if confidence > float(existing.get("confidence") or 0.0):
            existing["confidence"] = confidence
            existing["evidence_source"] = evidence_source
            existing["evidence_url"] = obs.get("normalized_url")
            existing["source_field"] = source_field
            existing["source_doc_id"] = obs.get("source_doc_id")

    return list(by_key.values())


def truncate_artifact_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE TABLE
                paper_artifact_links,
                artifact_observations,
                artifact_entities
            RESTART IDENTITY;
            """
        )


def db_scalar(conn, sql: str) -> int:
    with conn.cursor() as cur:
        cur.execute(sql)
        value = cur.fetchone()[0]
        return int(value or 0)


def ensure_canonical_documents_exist(conn) -> int:
    return db_scalar(conn, "SELECT COUNT(*) FROM canonical_documents;")


def upsert_artifact_entities(conn, entities: list[dict[str, Any]]) -> int:
    sql = """
    INSERT INTO artifact_entities (
        artifact_id,
        artifact_type,
        provider,
        external_id,
        normalized_url,
        canonical_url,
        name,
        owner,
        title,
        description,
        license,
        stars,
        forks,
        downloads,
        likes,
        topics,
        tags,
        metadata,
        first_seen_at,
        last_seen_at,
        fetched_at,
        created_at,
        updated_at
    )
    VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s::jsonb, %s::jsonb, %s::jsonb,
        now(), now(), %s, %s, %s
    )
    ON CONFLICT (artifact_id)
    DO UPDATE SET
        artifact_type = EXCLUDED.artifact_type,
        provider = EXCLUDED.provider,
        external_id = EXCLUDED.external_id,
        normalized_url = EXCLUDED.normalized_url,
        canonical_url = EXCLUDED.canonical_url,
        name = COALESCE(EXCLUDED.name, artifact_entities.name),
        owner = COALESCE(EXCLUDED.owner, artifact_entities.owner),
        title = COALESCE(EXCLUDED.title, artifact_entities.title),
        description = COALESCE(EXCLUDED.description, artifact_entities.description),
        license = COALESCE(EXCLUDED.license, artifact_entities.license),
        stars = COALESCE(EXCLUDED.stars, artifact_entities.stars),
        forks = COALESCE(EXCLUDED.forks, artifact_entities.forks),
        downloads = COALESCE(EXCLUDED.downloads, artifact_entities.downloads),
        likes = COALESCE(EXCLUDED.likes, artifact_entities.likes),
        topics = EXCLUDED.topics,
        tags = EXCLUDED.tags,
        metadata = artifact_entities.metadata || EXCLUDED.metadata,
        last_seen_at = now(),
        fetched_at = COALESCE(EXCLUDED.fetched_at, artifact_entities.fetched_at),
        created_at = COALESCE(EXCLUDED.created_at, artifact_entities.created_at),
        updated_at = COALESCE(EXCLUDED.updated_at, artifact_entities.updated_at);
    """

    count = 0
    with conn.cursor() as cur:
        for entity in entities:
            cur.execute(
                sql,
                (
                    entity.get("artifact_id"),
                    entity.get("artifact_type"),
                    entity.get("provider"),
                    entity.get("external_id"),
                    entity.get("normalized_url"),
                    entity.get("canonical_url"),
                    entity.get("name"),
                    entity.get("owner"),
                    entity.get("title"),
                    entity.get("description"),
                    entity.get("license"),
                    entity.get("stars"),
                    entity.get("forks"),
                    entity.get("downloads"),
                    entity.get("likes"),
                    jsonb(entity.get("topics") or []),
                    jsonb(entity.get("tags") or []),
                    jsonb(entity.get("metadata") or {}),
                    entity.get("fetched_at"),
                    entity.get("created_at"),
                    entity.get("updated_at"),
                ),
            )
            count += 1

    return count


def upsert_artifact_observations(conn, observations: list[dict[str, Any]]) -> int:
    sql = """
    INSERT INTO artifact_observations (
        observation_id,
        artifact_id,
        artifact_type,
        provider,
        raw_url,
        normalized_url,
        source_layer,
        source_name,
        source_doc_id,
        canonical_id,
        source_field,
        evidence_text,
        relation_type,
        confidence,
        observed_at,
        metadata
    )
    VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s::jsonb
    )
    ON CONFLICT (observation_id)
    DO UPDATE SET
        artifact_id = EXCLUDED.artifact_id,
        artifact_type = EXCLUDED.artifact_type,
        provider = EXCLUDED.provider,
        raw_url = EXCLUDED.raw_url,
        normalized_url = EXCLUDED.normalized_url,
        source_layer = EXCLUDED.source_layer,
        source_name = EXCLUDED.source_name,
        source_doc_id = EXCLUDED.source_doc_id,
        canonical_id = EXCLUDED.canonical_id,
        source_field = EXCLUDED.source_field,
        evidence_text = EXCLUDED.evidence_text,
        relation_type = EXCLUDED.relation_type,
        confidence = EXCLUDED.confidence,
        observed_at = EXCLUDED.observed_at,
        metadata = artifact_observations.metadata || EXCLUDED.metadata;
    """

    count = 0
    with conn.cursor() as cur:
        for obs in observations:
            cur.execute(
                sql,
                (
                    obs.get("observation_id"),
                    obs.get("artifact_id"),
                    obs.get("artifact_type"),
                    obs.get("provider"),
                    obs.get("raw_url"),
                    obs.get("normalized_url"),
                    obs.get("source_layer"),
                    obs.get("source_name"),
                    obs.get("source_doc_id"),
                    obs.get("canonical_id"),
                    obs.get("source_field"),
                    obs.get("evidence_text"),
                    obs.get("relation_type"),
                    float(obs.get("confidence") or 0.0),
                    obs.get("observed_at") or utc_now_iso(),
                    jsonb(obs.get("metadata") or {}),
                ),
            )
            count += 1

    return count


def upsert_paper_artifact_links(conn, links: list[dict[str, Any]]) -> int:
    sql = """
    INSERT INTO paper_artifact_links (
        link_id,
        canonical_id,
        artifact_id,
        relation_type,
        confidence,
        evidence_source,
        evidence_url,
        source_field,
        source_doc_id,
        metadata,
        created_at,
        updated_at
    )
    VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now(), now()
    )
    ON CONFLICT ON CONSTRAINT paper_artifact_links_unique
    DO UPDATE SET
        confidence = GREATEST(paper_artifact_links.confidence, EXCLUDED.confidence),
        evidence_url = COALESCE(EXCLUDED.evidence_url, paper_artifact_links.evidence_url),
        source_doc_id = COALESCE(EXCLUDED.source_doc_id, paper_artifact_links.source_doc_id),
        metadata = paper_artifact_links.metadata || EXCLUDED.metadata,
        updated_at = now();
    """

    count = 0
    with conn.cursor() as cur:
        for link in links:
            cur.execute(
                sql,
                (
                    link.get("link_id"),
                    link.get("canonical_id"),
                    link.get("artifact_id"),
                    link.get("relation_type"),
                    float(link.get("confidence") or 0.0),
                    link.get("evidence_source"),
                    link.get("evidence_url"),
                    link.get("source_field"),
                    link.get("source_doc_id"),
                    jsonb(link.get("metadata") or {}),
                ),
            )
            count += 1

    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export artifact entities, observations and trusted paper-artifact links to Postgres."
    )
    parser.add_argument("--entities", type=Path, default=DEFAULT_ENTITIES_PATH)
    parser.add_argument("--links", type=Path, default=DEFAULT_LINKS_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--github-metadata",
        type=Path,
        default=None,
        help=(
            "Optional GitHub enrichment JSONL. If omitted, the default latest "
            "path is used when it exists. If neither exists, export remains "
            "backward-compatible and skips GitHub metadata merge."
        ),
    )
    parser.add_argument(
        "--no-github-metadata",
        action="store_true",
        help="Force skipping GitHub metadata even if the default latest file exists.",
    )
    parser.add_argument(
        "--huggingface-metadata",
        type=Path,
        default=None,
        help=(
            "Optional Hugging Face enrichment JSONL. If omitted, the default latest "
            "path is used when it exists. If neither exists, export remains "
            "backward-compatible and skips Hugging Face metadata merge."
        ),
    )
    parser.add_argument(
        "--no-huggingface-metadata",
        action="store_true",
        help="Force skipping Hugging Face metadata even if the default latest file exists.",
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--require-canonical-docs", action="store_true", default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    if not args.entities.exists():
        raise FileNotFoundError(f"Artifact entities file not found: {args.entities}")

    if not args.links.exists():
        raise FileNotFoundError(f"Artifact links file not found: {args.links}")

    print(f"[INFO] Loading artifact entities: {args.entities}")
    raw_entities = load_jsonl(args.entities)

    print(f"[INFO] Loading artifact observations: {args.links}")
    raw_observations = load_jsonl(args.links)

    github_metadata_path: Path | None = None
    if not args.no_github_metadata:
        if args.github_metadata is not None:
            github_metadata_path = args.github_metadata
        elif DEFAULT_GITHUB_METADATA_PATH.exists():
            github_metadata_path = DEFAULT_GITHUB_METADATA_PATH

    github_metadata_rows: list[dict[str, Any]] = []
    if github_metadata_path is not None:
        print(f"[INFO] Loading GitHub metadata: {github_metadata_path}")
        github_metadata_rows = load_github_metadata(github_metadata_path)
    else:
        print("[INFO] GitHub metadata merge skipped")

    huggingface_metadata_path: Path | None = None
    if not args.no_huggingface_metadata:
        if args.huggingface_metadata is not None:
            huggingface_metadata_path = args.huggingface_metadata
        elif DEFAULT_HUGGINGFACE_METADATA_PATH.exists():
            huggingface_metadata_path = DEFAULT_HUGGINGFACE_METADATA_PATH

    huggingface_metadata_rows: list[dict[str, Any]] = []
    if huggingface_metadata_path is not None:
        print(f"[INFO] Loading Hugging Face metadata: {huggingface_metadata_path}")
        huggingface_metadata_rows = load_huggingface_metadata(huggingface_metadata_path)
    else:
        print("[INFO] Hugging Face metadata merge skipped")

    db_entities, artifact_id_remap, normalized_url_collisions = dedupe_entities_for_db(raw_entities)
    db_entities, github_metadata_report = merge_github_metadata_into_entities(
        db_entities,
        github_metadata_rows,
    )
    db_entities, huggingface_metadata_report = merge_huggingface_metadata_into_entities(
        db_entities,
        huggingface_metadata_rows,
    )
    entities_by_id = {
        entity["artifact_id"]: entity
        for entity in db_entities
        if entity.get("artifact_id")
    }

    observations = remap_observations(
        raw_observations,
        entities_by_id=entities_by_id,
        artifact_id_remap=artifact_id_remap,
    )

    trusted_links = build_trusted_link_rows(observations)

    by_provider_entities = Counter(e.get("provider") for e in db_entities)
    by_provider_observations = Counter(o.get("provider") for o in observations)
    by_relation_observations = Counter(o.get("relation_type") for o in observations)

    print(f"[INFO] raw_entities={len(raw_entities)}")
    print(f"[INFO] db_entities={len(db_entities)}")
    print(f"[INFO] observations={len(observations)}")
    print(f"[INFO] trusted_paper_artifact_links={len(trusted_links)}")
    print(f"[INFO] normalized_url_collisions={len(normalized_url_collisions)}")
    if github_metadata_report.get("github_metadata_loaded"):
        print(f"[INFO] github_metadata_rows={github_metadata_report.get('github_metadata_rows_count')}")
        print(f"[INFO] github_metadata_found={github_metadata_report.get('github_metadata_found_count')}")
        print(f"[INFO] github_metadata_applied={github_metadata_report.get('github_metadata_applied_count')}")
        print(f"[INFO] github_metadata_missing_entities={github_metadata_report.get('github_metadata_missing_entity_count')}")
    if huggingface_metadata_report.get("huggingface_metadata_loaded"):
        print(f"[INFO] huggingface_metadata_rows={huggingface_metadata_report.get('huggingface_metadata_rows_count')}")
        print(f"[INFO] huggingface_metadata_found={huggingface_metadata_report.get('huggingface_metadata_found_count')}")
        print(f"[INFO] huggingface_metadata_applied={huggingface_metadata_report.get('huggingface_metadata_applied_count')}")
        print(f"[INFO] huggingface_metadata_missing_entities={huggingface_metadata_report.get('huggingface_metadata_missing_entity_count')}")

    report: dict[str, Any] = {
        "report_name": "export_artifacts_postgres_v1",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "entities_path": str(args.entities).replace("\\", "/"),
        "links_path": str(args.links).replace("\\", "/"),
        "github_metadata_path": (
            str(github_metadata_path).replace("\\", "/")
            if github_metadata_path is not None
            else None
        ),
        "huggingface_metadata_path": (
            str(huggingface_metadata_path).replace("\\", "/")
            if huggingface_metadata_path is not None
            else None
        ),
        **github_metadata_report,
        **huggingface_metadata_report,
        "dry_run": args.dry_run,
        "replace": args.replace,
        "raw_entities_count": len(raw_entities),
        "db_entities_count": len(db_entities),
        "observations_count": len(observations),
        "trusted_paper_artifact_links_count": len(trusted_links),
        "normalized_url_collisions_count": len(normalized_url_collisions),
        "normalized_url_collisions_sample": normalized_url_collisions[:30],
        "by_provider_entities": dict(sorted(by_provider_entities.items())),
        "by_provider_observations": dict(sorted(by_provider_observations.items())),
        "by_relation_observations": dict(sorted(by_relation_observations.items())),
        "db": {
            "host": get_db_config()["host"],
            "port": get_db_config()["port"],
            "dbname": get_db_config()["dbname"],
            "user": get_db_config()["user"],
        },
        "ok": False,
    }

    if args.dry_run:
        report["ok"] = True
        report["message"] = "Dry run completed; no DB writes performed."
        write_export_reports(args.report_dir, report)
        print("[OK] dry-run completed")
        return

    conn = connect_db()

    try:
        canonical_count = ensure_canonical_documents_exist(conn)
        report["canonical_documents_count_before"] = canonical_count

        if args.require_canonical_docs and canonical_count == 0:
            raise RuntimeError(
                "canonical_documents table is empty. "
                "Run scripts.export.export_postgres_v1 before exporting artifact links."
            )

        if args.replace:
            print("[INFO] Replacing artifact tables...")
            truncate_artifact_tables(conn)

        print("[INFO] Upserting artifact_entities...")
        upserted_entities = upsert_artifact_entities(conn, db_entities)

        print("[INFO] Upserting artifact_observations...")
        upserted_observations = upsert_artifact_observations(conn, observations)

        print("[INFO] Upserting paper_artifact_links...")
        upserted_links = upsert_paper_artifact_links(conn, trusted_links)

        conn.commit()

        report.update(
            {
                "upserted_entities": upserted_entities,
                "upserted_observations": upserted_observations,
                "upserted_paper_artifact_links": upserted_links,
                "artifact_entities_db_count": db_scalar(conn, "SELECT COUNT(*) FROM artifact_entities;"),
                "artifact_observations_db_count": db_scalar(conn, "SELECT COUNT(*) FROM artifact_observations;"),
                "paper_artifact_links_db_count": db_scalar(conn, "SELECT COUNT(*) FROM paper_artifact_links;"),
                "canonical_documents_count_after": db_scalar(conn, "SELECT COUNT(*) FROM canonical_documents;"),
                "ok": True,
            }
        )

    except Exception as exc:
        conn.rollback()
        report["ok"] = False
        report["error"] = repr(exc)
        write_export_reports(args.report_dir, report)
        raise

    finally:
        conn.close()

    write_export_reports(args.report_dir, report)

    print(f"[OK] upserted_entities={report['upserted_entities']}")
    print(f"[OK] upserted_observations={report['upserted_observations']}")
    print(f"[OK] upserted_paper_artifact_links={report['upserted_paper_artifact_links']}")
    print(f"[OK] artifact_entities_db_count={report['artifact_entities_db_count']}")
    print(f"[OK] artifact_observations_db_count={report['artifact_observations_db_count']}")
    print(f"[OK] paper_artifact_links_db_count={report['paper_artifact_links_db_count']}")
    print(f"[OK] report JSON: {args.report_dir / 'export_artifacts_postgres_v1_latest.json'}")


def write_export_reports(report_dir: Path, report: dict[str, Any]) -> None:
    history_dir = report_dir / "history"
    run_ts = report["run_ts"]

    latest_json = report_dir / "export_artifacts_postgres_v1_latest.json"
    history_json = history_dir / f"export_artifacts_postgres_v1_{run_ts}.json"

    write_json(latest_json, report)
    write_json(history_json, report)


if __name__ == "__main__":
    main()