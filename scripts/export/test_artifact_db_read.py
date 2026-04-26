from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


try:
    import psycopg2 as pg_driver  # type: ignore
except ImportError:
    try:
        import psycopg as pg_driver  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Neither psycopg2 nor psycopg is installed. "
            "Install psycopg or psycopg2 in the ml_radar environment."
        ) from exc


REPORT_DIR = Path("artifacts/reports/export")
HISTORY_DIR = REPORT_DIR / "history"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        os.environ.setdefault(key, value)


load_dotenv_file(Path(".env"))
load_dotenv_file(Path("infra/docker/.env"))


def get_db_config() -> dict[str, Any]:
    return {
        "host": os.getenv(
            "ML_RADAR_DB_HOST",
            os.getenv("ML_RADAR_POSTGRES_HOST", os.getenv("POSTGRES_HOST", "127.0.0.1")),
        ),
        "port": int(
            os.getenv(
                "ML_RADAR_DB_PORT",
                os.getenv("ML_RADAR_POSTGRES_PORT", os.getenv("POSTGRES_PORT", "15432")),
            )
        ),
        "dbname": os.getenv(
            "ML_RADAR_DB_NAME",
            os.getenv(
                "ML_RADAR_POSTGRES_DBNAME",
                os.getenv("POSTGRES_DB", "ml_radar"),
            ),
        ),
        "user": os.getenv(
            "ML_RADAR_DB_USER",
            os.getenv("ML_RADAR_POSTGRES_USER", os.getenv("POSTGRES_USER", "ml_radar")),
        ),
        "password": os.getenv(
            "ML_RADAR_DB_PASSWORD",
            os.getenv(
                "ML_RADAR_POSTGRES_PASSWORD",
                os.getenv("POSTGRES_PASSWORD", "ml_radar"),
            ),
        ),
    }


def connect_db():
    return pg_driver.connect(**get_db_config())


def fetch_one(conn, sql: str, params: tuple[Any, ...] | None = None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def fetch_all(conn, sql: str, params: tuple[Any, ...] | None = None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def scalar_int(conn, sql: str) -> int:
    row = fetch_one(conn, sql)
    if not row:
        return 0
    return int(row[0] or 0)


def table_exists(conn, table_name: str) -> bool:
    row = fetch_one(
        conn,
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
        );
        """,
        (table_name,),
    )
    return bool(row[0]) if row else False


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines: list[str] = []

    lines.append("# Artifact DB read smoke check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- OK: **{report['ok']}**")
    lines.append("")

    lines.append("## Counts")
    lines.append("")
    for key in [
        "canonical_documents_count",
        "artifact_entities_count",
        "artifact_observations_count",
        "paper_artifact_links_count",
        "join_canonical_artifact_entities_count",
        "join_canonical_documents_count",
        "join_artifact_entities_count",
    ]:
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")

    lines.append("## Required checks")
    lines.append("")
    lines.append("| Check | OK |")
    lines.append("|---|---:|")
    for name, ok in report["required_checks"].items():
        lines.append(f"| `{name}` | {ok} |")
    lines.append("")

    if report["required_failed_checks"]:
        lines.append("## Required failures")
        lines.append("")
        for item in report["required_failed_checks"]:
            lines.append(f"- `{item}`")
        lines.append("")

    lines.append("## Provider distribution")
    lines.append("")
    add_table(lines, report.get("provider_distribution") or [])

    lines.append("## Link relation distribution")
    lines.append("")
    add_table(lines, report.get("relation_distribution") or [])

    lines.append("## Provider × relation distribution")
    lines.append("")
    add_table(lines, report.get("provider_relation_distribution") or [])

    lines.append("## Sample joined links")
    lines.append("")
    samples = report.get("sample_joined_links") or []
    if not samples:
        lines.append("_empty_")
    else:
        lines.append("| Title | Provider | Artifact type | Relation | Confidence | URL |")
        lines.append("|---|---|---|---|---:|---|")
        for row in samples:
            title = str(row.get("title") or "").replace("|", "\\|")[:120]
            provider = row.get("provider")
            artifact_type = row.get("artifact_type")
            relation_type = row.get("relation_type")
            confidence = row.get("confidence")
            url = str(row.get("normalized_url") or "").replace("|", "\\|")
            lines.append(
                f"| {title} | `{provider}` | `{artifact_type}` | `{relation_type}` | {confidence} | {url} |"
            )
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def add_table(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("_empty_")
        lines.append("")
        return

    headers = list(rows[0].keys())
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")

    for row in rows:
        values = [str(row.get(h, "")).replace("|", "\\|") for h in headers]
        lines.append("| " + " | ".join(values) + " |")

    lines.append("")


def rows_to_dicts(rows, columns: list[str]) -> list[dict[str, Any]]:
    return [
        {col: value for col, value in zip(columns, row)}
        for row in rows
    ]


def main() -> None:
    run_ts = utc_now_ts()

    report: dict[str, Any] = {
        "report_name": "test_artifact_db_read",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "db": {
            "host": get_db_config()["host"],
            "port": get_db_config()["port"],
            "dbname": get_db_config()["dbname"],
            "user": get_db_config()["user"],
        },
        "ok": False,
    }

    conn = connect_db()

    try:
        table_names = [
            "canonical_documents",
            "artifact_entities",
            "artifact_observations",
            "paper_artifact_links",
        ]

        table_exists_map = {
            name: table_exists(conn, name)
            for name in table_names
        }

        report["table_exists"] = table_exists_map

        canonical_documents_count = scalar_int(conn, "SELECT COUNT(*) FROM canonical_documents;")
        artifact_entities_count = scalar_int(conn, "SELECT COUNT(*) FROM artifact_entities;")
        artifact_observations_count = scalar_int(conn, "SELECT COUNT(*) FROM artifact_observations;")
        paper_artifact_links_count = scalar_int(conn, "SELECT COUNT(*) FROM paper_artifact_links;")

        join_canonical_artifact_entities_count = scalar_int(
            conn,
            """
            SELECT COUNT(*)
            FROM paper_artifact_links pal
            JOIN canonical_documents cd
              ON cd.canonical_id = pal.canonical_id
            JOIN artifact_entities ae
              ON ae.artifact_id = pal.artifact_id;
            """,
        )

        join_canonical_documents_count = scalar_int(
            conn,
            """
            SELECT COUNT(DISTINCT pal.canonical_id)
            FROM paper_artifact_links pal
            JOIN canonical_documents cd
              ON cd.canonical_id = pal.canonical_id;
            """,
        )

        join_artifact_entities_count = scalar_int(
            conn,
            """
            SELECT COUNT(DISTINCT pal.artifact_id)
            FROM paper_artifact_links pal
            JOIN artifact_entities ae
              ON ae.artifact_id = pal.artifact_id;
            """,
        )

        provider_distribution = rows_to_dicts(
            fetch_all(
                conn,
                """
                SELECT provider, COUNT(*) AS count
                FROM artifact_entities
                GROUP BY provider
                ORDER BY COUNT(*) DESC, provider ASC;
                """,
            ),
            ["provider", "count"],
        )

        relation_distribution = rows_to_dicts(
            fetch_all(
                conn,
                """
                SELECT relation_type, COUNT(*) AS count
                FROM paper_artifact_links
                GROUP BY relation_type
                ORDER BY COUNT(*) DESC, relation_type ASC;
                """,
            ),
            ["relation_type", "count"],
        )

        provider_relation_distribution = rows_to_dicts(
            fetch_all(
                conn,
                """
                SELECT ae.provider, pal.relation_type, COUNT(*) AS count
                FROM paper_artifact_links pal
                JOIN artifact_entities ae
                  ON ae.artifact_id = pal.artifact_id
                GROUP BY ae.provider, pal.relation_type
                ORDER BY COUNT(*) DESC, ae.provider ASC, pal.relation_type ASC;
                """,
            ),
            ["provider", "relation_type", "count"],
        )

        sample_joined_links = rows_to_dicts(
            fetch_all(
                conn,
                """
                SELECT
                    cd.title,
                    ae.provider,
                    ae.artifact_type,
                    ae.normalized_url,
                    pal.relation_type,
                    pal.confidence
                FROM paper_artifact_links pal
                JOIN canonical_documents cd
                  ON cd.canonical_id = pal.canonical_id
                JOIN artifact_entities ae
                  ON ae.artifact_id = pal.artifact_id
                ORDER BY pal.confidence DESC, cd.title ASC
                LIMIT 20;
                """,
            ),
            ["title", "provider", "artifact_type", "normalized_url", "relation_type", "confidence"],
        )

        required_checks = {
            "canonical_documents_table_exists": table_exists_map["canonical_documents"],
            "artifact_entities_table_exists": table_exists_map["artifact_entities"],
            "artifact_observations_table_exists": table_exists_map["artifact_observations"],
            "paper_artifact_links_table_exists": table_exists_map["paper_artifact_links"],
            "canonical_documents_non_empty": canonical_documents_count > 0,
            "artifact_entities_non_empty": artifact_entities_count > 0,
            "artifact_observations_non_empty": artifact_observations_count > 0,
            "paper_artifact_links_non_empty": paper_artifact_links_count > 0,
            "paper_artifact_links_join_all_rows": (
                paper_artifact_links_count > 0
                and join_canonical_artifact_entities_count == paper_artifact_links_count
            ),
            "joined_canonical_documents_non_empty": join_canonical_documents_count > 0,
            "joined_artifact_entities_non_empty": join_artifact_entities_count > 0,
            "provider_distribution_non_empty": len(provider_distribution) > 0,
            "relation_distribution_non_empty": len(relation_distribution) > 0,
            "sample_joined_links_non_empty": len(sample_joined_links) > 0,
        }

        required_failed = [
            name
            for name, ok in required_checks.items()
            if not ok
        ]

        report.update(
            {
                "canonical_documents_count": canonical_documents_count,
                "artifact_entities_count": artifact_entities_count,
                "artifact_observations_count": artifact_observations_count,
                "paper_artifact_links_count": paper_artifact_links_count,
                "join_canonical_artifact_entities_count": join_canonical_artifact_entities_count,
                "join_canonical_documents_count": join_canonical_documents_count,
                "join_artifact_entities_count": join_artifact_entities_count,
                "provider_distribution": provider_distribution,
                "relation_distribution": relation_distribution,
                "provider_relation_distribution": provider_relation_distribution,
                "sample_joined_links": sample_joined_links,
                "required_checks": required_checks,
                "required_failed_count": len(required_failed),
                "required_failed_checks": required_failed,
                "ok": len(required_failed) == 0,
            }
        )

    finally:
        conn.close()

    latest_json = REPORT_DIR / "test_artifact_db_read_latest.json"
    latest_md = REPORT_DIR / "test_artifact_db_read_latest.md"
    history_json = HISTORY_DIR / f"test_artifact_db_read_{run_ts}.json"
    history_md = HISTORY_DIR / f"test_artifact_db_read_{run_ts}.md"

    write_json(latest_json, report)
    write_json(history_json, report)
    write_markdown(latest_md, report)
    write_markdown(history_md, report)

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")

    print(f"[CHECK] canonical_documents_count={report.get('canonical_documents_count')}")
    print(f"[CHECK] artifact_entities_count={report.get('artifact_entities_count')}")
    print(f"[CHECK] artifact_observations_count={report.get('artifact_observations_count')}")
    print(f"[CHECK] paper_artifact_links_count={report.get('paper_artifact_links_count')}")
    print(
        "[CHECK] join_canonical_artifact_entities_count="
        f"{report.get('join_canonical_artifact_entities_count')}"
    )
    print(f"[CHECK] join_canonical_documents_count={report.get('join_canonical_documents_count')}")
    print(f"[CHECK] join_artifact_entities_count={report.get('join_artifact_entities_count')}")
    print(f"[CHECK] required_failed_count={report.get('required_failed_count')}")
    print(f"[CHECK] required_failed_checks={report.get('required_failed_checks')}")
    print(f"[CHECK] ok={report.get('ok')}")

    if not report["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()