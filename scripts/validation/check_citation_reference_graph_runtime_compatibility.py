from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DOC_PATH = Path("docs/citation_reference_graph_runtime_compatibility_v0.1.md")

REQUIRED_MARKERS = (
    "status = design-only compatibility contract",
    "depends_on = Citation / Reference Graph API Design v0.1",
    "depends_on = Citation / Reference Graph API Response Fixtures v0.1",
    "implements_public_api = false",
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
    "graph_version = v0.1",
    "canonical_doc_count = 60954",
    "retrieval_build_id = 20260504T164021Z",
    "nodes_count = 529295",
    "edges_count = 745516",
    "paper_nodes = 60954",
    "external_reference_nodes = 468336",
    "source_family_nodes = 5",
    "paper_references_paper_edges = 6165",
    "paper_references_external_edges = 703234",
    "paper_has_reference_source_family_edges = 36117",
    "reference_resolution_ratio = 0.00869",
    "metadata_reference_fields_only = true",
    "full_text_parsed = false",
    "pdfs_parsed = false",
    "bibliography_sections_parsed = false",
    "not_a_complete_citation_index = true",
    "graph_canonical_baseline_mismatch",
    "graph_package_stale",
    "graph_artifacts_not_found",
    "graph_artifacts_invalid",
    "graph_artifacts_unsafe",
    "graph_version_unsupported",
    "graph_manual_review_incomplete",
    "graph_exposure_mode = local_inspection",
    "graph_exposure_mode = public",
    "Future graph runtime readiness must not affect general API health by default.",
    "file-backed CitationGraphStore loader = implemented",
    "GET /citation-graph/papers/{canonical_id}/references = implemented",
    "GET /citation-graph/papers/{canonical_id}/citations = implemented",
    "GET /citation-graph/external-references/{reference_id}/papers = implemented",
    "GET /citation-graph/source-families = implemented",
    "GET /citation-graph/top-referenced-papers = implemented",
    "GET /citation-graph/top-external-references = implemented",
    "narrow read-only traversal endpoint count = 6",
    "full runtime graph query service = not implemented",
    "The compatibility design does not approve broad traversal/runtime promotion by",
)

FORBIDDEN_MARKERS = (
    "status = promoted-runtime",
    "implements_public_api = true",
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
    "## Compatibility target",
    "## Candidate runtime inputs",
    "## Required compatibility checks",
    "## Local-only vs public-exposure modes",
    "## Stale-version semantics",
    "## Error mapping",
    "## Runtime readiness semantics",
    "## No-mutation requirements",
    "## Regression test plan",
    "## Implementation gates",
)


def validate_runtime_compatibility_doc(path: Path = DEFAULT_DOC_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "summary": {
                "ok": False,
                "required_failed_count": 1,
                "warning_count": 0,
            },
            "verdict": {
                "required_failed_checks": ["runtime_compatibility_doc_exists"],
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

    if "fail closed" not in text:
        failed_checks.append("fail_closed_semantics_present")

    if "/health may remain ready" not in text:
        failed_checks.append("health_independent_semantics_present")

    if "write latest pointers" not in text:
        failed_checks.append("no_latest_pointer_mutation_present")

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
        description="Validate Citation / Reference Graph Runtime Compatibility Design v0.1."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_DOC_PATH,
        help=f"Runtime compatibility design document path. Default: {DEFAULT_DOC_PATH}",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when required checks fail.",
    )
    args = parser.parse_args(argv)

    report = validate_runtime_compatibility_doc(path=args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if args.strict and not report["summary"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

