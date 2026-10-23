from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_full_ner_coverage_audit import validate_sample_package

DEFAULT_CONFIG = Path("configs/scientific_entity_full_ner_coverage_audit_v0.1.yaml")
DEFAULT_GUIDE = Path("docs/scientific_entity_full_ner_coverage_annotation_guide_v0.1.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate immutable full NER coverage audit sample.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = validate_sample_package(args.config, Path.cwd(), Path.cwd() / DEFAULT_GUIDE)
    for item in report.get("checks", []):
        status = "OK" if item["ok"] else "FAIL"
        print(f"[{status}] check={item['check']} detail={item['detail']}")
    for key, value in report.items():
        if key in {"checks", "failed_checks"}:
            continue
        print(f"[OK] {key}={value}")
    if args.strict and report["required_failed_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
