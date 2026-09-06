"""FastAPI application entrypoint.

`main.py` contains FastAPI initialization, lifespan wiring,
router registration, and static file serving for the frontend.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.logger import configure_logging
from src.db.database import (
    create_all_tables,
    dispose_engine,
    init_engine,
    is_db_available,
)
from src.db.writer import seed_design_scenarios_from_file
from src.features.chat.api.router import router as chat_router
from src.features.chat.domain.ingest import sync_interview_index
from src.features.chat.domain.services import SessionStore
from src.features.chat.infrastructure.qdrant import QdrantService
from src.features.chat.providers.ollama import OllamaClient
from src.features.design.api.router import router as design_router
from src.features.quiz.api.router import router as quiz_router
from src.features.sobes.api.router import router as sobes_router
from src.features.stats.api.router import router as stats_router

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    llm = OllamaClient(settings)
    qdrant = QdrantService(settings, llm)

    if not await llm.ping():
        logger.warning("Ollama недоступна по %s", settings.ollama_url)

    try:
        await qdrant.ensure_collection()
    except Exception:
        # API всё ещё может отдавать случайные вопросы и конфигурацию без Qdrant.
        # RAG-запросы вернут понятную ошибку до восстановления сервиса.
        logger.exception("Не удалось подготовить коллекцию Qdrant")

    # --- PostgreSQL (user statistics) ---
    try:
        init_engine(settings)
        if getattr(settings, "database_auto_create", True):
            await create_all_tables()
        if not await is_db_available():
            logger.warning("PostgreSQL недоступна, эндпоинты статистики вернут 503")
        else:
            logger.info("PostgreSQL готова: статистика ответов активна")
    except Exception:
        logger.exception("Не удалось инициализировать БД (PostgreSQL). Статистика будет недоступна.")

    app.state.settings = settings
    app.state.llm = llm
    app.state.qdrant = qdrant
    app.state.sessions = SessionStore(
        max_sessions=settings.session_store_max_sessions,
        max_messages_per_session=settings.session_history_limit,
        ttl_seconds=60 * 60 * 12,
    )

    stop = asyncio.Event()

    async def initial_ingest() -> None:
        """Первичная индексация не должна задерживать готовность HTTP API."""
        try:
            state = await sync_interview_index(settings, qdrant)
            logger.info("Состояние начальной индексации: %s", state)
        except Exception:
            logger.exception("Первая индексация docx не удалась")

        # Сид библиотеки сценариев системного дизайна в PostgreSQL
        try:
            library_path = getattr(settings, "design_library_path", "prompts/design/library.yaml")
            inserted = await seed_design_scenarios_from_file(library_path)
            logger.info("Сид библиотеки дизайна: обновлено строк=%s (path=%s)", inserted, library_path)
        except Exception:
            logger.exception("Сид библиотеки дизайна не удался")

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

    initial_ingest_task = asyncio.create_task(initial_ingest())
    task = asyncio.create_task(periodic_ingest_loop())
    yield
    stop.set()
    for background_task in (initial_ingest_task, task):
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass

    await qdrant.close()
    await llm.close()
    await dispose_engine()


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
app.include_router(sobes_router, prefix="/api")
app.include_router(design_router, prefix="/api")
app.include_router(stats_router, prefix="/api")

# Frontend is served by a separate service (see docker-compose.yml)
# CORS allows the frontend at http://localhost:3000 to call /api/*
