from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_PATH = PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
NORMALIZED_DIR = PROJECT_ROOT / "data" / "normalized"

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 15432,
    "dbname": "ml_radar",
    "user": "ml_radar",
    "password": "ml_radar_dev",
}


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else None, ensure_ascii=False)


def canonical_row(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": doc.get("canonical_id"),
        "reconciliation_key": doc.get("reconciliation_key"),
        "document_type": doc.get("document_type"),
        "title": doc.get("title"),
        "abstract": doc.get("abstract"),
        "year": doc.get("year"),
        "published_at": doc.get("published_at"),
        "publication_date": doc.get("publication_date"),
        "updated_record_at": doc.get("updated_record_at"),
        "doi": doc.get("doi"),
        "arxiv_id": doc.get("arxiv_id"),
        "openalex_id": doc.get("openalex_id"),
        "pmid": doc.get("pmid"),
        "pmcid": doc.get("pmcid"),
        "semantic_scholar_id": doc.get("semantic_scholar_id"),
        "dblp_id": doc.get("dblp_id"),
        "mag_id": doc.get("mag_id"),
        "journal_ref": doc.get("journal_ref"),
        "comment": doc.get("comment"),
        "venue": doc.get("venue"),
        "journal": doc.get("journal"),
        "conference": doc.get("conference"),
        "publisher": doc.get("publisher"),
        "publication_type": doc.get("publication_type"),
        "language": doc.get("language"),
        "landing_page_url": doc.get("landing_page_url"),
        "pdf_url": doc.get("pdf_url"),
        "repo_url": doc.get("repo_url"),
        "license": doc.get("license"),
        "open_access": doc.get("open_access"),
        "is_open_access": doc.get("is_open_access"),
        "is_preprint": doc.get("is_preprint"),
        "is_review": doc.get("is_review"),
        "is_survey": doc.get("is_survey"),
        "is_withdrawn": doc.get("is_withdrawn"),
        "citation_graph_available": doc.get("citation_graph_available"),
        "has_code_link": doc.get("has_code_link"),
        "has_dataset_link": doc.get("has_dataset_link"),
        "has_model_link": doc.get("has_model_link"),
        "has_pdf": doc.get("has_pdf"),
        "cited_by_count": doc.get("cited_by_count"),
        "references_count": doc.get("references_count"),
        "source_count": doc.get("source_count"),
        "unique_source_count": doc.get("unique_source_count"),
        "metadata_completeness_score": doc.get("metadata_completeness_score"),
        "authors": json_dumps(doc.get("authors", [])),
        "source_ids": json_dumps(doc.get("source_ids", {})),
        "external_ids": json_dumps(doc.get("external_ids", {})),
        "categories": json_dumps(doc.get("categories", [])),
        "concepts": json_dumps(doc.get("concepts", [])),
        "keywords": json_dumps(doc.get("keywords", [])),
        "tags": json_dumps(doc.get("tags", [])),
        "referenced_ids": json_dumps(doc.get("referenced_ids", [])),
        "referenced_dois": json_dumps(doc.get("referenced_dois", [])),
        "referenced_arxiv_ids": json_dumps(doc.get("referenced_arxiv_ids", [])),
        "code_links": json_dumps(doc.get("code_links", [])),
        "dataset_links": json_dumps(doc.get("dataset_links", [])),
        "model_links": json_dumps(doc.get("model_links", [])),
        "doc_ids": json_dumps(doc.get("doc_ids", [])),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_record_at") or doc.get("updated_at"),
    }


def source_row(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": doc.get("doc_id"),
        "source": doc.get("source"),
        "source_id": doc.get("source_id"),
        "source_record_id": doc.get("source_record_id"),
        "source_record_url": doc.get("source_record_url"),
        "source_api_url": doc.get("source_api_url"),
        "canonical_url": doc.get("canonical_url"),
        "content_hash": doc.get("content_hash"),
        "document_type": doc.get("document_type"),
        "doi": doc.get("doi"),
        "arxiv_id": doc.get("arxiv_id"),
        "openalex_id": doc.get("openalex_id"),
        "pmid": doc.get("pmid"),
        "pmcid": doc.get("pmcid"),
        "semantic_scholar_id": doc.get("semantic_scholar_id"),
        "dblp_id": doc.get("dblp_id"),
        "mag_id": doc.get("mag_id"),
        "title": doc.get("title"),
        "abstract": doc.get("abstract"),
        "year": doc.get("year"),
        "published_at": doc.get("published_at"),
        "publication_date": doc.get("publication_date"),
        "updated_source_at": doc.get("updated_source_at"),
        "landing_page_url": doc.get("landing_page_url"),
        "pdf_url": doc.get("pdf_url"),
        "repo_url": doc.get("repo_url"),
        "license": doc.get("license"),
        "open_access": doc.get("open_access"),
        "primary_category": doc.get("primary_category"),
        "comment": doc.get("comment"),
        "journal_ref": doc.get("journal_ref"),
        "venue": doc.get("venue"),
        "journal": doc.get("journal"),
        "conference": doc.get("conference"),
        "publisher": doc.get("publisher"),
        "publication_type": doc.get("publication_type"),
        "language": doc.get("language"),
        "cited_by_count": doc.get("cited_by_count"),
        "references_count": doc.get("references_count"),
        "citation_graph_available": doc.get("citation_graph_available"),
        "has_code_link": doc.get("has_code_link"),
        "has_dataset_link": doc.get("has_dataset_link"),
        "has_model_link": doc.get("has_model_link"),
        "has_pdf": doc.get("has_pdf"),
        "is_withdrawn": doc.get("is_withdrawn"),
        "is_open_access": doc.get("is_open_access"),
        "is_preprint": doc.get("is_preprint"),
        "is_review": doc.get("is_review"),
        "is_survey": doc.get("is_survey"),
        "raw_artifact_path": doc.get("raw_artifact_path"),
        "raw_source_name": doc.get("raw_source_name"),
        "ingested_at": doc.get("ingested_at"),
        "metadata_completeness_score": doc.get("metadata_completeness_score"),
        "pipeline_version": doc.get("pipeline_version"),
        "authors": json_dumps(doc.get("authors", [])),
        "source_ids": json_dumps(doc.get("source_ids", {})),
        "external_ids": json_dumps(doc.get("external_ids", {})),
        "categories": json_dumps(doc.get("categories", [])),
        "concepts": json_dumps(doc.get("concepts", [])),
        "keywords": json_dumps(doc.get("keywords", [])),
        "tags": json_dumps(doc.get("tags", [])),
        "referenced_ids": json_dumps(doc.get("referenced_ids", [])),
        "referenced_dois": json_dumps(doc.get("referenced_dois", [])),
        "referenced_arxiv_ids": json_dumps(doc.get("referenced_arxiv_ids", [])),
        "code_links": json_dumps(doc.get("code_links", [])),
        "dataset_links": json_dumps(doc.get("dataset_links", [])),
        "model_links": json_dumps(doc.get("model_links", [])),
        "stages": json_dumps(doc.get("stages", [])),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def insert_canonical(cur: psycopg.Cursor, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO canonical_documents (
            canonical_id, reconciliation_key, document_type, title, abstract,
            year, published_at, publication_date, updated_record_at,
            doi, arxiv_id, openalex_id, pmid, pmcid, semantic_scholar_id, dblp_id, mag_id,
            journal_ref, comment, venue, journal, conference, publisher, publication_type, language,
            landing_page_url, pdf_url, repo_url, license,
            open_access, is_open_access, is_preprint, is_review, is_survey, is_withdrawn,
            citation_graph_available, has_code_link, has_dataset_link, has_model_link, has_pdf,
            cited_by_count, references_count, source_count, unique_source_count, metadata_completeness_score,
            authors, source_ids, external_ids, categories, concepts, keywords, tags,
            referenced_ids, referenced_dois, referenced_arxiv_ids,
            code_links, dataset_links, model_links, doc_ids,
            created_at, updated_at
        )
        VALUES (
            %(canonical_id)s, %(reconciliation_key)s, %(document_type)s, %(title)s, %(abstract)s,
            %(year)s, %(published_at)s, %(publication_date)s, %(updated_record_at)s,
            %(doi)s, %(arxiv_id)s, %(openalex_id)s, %(pmid)s, %(pmcid)s, %(semantic_scholar_id)s, %(dblp_id)s, %(mag_id)s,
            %(journal_ref)s, %(comment)s, %(venue)s, %(journal)s, %(conference)s, %(publisher)s, %(publication_type)s, %(language)s,
            %(landing_page_url)s, %(pdf_url)s, %(repo_url)s, %(license)s,
            %(open_access)s, %(is_open_access)s, %(is_preprint)s, %(is_review)s, %(is_survey)s, %(is_withdrawn)s,
            %(citation_graph_available)s, %(has_code_link)s, %(has_dataset_link)s, %(has_model_link)s, %(has_pdf)s,
            %(cited_by_count)s, %(references_count)s, %(source_count)s, %(unique_source_count)s, %(metadata_completeness_score)s,
            %(authors)s::jsonb, %(source_ids)s::jsonb, %(external_ids)s::jsonb, %(categories)s::jsonb, %(concepts)s::jsonb, %(keywords)s::jsonb, %(tags)s::jsonb,
            %(referenced_ids)s::jsonb, %(referenced_dois)s::jsonb, %(referenced_arxiv_ids)s::jsonb,
            %(code_links)s::jsonb, %(dataset_links)s::jsonb, %(model_links)s::jsonb, %(doc_ids)s::jsonb,
            %(created_at)s, %(updated_at)s
        )
        ON CONFLICT (canonical_id) DO UPDATE SET
            title = EXCLUDED.title,
            abstract = EXCLUDED.abstract,
            updated_at = EXCLUDED.updated_at,
            metadata_completeness_score = EXCLUDED.metadata_completeness_score
        """,
        row,
    )


def insert_source(cur: psycopg.Cursor, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO source_documents (
            doc_id, source, source_id, source_record_id, source_record_url, source_api_url, canonical_url,
            content_hash, document_type,
            doi, arxiv_id, openalex_id, pmid, pmcid, semantic_scholar_id, dblp_id, mag_id,
            title, abstract, year, published_at, publication_date, updated_source_at,
            landing_page_url, pdf_url, repo_url, license,
            open_access, primary_category, comment, journal_ref, venue, journal, conference, publisher, publication_type, language,
            cited_by_count, references_count,
            citation_graph_available, has_code_link, has_dataset_link, has_model_link, has_pdf,
            is_withdrawn, is_open_access, is_preprint, is_review, is_survey,
            raw_artifact_path, raw_source_name, ingested_at, metadata_completeness_score, pipeline_version,
            authors, source_ids, external_ids, categories, concepts, keywords, tags,
            referenced_ids, referenced_dois, referenced_arxiv_ids,
            code_links, dataset_links, model_links, stages,
            created_at, updated_at
        )
        VALUES (
            %(doc_id)s, %(source)s, %(source_id)s, %(source_record_id)s, %(source_record_url)s, %(source_api_url)s, %(canonical_url)s,
            %(content_hash)s, %(document_type)s,
            %(doi)s, %(arxiv_id)s, %(openalex_id)s, %(pmid)s, %(pmcid)s, %(semantic_scholar_id)s, %(dblp_id)s, %(mag_id)s,
            %(title)s, %(abstract)s, %(year)s, %(published_at)s, %(publication_date)s, %(updated_source_at)s,
            %(landing_page_url)s, %(pdf_url)s, %(repo_url)s, %(license)s,
            %(open_access)s, %(primary_category)s, %(comment)s, %(journal_ref)s, %(venue)s, %(journal)s, %(conference)s, %(publisher)s, %(publication_type)s, %(language)s,
            %(cited_by_count)s, %(references_count)s,
            %(citation_graph_available)s, %(has_code_link)s, %(has_dataset_link)s, %(has_model_link)s, %(has_pdf)s,
            %(is_withdrawn)s, %(is_open_access)s, %(is_preprint)s, %(is_review)s, %(is_survey)s,
            %(raw_artifact_path)s, %(raw_source_name)s, %(ingested_at)s, %(metadata_completeness_score)s, %(pipeline_version)s,
            %(authors)s::jsonb, %(source_ids)s::jsonb, %(external_ids)s::jsonb, %(categories)s::jsonb, %(concepts)s::jsonb, %(keywords)s::jsonb, %(tags)s::jsonb,
            %(referenced_ids)s::jsonb, %(referenced_dois)s::jsonb, %(referenced_arxiv_ids)s::jsonb,
            %(code_links)s::jsonb, %(dataset_links)s::jsonb, %(model_links)s::jsonb, %(stages)s::jsonb,
            %(created_at)s, %(updated_at)s
        )
        ON CONFLICT (doc_id) DO UPDATE SET
            title = EXCLUDED.title,
            abstract = EXCLUDED.abstract,
            updated_at = EXCLUDED.updated_at,
            content_hash = EXCLUDED.content_hash
        """,
        row,
    )


def insert_link(cur: psycopg.Cursor, canonical_id: str, link: dict[str, Any]) -> None:
    source = link.get("source")
    source_id = link.get("source_id")

    doc_id = None
    if source == "arxiv":
        source_record_url = link.get("source_record_url")
        if source_record_url:
            cur.execute(
                """
                SELECT doc_id
                FROM source_documents
                WHERE source = %s AND source_record_url = %s
                LIMIT 1
                """,
                (source, source_record_url),
            )
            row = cur.fetchone()
            if row:
                doc_id = row[0]

    cur.execute(
        """
        INSERT INTO canonical_source_links (
            canonical_id, doc_id, source, source_id, source_record_id, source_record_url,
            canonical_url, fetched_at, source_updated_at, source_api_url, raw_source_name, run_ts
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        """,
        (
            canonical_id,
            doc_id,
            source,
            source_id,
            link.get("source_record_id"),
            link.get("source_record_url"),
            link.get("canonical_url"),
            link.get("fetched_at"),
            link.get("source_updated_at"),
            link.get("source_api_url"),
            link.get("raw_source_name"),
            link.get("run_ts"),
        ),
    )


def insert_references(cur: psycopg.Cursor, canonical_id: str, doc: dict[str, Any]) -> None:
    for value in doc.get("referenced_dois", []):
        cur.execute(
            "INSERT INTO document_references (canonical_id, reference_type, reference_value) VALUES (%s, %s, %s)",
            (canonical_id, "doi", value),
        )
    for value in doc.get("referenced_arxiv_ids", []):
        cur.execute(
            "INSERT INTO document_references (canonical_id, reference_type, reference_value) VALUES (%s, %s, %s)",
            (canonical_id, "arxiv", value),
        )
    for value in doc.get("referenced_ids", []):
        cur.execute(
            "INSERT INTO document_references (canonical_id, reference_type, reference_value) VALUES (%s, %s, %s)",
            (canonical_id, "generic", value),
        )


def iter_normalized_files() -> Iterable[Path]:
    for source_dir in NORMALIZED_DIR.iterdir():
        if not source_dir.is_dir():
            continue
        for path in source_dir.glob("*.jsonl"):
            yield path


def main() -> None:
    if not CANONICAL_PATH.exists():
        raise FileNotFoundError(f"Canonical file not found: {CANONICAL_PATH}")

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            print("Loading source documents...")
            source_count = 0
            for path in iter_normalized_files():
                for doc in read_jsonl(path):
                    insert_source(cur, source_row(doc))
                    source_count += 1
            print(f"Inserted/updated source docs: {source_count}")

            print("Loading canonical documents...")
            canonical_count = 0
            link_count = 0
            ref_count = 0

            for doc in read_jsonl(CANONICAL_PATH):
                insert_canonical(cur, canonical_row(doc))
                canonical_id = doc["canonical_id"]

                cur.execute("DELETE FROM canonical_source_links WHERE canonical_id = %s", (canonical_id,))
                cur.execute("DELETE FROM document_references WHERE canonical_id = %s", (canonical_id,))

                for link in doc.get("sources", []):
                    insert_link(cur, canonical_id, link)
                    link_count += 1

                before = ref_count
                insert_references(cur, canonical_id, doc)
                ref_count += (
                    len(doc.get("referenced_dois", []))
                    + len(doc.get("referenced_arxiv_ids", []))
                    + len(doc.get("referenced_ids", []))
                )

                canonical_count += 1

            cur.execute(
                """
                INSERT INTO export_runs (run_type, source_path, status, finished_at, details)
                VALUES (%s, %s, %s, NOW(), %s::jsonb)
                """,
                (
                    "postgres_v1_export",
                    str(PROJECT_ROOT / "data"),
                    "SUCCESS",
                    json.dumps(
                        {
                            "source_documents": source_count,
                            "canonical_documents": canonical_count,
                            "canonical_source_links": link_count,
                            "document_references": ref_count,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )

        conn.commit()

    print("Export completed successfully.")


if __name__ == "__main__":
    main()