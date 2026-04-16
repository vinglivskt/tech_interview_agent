"""
CLI-точка входа для ручного запуска индексации docx (``uv run ingest-interview``).
"""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.services.ingest import sync_interview_index
from app.services.llm import OllamaClient
from app.services.qdrant_service import QdrantService


async def _run() -> None:
    """Создаёт клиентов, гарантирует коллекцию и запускает синхронизацию индекса."""
    settings = get_settings()
    llm = OllamaClient(settings)
    q = QdrantService(settings, llm)
    await q.ensure_collection()
    state = await sync_interview_index(settings, q)
    print(state)
    await llm.close()


def main() -> None:
    """Синхронная обёртка для ``asyncio.run`` (консольный скрипт)."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
