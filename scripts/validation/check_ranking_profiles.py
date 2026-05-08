from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.ranking.profiles import (
    DEFAULT_RANKING_PROFILES_PATH,
    load_ranking_profiles,
)


DEFAULT_REPORTS_DIR = Path("artifacts/reports/ranking")

REQUIRED_PROFILE_NAMES = {
    "recent_artifact_ready",
    "huggingface_ready",
    "acl_radar",
}


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


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Ranking profiles quality check")
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

    lines.append("## Profiles")
    for profile in report.get("profiles", []):
        lines.append(f"### {profile['name']}")
        lines.append(f"- description: `{profile['description']}`")
        lines.append(f"- sort_by: `{profile['sort_by']}`")
        lines.append(f"- top_k: `{profile['top_k']}`")
        lines.append(f"- descending: `{profile['descending']}`")
        lines.append(f"- filters: `{profile['filters']}`")
        lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    if report.get("validation_error"):
        lines.append("## Validation error")
        lines.append("```text")
        lines.append(str(report["validation_error"]))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate ranking profiles config."
    )
    parser.add_argument(
        "--profiles-path",
        type=Path,
        default=DEFAULT_RANKING_PROFILES_PATH,
    )
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    validation_error: str | None = None
    profiles_payload: dict[str, Any] | None = None

    try:
        profiles_payload = load_ranking_profiles(args.profiles_path)
    except Exception as exc:
        validation_error = str(exc)

    profiles = []
    profile_names: list[str] = []
    default_profile = None

    if profiles_payload:
        default_profile = profiles_payload.get("default_profile")
        profiles_map = profiles_payload.get("profiles") or {}
        profile_names = sorted(profiles_map.keys())
        profiles = [profiles_map[name] for name in profile_names]

    missing_required_profiles = sorted(REQUIRED_PROFILE_NAMES - set(profile_names))

    checks = {
        "profiles_config_exists": args.profiles_path.exists(),
        "profiles_config_valid": validation_error is None,
        "profiles_non_empty": len(profile_names) > 0,
        "required_profiles_present": len(missing_required_profiles) == 0,
        "default_profile_present": default_profile is not None,
        "default_profile_exists": default_profile in profile_names if default_profile else False,
    }

    required_failed_checks = [name for name, ok in checks.items() if not ok]

    report = {
        "report_name": "ranking_profiles_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "profiles_path": normalize_path(args.profiles_path),
            "reports_dir": normalize_path(args.reports_dir),
            "required_profile_names": sorted(REQUIRED_PROFILE_NAMES),
        },
        "summary": {
            "schema_version": profiles_payload.get("schema_version") if profiles_payload else None,
            "default_profile": default_profile,
            "profile_count": len(profile_names),
            "profile_names": profile_names,
            "missing_required_profiles": missing_required_profiles,
        },
        "checks": checks,
        "profiles": profiles,
        "validation_error": validation_error,
        "verdict": {
            "ok": len(required_failed_checks) == 0,
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
        },
    }

    latest_json = args.reports_dir / "ranking_profiles_quality_latest.json"
    latest_md = args.reports_dir / "ranking_profiles_quality_latest.md"
    history_json = args.reports_dir / "history" / f"ranking_profiles_quality_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"ranking_profiles_quality_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    print(f"[OK] profiles_config_exists={checks['profiles_config_exists']}")
    print(f"[OK] profiles_config_valid={checks['profiles_config_valid']}")
    print(f"[OK] profile_count={report['summary']['profile_count']}")
    print(f"[OK] profile_names={report['summary']['profile_names']}")
    print(f"[OK] default_profile={report['summary']['default_profile']}")
    print(f"[OK] required_profiles_present={checks['required_profiles_present']}")
    print(f"[OK] ok={report['verdict']['ok']}")
    print(f"[OK] required_failed_count={report['verdict']['required_failed_count']}")
    print(f"[OK] required_failed_checks={report['verdict']['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if args.strict and not report["verdict"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()