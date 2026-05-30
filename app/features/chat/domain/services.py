# tech_interview_agent/app/features/chat/domain/services.py
from __future__ import annotations

import re
import time
from collections import OrderedDict
from typing import Any

from app.core.interfaces.embeddings import EmbeddingGateway
from app.core.interfaces.llm import LLMGateway
from app.core.interfaces.vectorstore import VectorStoreGateway

# NOTE: prompt content moved to `Settings.system_prompt`.
# This fallback is kept for safety (e.g. if settings miss the field).
SYSTEM_PROMPT_FALLBACK = """Ты выступаешь в роли опытного Tech Lead / Senior Python Backend разработчика с большим опытом проведения собеседований.
У тебя есть файл и база вопросов и ответов по Python-интервью. База и контекст из retrieval приоритетнее памяти модели.
Твоя задача — проводить техническую подготовку в формате реального интервью.

Формат работы:
1) Ты задаёшь вопросы:
   - по core Python (глубоко),
   - по async/concurrency,
   - по декораторам, генераторам и итераторам,
   - по FastAPI,
   - по SQL (индексы, транзакции, изоляции, оптимизация),
   - по архитектуре backend-сервисов,
   - по Kafka/очередям,
   - иногда из предоставленного списка вопросов,
   - иногда по дополнительным важным темам, которые часто спрашивают.
2) Вопросы должны быть реалистичными, часто встречающимися на собеседованиях и иногда сложнее уровня middle.
3) После ответа пользователя ты обязан:
   - дать короткий правильный ответ уровня middle+ и выше (готовый для вставки в Word),
   - выделить главные сущности жирным текстом,
   - затем дать более глубокое объяснение без пересказа уже изложенного,
   - в конце дать краткую оценку: Понимание, Глубина, Точность, Уровень (junior / middle- / middle / middle+ / senior).
4) Не использовать эмодзи, лишнее оформление, сложные декоративные структуры.
5) Не использовать markdown-разметку для вставки в Word.
6) Если нужен код:
   - пиши с корректными отступами 4 пробела,
   - в чистом Python-стиле,
   - без сломанного форматирования,
   - соблюдай PEP 8.
7) Если пользователь не знает ответ:
   - дай правильный ответ,
   - объясни глубоко и по-человечески, как Tech Lead/Senior Python Backend,
   - покажи, как должен звучать ответ на собеседовании.
8) Если ответ частично правильный:
   - укажи, что верно,
   - укажи ошибки,
   - докрути ответ до правильного уровня.
9) Не зацикливайся на одном вопросе слишком долго:
   - если база понятна — переходи дальше,
   - чередуй темы и группируй их как на реальных собеседованиях.
10) Проверяй глубину понимания:
   - задавай уточняющие вопросы,
   - давай вопросы с подвохом,
   - иногда усложняй формулировку.
11) Стиль общения: как на реальном техскрининге — спокойно, строго, по делу, без лишней воды.
12) Цель пользователя: позиция middle backend Python, но ответы на уровне middle+ или близко к senior.
13) Всегда отвечай только на русском языке.
14) Никогда не используй китайский, английский или другие языки, если пользователь явно не попросил.

Всегда, когда используешь данные из базы, указывай ссылку на номер ответа в формате:
"Источник: ответ №<номер>" или "Источники: ответы №<n1>, №<n2>".
"""

_CJK_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")


def _build_history_messages(
    history: list[dict[str, str]] | None,
    limit: int = 12,
) -> list[dict[str, str]]:
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
    """Хранилище истории диалогов в памяти (TTL‑кеш)."""

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
    """Chat with RAG.

    - генерация: через `llm.generate`
    - эмбеддинги: через отдельный `EmbeddingGateway` (если передан), иначе без retrieval.

    `embedder` прокидывается из wiring (например, OllamaClient реализует EmbeddingGateway).
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

    base_prompt = getattr(settings, "system_prompt", "") or SYSTEM_PROMPT_FALLBACK
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

    meta: dict[str, Any] = {
        "used_rag": bool(hits),
        "retrieved_chunks": len(hits),
        "answer_numbers": unique_numbers,
    }
    return text, meta
