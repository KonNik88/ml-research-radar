from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DOC_PATH = Path("docs/citation_reference_graph_api_design_v0.1.md")

REQUIRED_MARKERS = (
    "status = design-only",
    "implements_public_api = false",
    "creates_runtime_graph = false",
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
    "publication_ready = false",
    "metadata_reference_fields_only = true",
    "full_text_parsed = false",
    "pdfs_parsed = false",
    "bibliography_sections_parsed = false",
    "not_a_complete_citation_index = true",
    "GET /citation-graph/status",
    "GET /citation-graph/papers/{canonical_id}/references",
    "GET /citation-graph/papers/{canonical_id}/citations",
    "GET /citation-graph/external-references/{reference_id}/papers",
    "graph_runtime_not_enabled",
    "graph_artifacts_unsafe",
    "manual_review_complete = true",
    "publication_ready = true",
    "Endpoint implementation should start only after design review",
)

FORBIDDEN_MARKERS = (
    "status = implemented",
    "implements_public_api = true",
    "creates_runtime_graph = true",
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


def validate_design_doc(path: Path = DEFAULT_DOC_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "summary": {
                "ok": False,
                "required_failed_count": 1,
                "warning_count": 0,
            },
            "verdict": {
                "required_failed_checks": ["design_doc_exists"],
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

    if "## Non-goals" not in text:
        failed_checks.append("section_present:Non-goals")
    if "## Required implementation gates" not in text:
        failed_checks.append("section_present:Required implementation gates")
    if "## Open design questions" not in text:
        failed_checks.append("section_present:Open design questions")

    if "/citation-graph/" not in text:
        warnings.append("no citation-graph endpoint candidates found")

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
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Citation / Reference Graph API Design v0.1 safety markers."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_DOC_PATH,
        help=f"Design document path. Default: {DEFAULT_DOC_PATH}",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when required checks fail.",
    )
    args = parser.parse_args(argv)

    report = validate_design_doc(path=args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if args.strict and not report["summary"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

