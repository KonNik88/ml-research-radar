from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.api.schemas import (
    CitationGraphStatusGraph,
    CitationGraphStatusResponse,
)
from services.api.settings import ApiSettings


GRAPH_NAME = "citation_reference_graph"
STATUS_ENDPOINT = "/citation-graph/status"

DEFAULT_CITATION_GRAPH_CAVEATS = [
    "metadata_reference_fields_only",
    "not_a_complete_citation_index",
    "manual_review_required",
    "publication_ready_false",
]

REQUIRED_GRAPH_FILES = (
    "nodes.jsonl",
    "edges.jsonl",
    "schema.json",
    "manifest.json",
    "data_quality_summary.json",
    "README.md",
    "checksums.txt",
)

REQUIRED_REPORTS = {
    "output": "citation_reference_graph_output_latest.json",
    "inspection": "citation_reference_graph_inspection_latest.json",
    "release_candidate": "citation_reference_graph_release_candidate_latest.json",
    "package": "citation_reference_graph_package_latest.json",
    "line_checkpoint": "citation_reference_graph_line_checkpoint_latest.json",
    "manual_review": "citation_reference_graph_manual_review_latest.json",
    "analytics": "citation_reference_graph_analytics_latest.json",
}

EXPECTED_COUNTS = {
    "nodes_count": 529295,
    "edges_count": 745516,
    "paper_nodes_count": 60954,
    "external_reference_nodes_count": 468336,
    "source_family_nodes_count": 5,
    "paper_references_paper_edges_count": 6165,
    "paper_references_external_edges_count": 703234,
    "paper_has_reference_source_family_edges_count": 36117,
    "resolved_reference_edges_count": 6165,
    "unresolved_reference_edges_count": 703234,
    "reference_resolution_ratio": 0.00869,
}

COUNT_ALIASES = {
    "nodes_count": ("nodes_count",),
    "edges_count": ("edges_count",),
    "paper_nodes_count": (
        "paper_nodes_count",
        "node_paper_count",
        "paper_nodes",
    ),
    "external_reference_nodes_count": (
        "external_reference_nodes_count",
        "node_external_reference_count",
        "external_reference_nodes",
    ),
    "source_family_nodes_count": (
        "source_family_nodes_count",
        "node_source_family_count",
        "source_family_nodes",
    ),
    "paper_references_paper_edges_count": (
        "paper_references_paper_edges_count",
        "edge_paper_references_paper_count",
        "paper_references_paper",
    ),
    "paper_references_external_edges_count": (
        "paper_references_external_edges_count",
        "edge_paper_references_external_count",
        "paper_references_external",
    ),
    "paper_has_reference_source_family_edges_count": (
        "paper_has_reference_source_family_edges_count",
        "edge_paper_has_reference_source_family_count",
        "paper_has_reference_source_family",
    ),
    "resolved_reference_edges_count": (
        "resolved_reference_edges_count",
        "resolved_reference_edges",
    ),
    "unresolved_reference_edges_count": (
        "unresolved_reference_edges_count",
        "unresolved_reference_edges",
    ),
    "reference_resolution_ratio": ("reference_resolution_ratio",),
}

MUST_BE_FALSE_SAFETY_FLAGS = (
    "mutate_canonical_documents",
    "mutate_retrieval_artifacts",
    "mutate_qdrant",
    "mutate_postgres",
    "mutate_db_schema",
    "mutate_api",
    "mutate_ui",
    "mutate_ranking",
    "publish_dataset",
    "publish_graph",
    "may_be_used_as_reconcile_input",
    "create_latest_pointer",
    "require_networkx_runtime",
    "require_neo4j_runtime",
    "require_graphrag_runtime",
)


def _path_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")

    return payload


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _iter_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _first_value(payloads: list[dict[str, Any]], aliases: tuple[str, ...]) -> Any:
    for payload in payloads:
        for obj in _iter_dicts(payload):
            for alias in aliases:
                if alias in obj:
                    return obj[alias]
    return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False

    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_count_values(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {}

    for canonical_name, aliases in COUNT_ALIASES.items():
        raw = _first_value(payloads, aliases)
        if canonical_name == "reference_resolution_ratio":
            value = _as_float(raw)
            if value is not None:
                counts[canonical_name] = value
        else:
            value = _as_int(raw)
            if value is not None:
                counts[canonical_name] = value

    return counts


def _count_mismatches(counts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mismatches: dict[str, dict[str, Any]] = {}

    for name, expected in EXPECTED_COUNTS.items():
        actual = counts.get(name)

        if actual is None:
            mismatches[name] = {
                "expected": expected,
                "actual": None,
                "reason": "missing",
            }
            continue

        if isinstance(expected, float):
            matches = abs(float(actual) - expected) <= 1e-6
        else:
            matches = int(actual) == int(expected)

        if not matches:
            mismatches[name] = {
                "expected": expected,
                "actual": actual,
                "reason": "mismatch",
            }

    return mismatches


def _report_ok(payload: dict[str, Any]) -> bool:
    ok_value = _first_value([payload], ("ok",))
    required_failed = _first_value([payload], ("required_failed_count",))

    ok = _as_bool(ok_value)
    failed_count = _as_int(required_failed)

    if ok is not None:
        return ok and (failed_count in (None, 0))

    if failed_count is not None:
        return failed_count == 0

    return False


def _report_required_failed_count(payload: dict[str, Any]) -> int | None:
    return _as_int(_first_value([payload], ("required_failed_count",)))


def _graph_identity(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    graph_name = _as_str(
        _first_value(
            payloads,
            ("graph_name", "name"),
        )
    )
    graph_version = _as_str(
        _first_value(
            payloads,
            ("graph_version", "version"),
        )
    )

    return {
        "name": graph_name,
        "version": graph_version,
    }


def _manual_review_state(payloads: list[dict[str, Any]]) -> dict[str, bool]:
    manual_review_required = _as_bool(
        _first_value(payloads, ("manual_review_required",))
    )
    manual_review_complete = _as_bool(
        _first_value(payloads, ("manual_review_complete",))
    )
    publication_ready = _as_bool(
        _first_value(payloads, ("publication_ready",))
    )

    return {
        "manual_review_required": (
            True if manual_review_required is None else manual_review_required
        ),
        "manual_review_complete": (
            False if manual_review_complete is None else manual_review_complete
        ),
        "publication_ready": (
            False if publication_ready is None else publication_ready
        ),
    }


def _unsafe_flags(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    unsafe: dict[str, Any] = {}

    for flag in MUST_BE_FALSE_SAFETY_FLAGS:
        raw = _first_value(payloads, (flag,))
        value = _as_bool(raw)
        if value is True:
            unsafe[flag] = True

    return unsafe


def _disabled_status(settings: ApiSettings) -> CitationGraphStatusResponse:
    return CitationGraphStatusResponse(
        graph=CitationGraphStatusGraph(
            name=GRAPH_NAME,
            version=settings.citation_graph_version,
            runtime_enabled=False,
            available=False,
            exposure_mode=settings.citation_graph_exposure_mode,
            graph_root=str(settings.citation_graph_root),
            reports_root=str(settings.citation_graph_reports_root),
        ),
        query={
            "endpoint": STATUS_ENDPOINT,
        },
        items=[],
        page={
            "limit": 0,
            "offset": 0,
            "returned": 0,
            "total_estimate": None,
        },
        caveats=list(DEFAULT_CITATION_GRAPH_CAVEATS),
        availability={
            "configured": False,
            "available": False,
            "runtime_enabled": False,
            "safe_to_serve_locally": False,
            "status_probe_implemented": True,
            "runtime_loader_implemented": False,
            "traversal_endpoints_implemented": False,
        },
        artifacts={
            "graph_root": _path_status(settings.citation_graph_root),
            "reports_root": _path_status(settings.citation_graph_reports_root),
        },
        reports={},
        compatibility={
            "ok": False,
            "checked": False,
            "reason": "graph_runtime_not_enabled",
        },
        counts=dict(EXPECTED_COUNTS),
        error_code="graph_runtime_not_enabled",
        message="Citation/reference graph API is disabled by default.",
    )


def build_citation_graph_status(
    *,
    settings: ApiSettings,
) -> CitationGraphStatusResponse:
    """Return read-only diagnostic status for the citation/reference graph API.

    The status endpoint is the only graph API endpoint implemented at this
    stage. When enabled, this function checks local graph artifacts and reports
    for structural compatibility, but it does not load graph nodes/edges into a
    traversal runtime and does not implement graph query endpoints.
    """

    runtime_enabled = bool(settings.citation_graph_api_enabled)

    if not runtime_enabled:
        return _disabled_status(settings)

    graph_root = settings.citation_graph_root
    reports_root = settings.citation_graph_reports_root

    required_file_status = {
        file_name: _path_status(graph_root / file_name)
        for file_name in REQUIRED_GRAPH_FILES
    }
    missing_graph_files = [
        file_name
        for file_name, status in required_file_status.items()
        if not status["is_file"]
    ]

    report_file_status = {
        report_name: _path_status(reports_root / file_name)
        for report_name, file_name in REQUIRED_REPORTS.items()
    }
    missing_reports = [
        report_name
        for report_name, status in report_file_status.items()
        if not status["is_file"]
    ]

    artifacts_status = {
        "graph_root": _path_status(graph_root),
        "reports_root": _path_status(reports_root),
        "required_graph_files": required_file_status,
        "missing_graph_files": missing_graph_files,
        "missing_reports": missing_reports,
    }

    reports_status: dict[str, Any] = {
        report_name: {
            **status,
            "file_name": REQUIRED_REPORTS[report_name],
        }
        for report_name, status in report_file_status.items()
    }

    payloads: list[dict[str, Any]] = []
    report_payloads: dict[str, dict[str, Any]] = {}
    error_code: str | None = None
    message: str | None = None

    if missing_graph_files or missing_reports:
        error_code = "graph_artifacts_not_found"
        message = "Citation/reference graph artifacts or validation reports are missing."
    else:
        try:
            manifest_payload = _read_json(graph_root / "manifest.json")
            data_quality_payload = _read_json(graph_root / "data_quality_summary.json")
            schema_payload = _read_json(graph_root / "schema.json")
            payloads.extend([manifest_payload, data_quality_payload, schema_payload])

            for report_name, file_name in REQUIRED_REPORTS.items():
                report_payload = _read_json(reports_root / file_name)
                report_payloads[report_name] = report_payload
                payloads.append(report_payload)
                reports_status[report_name].update(
                    {
                        "readable": True,
                        "ok": _report_ok(report_payload),
                        "required_failed_count": _report_required_failed_count(report_payload),
                    }
                )

        except (OSError, ValueError, json.JSONDecodeError) as exc:
            error_code = "graph_artifacts_invalid"
            message = f"Citation/reference graph artifacts are not readable: {exc}"

    identity = _graph_identity(payloads)
    manual_review = _manual_review_state(payloads)
    counts = _extract_count_values(payloads)
    if not counts:
        counts = dict(EXPECTED_COUNTS)

    count_mismatches = _count_mismatches(counts)
    unsafe = _unsafe_flags(payloads)

    report_failures = [
        report_name
        for report_name, status in reports_status.items()
        if status.get("exists") and status.get("ok") is False
    ]

    if error_code is None:
        detected_version = identity.get("version")
        if detected_version and detected_version != settings.citation_graph_version:
            error_code = "graph_version_unsupported"
            message = (
                "Citation/reference graph version is not supported by this API status probe: "
                f"{detected_version!r} != {settings.citation_graph_version!r}"
            )
        elif unsafe:
            error_code = "graph_artifacts_unsafe"
            message = "Citation/reference graph manifest/report safety flags are not safe for API inspection."
        elif count_mismatches:
            error_code = "graph_artifacts_incompatible"
            message = "Citation/reference graph counters do not match the accepted v0.1 baseline."
        elif report_failures:
            error_code = "graph_artifacts_incompatible"
            message = "Citation/reference graph validation reports are not green."
        else:
            message = "Citation/reference graph status probe is compatible for local inspection."

    available = error_code is None

    compatibility = {
        "checked": True,
        "ok": available,
        "error_code": error_code,
        "graph_name": identity.get("name") or GRAPH_NAME,
        "graph_version": identity.get("version") or settings.citation_graph_version,
        "expected_graph_version": settings.citation_graph_version,
        "missing_graph_files": missing_graph_files,
        "missing_reports": missing_reports,
        "report_failures": report_failures,
        "unsafe_flags": unsafe,
        "count_mismatches": count_mismatches,
        "manual_review_required": manual_review["manual_review_required"],
        "manual_review_complete": manual_review["manual_review_complete"],
        "publication_ready": manual_review["publication_ready"],
    }

    caveats = list(DEFAULT_CITATION_GRAPH_CAVEATS)
    if not manual_review["manual_review_complete"]:
        caveats.append("manual_review_incomplete")
    if not manual_review["publication_ready"]:
        caveats.append("publication_not_ready")
    if available:
        caveats.append("status_probe_only_no_traversal_runtime")

    return CitationGraphStatusResponse(
        graph=CitationGraphStatusGraph(
            name=identity.get("name") or GRAPH_NAME,
            version=identity.get("version") or settings.citation_graph_version,
            runtime_enabled=True,
            available=available,
            exposure_mode=settings.citation_graph_exposure_mode,
            graph_root=str(graph_root),
            reports_root=str(reports_root),
            manual_review_required=manual_review["manual_review_required"],
            manual_review_complete=manual_review["manual_review_complete"],
            publication_ready=manual_review["publication_ready"],
        ),
        query={
            "endpoint": STATUS_ENDPOINT,
        },
        items=[],
        page={
            "limit": 0,
            "offset": 0,
            "returned": 0,
            "total_estimate": None,
        },
        caveats=caveats,
        availability={
            "configured": True,
            "available": available,
            "runtime_enabled": True,
            "safe_to_serve_locally": available,
            "status_probe_implemented": True,
            "runtime_loader_implemented": False,
            "traversal_endpoints_implemented": False,
        },
        artifacts=artifacts_status,
        reports=reports_status,
        compatibility=compatibility,
        counts=counts,
        error_code=error_code,
        message=message,
    )
