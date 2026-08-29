from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_comparison import (
    DEFAULT_CONFIG_PATH,
    build_semantic_prompt_comparison,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the v0.2a scientific-entity semantic-prompt controlled comparison."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--policy-build-dir", type=Path, required=True)
    parser.add_argument("--parent-raw-build-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--comparison-id")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_semantic_prompt_comparison(
        project_root=PROJECT_ROOT,
        config_path=args.config,
        development_package_dir=args.development_package_dir,
        policy_build_dir=args.policy_build_dir,
        parent_raw_build_dir=args.parent_raw_build_dir,
        output_root=args.output_root,
        comparison_id=args.comparison_id,
        execute=args.execute,
    )
    print(f"[OK] report={report['report']}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] comparison_id={report['comparison_id']}")
    print(f"[OK] development_document_count={report['development_document_count']}")
    print(f"[OK] reference_mention_count={report['reference_mention_count']}")
    print(f"[OK] candidate_prediction_count={report['candidate_prediction_count']}")
    print(f"[OK] consumed_heldout_candidate_exact_f1={report['consumed_heldout_candidate_exact_f1']}")
    print(f"[OK] consumed_heldout_candidate_relaxed_f1={report['consumed_heldout_candidate_relaxed_f1']}")
    print(f"[OK] consumed_heldout_model_to_method_count={report['consumed_heldout_model_to_method_count']}")
    print(f"[OK] consumed_heldout_method_to_task_count={report['consumed_heldout_method_to_task_count']}")
    print(f"[OK] consumed_heldout_total_type_mismatch_count={report['consumed_heldout_total_type_mismatch_count']}")
    print(f"[OK] consumed_heldout_method_semantic_sink_count={report['consumed_heldout_method_semantic_sink_count']}")
    print(f"[OK] all_hard_guardrails_passed={report['all_hard_guardrails_passed']}")
    print(f"[OK] candidate_promising_for_next_development_slice={report['candidate_promising_for_next_development_slice']}")
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] threshold_tuning_executed={report['threshold_tuning_executed']}")
    print(f"[OK] canonical_truth_mutated={report['canonical_truth_mutated']}")
    print(f"[OK] full_corpus_build_authorized={report['full_corpus_build_authorized']}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
