from __future__ import annotations

from typing import Iterable, List

from radar_core.contracts.document import NormalizedDocument


def deduplicate_documents(documents: Iterable[NormalizedDocument]) -> List[NormalizedDocument]:
    """
    Дедупликация внутри одного прогона.
    Пока стратегия простая:
    - один doc_id -> одна запись
    - если doc_id совпал, оставляем последнюю запись
    """
    by_doc_id: dict[str, NormalizedDocument] = {}

    for doc in documents:
        by_doc_id[doc.doc_id] = doc

    return list(by_doc_id.values())


def split_new_vs_updated(
    documents: Iterable[NormalizedDocument],
    existing_content_hash_by_doc_id: dict[str, str],
) -> tuple[list[NormalizedDocument], list[NormalizedDocument], list[NormalizedDocument]]:
    """
    Возвращает:
    - new_docs
    - updated_docs
    - unchanged_docs
    """
    new_docs: list[NormalizedDocument] = []
    updated_docs: list[NormalizedDocument] = []
    unchanged_docs: list[NormalizedDocument] = []

    for doc in documents:
        old_hash = existing_content_hash_by_doc_id.get(doc.doc_id)

        if old_hash is None:
            new_docs.append(doc)
        elif old_hash != doc.content_hash:
            updated_docs.append(doc)
        else:
            unchanged_docs.append(doc)

    return new_docs, updated_docs, unchanged_docs