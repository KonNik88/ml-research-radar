from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_full_ner_coverage_audit import (
    execute_full_ner_coverage_audit,
    plan_full_ner_coverage_audit,
)

DEFAULT_CONFIG = Path("configs/scientific_entity_full_ner_coverage_audit_v0.1.yaml")
DEFAULT_GUIDE = Path("docs/scientific_entity_full_ner_coverage_annotation_guide_v0.1.md")


def _print(report: dict) -> None:
    for key, value in report.items():
        if key == "checks":
            continue
        print(f"[OK] {key}={value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare prediction-blind full NER coverage audit sample.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    repo_root = Path.cwd()
    if args.execute:
        report = execute_full_ner_coverage_audit(args.config, repo_root, repo_root / DEFAULT_GUIDE)
    else:
        report = plan_full_ner_coverage_audit(args.config, repo_root)
    _print(report)


if __name__ == "__main__":
    main()
