from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = "docs/scientific_entity_literal_baseline_pilot_evaluation_v0.1.md"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_pilot_report_pins_build_and_review_provenance() -> None:
    report = _read(REPORT_PATH)

    assert "base_git_commit = 7c48111" in report
    assert (
        "evaluation_id = scientific-entity-evaluation-v0.1-20260822T114935748579Z"
        in report
    )
    assert (
        "review_id = scientific-entity-manual-review-v0.1-20260821T131320262656Z"
        in report
    )
    assert (
        "build_id = scientific-entity-literal-v0.1-20260822T114316573133Z"
        in report
    )
    assert "strict_validator_checks = 69 / 69" in report
    assert "required_failed_count = 0" in report


def test_pilot_report_pins_input_and_output_counts() -> None:
    report = _read(REPORT_PATH)

    assert "document_count = 24" in report
    assert "annotation_rows = 48" in report
    assert "reference_mention_count = 435" in report
    assert "prediction_mention_count = 30" in report
    assert "exact_match_count = 10" in report
    assert "relaxed_only_match_count = 6" in report
    assert "total_relaxed_match_count = 16" in report


def test_pilot_report_pins_descriptive_metrics_and_errors() -> None:
    report = _read(REPORT_PATH)

    assert "| Exact | 10 | 20 | 425 | 0.333333 | 0.022989 | 0.043012 |" in report
    assert "| Relaxed | 16 | 14 | 419 | 0.533333 | 0.036782 | 0.068818 |" in report
    assert "| boundary_mismatch | 17 |" in report
    assert "| type_mismatch | 2 |" in report
    assert "| false_positive | 1 |" in report
    assert "| false_negative | 406 |" in report
    assert "document_count_sufficient = false" in report
    assert "metrics_are_descriptive_only = true" in report
    assert "annotation_assistance = AI-assisted human adjudication" in report


def test_pilot_report_preserves_truth_and_promotion_boundaries() -> None:
    report = _read(REPORT_PATH)

    assert "canonical_truth_mutated = false" in report
    assert "production_extractor_selected = false" in report
    assert "full_corpus_build_authorized = false" in report
    assert "publication_ready = false" in report
    assert "literal baseline v0.1 = retain unchanged as deterministic control" in report
    assert "current 24-paper review = pilot/dev evidence" in report
    assert "duplicate evaluation harness = rejected" in report
    assert "commit raw paper text = forbidden" in report


def test_living_docs_preserve_literal_control_after_gliner_comparison() -> None:
    readme = _read("README.md")
    architecture = _read("docs/architecture.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")

    report_link = "docs/scientific_entity_literal_baseline_pilot_evaluation_v0.1.md"
    assert report_link in readme
    assert report_link in architecture
    assert "scientific entity real review complete = true" in checkpoint
    assert "scientific_entity_real_review_complete = true_bounded_local_pilot" in architecture
    # Do not pin the mutable living ``next`` pointer in a historical regression.
    # Current-state sequencing is covered centrally by test_project_state_current_v02.py.
    assert "Bounded Scientific Entity GLiNER Dev Calibration Tooling v0.1" in roadmap
    assert "Scientific Entity GLiNER Pilot Comparison v0.1" in roadmap
    assert "no duplicate evaluation harness" in roadmap
    assert "no production extractor selection" in roadmap
    assert "no full-corpus entity build" in roadmap
