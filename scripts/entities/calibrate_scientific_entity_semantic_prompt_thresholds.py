from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_threshold_calibration import (
    DEFAULT_CONFIG_PATH,
    build_semantic_prompt_threshold_calibration,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute bounded source-field threshold calibration for the "
            "frozen v0.2a semantic prompts."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--raw-build-dir", type=Path, required=True)
    parser.add_argument("--v02a-comparison-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--calibration-id")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_semantic_prompt_threshold_calibration(
        project_root=PROJECT_ROOT,
        config_path=args.config,
        development_package_dir=args.development_package_dir,
        raw_build_dir=args.raw_build_dir,
        v02a_comparison_dir=args.v02a_comparison_dir,
        output_root=args.output_root,
        calibration_id=args.calibration_id,
        execute=args.execute,
    )
    print(f"[OK] report={report['report']}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] calibration_id={report['calibration_id']}")
    print(f"[OK] document_count={report['document_count']}")
    print(f"[OK] reference_mention_count={report['reference_mention_count']}")
    print(f"[OK] raw_prediction_count={report['raw_prediction_count']}")
    print(f"[OK] trial_count={report['trial_count']}")
    print(f"[OK] eligible_trial_count={report['eligible_trial_count']}")
    print(f"[OK] selected_trial_id={report['selected_trial_id']}")
    print(f"[OK] selected_title_threshold={report['selected_title_threshold']}")
    print(f"[OK] selected_abstract_threshold={report['selected_abstract_threshold']}")
    print(f"[OK] selected_combined_exact_f1={report['selected_combined_exact_f1']}")
    print(f"[OK] selected_consumed_heldout_exact_f1={report['selected_consumed_heldout_exact_f1']}")
    print(f"[OK] selected_model_to_method_count={report['selected_model_to_method_count']}")
    print(f"[OK] selected_method_to_task_count={report['selected_method_to_task_count']}")
    print(f"[OK] selected_total_type_mismatch_count={report['selected_total_type_mismatch_count']}")
    print(f"[OK] selected_method_semantic_sink_count={report['selected_method_semantic_sink_count']}")
    print(f"[OK] all_hard_gates_passed={report['all_hard_gates_passed']}")
    print(f"[OK] candidate_promising_for_future_freeze={report['candidate_promising_for_future_freeze']}")
    print(f"[OK] raw_input_floor_may_be_binding={report['raw_input_floor_may_be_binding']}")
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] prompt_changes_executed={report['prompt_changes_executed']}")
    print(f"[OK] threshold_search_executed={report['threshold_search_executed']}")
    print(f"[OK] fresh_heldout_consumed={report['fresh_heldout_consumed']}")
    print(f"[OK] canonical_truth_mutated={report['canonical_truth_mutated']}")
    print(f"[OK] full_corpus_build_authorized={report['full_corpus_build_authorized']}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
