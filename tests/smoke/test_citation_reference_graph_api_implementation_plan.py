from __future__ import annotations

from pathlib import Path

from scripts.validation.check_citation_reference_graph_api_implementation_plan import (
    DEFAULT_DOC_PATH,
    REQUIRED_MARKERS,
    main,
    validate_implementation_plan_doc,
)


def test_citation_reference_graph_api_implementation_plan_doc_passes() -> None:
    report = validate_implementation_plan_doc(DEFAULT_DOC_PATH)

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0


def test_citation_reference_graph_api_implementation_plan_fails_when_marker_missing(
    tmp_path: Path,
) -> None:
    text = DEFAULT_DOC_PATH.read_text(encoding="utf-8")
    broken = text.replace(REQUIRED_MARKERS[0], "status = promoted-runtime")
    doc_path = tmp_path / "citation_reference_graph_api_implementation_plan_v0.1.md"
    doc_path.write_text(broken, encoding="utf-8")

    report = validate_implementation_plan_doc(doc_path)

    assert report["summary"]["ok"] is False
    assert f"required_marker_present:{REQUIRED_MARKERS[0]}" in report["verdict"]["required_failed_checks"]
    assert "forbidden_marker_absent:status = promoted-runtime" in report["verdict"]["required_failed_checks"]


def test_citation_reference_graph_api_implementation_plan_fails_when_first_slice_missing(
    tmp_path: Path,
) -> None:
    text = DEFAULT_DOC_PATH.read_text(encoding="utf-8")
    broken = text.replace("Citation Graph API Disabled Status Endpoint v0.1", "Full Graph API Implementation")
    doc_path = tmp_path / "citation_reference_graph_api_implementation_plan_v0.1.md"
    doc_path.write_text(broken, encoding="utf-8")

    report = validate_implementation_plan_doc(doc_path)

    assert report["summary"]["ok"] is False
    assert "first_code_slice_named" in report["verdict"]["required_failed_checks"]


def test_citation_reference_graph_api_implementation_plan_cli_strict_passes() -> None:
    assert main(["--strict", "--path", str(DEFAULT_DOC_PATH)]) == 0


def test_citation_reference_graph_api_implementation_plan_cli_strict_fails_on_missing_doc(
    tmp_path: Path,
) -> None:
    assert main(["--strict", "--path", str(tmp_path / "missing.md")]) == 1

