"""Validate Citation / Reference Graph release-candidate readiness.

This validator is intentionally read-only. It checks whether the already generated
Citation / Reference Graph output is technically ready to be treated as a local
reviewable candidate artifact.

It does not rebuild graph output, mutate canonical truth, touch Postgres/Qdrant,
change API/UI behavior, package graph files, or publish anything.
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


SCHEMA_VERSION = "citation_reference_graph_release_candidate_v1"

DEFAULT_GRAPH_DIR = Path("data/graphs/citation_reference_graph/v0.1")
DEFAULT_REPORT_DIR = Path("artifacts/reports/validation")
DEFAULT_OUTPUT_REPORT = DEFAULT_REPORT_DIR / "citation_reference_graph_output_latest.json"
DEFAULT_INSPECTION_REPORT = DEFAULT_REPORT_DIR / "citation_reference_graph_inspection_latest.json"
DEFAULT_QUERY_CLI_PATH = Path("scripts/graph/query_citation_reference_graph.py")

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
    "nodes_count": 529295,
    "edges_count": 745516,
    "node_paper_count": 60954,
    "node_external_reference_count": 468336,
    "node_source_family_count": 5,
    "edge_paper_references_paper_count": 6165,
    "edge_paper_references_external_count": 703234,
    "edge_paper_has_reference_source_family_count": 36117,
}

ACCEPTED_INSPECTION_COUNTS = {
    "resolved_reference_edges_count": 6165,
    "unresolved_reference_edges_count": 703234,
    "reference_resolution_ratio": 0.00869,
}

FALSE_SAFETY_FLAGS = (
    "may_overwrite_operational_latest",
    "may_be_used_as_reconcile_input",
    "may_change_db_schema",
    "may_change_api_behavior",
    "may_change_streamlit_behavior",
    "may_change_retrieval_behavior",
    "may_change_qdrant_behavior",
    "may_change_ranking_behavior",
    "may_require_graph_runtime",
    "may_publish_without_manual_review",
)


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
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bool_ok_report(report: dict[str, Any]) -> bool:
    if report.get("ok") is True:
        return True
    summary = _as_dict(report.get("summary"))
    if summary.get("ok") is True:
        return True
    verdict = _as_dict(report.get("verdict"))
    if verdict.get("ok") is True:
        return True
    return False


def _required_failed_count(report: dict[str, Any]) -> int | None:
    for container_key in ("summary", "verdict"):
        container = _as_dict(report.get(container_key))
        value = container.get("required_failed_count")
        if isinstance(value, int):
            return value
    value = report.get("required_failed_count")
    if isinstance(value, int):
        return value
    found = _recursive_find_first(report, "required_failed_count")
    if isinstance(found, int):
        return found
    return None


def _recursive_find_first(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _recursive_find_first(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _recursive_find_first(item, key)
            if found is not None:
                return found
    return None


def _recursive_find_number(obj: Any, key: str) -> int | float | None:
    value = _recursive_find_first(obj, key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    if as_float.is_integer():
        return int(as_float)
    return as_float


def _manifest_safety(manifest: dict[str, Any]) -> dict[str, Any]:
    safety = _as_dict(manifest.get("safety"))
    builder = _as_dict(manifest.get("builder"))
    return {
        "canonical_truth_impact": safety.get("canonical_truth_impact"),
        "builder_input_mode": builder.get("input_mode"),
        "live_db_dependency": builder.get("live_db_dependency"),
        **{key: safety.get(key) for key in FALSE_SAFETY_FLAGS},
    }


def _data_quality_ok(data_quality_summary: dict[str, Any]) -> bool:
    summary = _as_dict(data_quality_summary.get("summary"))
    return summary.get("ok") is True or data_quality_summary.get("ok") is True


def make_check(name: str, ok: bool, required: bool, message: str, details: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(name=name, ok=bool(ok), required=required, message=message, details=details)


def collect_graph_stats(graph_dir: Path) -> dict[str, Any]:
    node_counts: Counter[str] = Counter()
    edge_counts: Counter[str] = Counter()
    node_ids: set[str] = set()
    duplicate_node_ids: list[str] = []
    edge_ids: set[str] = set()
    duplicate_edge_ids: list[str] = []
    dangling_edges: list[str] = []
    invalid_confidence_edges: list[str] = []
    node_id_set_for_edges: set[str] = set()

    for node in iter_jsonl(graph_dir / "nodes.jsonl"):
        node_id = str(node.get("node_id")) if node.get("node_id") else None
        if node_id:
            if node_id in node_ids:
                duplicate_node_ids.append(node_id)
            node_ids.add(node_id)
            node_id_set_for_edges.add(node_id)
        node_counts[str(node.get("node_type") or "<missing>")] += 1

    openalex_reference_edges_count = 0
    doi_like_openalex_edges: list[str] = []
    top_external_counter: Counter[str] = Counter()
    top_referenced_counter: Counter[str] = Counter()

    for edge in iter_jsonl(graph_dir / "edges.jsonl"):
        edge_id = str(edge.get("edge_id")) if edge.get("edge_id") else "<missing>"
        if edge_id in edge_ids:
            duplicate_edge_ids.append(edge_id)
        edge_ids.add(edge_id)

        edge_type = str(edge.get("edge_type") or "<missing>")
        edge_counts[edge_type] += 1

        source_node_id = edge.get("source_node_id")
        target_node_id = edge.get("target_node_id")
        if source_node_id not in node_id_set_for_edges or target_node_id not in node_id_set_for_edges:
            dangling_edges.append(edge_id)

        try:
            confidence = float(edge.get("confidence"))
            if not 0.0 <= confidence <= 1.0:
                invalid_confidence_edges.append(edge_id)
        except Exception:  # noqa: BLE001 - report bad local data instead of crashing.
            invalid_confidence_edges.append(edge_id)

        reference_type = str(edge.get("reference_type") or "")
        reference_value = str(edge.get("reference_value") or "")
        target_reference_key = str(edge.get("target_reference_key") or "")
        reference_field = str(edge.get("reference_field") or "")
        combined_reference_text = "|".join([reference_type, reference_value, target_reference_key]).lower()

        if reference_type == "openalex_id":
            openalex_reference_edges_count += 1
        if reference_type == "doi" and "openalex.org" in combined_reference_text:
            doi_like_openalex_edges.append(edge_id)
        if reference_field == "referenced_ids" and reference_type == "doi" and reference_value.lower().startswith("w"):
            doi_like_openalex_edges.append(edge_id)

        if edge_type == "paper_references_external":
            top_external_counter[target_reference_key or str(target_node_id)] += 1
        elif edge_type == "paper_references_paper":
            top_referenced_counter[str(edge.get("target_canonical_id") or target_node_id)] += 1

    return {
        "nodes_count": sum(node_counts.values()),
        "edges_count": sum(edge_counts.values()),
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "derived_counts": {
            "node_paper_count": node_counts.get("paper", 0),
            "node_external_reference_count": node_counts.get("external_reference", 0),
            "node_source_family_count": node_counts.get("source_family", 0),
            "edge_paper_references_paper_count": edge_counts.get("paper_references_paper", 0),
            "edge_paper_references_external_count": edge_counts.get("paper_references_external", 0),
            "edge_paper_has_reference_source_family_count": edge_counts.get("paper_has_reference_source_family", 0),
        },
        "duplicate_node_ids": sorted(set(duplicate_node_ids)),
        "duplicate_edge_ids": sorted(set(duplicate_edge_ids)),
        "dangling_edges": sorted(set(dangling_edges)),
        "invalid_confidence_edges": sorted(set(invalid_confidence_edges)),
        "openalex_reference_edges_count": openalex_reference_edges_count,
        "doi_like_openalex_edges": sorted(set(doi_like_openalex_edges)),
        "top_referenced_papers_sample": [
            {"target_canonical_id": key, "count": value} for key, value in top_referenced_counter.most_common(5)
        ],
        "top_external_references_sample": [
            {"reference_key": key, "count": value} for key, value in top_external_counter.most_common(5)
        ],
    }


def check_release_candidate(
    graph_dir: Path,
    report_dir: Path,
    output_report_path: Path | None,
    inspection_report_path: Path | None,
    query_cli_path: Path | None,
    *,
    strict: bool = False,
    expected_graph_counts: dict[str, int] | None = None,
    expected_inspection_counts: dict[str, int | float] | None = None,
    require_openalex_normalization_smoke: bool = True,
    require_query_cli_presence: bool = True,
    write_reports: bool = True,
) -> dict[str, Any]:
    graph_dir = Path(graph_dir)
    report_dir = Path(report_dir)
    output_report_path = Path(output_report_path) if output_report_path else None
    inspection_report_path = Path(inspection_report_path) if inspection_report_path else None
    query_cli_path = Path(query_cli_path) if query_cli_path else None
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

    schema: dict[str, Any] = {}
    manifest: dict[str, Any] = {}
    data_quality_summary: dict[str, Any] = {}
    graph_stats: dict[str, Any] = {}

    if not missing_files:
        try:
            schema = load_json(graph_dir / "schema.json")
            manifest = load_json(graph_dir / "manifest.json")
            data_quality_summary = load_json(graph_dir / "data_quality_summary.json")
            graph_stats = collect_graph_stats(graph_dir)
            checks.append(make_check("graph_json_readable", True, True, "Graph JSON/JSONL files are readable"))
        except Exception as exc:  # noqa: BLE001 - validator should report any local data issue.
            checks.append(make_check("graph_json_readable", False, True, f"Failed to read graph output: {exc}"))

    if schema:
        graph_identity = _as_dict(schema.get("graph"))
        checks.append(
            make_check(
                "schema_identity",
                schema.get("schema_version") == "citation_reference_graph_schema_v1"
                and graph_identity.get("name") == "citation_reference_graph"
                and graph_identity.get("version") == "v0.1",
                True,
                "Schema identity matches Citation / Reference Graph v0.1",
                {"schema_version": schema.get("schema_version"), "graph": graph_identity},
            )
        )

    if manifest:
        graph_identity = _as_dict(manifest.get("graph"))
        safety = _manifest_safety(manifest)
        false_flag_mismatches = {
            key: safety.get(key) for key in FALSE_SAFETY_FLAGS if safety.get(key) is not False
        }
        safety_mismatches: dict[str, Any] = dict(false_flag_mismatches)
        if safety.get("canonical_truth_impact") != "none":
            safety_mismatches["canonical_truth_impact"] = safety.get("canonical_truth_impact")
        if safety.get("builder_input_mode") != "file":
            safety_mismatches["builder_input_mode"] = safety.get("builder_input_mode")
        if safety.get("live_db_dependency") is not False:
            safety_mismatches["live_db_dependency"] = safety.get("live_db_dependency")

        checks.append(
            make_check(
                "manifest_identity",
                manifest.get("schema_version") == "citation_reference_graph_manifest_v1"
                and graph_identity.get("name") == "citation_reference_graph"
                and graph_identity.get("version") == "v0.1",
                True,
                "Manifest identity matches Citation / Reference Graph v0.1",
                {"schema_version": manifest.get("schema_version"), "graph": graph_identity},
            )
        )
        checks.append(
            make_check(
                "manifest_safety_flags",
                not safety_mismatches,
                True,
                "Manifest safety flags preserve derived-layer boundaries"
                if not safety_mismatches
                else "Manifest safety flags do not match expected derived-layer boundaries",
                {"safety": safety, "mismatches": safety_mismatches},
            )
        )

    if data_quality_summary:
        checks.append(
            make_check(
                "data_quality_summary_ok",
                _data_quality_ok(data_quality_summary),
                True,
                "Data quality summary is ok",
                {"summary": _as_dict(data_quality_summary.get("summary"))},
            )
        )

    if graph_stats:
        duplicate_node_ids = graph_stats.get("duplicate_node_ids", [])
        duplicate_edge_ids = graph_stats.get("duplicate_edge_ids", [])
        dangling_edges = graph_stats.get("dangling_edges", [])
        invalid_confidence_edges = graph_stats.get("invalid_confidence_edges", [])
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
        checks.append(
            make_check(
                "edges_reference_existing_nodes",
                not dangling_edges,
                True,
                "Edges reference existing nodes" if not dangling_edges else "Dangling graph edges found",
                {"dangling_edges_sample": dangling_edges[:20]},
            )
        )
        checks.append(
            make_check(
                "edge_confidence_range_ok",
                not invalid_confidence_edges,
                True,
                "Edge confidence values are in [0, 1]"
                if not invalid_confidence_edges
                else "Invalid edge confidence values found",
                {"invalid_confidence_edges_sample": invalid_confidence_edges[:20]},
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
                    "Graph counts match the accepted post-normalization v0.1 baseline"
                    if not mismatches
                    else "Graph counts differ from the accepted post-normalization v0.1 baseline",
                    {"mismatches": mismatches, "actual_counts": actual_counts},
                )
            )

        if require_openalex_normalization_smoke:
            doi_like_openalex_edges = graph_stats.get("doi_like_openalex_edges", [])
            openalex_edges_count = int(graph_stats.get("openalex_reference_edges_count") or 0)
            checks.append(
                make_check(
                    "openalex_reference_normalization",
                    openalex_edges_count > 0 and not doi_like_openalex_edges,
                    True,
                    "OpenAlex references are present as openalex_id and not DOI-like URL values"
                    if openalex_edges_count > 0 and not doi_like_openalex_edges
                    else "OpenAlex reference normalization smoke failed",
                    {
                        "openalex_reference_edges_count": openalex_edges_count,
                        "doi_like_openalex_edges_sample": doi_like_openalex_edges[:20],
                    },
                )
            )

    if not missing_files:
        checksum_path = graph_dir / "checksums.txt"
        try:
            expected_checksums = parse_checksums(checksum_path)
            checksum_mismatches: dict[str, Any] = {}
            checksum_missing: list[str] = []
            for name in REQUIRED_GRAPH_FILES:
                if name == "checksums.txt":
                    continue
                path = graph_dir / name
                actual_checksum = sha256_file(path)
                expected_checksum = expected_checksums.get(name)
                if expected_checksum is None:
                    checksum_missing.append(name)
                elif expected_checksum != actual_checksum:
                    checksum_mismatches[name] = {"expected": expected_checksum, "actual": actual_checksum}
            checks.append(
                make_check(
                    "checksums_match",
                    not checksum_missing and not checksum_mismatches,
                    True,
                    "Checksums match required graph files"
                    if not checksum_missing and not checksum_mismatches
                    else "Checksum issues found",
                    {"missing": checksum_missing, "mismatches": checksum_mismatches},
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("checksums_match", False, True, f"Failed to validate checksums: {exc}"))

    output_report: dict[str, Any] = {}
    if output_report_path and output_report_path.exists():
        try:
            output_report = load_json(output_report_path)
            failed_count = _required_failed_count(output_report)
            ok = _bool_ok_report(output_report) and failed_count == 0
            checks.append(
                make_check(
                    "output_validator_report_ok",
                    ok,
                    strict,
                    "Output validator report is ok with zero required failures"
                    if ok
                    else "Output validator report is not ok or has required failures",
                    {"path": str(output_report_path), "required_failed_count": failed_count},
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                make_check(
                    "output_validator_report_ok",
                    False,
                    strict,
                    f"Failed to read output validator report: {exc}",
                    {"path": str(output_report_path)},
                )
            )
    else:
        checks.append(
            make_check(
                "output_validator_report_exists",
                False,
                strict,
                "Output validator report is missing",
                {"path": str(output_report_path) if output_report_path else None},
            )
        )

    inspection_report: dict[str, Any] = {}
    if inspection_report_path and inspection_report_path.exists():
        try:
            inspection_report = load_json(inspection_report_path)
            failed_count = _required_failed_count(inspection_report)
            ok = _bool_ok_report(inspection_report) and failed_count == 0
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
            actual = _recursive_find_number(inspection_report, key)
            if isinstance(expected, float):
                matches = actual is not None and abs(float(actual) - expected) < 1e-9
            else:
                matches = actual == expected
            if not matches:
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

    if require_query_cli_presence:
        checks.append(
            make_check(
                "query_cli_file_exists",
                bool(query_cli_path and query_cli_path.exists()),
                True,
                "Query CLI file exists" if query_cli_path and query_cli_path.exists() else "Query CLI file is missing",
                {"path": str(query_cli_path) if query_cli_path else None},
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
        "output_report_path": str(output_report_path) if output_report_path else None,
        "inspection_report_path": str(inspection_report_path) if inspection_report_path else None,
        "query_cli_path": str(query_cli_path) if query_cli_path else None,
        "report_dir": str(report_dir),
        "summary": summary,
        "graph_stats": graph_stats,
        "manifest_safety": _manifest_safety(manifest) if manifest else {},
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
            "manual_review_complete": False,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "required_failed_checks": [check.name for check in required_failed],
            "warning_checks": [check.name for check in warnings],
        },
        "boundaries": {
            "read_only": True,
            "rebuilds_graph": False,
            "packages_graph": False,
            "publishes_graph": False,
            "mutates_canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "changes_postgres": False,
            "changes_db_schema": False,
            "changes_qdrant": False,
            "changes_retrieval": False,
            "changes_ranking": False,
            "changes_api": False,
            "changes_ui": False,
            "requires_networkx_runtime": False,
            "requires_neo4j_runtime": False,
            "requires_graphrag_runtime": False,
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
        "# Citation / Reference Graph Release Candidate Check",
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
        f"- manual_review_complete: `{verdict['manual_review_complete']}`",
        f"- publication_ready: `{verdict['publication_ready']}`",
        f"- publication_block_reason: `{verdict['publication_block_reason']}`",
        "",
        "## Graph counters",
        "",
        f"- nodes_count: `{graph_stats.get('nodes_count')}`",
        f"- edges_count: `{graph_stats.get('edges_count')}`",
        f"- openalex_reference_edges_count: `{graph_stats.get('openalex_reference_edges_count')}`",
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
    latest_json = report_dir / "citation_reference_graph_release_candidate_latest.json"
    latest_md = report_dir / "citation_reference_graph_release_candidate_latest.md"
    history_json = history_dir / f"citation_reference_graph_release_candidate_{run_ts}.json"
    history_md = history_dir / f"citation_reference_graph_release_candidate_{run_ts}.md"

    json_text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    md_text = render_markdown(result)

    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(md_text, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Citation / Reference Graph release-candidate readiness.")
    parser.add_argument("--graph-dir", type=Path, default=DEFAULT_GRAPH_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_REPORT)
    parser.add_argument("--inspection-report", type=Path, default=DEFAULT_INSPECTION_REPORT)
    parser.add_argument("--query-cli-path", type=Path, default=DEFAULT_QUERY_CLI_PATH)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--no-write-reports",
        action="store_true",
        help="Run checks without writing latest/history validation reports.",
    )
    parser.add_argument(
        "--skip-accepted-counts",
        action="store_true",
        help="Do not require accepted post-normalization graph v0.1 baseline counters.",
    )
    parser.add_argument(
        "--skip-inspection-diagnostic-counts",
        action="store_true",
        help="Do not compare accepted inspection diagnostic counters.",
    )
    parser.add_argument(
        "--skip-report-checks",
        action="store_true",
        help="Do not require latest output/inspection validator reports in strict mode.",
    )
    parser.add_argument(
        "--skip-openalex-normalization-smoke",
        action="store_true",
        help="Do not require the OpenAlex reference normalization smoke check.",
    )
    parser.add_argument(
        "--skip-query-cli-presence",
        action="store_true",
        help="Do not require scripts/graph/query_citation_reference_graph.py to exist.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    result = check_release_candidate(
        graph_dir=args.graph_dir,
        report_dir=args.report_dir,
        output_report_path=None if args.skip_report_checks else args.output_report,
        inspection_report_path=None if args.skip_report_checks else args.inspection_report,
        query_cli_path=None if args.skip_query_cli_presence else args.query_cli_path,
        strict=args.strict,
        expected_graph_counts=None if args.skip_accepted_counts else ACCEPTED_GRAPH_COUNTS,
        expected_inspection_counts=None if args.skip_inspection_diagnostic_counts else ACCEPTED_INSPECTION_COUNTS,
        require_openalex_normalization_smoke=not args.skip_openalex_normalization_smoke,
        require_query_cli_presence=not args.skip_query_cli_presence,
        write_reports=not args.no_write_reports,
    )

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    if not result["summary"]["ok"]:
        print("required_failed_checks:", ", ".join(result["verdict"]["required_failed_checks"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
