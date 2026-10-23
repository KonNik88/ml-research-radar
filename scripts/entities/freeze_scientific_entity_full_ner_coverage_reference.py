"""Freeze completed blind full NER coverage reference; no production inference."""
from __future__ import annotations
import argparse
from pathlib import Path
from radar_core.entities.scientific_entity_full_ner_coverage_reference import (
    execute_reference_freeze, plan_reference_freeze,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/scientific_entity_full_ner_coverage_reference_v0.1.yaml"))
    parser.add_argument("--annotations-path", type=Path, default=None,
        help="Optional alternate completed annotations JSONL path inside the repository; exact SHA is still required")
    parser.add_argument("--execute", action="store_true", help="Create immutable reference exactly once")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = args.config if args.config.is_absolute() else root / args.config
    source = args.annotations_path
    if source is not None and not source.is_absolute():
        source = root / source
    result = (execute_reference_freeze if args.execute else plan_reference_freeze)(config,root,source)
    for k,v in result.items():
        print(f"[OK] {k}={v}")

if __name__ == "__main__":
    main()
