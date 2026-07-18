from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DOC_PATH = Path("docs/citation_reference_graph_api_implementation_plan_v0.1.md")

REQUIRED_MARKERS = (
    "status = implementation-plan-only",
    "depends_on = Citation / Reference Graph API Design v0.1",
    "depends_on = Citation / Reference Graph API Response Fixtures v0.1",
    "depends_on = Citation / Reference Graph Runtime Compatibility Design v0.1",
    "implements_public_api = false",
    "implements_endpoint_code = false",
    "creates_runtime_graph = false",
    "implements_runtime_loader = false",
    "materializes_graph_in_db = false",
    "implements_graphrag = false",
    "mutates_canonical_documents = false",
    "mutates_retrieval_artifacts = false",
    "mutates_qdrant = false",
    "mutates_postgres = false",
    "mutates_api = false",
    "mutates_ui = false",
    "mutates_ranking = false",
    "publishes_dataset = false",
    "may_be_used_as_reconcile_input = false",
    "manual_review_required = true",
    "manual_review_complete = false",
    "publication_ready = false",
    "ML_RADAR_CITATION_GRAPH_API_ENABLED=false",
    "ML_RADAR_CITATION_GRAPH_EXPOSURE_MODE=local_inspection",
    "GET /citation-graph/status = implemented",
    "GET /citation-graph/papers/{canonical_id}/references = implemented",
    "GET /citation-graph/papers/{canonical_id}/citations = implemented",
    "GET /citation-graph/external-references/{reference_id}/papers = implemented",
    "GET /citation-graph/source-families = implemented",
    "GET /citation-graph/top-referenced-papers = implemented",
    "GET /citation-graph/top-external-references = implemented",
    "narrow read-only traversal endpoint count = 6",
    "file-backed CitationGraphStore loader = implemented",
    "full graph runtime query service = not implemented",
    "graph_runtime_not_enabled",
    "graph_artifacts_not_found",
    "graph_artifacts_invalid",
    "graph_artifacts_unsafe",
    "graph_version_unsupported",
    "graph_manual_review_incomplete",
    "graph_canonical_baseline_mismatch",
    "graph_package_stale",
    "/health readiness does not require citation graph runtime",
    "/search behavior does not change",
    "Qdrant is not required for citation graph API",
    "set ML_RADAR_CITATION_GRAPH_API_ENABLED=false",
    "The next safe direction is review/regression/design hardening rather than adding",
)

FORBIDDEN_MARKERS = (
    "status = promoted-runtime",
    "implements_public_api = true",
    "implements_endpoint_code = true",
    "creates_runtime_graph = true",
    "implements_runtime_loader = true",
    "materializes_graph_in_db = true",
    "implements_graphrag = true",
    "mutates_canonical_documents = true",
    "mutates_retrieval_artifacts = true",
    "mutates_qdrant = true",
    "mutates_postgres = true",
    "mutates_api = true",
    "mutates_ui = true",
    "mutates_ranking = true",
    "publishes_dataset = true",
    "may_be_used_as_reconcile_input = true",
)

REQUIRED_SECTIONS = (
    "## Future configuration",
    "## Future module layout",
    "## Future runtime objects",
    "## Future endpoints",
    "## Response contract",
    "## Error contract",
    "## Compatibility behavior",
    "## Health and runtime semantics",
    "## No-mutation requirements",
    "## Test plan",
    "## Rollout plan",
    "## Rollback plan",
    "## Explicit non-goals",
)


def validate_implementation_plan_doc(path: Path = DEFAULT_DOC_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "summary": {
                "ok": False,
                "required_failed_count": 1,
                "warning_count": 0,
            },
            "verdict": {
                "required_failed_checks": ["implementation_plan_doc_exists"],
                "warnings": [],
            },
            "path": str(path),
        }

    text = path.read_text(encoding="utf-8")
    failed_checks: list[str] = []
    warnings: list[str] = []

    for marker in REQUIRED_MARKERS:
        if marker not in text:
            failed_checks.append(f"required_marker_present:{marker}")

    for marker in FORBIDDEN_MARKERS:
        if marker in text:
            failed_checks.append(f"forbidden_marker_absent:{marker}")

    for section in REQUIRED_SECTIONS:
        if section not in text:
            failed_checks.append(f"section_present:{section}")

    if "Citation Graph API Disabled Status Endpoint v0.1" not in text:
        failed_checks.append("first_code_slice_named")

    if "no additional endpoint code in this lifecycle-consistency slice" not in text:
        failed_checks.append("non_goal_no_additional_endpoint_code_present")

    return {
        "summary": {
            "ok": not failed_checks,
            "required_failed_count": len(failed_checks),
            "warning_count": len(warnings),
        },
        "verdict": {
            "required_failed_checks": failed_checks,
            "warnings": warnings,
        },
        "path": str(path),
        "required_marker_count": len(REQUIRED_MARKERS),
        "forbidden_marker_count": len(FORBIDDEN_MARKERS),
        "required_section_count": len(REQUIRED_SECTIONS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Citation / Reference Graph API Implementation Plan v0.1."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_DOC_PATH,
        help=f"Implementation plan document path. Default: {DEFAULT_DOC_PATH}",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when required checks fail.",
    )
    args = parser.parse_args(argv)

    report = validate_implementation_plan_doc(path=args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if args.strict and not report["summary"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

