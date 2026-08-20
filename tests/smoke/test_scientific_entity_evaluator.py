from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts.entities.evaluate_scientific_entity_evidence import (
    REQUIRED_FILES,
    ScientificEntityEvaluationBuildError,
    evaluate_evidence,
    main as evaluate_main,
)
from scripts.validation.check_scientific_entity_evaluation import validate_evaluation


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "scientific_entity_evaluation_v0_1"
FIXED_TIME = datetime(2026, 8, 21, 11, 0, 0, tzinfo=timezone.utc)
EVALUATION_ID = "scientific-entity-evaluation-fixture-v0.1"


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _execute(
    tmp_path: Path,
    *,
    output_name: str = "output",
    evaluation_id: str = EVALUATION_ID,
) -> tuple[dict[str, Any], Path]:
    output_root = tmp_path / output_name
    report = evaluate_evidence(
        output_root=output_root,
        evaluation_id=evaluation_id,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    return report, output_root / evaluation_id


def test_plan_mode_computes_metrics_without_writing(tmp_path: Path) -> None:
    output_root = tmp_path / "plan"

    report = evaluate_evidence(
        output_root=output_root,
        evaluation_id=EVALUATION_ID,
        execute=False,
        generated_at_utc=FIXED_TIME,
    )

    assert report["ok"] is True
    assert report["mode"] == "plan"
    assert report["phase_complete"] is False
    assert report["input_document_count"] == 4
    assert report["reference_mention_count"] == 18
    assert report["prediction_mention_count"] == 17
    assert report["exact_match_count"] == 14
    assert report["relaxed_only_match_count"] == 1
    assert report["error_count"] == 5
    assert report["written_files"] == []
    assert not output_root.exists()


def test_fixture_metrics_match_tracked_expected_metrics(tmp_path: Path) -> None:
    _, evaluation_dir = _execute(tmp_path)

    assert _json(evaluation_dir / "metrics.json") == _json(
        FIXTURE_DIR / "expected_metrics.json"
    )


def test_exact_and_relaxed_micro_metrics_are_known() -> None:
    report = evaluate_evidence(
        evaluation_id=EVALUATION_ID,
        execute=False,
        generated_at_utc=FIXED_TIME,
    )

    assert report["exact_micro"] == {
        "true_positive": 14,
        "false_positive": 3,
        "false_negative": 4,
        "reference_support": 18,
        "prediction_support": 17,
        "precision_denominator": 17,
        "recall_denominator": 18,
        "precision": 0.823529,
        "recall": 0.777778,
        "f1": 0.8,
    }
    assert report["relaxed_micro"]["true_positive"] == 15
    assert report["relaxed_micro"]["precision"] == 0.882353
    assert report["relaxed_micro"]["recall"] == 0.833333
    assert report["relaxed_micro"]["f1"] == 0.857143


def test_execute_creates_exact_immutable_layout(tmp_path: Path) -> None:
    report, evaluation_dir = _execute(tmp_path)

    assert report["mode"] == "execute"
    assert report["phase_complete"] is True
    assert set(report["written_files"]) == set(REQUIRED_FILES)
    assert {path.name for path in evaluation_dir.iterdir()} == set(REQUIRED_FILES)


def test_generated_evaluation_passes_independent_validator(tmp_path: Path) -> None:
    _, evaluation_dir = _execute(tmp_path)

    validation = validate_evaluation(
        evaluation_dir=evaluation_dir,
        write_reports=False,
    )

    assert validation["summary"]["ok"] is True
    assert validation["summary"]["required_failed_count"] == 0
    assert validation["summary"]["exact_match_count"] == 14
    assert validation["verdict"]["next_slice"] == (
        "bounded_scientific_entity_manual_review_evidence_v0.1"
    )


def test_fixture_contains_each_automatic_error_kind(tmp_path: Path) -> None:
    _, evaluation_dir = _execute(tmp_path)
    errors = _jsonl(evaluation_dir / "errors.jsonl")

    assert {row["error_kind"] for row in errors} == {
        "boundary_mismatch",
        "type_mismatch",
        "false_positive",
        "false_negative",
    }
    counts = _json(evaluation_dir / "metrics.json")["error_count_by_kind"]
    assert counts == {
        "boundary_mismatch": 1,
        "type_mismatch": 1,
        "false_positive": 1,
        "false_negative": 2,
    }


def test_matches_are_one_to_one_and_include_one_relaxed_pair(tmp_path: Path) -> None:
    _, evaluation_dir = _execute(tmp_path)
    rows = _jsonl(evaluation_dir / "matches.jsonl")

    assert len(rows) == 15
    assert len({row["reference_id"] for row in rows}) == len(rows)
    assert len({row["prediction_evidence_id"] for row in rows}) == len(rows)
    assert sum(row["match_kind"] == "relaxed" for row in rows) == 1
    relaxed = next(row for row in rows if row["match_kind"] == "relaxed")
    assert relaxed["char_iou"] == pytest.approx(14 / 23)


def test_per_type_metrics_cover_all_types_and_do_not_claim_sufficiency(
    tmp_path: Path,
) -> None:
    _, evaluation_dir = _execute(tmp_path)
    payload = _json(evaluation_dir / "per_type_metrics.json")

    assert [row["entity_type"] for row in payload["rows"]] == [
        "task",
        "method",
        "dataset",
        "metric",
        "model",
        "domain",
    ]
    assert all(row["support_sufficient"] is False for row in payload["rows"])
    assert (
        _json(evaluation_dir / "metrics.json")["data_sufficiency"][
            "promotion_sample_sufficient"
        ]
        is False
    )


def test_repeated_fixed_evaluations_are_byte_deterministic(tmp_path: Path) -> None:
    _, first = _execute(tmp_path, output_name="first")
    _, second = _execute(tmp_path, output_name="second")

    assert {name: (first / name).read_bytes() for name in REQUIRED_FILES} == {
        name: (second / name).read_bytes() for name in REQUIRED_FILES
    }


def test_existing_evaluation_directory_is_not_overwritten(tmp_path: Path) -> None:
    _, evaluation_dir = _execute(tmp_path)
    manifest_before = (evaluation_dir / "manifest.json").read_bytes()

    with pytest.raises(FileExistsError, match="overwrite is forbidden"):
        _execute(tmp_path)

    assert (evaluation_dir / "manifest.json").read_bytes() == manifest_before


def test_all_generated_files_are_utf8_lf(tmp_path: Path) -> None:
    _, evaluation_dir = _execute(tmp_path)

    for filename in REQUIRED_FILES:
        raw = (evaluation_dir / filename).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in raw
        assert raw.endswith(b"\n")
        raw.decode("utf-8")


def test_fixture_status_is_reserved_for_tracked_fixture(tmp_path: Path) -> None:
    copied_documents = tmp_path / "canonical_documents.jsonl"
    copied_documents.write_bytes((FIXTURE_DIR / "canonical_documents.jsonl").read_bytes())

    with pytest.raises(ScientificEntityEvaluationBuildError, match="reserved"):
        evaluate_evidence(
            documents_path=copied_documents,
            output_root=tmp_path / "output",
            status="fixture",
            execute=False,
        )


def test_candidate_status_requires_reviewed_candidate_inputs(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityEvaluationBuildError, match="reviewed_candidate"):
        evaluate_evidence(
            output_root=tmp_path / "output",
            status="candidate",
            execute=False,
        )


def test_current_canonical_path_is_forbidden_before_read(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityEvaluationBuildError, match="canonical corpus"):
        evaluate_evidence(
            documents_path=(
                ROOT
                / "data"
                / "analytics"
                / "reconciled"
                / "canonical_documents.jsonl"
            ),
            output_root=tmp_path / "output",
            status="candidate",
            execute=False,
        )


def test_document_limit_above_hard_cap_fails(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityEvaluationBuildError, match="hard limit"):
        evaluate_evidence(
            output_root=tmp_path / "output",
            max_documents=101,
            execute=False,
        )


def test_reference_hash_tampering_fails_before_evaluation(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference_mentions.jsonl"
    rows = _jsonl(FIXTURE_DIR / "reference_mentions.jsonl")
    rows[0]["uncertain"] = True
    reference_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ScientificEntityEvaluationBuildError, match="SHA-256"):
        evaluate_evidence(
            reference_mentions_path=reference_path,
            output_root=tmp_path / "output",
            status="candidate",
            execute=False,
        )


def test_cli_defaults_to_non_mutating_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "cli-plan"

    exit_code = evaluate_main(
        [
            "--output-root",
            str(output_root),
            "--evaluation-id",
            EVALUATION_ID,
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "[OK] mode=plan" in output
    assert "[OK] phase_complete=False" in output
    assert not output_root.exists()
