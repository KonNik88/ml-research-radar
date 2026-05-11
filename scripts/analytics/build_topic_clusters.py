from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.analytics.topic_clusters import (
    DEFAULT_TOPIC_CLUSTERS_CONFIG_PATH,
    build_topic_cluster_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a file-first topic cluster run over latest retrieval dense embeddings."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_TOPIC_CLUSTERS_CONFIG_PATH,
        help="Path to topic cluster YAML config.",
    )
    parser.add_argument(
        "--n-clusters",
        type=int,
        default=None,
        help="Override method.params.n_clusters from config.",
    )
    parser.add_argument(
        "--no-write-latest",
        action="store_true",
        help="Write timestamped run artifacts and history report, but do not update latest pointers.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    result = build_topic_cluster_run(
        config_path=args.config,
        n_clusters_override=args.n_clusters,
        write_latest_override=False if args.no_write_latest else None,
    )

    summary = result["summary"]
    counts = summary["counts"]
    metrics = summary["global_metrics"]
    paths = result["paths"]

    print("[OK] topic cluster run built")
    print(f"[OK] cluster_build_id={summary['cluster_build_id']}")
    print(f"[OK] retrieval_build_id={summary['retrieval_build_id']}")
    print(f"[OK] cluster_config_hash={summary['cluster_config_hash']}")
    print(f"[OK] algorithm={summary['method']['algorithm']}")
    print(f"[OK] params={summary['method']['params']}")
    print(f"[OK] embedding_model={summary['embedding']['model_name']}")
    print(f"[OK] embedding_shape={summary['embedding']['shape']}")
    print(f"[OK] assigned_rows_count={counts['assigned_rows_count']}")
    print(f"[OK] cluster_count={counts['cluster_count']}")
    print(f"[OK] empty_cluster_count={counts['empty_cluster_count']}")
    print(f"[OK] largest_cluster_size={metrics['largest_cluster_size']}")
    print(f"[OK] largest_cluster_ratio={metrics['largest_cluster_ratio']}")
    print(f"[OK] run_dir={paths['run_dir']}")
    print(f"[OK] assignments_path={paths['assignments_path']}")
    print(f"[OK] summary_path={paths['summary_path']}")
    print(f"[OK] label_candidates_path={paths['label_candidates_path']}")
    if result["write_latest"]:
        print(f"[OK] latest_path={paths['latest_path']}")
        print(f"[OK] latest_report_json={paths['latest_report_json_path']}")
        print(f"[OK] latest_report_md={paths['latest_report_md_path']}")
    else:
        print("[OK] latest pointer was not updated (--no-write-latest)")


if __name__ == "__main__":
    main()
