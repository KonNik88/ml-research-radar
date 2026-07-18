from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_DOC_PATH = Path("docs/citation_reference_graph_api_response_fixtures_v0.1.md")

REQUIRED_MARKERS = (
    "status = design-only fixture contract",
    "depends_on = Citation / Reference Graph API Design v0.1",
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
    "manual_review_complete = false",
    "publication_ready = false",
    "metadata_reference_fields_only = true",
    "full_text_parsed = false",
    "pdfs_parsed = false",
    "bibliography_sections_parsed = false",
    "not_a_complete_citation_index = true",
    "GET /citation-graph/status = implemented",
    "GET /citation-graph/papers/{canonical_id}/references = implemented",
    "GET /citation-graph/papers/{canonical_id}/citations = implemented",
    "GET /citation-graph/external-references/{reference_id}/papers = implemented",
    "GET /citation-graph/source-families = implemented",
    "GET /citation-graph/top-referenced-papers = implemented",
    "GET /citation-graph/top-external-references = implemented",
    "narrow read-only traversal endpoint count = 6",
    '"status_probe_implemented": true',
    '"file_backed_store_loader_implemented": true',
    '"runtime_loader_implemented": false',
    '"traversal_endpoints_implemented": true',
    '"implemented_traversal_endpoint_count": 6',
    '"full_graph_runtime_subsystem_implemented": false',
    "graph_runtime_not_enabled",
    "graph_artifacts_not_found",
    "graph_artifacts_unsafe",
    "graph_version_unsupported",
    "canonical_id_not_found",
    "external_reference_not_found",
    "Graph Runtime Stale-Version Compatibility Design v0.1",
    "Graph API Implementation Plan v0.1",
    "It does not approve broad traversal/runtime promotion,",
)

FORBIDDEN_MARKERS = (
    "status = promoted-runtime",
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

REQUIRED_TOP_LEVEL_SUCCESS_KEYS = ("graph", "query", "items", "page", "caveats")
REQUIRED_GRAPH_FLAGS = {
    "metadata_reference_fields_only": True,
    "full_text_parsed": False,
    "pdfs_parsed": False,
    "bibliography_sections_parsed": False,
    "manual_review_required": True,
    "manual_review_complete": False,
    "publication_ready": False,
    "may_be_used_as_reconcile_input": False,
    "not_a_complete_citation_index": True,
}


def _json_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in re.finditer(r"```json\n(.*?)\n```", text, flags=re.DOTALL):
        blocks.append(json.loads(match.group(1)))
    return blocks


def _is_success_fixture(block: dict[str, Any]) -> bool:
    return all(key in block for key in REQUIRED_TOP_LEVEL_SUCCESS_KEYS)


def validate_response_fixture_doc(path: Path = DEFAULT_DOC_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "summary": {
                "ok": False,
                "required_failed_count": 1,
                "warning_count": 0,
            },
            "verdict": {
                "required_failed_checks": ["response_fixture_doc_exists"],
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

    for section in (
        "## Shared response rules",
        "## Status fixture",
        "## Outgoing references fixture",
        "## Incoming citations fixture",
        "## Error fixture contract",
        "## Required implementation regression tests",
        "## Implementation gates",
    ):
        if section not in text:
            failed_checks.append(f"section_present:{section}")

    try:
        blocks = _json_blocks(text)
    except json.JSONDecodeError as exc:
        failed_checks.append(f"json_fixtures_parse:{exc.msg}")
        blocks = []

    success_blocks = [block for block in blocks if _is_success_fixture(block)]
    if len(success_blocks) < 7:
        failed_checks.append("success_fixture_count_at_least_7")

    error_blocks = [block for block in blocks if "error_code" in block]
    if not error_blocks:
        failed_checks.append("error_fixture_present")

    for index, block in enumerate(success_blocks):
        graph = block.get("graph", {})
        if not isinstance(graph, dict):
            failed_checks.append(f"success_fixture_{index}_graph_is_object")
            continue
        for flag, expected in REQUIRED_GRAPH_FLAGS.items():
            if graph.get(flag) is not expected:
                failed_checks.append(f"success_fixture_{index}_graph_flag:{flag}")

        page = block.get("page", {})
        if not isinstance(page, dict):
            failed_checks.append(f"success_fixture_{index}_page_is_object")
        else:
            for key in ("limit", "offset", "returned", "total_estimate"):
                if key not in page:
                    failed_checks.append(f"success_fixture_{index}_page_key:{key}")

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
        "json_fixture_count": len(blocks),
        "success_fixture_count": len(success_blocks),
        "error_fixture_count": len(error_blocks),
        "required_marker_count": len(REQUIRED_MARKERS),
        "forbidden_marker_count": len(FORBIDDEN_MARKERS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Citation / Reference Graph API Response Fixtures v0.1."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_DOC_PATH,
        help=f"Response fixture document path. Default: {DEFAULT_DOC_PATH}",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when required checks fail.",
    )
    args = parser.parse_args(argv)

    report = validate_response_fixture_doc(path=args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if args.strict and not report["summary"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

