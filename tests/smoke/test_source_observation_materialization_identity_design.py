from __future__ import annotations

from pathlib import Path

from scripts.validation.check_source_observation_materialization_identity_design import (
    CANDIDATE_PHASE_MARKERS,
    INVARIANT_MARKERS,
    LEGACY_PHASE_MARKERS,
    REQUIRED_DESIGN_MARKERS,
    REQUIRED_SECTIONS,
    build_report,
)


def _valid_design() -> str:
    return "\n".join(
        [
            "# Source Observation Materialization Identity Design v0.1",
            "implementation_status = not_started",
            "migration_status = not_started",
            "promotion_status = not_started",
            "canonical truth mutation is forbidden",
            "must not rename artifact-layer `source_doc_id`",
            "strategy = clean candidate database rebuild",
            "in_place_alter_operational_db = false",
            *REQUIRED_SECTIONS,
            *REQUIRED_DESIGN_MARKERS,
        ]
    )


def _grouped_markers(
    marker_sets: tuple[dict[str, tuple[str, str]], ...],
) -> dict[str, str]:
    grouped: dict[str, list[str]] = {
        "identity_helper": [],
        "schema": [],
        "indexes": [],
        "exporter": [],
        "api_db": [],
        "parity": [],
    }
    for marker_set in marker_sets:
        for _, (name, marker) in marker_set.items():
            grouped[name].append(marker)
    return {name: "\n".join(markers) for name, markers in grouped.items()}


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "design": tmp_path / "design.md",
        "identity_helper": tmp_path / "identity.py",
        "schema": tmp_path / "01_schema.sql",
        "indexes": tmp_path / "02_indexes.sql",
        "exporter": tmp_path / "exporter.py",
        "api_db": tmp_path / "db.py",
        "parity": tmp_path / "parity.py",
    }


def _report(
    tmp_path: Path,
    *,
    phase: str = "legacy",
    design_text: str | None = None,
    schema_text: str | None = None,
) -> dict:
    phase_markers = (
        LEGACY_PHASE_MARKERS
        if phase == "legacy"
        else CANDIDATE_PHASE_MARKERS
    )
    texts = _grouped_markers((INVARIANT_MARKERS, phase_markers))
    if schema_text is not None:
        texts["schema"] = schema_text

    return build_report(
        design_text=_valid_design() if design_text is None else design_text,
        identity_helper_text=texts["identity_helper"],
        schema_text=texts["schema"],
        indexes_text=texts["indexes"],
        exporter_text=texts["exporter"],
        api_db_text=texts["api_db"],
        parity_text=texts["parity"],
        input_paths=_paths(tmp_path),
    )


def test_complete_design_is_ready_on_legacy_baseline(tmp_path: Path) -> None:
    report = _report(tmp_path, phase="legacy")

    assert report["verdict"]["ok"] is True
    assert report["repository_phase"] == "legacy_baseline"
    assert report["verdict"]["design_ready_for_implementation_slice"] is True
    assert report["verdict"]["implementation_matches_design_candidate"] is False
    assert report["verdict"]["selected_identity"] == "source_observation_id"
    assert report["verdict"]["selected_migration_strategy"] == (
        "candidate_database_rebuild"
    )
    assert report["postgres_mutated"] is False
    assert report["canonical_truth_mutated"] is False


def test_design_validator_remains_green_after_candidate_implementation(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path, phase="candidate")

    assert report["verdict"]["ok"] is True
    assert report["repository_phase"] == "candidate_implementation"
    assert report["verdict"]["design_ready_for_implementation_slice"] is False
    assert report["verdict"]["implementation_matches_design_candidate"] is True
    assert report["verdict"]["next_slice"] is None


def test_missing_required_section_fails(tmp_path: Path) -> None:
    design_text = _valid_design().replace(
        "## 12. Rollback and failure isolation",
        "",
    )
    report = _report(tmp_path, design_text=design_text)

    assert report["verdict"]["ok"] is False
    assert (
        "section:## 12. Rollback and failure isolation"
        in report["verdict"]["required_failed_checks"]
    )


def test_missing_candidate_identity_marker_fails(tmp_path: Path) -> None:
    design_text = _valid_design().replace(
        "UNIQUE (canonical_id, source_observation_id)",
        "",
    )
    report = _report(tmp_path, design_text=design_text)

    assert report["verdict"]["ok"] is False
    assert any(
        "UNIQUE (canonical_id, source_observation_id)" in name
        for name in report["verdict"]["required_failed_checks"]
    )


def test_unrecognized_partial_repository_phase_fails(tmp_path: Path) -> None:
    texts = _grouped_markers((INVARIANT_MARKERS,))
    report = build_report(
        design_text=_valid_design(),
        identity_helper_text=texts["identity_helper"],
        schema_text="doc_id TEXT",
        indexes_text="",
        exporter_text="",
        api_db_text=texts["api_db"],
        parity_text=texts["parity"],
        input_paths=_paths(tmp_path),
    )

    assert report["verdict"]["ok"] is False
    assert report["repository_phase"] == "unrecognized_or_partial"
    assert (
        "repository_materialization_phase_recognized"
        in report["verdict"]["required_failed_checks"]
    )


def test_expected_contract_markers_are_guarded() -> None:
    assert "source_documents.source_observation_id" in REQUIRED_DESIGN_MARKERS
    assert (
        "UNIQUE (canonical_id, source_observation_id)"
        in REQUIRED_DESIGN_MARKERS
    )
    assert "--require-full-parity" in REQUIRED_DESIGN_MARKERS
    assert "legacy_doc_id =\n    preserved_non_unique_compatibility_field" in (
        REQUIRED_DESIGN_MARKERS
    )
    assert "legacy_exporter_conflict_target_present" in LEGACY_PHASE_MARKERS
    assert (
        "candidate_exporter_conflict_target_present"
        in CANDIDATE_PHASE_MARKERS
    )
