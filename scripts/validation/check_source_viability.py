from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("configs/source_viability.yaml")
REPORT_DIR = Path("artifacts/reports/validation")
HISTORY_DIR = REPORT_DIR / "history"


@dataclass
class CheckResult:
    source: str
    check_name: str
    required: bool
    ok: bool
    status_code: int | None
    elapsed_ms: float | None
    error: str | None
    details: dict[str, Any]


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required for source viability config. "
            "Install it or add it to the project environment."
        ) from exc

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)

    if not isinstance(payload, dict):
        raise ValueError(f"Invalid YAML config: {path}")

    return payload


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_by_path(payload: Any, path: str) -> Any:
    if path == ".":
        return payload

    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        else:
            return None

    return current


def add_query_param(url: str, name: str, value: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

    # Avoid adding duplicate auth params if the URL already contains them.
    existing_names = {k for k, _ in query}
    if name not in existing_names:
        query.append((name, value))

    new_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
    )


def build_headers(
    *,
    defaults: dict[str, Any],
    source_cfg: dict[str, Any],
) -> dict[str, str]:
    headers = {
        "User-Agent": str(defaults.get("user_agent", "ML-Research-Radar source-viability-check")),
        "Accept": "application/json, text/xml, application/xml, text/plain, */*",
    }

    auth = source_cfg.get("auth") or {}
    token_env = auth.get("token_env")
    token = os.getenv(str(token_env)) if token_env else None

    header_name = auth.get("header")
    if token and header_name:
        scheme = auth.get("scheme")
        headers[str(header_name)] = f"{scheme} {token}" if scheme else token

    return headers


def prepare_url(
    *,
    url: str,
    source_cfg: dict[str, Any],
) -> str:
    auth = source_cfg.get("auth") or {}
    token_env = auth.get("token_env")
    token = os.getenv(str(token_env)) if token_env else None

    query_param = auth.get("query_param")
    if token and query_param:
        return add_query_param(url, str(query_param), token)

    return url


def http_get_once(
    *,
    url: str,
    headers: dict[str, str],
    timeout_sec: int,
) -> tuple[int, dict[str, str], bytes, float]:
    req = urllib.request.Request(url=url, headers=headers, method="GET")
    started = time.perf_counter()

    with urllib.request.urlopen(req, timeout=timeout_sec) as response:
        body = response.read()
        elapsed_ms = (time.perf_counter() - started) * 1000
        status_code = int(response.status)
        response_headers = {k.lower(): v for k, v in response.headers.items()}
        return status_code, response_headers, body, elapsed_ms


def is_retryable_http_status(status_code: int | None) -> bool:
    if status_code is None:
        return True
    return status_code in {408, 425, 429, 500, 502, 503, 504}


def parse_body(body: bytes, content_type: str) -> tuple[Any | None, str]:
    text = body.decode("utf-8", errors="replace")

    if "json" in content_type.lower():
        try:
            return json.loads(text), text
        except json.JSONDecodeError:
            return None, text

    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(text), text
        except json.JSONDecodeError:
            return None, text

    return None, text


def evaluate_expectation(
    *,
    expect: dict[str, Any],
    status_code: int,
    headers: dict[str, str],
    parsed_json: Any | None,
    text: str,
) -> tuple[bool, dict[str, Any]]:
    details: dict[str, Any] = {
        "status_code": status_code,
        "content_type": headers.get("content-type"),
    }

    expected_status = expect.get("status_code")
    if expected_status is not None and status_code != int(expected_status):
        details["failed"] = f"status_code != {expected_status}"
        return False, details

    root_type = expect.get("root_type")
    if root_type:
        if root_type == "list" and not isinstance(parsed_json, list):
            details["failed"] = "root JSON is not list"
            return False, details
        if root_type == "dict" and not isinstance(parsed_json, dict):
            details["failed"] = "root JSON is not dict"
            return False, details

    json_path_exists = expect.get("json_path_exists")
    if json_path_exists:
        if parsed_json is None:
            details["failed"] = "response is not valid JSON"
            return False, details

        value = get_by_path(parsed_json, str(json_path_exists))
        details["json_path_exists"] = json_path_exists
        details["json_path_value_type"] = type(value).__name__ if value is not None else None

        if value is None:
            details["failed"] = f"missing JSON path: {json_path_exists}"
            return False, details

    min_items = expect.get("min_items")
    min_items_path = expect.get("min_items_path")

    if min_items is not None:
        target = parsed_json
        if min_items_path:
            if parsed_json is None:
                details["failed"] = "response is not valid JSON"
                return False, details
            target = get_by_path(parsed_json, str(min_items_path))

        if not isinstance(target, list):
            details["failed"] = f"target is not list for min_items check: {min_items_path or '.'}"
            return False, details

        details["items_count"] = len(target)
        if len(target) < int(min_items):
            details["failed"] = f"items_count < {min_items}"
            return False, details

    text_contains_any = expect.get("text_contains_any") or []
    if text_contains_any:
        if not any(str(needle) in text for needle in text_contains_any):
            details["failed"] = "none of expected text fragments found"
            details["expected_fragments"] = text_contains_any
            return False, details

    return True, details


def make_error_result(
    *,
    source_name: str,
    check_name: str,
    required: bool,
    status_code: int | None,
    elapsed_ms: float | None,
    error: str,
    raw_url: str,
    response_preview: str = "",
    attempt: int,
    attempts: int,
) -> CheckResult:
    return CheckResult(
        source=source_name,
        check_name=check_name,
        required=required,
        ok=False,
        status_code=status_code,
        elapsed_ms=round(elapsed_ms, 3) if elapsed_ms is not None else None,
        error=error,
        details={
            "url": raw_url,
            "response_preview": response_preview,
            "attempt": attempt,
            "attempts": attempts,
        },
    )


def run_check(
    *,
    source_name: str,
    source_cfg: dict[str, Any],
    check_cfg: dict[str, Any],
    defaults: dict[str, Any],
) -> CheckResult:
    check_name = str(check_cfg.get("name", "unnamed_check"))
    required = bool(check_cfg.get("required", True))
    method = str(check_cfg.get("method", "GET")).upper()

    if method != "GET":
        return CheckResult(
            source=source_name,
            check_name=check_name,
            required=required,
            ok=False,
            status_code=None,
            elapsed_ms=None,
            error=f"Unsupported method: {method}",
            details={},
        )

    raw_url = str(check_cfg["url"])
    url = prepare_url(url=raw_url, source_cfg=source_cfg)
    headers = build_headers(defaults=defaults, source_cfg=source_cfg)
    timeout_sec = int(defaults.get("timeout_sec", 20))
    max_preview_chars = int(defaults.get("max_preview_chars", 500))

    retry_count = int(defaults.get("retry_count", 0))
    retry_sleep_sec = float(defaults.get("retry_sleep_sec", 0))
    attempts = max(retry_count + 1, 1)

    last_result: CheckResult | None = None

    for attempt in range(1, attempts + 1):
        try:
            status_code, response_headers, body, elapsed_ms = http_get_once(
                url=url,
                headers=headers,
                timeout_sec=timeout_sec,
            )
            parsed_json, text = parse_body(body, response_headers.get("content-type", ""))

            ok, details = evaluate_expectation(
                expect=check_cfg.get("expect") or {},
                status_code=status_code,
                headers=response_headers,
                parsed_json=parsed_json,
                text=text,
            )

            details["url"] = raw_url
            details["attempt"] = attempt
            details["attempts"] = attempts
            details["response_preview"] = text[:max_preview_chars]

            result = CheckResult(
                source=source_name,
                check_name=check_name,
                required=required,
                ok=ok,
                status_code=status_code,
                elapsed_ms=round(elapsed_ms, 3),
                error=None if ok else details.get("failed", "expectation failed"),
                details=details,
            )

            last_result = result

            # If expectation failed but HTTP status itself is not retryable,
            # retrying will not help.
            if ok or not is_retryable_http_status(status_code):
                return result

        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            text = body.decode("utf-8", errors="replace")[:max_preview_chars]
            result = make_error_result(
                source_name=source_name,
                check_name=check_name,
                required=required,
                status_code=int(exc.code),
                elapsed_ms=None,
                error=f"HTTPError: {exc.code} {exc.reason}",
                raw_url=raw_url,
                response_preview=text,
                attempt=attempt,
                attempts=attempts,
            )
            last_result = result

            if not is_retryable_http_status(int(exc.code)):
                return result

        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            result = make_error_result(
                source_name=source_name,
                check_name=check_name,
                required=required,
                status_code=None,
                elapsed_ms=None,
                error=f"{type(exc).__name__}: {exc}",
                raw_url=raw_url,
                attempt=attempt,
                attempts=attempts,
            )
            last_result = result

        except Exception as exc:
            result = make_error_result(
                source_name=source_name,
                check_name=check_name,
                required=required,
                status_code=None,
                elapsed_ms=None,
                error=f"{type(exc).__name__}: {exc}",
                raw_url=raw_url,
                attempt=attempt,
                attempts=attempts,
            )
            last_result = result

        if attempt < attempts:
            time.sleep(retry_sleep_sec)

    assert last_result is not None
    return last_result


def summarize_source(source_cfg: dict[str, Any], results: list[CheckResult]) -> dict[str, Any]:
    configured_status = source_cfg.get("status")

    if configured_status in {"blocked", "archived"}:
        return {
            "source_type": source_cfg.get("source_type"),
            "configured_status": configured_status,
            "verdict": configured_status,
            "required_checks": 0,
            "required_failed": 0,
            "optional_failed": 0,
            "notes": source_cfg.get("notes"),
        }

    required = [r for r in results if r.required]
    optional = [r for r in results if not r.required]

    required_failed = [r for r in required if not r.ok]
    optional_failed = [r for r in optional if not r.ok]

    if required_failed:
        verdict = "blocked"
    elif optional_failed:
        verdict = "viable_with_warnings"
    else:
        verdict = "viable"

    return {
        "source_type": source_cfg.get("source_type"),
        "configured_status": configured_status,
        "verdict": verdict,
        "required_checks": len(required),
        "required_failed": len(required_failed),
        "optional_failed": len(optional_failed),
        "notes": source_cfg.get("notes"),
    }


def result_to_dict(result: CheckResult) -> dict[str, Any]:
    return {
        "source": result.source,
        "check_name": result.check_name,
        "required": result.required,
        "ok": result.ok,
        "status_code": result.status_code,
        "elapsed_ms": result.elapsed_ms,
        "error": result.error,
        "details": result.details,
    }


def write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Source viability report")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at_utc']}`")
    lines.append(f"- Run ts: `{payload['run_ts']}`")
    lines.append(f"- Config: `{payload['config_path']}`")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Source | Type | Configured | Verdict | Required failed | Optional failed |")
    lines.append("|---|---|---|---|---:|---:|")
    for source, summary in payload["summary"].items():
        lines.append(
            f"| {source} | {summary.get('source_type')} | {summary.get('configured_status')} "
            f"| **{summary.get('verdict')}** | {summary.get('required_failed')} | {summary.get('optional_failed')} |"
        )

    lines.append("")
    lines.append("## Checks")
    lines.append("")

    for result in payload["checks"]:
        status = "OK" if result["ok"] else "FAIL"
        required = "required" if result["required"] else "optional"
        details = result.get("details") or {}

        lines.append(f"### {result['source']} / {result['check_name']}")
        lines.append("")
        lines.append(f"- status: **{status}**")
        lines.append(f"- type: `{required}`")
        lines.append(f"- status_code: `{result.get('status_code')}`")
        lines.append(f"- elapsed_ms: `{result.get('elapsed_ms')}`")
        lines.append(f"- attempt: `{details.get('attempt')}` / `{details.get('attempts')}`")
        if result.get("error"):
            lines.append(f"- error: `{result['error']}`")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check viability of candidate data sources.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Source name to check. Can be repeated. Default: all enabled sources.",
    )
    parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="Include disabled/blocked sources in summary.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero code if any selected source has failed required checks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = load_yaml(args.config)
    defaults = config.get("defaults") or {}
    sources = config.get("sources") or {}

    selected = set(args.source or [])
    if selected:
        missing = selected - set(sources)
        if missing:
            raise ValueError(f"Unknown sources in --source: {sorted(missing)}")

    run_ts = utc_now_ts()
    all_results: list[CheckResult] = []
    summary: dict[str, Any] = {}

    for source_name, source_cfg in sources.items():
        if selected and source_name not in selected:
            continue

        enabled = bool(source_cfg.get("enabled", True))
        if not enabled and not args.include_disabled:
            continue

        checks = source_cfg.get("checks") or []
        source_results: list[CheckResult] = []

        if enabled:
            for check_cfg in checks:
                result = run_check(
                    source_name=source_name,
                    source_cfg=source_cfg,
                    check_cfg=check_cfg,
                    defaults=defaults,
                )
                source_results.append(result)
                all_results.append(result)

        summary[source_name] = summarize_source(source_cfg, source_results)

    payload = {
        "report_name": "source_viability",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "config_path": str(args.config).replace("\\", "/"),
        "summary": summary,
        "checks": [result_to_dict(r) for r in all_results],
    }

    latest_json = REPORT_DIR / "source_viability_latest.json"
    latest_md = REPORT_DIR / "source_viability_latest.md"
    history_json = HISTORY_DIR / f"source_viability_{run_ts}.json"
    history_md = HISTORY_DIR / f"source_viability_{run_ts}.md"

    dump_json(latest_json, payload)
    dump_json(history_json, payload)
    write_markdown_report(latest_md, payload)
    write_markdown_report(history_md, payload)

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")

    failed_required = [
        (source, s)
        for source, s in summary.items()
        if int(s.get("required_failed") or 0) > 0
    ]

    for source, s in summary.items():
        print(
            f"[VIABILITY] source={source} type={s.get('source_type')} "
            f"configured={s.get('configured_status')} verdict={s.get('verdict')} "
            f"required_failed={s.get('required_failed')} optional_failed={s.get('optional_failed')}"
        )

    if args.strict and failed_required:
        print("[FAIL] Some sources failed required checks in strict mode")
        sys.exit(1)


if __name__ == "__main__":
    main()