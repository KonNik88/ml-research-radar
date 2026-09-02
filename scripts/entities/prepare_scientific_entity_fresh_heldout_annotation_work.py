from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_reference import (
    ScientificEntityFreshHeldoutReferenceError,
)
from radar_core.entities.scientific_entity_fresh_heldout_reference import (
    REPORT_NAME,
    prepare_annotation_working_copy,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_reference_freeze_v0.2.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a mutable prediction-blind working copy for the frozen fresh v0.2 held-out annotations."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare_annotation_working_copy(
            project_root=ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            canonical_path=args.canonical,
            development_package_dir=args.development_package_dir,
            output_root=args.output_root,
            execute=args.execute,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError, ScientificEntityFreshHeldoutReferenceError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    for key in (
        "report", "mode", "phase_complete", "sample_id", "review_id",
        "annotation_row_count", "blank_annotations_sha256",
        "selected_canonical_ids_sha256", "working_copy_is_mutable_non_evidence",
        "prediction_blind", "model_inference_executed", "evaluation_executed",
        "output_dir", "next_slice",
    ):
        print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
