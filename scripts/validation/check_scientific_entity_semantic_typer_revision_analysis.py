from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_semantic_typer_revision_analysis import (
    validate_semantic_typer_revision_analysis,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_revision_analysis_v0.3.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Scientific Entity Semantic Typer v0.3 H1 failure/revision analysis.")
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    checks, summary = validate_semantic_typer_revision_analysis(
        project_root=ROOT,
        config_path=args.config,
        evaluation_dir=args.evaluation_dir,
        analysis_dir=args.analysis_dir,
    )
    for key in (
        "report", "validation_scope", "analysis_id", "policy_selected", "selected_threshold",
        "total_checks", "required_failed_count", "next_slice",
    ):
        if key in summary:
            print(f"[OK] {key}={summary[key]}")
    if args.strict and summary.get("required_failed_count", 0):
        for name, ok, detail in checks:
            if not ok:
                print(f"[FAIL] {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
