from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_semantic_typer_development import (
    validate_semantic_typer_development,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"


def _print_summary(summary: dict) -> None:
    preferred = (
        "report",
        "validation_scope",
        "package_id",
        "case_count",
        "baseline_correct_same_span_count",
        "baseline_wrong_same_span_count",
        "primary_metric_eligible_count",
        "primary_metric_excluded_count",
        "total_checks",
        "required_failed_count",
        "next_slice",
    )
    for key in preferred:
        if key in summary:
            print(f"[OK] {key}={summary[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Scientific Entity Semantic Typer v0.3 development evidence."
    )
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    checks, summary = validate_semantic_typer_development(
        project_root=ROOT,
        config_path=args.config,
        package_dir=args.package_dir,
        evaluation_dir=args.evaluation_dir,
        review_dir=args.review_dir,
        diagnostics_dir=args.diagnostics_dir,
    )
    _print_summary(summary)
    if args.strict and summary.get("required_failed_count", 0):
        for name, ok, detail in checks:
            if not ok:
                print(f"[FAIL] {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
