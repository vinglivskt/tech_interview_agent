# Генерация неправильных вариантов ответов для квиза с помощью LLM.
from __future__ import annotations

import json
import logging

from app.features.chat.providers.ollama import OllamaClient

logger = logging.getLogger(__name__)

# Системный промпт для генерации правдоподобных неправильных ответов
_WRONG_ANSWERS_SYSTEM_PROMPT = (
    "Ты — эксперт по проведению технических собеседований на Python.\n"
    "Твоя задача — сгенерировать 3 правдоподобных, но НЕПРАВИЛЬНЫХ варианта ответа "
    "для вопроса с множественным выбором.\n\n"
    "Требования:\n"
    "- Неправильные ответы должны звучать реалистично и отражать типичные заблуждения.\n"
    "- Они не должны быть слишком очевидно неправильными.\n"
    "- Длина и стиль должны быть сопоставимы с правильным ответом.\n"
    "- Отвечай СТРОГО в формате JSON-массива из 3 строк, без пояснений.\n"
    '  Пример: ["неправильный ответ 1", "неправильный ответ 2", "неправильный ответ 3"]\n'
)


async def generate_wrong_answers(
    llm: OllamaClient,
    question: str,
    correct_answer: str,
) -> list[str]:
    """
    Генерирует 3 правдоподобных, но неправильных варианта ответа с помощью LLM.

    :param llm: клиент LLM (OllamaClient)
    :param question: текст вопроса
    :param correct_answer: правильный ответ (для контекста)
    :return: список из 3 неправильных ответов
    """
    user_prompt = (
        f"Вопрос: {question}\n\n"
        f"Правильный ответ: {correct_answer}\n\n"
        "Сгенерируй 3 правдоподобных, но неправильных варианта ответа. "
        "Верни только JSON-массив из 3 строк."
    )

    messages = [
        {"role": "system", "content": _WRONG_ANSWERS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = await llm.generate(messages, temperature=0.9, max_tokens=512)
        # Пытаемся распарсить JSON из ответа
        # Иногда LLM оборачивает в ```json ... ```
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Убираем markdown-обёртку
            cleaned = cleaned.split("```", 1)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        result = json.loads(cleaned)
        if isinstance(result, list) and len(result) >= 3:
            return [str(item).strip() for item in result[:3]]
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Не удалось сгенерировать неправильные ответы через LLM: %s", exc)

    # Fallback: возвращаем шаблонные неправильные ответы
    return [
        f"Неверный вариант A для вопроса: {question[:50]}...",
        f"Неверный вариант B для вопроса: {question[:50]}...",
        f"Неверный вариант C для вопроса: {question[:50]}...",
    ]
