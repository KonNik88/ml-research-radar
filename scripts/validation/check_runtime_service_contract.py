from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.api.runtime_services import (
    RUNTIME_SERVICE_CONTRACT_VERSION,
    build_runtime_service_status,
)


DEFAULT_API_BASE_URL = os.getenv("ML_RADAR_API_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_TIMEOUT_SECONDS = 30

REPORT_DIR = Path("artifacts/reports/runtime")
HISTORY_DIR = REPORT_DIR / "history"

LATEST_JSON_PATH = REPORT_DIR / "runtime_service_contract_latest.json"
LATEST_MD_PATH = REPORT_DIR / "runtime_service_contract_latest.md"

EXPECTED_SERVICE_NAMES = {
    "api_runtime",
    "file_retrieval_runtime",
    "postgres_document_runtime",
    "search_lexical",
    "search_dense",
    "search_hybrid",
    "artifact_api",
    "workspace_collections",
    "qdrant_experimental",
    "citation_graph",
}

SERVICE_ROW_FIELDS = {
    "status",
    "available",
    "configured",
    "required",
    "health_blocking",
    "reason",
    "backend_mode",
    "endpoints",
    "caveats",
    "metadata",
}

VALID_SERVICE_STATUSES = {
    "available",
    "unavailable",
    "not_configured",
    "unsupported",
    "unknown",
}


@dataclass(frozen=True)
class RuntimeServiceScenario:
    name: str
    snapshot: dict[str, Any]
    settings_overrides: dict[str, Any]
    expected_overall_status: str
    expected_backend_mode: str
    expected_services: dict[str, dict[str, Any]]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(render_markdown_report(report), encoding="utf-8")


def clean_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def _settings(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "workspace_database_url": None,
        "citation_graph_api_enabled": False,
        "citation_graph_root": Path("__missing_runtime_contract_citation_graph_root__"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _file_snapshot(
    *,
    ready: bool = True,
    dense_ready: bool = True,
    qdrant_ok: bool | None = False,
) -> dict[str, Any]:
    return {
        "ready": ready,
        "backend_mode": "file",
        "build_id": "fixture-file-runtime",
        "corpus_doc_count": 2,
        "loaded_components": {
            "manifest": ready,
            "documents": ready,
            "lexical_artifacts": ready,
            "dense_artifacts": dense_ready,
            "embedding_model": dense_ready,
            "db_store": False,
        },
        "db_connected": False,
        "qdrant": {
            "ok": qdrant_ok,
            "collection_exists": qdrant_ok,
            "collection_name": "ml_radar_dense_benchmark_v1",
            "profile_name": "ef_256",
            "error": None if qdrant_ok else "Qdrant fixture unavailable",
        },
    }


def _db_snapshot(*, ready: bool = True, db_connected: bool = True) -> dict[str, Any]:
    return {
        "ready": ready,
        "backend_mode": "db",
        "build_id": "fixture-db-runtime",
        "corpus_doc_count": 2,
        "loaded_components": {
            "manifest": False,
            "documents": False,
            "lexical_artifacts": False,
            "dense_artifacts": False,
            "embedding_model": False,
            "db_store": db_connected,
        },
        "db_connected": db_connected,
        "qdrant": {
            "ok": False,
            "collection_exists": False,
        },
    }


def runtime_service_scenarios() -> list[RuntimeServiceScenario]:
    return [
        RuntimeServiceScenario(
            name="file_ready_dense_qdrant_unavailable",
            snapshot=_file_snapshot(dense_ready=True, qdrant_ok=False),
            settings_overrides={},
            expected_overall_status="ready",
            expected_backend_mode="file",
            expected_services={
                "api_runtime": {"status": "available", "available": True},
                "file_retrieval_runtime": {"status": "available", "available": True},
                "postgres_document_runtime": {"status": "not_configured", "available": False},
                "search_lexical": {"status": "available", "available": True},
                "search_dense": {"status": "available", "available": True},
                "search_hybrid": {"status": "available", "available": True},
                "artifact_api": {"status": "not_configured", "available": False},
                "workspace_collections": {"status": "unknown", "available": None},
                "qdrant_experimental": {"status": "unavailable", "available": False},
                "citation_graph": {"status": "not_configured", "available": False},
            },
        ),
        RuntimeServiceScenario(
            name="file_ready_dense_missing",
            snapshot=_file_snapshot(dense_ready=False, qdrant_ok=None),
            settings_overrides={},
            expected_overall_status="ready",
            expected_backend_mode="file",
            expected_services={
                "file_retrieval_runtime": {"status": "available", "available": True},
                "search_lexical": {"status": "available", "available": True},
                "search_dense": {"status": "unavailable", "available": False},
                "search_hybrid": {"status": "unavailable", "available": False},
                "qdrant_experimental": {"status": "unavailable", "available": False},
            },
        ),
        RuntimeServiceScenario(
            name="db_ready_core_optional_unsupported",
            snapshot=_db_snapshot(ready=True, db_connected=True),
            settings_overrides={"workspace_database_url": "postgresql://fixture/fixture"},
            expected_overall_status="ready",
            expected_backend_mode="db",
            expected_services={
                "api_runtime": {"status": "available", "available": True},
                "file_retrieval_runtime": {"status": "not_configured", "available": False},
                "postgres_document_runtime": {"status": "available", "available": True},
                "search_lexical": {"status": "available", "available": True},
                "search_dense": {"status": "unsupported", "available": False},
                "search_hybrid": {"status": "unsupported", "available": False},
                "artifact_api": {"status": "available", "available": True},
                "workspace_collections": {"status": "available", "available": True},
                "qdrant_experimental": {"status": "unsupported", "available": False},
            },
        ),
        RuntimeServiceScenario(
            name="db_unavailable_blocks_health",
            snapshot=_db_snapshot(ready=False, db_connected=False),
            settings_overrides={"workspace_database_url": "postgresql://fixture/fixture"},
            expected_overall_status="unavailable",
            expected_backend_mode="db",
            expected_services={
                "api_runtime": {"status": "unavailable", "available": False},
                "postgres_document_runtime": {"status": "unavailable", "available": False},
                "search_lexical": {"status": "unavailable", "available": False},
                "artifact_api": {"status": "unavailable", "available": False},
            },
        ),
        RuntimeServiceScenario(
            name="citation_graph_enabled_missing_root",
            snapshot=_db_snapshot(ready=True, db_connected=True),
            settings_overrides={
                "workspace_database_url": "postgresql://fixture/fixture",
                "citation_graph_api_enabled": True,
                "citation_graph_root": Path("__missing_runtime_contract_citation_graph_root__"),
            },
            expected_overall_status="ready",
            expected_backend_mode="db",
            expected_services={
                "citation_graph": {
                    "status": "unavailable",
                    "available": False,
                    "configured": True,
                    "health_blocking": False,
                },
            },
        ),
        RuntimeServiceScenario(
            name="unsupported_backend_blocks_health",
            snapshot={
                "ready": True,
                "backend_mode": "sqlite",
                "build_id": "fixture-unsupported-runtime",
                "loaded_components": {},
                "db_connected": False,
                "qdrant": {},
            },
            settings_overrides={},
            expected_overall_status="unavailable",
            expected_backend_mode="sqlite",
            expected_services={
                "file_retrieval_runtime": {"status": "unsupported", "available": False},
                "postgres_document_runtime": {"status": "unsupported", "available": False},
                "search_lexical": {"status": "unavailable", "available": False},
                "search_dense": {"status": "unsupported", "available": False},
                "search_hybrid": {"status": "unsupported", "available": False},
            },
        ),
    ]


def _service_row(status: Mapping[str, Any], service_name: str) -> dict[str, Any]:
    services = status.get("services")
    if not isinstance(services, Mapping):
        return {}
    service = services.get(service_name)
    return dict(service) if isinstance(service, Mapping) else {}


def recompute_counts(services: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    required = [service for service in services.values() if service.get("required") is True]
    optional = [service for service in services.values() if service.get("required") is not True]
    health_blocking = [
        service for service in services.values() if service.get("health_blocking") is True
    ]

    return {
        "service_count": len(services),
        "required_count": len(required),
        "required_available_count": sum(
            1 for service in required if service.get("available") is True
        ),
        "optional_count": len(optional),
        "optional_available_count": sum(
            1 for service in optional if service.get("available") is True
        ),
        "optional_unavailable_count": sum(
            1 for service in optional if service.get("available") is False
        ),
        "health_blocking_count": len(health_blocking),
        "health_blocking_available_count": sum(
            1 for service in health_blocking if service.get("available") is True
        ),
    }


def validate_service_status(
    *,
    status: Mapping[str, Any],
    scenario: RuntimeServiceScenario | None = None,
) -> dict[str, bool]:
    services = status.get("services") if isinstance(status.get("services"), Mapping) else {}
    counts = status.get("counts") if isinstance(status.get("counts"), Mapping) else {}
    recomputed_counts = recompute_counts(services)

    checks: dict[str, bool] = {
        "schema_version_ok": status.get("schema_version") == RUNTIME_SERVICE_CONTRACT_VERSION,
        "services_present": EXPECTED_SERVICE_NAMES <= set(services),
        "service_rows_have_required_fields": all(
            SERVICE_ROW_FIELDS <= set(service)
            for service in services.values()
            if isinstance(service, Mapping)
        ),
        "service_status_values_valid": all(
            service.get("status") in VALID_SERVICE_STATUSES
            for service in services.values()
            if isinstance(service, Mapping)
        ),
        "service_availability_values_valid": all(
            service.get("available") in {True, False, None}
            for service in services.values()
            if isinstance(service, Mapping)
        ),
        "service_counts_match": counts == recomputed_counts,
        "required_services_do_not_have_unknown_availability": all(
            service.get("available") in {True, False}
            for service in services.values()
            if isinstance(service, Mapping) and service.get("required") is True
        ),
        "optional_services_are_not_health_blocking": all(
            service.get("health_blocking") is False
            for service in services.values()
            if isinstance(service, Mapping) and service.get("required") is not True
        ),
    }

    health_blocking_ready = (
        recomputed_counts["health_blocking_available_count"]
        == recomputed_counts["health_blocking_count"]
    )
    if health_blocking_ready:
        checks["overall_status_matches_health_boundary"] = (
            status.get("overall_status") == "ready"
        )
    else:
        checks["overall_status_matches_health_boundary"] = (
            status.get("overall_status") == "unavailable"
        )

    qdrant_service = _service_row(status, "qdrant_experimental")
    citation_service = _service_row(status, "citation_graph")
    checks["qdrant_optional_boundary_ok"] = (
        qdrant_service.get("required") is False
        and qdrant_service.get("health_blocking") is False
    )
    checks["citation_graph_optional_boundary_ok"] = (
        citation_service.get("required") is False
        and citation_service.get("health_blocking") is False
    )

    if scenario is not None:
        checks["scenario_overall_status_ok"] = (
            status.get("overall_status") == scenario.expected_overall_status
        )
        checks["scenario_backend_mode_ok"] = (
            status.get("backend_mode") == scenario.expected_backend_mode
        )
        for service_name, expected_fields in scenario.expected_services.items():
            service = _service_row(status, service_name)
            for field_name, expected_value in expected_fields.items():
                checks[f"scenario_{service_name}_{field_name}_ok"] = (
                    service.get(field_name) == expected_value
                )

    return checks


def scenario_summary(status: Mapping[str, Any]) -> dict[str, Any]:
    services = status.get("services") if isinstance(status.get("services"), Mapping) else {}
    return {
        "overall_status": status.get("overall_status"),
        "backend_mode": status.get("backend_mode"),
        "counts": status.get("counts"),
        "services": {
            name: {
                "status": service.get("status"),
                "available": service.get("available"),
                "configured": service.get("configured"),
                "required": service.get("required"),
                "health_blocking": service.get("health_blocking"),
            }
            for name, service in sorted(services.items())
            if isinstance(service, Mapping)
        },
    }


def request_json(
    *,
    base_url: str,
    path: str,
    timeout_seconds: int,
) -> tuple[bool, dict[str, Any], str | None]:
    url = f"{clean_base_url(base_url)}{path}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            status_code = response.status
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if len(body) > 800:
            body = body[:800] + "..."
        return False, {}, f"HTTP {exc.code}: {body}"
    except (OSError, URLError) as exc:
        return False, {}, repr(exc)

    if status_code < 200 or status_code >= 300:
        if len(body) > 800:
            body = body[:800] + "..."
        return False, {}, f"HTTP {status_code}: {body}"

    try:
        payload = json.loads(body)
    except Exception as exc:
        return False, {}, f"JSON parse error: {exc!r}"

    if not isinstance(payload, dict):
        return False, {}, f"Expected JSON object, got {type(payload).__name__}"

    return True, payload, None


def record_live_api_checks(
    *,
    base_url: str,
    timeout_seconds: int,
    checks: dict[str, bool],
    extracted_values: dict[str, Any],
    errors: dict[str, Any],
) -> None:
    base_url = clean_base_url(base_url)
    extracted_values["api_base_url"] = base_url

    health_ok, health_payload, health_error = request_json(
        base_url=base_url,
        path="/health",
        timeout_seconds=timeout_seconds,
    )
    checks["live_health_endpoint_ok"] = health_ok
    checks["live_health_ready"] = bool(
        health_payload.get("ready") is True
        or str(health_payload.get("status", "")).lower() in {"ok", "ready", "healthy"}
    )
    extracted_values["live_health_status"] = health_payload.get("status")
    extracted_values["live_health_backend_mode"] = health_payload.get("backend_mode")
    if health_error:
        errors["live_health_error"] = health_error

    runtime_ok, runtime_payload, runtime_error = request_json(
        base_url=base_url,
        path="/runtime",
        timeout_seconds=timeout_seconds,
    )
    service_status = (
        runtime_payload.get("service_status")
        if isinstance(runtime_payload.get("service_status"), Mapping)
        else {}
    )
    checks["live_runtime_endpoint_ok"] = runtime_ok
    live_contract_checks = validate_service_status(status=service_status)
    checks.update({f"live_runtime_{key}": value for key, value in live_contract_checks.items()})
    checks["live_runtime_overall_ready"] = service_status.get("overall_status") == "ready"
    extracted_values["live_runtime_service_status"] = scenario_summary(service_status)
    if runtime_error:
        errors["live_runtime_error"] = runtime_error


def build_report(
    *,
    check_api: bool,
    api_base_url: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    extracted_values: dict[str, Any] = {
        "check_api": check_api,
        "contract_version": RUNTIME_SERVICE_CONTRACT_VERSION,
    }
    errors: dict[str, Any] = {}

    scenario_reports: list[dict[str, Any]] = []
    for scenario in runtime_service_scenarios():
        status = build_runtime_service_status(
            snapshot=scenario.snapshot,
            settings=_settings(**scenario.settings_overrides),
        )
        scenario_checks = validate_service_status(status=status, scenario=scenario)
        scenario_ok = all(scenario_checks.values())
        checks[f"scenario_{scenario.name}_ok"] = scenario_ok
        checks.update(
            {
                f"scenario_{scenario.name}_{check_name}": check_value
                for check_name, check_value in scenario_checks.items()
            }
        )
        scenario_reports.append(
            {
                "name": scenario.name,
                "ok": scenario_ok,
                "failed_checks": [
                    key for key, value in scenario_checks.items() if value is not True
                ],
                "summary": scenario_summary(status),
            }
        )

    extracted_values["scenario_count"] = len(scenario_reports)
    extracted_values["scenario_reports"] = scenario_reports

    if check_api:
        record_live_api_checks(
            base_url=api_base_url,
            timeout_seconds=timeout_seconds,
            checks=checks,
            extracted_values=extracted_values,
            errors=errors,
        )

    required_checks = sorted(checks)
    required_failed_checks = [
        check_name for check_name in required_checks if checks.get(check_name) is not True
    ]

    return {
        "generated_at_utc": utc_now().isoformat(),
        "ok": not required_failed_checks,
        "required_failed_count": len(required_failed_checks),
        "required_failed_checks": required_failed_checks,
        "checks": checks,
        "extracted_values": extracted_values,
        "errors": errors,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    checks = report.get("checks") or {}
    extracted = report.get("extracted_values") or {}
    errors = report.get("errors") or {}
    scenario_reports = extracted.get("scenario_reports") or []

    lines: list[str] = [
        "# Runtime service contract report",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- ok: `{report.get('ok')}`",
        f"- contract_version: `{extracted.get('contract_version')}`",
        f"- check_api: `{extracted.get('check_api')}`",
        f"- required_failed_count: `{report.get('required_failed_count')}`",
        f"- required_failed_checks: `{report.get('required_failed_checks')}`",
        "",
        "## Scenario Matrix",
        "",
    ]

    for scenario in scenario_reports:
        summary = scenario.get("summary") if isinstance(scenario, Mapping) else {}
        lines.append(f"### {scenario.get('name')}")
        lines.append("")
        lines.append(f"- ok: `{scenario.get('ok')}`")
        lines.append(f"- overall_status: `{summary.get('overall_status')}`")
        lines.append(f"- backend_mode: `{summary.get('backend_mode')}`")
        lines.append(f"- failed_checks: `{scenario.get('failed_checks')}`")
        lines.append("")

    lines.extend(["## Checks", ""])
    for key, value in checks.items():
        lines.append(f"- {key}: `{value}`")

    if errors:
        lines.extend(["", "## Errors / diagnostics", ""])
        for key, value in errors.items():
            lines.append(f"- {key}: `{value}`")

    lines.append("")
    return "\n".join(lines)


def print_report(report: dict[str, Any]) -> None:
    for key, value in report.get("checks", {}).items():
        status = "OK" if value is True else "FAIL"
        print(f"[{status}] {key}={value}")

    print(f"[{'OK' if report.get('ok') else 'FAIL'}] ok={report.get('ok')}")
    print(f"[OK] required_failed_count={report.get('required_failed_count')}")
    print(f"[OK] required_failed_checks={report.get('required_failed_checks')}")
    print(f"[OK] latest JSON: {LATEST_JSON_PATH}")
    print(f"[OK] latest Markdown: {LATEST_MD_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the runtime_services_v0.1 service matrix contract.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any required check fails.",
    )
    parser.add_argument(
        "--check-api",
        action="store_true",
        help="Also validate live /health and /runtime endpoints.",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Base URL for live API checks.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout for live API checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        check_api=bool(args.check_api),
        api_base_url=str(args.api_base_url),
        timeout_seconds=int(args.timeout_seconds),
    )

    history_json_path = (
        HISTORY_DIR / f"runtime_service_contract_{utc_stamp()}.json"
    )
    history_md_path = (
        HISTORY_DIR / f"runtime_service_contract_{utc_stamp()}.md"
    )

    write_json(LATEST_JSON_PATH, report)
    write_markdown(LATEST_MD_PATH, report)
    write_json(history_json_path, report)
    write_markdown(history_md_path, report)

    print_report(report)

    if args.strict and not report["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
