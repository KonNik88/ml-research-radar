from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_frozen_inference import (
    ScientificEntityFreshHeldoutFrozenInferenceError,
)
from radar_core.entities.scientific_entity_fresh_heldout_frozen_inference import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    REPORT_NAME,
    plan_or_execute_frozen_inference,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the one-shot frozen v0.2c raw inference on the fresh independent held-out. PLAN never runs the model."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--model-cache-dir", type=Path, default=None)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = plan_or_execute_frozen_inference(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            canonical_path=args.canonical,
            model_cache_dir=args.model_cache_dir,
            allow_model_download=args.allow_model_download,
            execute=args.execute,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError, ScientificEntityFreshHeldoutFrozenInferenceError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    for key in (
        "report", "mode", "phase_complete", "candidate_id", "runtime_config_sha256",
        "sample_id", "review_id", "reference_mention_count",
        "reference_validation_required_failed_count", "input_document_count", "build_id",
        "one_shot_already_executed", "plan_runs_model_inference", "model_inference_executed",
        "policy_applied", "evaluation_executed", "acceptance_decision_made",
        "canonical_truth_mutated", "production_extractor_selected", "full_corpus_build_authorized",
        "output_dir", "next_slice",
    ):
        print(f"[OK] {key}={report.get(key)}")
    for key in ("raw_mention_count", "extractor_fingerprint", "model_artifact_verified", "backbone_config_verified", "runtime_device_name", "inference_duration_seconds", "peak_cuda_memory_bytes"):
        if key in report:
            print(f"[OK] {key}={report.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
