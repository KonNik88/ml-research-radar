from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


DEFAULT_CONFIG = Path("configs/artifact_extraction.yaml")

DEFAULT_SOURCE_DIRS = [
    "arxiv",
    "openalex_alignment",
    "semantic_scholar_alignment",
    "crossref_alignment",
]

URL_RE = re.compile(
    r"""(?ix)
    \b(
        https?://[^\s<>"'\]\)]+
        |
        www\.[^\s<>"'\]\)]+
    )
    """
)

TRAILING_PUNCTUATION = ".,;:!?)]}>'\"”’»"

EXCLUDED_GENERIC_DOMAINS = {
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

    # Bibliographic / publisher / proceedings pages.
    # These should not become generic code/dataset/model artifacts.
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
    "w3.org",
    "www.w3.org",
}


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(*parts: Any, length: int = 32) -> str:
    text = "\n".join("" if p is None else str(p) for p in parts)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required. Install it or add it to the project environment."
        ) from exc

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)

    if not isinstance(payload, dict):
        raise ValueError(f"Invalid YAML config: {path}")

    return payload


def iter_jsonl(path: Path, max_docs: int | None = None):
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc

            count += 1
            if max_docs is not None and count >= max_docs:
                break


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_scalar_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def iter_strings(value: Any):
    if value is None:
        return

    if isinstance(value, str):
        text = normalize_scalar_text(value)
        if text:
            yield text
        return

    if isinstance(value, (int, float, bool)):
        return

    if isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
        return

    if isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
        return


def clean_raw_url(url: str) -> str:
    url = url.strip()

    while url and url[-1] in TRAILING_PUNCTUATION:
        url = url[:-1]

    if url.startswith("www."):
        url = "https://" + url

    return url


def extract_urls(text: str) -> list[str]:
    out: list[str] = []
    for match in URL_RE.finditer(text or ""):
        url = clean_raw_url(match.group(1))
        if url:
            out.append(url)
    return out


def normalize_host(host: str) -> str:
    host = (host or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_path_segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def build_url(scheme: str, host: str, segments: list[str]) -> str:
    return urlunparse((scheme, host, "/" + "/".join(segments), "", "", ""))


def strip_git_suffix(value: str) -> str:
    if value.endswith(".git"):
        return value[:-4]
    return value


def infer_relation_from_field(source_field: str) -> str | None:
    field = (source_field or "").lower()

    if field in {"repo_url", "code_links"} or "repo" in field or "code" in field:
        return "code"

    if "dataset" in field or "data_links" in field:
        return "dataset"

    if "model" in field:
        return "model"

    return None


def infer_relation_from_text(text: str, relation_keywords: dict[str, list[str]]) -> str:
    lowered = (text or "").lower()

    for relation in ["code", "dataset", "model", "demo"]:
        for keyword in relation_keywords.get(relation, []):
            if keyword.lower() in lowered:
                return relation

    return "unknown"


def is_probably_paper_or_bibliographic_url(host: str) -> bool:
    host = normalize_host(host)
    return host in EXCLUDED_GENERIC_DOMAINS


def classify_url(
    *,
    raw_url: str,
    relation_hint: str,
    artifact_types_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    parsed = urlparse(raw_url)
    host = normalize_host(parsed.netloc)
    segments = normalize_path_segments(parsed.path)

    if not host:
        return None

    scheme = "https"

    # GitHub repository
    if host == "github.com" and len(segments) >= 2:
        owner = segments[0]
        repo = strip_git_suffix(segments[1])

        if owner and repo and owner.lower() not in {
            "topics",
            "features",
            "marketplace",
            "collections",
            "search",
            "orgs",
            "apps",
            "pricing",
        }:
            normalized_url = build_url(scheme, "github.com", [owner, repo])
            external_id = f"{owner}/{repo}"

            return {
                "artifact_type": "github_repository",
                "provider": "github",
                "normalized_url": normalized_url,
                "canonical_url": normalized_url,
                "external_id": external_id,
                "owner": owner,
                "name": repo,
            }

    # GitLab repository
    if host == "gitlab.com" and len(segments) >= 2:
        owner = segments[0]
        repo = strip_git_suffix(segments[1])
        normalized_url = build_url(scheme, "gitlab.com", [owner, repo])

        return {
            "artifact_type": "gitlab_repository",
            "provider": "gitlab",
            "normalized_url": normalized_url,
            "canonical_url": normalized_url,
            "external_id": f"{owner}/{repo}",
            "owner": owner,
            "name": repo,
        }

    # Bitbucket repository
    if host == "bitbucket.org" and len(segments) >= 2:
        owner = segments[0]
        repo = strip_git_suffix(segments[1])
        normalized_url = build_url(scheme, "bitbucket.org", [owner, repo])

        return {
            "artifact_type": "bitbucket_repository",
            "provider": "bitbucket",
            "normalized_url": normalized_url,
            "canonical_url": normalized_url,
            "external_id": f"{owner}/{repo}",
            "owner": owner,
            "name": repo,
        }

    # Codeberg repository
    if host == "codeberg.org" and len(segments) >= 2:
        owner = segments[0]
        repo = strip_git_suffix(segments[1])
        normalized_url = build_url(scheme, "codeberg.org", [owner, repo])

        return {
            "artifact_type": "codeberg_repository",
            "provider": "codeberg",
            "normalized_url": normalized_url,
            "canonical_url": normalized_url,
            "external_id": f"{owner}/{repo}",
            "owner": owner,
            "name": repo,
        }

    # Hugging Face Hub
    if host == "huggingface.co":
        if len(segments) >= 3 and segments[0] == "datasets":
            namespace = segments[1]
            name = segments[2]
            normalized_url = build_url(scheme, "huggingface.co", ["datasets", namespace, name])

            return {
                "artifact_type": "huggingface_dataset",
                "provider": "huggingface",
                "normalized_url": normalized_url,
                "canonical_url": normalized_url,
                "external_id": f"datasets/{namespace}/{name}",
                "owner": namespace,
                "name": name,
            }

        if len(segments) >= 3 and segments[0] == "spaces":
            namespace = segments[1]
            name = segments[2]
            normalized_url = build_url(scheme, "huggingface.co", ["spaces", namespace, name])

            return {
                "artifact_type": "huggingface_space",
                "provider": "huggingface",
                "normalized_url": normalized_url,
                "canonical_url": normalized_url,
                "external_id": f"spaces/{namespace}/{name}",
                "owner": namespace,
                "name": name,
            }

        if len(segments) >= 2 and segments[0] not in {
            "api",
            "docs",
            "datasets",
            "spaces",
            "models",
            "papers",
            "blog",
            "pricing",
            "settings",
        }:
            namespace = segments[0]
            name = segments[1]
            normalized_url = build_url(scheme, "huggingface.co", [namespace, name])

            return {
                "artifact_type": "huggingface_model",
                "provider": "huggingface",
                "normalized_url": normalized_url,
                "canonical_url": normalized_url,
                "external_id": f"{namespace}/{name}",
                "owner": namespace,
                "name": name,
            }

    # YouTube demo/video links
    if host in {"youtube.com", "m.youtube.com"} and len(segments) >= 1 and segments[0] == "watch":
        query = urllib.parse.parse_qs(parsed.query)
        video_id = (query.get("v") or [None])[0]

        if video_id:
            normalized_url = f"https://www.youtube.com/watch?v={video_id}"

            return {
                "artifact_type": "youtube_video",
                "provider": "youtube",
                "normalized_url": normalized_url,
                "canonical_url": normalized_url,
                "external_id": video_id,
                "owner": None,
                "name": video_id,
            }

    if host == "youtu.be" and len(segments) >= 1:
        video_id = segments[0]
        normalized_url = f"https://www.youtube.com/watch?v={video_id}"

        return {
            "artifact_type": "youtube_video",
            "provider": "youtube",
            "normalized_url": normalized_url,
            "canonical_url": normalized_url,
            "external_id": video_id,
            "owner": None,
            "name": video_id,
        }

    # Kaggle datasets
    if host == "kaggle.com" and len(segments) >= 3 and segments[0] == "datasets":
        owner = segments[1]
        name = segments[2]
        normalized_url = build_url(scheme, "kaggle.com", ["datasets", owner, name])

        return {
            "artifact_type": "kaggle_dataset",
            "provider": "kaggle",
            "normalized_url": normalized_url,
            "canonical_url": normalized_url,
            "external_id": f"{owner}/{name}",
            "owner": owner,
            "name": name,
        }

    # Zenodo records
    if host == "zenodo.org" and len(segments) >= 2 and segments[0] in {"record", "records"}:
        record_id = segments[1]
        normalized_url = build_url(scheme, "zenodo.org", ["records", record_id])

        return {
            "artifact_type": "zenodo_artifact",
            "provider": "zenodo",
            "normalized_url": normalized_url,
            "canonical_url": normalized_url,
            "external_id": record_id,
            "owner": None,
            "name": record_id,
        }

    # Figshare
    if host.endswith("figshare.com"):
        normalized_url = urlunparse((scheme, host, parsed.path.rstrip("/"), "", "", ""))

        return {
            "artifact_type": "figshare_artifact",
            "provider": "figshare",
            "normalized_url": normalized_url,
            "canonical_url": normalized_url,
            "external_id": normalized_url,
            "owner": None,
            "name": segments[-1] if segments else None,
        }

    # Do not treat arbitrary PDFs as generic code/dataset/model artifacts.
    # Most unknown PDF URLs are full-text mirrors or institutional repository copies.
    if parsed.path.lower().endswith(".pdf"):
        return None

    # Generic artifact URLs:
    # Only keep them if relation is not unknown and the URL is not a bibliographic/paper URL.
    if relation_hint != "unknown" and not is_probably_paper_or_bibliographic_url(host):
        if relation_hint == "code":
            artifact_type = "generic_code_url"
        elif relation_hint == "dataset":
            artifact_type = "generic_dataset_url"
        elif relation_hint == "model":
            artifact_type = "generic_model_url"
        else:
            artifact_type = "generic_artifact_url"

        normalized_url = urlunparse((scheme, host, parsed.path.rstrip("/"), "", "", ""))

        return {
            "artifact_type": artifact_type,
            "provider": "generic",
            "normalized_url": normalized_url,
            "canonical_url": normalized_url,
            "external_id": normalized_url,
            "owner": None,
            "name": segments[-1] if segments else host,
        }

    return None


def compute_confidence(
    *,
    artifact_type: str,
    source_field: str,
    evidence_text: str,
    relation_type: str,
    config: dict[str, Any],
) -> float:
    artifact_cfg = (config.get("artifact_types") or {}).get(artifact_type) or {}
    base = float(artifact_cfg.get("confidence_base", 0.5))

    confidence_cfg = config.get("confidence") or {}
    field = (source_field or "").lower()

    if field in {"repo_url", "code_links", "dataset_links", "model_links"}:
        context_conf = float(confidence_cfg.get("existing_structured_field", 1.0))
    elif "comment" in field and relation_type != "unknown":
        context_conf = float(confidence_cfg.get("comment_with_keyword", 0.9))
    elif "abstract" in field and relation_type != "unknown":
        context_conf = float(confidence_cfg.get("abstract_with_keyword", 0.8))
    elif "metadata" in field and relation_type != "unknown":
        context_conf = float(confidence_cfg.get("metadata_with_keyword", 0.7))
    else:
        context_conf = float(confidence_cfg.get("generic_url", 0.5))

    return round(min(max(base, context_conf), 1.0), 4)


def relation_from_artifact_type(artifact_type: str, fallback: str) -> str:
    if "dataset" in artifact_type:
        return "dataset"
    if "model" in artifact_type:
        return "model"
    if "space" in artifact_type:
        return "demo"
    if "youtube" in artifact_type or "video" in artifact_type:
        return "demo"
    if "repository" in artifact_type or artifact_type == "generic_code_url":
        return "code"

    return fallback or "unknown"


def make_entity(row: dict[str, Any]) -> dict[str, Any]:
    artifact_id = stable_hash("artifact", row["artifact_type"], row["normalized_url"])

    return {
        "artifact_id": artifact_id,
        "artifact_type": row["artifact_type"],
        "provider": row["provider"],
        "external_id": row.get("external_id"),
        "normalized_url": row["normalized_url"],
        "canonical_url": row["canonical_url"],
        "name": row.get("name"),
        "owner": row.get("owner"),
        "metadata": {
            "first_extraction_stage": "internal_artifact_extraction_v1",
        },
    }


def make_observation(
    *,
    entity: dict[str, Any],
    raw_url: str,
    source_layer: str,
    source_name: str | None,
    source_doc_id: str | None,
    canonical_id: str | None,
    source_field: str,
    evidence_text: str,
    relation_type: str,
    confidence: float,
    line_no: int | None,
) -> dict[str, Any]:
    observation_id = stable_hash(
        "artifact_observation",
        canonical_id,
        source_doc_id,
        source_field,
        raw_url,
        entity["artifact_id"],
        line_no,
    )

    return {
        "observation_id": observation_id,
        "artifact_id": entity["artifact_id"],
        "artifact_type": entity["artifact_type"],
        "provider": entity["provider"],
        "raw_url": raw_url,
        "normalized_url": entity["normalized_url"],
        "source_layer": source_layer,
        "source_name": source_name,
        "source_doc_id": source_doc_id,
        "canonical_id": canonical_id,
        "source_field": source_field,
        "evidence_text": evidence_text[:500],
        "relation_type": relation_type,
        "confidence": confidence,
        "observed_at": utc_now_iso(),
        "metadata": {
            "extraction_stage": "internal_artifact_extraction_v1",
            "line_no": line_no,
        },
    }


def extract_artifacts_from_doc(
    *,
    doc: dict[str, Any],
    fields: list[str],
    source_layer: str,
    source_name: str | None,
    source_doc_id: str | None,
    canonical_id: str | None,
    line_no: int | None,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    relation_keywords = config.get("relation_keywords") or {}
    artifact_types_cfg = config.get("artifact_types") or {}
    max_urls_per_document = int(
        ((config.get("url_extraction") or {}).get("max_urls_per_document")) or 50
    )

    entities: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    seen_doc_urls: set[tuple[str, str]] = set()

    for field in fields:
        if field not in doc:
            continue

        value = doc.get(field)

        for evidence_text in iter_strings(value):
            urls = extract_urls(evidence_text)
            if not urls:
                continue

            for raw_url in urls:
                if len(seen_doc_urls) >= max_urls_per_document:
                    break

                raw_url = clean_raw_url(raw_url)
                field_relation = infer_relation_from_field(field)
                text_relation = infer_relation_from_text(evidence_text, relation_keywords)
                relation_hint = field_relation or text_relation

                classified = classify_url(
                    raw_url=raw_url,
                    relation_hint=relation_hint,
                    artifact_types_cfg=artifact_types_cfg,
                )

                if not classified:
                    continue

                    # Generic URLs in abstracts are noisy:
                    # XML namespaces, publisher links, formatting URLs and incidental URLs
                    # can be misclassified because the abstract contains words like
                    # "model", "dataset", or "code".
                    # Keep provider-specific links from abstracts, but skip generic ones.
                if field == "abstract" and classified.get("provider") == "generic":
                    continue

                artifact_type = classified["artifact_type"]
                relation_type = relation_from_artifact_type(artifact_type, relation_hint)
                confidence = compute_confidence(
                    artifact_type=artifact_type,
                    source_field=field,
                    evidence_text=evidence_text,
                    relation_type=relation_type,
                    config=config,
                )

                # Artifact observations are paper-linked evidence.
                # If a source-level row cannot be mapped to the current
                # canonical corpus, keep it out of strict extraction output.
                if not canonical_id:
                    continue

                # Unknown relation observations are not useful for trusted
                # paper-artifact materialization and fail strict quality checks.
                if relation_type == "unknown":
                    continue

                dedup_key = (classified["normalized_url"], field)

                dedup_key = (classified["normalized_url"], field)
                if dedup_key in seen_doc_urls:
                    continue
                seen_doc_urls.add(dedup_key)

                entity = make_entity(classified)
                observation = make_observation(
                    entity=entity,
                    raw_url=raw_url,
                    source_layer=source_layer,
                    source_name=source_name,
                    source_doc_id=source_doc_id,
                    canonical_id=canonical_id,
                    source_field=field,
                    evidence_text=evidence_text,
                    relation_type=relation_type,
                    confidence=confidence,
                    line_no=line_no,
                )

                entities.append(entity)
                observations.append(observation)

    return entities, observations


def jsonl_line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def latest_documents_file(source_dir: Path) -> Path | None:
    candidates = sorted(source_dir.glob("documents.*.jsonl"), reverse=True)
    if not candidates:
        return None

    primary_snapshot_re = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")

    primary_candidates = [
        candidate
        for candidate in candidates
        if primary_snapshot_re.match(candidate.name)
    ]

    fallback_candidates = [
        candidate
        for candidate in candidates
        if candidate not in primary_candidates
    ]

    for candidate in primary_candidates + fallback_candidates:
        if jsonl_line_count(candidate) > 0:
            return candidate

    return None


def parse_source_file_overrides(values: list[str]) -> dict[str, Path]:
    overrides: dict[str, Path] = {}

    for value in values:
        if "=" not in value:
            raise ValueError(
                f"Invalid --source-file value: {value!r}. "
                "Expected format: source_name=path/to/documents.jsonl"
            )

        source_name, path_text = value.split("=", 1)
        source_name = source_name.strip()
        path_text = path_text.strip()

        if not source_name:
            raise ValueError(f"Invalid --source-file value without source name: {value!r}")

        if not path_text:
            raise ValueError(f"Invalid --source-file value without path: {value!r}")

        overrides[source_name] = Path(path_text)

    return overrides


def resolve_source_file(
    *,
    source_name: str,
    source_dir: Path,
    config_source_files: dict[str, Any],
    cli_source_files: dict[str, Path],
) -> Path | None:
    if source_name in cli_source_files:
        path = cli_source_files[source_name]
        if not path.exists():
            raise FileNotFoundError(f"CLI source file for {source_name} does not exist: {path}")
        if jsonl_line_count(path) == 0:
            raise ValueError(f"CLI source file for {source_name} is empty: {path}")
        return path

    if source_name in config_source_files:
        path = Path(str(config_source_files[source_name]))
        if not path.exists():
            raise FileNotFoundError(f"Configured source file for {source_name} does not exist: {path}")
        if jsonl_line_count(path) == 0:
            raise ValueError(f"Configured source file for {source_name} is empty: {path}")
        return path

    return latest_documents_file(source_dir)


def load_canonical_doc_id_map(canonical_rows: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for doc in canonical_rows:
        canonical_id = doc.get("canonical_id")
        if not canonical_id:
            continue

        for doc_id in doc.get("doc_ids") or []:
            if doc_id:
                mapping[str(doc_id)] = str(canonical_id)

    return mapping


def deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}

    for entity in entities:
        artifact_id = entity["artifact_id"]

        if artifact_id not in by_id:
            by_id[artifact_id] = entity
        else:
            existing = by_id[artifact_id]
            for key in ["owner", "name", "external_id"]:
                if not existing.get(key) and entity.get(key):
                    existing[key] = entity[key]

    return sorted(
        by_id.values(),
        key=lambda x: (x["provider"], x["artifact_type"], x["normalized_url"]),
    )


def deduplicate_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}

    for obs in observations:
        observation_id = obs["observation_id"]
        if observation_id not in by_id:
            by_id[observation_id] = obs

    return sorted(
        by_id.values(),
        key=lambda x: (
            x.get("canonical_id") or "",
            x.get("provider") or "",
            x.get("artifact_type") or "",
            x.get("normalized_url") or "",
            x.get("source_field") or "",
        ),
    )


def build_report(
    *,
    run_ts: str,
    config_path: Path,
    canonical_path: Path,
    source_files: list[Path],
    canonical_docs_processed: int,
    source_docs_processed: int,
    entities: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    validation_cfg: dict[str, Any],
) -> dict[str, Any]:
    by_type = Counter(e["artifact_type"] for e in entities)
    by_provider = Counter(e["provider"] for e in entities)
    by_relation = Counter(o["relation_type"] for o in observations)
    by_source_layer = Counter(o["source_layer"] for o in observations)
    by_source_field = Counter(o["source_field"] for o in observations)

    linked_canonical_ids = {
        o["canonical_id"]
        for o in observations
        if o.get("canonical_id")
    }

    warnings: list[str] = []

    min_expected_total_links = int(validation_cfg.get("min_expected_total_links", 1))
    if len(observations) < min_expected_total_links:
        warnings.append(
            f"observations_count below expected minimum: {len(observations)} < {min_expected_total_links}"
        )

    if validation_cfg.get("warn_if_no_github_links", True) and by_provider.get("github", 0) == 0:
        warnings.append("no GitHub links found")

    if validation_cfg.get("warn_if_no_huggingface_links", False) and by_provider.get("huggingface", 0) == 0:
        warnings.append("no Hugging Face links found")

    return {
        "report_name": "artifact_links_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "config_path": str(config_path).replace("\\", "/"),
        "canonical_path": str(canonical_path).replace("\\", "/"),
        "source_files": [str(p).replace("\\", "/") for p in source_files],
        "canonical_docs_processed": canonical_docs_processed,
        "source_docs_processed": source_docs_processed,
        "entities_count": len(entities),
        "observations_count": len(observations),
        "linked_canonical_docs_count": len(linked_canonical_ids),
        "by_artifact_type": dict(sorted(by_type.items())),
        "by_provider": dict(sorted(by_provider.items())),
        "by_relation": dict(sorted(by_relation.items())),
        "by_source_layer": dict(sorted(by_source_layer.items())),
        "by_source_field": dict(sorted(by_source_field.items())),
        "warnings": warnings,
        "ok": len(warnings) == 0,
    }


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines: list[str] = []

    lines.append("# Artifact links quality report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Canonical docs processed: **{report['canonical_docs_processed']}**")
    lines.append(f"- Source docs processed: **{report['source_docs_processed']}**")
    lines.append(f"- Artifact entities: **{report['entities_count']}**")
    lines.append(f"- Artifact observations: **{report['observations_count']}**")
    lines.append(f"- Linked canonical docs: **{report['linked_canonical_docs_count']}**")
    lines.append(f"- OK: **{report['ok']}**")
    lines.append("")

    if report["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    def add_counter(title: str, key: str) -> None:
        lines.append(f"## {title}")
        lines.append("")
        rows = report.get(key) or {}
        if not rows:
            lines.append("_empty_")
            lines.append("")
            return

        lines.append("| Value | Count |")
        lines.append("|---|---:|")
        for value, count in rows.items():
            lines.append(f"| `{value}` | {count} |")
        lines.append("")

    add_counter("By provider", "by_provider")
    add_counter("By artifact type", "by_artifact_type")
    add_counter("By relation", "by_relation")
    add_counter("By source layer", "by_source_layer")
    add_counter("By source field", "by_source_field")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract artifact links from canonical and normalized paper records."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical-only", action="store_true")
    parser.add_argument("--source-dir", action="append", default=[])
    parser.add_argument(
        "--source-file",
        action="append",
        default=[],
        help=(
            "Explicit source snapshot file in format source_name=path/to/documents.jsonl. "
            "Can be repeated. Overrides config inputs.source_files and auto-discovery."
        ),
    )
    parser.add_argument("--max-docs", type=int, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = load_yaml(args.config)

    inputs_cfg = config.get("inputs") or {}
    outputs_cfg = config.get("outputs") or {}
    url_cfg = config.get("url_extraction") or {}

    config_source_files = inputs_cfg.get("source_files") or {}
    cli_source_files = parse_source_file_overrides(args.source_file or [])

    canonical_path = Path(
        inputs_cfg.get("canonical_path", "data/analytics/reconciled/canonical_documents.jsonl")
    )
    normalized_dir = Path(inputs_cfg.get("normalized_dir", "data/normalized"))

    enriched_dir = Path(outputs_cfg.get("enriched_dir", "data/enriched/artifact_links"))
    reports_dir = Path(outputs_cfg.get("reports_dir", "artifacts/reports/validation"))
    history_dir = reports_dir / "history"

    include_fields = url_cfg.get("include_fields") or {}

    canonical_fields = include_fields.get("canonical") or [
        "abstract",
        "comment",
        "repo_url",
        "code_links",
        "dataset_links",
        "model_links",
        "external_urls",
        "metadata",
    ]

    source_fields = include_fields.get("source") or [
        "abstract",
        "comment",
        "repo_url",
        "code_links",
        "dataset_links",
        "model_links",
        "external_urls",
        "metadata",
    ]

    if not canonical_path.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {canonical_path}")

    run_ts = utc_now_ts()

    all_entities: list[dict[str, Any]] = []
    all_observations: list[dict[str, Any]] = []

    canonical_rows: list[dict[str, Any]] = []
    canonical_docs_processed = 0

    print(f"[INFO] Loading canonical corpus: {canonical_path}")

    for doc, line_no in iter_jsonl(canonical_path, max_docs=args.max_docs):
        canonical_rows.append(doc)
        canonical_docs_processed += 1

        canonical_id = doc.get("canonical_id")

        entities, observations = extract_artifacts_from_doc(
            doc=doc,
            fields=canonical_fields,
            source_layer="canonical",
            source_name="canonical",
            source_doc_id=None,
            canonical_id=canonical_id,
            line_no=line_no,
            config=config,
        )
        all_entities.extend(entities)
        all_observations.extend(observations)

    doc_id_to_canonical_id = load_canonical_doc_id_map(canonical_rows)

    source_files: list[Path] = []
    source_docs_processed = 0

    if not args.canonical_only:
        source_dirs = args.source_dir or inputs_cfg.get("source_dirs") or DEFAULT_SOURCE_DIRS

        for source_dir_name in source_dirs:
            source_dir = normalized_dir / source_dir_name

            if not source_dir.exists():
                print(f"[WARN] source dir does not exist, skipping: {source_dir}")
                continue

            latest_file = resolve_source_file(
                source_name=source_dir_name,
                source_dir=source_dir,
                config_source_files=config_source_files,
                cli_source_files=cli_source_files,
            )

            if not latest_file:
                print(f"[WARN] no non-empty documents.*.jsonl in source dir, skipping: {source_dir}")
                continue

            source_files.append(latest_file)
            print(f"[INFO] Loading source snapshot: {latest_file}")

            for doc, line_no in iter_jsonl(latest_file, max_docs=args.max_docs):
                source_docs_processed += 1

                source_name = doc.get("source") or source_dir_name
                source_doc_id = doc.get("doc_id")
                canonical_id = doc_id_to_canonical_id.get(str(source_doc_id)) if source_doc_id else None

                entities, observations = extract_artifacts_from_doc(
                    doc=doc,
                    fields=source_fields,
                    source_layer="source",
                    source_name=source_name,
                    source_doc_id=source_doc_id,
                    canonical_id=canonical_id,
                    line_no=line_no,
                    config=config,
                )
                all_entities.extend(entities)
                all_observations.extend(observations)

    entities = deduplicate_entities(all_entities)
    observations = deduplicate_observations(all_observations)

    artifact_entities_path = enriched_dir / f"artifact_entities.{run_ts}.jsonl"
    artifact_links_path = enriched_dir / f"artifact_links.{run_ts}.jsonl"

    artifact_entities_latest = enriched_dir / "artifact_entities_latest.jsonl"
    artifact_links_latest = enriched_dir / "artifact_links_latest.jsonl"

    write_jsonl(artifact_entities_path, entities)
    write_jsonl(artifact_links_path, observations)

    shutil.copyfile(artifact_entities_path, artifact_entities_latest)
    shutil.copyfile(artifact_links_path, artifact_links_latest)

    report = build_report(
        run_ts=run_ts,
        config_path=args.config,
        canonical_path=canonical_path,
        source_files=source_files,
        canonical_docs_processed=canonical_docs_processed,
        source_docs_processed=source_docs_processed,
        entities=entities,
        observations=observations,
        validation_cfg=config.get("validation") or {},
    )

    report_latest_json = reports_dir / "artifact_links_quality_latest.json"
    report_latest_md = reports_dir / "artifact_links_quality_latest.md"
    report_history_json = history_dir / f"artifact_links_quality_{run_ts}.json"
    report_history_md = history_dir / f"artifact_links_quality_{run_ts}.md"

    write_json(report_latest_json, report)
    write_json(report_history_json, report)
    write_markdown_report(report_latest_md, report)
    write_markdown_report(report_history_md, report)

    print(f"[OK] artifact entities: {artifact_entities_path}")
    print(f"[OK] artifact links: {artifact_links_path}")
    print(f"[OK] latest entities: {artifact_entities_latest}")
    print(f"[OK] latest links: {artifact_links_latest}")
    print(f"[OK] report JSON: {report_latest_json}")
    print(f"[OK] report MD: {report_latest_md}")

    print(f"[SUMMARY] canonical_docs_processed={canonical_docs_processed}")
    print(f"[SUMMARY] source_docs_processed={source_docs_processed}")
    print(f"[SUMMARY] entities_count={len(entities)}")
    print(f"[SUMMARY] observations_count={len(observations)}")
    print(f"[SUMMARY] linked_canonical_docs_count={report['linked_canonical_docs_count']}")
    print(f"[SUMMARY] by_provider={report['by_provider']}")
    print(f"[SUMMARY] by_artifact_type={report['by_artifact_type']}")
    print(f"[SUMMARY] warnings={report['warnings']}")

    if args.strict and not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()