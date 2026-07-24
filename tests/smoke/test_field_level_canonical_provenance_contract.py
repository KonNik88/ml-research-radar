from __future__ import annotations

from pathlib import Path

from scripts.validation.check_field_level_canonical_provenance_contract import (
    ACCEPTED_STRATEGY_KINDS,
    FIELD_STRATEGIES,
    MODEL_DEFAULT_FIELDS,
    REQUIRED_CONTRACT_MARKERS,
    REQUIRED_IDENTITY_FUNCTIONS,
    REQUIRED_RECONCILE_FUNCTIONS,
    REQUIRED_SECTIONS,
    build_report,
)


def _canonical_contract() -> str:
    fields = "\n".join(f"    {name}: str" for name in FIELD_STRATEGIES)
    return f"class CanonicalDocument:\n{fields}\n"


def _normalized_contract() -> str:
    fields = (
        "doc_id",
        "source",
        "source_id",
        "source_record_id",
        "source_record_url",
        "source_api_url",
        "canonical_url",
    )
    return "class NormalizedDocument:\n" + "\n".join(
        f"    {name}: str" for name in fields
    )


def _functions(names: set[str]) -> str:
    return "\n\n".join(f"def {name}():\n    pass" for name in sorted(names))


def _reconcile() -> str:
    assembly = sorted(set(FIELD_STRATEGIES) - MODEL_DEFAULT_FIELDS)
    keywords = ",\n        ".join(f"{name}=None" for name in assembly)
    return (
        _functions(REQUIRED_RECONCILE_FUNCTIONS)
        + "\n\ndef synthetic_builder():\n"
        + "    return CanonicalDocument(\n        "
        + keywords
        + "\n    )\n"
    )


def _identity() -> str:
    return _functions(REQUIRED_IDENTITY_FUNCTIONS)


def _contract() -> str:
    lines = [
        "# Field-Level Canonical Provenance Contract v0.1",
        *REQUIRED_SECTIONS,
        *REQUIRED_CONTRACT_MARKERS,
    ]
    for field_name, strategy in FIELD_STRATEGIES.items():
        lines.append(f"`{field_name}` uses `{strategy}`")
    return "\n".join(lines)


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "contract": tmp_path / "contract.md",
        "reconcile": tmp_path / "reconcile.py",
        "canonical_contract": tmp_path / "canonical.py",
        "normalized_contract": tmp_path / "document.py",
        "source_identity": tmp_path / "identity.py",
    }


def _report(tmp_path: Path, **overrides: str) -> dict:
    payload = {
        "contract_text": _contract(),
        "reconcile_text": _reconcile(),
        "canonical_contract_text": _canonical_contract(),
        "normalized_contract_text": _normalized_contract(),
        "source_identity_text": _identity(),
    }
    payload.update(overrides)
    return build_report(**payload, input_paths=_paths(tmp_path))


def test_complete_contract_matches_current_shape(tmp_path: Path) -> None:
    report = _report(tmp_path)

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["contract_matches_current_reconciliation"] is True
    assert report["verdict"]["canonical_contract_change_required"] is False
    assert report["verdict"]["reconciliation_behavior_change_required"] is False
    assert report["verdict"]["next_slice"] == (
        "field_level_canonical_provenance_evidence_builder_v0.1"
    )
    assert report["summary"]["canonical_field_count"] == len(FIELD_STRATEGIES)
    assert report["summary"]["classified_field_count"] == len(FIELD_STRATEGIES)


def test_missing_canonical_field_classification_fails(tmp_path: Path) -> None:
    text = _canonical_contract() + "    unexpected_field: str\n"
    report = _report(tmp_path, canonical_contract_text=text)

    assert report["verdict"]["ok"] is False
    assert "all_canonical_fields_classified" in report["verdict"][
        "required_failed_checks"
    ]


def test_missing_assembly_field_fails(tmp_path: Path) -> None:
    reconcile = _reconcile().replace("title=None,\n        ", "")
    report = _report(tmp_path, reconcile_text=reconcile)

    assert report["verdict"]["ok"] is False
    assert "all_non_default_fields_are_assembled" in report["verdict"][
        "required_failed_checks"
    ]


def test_runtime_defaults_must_not_be_explicitly_assembled(tmp_path: Path) -> None:
    reconcile = _reconcile().replace(
        "\n    )\n",
        ",\n        created_at=None,\n        updated_record_at=None\n    )\n",
        1,
    )
    report = _report(tmp_path, reconcile_text=reconcile)

    assert report["verdict"]["ok"] is False
    assert "runtime_default_fields_are_not_explicitly_assembled" in report[
        "verdict"
    ]["required_failed_checks"]


def test_missing_reconcile_function_fails(tmp_path: Path) -> None:
    reconcile = _reconcile().replace(
        "def choose_best_title():\n    pass\n\n",
        "",
    )
    report = _report(tmp_path, reconcile_text=reconcile)

    assert report["verdict"]["ok"] is False
    assert "required_reconcile_functions_present" in report["verdict"][
        "required_failed_checks"
    ]


def test_missing_identity_function_fails(tmp_path: Path) -> None:
    identity = _identity().replace(
        "def build_source_observation_identity_from_mapping():\n    pass\n\n",
        "",
    )
    report = _report(tmp_path, source_identity_text=identity)

    assert report["verdict"]["ok"] is False
    assert "required_identity_functions_present" in report["verdict"][
        "required_failed_checks"
    ]


def test_contract_must_distinguish_observation_states(tmp_path: Path) -> None:
    contract = _contract().replace("field candidate observation", "")
    report = _report(tmp_path, contract_text=contract)

    assert report["verdict"]["ok"] is False
    assert any(
        name.startswith("marker:field candidate observation")
        for name in report["verdict"]["required_failed_checks"]
    )


def test_all_strategies_are_known_and_coverage_is_exact() -> None:
    assert set(FIELD_STRATEGIES.values()) <= ACCEPTED_STRATEGY_KINDS
    assert MODEL_DEFAULT_FIELDS == {"created_at", "updated_record_at"}
    assert FIELD_STRATEGIES["title"] == "winner"
    assert FIELD_STRATEGIES["authors"] == "ordered_union"
    assert FIELD_STRATEGIES["metadata_completeness_score"] == "derived_score"
    assert FIELD_STRATEGIES["reconciliation_key"] == "identity_derived"
