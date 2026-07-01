"""Validate Paper-Artifact Graph release-candidate readiness.

This validator is intentionally read-only. It checks whether the already generated
Paper-Artifact Graph output is technically ready to be treated as a local
reviewable candidate artifact.

It does not rebuild graph output, mutate canonical truth, touch Postgres/Qdrant,
change API/UI behavior, or publish anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "paper_artifact_graph_release_candidate_v1"

DEFAULT_GRAPH_DIR = Path("data/graphs/paper_artifact_graph/v0.1")
DEFAULT_REPORT_DIR = Path("artifacts/reports/validation")
DEFAULT_INSPECTION_REPORT = DEFAULT_REPORT_DIR / "paper_artifact_graph_inspection_latest.json"

REQUIRED_GRAPH_FILES = (
    "nodes.jsonl",
    "edges.jsonl",
    "schema.json",
    "manifest.json",
    "data_quality_summary.json",
    "README.md",
    "checksums.txt",
)

ACCEPTED_GRAPH_COUNTS = {
    "nodes_count": 68385,
    "edges_count": 163757,
    "node_paper_count": 60954,
    "node_artifact_count": 7336,
    "node_provider_count": 10,
    "node_source_family_count": 5,
    "node_topic_cluster_count": 80,
    "edge_paper_has_artifact_count": 7430,
    "edge_artifact_from_provider_count": 7336,
    "edge_paper_observed_in_source_family_count": 88037,
    "edge_paper_assigned_to_topic_cluster_count": 60954,
}

ACCEPTED_INSPECTION_COUNTS = {
    "papers_with_artifacts_count": 6673,
    "topic_clusters_with_artifact_ready_papers_count": 80,
}

ACCEPTED_PROVIDER_SMOKE = {
    "provider": "github",
    "artifacts": 5953,
    "paper_artifact_links": 6019,
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool
    message: str
    details: dict[str, Any] | None = None

    @property
    def status(self) -> str:
        if self.ok:
            return "passed"
        if self.required:
            return "failed"
        return "warning"


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSONL record: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: JSONL record must be an object")
            yield record


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def parse_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if is_sha256(parts[0]):
            checksum = parts[0].lower()
            filename = parts[1].lstrip("*")
        elif is_sha256(parts[-1]):
            checksum = parts[-1].lower()
            filename = parts[0].lstrip("*")
        else:
            continue
        checksums[filename.replace("\\", "/")] = checksum
    return checksums


def record_type(record: dict[str, Any]) -> str | None:
    value = record.get("type") or record.get("node_type") or record.get("edge_type") or record.get("kind")
    if value is None:
        return None
    return str(value)


def record_id(record: dict[str, Any]) -> str | None:
    value = record.get("id") or record.get("node_id") or record.get("edge_id")
    if value is None:
        return None
    return str(value)


def edge_source(record: dict[str, Any]) -> str | None:
    for key in ("source_node_id", "source", "source_id", "from", "from_id", "src"):
        value = record.get(key)
        if value is not None:
            return str(value)
    return None


def edge_target(record: dict[str, Any]) -> str | None:
    for key in ("target_node_id", "target", "target_id", "to", "to_id", "dst"):
        value = record.get(key)
        if value is not None:
            return str(value)
    return None


def recursive_find_first(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = recursive_find_first(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = recursive_find_first(item, key)
            if found is not None:
                return found
    return None


def recursive_find_int(obj: Any, key: str) -> int | None:
    value = recursive_find_first(obj, key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def manifest_builder_input_mode(manifest: dict[str, Any]) -> Any:
    builder = manifest.get("builder")
    if isinstance(builder, dict):
        value = builder.get("input_mode")
        if value is not None:
            return value

    value = recursive_find_first(manifest, "builder_input_mode")
    if value is not None:
        return value

    return recursive_find_first(manifest, "input_mode")


def manifest_safety_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "canonical_truth",
        "may_be_used_as_reconcile_input",
        "publication_ready",
        "dry_run",
        "live_db_dependency",
        "create_latest_pointer",
    )
    summary = {key: recursive_find_first(manifest, key) for key in keys}
    summary["builder_input_mode"] = manifest_builder_input_mode(manifest)
    return summary


def data_quality_ok(data_quality_summary: dict[str, Any]) -> bool:
    if data_quality_summary.get("ok") is True:
        return True
    if data_quality_summary.get("status") in {"ok", "green", "passed"}:
        return True
    summary = data_quality_summary.get("summary")
    if isinstance(summary, dict) and summary.get("ok") is True:
        return True
    return False


def inspection_ok(report: dict[str, Any]) -> bool:
    if report.get("ok") is True:
        return True
    summary = report.get("summary")
    if isinstance(summary, dict) and summary.get("ok") is True:
        return True
    verdict = report.get("verdict")
    if isinstance(verdict, dict) and verdict.get("ok") is True:
        return True
    return False


def inspection_required_failed_count(report: dict[str, Any]) -> int | None:
    for container_key in ("summary", "verdict"):
        container = report.get(container_key)
        if isinstance(container, dict):
            value = container.get("required_failed_count")
            if isinstance(value, int):
                return value
    value = report.get("required_failed_count")
    if isinstance(value, int):
        return value
    return recursive_find_int(report, "required_failed_count")


def collect_graph_stats(graph_dir: Path) -> dict[str, Any]:
    nodes_path = graph_dir / "nodes.jsonl"
    edges_path = graph_dir / "edges.jsonl"

    node_counts: Counter[str] = Counter()
    edge_counts: Counter[str] = Counter()
    node_ids: set[str] = set()
    duplicate_node_ids: list[str] = []
    edge_ids: set[str] = set()
    duplicate_edge_ids: list[str] = []

    for node in iter_jsonl(nodes_path):
        node_id = record_id(node)
        if node_id:
            if node_id in node_ids:
                duplicate_node_ids.append(node_id)
            node_ids.add(node_id)
        node_counts[record_type(node) or "<missing>"] += 1

    provider_artifacts: dict[str, set[str]] = {}
    paper_artifact_edges: list[tuple[str | None, str | None]] = []

    for edge in iter_jsonl(edges_path):
        edge_id = record_id(edge)
        if edge_id:
            if edge_id in edge_ids:
                duplicate_edge_ids.append(edge_id)
            edge_ids.add(edge_id)

        edge_kind = record_type(edge) or "<missing>"
        edge_counts[edge_kind] += 1
        src = edge_source(edge)
        dst = edge_target(edge)

        if edge_kind == "artifact_from_provider" and src and dst and dst.startswith("provider:"):
            provider = dst.split(":", 1)[1]
            provider_artifacts.setdefault(provider, set()).add(src)
        elif edge_kind == "paper_has_artifact":
            paper_artifact_edges.append((src, dst))

    provider_smoke: dict[str, dict[str, int]] = {}
    for provider, artifacts in provider_artifacts.items():
        link_count = sum(1 for _, artifact_id in paper_artifact_edges if artifact_id in artifacts)
        provider_smoke[provider] = {
            "artifacts": len(artifacts),
            "paper_artifact_links": link_count,
        }

    return {
        "nodes_count": sum(node_counts.values()),
        "edges_count": sum(edge_counts.values()),
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "duplicate_node_ids": sorted(set(duplicate_node_ids)),
        "duplicate_edge_ids": sorted(set(duplicate_edge_ids)),
        "provider_smoke": provider_smoke,
        "derived_counts": {
            "node_paper_count": node_counts.get("paper", 0),
            "node_artifact_count": node_counts.get("artifact", 0),
            "node_provider_count": node_counts.get("provider", 0),
            "node_source_family_count": node_counts.get("source_family", 0),
            "node_topic_cluster_count": node_counts.get("topic_cluster", 0),
            "edge_paper_has_artifact_count": edge_counts.get("paper_has_artifact", 0),
            "edge_artifact_from_provider_count": edge_counts.get("artifact_from_provider", 0),
            "edge_paper_observed_in_source_family_count": edge_counts.get("paper_observed_in_source_family", 0),
            "edge_paper_assigned_to_topic_cluster_count": edge_counts.get("paper_assigned_to_topic_cluster", 0),
        },
    }


def make_check(name: str, ok: bool, required: bool, message: str, details: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(name=name, ok=ok, required=required, message=message, details=details)


def check_release_candidate(
    graph_dir: Path,
    report_dir: Path,
    inspection_report_path: Path | None,
    *,
    strict: bool = False,
    expected_graph_counts: dict[str, int] | None = None,
    expected_inspection_counts: dict[str, int] | None = None,
    expected_provider_smoke: dict[str, Any] | None = None,
    write_reports: bool = True,
) -> dict[str, Any]:
    graph_dir = Path(graph_dir)
    report_dir = Path(report_dir)
    inspection_report_path = Path(inspection_report_path) if inspection_report_path else None
    checks: list[CheckResult] = []

    required_files = [graph_dir / name for name in REQUIRED_GRAPH_FILES]
    missing_files = [str(path) for path in required_files if not path.exists()]
    checks.append(
        make_check(
            "graph_output_files_exist",
            not missing_files,
            True,
            "Required graph output files are present" if not missing_files else "Required graph output files are missing",
            {"missing_files": missing_files},
        )
    )

    manifest: dict[str, Any] = {}
    data_quality_summary: dict[str, Any] = {}
    graph_stats: dict[str, Any] = {}

    if not missing_files:
        try:
            manifest = load_json(graph_dir / "manifest.json")
            data_quality_summary = load_json(graph_dir / "data_quality_summary.json")
            graph_stats = collect_graph_stats(graph_dir)
            checks.append(make_check("graph_json_readable", True, True, "Graph JSON/JSONL files are readable"))
        except Exception as exc:  # noqa: BLE001 - validator should report any local data issue.
            checks.append(make_check("graph_json_readable", False, True, f"Failed to read graph output: {exc}"))

    if manifest:
        safety = manifest_safety_summary(manifest)
        expected_safety = {
            "canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "publication_ready": False,
            "dry_run": False,
            "live_db_dependency": False,
            "create_latest_pointer": False,
        }
        mismatches = {
            key: {"expected": expected, "actual": safety.get(key)}
            for key, expected in expected_safety.items()
            if safety.get(key) is not expected
        }
        checks.append(
            make_check(
                "manifest_safety_flags",
                not mismatches,
                True,
                "Manifest safety flags preserve derived-layer boundaries"
                if not mismatches
                else "Manifest safety flags do not match expected derived-layer boundaries",
                {"safety": safety, "mismatches": mismatches},
            )
        )
        checks.append(
            make_check(
                "manifest_file_mode",
                safety.get("builder_input_mode") == "file",
                True,
                "Builder input mode is file"
                if safety.get("builder_input_mode") == "file"
                else "Builder input mode is not file",
                {"builder_input_mode": safety.get("builder_input_mode")},
            )
        )

    if data_quality_summary:
        checks.append(
            make_check(
                "data_quality_summary_ok",
                data_quality_ok(data_quality_summary),
                True,
                "Data quality summary is ok",
                {"ok": data_quality_summary.get("ok"), "status": data_quality_summary.get("status")},
            )
        )

    if graph_stats:
        duplicate_node_ids = graph_stats.get("duplicate_node_ids", [])
        duplicate_edge_ids = graph_stats.get("duplicate_edge_ids", [])
        checks.append(
            make_check(
                "no_duplicate_node_ids",
                not duplicate_node_ids,
                True,
                "No duplicate node IDs" if not duplicate_node_ids else "Duplicate node IDs found",
                {"duplicate_node_ids_sample": duplicate_node_ids[:20]},
            )
        )
        checks.append(
            make_check(
                "no_duplicate_edge_ids",
                not duplicate_edge_ids,
                True,
                "No duplicate edge IDs" if not duplicate_edge_ids else "Duplicate edge IDs found",
                {"duplicate_edge_ids_sample": duplicate_edge_ids[:20]},
            )
        )

        if expected_graph_counts:
            actual_counts = {
                "nodes_count": graph_stats["nodes_count"],
                "edges_count": graph_stats["edges_count"],
                **graph_stats["derived_counts"],
            }
            mismatches = {
                key: {"expected": expected, "actual": actual_counts.get(key)}
                for key, expected in expected_graph_counts.items()
                if actual_counts.get(key) != expected
            }
            checks.append(
                make_check(
                    "accepted_graph_counts",
                    not mismatches,
                    True,
                    "Graph counts match the accepted v0.1 baseline"
                    if not mismatches
                    else "Graph counts differ from the accepted v0.1 baseline",
                    {"mismatches": mismatches, "actual_counts": actual_counts},
                )
            )

        if expected_provider_smoke:
            provider = str(expected_provider_smoke["provider"])
            actual_provider = graph_stats.get("provider_smoke", {}).get(provider)
            expected_provider = {
                "artifacts": int(expected_provider_smoke["artifacts"]),
                "paper_artifact_links": int(expected_provider_smoke["paper_artifact_links"]),
            }
            provider_mismatches = {
                key: {"expected": value, "actual": (actual_provider or {}).get(key)}
                for key, value in expected_provider.items()
                if not actual_provider or actual_provider.get(key) != value
            }
            checks.append(
                make_check(
                    f"provider_{provider}_query_smoke",
                    not provider_mismatches,
                    False,
                    f"Provider {provider!r} smoke counters match accepted diagnostics"
                    if not provider_mismatches
                    else f"Provider {provider!r} smoke counters differ from accepted diagnostics",
                    {
                        "provider": provider,
                        "expected": expected_provider,
                        "actual": actual_provider,
                        "mismatches": provider_mismatches,
                    },
                )
            )

    if not missing_files:
        checksum_path = graph_dir / "checksums.txt"
        try:
            expected_checksums = parse_checksums(checksum_path)
            checksum_mismatches: dict[str, Any] = {}
            for name in REQUIRED_GRAPH_FILES:
                if name == "checksums.txt":
                    continue
                path = graph_dir / name
                actual_checksum = sha256_file(path)
                expected_checksum = expected_checksums.get(name)
                if expected_checksum != actual_checksum:
                    checksum_mismatches[name] = {"expected": expected_checksum, "actual": actual_checksum}
            checks.append(
                make_check(
                    "checksums_match",
                    not checksum_mismatches,
                    True,
                    "Checksums match required graph files"
                    if not checksum_mismatches
                    else "Checksum mismatches found",
                    {"mismatches": checksum_mismatches},
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("checksums_match", False, True, f"Failed to validate checksums: {exc}"))

    inspection_report: dict[str, Any] = {}
    if inspection_report_path and inspection_report_path.exists():
        try:
            inspection_report = load_json(inspection_report_path)
            failed_count = inspection_required_failed_count(inspection_report)
            ok = inspection_ok(inspection_report) and failed_count == 0
            checks.append(
                make_check(
                    "inspection_report_ok",
                    ok,
                    strict,
                    "Inspection report is ok with zero required failures"
                    if ok
                    else "Inspection report is not ok or has required failures",
                    {"path": str(inspection_report_path), "required_failed_count": failed_count},
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                make_check(
                    "inspection_report_ok",
                    False,
                    strict,
                    f"Failed to read inspection report: {exc}",
                    {"path": str(inspection_report_path)},
                )
            )
    else:
        checks.append(
            make_check(
                "inspection_report_exists",
                False,
                strict,
                "Inspection report is missing",
                {"path": str(inspection_report_path) if inspection_report_path else None},
            )
        )

    if inspection_report and expected_inspection_counts:
        inspection_mismatches = {}
        for key, expected in expected_inspection_counts.items():
            actual = recursive_find_int(inspection_report, key)
            if actual != expected:
                inspection_mismatches[key] = {"expected": expected, "actual": actual}
        checks.append(
            make_check(
                "accepted_inspection_counts",
                not inspection_mismatches,
                False,
                "Inspection counters match accepted diagnostics"
                if not inspection_mismatches
                else "Inspection counters differ from accepted diagnostics",
                {"mismatches": inspection_mismatches},
            )
        )

    required_failed = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    ok = not required_failed

    summary = {
        "ok": ok,
        "strict": strict,
        "required_failed_count": len(required_failed),
        "warning_count": len(warnings),
        "total_checks": len(checks),
    }

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "graph_dir": str(graph_dir),
        "inspection_report_path": str(inspection_report_path) if inspection_report_path else None,
        "report_dir": str(report_dir),
        "summary": summary,
        "graph_stats": graph_stats,
        "manifest_safety": manifest_safety_summary(manifest) if manifest else {},
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "ok": check.ok,
                "required": check.required,
                "message": check.message,
                "details": check.details or {},
            }
            for check in checks
        ],
        "verdict": {
            "technical_graph_candidate_ready": ok,
            "manual_review_required": True,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "required_failed_checks": [check.name for check in required_failed],
            "warning_checks": [check.name for check in warnings],
        },
        "boundaries": {
            "read_only": True,
            "rebuilds_graph": False,
            "mutates_canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "changes_postgres": False,
            "changes_qdrant": False,
            "changes_retrieval": False,
            "changes_ranking": False,
            "changes_api": False,
            "changes_ui": False,
            "publishes_dataset": False,
        },
    }

    if write_reports:
        write_validation_reports(result, report_dir)

    return result


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    verdict = result["verdict"]
    graph_stats = result.get("graph_stats") or {}

    lines = [
        "# Paper-Artifact Graph Release Candidate Check",
        "",
        f"- schema_version: `{result['schema_version']}`",
        f"- generated_at: `{result['generated_at']}`",
        f"- graph_dir: `{result['graph_dir']}`",
        f"- ok: `{summary['ok']}`",
        f"- strict: `{summary['strict']}`",
        f"- required_failed_count: `{summary['required_failed_count']}`",
        f"- warning_count: `{summary['warning_count']}`",
        "",
        "## Verdict",
        "",
        f"- technical_graph_candidate_ready: `{verdict['technical_graph_candidate_ready']}`",
        f"- manual_review_required: `{verdict['manual_review_required']}`",
        f"- publication_ready: `{verdict['publication_ready']}`",
        f"- publication_block_reason: `{verdict['publication_block_reason']}`",
        "",
        "## Graph counters",
        "",
        f"- nodes_count: `{graph_stats.get('nodes_count')}`",
        f"- edges_count: `{graph_stats.get('edges_count')}`",
        "",
        "### Node counts",
        "",
    ]

    for key, value in (graph_stats.get("node_counts") or {}).items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "### Edge counts", ""])
    for key, value in (graph_stats.get("edge_counts") or {}).items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Check | Required | Status | Message |",
            "|---|---:|---|---|",
        ]
    )
    for check in result["checks"]:
        message = str(check["message"]).replace("|", "\\|")
        lines.append(f"| `{check['name']}` | `{check['required']}` | `{check['status']}` | {message} |")

    lines.extend(["", "## Boundaries", ""])
    for key, value in result["boundaries"].items():
        lines.append(f"- {key}: `{value}`")

    lines.append("")
    return "\n".join(lines)


def write_validation_reports(result: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir = report_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    run_ts = utc_now_compact()
    latest_json = report_dir / "paper_artifact_graph_release_candidate_latest.json"
    latest_md = report_dir / "paper_artifact_graph_release_candidate_latest.md"
    history_json = history_dir / f"paper_artifact_graph_release_candidate_{run_ts}.json"
    history_md = history_dir / f"paper_artifact_graph_release_candidate_{run_ts}.md"

    json_text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    md_text = render_markdown(result)

    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(md_text, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Paper-Artifact Graph release-candidate readiness.")
    parser.add_argument("--graph-dir", type=Path, default=DEFAULT_GRAPH_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--inspection-report", type=Path, default=DEFAULT_INSPECTION_REPORT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--no-write-reports",
        action="store_true",
        help="Run checks without writing latest/history validation reports.",
    )
    parser.add_argument(
        "--skip-accepted-counts",
        action="store_true",
        help="Do not require accepted graph v0.1 baseline counters.",
    )
    parser.add_argument(
        "--skip-provider-smoke",
        action="store_true",
        help="Do not run provider github diagnostic smoke counter comparison.",
    )
    parser.add_argument(
        "--skip-inspection-diagnostic-counts",
        action="store_true",
        help="Do not compare accepted inspection diagnostic counters.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    result = check_release_candidate(
        graph_dir=args.graph_dir,
        report_dir=args.report_dir,
        inspection_report_path=args.inspection_report,
        strict=args.strict,
        expected_graph_counts=None if args.skip_accepted_counts else ACCEPTED_GRAPH_COUNTS,
        expected_inspection_counts=None if args.skip_inspection_diagnostic_counts else ACCEPTED_INSPECTION_COUNTS,
        expected_provider_smoke=None if args.skip_provider_smoke else ACCEPTED_PROVIDER_SMOKE,
        write_reports=not args.no_write_reports,
    )

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    if not result["summary"]["ok"]:
        print("required_failed_checks:", ", ".join(result["verdict"]["required_failed_checks"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
