from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_typing_root_cause_review import (
    finalize_review,
    prepare_working_copy,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_typing_root_cause_review_v0.3.yaml"


def _print_report(report: dict) -> None:
    preferred = (
        "report",
        "phase",
        "mode",
        "phase_complete",
        "review_id",
        "parent_analysis_id",
        "evaluation_id",
        "type_mismatch_count",
        "same_span_type_mismatch_count",
        "model_to_method_count",
        "method_to_task_count",
        "method_sink_count",
        "working_complete_count",
        "working_pending_count",
        "reviewed_case_count",
        "pending_count",
        "root_causes_assigned",
        "human_review_only",
        "model_inference_executed",
        "threshold_tuning_executed",
        "policy_reapplied",
        "evaluation_recomputed",
        "canonical_truth_mutated",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "automatic_root_cause_assignment_executed",
        "automatic_candidate_selection_executed",
        "output_dir",
        "next_slice",
    )
    for key in preferred:
        if key in report:
            print(f"[OK] {key}={report[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare/finalize Scientific Entity typing root-cause review v0.3."
    )
    parser.add_argument(
        "--phase",
        choices=("prepare", "finalize"),
        required=True,
    )
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--review-id")
    parser.add_argument("--working-dir", type=Path)
    parser.add_argument("--working-root", type=Path)
    parser.add_argument("--final-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    if args.phase == "prepare":
        if args.working_dir is not None:
            parser.error("--working-dir is only valid for --phase finalize")
        report = prepare_working_copy(
            project_root=ROOT,
            config_path=args.config,
            diagnostics_dir=args.diagnostics_dir,
            review_id=args.review_id,
            working_root=args.working_root,
            execute=args.execute,
        )
    else:
        if args.working_dir is None:
            parser.error("--working-dir is required for --phase finalize")
        if args.review_id is not None:
            parser.error("--review-id is derived from the working manifest during finalize")
        report = finalize_review(
            project_root=ROOT,
            config_path=args.config,
            diagnostics_dir=args.diagnostics_dir,
            working_dir=args.working_dir,
            final_root=args.final_root,
            execute=args.execute,
        )

    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
