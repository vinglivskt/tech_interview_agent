"""
Точка входа HTTP: FastAPI-приложение для интервью-помощника с RAG.

При старте выполняется синхронизация индекса Qdrant с docx-файлом вопросов.
Фоновая задача периодически проверяет изменения файла и переиндексирует данные.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.chat_rag import run_chat
from app.services.ingest import sync_interview_index
from app.services.qdrant_service import QdrantService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionStore:
    def __init__(self, max_sessions: int, max_messages_per_session: int, ttl_seconds: int) -> None:
        self._max_sessions = max_sessions
        self._max_messages_per_session = max_messages_per_session
        self._ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, tuple[float, list[dict[str, str]]]] = OrderedDict()

    def _prune_expired(self) -> None:
        now = time.time()
        expired_keys = [
            session_id for session_id, (updated_at, _) in self._store.items() if now - updated_at > self._ttl_seconds
        ]
        for session_id in expired_keys:
            self._store.pop(session_id, None)

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        self._prune_expired()
        session = self._store.get(session_id)
        if session is None:
            return []
        _, history = session
        self._store.move_to_end(session_id)
        return list(history)

    def save_history(self, session_id: str, history: list[dict[str, str]]) -> None:
        self._prune_expired()
        self._store[session_id] = (
            time.time(),
            history[-self._max_messages_per_session :],
        )
        self._store.move_to_end(session_id)
        while len(self._store) > self._max_sessions:
            self._store.popitem(last=False)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Инициализация при запуске и корректное завершение фоновых задач.

    Сохраняет в ``app.state``: ``settings``, ``openai``, ``qdrant`` — используются
    в обработчиках через ``request.app.state``.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY не задан — чат и индексация недоступны")

    openai = AsyncOpenAI(api_key=settings.openai_api_key or "sk-placeholder")
    qdrant = QdrantService(settings, openai)

    if settings.openai_api_key:
        await qdrant.ensure_collection()
        try:
            state = await sync_interview_index(settings, qdrant)
            logger.info("Состояние индекса: %s", state)
        except Exception:
            logger.exception("Первая индексация docx не удалась")

    app.state.settings = settings
    app.state.openai = openai
    app.state.qdrant = qdrant
    app.state.sessions = SessionStore(
        max_sessions=settings.session_store_max_sessions,
        max_messages_per_session=settings.session_history_limit,
        ttl_seconds=60 * 60 * 12,
    )

    stop = asyncio.Event()

    async def periodic_ingest_loop() -> None:
        """Периодически проверяет изменения docx и обновляет индекс при необходимости."""
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=settings.ingest_interval_hours * 3600.0,
                )
            except TimeoutError:
                if not settings.openai_api_key:
                    continue
                try:
                    state = await sync_interview_index(settings, qdrant)
                    if state.get("status") == "updated":
                        logger.info("Индекс обновлён: %s", state)
                except Exception:
                    logger.exception("Периодическая индексация не удалась")

    task = asyncio.create_task(periodic_ingest_loop()) if settings.openai_api_key else None
    yield
    stop.set()
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await qdrant.close()
    await openai.close()


app = FastAPI(
    title="Interview Assistant RAG (Qdrant + OpenAI)",
    description="Личный помощник по подготовке к Python собеседованиям",
    lifespan=lifespan,
)

cors_allow_origins = [origin.strip() for origin in get_settings().cors_allow_origins if origin.strip()]
allow_all_origins = "*" in cors_allow_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else cors_allow_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health(request: Request) -> dict:
    """
    Проверка живости API и доступности Qdrant.

    Возвращает ``qdrant: true``, если HTTP-клиент успешно получил список коллекций.
    """
    q = request.app.state.qdrant
    q_ok = await q.ping()
    return {
        "status": "ok",
        "qdrant": q_ok,
        "openai_configured": bool(request.app.state.settings.openai_api_key),
    }


class ChatRequest(BaseModel):
    """Тело POST ``/api/chat``: один обязательный текст запроса."""

    message: str = Field(
        ..., min_length=1, max_length=get_settings().chat_max_message_length, description="Текст запроса пользователя"
    )
    session_id: str = Field(default="default", min_length=1, description="Идентификатор диалога")


@app.post("/api/chat")
async def chat(request: Request, body: ChatRequest) -> dict:
    """
    Чат с RAG: делегирует логику ``run_chat`` (function calling + поиск в Qdrant).

    При отсутствии ``OPENAI_API_KEY`` возвращает ``error`` и ``answer: null``.
    Успешный ответ: ``answer`` (строка), ``meta`` (``used_rag``, ``retrieved_chunks``, …).
    """
    settings = request.app.state.settings
    if not settings.openai_api_key:
        return {"error": "OPENAI_API_KEY не задан", "answer": None}

    sessions = request.app.state.sessions
    session_id = body.session_id.strip() or "default"
    message = body.message.strip()
    history = sessions.get_history(session_id)

    answer, meta = await run_chat(
        settings,
        request.app.state.openai,
        request.app.state.qdrant,
        message,
        history=history,
    )

    new_history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    sessions.save_history(session_id, new_history)
    return {"answer": answer, "meta": meta}


# Каталог со статикой лежит рядом с пакетом app (корень репозитория /static)
static_dir = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
async def index() -> FileResponse:
    """Отдаёт одностраничный фронт (форма чата)."""
    return FileResponse(static_dir / "index.html")
