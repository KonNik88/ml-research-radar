from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


DEFAULT_INPUT_PATH = Path("data/enriched/artifact_links/artifact_entities_latest.jsonl")
DEFAULT_OUTPUT_DIR = Path("data/enriched/github_artifacts")
DEFAULT_REPORT_DIR = Path("artifacts/reports/validation")
DEFAULT_TOKEN_ENV = "GITHUB_TOKEN"

USER_AGENT = "ML-Research-Radar-GitHub-Enrichment/1.0"
GITHUB_API_VERSION = "2022-11-28"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc
    return rows


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _clean_part(value: Any) -> str:
    return str(value or "").strip().strip("/")


def parse_owner_repo(entity: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return (owner, repo, reason_if_invalid)."""
    external_id = _clean_part(entity.get("external_id"))
    if external_id and "/" in external_id:
        parts = [p for p in external_id.split("/") if p]
        if len(parts) == 2:
            owner, repo = parts
            return owner, repo, None

    normalized_url = _clean_part(entity.get("normalized_url"))
    if normalized_url:
        parsed = urlparse(normalized_url)
        host = (parsed.netloc or "").lower()
        if host == "github.com" or host.endswith(".github.com"):
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2:
                return parts[0], parts[1], None

    owner = _clean_part(entity.get("owner"))
    name = _clean_part(entity.get("name"))
    if owner and name:
        return owner, name, None

    return None, None, "cannot_parse_owner_repo"


def github_api_url(owner: str, repo: str) -> str:
    owner_q = quote(owner, safe="")
    repo_q = quote(repo, safe="")
    return f"https://api.github.com/repos/{owner_q}/{repo_q}"


def normalize_license(payload: dict[str, Any]) -> str | None:
    license_payload = payload.get("license")
    if not isinstance(license_payload, dict):
        return None

    spdx_id = str(license_payload.get("spdx_id") or "").strip()
    if spdx_id and spdx_id.upper() != "NOASSERTION":
        return spdx_id.lower()

    key = str(license_payload.get("key") or "").strip()
    if key:
        return key.lower()

    name = str(license_payload.get("name") or "").strip()
    return name or None


def normalize_found_row(
    *,
    entity: dict[str, Any],
    owner: str,
    repo: str,
    api_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    fetched_at: str,
) -> dict[str, Any]:
    license_payload = payload.get("license") if isinstance(payload.get("license"), dict) else None

    return {
        "artifact_id": entity.get("artifact_id"),
        "provider": "github",
        "external_id": f"{owner}/{repo}",
        "owner": owner,
        "name": repo,
        "normalized_url": entity.get("normalized_url") or f"https://github.com/{owner}/{repo}",
        "github_api_url": api_url,
        "fetched_at": fetched_at,
        "status": "found",
        "http_status": 200,
        "description": payload.get("description"),
        "homepage": payload.get("homepage") or None,
        "language": payload.get("language"),
        "license": normalize_license(payload),
        "stars": payload.get("stargazers_count"),
        "forks": payload.get("forks_count"),
        "watchers": payload.get("watchers_count"),
        "open_issues": payload.get("open_issues_count"),
        "topics": payload.get("topics") or [],
        "default_branch": payload.get("default_branch"),
        "archived": payload.get("archived"),
        "disabled": payload.get("disabled"),
        "private": payload.get("private"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "pushed_at": payload.get("pushed_at"),
        "html_url": payload.get("html_url"),
        "metadata": {
            "source": "github_api",
            "enrichment_stage": "github_artifact_enrichment_v1",
            "rate_limit_remaining": headers.get("x-ratelimit-remaining"),
            "rate_limit_limit": headers.get("x-ratelimit-limit"),
            "rate_limit_reset": headers.get("x-ratelimit-reset"),
            "etag": headers.get("etag"),
            "license_raw": license_payload,
        },
    }


def error_row(
    *,
    entity: dict[str, Any],
    owner: str | None,
    repo: str | None,
    api_url: str | None,
    fetched_at: str,
    status: str,
    http_status: int | None = None,
    error: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = headers or {}
    external_id = f"{owner}/{repo}" if owner and repo else entity.get("external_id")

    return {
        "artifact_id": entity.get("artifact_id"),
        "provider": "github",
        "external_id": external_id,
        "owner": owner or entity.get("owner"),
        "name": repo or entity.get("name"),
        "normalized_url": entity.get("normalized_url"),
        "github_api_url": api_url,
        "fetched_at": fetched_at,
        "status": status,
        "http_status": http_status,
        "error": error,
        "metadata": {
            "source": "github_api",
            "enrichment_stage": "github_artifact_enrichment_v1",
            "rate_limit_remaining": headers.get("x-ratelimit-remaining"),
            "rate_limit_limit": headers.get("x-ratelimit-limit"),
            "rate_limit_reset": headers.get("x-ratelimit-reset"),
        },
    }


def headers_to_dict(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        out[str(key).lower()] = str(value)
    return out


def classify_http_error(exc: HTTPError, headers: dict[str, str]) -> str:
    if exc.code == 404:
        return "not_found"
    if exc.code in {429}:
        return "rate_limited"
    if exc.code == 403 and headers.get("x-ratelimit-remaining") == "0":
        return "rate_limited"
    if exc.code in {401, 403}:
        return "forbidden"
    return "error"


def fetch_github_repo(
    *,
    entity: dict[str, Any],
    owner: str,
    repo: str,
    token: str | None,
    timeout_sec: float,
) -> dict[str, Any]:
    fetched_at = utc_now_iso()
    api_url = github_api_url(owner, repo)

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(api_url, headers=headers, method="GET")

    try:
        with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310 - controlled GitHub API URL
            response_headers = headers_to_dict(response.headers)
            payload = json.loads(response.read().decode("utf-8"))
            return normalize_found_row(
                entity=entity,
                owner=owner,
                repo=repo,
                api_url=api_url,
                payload=payload,
                headers=response_headers,
                fetched_at=fetched_at,
            )

    except HTTPError as exc:
        response_headers = headers_to_dict(exc.headers)
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
            message = error_payload.get("message") or repr(exc)
        except Exception:
            message = repr(exc)

        status = classify_http_error(exc, response_headers)
        return error_row(
            entity=entity,
            owner=owner,
            repo=repo,
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
            owner=owner,
            repo=repo,
            api_url=api_url,
            fetched_at=fetched_at,
            status="error",
            http_status=None,
            error=repr(exc),
        )

    except Exception as exc:
        return error_row(
            entity=entity,
            owner=owner,
            repo=repo,
            api_url=api_url,
            fetched_at=fetched_at,
            status="error",
            http_status=None,
            error=repr(exc),
        )


def select_github_entities(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    selected = [
        row for row in rows
        if row.get("provider") == "github"
        and row.get("artifact_type") == "github_repository"
    ]
    selected.sort(key=lambda x: (str(x.get("owner") or "").lower(), str(x.get("name") or "").lower(), str(x.get("artifact_id") or "")))
    if limit is not None:
        selected = selected[:limit]
    return selected


def build_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# GitHub artifact enrichment report")
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
        "github_entities_count",
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
        description="Enrich extracted GitHub artifact entities with GitHub API repository metadata."
    )
    parser.add_argument("--input-path", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Limit number of GitHub repositories to process.")
    parser.add_argument("--dry-run", action="store_true", help="Plan requests and write report, but do not call GitHub API or write metadata JSONL.")
    parser.add_argument("--sleep-sec", type=float, default=0.2, help="Delay between GitHub API requests.")
    parser.add_argument("--timeout-sec", type=float, default=20.0, help="HTTP timeout per GitHub API request.")
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV, help="Environment variable containing GitHub token.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    if not args.input_path.exists():
        raise FileNotFoundError(f"Artifact entities file not found: {args.input_path}")

    token = os.getenv(args.token_env)
    token_present = bool(token)

    all_entities = load_jsonl(args.input_path)
    github_entities_all = select_github_entities(all_entities, limit=None)
    github_entities = select_github_entities(all_entities, limit=args.limit)

    output_path = args.output_dir / f"github_artifact_metadata.{run_ts}.jsonl"
    latest_output_path = args.output_dir / "github_artifact_metadata_latest.jsonl"

    rows: list[dict[str, Any]] = []
    skipped_invalid = 0
    warnings: list[str] = []

    print(f"[INFO] input_path={args.input_path}")
    print(f"[INFO] input_entities={len(all_entities)}")
    print(f"[INFO] github_entities_total={len(github_entities_all)}")
    print(f"[INFO] requested_count={len(github_entities)}")
    print(f"[INFO] dry_run={args.dry_run}")
    print(f"[INFO] token_present={token_present}")

    if args.dry_run:
        for entity in github_entities:
            owner, repo, invalid_reason = parse_owner_repo(entity)
            if invalid_reason:
                skipped_invalid += 1
                continue
            print(f"[DRY-RUN] would fetch {github_api_url(owner or '', repo or '')}")
    else:
        for idx, entity in enumerate(github_entities, start=1):
            owner, repo, invalid_reason = parse_owner_repo(entity)
            if invalid_reason or not owner or not repo:
                skipped_invalid += 1
                rows.append(
                    error_row(
                        entity=entity,
                        owner=owner,
                        repo=repo,
                        api_url=None,
                        fetched_at=utc_now_iso(),
                        status="skipped_invalid_external_id",
                        error=invalid_reason or "invalid_owner_repo",
                    )
                )
                continue

            print(f"[INFO] ({idx}/{len(github_entities)}) fetching {owner}/{repo}")
            row = fetch_github_repo(
                entity=entity,
                owner=owner,
                repo=repo,
                token=token,
                timeout_sec=args.timeout_sec,
            )
            rows.append(row)

            if row.get("status") == "rate_limited":
                warnings.append("GitHub rate limit reached; stopping early.")
                print("[WARN] GitHub rate limit reached; stopping early.")
                break

            if args.sleep_sec > 0 and idx < len(github_entities):
                time.sleep(args.sleep_sec)

        write_jsonl(output_path, rows)
        write_jsonl(latest_output_path, rows)

    status_distribution = Counter(row.get("status") for row in rows)

    rate_limit_remaining_values = [
        dig for row in rows
        for dig in [((row.get("metadata") or {}).get("rate_limit_remaining"))]
        if dig is not None
    ]
    rate_limit_remaining = rate_limit_remaining_values[-1] if rate_limit_remaining_values else None

    report: dict[str, Any] = {
        "report_name": "github_artifact_enrichment",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "input_path": normalize_path(args.input_path),
        "output_path": None if args.dry_run else normalize_path(output_path),
        "latest_output_path": None if args.dry_run else normalize_path(latest_output_path),
        "dry_run": bool(args.dry_run),
        "limit": args.limit,
        "sleep_sec": args.sleep_sec,
        "timeout_sec": args.timeout_sec,
        "token_env": args.token_env,
        "token_present": token_present,
        "input_entities_count": len(all_entities),
        "github_entities_count": len(github_entities_all),
        "requested_count": len(github_entities),
        "processed_count": len(rows),
        "found_count": int(status_distribution.get("found", 0)),
        "not_found_count": int(status_distribution.get("not_found", 0)),
        "forbidden_count": int(status_distribution.get("forbidden", 0)),
        "rate_limited_count": int(status_distribution.get("rate_limited", 0)),
        "error_count": int(status_distribution.get("error", 0)),
        "skipped_invalid_external_id_count": int(status_distribution.get("skipped_invalid_external_id", 0)) + skipped_invalid if args.dry_run else int(status_distribution.get("skipped_invalid_external_id", 0)),
        "status_distribution": dict(sorted((str(k), int(v)) for k, v in status_distribution.items() if k is not None)),
        "rate_limit_remaining": rate_limit_remaining,
        "warnings": warnings,
        "ok": True,
    }

    if not args.dry_run:
        if report["processed_count"] == 0 and report["requested_count"] > 0:
            report["ok"] = False
            warnings.append("No GitHub rows were processed.")
        if report["rate_limited_count"] > 0:
            report["ok"] = False
        # Network/API errors are allowed to be represented row-wise, but a run with only errors is not useful.
        if report["found_count"] == 0 and report["processed_count"] > 0 and report["error_count"] == report["processed_count"]:
            report["ok"] = False

    latest_report_json = args.report_dir / "github_artifact_enrichment_latest.json"
    latest_report_md = args.report_dir / "github_artifact_enrichment_latest.md"
    history_report_json = args.report_dir / "history" / f"github_artifact_enrichment_{run_ts}.json"
    history_report_md = args.report_dir / "history" / f"github_artifact_enrichment_{run_ts}.md"

    write_json(latest_report_json, report)
    write_json(history_report_json, report)
    markdown = build_markdown_report(report)
    ensure_parent(latest_report_md)
    latest_report_md.write_text(markdown, encoding="utf-8")
    ensure_parent(history_report_md)
    history_report_md.write_text(markdown, encoding="utf-8")

    print(f"[OK] report JSON: {latest_report_json}")
    print(f"[OK] report Markdown: {latest_report_md}")
    if not args.dry_run:
        print(f"[OK] output JSONL: {output_path}")
        print(f"[OK] latest output JSONL: {latest_output_path}")
    print(f"[OK] ok={report['ok']}")

    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
