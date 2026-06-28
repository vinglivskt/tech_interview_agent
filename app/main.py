"""FastAPI application entrypoint.

VSA migration: `main.py` contains only FastAPI initialization, lifespan wiring,
router registration and static file serving.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.logger import configure_logging
from app.features.chat.api.router import router as chat_router
from app.features.chat.domain.ingest import sync_interview_index
from app.features.chat.domain.services import SessionStore
from app.features.chat.infrastructure.qdrant import QdrantService
from app.features.chat.providers.ollama import OllamaClient
from app.features.quiz.api.router import router as quiz_router

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    llm = OllamaClient(settings)
    qdrant = QdrantService(settings, llm)

    if not await llm.ping():
        logger.warning("Ollama недоступна по %s", settings.ollama_url)

    await qdrant.ensure_collection()

    try:
        state = await sync_interview_index(settings, qdrant)
        logger.info("Состояние индекса: %s", state)
    except Exception:
        # В docker-compose Ollama может быть не поднята/недоступна.
        # Не валим приложение на старте: чат/health должны продолжить работать,
        # а индексация повторится по расписанию.
        logger.exception("Первая индексация docx не удалась")

    app.state.settings = settings
    app.state.llm = llm
    app.state.qdrant = qdrant
    app.state.sessions = SessionStore(
        max_sessions=settings.session_store_max_sessions,
        max_messages_per_session=settings.session_history_limit,
        ttl_seconds=60 * 60 * 12,
    )

    stop = asyncio.Event()

    async def periodic_ingest_loop() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=settings.ingest_interval_hours * 3600.0,
                )
            except TimeoutError:
                try:
                    state = await sync_interview_index(settings, qdrant)
                    if state.get("status") == "updated":
                        logger.info("Индекс обновлён: %s", state)
                except Exception:
                    logger.exception("Периодическая индексация не удалась")

    task = asyncio.create_task(periodic_ingest_loop())
    yield
    stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    await qdrant.close()
    await llm.close()


app = FastAPI(
    title="Interview Assistant RAG (Qdrant + Ollama)",
    description="Личный помощник по подготовке к Python собеседованиям",
    lifespan=lifespan,
)

# CORS
cors_allow_origins = [origin.strip() for origin in get_settings().cors_allow_origins if origin.strip()]
allow_all_origins = "*" in cors_allow_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else cors_allow_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat_router, prefix="/api")
app.include_router(quiz_router, prefix="/api")

# Static
static_dir = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")
