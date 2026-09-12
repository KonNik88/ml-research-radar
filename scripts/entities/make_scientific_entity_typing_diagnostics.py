from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_typing_diagnostics import (
    REPORT_NAME,
    ScientificEntityTypingDiagnosticsError,
    prepare_typing_diagnostics,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_typing_diagnostics_v0.3.yaml"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Prepare Scientific Entity v0.3 typing diagnostics from immutable v0.2c evidence.")
    p.add_argument("--evaluation-dir", type=Path, required=True)
    p.add_argument("--decision-dir", type=Path, required=True)
    p.add_argument("--sample-dir", type=Path, required=True)
    p.add_argument("--reference-dir", type=Path, required=True)
    p.add_argument("--prediction-dir", type=Path, required=True)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--output-root", type=Path)
    p.add_argument("--analysis-id")
    p.add_argument("--execute", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare_typing_diagnostics(
            project_root=ROOT,
            config_path=args.config,
            evaluation_dir=args.evaluation_dir,
            decision_dir=args.decision_dir,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            prediction_dir=args.prediction_dir,
            output_root=args.output_root,
            analysis_id=args.analysis_id,
            execute=args.execute,
        )
    except (FileNotFoundError, OSError, ValueError, ScientificEntityTypingDiagnosticsError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1
    print(f"[OK] report={report['report']}")
    for key in (
        "mode", "phase_complete", "analysis_id", "evaluation_id", "decision_id",
        "type_mismatch_count", "same_span_type_mismatch_count", "same_span_type_mismatch_share",
        "model_to_method_count", "method_to_task_count", "method_sink_count", "maximum_sink_type", "maximum_sink_count",
        "high_confidence_at_0_8_count", "high_confidence_at_0_9_count", "root_causes_assigned",
        "model_inference_executed", "threshold_tuning_executed", "policy_reapplied", "evaluation_recomputed",
        "canonical_truth_mutated", "production_extractor_selected", "full_corpus_build_authorized",
        "output_dir", "next_slice",
    ):
        print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
