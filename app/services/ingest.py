"""
Пайплайн индексации для интервью-ассистента.

Источник: ``.docx`` файл с вопросами и ответами.
Коллекция обновляется только если исходный файл реально изменился.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.interview_docx import load_interview_qa
from app.services.qdrant_service import QdrantService
from app.services.vectorization import chunk_text

logger = logging.getLogger(__name__)

INTERVIEW_KIND = "interview_qa"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        logger.info("Файл состояния ingest не найден: %s", path)
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Не удалось прочитать файл состояния ingest: %s", path)
        return {}
    logger.info("Прочитано состояние ingest из %s: %s", path, state)
    return state


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Сохранено состояние ingest в %s: %s", path, state)


async def sync_interview_index(
    settings: Settings, qdrant: QdrantService
) -> dict[str, Any]:
    """
    Синхронизирует Qdrant-индекс с docx-файлом.

    Если хеш файла не изменился с прошлого успешного ingest — индексация пропускается.
    """
    source_path = Path(settings.interview_docx_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Файл не найден: {source_path}")

    state_path = Path(settings.ingest_state_path)
    current_hash = _sha256_file(source_path)
    old_state = _read_state(state_path)
    old_hash = old_state.get("doc_hash")

    if old_hash == current_hash:
        logger.info("Индексация пропущена: файл %s не изменился", source_path.name)
        return {
            "status": "skipped",
            "reason": "file_not_changed",
            "doc_hash": current_hash,
            "indexed_questions": old_state.get("indexed_questions", 0),
            "indexed_chunks": old_state.get("indexed_chunks", 0),
        }

    qa_items = load_interview_qa(source_path)
    if not qa_items:
        raise ValueError("В docx не удалось найти вопросы для индексации")

    chunk_payload_pairs: list[tuple[str, dict[str, Any]]] = []
    for qa in qa_items:
        chunks = chunk_text(
            qa.as_document,
            settings.vectorization_max_chunk_chars,
            settings.vectorization_overlap,
        )
        for chunk_index, chunk in enumerate(chunks):
            chunk_payload_pairs.append(
                (
                    chunk,
                    {
                        "kind": INTERVIEW_KIND,
                        "source_file": source_path.name,
                        "question_number": qa.number,
                        "question_text": qa.question,
                        "answer_number": qa.number,
                        "chunk_index": chunk_index,
                        "chunk_total": len(chunks),
                        "doc_hash": current_hash,
                    },
                )
            )

    old_doc_hash = old_state.get("doc_hash")
    await qdrant.upsert_chunks_with_payloads(chunk_payload_pairs)

    if old_doc_hash:
        await qdrant.delete_by_payload_kind(INTERVIEW_KIND, doc_hash=old_doc_hash)

    new_state = {
        "doc_hash": current_hash,
        "source_path": str(source_path),
        "indexed_questions": len(qa_items),
        "indexed_chunks": len(chunk_payload_pairs),
    }
    _write_state(state_path, new_state)
    logger.info(
        "Индекс обновлён из %s: вопросов=%s, фрагментов=%s, doc_hash=%s",
        source_path.name,
        len(qa_items),
        len(chunk_payload_pairs),
        current_hash,
    )
    return {"status": "updated", **new_state}
