from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_heldout_review import finalize_heldout_review


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_heldout_review_evidence_v0.1.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finalize prediction-blind held-out scientific-entity review evidence v0.1"
    )
    parser.add_argument("--prepared-dir", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--annotator-id", action="append", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    report = finalize_heldout_review(
        prepared_dir=args.prepared_dir,
        annotations_path=args.annotations,
        config_path=args.config,
        annotator_ids=args.annotator_id,
        output_root=args.output_root,
        execute=args.execute,
    )
    print("[OK] report=" + report["report"])
    print("[OK] mode=" + report["mode"])
    print(f"[OK] phase_complete={report['phase_complete']}")
    print("[OK] review_id=" + report["review_id"])
    print(f"[OK] document_count={report['document_count']}")
    print(f"[OK] annotation_row_count={report['annotation_row_count']}")
    print(f"[OK] reference_mention_count={report['reference_mention_count']}")
    print(
        f"[OK] uncertain_reference_mention_count={report['uncertain_reference_mention_count']}"
    )
    for key, value in report["reference_count_by_type"].items():
        print(f"[OK] reference_count_by_type:{key}={value}")
    print("[OK] blank_annotations_sha256=" + report["blank_annotations_sha256"])
    print("[OK] completed_annotations_sha256=" + report["completed_annotations_sha256"])
    print(f"[OK] prediction_blind={report['prediction_blind']}")
    print(f"[OK] heldout_dev_overlap_count={report['heldout_dev_overlap_count']}")
    print(f"[OK] evaluation_harness_ready={report['evaluation_harness_ready']}")
    print("[OK] output_dir=" + report["output_dir"])
    print("[OK] next_slice=" + report["next_slice"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
