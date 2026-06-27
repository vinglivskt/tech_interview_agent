# tech_interview_agent/app/features/chat/domain/services.py
from __future__ import annotations

import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from app.core.interfaces.embeddings import EmbeddingGateway
from app.core.interfaces.llm import LLMGateway
from app.core.interfaces.vectorstore import VectorStoreGateway
from app.features.chat.domain.docx_repository import question_exists

_CJK_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")


def _resolve_system_prompt_path(settings: Any) -> Path:
    """
    Определяет путь к файлу системного промпта.
    Приоритет: настройка system_prompt_path > переменная окружения SYSTEM_PROMPT_PATH >
    путь относительно корня проекта (prompts/system_prompt.md).
    :param settings: настройки приложения
    :return: абсолютный путь к файлу промпта
    """
    import os

    # 1. Явный путь из настроек
    prompt_path = getattr(settings, "system_prompt_path", None)
    if prompt_path:
        return Path(prompt_path)

    # 2. Переменная окружения
    env_path = os.environ.get("SYSTEM_PROMPT_PATH")
    if env_path:
        return Path(env_path)

    # 3. Относительно корня проекта
    # В Docker: /app/prompts/system_prompt.md
    # Локально: <repo_root>/prompts/system_prompt.md
    app_dir = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [
        app_dir / "prompts" / "system_prompt.md",  # Docker (/app/prompts/)
        app_dir.parent / "prompts" / "system_prompt.md",  # локально (<repo>/prompts/)
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Если не нашли — возвращаем путь по умолчанию (для сообщения об ошибке)
    return candidates[0]


def _load_system_prompt(settings: Any) -> str:
    """
    Загружает системный промпт из markdown-файла.
    Путь определяется относительно корня проекта.
    :param settings: настройки приложения
    :return: содержимое файла промпта
    """
    prompt_path = _resolve_system_prompt_path(settings)
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"System prompt file not found: {prompt_path}. "
            "Please ensure prompts/system_prompt.md exists in the project root."
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load system prompt from {prompt_path}: {e}")


def _build_history_messages(
    history: list[dict[str, str]] | None,
    limit: int = 12,
) -> list[dict[str, str]]:
    """
    Преобразует историю сообщений в формат для LLM (ограничивает по количеству).
    :param history: список сообщений
    :param limit: максимальное число сообщений
    :return: список сообщений для LLM
    """
    if not history:
        return []

    messages: list[dict[str, str]] = []
    for item in history[-limit:]:
        role = item.get("role", "")
        content = (item.get("content", "") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append({"role": "user", "content": content})
        elif role == "assistant":
            messages.append({"role": "assistant", "content": content})
    return messages


class SessionStore:
    """
    Хранилище истории диалогов в памяти (TTL‑кеш).
    Позволяет ограничивать число сессий, сообщений и время жизни.
    """

    def __init__(self, max_sessions: int, max_messages_per_session: int, ttl_seconds: int) -> None:
        self.max_sessions = max_sessions
        self.max_messages_per_session = max_messages_per_session
        self.ttl = ttl_seconds
        self.store: OrderedDict[str, tuple[float, list[dict[str, str]]]] = OrderedDict()

    def _prune(self) -> None:
        now = time.time()
        expired = [sid for sid, (ts, _) in self.store.items() if now - ts > self.ttl]
        for sid in expired:
            self.store.pop(sid, None)

    def get(self, session_id: str) -> list[dict[str, str]]:
        self._prune()
        entry = self.store.get(session_id)
        return list(entry[1]) if entry else []

    def save(self, session_id: str, history: list[dict[str, str]]) -> None:
        self._prune()
        self.store[session_id] = (time.time(), history[-self.max_messages_per_session :])
        self.store.move_to_end(session_id)
        while len(self.store) > self.max_sessions:
            self.store.popitem(last=False)


async def run_chat(
    settings: Any,
    llm: LLMGateway,
    vectorstore: VectorStoreGateway,
    user_message: str,
    history: list[dict[str, str]] | None = None,
    history_limit: int | None = None,
    *,
    embedder: EmbeddingGateway | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Основная функция общения с ассистентом с использованием RAG.
    1. Получает эмбеддинг запроса и ищет релевантные фрагменты в Qdrant.
    2. Формирует system_prompt с контекстом.
    3. Вызывает LLM для генерации ответа.
    4. Возвращает ответ и метаинформацию (использовался ли RAG, номера ответов и т.д.).
    :param settings: настройки приложения
    :param llm: шлюз к LLM
    :param vectorstore: шлюз к векторному хранилищу
    :param user_message: сообщение пользователя
    :param history: история диалога
    :param history_limit: лимит истории
    :param embedder: шлюз к эмбеддингам
    :return: ответ ассистента и метаинформация
    """

    top_k = getattr(settings, "interview_top_k", 5)
    hits: list[dict[str, Any]] = []

    try:
        if embedder is not None:
            query_vec = (await embedder.embed([user_message]))[0]
            hits = await vectorstore.search(query_vec, top_k=top_k)
        else:
            # fallback for vectorstore implementations that expose legacy helper
            if hasattr(vectorstore, "search_payload"):
                hits = await vectorstore.search_payload(user_message, limit=top_k)  # type: ignore[attr-defined]
    except Exception:
        hits = []

    numbers: list[int] = []
    context_parts: list[str] = []
    for hit in hits:
        text = str(hit.get("text", "")).strip()
        answer_number = hit.get("answer_number")
        if isinstance(answer_number, int):
            numbers.append(answer_number)
        if text:
            label = f"[answer_number={answer_number}] " if answer_number is not None else ""
            context_parts.append(f"{label}{text}")

    unique_numbers = sorted(set(numbers))
    refs = ", ".join(str(number) for number in unique_numbers) if unique_numbers else "нет"
    rag_context = (
        "\n\n---\n\n".join(context_parts)
        if context_parts
        else "(в базе пока нет подходящих фрагментов — ответь аккуратно и без выдуманных ссылок)"
    )

    # Load system prompt from markdown file
    base_prompt = _load_system_prompt(settings)
    system_prompt = (
        f"{base_prompt}\n\n"
        "Контекст из векторной базы:\n"
        f"{rag_context}\n\n"
        "Если используешь сведения из базы, обязательно укажи источник(и) "
        f"в формате 'ответ №N'. Найденные номера: {refs}."
    )

    effective_limit = history_limit if history_limit is not None else getattr(settings, "session_history_limit", 20)

    messages = [
        {"role": "system", "content": system_prompt},
        *_build_history_messages(history, limit=effective_limit),
        {"role": "user", "content": user_message.strip()},
    ]

    text = (await llm.generate(messages)).strip()

    if _CJK_RE.search(text):
        messages.append(
            {
                "role": "user",
                "content": "Переформулируй предыдущий ответ полностью на русском языке без иностранных вставок.",
            }
        )
        text = (await llm.generate(messages)).strip()

    if unique_numbers and "ответ №" not in text.lower() and "ответы №" not in text.lower():
        refs_suffix = ", ".join(str(number) for number in unique_numbers)
        text = f"{text}\n\nИсточники: ответы №{refs_suffix}"

    # Проверяем, есть ли этот вопрос в базе docx
    # Если нет — предлагаем сохранить ответ
    docx_path = Path(getattr(settings, "interview_docx_path", ""))
    in_base = question_exists(docx_path, user_message) if docx_path.exists() else False

    meta: dict[str, Any] = {
        "used_rag": bool(hits),
        "retrieved_chunks": len(hits),
        "answer_numbers": unique_numbers,
        "suggest_save": not in_base,
    }
    return text, meta
