"""
CLI-точка входа для ручного запуска индексации docx (``uv run ingest-interview``).
"""

from __future__ import annotations

import asyncio
import sys

from openai import AsyncOpenAI

from app.config import get_settings
from app.services.ingest import sync_interview_index
from app.services.qdrant_service import QdrantService


async def _run() -> None:
    """Создаёт клиентов, гарантирует коллекцию и запускает синхронизацию индекса."""
    settings = get_settings()
    if not settings.openai_api_key:
        print("Задайте OPENAI_API_KEY в окружении или .env", file=sys.stderr)
        sys.exit(1)
    openai = AsyncOpenAI(api_key=settings.openai_api_key)
    q = QdrantService(settings, openai)
    await q.ensure_collection()
    state = await sync_interview_index(settings, q)
    print(state)


def main() -> None:
    """Синхронная обёртка для ``asyncio.run`` (консольный скрипт)."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
