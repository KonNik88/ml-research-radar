from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_typing_root_cause_review import (
    validate_final_review,
    validate_working_copy,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_typing_root_cause_review_v0.3.yaml"


def _print_summary(summary: dict) -> None:
    preferred = (
        "report",
        "validation_scope",
        "review_id",
        "parent_analysis_id",
        "type_mismatch_count",
        "complete_count",
        "pending_count",
        "review_complete",
        "reviewed_case_count",
        "root_causes_assigned",
        "total_checks",
        "required_failed_count",
        "next_slice",
    )
    for key in preferred:
        if key in summary:
            print(f"[OK] {key}={summary[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Scientific Entity typing root-cause review v0.3."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--working-dir", type=Path)
    group.add_argument("--review-dir", type=Path)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    if args.working_dir is not None:
        checks, summary = validate_working_copy(
            working_dir=args.working_dir,
            config_path=args.config,
            diagnostics_dir=args.diagnostics_dir,
        )
    else:
        checks, summary = validate_final_review(
            review_dir=args.review_dir,
            config_path=args.config,
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
