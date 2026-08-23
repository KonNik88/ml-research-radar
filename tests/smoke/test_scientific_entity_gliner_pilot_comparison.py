from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = "docs/scientific_entity_gliner_pilot_comparison_v0.1.md"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_comparison_pins_immutable_evidence_chain() -> None:
    report = _read(REPORT_PATH)

    assert "base_git_commit = d2f92c1" in report
    assert (
        "review_id = scientific-entity-manual-review-v0.1-20260821T131320262656Z"
        in report
    )
    assert (
        "gliner_build_id = "
        "scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z"
        in report
    )
    assert (
        "gliner_evaluation_id = "
        "scientific-entity-evaluation-v0.1-20260823T124036780234Z"
        in report
    )
    assert "gliner_build_validator = 91 / 91 required checks" in report
    assert "gliner_evaluation_validator = 69 / 69 required checks" in report
    assert "required_failed_count = 0" in report


def test_comparison_pins_micro_and_control_metrics() -> None:
    report = _read(REPORT_PATH)

    assert (
        "| Literal v0.1 | Exact | 10 | 20 | 425 | 0.333333 | 0.022989 | "
        "0.043012 |"
    ) in report
    assert (
        "| GLiNER v0.1 | Exact | 176 | 370 | 259 | 0.322344 | 0.404598 | "
        "0.358817 |"
    ) in report
    assert (
        "| Literal v0.1 | Relaxed | 16 | 14 | 419 | 0.533333 | 0.036782 | "
        "0.068818 |"
    ) in report
    assert (
        "| GLiNER v0.1 | Relaxed | 195 | 351 | 240 | 0.357143 | 0.448276 | "
        "0.397554 |"
    ) in report
    assert "exact F1 ratio = 8.34x literal" in report
    assert "relaxed F1 ratio = 5.78x literal" in report


def test_comparison_pins_source_type_and_error_diagnostics() -> None:
    report = _read(REPORT_PATH)

    assert "| Title | Relaxed | 58 | 44 | 0.590909 | 0.448276 | 0.509804 |" in report
    assert (
        "| Abstract | Relaxed | 377 | 502 | 0.336653 | 0.448276 | 0.384528 |"
        in report
    )
    assert "| model | 0.429688 | 0.509259 | 0.466102 | 0.460938 | 0.546296 | 0.500000 |" in report
    assert "| domain | 0.108108 | 0.121212 | 0.114286 | 0.108108 | 0.121212 | 0.114286 |" in report
    assert "| boundary_mismatch | 22 |" in report
    assert "| type_mismatch | 113 |" in report
    assert "| false_positive | 235 |" in report
    assert "| false_negative | 124 |" in report
    assert "85 of 113 type mismatches (`75.2%`)" in report


def test_comparison_pins_uncalibrated_score_evidence() -> None:
    report = _read(REPORT_PATH)

    assert "| exact | 176 | 0.505371 | 0.827148 | 0.806810 | 0.989258 |" in report
    assert (
        "| type_mismatch | 113 | 0.501465 | 0.784180 | 0.777979 | 0.996582 |"
        in report
    )
    assert (
        "| false_positive | 235 | 0.500488 | 0.676270 | 0.687060 | 0.988281 |"
        in report
    )
    assert "an uncalibrated model score, not a" in report


def test_comparison_preserves_dev_holdout_and_scale_boundaries() -> None:
    report = _read(REPORT_PATH)

    assert "document_count_sufficient = false" in report
    assert "promotion_sample_sufficient = false" in report
    assert "metrics_are_descriptive_only = true" in report
    assert "GLiNER candidate v0.1 = retain as leading bounded candidate" in report
    assert "GLiNER candidate v0.1 production promotion = rejected" in report
    assert "same 24 papers described as held-out after tuning = forbidden" in report
    assert "second-stage classifier = deferred" in report
    assert "full-corpus extraction = forbidden" in report
    assert "32-paper disjoint" in report
    assert "not final production evidence" in report


def test_living_docs_advance_to_bounded_dev_calibration() -> None:
    readme = _read("README.md")
    architecture = _read("docs/architecture.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")

    link = "docs/scientific_entity_gliner_pilot_comparison_v0.1.md"
    assert link in readme
    assert link in checkpoint
    assert link in roadmap
    assert "Scientific Entity GLiNER Pilot Comparison v0.1" in architecture
    assert "next entity slice = Bounded Scientific Entity GLiNER Dev Calibration v0.1" in checkpoint
    assert (
        "next authorized slice = Bounded Scientific Entity GLiNER Dev Calibration "
        "v0.1"
    ) in roadmap
    assert "production extractor selected = false" in architecture
    assert "full-corpus build authorized = false" in architecture
