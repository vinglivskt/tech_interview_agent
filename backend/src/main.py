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
from httpx import ConnectError, ConnectTimeout

from src.core.config import get_settings
from src.core.interfaces.embeddings import EmbeddingGateway
from src.core.interfaces.llm import LLMGateway
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
from src.features.chat.providers.composite import CompositeLLMClient
from src.features.chat.providers.ollama import OllamaClient
from src.features.chat.providers.opencode import OpenCodeClient
from src.features.design.api.router import router as design_router
from src.features.design.domain.graph import create_design_checkpointer
from src.features.quiz.api.router import router as quiz_router
from src.features.sobes.api.router import router as sobes_router
from src.features.stats.api.router import router as stats_router

configure_logging()
logger = logging.getLogger(__name__)

_INGEST_UNAVAILABLE_HINT = (
    "Индексация docx пропущена: не работает провайдер эмбеддингов (Ollama по %s). "
    "Генерация через OpenCode Zen продолжит работать, но RAG-поиск и индексация "
    "не появятся до запуска Ollama."
)


def _log_ingest_failure(exc: Exception, *, phase: str, ollama_url: str) -> None:
    """Логирует сбой индексации, разделяя ожидаемый и неожиданный случаи.

    Недоступность Ollama — это состояние конфигурации, о котором уже сообщено
    при старте. Дублировать его многокадровым traceback не нужно: он только
    забивает лог и прячет реальные ошибки. Неожиданные сбои по-прежнему
    логируются с полным traceback.
    """
    if isinstance(exc, (ConnectError, ConnectTimeout)):
        logger.warning(_INGEST_UNAVAILABLE_HINT, ollama_url)
    else:
        logger.exception("%s: %s", phase, exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # --- Провайдер генерации LLM ---
    llm: LLMGateway
    if settings.llm_provider == "opencode":
        llm = OpenCodeClient(settings)
        if not await llm.ping():
            logger.warning("OpenCode Zen недоступен по %s", settings.opencode_url)
    else:
        ollama_llm = OllamaClient(settings)
        if await ollama_llm.ping():
            llm = ollama_llm
        else:
            logger.warning(
                "Ollama недоступна по %s — переключаю генерацию на OpenCode Zen (%s)",
                settings.ollama_url,
                settings.opencode_model,
            )
            await ollama_llm.close()
            llm = OpenCodeClient(settings)

    # --- Провайдер эмбеддингов (всегда Ollama: у Zen нет /embeddings) ---
    embeddings_available = True
    if isinstance(llm, OllamaClient):
        embedder: EmbeddingGateway = llm
    else:
        embedder = OllamaClient(settings)
        if not await embedder.ping():
            embeddings_available = False
            logger.error(
                "Ollama недоступна (%s) — эмбеддингов не будет: RAG-поиск и индексация "
                "docx не заработают. Zen эмбеддинги не отдаёт. Запустите Ollama.",
                settings.ollama_url,
            )

    client = CompositeLLMClient(llm, embedder)
    qdrant = QdrantService(settings, client)

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
    app.state.llm = client
    app.state.qdrant = qdrant
    app.state.sessions = SessionStore(
        max_sessions=settings.session_store_max_sessions,
        max_messages_per_session=settings.session_history_limit,
        ttl_seconds=60 * 60 * 12,
    )

    # LangGraph-чекпоинтер режима «Системный дизайн» (postgres с фолбэком на memory)
    try:
        design_checkpointer, design_checkpointer_close = await create_design_checkpointer(settings)
    except Exception:
        logger.exception("Не удалось создать чекпоинтер дизайна")
        from langgraph.checkpoint.memory import MemorySaver

        design_checkpointer, design_checkpointer_close = MemorySaver(), None
    app.state.design_checkpointer = design_checkpointer

    stop = asyncio.Event()

    async def initial_ingest() -> None:
        """Первичная индексация не должна задерживать готовность HTTP API."""
        try:
            state = await sync_interview_index(settings, qdrant)
            logger.info("Состояние начальной индексации: %s", state)
        except Exception as exc:
            if embeddings_available:
                _log_ingest_failure(
                    exc, phase="Первая индексация docx не удалась", ollama_url=settings.ollama_url
                )
            else:
                logger.warning(_INGEST_UNAVAILABLE_HINT, settings.ollama_url)

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
                except Exception as exc:
                    _log_ingest_failure(
                        exc,
                        phase="Периодическая индексация не удалась",
                        ollama_url=settings.ollama_url,
                    )

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
    await client.close()
    if design_checkpointer_close is not None:
        try:
            await design_checkpointer_close()
        except Exception:
            logger.exception("Ошибка при закрытии чекпоинтера дизайна")
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
