"""Логика интервью-ассистента с RAG и генерацией через OpenAI Chat API."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionAssistantMessageParam, ChatCompletionMessageParam

from app.config import Settings
from app.services.qdrant_service import QdrantService

SYSTEM_PROMPT = """Ты выступаешь в роли опытного Tech Lead / Senior Python Backend разработчика с большим опытом проведения собеседований.
У тебя есть база вопросов и ответов по Python-интервью. База приоритетнее памяти модели.

Правила:
1) Работай в формате реального техскрина по backend Python middle/middle+.
2) Когда пользователь просит провести интервью или хочет вопрос — задавай следующий вопрос.
3) После ответа пользователя:
   - дай короткий эталонный ответ (готовый для Word),
   - затем углуби объяснение без повторов,
   - потом оцени: Понимание, Глубина, Точность, Уровень.
4) Всегда, когда используешь данные из базы, указывай ссылку на номер ответа в формате:
   "Источник: ответ №<номер>" или "Источники: ответы №<n1>, №<n2>".
5) Не используй эмодзи и лишнее оформление.
"""


def _build_history_messages(history: list[dict[str, str]] | None) -> list[ChatCompletionMessageParam]:
    if not history:
        return []

    messages: list[ChatCompletionMessageParam] = []
    for item in history[-12:]:
        role = item.get("role", "")
        content = (item.get("content", "") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append({"role": "user", "content": content})
        elif role == "assistant":
            messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=content))
    return messages


async def run_chat(
    settings: Settings,
    openai: AsyncOpenAI,
    qdrant: QdrantService,
    user_message: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Выполняет диалог с retrieval из Qdrant.

    Args:
        settings: Конфигурация приложения.
        openai: Клиент OpenAI.
        qdrant: Сервис поиска по коллекции.
        user_message: Текст пользователя.
        history: История диалога.

    Returns:
        Кортеж ``(ответ_строка, meta)``.
    """
    hits = await qdrant.search_payload(user_message, limit=settings.interview_top_k)

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

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                "Контекст из векторной базы:\n"
                f"{rag_context}\n\n"
                "Если используешь сведения из базы, обязательно укажи источник(и) "
                f"в формате 'ответ №N'. Найденные номера: {refs}."
            ),
        },
        *_build_history_messages(history),
        {"role": "user", "content": user_message.strip()},
    ]

    resp = await openai.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
    )
    text = (resp.choices[0].message.content or "").strip()

    if unique_numbers and "ответ №" not in text.lower() and "ответы №" not in text.lower():
        refs_suffix = ", ".join(str(number) for number in unique_numbers)
        text = f"{text}\n\nИсточники: ответы №{refs_suffix}"

    meta: dict[str, Any] = {
        "used_rag": bool(hits),
        "retrieved_chunks": len(hits),
        "answer_numbers": unique_numbers,
    }
    return text, meta
