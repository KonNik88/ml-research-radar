from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import H2ProductionAuditError
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit import DEFAULT_CONFIG, REPORT_NAME, plan_or_execute_h2_production_audit_sample

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE = ROOT / "data" / "entities" / "scientific_entity_semantic_typer_h2_full_corpus_candidate" / "v0.3" / "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare the preregistered prediction-blind H2 v0.3 production audit sample.")
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = plan_or_execute_h2_production_audit_sample(project_root=ROOT, config_path=args.config, candidate_dir=args.candidate_dir, canonical_path=args.canonical, output_root=args.output_root, execute=args.execute)
    except (FileNotFoundError, FileExistsError, OSError, ValueError, H2ProductionAuditError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2
    for key in ("report", "mode", "phase_complete", "audit_id", "candidate_build_id", "materialization_fingerprint_sha256", "canonical_sha256", "canonical_document_count", "audit_case_count", "override_sample_count", "preserved_method_sample_count", "fallback_method_sample_count", "sample_already_exists", "prediction_blind", "plan_writes_output", "plan_reads_candidate_predictions", "model_inference_executed", "threshold_tuning_executed", "policy_revision_executed", "canonical_truth_mutated", "production_latest_promotion_authorized", "output_dir", "next_slice"):
        if key in report:
            print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
