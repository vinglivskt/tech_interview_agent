# Генерация неправильных вариантов ответов для квиза с помощью LLM.
from __future__ import annotations

import json
import logging

from app.features.chat.providers.ollama import OllamaClient

logger = logging.getLogger(__name__)

# Системный промпт для генерации правдоподобных неправильных ответов
_WRONG_ANSWERS_SYSTEM_PROMPT = (
    "Ты — эксперт по составлению тестов для программистов.\n"
    "Сгенерируй 3 НЕПРАВИЛЬНЫХ варианта ответа для вопроса с множественным выбором.\n\n"
    "КРИТИЧЕСКИ ВАЖНО:\n"
    "- Все 4 варианта (правильный + 3 твоих) должны быть ОДИНАКОВОЙ ДЛИНЫ (+-20%)\n"
    "- Неправильные ответы должны звучать ПРАВДОПОДОБНО — как ответ человека, который почти знает тему\n"
    "- НЕ делай неправильные ответы очевидно неверными (без абсурда, шуток, случайных слов)\n"
    "- Используй ТЕ ЖЕ технические термины что и в правильном ответе\n"
    "- Ошибки должны быть ТИПИЧНЫМИ заблуждениями — путаница терминов, неверный порядок действий, перепутанные концепции\n"
    "- Каждый ответ: 1-2 предложения, максимум 15 слов\n"
    "- Неправильный вопрос не должен быть просто перемешанным правильным, а должен отличаться от правильного\n"
    "- Отвечай ТОЛЬКО JSON-массивом из 3 строк, без markdown, без пояснений\n\n"
    'Формат: ["ответ 1", "ответ 2", "ответ 3"]\n'
    'Пример для вопроса "Что такое GIL?": '
    '["Блокировка ограничивающая параллельное выполнение потоков в Python", '
    '"Механизм для синхронизации доступа к файлам в многопоточных программах", '
    '"Специальный протокол для работы с сетевыми соединениями в async коде"]'
)


def _truncate_to_length(text: str, target_length: int) -> str:
    """Обрезает текст до целевой длины, сохраняя целые слова."""
    if len(text) <= target_length:
        return text
    # Ищем последнее предложение или запятую в пределах target_length
    truncated = text[:target_length]
    last_period = truncated.rfind(".")
    last_comma = truncated.rfind(",")
    cut_at = max(last_period, last_comma)
    if cut_at > target_length * 0.5:
        return truncated[: cut_at + 1].strip()
    return truncated.rsplit(" ", 1)[0].strip()


async def generate_wrong_answers(
    llm: OllamaClient,
    question: str,
    correct_answer: str,
) -> list[str]:
    """
    Генерирует 3 правдоподобных, но неправильных варианта ответа с помощью LLM.
    Все варианты будут приведены к одинаковой длине.

    :param llm: клиент LLM (OllamaClient)
    :param question: текст вопроса
    :param correct_answer: правильный ответ (для контекста)
    :return: список из 3 неправильных ответов
    """
    target_length = len(correct_answer)
    length_hint = (
        f"\n\nЦелевая длина каждого ответа: ~{target_length} символов "
        f"(+-20%, т.е. от {int(target_length * 0.8)} до {int(target_length * 1.2)} символов). "
        f"Правильный ответ имеет длину {target_length} символов."
    )

    user_prompt = (
        f"Вопрос: {question}\n\n"
        f"Правильный ответ ({target_length} симв.): {correct_answer}\n\n"
        "Сгенерируй 3 неправильных варианта одинаковой длины с правильным." + length_hint
    )

    messages = [
        {"role": "system", "content": _WRONG_ANSWERS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = await llm.generate(messages, temperature=0.8, max_tokens=300)
        cleaned = raw.strip()

        # Убираем markdown-обёртку если есть
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 1)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        result = json.loads(cleaned)
        if isinstance(result, list) and len(result) >= 3:
            wrong_answers = [str(item).strip() for item in result[:3]]

            # Приводим все ответы к целевой длине
            adjusted = []
            for ans in wrong_answers:
                if len(ans) > target_length * 1.3:
                    ans = _truncate_to_length(ans, target_length)
                adjusted.append(ans)

            return adjusted

    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Не удалось сгенерировать неправильные ответы через LLM: %s", exc)

    # Fallback: генерируем правдоподобные неправильные ответы на основе правильного
    return _generate_fallback_wrong_answers(correct_answer)


def _generate_fallback_wrong_answers(correct_answer: str) -> list[str]:
    """
    Генерирует fallback-ответы когда LLM не сработал.
    Создаёт правдоподобные варианты путём модификации правильного ответа.
    """
    # Простые эвристики для создания неправильных вариантов
    words = correct_answer.split()

    if len(words) < 3:
        return [
            f"Неверно: {correct_answer}",
            f"Противоположно: {correct_answer}",
            f"Ошибочное утверждение о {correct_answer[:20]}",
        ]

    # Вариант 1: убираем ключевое слово
    mid = len(words) // 2
    variant1 = " ".join(words[:mid] + words[mid + 1 :])

    # Вариант 2: меняем порядок частей
    if "," in correct_answer:
        parts = correct_answer.split(", ")
        parts[0], parts[-1] = parts[-1], parts[0]
        variant2 = ", ".join(parts)
    else:
        variant2 = " ".join(words[::-1][: len(words)])

    # Вариант 3: заменяем половину слов
    variant3 = " ".join(words[::2] + words[len(words) // 2 :: 2])

    return [variant1, variant2, variant3]
