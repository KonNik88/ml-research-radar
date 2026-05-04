from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen


DEFAULT_INPUT_PATH = Path("data/enriched/artifact_links/artifact_entities_latest.jsonl")
DEFAULT_OUTPUT_DIR = Path("data/enriched/huggingface_artifacts")
DEFAULT_REPORT_DIR = Path("artifacts/reports/validation")
DEFAULT_TOKEN_ENV = "HF_TOKEN"

USER_AGENT = "ML-Research-Radar-HuggingFace-Enrichment/1.1"

HF_ARTIFACT_TYPES = {
    "huggingface_model": "model",
    "huggingface_dataset": "dataset",
    "huggingface_space": "space",
}

VALID_REPO_TYPES = {"model", "dataset", "space"}

# Conservative Hugging Face repo part pattern.
# Good examples:
#   owner/model-name
#   sentence-transformers/all-MiniLM-L6-v2
#   dcml0714/GSM8K-Zero
REPO_PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

INVALID_REPO_ID_MARKERS = {
    "{",
    "}",
    "[",
    "]",
    "\\",
    "$",
    "`",
    "<",
    ">",
    "http://",
    "https://",
    "www.",
    "%7b",
    "%7d",
    "%5b",
    "%5d",
}

# Common trailing garbage when URLs are extracted from markdown/latex/sentences.
# Important: do not strip "." because dots may be legitimate in HF repo names.
TRAILING_GARBAGE_CHARS = " \t\r\n,;:)]}"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row must be object: {path} line={line_no}")
            rows.append(payload)
    return rows


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _clean_part(value: Any) -> str:
    return str(value or "").strip().strip("/")


def _decode_and_strip_candidate(candidate: str) -> str:
    """
    Decode URL-encoded braces and strip only obvious trailing extraction garbage.

    Example:
      temporal-vqa%7D -> temporal-vqa
      generate-lagrangians%7D -> generate-lagrangians

    But internal garbage remains invalid:
      StreetCLIP}{\\text{StreetCLIP}}$ -> invalid
    """
    decoded = unquote(str(candidate or "").strip())
    return decoded.strip(TRAILING_GARBAGE_CHARS).strip("/")


def infer_repo_type(entity: dict[str, Any]) -> str | None:
    artifact_type = str(entity.get("artifact_type") or "")
    if artifact_type in HF_ARTIFACT_TYPES:
        return HF_ARTIFACT_TYPES[artifact_type]

    external_id = _clean_part(entity.get("external_id"))
    normalized_url = _clean_part(entity.get("normalized_url")).lower()

    if external_id.startswith("datasets/"):
        return "dataset"
    if external_id.startswith("spaces/"):
        return "space"

    if "huggingface.co/datasets/" in normalized_url:
        return "dataset"
    if "huggingface.co/spaces/" in normalized_url:
        return "space"

    if entity.get("provider") == "huggingface":
        return "model"

    return None


def is_collection_url_or_id(entity: dict[str, Any]) -> bool:
    external_id = _clean_part(entity.get("external_id")).lower()
    normalized_url = _clean_part(entity.get("normalized_url")).lower()

    if external_id.startswith("collections/"):
        return True

    parsed = urlparse(normalized_url)
    parts = [part for part in parsed.path.split("/") if part]

    return (
        (parsed.netloc or "").lower() == "huggingface.co"
        and len(parts) >= 1
        and parts[0].lower() == "collections"
    )


def is_valid_hf_repo_id(repo_id: str) -> tuple[bool, str | None]:
    """
    Validate normalized Hugging Face repo id.

    Valid repo_id shape:
      owner/name

    This intentionally excludes:
      collections/...
      dirty LaTeX/markdown tails
      embedded URLs
      brackets/braces
      spaces
      extra slashes
    """
    if not repo_id:
        return False, "empty_repo_id"

    lowered = repo_id.lower()

    for marker in INVALID_REPO_ID_MARKERS:
        if marker in lowered:
            return False, f"invalid_marker:{marker}"

    if any(ch.isspace() for ch in repo_id):
        return False, "contains_whitespace"

    parts = repo_id.split("/")
    if len(parts) != 2:
        return False, "repo_id_must_have_exactly_two_parts"

    owner, name = parts
    if not owner or not name:
        return False, "empty_owner_or_name"

    if owner.lower() in {"datasets", "spaces", "collections", "models"}:
        return False, f"reserved_owner_prefix:{owner}"

    if not REPO_PART_RE.match(owner):
        return False, f"invalid_owner:{owner}"

    if not REPO_PART_RE.match(name):
        return False, f"invalid_name:{name}"

    return True, None


def _external_id_to_candidate(entity: dict[str, Any], repo_type: str) -> str | None:
    external_id = _clean_part(entity.get("external_id"))
    if not external_id:
        return None

    if external_id.lower().startswith("collections/"):
        return external_id

    if repo_type == "dataset" and external_id.startswith("datasets/"):
        return external_id[len("datasets/") :]

    if repo_type == "space" and external_id.startswith("spaces/"):
        return external_id[len("spaces/") :]

    return external_id


def _url_to_candidate(entity: dict[str, Any], repo_type: str) -> str | None:
    normalized_url = _clean_part(entity.get("normalized_url"))
    if not normalized_url:
        return None

    parsed = urlparse(normalized_url)
    host = (parsed.netloc or "").lower()
    parts = [part for part in parsed.path.split("/") if part]

    if host != "huggingface.co":
        return None

    if not parts:
        return None

    if parts[0].lower() == "collections":
        if len(parts) >= 2:
            return f"collections/{parts[1]}"
        return "collections"

    if repo_type == "dataset":
        if len(parts) >= 3 and parts[0] == "datasets":
            return f"{parts[1]}/{parts[2]}"
        return None

    if repo_type == "space":
        if len(parts) >= 3 and parts[0] == "spaces":
            return f"{parts[1]}/{parts[2]}"
        return None

    if repo_type == "model":
        if parts[0] in {"datasets", "spaces", "collections"}:
            return None
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"

    return None


def _owner_name_to_candidate(entity: dict[str, Any]) -> str | None:
    owner = _clean_part(entity.get("owner"))
    name = _clean_part(entity.get("name"))
    if owner and name:
        return f"{owner}/{name}"
    return None


def parse_repo_id(entity: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """
    Return:
      (repo_type, repo_id, invalid_reason)

    repo_type:
      model | dataset | space

    repo_id:
      owner/name

    Invalid rows are still returned with a best-effort repo_id where possible,
    so validation/reporting can preserve what was skipped.
    """
    repo_type = infer_repo_type(entity)

    if repo_type not in VALID_REPO_TYPES:
        return repo_type, None, "cannot_infer_repo_type"

    if is_collection_url_or_id(entity):
        candidate = (
            _external_id_to_candidate(entity, repo_type)
            or _url_to_candidate(entity, repo_type)
            or _owner_name_to_candidate(entity)
            or "collections"
        )
        candidate = _decode_and_strip_candidate(candidate)
        return repo_type, candidate, "unsupported_huggingface_collection_url"

    candidates = [
        _external_id_to_candidate(entity, repo_type),
        _url_to_candidate(entity, repo_type),
        _owner_name_to_candidate(entity),
    ]

    last_candidate: str | None = None
    last_reason: str | None = None

    for candidate in candidates:
        if not candidate:
            continue

        cleaned = _decode_and_strip_candidate(candidate)
        last_candidate = cleaned

        ok, reason = is_valid_hf_repo_id(cleaned)
        if ok:
            return repo_type, cleaned, None

        last_reason = reason

    return repo_type, last_candidate, last_reason or "cannot_parse_valid_repo_id"


def external_id_for_output(repo_type: str | None, repo_id: str | None, entity: dict[str, Any]) -> str | None:
    existing = entity.get("external_id")
    if existing:
        return str(existing)

    if not repo_type or not repo_id:
        return None

    if repo_type == "dataset":
        return f"datasets/{repo_id}"
    if repo_type == "space":
        return f"spaces/{repo_id}"
    return repo_id


def huggingface_api_url(repo_type: str, repo_id: str) -> str:
    repo_q = quote(repo_id, safe="/")
    if repo_type == "dataset":
        return f"https://huggingface.co/api/datasets/{repo_q}"
    if repo_type == "space":
        return f"https://huggingface.co/api/spaces/{repo_q}"
    return f"https://huggingface.co/api/models/{repo_q}"


def normalized_hf_url(repo_type: str, repo_id: str) -> str:
    if repo_type == "dataset":
        return f"https://huggingface.co/datasets/{repo_id}"
    if repo_type == "space":
        return f"https://huggingface.co/spaces/{repo_id}"
    return f"https://huggingface.co/{repo_id}"


def headers_to_dict(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        out[str(key).lower()] = str(value)
    return out


def extract_card_data(payload: dict[str, Any]) -> dict[str, Any] | None:
    card_data = payload.get("cardData")
    if isinstance(card_data, dict):
        return card_data

    card_data = payload.get("card_data")
    if isinstance(card_data, dict):
        return card_data

    return None


def extract_license(payload: dict[str, Any]) -> str | None:
    card_data = extract_card_data(payload) or {}

    for key in ("license", "license_name", "licenseName"):
        value = card_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()

    value = payload.get("license")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()

    tags = payload.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            text = str(tag or "").strip()
            if text.startswith("license:"):
                return text.split(":", 1)[1].strip().lower()

    return None


def normalize_tags(payload: dict[str, Any]) -> list[str]:
    tags = payload.get("tags")
    if not isinstance(tags, list):
        return []
    return sorted({str(tag).strip() for tag in tags if str(tag).strip()})


def normalize_siblings(payload: dict[str, Any], max_items: int = 50) -> list[str]:
    siblings = payload.get("siblings")
    if not isinstance(siblings, list):
        return []

    out: list[str] = []
    for item in siblings[:max_items]:
        if isinstance(item, dict):
            filename = item.get("rfilename") or item.get("filename")
            if filename:
                out.append(str(filename))
        elif isinstance(item, str):
            out.append(item)

    return out


def safe_int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def normalize_found_row(
    *,
    entity: dict[str, Any],
    repo_type: str,
    repo_id: str,
    api_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    fetched_at: str,
) -> dict[str, Any]:
    owner, name = repo_id.split("/", 1)
    card_data = extract_card_data(payload)

    return {
        "artifact_id": entity.get("artifact_id"),
        "provider": "huggingface",
        "artifact_type": entity.get("artifact_type"),
        "repo_type": repo_type,
        "external_id": external_id_for_output(repo_type, repo_id, entity),
        "repo_id": repo_id,
        "owner": owner,
        "name": name,
        "normalized_url": normalized_hf_url(repo_type, repo_id),
        "input_normalized_url": entity.get("normalized_url"),
        "input_external_id": entity.get("external_id"),
        "huggingface_api_url": api_url,
        "fetched_at": fetched_at,
        "status": "found",
        "http_status": 200,
        "description": payload.get("description"),
        "downloads": safe_int_or_none(payload.get("downloads")),
        "likes": safe_int_or_none(payload.get("likes")),
        "tags": normalize_tags(payload),
        "license": extract_license(payload),
        "pipeline_tag": payload.get("pipeline_tag") or payload.get("pipelineTag"),
        "library_name": payload.get("library_name") or payload.get("libraryName"),
        "model_index": payload.get("model-index") or payload.get("model_index"),
        "siblings": normalize_siblings(payload),
        "private": payload.get("private"),
        "gated": payload.get("gated"),
        "disabled": payload.get("disabled"),
        "created_at": payload.get("createdAt") or payload.get("created_at"),
        "updated_at": payload.get("lastModified") or payload.get("last_modified"),
        "last_modified": payload.get("lastModified") or payload.get("last_modified"),
        "metadata": {
            "source": "huggingface_api",
            "enrichment_stage": "huggingface_artifact_enrichment_v1",
            "rate_limit": headers.get("ratelimit"),
            "rate_limit_policy": headers.get("ratelimit-policy"),
            "x_request_id": headers.get("x-request-id"),
            "card_data": card_data,
            "raw_keys": sorted(payload.keys()),
            "input_entity": {
                "artifact_id": entity.get("artifact_id"),
                "artifact_type": entity.get("artifact_type"),
                "external_id": entity.get("external_id"),
                "normalized_url": entity.get("normalized_url"),
                "owner": entity.get("owner"),
                "name": entity.get("name"),
            },
        },
    }


def error_row(
    *,
    entity: dict[str, Any],
    repo_type: str | None,
    repo_id: str | None,
    api_url: str | None,
    fetched_at: str,
    status: str,
    http_status: int | None = None,
    error: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = headers or {}

    owner = entity.get("owner")
    name = entity.get("name")
    if repo_id and "/" in repo_id:
        owner, name = repo_id.split("/", 1)

    return {
        "artifact_id": entity.get("artifact_id"),
        "provider": "huggingface",
        "artifact_type": entity.get("artifact_type"),
        "repo_type": repo_type,
        "external_id": external_id_for_output(repo_type, repo_id, entity),
        "repo_id": repo_id,
        "owner": owner,
        "name": name,
        "normalized_url": entity.get("normalized_url"),
        "input_normalized_url": entity.get("normalized_url"),
        "input_external_id": entity.get("external_id"),
        "huggingface_api_url": api_url,
        "fetched_at": fetched_at,
        "status": status,
        "http_status": http_status,
        "error": error,
        "metadata": {
            "source": "huggingface_api",
            "enrichment_stage": "huggingface_artifact_enrichment_v1",
            "rate_limit": headers.get("ratelimit"),
            "rate_limit_policy": headers.get("ratelimit-policy"),
            "x_request_id": headers.get("x-request-id"),
            "input_entity": {
                "artifact_id": entity.get("artifact_id"),
                "artifact_type": entity.get("artifact_type"),
                "external_id": entity.get("external_id"),
                "normalized_url": entity.get("normalized_url"),
                "owner": entity.get("owner"),
                "name": entity.get("name"),
            },
        },
    }


def classify_http_error(exc: HTTPError, headers: dict[str, str]) -> str:
    if exc.code == 404:
        return "not_found"
    if exc.code == 429:
        return "rate_limited"
    if exc.code in {401, 403}:
        return "forbidden"
    return "error"


def fetch_huggingface_repo(
    *,
    entity: dict[str, Any],
    repo_type: str,
    repo_id: str,
    token: str | None,
    timeout_sec: float,
) -> dict[str, Any]:
    fetched_at = utc_now_iso()
    api_url = huggingface_api_url(repo_type, repo_id)

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(api_url, headers=headers, method="GET")

    try:
        with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310 - controlled HF API URL
            response_headers = headers_to_dict(response.headers)
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                return error_row(
                    entity=entity,
                    repo_type=repo_type,
                    repo_id=repo_id,
                    api_url=api_url,
                    fetched_at=fetched_at,
                    status="error",
                    http_status=200,
                    error="HF API response is not JSON object",
                    headers=response_headers,
                )

            return normalize_found_row(
                entity=entity,
                repo_type=repo_type,
                repo_id=repo_id,
                api_url=api_url,
                payload=payload,
                headers=response_headers,
                fetched_at=fetched_at,
            )

    except HTTPError as exc:
        response_headers = headers_to_dict(exc.headers)
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
            message = error_payload.get("error") or error_payload.get("message") or repr(exc)
        except Exception:
            message = repr(exc)

        status = classify_http_error(exc, response_headers)
        return error_row(
            entity=entity,
            repo_type=repo_type,
            repo_id=repo_id,
            api_url=api_url,
            fetched_at=fetched_at,
            status=status,
            http_status=exc.code,
            error=message,
            headers=response_headers,
        )

    except URLError as exc:
        return error_row(
            entity=entity,
            repo_type=repo_type,
            repo_id=repo_id,
            api_url=api_url,
            fetched_at=fetched_at,
            status="error",
            http_status=None,
            error=repr(exc),
        )

    except Exception as exc:
        return error_row(
            entity=entity,
            repo_type=repo_type,
            repo_id=repo_id,
            api_url=api_url,
            fetched_at=fetched_at,
            status="error",
            http_status=None,
            error=repr(exc),
        )


def select_huggingface_entities(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if row.get("provider") == "huggingface"
        and row.get("artifact_type") in HF_ARTIFACT_TYPES
    ]
    selected.sort(
        key=lambda x: (
            str(x.get("artifact_type") or ""),
            str(x.get("owner") or "").lower(),
            str(x.get("name") or "").lower(),
            str(x.get("artifact_id") or ""),
        )
    )
    if limit is not None:
        selected = selected[:limit]
    return selected


def build_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Hugging Face artifact enrichment report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Dry run: `{report['dry_run']}`")
    lines.append(f"- Input path: `{report['input_path']}`")
    lines.append(f"- Output path: `{report.get('output_path')}`")
    lines.append(f"- Token present: `{report['token_present']}`")
    lines.append("")
    lines.append("## Counts")
    for key in (
        "input_entities_count",
        "huggingface_entities_count",
        "requested_count",
        "processed_count",
        "found_count",
        "not_found_count",
        "forbidden_count",
        "rate_limited_count",
        "error_count",
        "skipped_invalid_external_id_count",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")

    lines.append("")
    lines.append("## Artifact type distribution")
    for key, value in sorted(report.get("artifact_type_distribution", {}).items()):
        lines.append(f"- {key}: `{value}`")

    lines.append("")
    lines.append("## Repo type distribution")
    for key, value in sorted(report.get("repo_type_distribution", {}).items()):
        lines.append(f"- {key}: `{value}`")

    lines.append("")
    lines.append("## Status distribution")
    for key, value in sorted(report.get("status_distribution", {}).items()):
        lines.append(f"- {key}: `{value}`")

    lines.append("")
    lines.append("## Verdict")
    lines.append(f"- ok: `{report['ok']}`")
    if report.get("warnings"):
        lines.append("- warnings:")
        for warning in report["warnings"]:
            lines.append(f"  - `{warning}`")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich extracted Hugging Face artifact entities with Hugging Face Hub API metadata."
    )
    parser.add_argument("--input-path", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Limit number of Hugging Face repos to process.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan requests and write report, but do not call Hugging Face API or write metadata JSONL.",
    )
    parser.add_argument("--sleep-sec", type=float, default=0.2, help="Delay between Hugging Face API requests.")
    parser.add_argument("--timeout-sec", type=float, default=30.0, help="HTTP timeout per Hugging Face API request.")
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV, help="Environment variable containing Hugging Face token.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    if not args.input_path.exists():
        raise FileNotFoundError(f"Artifact entities file not found: {args.input_path}")

    token = os.getenv(args.token_env)
    token_present = bool(token)

    all_entities = load_jsonl(args.input_path)
    hf_entities_all = select_huggingface_entities(all_entities, limit=None)
    hf_entities = select_huggingface_entities(all_entities, limit=args.limit)

    output_path = args.output_dir / f"huggingface_artifact_metadata.{run_ts}.jsonl"
    latest_output_path = args.output_dir / "huggingface_artifact_metadata_latest.jsonl"

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    print(f"[INFO] input_path={args.input_path}")
    print(f"[INFO] input_entities={len(all_entities)}")
    print(f"[INFO] huggingface_entities_total={len(hf_entities_all)}")
    print(f"[INFO] requested_count={len(hf_entities)}")
    print(f"[INFO] dry_run={args.dry_run}")
    print(f"[INFO] token_present={token_present}")

    if args.dry_run:
        skipped_invalid = 0
        for entity in hf_entities:
            repo_type, repo_id, invalid_reason = parse_repo_id(entity)
            if invalid_reason or not repo_type or not repo_id:
                skipped_invalid += 1
                print(
                    "[DRY-RUN] would skip "
                    f"artifact_id={entity.get('artifact_id')} "
                    f"repo_type={repo_type} repo_id={repo_id} "
                    f"reason={invalid_reason}"
                )
                continue
            print(f"[DRY-RUN] would fetch {huggingface_api_url(repo_type, repo_id)}")
        if skipped_invalid:
            warnings.append(f"dry_run_skipped_invalid_count={skipped_invalid}")
    else:
        for idx, entity in enumerate(hf_entities, start=1):
            repo_type, repo_id, invalid_reason = parse_repo_id(entity)

            if invalid_reason or not repo_type or not repo_id:
                rows.append(
                    error_row(
                        entity=entity,
                        repo_type=repo_type,
                        repo_id=repo_id,
                        api_url=None,
                        fetched_at=utc_now_iso(),
                        status="skipped_invalid_external_id",
                        error=invalid_reason or "invalid_repo_id",
                    )
                )
                print(
                    "[WARN] "
                    f"({idx}/{len(hf_entities)}) skipping invalid HF artifact "
                    f"repo_type={repo_type} repo_id={repo_id} reason={invalid_reason}"
                )
                continue

            print(f"[INFO] ({idx}/{len(hf_entities)}) fetching {repo_type}:{repo_id}")
            row = fetch_huggingface_repo(
                entity=entity,
                repo_type=repo_type,
                repo_id=repo_id,
                token=token,
                timeout_sec=args.timeout_sec,
            )
            rows.append(row)

            if row.get("status") == "rate_limited":
                warnings.append(f"rate_limited at {repo_type}:{repo_id}")
                print(f"[WARN] rate_limited at {repo_type}:{repo_id}")
                break

            if idx < len(hf_entities) and args.sleep_sec > 0:
                time.sleep(args.sleep_sec)

        write_jsonl(output_path, rows)
        write_jsonl(latest_output_path, rows)

    status_distribution = Counter(str(row.get("status") or "missing_status") for row in rows)
    artifact_type_distribution = Counter(
        str(row.get("artifact_type") or "missing_artifact_type")
        for row in hf_entities_all
    )
    repo_type_distribution = Counter(
        str(infer_repo_type(entity) or "unknown")
        for entity in hf_entities_all
    )

    found_count = status_distribution.get("found", 0)
    not_found_count = status_distribution.get("not_found", 0)
    forbidden_count = status_distribution.get("forbidden", 0)
    rate_limited_count = status_distribution.get("rate_limited", 0)
    error_count = status_distribution.get("error", 0)
    skipped_invalid_count = status_distribution.get("skipped_invalid_external_id", 0)

    if len(hf_entities_all) == 0:
        warnings.append("no Hugging Face artifact entities found")

    ok = (
        len(hf_entities_all) > 0
        and (
            args.dry_run
            or (
                len(rows) > 0
                and rate_limited_count == 0
                and error_count == 0
            )
        )
    )

    report = {
        "report_name": "huggingface_artifact_enrichment",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "dry_run": bool(args.dry_run),
        "input_path": normalize_path(args.input_path),
        "output_path": None if args.dry_run else normalize_path(output_path),
        "latest_output_path": None if args.dry_run else normalize_path(latest_output_path),
        "token_present": token_present,
        "input_entities_count": len(all_entities),
        "huggingface_entities_count": len(hf_entities_all),
        "requested_count": len(hf_entities),
        "processed_count": len(rows),
        "found_count": found_count,
        "not_found_count": not_found_count,
        "forbidden_count": forbidden_count,
        "rate_limited_count": rate_limited_count,
        "error_count": error_count,
        "skipped_invalid_external_id_count": skipped_invalid_count,
        "status_distribution": dict(sorted(status_distribution.items())),
        "artifact_type_distribution": dict(sorted(artifact_type_distribution.items())),
        "repo_type_distribution": dict(sorted(repo_type_distribution.items())),
        "warnings": sorted(set(warnings)),
        "ok": ok,
    }

    latest_json = args.report_dir / "huggingface_artifact_enrichment_latest.json"
    latest_md = args.report_dir / "huggingface_artifact_enrichment_latest.md"
    history_json = args.report_dir / "history" / f"huggingface_artifact_enrichment_{run_ts}.json"
    history_md = args.report_dir / "history" / f"huggingface_artifact_enrichment_{run_ts}.md"

    write_json(latest_json, report)
    write_json(history_json, report)
    write_text(latest_md, build_markdown_report(report))
    write_text(history_md, build_markdown_report(report))

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")
    if not args.dry_run:
        print(f"[OK] output JSONL: {output_path}")
        print(f"[OK] latest JSONL: {latest_output_path}")

    print(f"[SUMMARY] huggingface_entities_count={len(hf_entities_all)}")
    print(f"[SUMMARY] requested_count={len(hf_entities)}")
    print(f"[SUMMARY] processed_count={len(rows)}")
    print(f"[SUMMARY] found_count={found_count}")
    print(f"[SUMMARY] not_found_count={not_found_count}")
    print(f"[SUMMARY] forbidden_count={forbidden_count}")
    print(f"[SUMMARY] rate_limited_count={rate_limited_count}")
    print(f"[SUMMARY] error_count={error_count}")
    print(f"[SUMMARY] skipped_invalid_external_id_count={skipped_invalid_count}")
    print(f"[SUMMARY] ok={ok}")

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()