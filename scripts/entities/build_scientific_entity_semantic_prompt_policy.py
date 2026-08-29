from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_policy import (
    DEFAULT_CONFIG_PATH,
    build_semantic_prompt_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or execute v0.2a semantic-prompt policy materialization.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--parent-build-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--build-id", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_semantic_prompt_policy(
        config_path=args.config,
        parent_build_dir=args.parent_build_dir,
        development_package_dir=args.development_package_dir,
        output_root=args.output_root,
        build_id=args.build_id,
        execute=args.execute,
    )
    for key in (
        "report", "mode", "phase_complete", "build_id", "parent_build_id",
        "development_package_id", "candidate_id", "input_document_count",
        "input_prediction_count", "selected_prediction_count", "rejected_prediction_count",
        "extractor_fingerprint_changed", "title_threshold", "abstract_threshold",
        "model_inference_executed", "threshold_tuning_executed", "canonical_truth_mutated",
        "full_corpus_build_authorized", "production_extractor_selected", "output_dir", "next_slice",
    ):
        print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
