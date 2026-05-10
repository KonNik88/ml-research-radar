from __future__ import annotations

import argparse
import importlib.util
import json
import py_compile
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


DEFAULT_APP_PATH = Path("services/ui/app.py")
DEFAULT_REPORT_DIR = Path("artifacts/reports/ui")
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"

REQUIRED_UI_SNIPPETS = {
    "reset_button": "Reset discovery filters",
    "run_button": "Run discovery ranking",
    "profile_default_state": "Profile default",
}

REQUIRED_DISCOVERY_SNIPPETS = {
    "profiles_endpoint": "/discovery/profiles",
    "ranking_endpoint": "/discovery/ranking",
    "paper_detail_endpoint": "/discovery/papers/",
    "similar_endpoint_suffix": "/similar",
}

REQUIRED_SIMILAR_SNIPPETS = {
    "semantic_mode": "semantic",
    "radar_adjusted_mode": "radar_adjusted",
}

FORBIDDEN_SNIPPETS = {
    "deprecated_use_container_width": "use_container_width",
}


@dataclass
class ReportPaths:
    latest_json: str
    latest_markdown: str
    history_json: str
    history_markdown: str


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path) -> str:
    return path.as_posix()


def import_available(module_name: str) -> tuple[bool, str | None]:
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return False, f"module not found: {module_name}"
    return True, None


def compile_python_file(path: Path) -> tuple[bool, str | None]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, None
    except py_compile.PyCompileError as exc:
        return False, str(exc)
    except Exception as exc:  # pragma: no cover - defensive guard for local validation script
        return False, repr(exc)


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except Exception as exc:  # pragma: no cover - defensive guard for local validation script
        return "", repr(exc)


def request_json(api_base_url: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    import requests

    url = urljoin(api_base_url.rstrip("/") + "/", path.lstrip("/"))
    try:
        response = requests.get(url, params=params, timeout=30)
        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw_text": response.text[:1000]}
        return {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "url": response.url,
            "json": payload,
        }
    except Exception as exc:  # pragma: no cover - depends on local API availability
        return {
            "ok": False,
            "status_code": None,
            "url": url,
            "error": repr(exc),
        }


def build_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Streamlit Discovery UI quality report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{report['generated_at_utc']}`")
    lines.append(f"- app_path: `{report['app_path']}`")
    lines.append(f"- strict: `{report['strict']}`")
    lines.append(f"- check_api: `{report['check_api']}`")
    lines.append(f"- ok: `{report['ok']}`")
    lines.append(f"- required_failed_count: `{report['required_failed_count']}`")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    for name, value in report["checks"].items():
        mark = "OK" if value else "FAIL"
        lines.append(f"- **{mark}** `{name}` = `{value}`")
    lines.append("")

    if report.get("missing_required_snippets"):
        lines.append("## Missing required snippets")
        lines.append("")
        for item in report["missing_required_snippets"]:
            lines.append(f"- `{item}`")
        lines.append("")

    if report.get("present_forbidden_snippets"):
        lines.append("## Present forbidden snippets")
        lines.append("")
        for item in report["present_forbidden_snippets"]:
            lines.append(f"- `{item}`")
        lines.append("")

    if report.get("api"):
        lines.append("## API smoke")
        lines.append("")
        for name, payload in report["api"].items():
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- ok: `{payload.get('ok')}`")
            lines.append(f"- status_code: `{payload.get('status_code')}`")
            if payload.get("url"):
                lines.append(f"- url: `{payload.get('url')}`")
            if payload.get("error"):
                lines.append(f"- error: `{payload.get('error')}`")
            lines.append("")

    if report.get("required_failed_checks"):
        lines.append("## Required failed checks")
        lines.append("")
        for name in report["required_failed_checks"]:
            lines.append(f"- `{name}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_reports(report: dict[str, Any], report_dir: Path, timestamp: str) -> ReportPaths:
    history_dir = report_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    latest_json = report_dir / "streamlit_discovery_ui_quality_latest.json"
    latest_markdown = report_dir / "streamlit_discovery_ui_quality_latest.md"
    history_json = history_dir / f"streamlit_discovery_ui_quality_{timestamp}.json"
    history_markdown = history_dir / f"streamlit_discovery_ui_quality_{timestamp}.md"

    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    markdown = build_markdown_report(report)

    latest_json.write_text(payload + "\n", encoding="utf-8")
    history_json.write_text(payload + "\n", encoding="utf-8")
    latest_markdown.write_text(markdown, encoding="utf-8")
    history_markdown.write_text(markdown, encoding="utf-8")

    return ReportPaths(
        latest_json=normalize_path(latest_json),
        latest_markdown=normalize_path(latest_markdown),
        history_json=normalize_path(history_json),
        history_markdown=normalize_path(history_markdown),
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    timestamp = utc_timestamp()
    app_path = Path(args.app_path)
    report_dir = Path(args.report_dir)

    streamlit_import_ok, streamlit_import_error = import_available("streamlit")
    requests_import_ok, requests_import_error = import_available("requests")

    app_exists = app_path.exists()
    app_non_empty = app_exists and app_path.stat().st_size > 0

    py_compile_ok = False
    py_compile_error: str | None = None
    app_text = ""
    app_read_error: str | None = None

    if app_exists:
        py_compile_ok, py_compile_error = compile_python_file(app_path)
        app_text, app_read_error = read_text(app_path)

    required_snippets = {
        **REQUIRED_UI_SNIPPETS,
        **REQUIRED_DISCOVERY_SNIPPETS,
        **REQUIRED_SIMILAR_SNIPPETS,
    }
    snippet_presence = {
        name: snippet in app_text for name, snippet in required_snippets.items()
    }
    missing_required_snippets = [
        name for name, present in snippet_presence.items() if not present
    ]

    forbidden_presence = {
        name: snippet in app_text for name, snippet in FORBIDDEN_SNIPPETS.items()
    }
    present_forbidden_snippets = [
        name for name, present in forbidden_presence.items() if present
    ]

    legacy_search_endpoint_present = "/search" in app_text

    api_payloads: dict[str, Any] = {}
    api_checks: dict[str, bool] = {}
    if args.check_api:
        health = request_json(args.api_base_url, "/health")
        profiles = request_json(args.api_base_url, "/discovery/profiles")
        ranking = request_json(
            args.api_base_url,
            "/discovery/ranking/recent_artifact_ready",
            params={"top_k": 1, "min_year": 2025, "has_code": "true"},
        )

        api_payloads = {
            "health": {key: value for key, value in health.items() if key != "json"},
            "profiles": {key: value for key, value in profiles.items() if key != "json"},
            "ranking_override": {
                key: value for key, value in ranking.items() if key != "json"
            },
        }

        health_json = health.get("json") if isinstance(health.get("json"), dict) else {}
        profiles_json = (
            profiles.get("json") if isinstance(profiles.get("json"), dict) else {}
        )
        ranking_json = (
            ranking.get("json") if isinstance(ranking.get("json"), dict) else {}
        )
        ranking_results = ranking_json.get("results") or []
        ranking_filters = ranking_json.get("filters") or {}

        api_checks = {
            "api_health_endpoint_ok": bool(health.get("ok")),
            "api_health_ready": bool(health_json.get("ready")),
            "api_profiles_endpoint_ok": bool(profiles.get("ok")),
            "api_profiles_non_empty": int(profiles_json.get("profile_count") or 0) > 0,
            "api_ranking_override_endpoint_ok": bool(ranking.get("ok")),
            "api_ranking_override_results_non_empty": len(ranking_results) > 0,
            "api_ranking_override_filters_echoed": (
                ranking_filters.get("min_year") == 2025
                and ranking_filters.get("has_code") is True
            ),
        }

    checks: dict[str, bool] = {
        "app_exists": app_exists,
        "app_non_empty": app_non_empty,
        "py_compile_ok": py_compile_ok,
        "app_read_ok": app_exists and app_read_error is None,
        "streamlit_import_ok": streamlit_import_ok,
        "requests_import_ok": requests_import_ok,
        "required_ui_snippets_present": all(snippet_presence.values()),
        "discovery_endpoint_strings_present": all(
            snippet_presence[name] for name in REQUIRED_DISCOVERY_SNIPPETS
        ),
        "similar_modes_present": all(
            snippet_presence[name] for name in REQUIRED_SIMILAR_SNIPPETS
        ),
        "reset_button_present": snippet_presence["reset_button"],
        "no_deprecated_use_container_width": not forbidden_presence[
            "deprecated_use_container_width"
        ],
        "legacy_search_endpoint_absent": not legacy_search_endpoint_present,
        **api_checks,
    }

    required_check_names = [
        "app_exists",
        "app_non_empty",
        "py_compile_ok",
        "app_read_ok",
        "streamlit_import_ok",
        "requests_import_ok",
        "required_ui_snippets_present",
        "discovery_endpoint_strings_present",
        "similar_modes_present",
        "reset_button_present",
        "no_deprecated_use_container_width",
    ]

    # Keep this diagnostic non-required for now: a docstring or comment can mention /search.
    if args.require_no_legacy_search:
        required_check_names.append("legacy_search_endpoint_absent")

    if args.check_api:
        required_check_names.extend(
            [
                "api_health_endpoint_ok",
                "api_health_ready",
                "api_profiles_endpoint_ok",
                "api_profiles_non_empty",
                "api_ranking_override_endpoint_ok",
                "api_ranking_override_results_non_empty",
                "api_ranking_override_filters_echoed",
            ]
        )

    required_failed_checks = [name for name in required_check_names if not checks.get(name)]

    report: dict[str, Any] = {
        "name": "streamlit_discovery_ui_quality",
        "generated_at_utc": timestamp,
        "strict": bool(args.strict),
        "check_api": bool(args.check_api),
        "api_base_url": args.api_base_url,
        "app_path": normalize_path(app_path),
        "report_dir": normalize_path(report_dir),
        "checks": checks,
        "required_check_names": required_check_names,
        "required_failed_checks": required_failed_checks,
        "required_failed_count": len(required_failed_checks),
        "ok": len(required_failed_checks) == 0,
        "snippet_presence": snippet_presence,
        "forbidden_presence": forbidden_presence,
        "missing_required_snippets": missing_required_snippets,
        "present_forbidden_snippets": present_forbidden_snippets,
        "diagnostics": {
            "streamlit_import_error": streamlit_import_error,
            "requests_import_error": requests_import_error,
            "py_compile_error": py_compile_error,
            "app_read_error": app_read_error,
            "legacy_search_endpoint_present": legacy_search_endpoint_present,
            "app_size_bytes": app_path.stat().st_size if app_exists else 0,
        },
        "api": api_payloads,
    }

    paths = write_reports(report, report_dir, timestamp)
    report["outputs"] = asdict(paths)

    # Re-write reports with their own output paths included.
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    markdown = build_markdown_report(report)
    Path(paths.latest_json).write_text(payload + "\n", encoding="utf-8")
    Path(paths.history_json).write_text(payload + "\n", encoding="utf-8")
    Path(paths.latest_markdown).write_text(markdown, encoding="utf-8")
    Path(paths.history_markdown).write_text(markdown, encoding="utf-8")

    return report


def print_report(report: dict[str, Any]) -> None:
    def ok_line(name: str, value: Any) -> None:
        prefix = "[OK]" if bool(value) else "[FAIL]"
        print(f"{prefix} {name}={value}")

    for name, value in report["checks"].items():
        ok_line(name, value)

    print(f"[OK] app_path={report['app_path']}")
    print(f"[OK] check_api={report['check_api']}")
    print(f"[OK] ok={report['ok']}")
    print(f"[OK] required_failed_count={report['required_failed_count']}")
    print(f"[OK] required_failed_checks={report['required_failed_checks']}")
    missing_required_snippets = report.get("missing_required_snippets") or []
    if missing_required_snippets:
        print(f"[FAIL] missing_required_snippets={missing_required_snippets}")

    outputs = report.get("outputs") or {}
    if outputs:
        print(f"[OK] latest JSON: {outputs.get('latest_json')}")
        print(f"[OK] latest Markdown: {outputs.get('latest_markdown')}")
        print(f"[OK] history JSON: {outputs.get('history_json')}")
        print(f"[OK] history Markdown: {outputs.get('history_markdown')}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Streamlit Discovery UI static contract and optional API smoke."
    )
    parser.add_argument("--app-path", default=str(DEFAULT_APP_PATH))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument(
        "--check-api",
        action="store_true",
        help="Also check a running FastAPI Discovery API at --api-base-url.",
    )
    parser.add_argument(
        "--require-no-legacy-search",
        action="store_true",
        help="Fail if the UI file contains the literal '/search'.",
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    print_report(report)

    if args.strict and not report["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
