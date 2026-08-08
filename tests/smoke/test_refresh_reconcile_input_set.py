from __future__ import annotations

from pathlib import Path

from scripts.update import run_incremental_reconcile_stage as reconcile_stage


def test_acl_documents_latest_is_full_snapshot_shape() -> None:
    assert reconcile_stage.is_full_snapshot_file(
        Path("data/normalized/acl_anthology/documents_latest.jsonl")
    )


def test_acl_input_defaults_to_latest_full_snapshot(tmp_path: Path) -> None:
    normalized_root = tmp_path / "data/normalized"
    acl_path = normalized_root / "acl_anthology/documents_latest.jsonl"
    acl_path.parent.mkdir(parents=True, exist_ok=True)
    acl_path.write_text('{"id": "2024.acl-long.109"}\n', encoding="utf-8")

    assert reconcile_stage.resolve_acl_input(normalized_root, None) == acl_path


def test_explicit_acl_input_is_preserved(tmp_path: Path) -> None:
    normalized_root = tmp_path / "data/normalized"
    explicit_path = tmp_path / "custom/acl.jsonl"

    assert reconcile_stage.resolve_acl_input(normalized_root, explicit_path) == explicit_path
