# tech_interview_agent/app/features/chat/domain/services.py
from __future__ import annotations

import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from src.core.interfaces.embeddings import EmbeddingGateway
from src.core.interfaces.llm import LLMGateway
from src.core.interfaces.vectorstore import VectorStoreGateway
from src.features.chat.domain.docx_repository import question_exists

_CJK_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")


def _resolve_system_prompt_path(settings: Any) -> Path:
    """
    Определяет путь к файлу системного промпта.
    Путь берётся из настройки system_prompt_path.
    :param settings: настройки приложения
    :return: абсолютный путь к файлу промпта
    """
    # Путь из настроек (по умолчанию /app/prompts/chat/system.md)
    prompt_path = getattr(settings, "system_prompt_path", None)
    if prompt_path:
        return Path(prompt_path)

    # Fallback: относительно корня проекта
    app_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
    return app_dir / "prompts" / "chat" / "system.md"


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
        ) from None
    except Exception as e:
        raise RuntimeError(f"Failed to load system prompt from {prompt_path}: {e}") from e


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

    # Выбираем один единственный номер ответа (первый из самых релевантных хитов)
    selected_number: int | None = None
    for hit in hits:
        an = hit.get("answer_number")
        if isinstance(an, int):
            selected_number = an
            break

    selected_hits = hits if selected_number is None else [h for h in hits if h.get("answer_number") == selected_number]

    numbers: list[int] = [selected_number] if selected_number is not None else []
    context_parts: list[str] = []
    for hit in selected_hits:
        text = str(hit.get("text", "")).strip()
        if not text:
            continue
        answer_number = hit.get("answer_number")
        label = f"[answer_number={answer_number}] " if answer_number is not None else ""
        context_parts.append(f"{label}{text}")

    refs = str(selected_number) if selected_number is not None else "нет"
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
        "Если используешь сведения из базы, укажи источник в формате 'ответ №N'. "
        "Используй только один источник и не объединяй ответы с разными номерами. "
        f"Найденный номер: {refs}."
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

    if selected_number is not None and "ответ №" not in text.lower():
        text = f"{text}\n\nИсточники: ответ №{selected_number}"

    # Проверяем, есть ли этот вопрос в базе docx
    # Если нет — предлагаем сохранить ответ
    docx_path = Path(getattr(settings, "interview_docx_path", ""))
    in_base = question_exists(docx_path, user_message) if docx_path.exists() else False

    # Парсим оценку из текста ассистента (если он её выставил) и определяем категорию
    # для статистики. Если пользователь явно отказался отвечать — score_percent=0.
    from src.features.chat.domain.scoring_parser import grade_user_response

    grade = grade_user_response(
        user_message=user_message,
        assistant_text=text,
        pass_threshold=int(getattr(settings, "sobes_pass_threshold_percent", 50)),
    )

    meta: dict[str, Any] = {
        "used_rag": bool(hits),
        "retrieved_chunks": len(selected_hits),
        "answer_numbers": numbers,
        "suggest_save": not in_base,
        "score_percent": grade["score_percent"],
        "category": grade["category"],
        "is_decline": grade["is_decline"],
        "has_grade": grade["has_grade"],
        "comprehension": grade["comprehension"],
        "depth": grade["depth"],
        "accuracy": grade["accuracy"],
        "level": grade["level"],
    }
    return text, meta
