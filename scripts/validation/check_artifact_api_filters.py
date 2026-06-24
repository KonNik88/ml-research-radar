from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")
DEFAULT_TOP_K = 5
DEFAULT_BACKEND_MODE = "db"
ARTIFACT_PROVIDER = "github"
ARTIFACT_STATUS_FOUND = "found"
MIN_STARS_FALLBACK = 1
DATE_RANGE_AFTER_INVALID = "2030-01-01T00:00:00Z"
DATE_RANGE_BEFORE_INVALID = "2000-01-01T00:00:00Z"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_non_empty_dict(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def request_json(
    client: TestClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.get(path, params=params)

    payload: Any
    try:
        payload = response.json()
    except Exception:
        payload = None

    return {
        "path": path,
        "params": params or {},
        "status_code": response.status_code,
        "ok": 200 <= response.status_code < 300,
        "json": payload,
    }


def endpoint_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "json"}


def result_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("json")
    return payload if isinstance(payload, dict) else {}


def payload_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    return [row for row in results if isinstance(row, dict)]


def github_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    github = metadata.get("github")
    return github if isinstance(github, dict) else {}


def timestamps_from_rows(rows: list[dict[str, Any]], field_name: str) -> list[datetime]:
    values: list[datetime] = []
    for row in rows:
        raw_value = row.get(field_name)
        parsed = parse_timestamp(raw_value if isinstance(raw_value, str) else None)
        if parsed is not None:
            values.append(parsed)
    return values


def pushed_timestamps_from_rows(rows: list[dict[str, Any]]) -> list[datetime]:
    values: list[datetime] = []
    for row in rows:
        pushed_at = github_metadata(row).get("pushed_at")
        parsed = parse_timestamp(pushed_at if isinstance(pushed_at, str) else None)
        if parsed is not None:
            values.append(parsed)
    return values


def is_sorted_desc(values: list[datetime | float | int]) -> bool:
    return values == sorted(values, reverse=True)


def stars_from_rows(rows: list[dict[str, Any]]) -> list[int]:
    return [safe_int(row.get("stars")) for row in rows]


def forks_from_rows(rows: list[dict[str, Any]]) -> list[int]:
    return [safe_int(row.get("forks")) for row in rows]


def first_language(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        language = github_metadata(row).get("language")
        if isinstance(language, str) and language.strip():
            return language.strip()
    return None


def first_artifact_id(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        artifact_id = row.get("artifact_id")
        if artifact_id:
            return str(artifact_id)
    return None


def first_canonical_id(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        canonical_id = row.get("canonical_id")
        if canonical_id:
            return str(canonical_id)
    return None


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Artifact API filters check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Endpoints")
    for name, payload in report["endpoints"].items():
        lines.append(f"### {name}")
        lines.append(f"- path: `{payload.get('path')}`")
        lines.append(f"- params: `{payload.get('params')}`")
        lines.append(f"- status_code: `{payload.get('status_code')}`")
        lines.append(f"- ok: `{payload.get('ok')}`")
        if payload.get("error"):
            lines.append(f"- error: `{payload.get('error')}`")
        lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate DB-backed Artifact API filters and linked document-artifact "
            "endpoints. This check uses FastAPI TestClient, does not call external "
            "artifact providers, and does not mutate canonical or retrieval data."
        )
    )
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--backend-mode",
        choices=["db"],
        default=DEFAULT_BACKEND_MODE,
        help="Artifact API filters are DB-backed and require db backend mode.",
    )
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    os.environ["ML_RADAR_SEARCH_BACKEND"] = args.backend_mode

    # Import after env setup, because services.api.app initializes settings/runtime.
    from services.api.settings import get_settings  # noqa: WPS433

    get_settings.cache_clear()

    from services.api.app import app  # noqa: WPS433

    endpoints: dict[str, dict[str, Any]] = {}

    with TestClient(app) as client:
        runtime = request_json(client, "/runtime")
        endpoints["runtime"] = endpoint_meta(runtime)

        artifacts_github = request_json(
            client,
            "/artifacts",
            params={"provider": ARTIFACT_PROVIDER, "limit": args.top_k},
        )
        endpoints["artifacts_provider_github"] = endpoint_meta(artifacts_github)

        artifacts_has_github_metadata = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "has_github_metadata": "true",
                "limit": args.top_k,
            },
        )
        endpoints["artifacts_has_github_metadata"] = endpoint_meta(
            artifacts_has_github_metadata
        )

        artifacts_status_found = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "github_status": ARTIFACT_STATUS_FOUND,
                "limit": args.top_k,
            },
        )
        endpoints["artifacts_github_status_found"] = endpoint_meta(
            artifacts_status_found
        )

        artifacts_stars_source = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "github_status": ARTIFACT_STATUS_FOUND,
                "sort_by": "stars_desc",
                "limit": args.top_k,
            },
        )
        endpoints["artifacts_stars_desc_source"] = endpoint_meta(artifacts_stars_source)

        artifacts_forks_source = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "github_status": ARTIFACT_STATUS_FOUND,
                "sort_by": "forks_desc",
                "limit": args.top_k,
            },
        )
        endpoints["artifacts_forks_desc_source"] = endpoint_meta(artifacts_forks_source)

        metadata_rows = payload_results(result_payload(artifacts_has_github_metadata))
        language_filter_value = first_language(metadata_rows)

        if language_filter_value:
            artifacts_language = request_json(
                client,
                "/artifacts",
                params={
                    "provider": ARTIFACT_PROVIDER,
                    "language": language_filter_value,
                    "limit": args.top_k,
                },
            )
        else:
            artifacts_language = {
                "path": "/artifacts",
                "params": {"provider": ARTIFACT_PROVIDER, "language": None},
                "status_code": None,
                "ok": False,
                "json": None,
                "error": "No language value resolved from GitHub metadata sample.",
            }
        endpoints["artifacts_language"] = endpoint_meta(artifacts_language)

        artifacts_archived_false = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "archived": "false",
                "limit": args.top_k,
            },
        )
        endpoints["artifacts_archived_false"] = endpoint_meta(artifacts_archived_false)

        star_rows = payload_results(result_payload(artifacts_stars_source))
        star_values = [value for value in stars_from_rows(star_rows) if value > 0]
        min_stars_threshold = min(star_values) if star_values else MIN_STARS_FALLBACK

        artifacts_min_stars = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "min_stars": min_stars_threshold,
                "sort_by": "stars_desc",
                "limit": args.top_k,
            },
        )
        endpoints["artifacts_min_stars"] = endpoint_meta(artifacts_min_stars)

        artifacts_pushed_desc = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "github_status": ARTIFACT_STATUS_FOUND,
                "sort_by": "pushed_desc",
                "limit": args.top_k,
            },
        )
        endpoints["artifacts_pushed_desc"] = endpoint_meta(artifacts_pushed_desc)

        pushed_rows = payload_results(result_payload(artifacts_pushed_desc))
        pushed_values = pushed_timestamps_from_rows(pushed_rows)
        pushed_after_threshold_raw = None
        if pushed_rows:
            for row in reversed(pushed_rows):
                pushed_after_threshold_raw = github_metadata(row).get("pushed_at")
                if pushed_after_threshold_raw:
                    break

        if pushed_after_threshold_raw:
            artifacts_pushed_after = request_json(
                client,
                "/artifacts",
                params={
                    "provider": ARTIFACT_PROVIDER,
                    "pushed_after": pushed_after_threshold_raw,
                    "sort_by": "pushed_desc",
                    "limit": args.top_k,
                },
            )
        else:
            artifacts_pushed_after = {
                "path": "/artifacts",
                "params": {"provider": ARTIFACT_PROVIDER, "pushed_after": None},
                "status_code": None,
                "ok": False,
                "json": None,
                "error": "No pushed_at value resolved from GitHub artifact sample.",
            }
        endpoints["artifacts_pushed_after"] = endpoint_meta(artifacts_pushed_after)

        artifacts_updated_desc = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "github_status": ARTIFACT_STATUS_FOUND,
                "sort_by": "updated_desc",
                "limit": args.top_k,
            },
        )
        endpoints["artifacts_updated_desc"] = endpoint_meta(artifacts_updated_desc)

        updated_rows = payload_results(result_payload(artifacts_updated_desc))
        updated_values = timestamps_from_rows(updated_rows, "updated_at")
        updated_before_threshold_raw = None
        if updated_rows:
            for row in updated_rows:
                updated_before_threshold_raw = row.get("updated_at")
                if updated_before_threshold_raw:
                    break

        if updated_before_threshold_raw:
            artifacts_updated_before = request_json(
                client,
                "/artifacts",
                params={
                    "provider": ARTIFACT_PROVIDER,
                    "updated_before": updated_before_threshold_raw,
                    "sort_by": "updated_desc",
                    "limit": args.top_k,
                },
            )
        else:
            artifacts_updated_before = {
                "path": "/artifacts",
                "params": {"provider": ARTIFACT_PROVIDER, "updated_before": None},
                "status_code": None,
                "ok": False,
                "json": None,
                "error": "No updated_at value resolved from GitHub artifact sample.",
            }
        endpoints["artifacts_updated_before"] = endpoint_meta(
            artifacts_updated_before
        )

        artifacts_pushed_invalid_range = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "pushed_after": DATE_RANGE_AFTER_INVALID,
                "pushed_before": DATE_RANGE_BEFORE_INVALID,
            },
        )
        endpoints["artifacts_pushed_invalid_range"] = endpoint_meta(
            artifacts_pushed_invalid_range
        )

        artifacts_updated_invalid_range = request_json(
            client,
            "/artifacts",
            params={
                "provider": ARTIFACT_PROVIDER,
                "updated_after": DATE_RANGE_AFTER_INVALID,
                "updated_before": DATE_RANGE_BEFORE_INVALID,
            },
        )
        endpoints["artifacts_updated_invalid_range"] = endpoint_meta(
            artifacts_updated_invalid_range
        )

        artifact_id = first_artifact_id(payload_results(result_payload(artifacts_github)))
        if artifact_id:
            artifact_detail = request_json(client, f"/artifacts/{artifact_id}")
            artifact_linked_papers = request_json(
                client,
                f"/artifacts/{artifact_id}/papers",
                params={"limit": args.top_k, "sort_by": "confidence_desc"},
            )
        else:
            artifact_detail = {
                "path": "/artifacts/{artifact_id}",
                "params": {},
                "status_code": None,
                "ok": False,
                "json": None,
                "error": "No artifact_id resolved from GitHub artifact sample.",
            }
            artifact_linked_papers = {
                "path": "/artifacts/{artifact_id}/papers",
                "params": {},
                "status_code": None,
                "ok": False,
                "json": None,
                "error": "No artifact_id resolved from GitHub artifact sample.",
            }
        endpoints["artifact_detail"] = endpoint_meta(artifact_detail)
        endpoints["artifact_linked_papers"] = endpoint_meta(artifact_linked_papers)

        documents_has_trusted_artifact = request_json(
            client,
            "/documents",
            params={"has_trusted_artifact": "true", "limit": args.top_k},
        )
        endpoints["documents_has_trusted_artifact"] = endpoint_meta(
            documents_has_trusted_artifact
        )

        documents_artifact_provider_github = request_json(
            client,
            "/documents",
            params={"artifact_provider": ARTIFACT_PROVIDER, "limit": args.top_k},
        )
        endpoints["documents_artifact_provider_github"] = endpoint_meta(
            documents_artifact_provider_github
        )

        canonical_id = first_canonical_id(
            payload_results(result_payload(documents_artifact_provider_github))
        )
        if canonical_id:
            document_artifacts = request_json(
                client,
                f"/documents/{canonical_id}/artifacts",
                params={"provider": ARTIFACT_PROVIDER},
            )
        else:
            document_artifacts = {
                "path": "/documents/{canonical_id}/artifacts",
                "params": {"provider": ARTIFACT_PROVIDER},
                "status_code": None,
                "ok": False,
                "json": None,
                "error": "No canonical_id resolved from artifact_provider=github sample.",
            }
        endpoints["document_artifacts_provider_github"] = endpoint_meta(
            document_artifacts
        )

    runtime_payload = result_payload(runtime)
    artifacts_github_payload = result_payload(artifacts_github)
    artifacts_github_rows = payload_results(artifacts_github_payload)
    has_metadata_payload = result_payload(artifacts_has_github_metadata)
    has_metadata_rows = payload_results(has_metadata_payload)
    status_found_payload = result_payload(artifacts_status_found)
    status_found_rows = payload_results(status_found_payload)
    stars_source_payload = result_payload(artifacts_stars_source)
    stars_source_rows = payload_results(stars_source_payload)
    forks_source_payload = result_payload(artifacts_forks_source)
    forks_source_rows = payload_results(forks_source_payload)
    language_payload = result_payload(artifacts_language)
    language_rows = payload_results(language_payload)
    archived_false_payload = result_payload(artifacts_archived_false)
    archived_false_rows = payload_results(archived_false_payload)
    min_stars_payload = result_payload(artifacts_min_stars)
    min_stars_rows = payload_results(min_stars_payload)
    pushed_after_payload = result_payload(artifacts_pushed_after)
    pushed_after_rows = payload_results(pushed_after_payload)
    updated_before_payload = result_payload(artifacts_updated_before)
    updated_before_rows = payload_results(updated_before_payload)
    artifact_detail_payload = result_payload(artifact_detail)
    artifact_detail_body = artifact_detail_payload.get("artifact")
    artifact_detail_body = (
        artifact_detail_body if isinstance(artifact_detail_body, dict) else {}
    )
    artifact_linked_papers_payload = result_payload(artifact_linked_papers)
    artifact_linked_papers_rows = payload_results(artifact_linked_papers_payload)
    documents_has_trusted_payload = result_payload(documents_has_trusted_artifact)
    documents_has_trusted_rows = payload_results(documents_has_trusted_payload)
    documents_github_payload = result_payload(documents_artifact_provider_github)
    documents_github_rows = payload_results(documents_github_payload)
    document_artifacts_payload = result_payload(document_artifacts)
    document_artifacts_rows = payload_results(document_artifacts_payload)

    pushed_after_threshold = parse_timestamp(
        pushed_after_threshold_raw if isinstance(pushed_after_threshold_raw, str) else None
    )
    updated_before_threshold = parse_timestamp(
        updated_before_threshold_raw
        if isinstance(updated_before_threshold_raw, str)
        else None
    )

    pushed_after_values = pushed_timestamps_from_rows(pushed_after_rows)
    updated_before_values = timestamps_from_rows(updated_before_rows, "updated_at")

    checks: dict[str, bool] = {
        "runtime_endpoint_ok": bool(runtime.get("ok")),
        "runtime_db_ready": (
            runtime_payload.get("ready") is True
            and runtime_payload.get("backend_mode") == "db"
            and runtime_payload.get("db_connected") is True
        ),
        "artifacts_provider_github_endpoint_ok": bool(artifacts_github.get("ok")),
        "artifacts_provider_github_results_non_empty": len(artifacts_github_rows) > 0,
        "artifacts_provider_github_rows_match": (
            len(artifacts_github_rows) > 0
            and all(
                row.get("provider") == ARTIFACT_PROVIDER
                and row.get("artifact_type") == "github_repository"
                for row in artifacts_github_rows
            )
        ),
        "artifacts_has_github_metadata_endpoint_ok": bool(
            artifacts_has_github_metadata.get("ok")
        ),
        "artifacts_has_github_metadata_results_non_empty": len(has_metadata_rows) > 0,
        "artifacts_has_github_metadata_rows_match": (
            len(has_metadata_rows) > 0
            and all(is_non_empty_dict(github_metadata(row)) for row in has_metadata_rows)
        ),
        "artifacts_github_status_found_endpoint_ok": bool(artifacts_status_found.get("ok")),
        "artifacts_github_status_found_results_non_empty": len(status_found_rows) > 0,
        "artifacts_github_status_found_rows_match": (
            len(status_found_rows) > 0
            and all(
                github_metadata(row).get("status") == ARTIFACT_STATUS_FOUND
                for row in status_found_rows
            )
        ),
        "artifacts_stars_desc_endpoint_ok": bool(artifacts_stars_source.get("ok")),
        "artifacts_stars_desc_sorted": (
            len(stars_source_rows) > 0
            and is_sorted_desc(stars_from_rows(stars_source_rows))
        ),
        "artifacts_forks_desc_endpoint_ok": bool(artifacts_forks_source.get("ok")),
        "artifacts_forks_desc_sorted": (
            len(forks_source_rows) > 0
            and is_sorted_desc(forks_from_rows(forks_source_rows))
        ),
        "artifacts_min_stars_endpoint_ok": bool(artifacts_min_stars.get("ok")),
        "artifacts_min_stars_results_non_empty": len(min_stars_rows) > 0,
        "artifacts_min_stars_rows_match": (
            len(min_stars_rows) > 0
            and all(safe_int(row.get("stars")) >= min_stars_threshold for row in min_stars_rows)
        ),
        "artifacts_min_stars_sorted": (
            len(min_stars_rows) > 0 and is_sorted_desc(stars_from_rows(min_stars_rows))
        ),
        "artifacts_language_value_resolved": bool(language_filter_value),
        "artifacts_language_endpoint_ok": bool(artifacts_language.get("ok")),
        "artifacts_language_results_non_empty": len(language_rows) > 0,
        "artifacts_language_rows_match": (
            bool(language_filter_value)
            and len(language_rows) > 0
            and all(
                str(github_metadata(row).get("language") or "").lower()
                == str(language_filter_value).lower()
                for row in language_rows
            )
        ),
        "artifacts_archived_false_endpoint_ok": bool(artifacts_archived_false.get("ok")),
        "artifacts_archived_false_results_non_empty": len(archived_false_rows) > 0,
        "artifacts_archived_false_rows_match": (
            len(archived_false_rows) > 0
            and all(github_metadata(row).get("archived") is False for row in archived_false_rows)
        ),
        "artifacts_pushed_desc_endpoint_ok": bool(artifacts_pushed_desc.get("ok")),
        "artifacts_pushed_desc_results_non_empty": len(pushed_rows) > 0,
        "artifacts_pushed_desc_values_present": len(pushed_values) == len(pushed_rows) > 0,
        "artifacts_pushed_desc_sorted": len(pushed_values) > 0 and is_sorted_desc(pushed_values),
        "artifacts_pushed_after_threshold_resolved": pushed_after_threshold is not None,
        "artifacts_pushed_after_endpoint_ok": bool(artifacts_pushed_after.get("ok")),
        "artifacts_pushed_after_results_non_empty": len(pushed_after_rows) > 0,
        "artifacts_pushed_after_rows_match": (
            pushed_after_threshold is not None
            and len(pushed_after_values) == len(pushed_after_rows) > 0
            and all(value >= pushed_after_threshold for value in pushed_after_values)
        ),
        "artifacts_pushed_after_sorted": (
            len(pushed_after_values) > 0 and is_sorted_desc(pushed_after_values)
        ),
        "artifacts_updated_desc_endpoint_ok": bool(artifacts_updated_desc.get("ok")),
        "artifacts_updated_desc_results_non_empty": len(updated_rows) > 0,
        "artifacts_updated_desc_values_present": len(updated_values) == len(updated_rows) > 0,
        "artifacts_updated_desc_sorted": len(updated_values) > 0 and is_sorted_desc(updated_values),
        "artifacts_updated_before_threshold_resolved": updated_before_threshold is not None,
        "artifacts_updated_before_endpoint_ok": bool(artifacts_updated_before.get("ok")),
        "artifacts_updated_before_results_non_empty": len(updated_before_rows) > 0,
        "artifacts_updated_before_rows_match": (
            updated_before_threshold is not None
            and len(updated_before_values) == len(updated_before_rows) > 0
            and all(value <= updated_before_threshold for value in updated_before_values)
        ),
        "artifacts_updated_before_sorted": (
            len(updated_before_values) > 0 and is_sorted_desc(updated_before_values)
        ),
        "artifacts_pushed_invalid_range_returns_400": (
            artifacts_pushed_invalid_range.get("status_code") == 400
        ),
        "artifacts_updated_invalid_range_returns_400": (
            artifacts_updated_invalid_range.get("status_code") == 400
        ),
        "artifact_id_resolved": bool(artifact_id),
        "artifact_detail_endpoint_ok": bool(artifact_detail.get("ok")),
        "artifact_detail_found": (
            artifact_detail_payload.get("found") is True
            and artifact_detail_payload.get("artifact_id") == artifact_id
            and artifact_detail_body.get("artifact_id") == artifact_id
        ),
        "artifact_linked_papers_endpoint_ok": bool(artifact_linked_papers.get("ok")),
        "artifact_linked_papers_results_non_empty": len(artifact_linked_papers_rows) > 0,
        "artifact_linked_papers_rows_match": (
            len(artifact_linked_papers_rows) > 0
            and all(
                row.get("artifact_id") == artifact_id
                and bool(row.get("canonical_id"))
                and isinstance(row.get("paper"), dict)
                and row["paper"].get("canonical_id") == row.get("canonical_id")
                for row in artifact_linked_papers_rows
            )
        ),
        "documents_has_trusted_artifact_endpoint_ok": bool(
            documents_has_trusted_artifact.get("ok")
        ),
        "documents_has_trusted_artifact_results_non_empty": (
            len(documents_has_trusted_rows) > 0
        ),
        "documents_artifact_provider_github_endpoint_ok": bool(
            documents_artifact_provider_github.get("ok")
        ),
        "documents_artifact_provider_github_results_non_empty": len(documents_github_rows) > 0,
        "canonical_id_resolved": bool(canonical_id),
        "document_artifacts_endpoint_ok": bool(document_artifacts.get("ok")),
        "document_artifacts_results_non_empty": len(document_artifacts_rows) > 0,
        "document_artifacts_rows_match": (
            bool(canonical_id)
            and len(document_artifacts_rows) > 0
            and all(
                row.get("canonical_id") == canonical_id
                and isinstance(row.get("artifact"), dict)
                and row["artifact"].get("provider") == ARTIFACT_PROVIDER
                for row in document_artifacts_rows
            )
        ),
    }

    required_check_names = list(checks.keys())
    required_failed_checks = [name for name in required_check_names if not checks[name]]

    report = {
        "report_name": "artifact_api_filters_check",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "reports_dir": normalize_path(args.reports_dir),
            "backend_mode": args.backend_mode,
            "top_k": args.top_k,
            "artifact_provider": ARTIFACT_PROVIDER,
            "artifact_status_found": ARTIFACT_STATUS_FOUND,
        },
        "summary": {
            "runtime_backend_mode": runtime_payload.get("backend_mode"),
            "runtime_ready": runtime_payload.get("ready"),
            "runtime_db_connected": runtime_payload.get("db_connected"),
            "artifacts_provider_github_total": artifacts_github_payload.get("total"),
            "artifacts_provider_github_results_count": len(artifacts_github_rows),
            "artifacts_has_github_metadata_total": has_metadata_payload.get("total"),
            "artifacts_github_status_found_total": status_found_payload.get("total"),
            "stars_desc_results_count": len(stars_source_rows),
            "forks_desc_results_count": len(forks_source_rows),
            "min_stars_threshold": min_stars_threshold,
            "min_stars_total": min_stars_payload.get("total"),
            "language_filter_value": language_filter_value,
            "language_total": language_payload.get("total"),
            "archived_false_total": archived_false_payload.get("total"),
            "pushed_after_threshold": pushed_after_threshold_raw,
            "pushed_after_total": pushed_after_payload.get("total"),
            "updated_before_threshold": updated_before_threshold_raw,
            "updated_before_total": updated_before_payload.get("total"),
            "artifact_id": artifact_id,
            "artifact_linked_papers_total": artifact_linked_papers_payload.get("total"),
            "documents_has_trusted_artifact_total": documents_has_trusted_payload.get("total"),
            "documents_artifact_provider_github_total": documents_github_payload.get("total"),
            "canonical_id": canonical_id,
            "document_artifacts_total": document_artifacts_payload.get("total"),
        },
        "checks": checks,
        "endpoints": endpoints,
        "verdict": {
            "ok": len(required_failed_checks) == 0,
            "strict": bool(args.strict),
            "required_check_count": len(required_check_names),
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
        },
    }

    latest_json = args.reports_dir / "artifact_api_filters_check_latest.json"
    latest_md = args.reports_dir / "artifact_api_filters_check_latest.md"
    history_json = args.reports_dir / "history" / f"artifact_api_filters_check_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"artifact_api_filters_check_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    for key, value in report["summary"].items():
        print(f"[OK] {key}={value}")

    for key, value in checks.items():
        print(f"[OK] {key}={value}")

    verdict = report["verdict"]
    print(f"[OK] strict={verdict['strict']}")
    print(f"[OK] ok={verdict['ok']}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
