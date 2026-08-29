from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_prompt_candidate import (
    SemanticPromptCandidateError,
    validate_candidate_contract,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_candidate_v0.2a.yaml"
REPORT_NAME = "scientific_entity_semantic_prompt_candidate_v02a_contract"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the frozen Scientific Entity semantic-prompt v0.2a design contract."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_candidate_contract(
            project_root=ROOT,
            design_config_path=args.config,
        )
    except (FileNotFoundError, OSError, ValueError, SemanticPromptCandidateError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1 if args.strict else 0

    print(f"[OK] report={REPORT_NAME}")
    print(f"[OK] candidate_id={report['candidate_id']}")
    print(f"[OK] status={report['status']}")
    print(f"[OK] development_document_count={report['development_document_count']}")
    print(f"[OK] changed_prompt_count={report['changed_prompt_count']}")
    print(f"[OK] runtime_config_sha_changed={report['runtime_config_sha_changed']}")
    print(f"[OK] raw_candidate_inference_threshold={report['raw_candidate_inference_threshold']}")
    print(f"[OK] title_policy_threshold={report['title_policy_threshold']}")
    print(f"[OK] abstract_policy_threshold={report['abstract_policy_threshold']}")
    print(f"[OK] model_repository={report['model_repository']}")
    print(f"[OK] model_revision={report['model_revision']}")
    print(f"[OK] window_size_tokens={report['window_size_tokens']}")
    print(f"[OK] window_overlap_tokens={report['window_overlap_tokens']}")
    print(f"[OK] minimum_overall_exact_f1={report['minimum_overall_exact_f1']}")
    print(f"[OK] maximum_model_to_method_count={report['maximum_model_to_method_count']}")
    print(f"[OK] maximum_method_to_task_count={report['maximum_method_to_task_count']}")
    print(f"[OK] maximum_total_type_mismatch_count={report['maximum_total_type_mismatch_count']}")
    print(f"[OK] maximum_method_semantic_sink_count={report['maximum_method_semantic_sink_count']}")
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] threshold_tuning_executed={report['threshold_tuning_executed']}")
    print(f"[OK] canonical_truth_mutated={report['canonical_truth_mutated']}")
    print(f"[OK] full_corpus_build_authorized={report['full_corpus_build_authorized']}")
    print(f"[OK] production_extractor_selected={report['production_extractor_selected']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
