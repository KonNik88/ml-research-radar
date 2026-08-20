from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from radar_core.contracts.scientific_entity_evidence import EntityEvidenceBuildStatus
from scripts.entities.build_scientific_entity_evidence_baseline import (
    ScientificEntityEvidenceBuildError,
    build_baseline,
    main as build_main,
)
from scripts.validation.check_scientific_entity_evidence_build import (
    REQUIRED_FILES,
    validate_build,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "scientific_entity_extractor_baseline_v0.1.yaml"
FIXTURE_DIR = (
    ROOT / "tests" / "fixtures" / "scientific_entity_extractor_baseline_v0_1"
)
FIXTURE_INPUT = FIXTURE_DIR / "canonical_documents.jsonl"
FIXED_TIME = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _execute(
    tmp_path: Path,
    *,
    build_id: str = "bounded-baseline-test-v0.1",
    config_path: Path = CONFIG_PATH,
    input_path: Path = FIXTURE_INPUT,
    status: str = "fixture",
    output_name: str = "output",
) -> tuple[dict[str, Any], Path]:
    output_root = tmp_path / output_name
    report = build_baseline(
        config_path=config_path,
        input_path=input_path,
        output_root=output_root,
        build_id=build_id,
        status=status,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    return report, output_root / build_id


def _write_config(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    *,
    filename: str = "baseline.yaml",
) -> Path:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    mutate(payload)
    path = tmp_path / filename
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_candidate_input(tmp_path: Path, title_suffix: str = "") -> Path:
    rows = _read_jsonl(FIXTURE_INPUT)
    rows[0]["title"] = f"{rows[0]['title']}{title_suffix}"
    path = tmp_path / "candidate_documents.jsonl"
    text = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    )
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _check_map(report: dict[str, Any]) -> dict[str, bool]:
    return {check["name"]: check["ok"] for check in report["checks"]}


def test_plan_mode_computes_build_without_writing(tmp_path: Path) -> None:
    output_root = tmp_path / "plan-output"

    report = build_baseline(
        output_root=output_root,
        build_id="plan-only-v0.1",
        execute=False,
        generated_at_utc=FIXED_TIME,
    )

    assert report["ok"] is True
    assert report["mode"] == "plan"
    assert report["phase_complete"] is False
    assert report["input_document_count"] == 4
    assert report["mention_count"] == 17
    assert report["written_files"] == []
    assert not output_root.exists()


def test_execute_creates_exact_immutable_layout(tmp_path: Path) -> None:
    report, build_dir = _execute(tmp_path)

    assert report["mode"] == "execute"
    assert report["phase_complete"] is True
    assert set(report["written_files"]) == set(REQUIRED_FILES)
    assert {path.name for path in build_dir.iterdir()} == set(REQUIRED_FILES)


def test_execute_matches_tracked_expected_spans(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    records = _read_jsonl(build_dir / "mentions.jsonl")
    expected = _read_jsonl(FIXTURE_DIR / "expected_spans.jsonl")
    fields = (
        "canonical_id",
        "source_field",
        "entity_type",
        "char_start",
        "char_end",
        "surface_text",
    )
    semantic = [{field: record[field] for field in fields} for record in records]

    assert semantic == expected


def test_independent_validator_accepts_generated_build(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)

    report = validate_build(build_dir=build_dir, write_reports=False)

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["summary"]["input_document_count"] == 4
    assert report["summary"]["mention_count"] == 17
    assert _check_map(report)["manifest_code_revision_matches_current_source"] is True
    assert report["verdict"]["authorized_follow_on"] == (
        "scientific_entity_review_and_evaluation_v0.1"
    )
    assert report["verdict"]["next_slice"] == (
        "bounded_scientific_entity_manual_review_evidence_v0.1"
    )


def test_validator_can_write_latest_and_history_reports(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    report_dir = tmp_path / "reports"

    report = validate_build(
        build_dir=build_dir,
        write_reports=True,
        report_dir=report_dir,
    )

    assert report["summary"]["ok"] is True
    assert (report_dir / "scientific_entity_evidence_build_latest.json").is_file()
    assert (report_dir / "scientific_entity_evidence_build_latest.md").is_file()
    assert len(list((report_dir / "history").glob("*.json"))) == 1
    assert len(list((report_dir / "history").glob("*.md"))) == 1


def test_input_above_selected_limit_fails_instead_of_truncating(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityEvidenceBuildError, match="truncation is forbidden"):
        build_baseline(
            output_root=tmp_path / "output",
            max_documents=3,
            execute=False,
        )


def test_requested_limit_above_hard_cap_fails(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityEvidenceBuildError, match="hard limit"):
        build_baseline(
            output_root=tmp_path / "output",
            max_documents=101,
            execute=False,
        )


def test_zero_document_limit_fails(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityEvidenceBuildError, match="must be positive"):
        build_baseline(
            output_root=tmp_path / "output",
            max_documents=0,
            execute=False,
        )


def test_accepted_status_cannot_be_emitted(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityEvidenceBuildError, match="cannot emit accepted"):
        build_baseline(
            output_root=tmp_path / "output",
            status=EntityEvidenceBuildStatus.ACCEPTED,
            execute=False,
        )


def test_fixture_status_is_reserved_for_tracked_fixture(tmp_path: Path) -> None:
    candidate_input = _write_candidate_input(tmp_path)

    with pytest.raises(ScientificEntityEvidenceBuildError, match="fixture status is reserved"):
        build_baseline(
            input_path=candidate_input,
            output_root=tmp_path / "output",
            status="fixture",
            execute=False,
        )


def test_configured_current_canonical_path_is_forbidden(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityEvidenceBuildError, match="canonical corpus"):
        build_baseline(
            input_path=(
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


def test_existing_build_directory_is_never_overwritten(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    manifest_before = (build_dir / "manifest.json").read_bytes()

    with pytest.raises(FileExistsError, match="overwrite is forbidden"):
        _execute(tmp_path)

    assert (build_dir / "manifest.json").read_bytes() == manifest_before


def test_repeated_builds_are_byte_deterministic_for_fixed_inputs(tmp_path: Path) -> None:
    _, first = _execute(tmp_path, output_name="first")
    _, second = _execute(tmp_path, output_name="second")

    assert {
        name: (first / name).read_bytes() for name in REQUIRED_FILES
    } == {
        name: (second / name).read_bytes() for name in REQUIRED_FILES
    }


def test_config_change_preserves_mention_ids_and_changes_evidence_ids(
    tmp_path: Path,
) -> None:
    _, first = _execute(tmp_path, output_name="first")

    def mutate(payload: dict[str, Any]) -> None:
        payload["rules"].append(
            {"entity_type": "method", "term": "unused synthetic method"}
        )

    changed_config = _write_config(tmp_path, mutate)
    _, second = _execute(
        tmp_path,
        config_path=changed_config,
        output_name="second",
    )
    first_rows = _read_jsonl(first / "mentions.jsonl")
    second_rows = _read_jsonl(second / "mentions.jsonl")

    assert [row["mention_id"] for row in first_rows] == [
        row["mention_id"] for row in second_rows
    ]
    assert [row["evidence_id"] for row in first_rows] != [
        row["evidence_id"] for row in second_rows
    ]


def test_source_text_change_changes_mention_identity(tmp_path: Path) -> None:
    _, first = _execute(tmp_path, output_name="first")
    changed_input = _write_candidate_input(tmp_path, title_suffix=" updated")
    _, second = _execute(
        tmp_path,
        input_path=changed_input,
        status="candidate",
        output_name="second",
    )
    first_bert = _read_jsonl(first / "mentions.jsonl")[0]
    second_bert = _read_jsonl(second / "mentions.jsonl")[0]

    assert first_bert["surface_text"] == second_bert["surface_text"] == "BERT"
    assert first_bert["mention_id"] != second_bert["mention_id"]


def test_all_generated_text_files_are_utf8_lf(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)

    for filename in REQUIRED_FILES:
        raw = (build_dir / filename).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in raw
        assert raw.endswith(b"\n")
        raw.decode("utf-8")


def test_validator_rejects_crlf_even_when_checksum_is_updated(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    readme_path = build_dir / "README.md"
    readme_path.write_bytes(readme_path.read_bytes().replace(b"\n", b"\r\n"))
    readme_sha = hashlib.sha256(readme_path.read_bytes()).hexdigest()
    checksum_path = build_dir / "checksums.txt"
    checksum_rows = checksum_path.read_text(encoding="utf-8").splitlines()
    checksum_rows = [
        f"{readme_sha}  README.md" if row.endswith("  README.md") else row
        for row in checksum_rows
    ]
    checksum_path.write_text(
        "\n".join(checksum_rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    report = validate_build(build_dir=build_dir, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["output_utf8_lf:README.md"] is False
    assert _check_map(report)["checksum_matches:README.md"] is True


def test_validator_rejects_corrupt_mention_surface(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    mention_path = build_dir / "mentions.jsonl"
    records = _read_jsonl(mention_path)
    records[0]["surface_text"] = "wrong"
    mention_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in records
        ),
        encoding="utf-8",
        newline="\n",
    )

    report = validate_build(build_dir=build_dir, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["mention_evidence_recomputed"] is False


def test_validator_rejects_build_directory_identity_mismatch(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    renamed = build_dir.with_name("renamed-build")
    build_dir.rename(renamed)

    report = validate_build(build_dir=renamed, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["build_directory_matches_build_id"] is False


def test_cli_defaults_to_non_mutating_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "cli-plan"

    exit_code = build_main(
        [
            "--output-root",
            str(output_root),
            "--build-id",
            "cli-plan-v0.1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "[OK] mode=plan" in output
    assert "[OK] phase_complete=False" in output
    assert not output_root.exists()


def test_cli_returns_nonzero_for_unsafe_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = build_main(
        [
            "--output-root",
            str(tmp_path / "output"),
            "--max-documents",
            "101",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "[FAILED]" in output
    assert "hard limit" in output
