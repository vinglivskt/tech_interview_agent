from __future__ import annotations

import json
from typing import Any

from app.features.chat.providers.ollama import OllamaClient


async def score_free_answer(
    llm: OllamaClient,
    question_text: str,
    reference_answer: str,
    user_answer: str,
    *,
    pass_threshold: int,
    max_expl_len: int,
) -> tuple[int, bool, str, list[str], list[str]]:
    """
    Оценивает свободный ответ пользователя через LLM.
    Возвращает (percent, is_counted, explanation, covered_points, missed_points).
    При сбое парсинга — безопасный degrade (0%).
    """
    system = (
        "Ты технический интервьюер. Сравни ответ кандидата с эталоном. Отвечай строго JSON. "
        "Верни: {score_percent:int 0..100, covered_points:[str], missed_points:[str], techlead_explanation:str}."
    )
    user = (
        "Вопрос: "
        + question_text
        + "\nЭталонный ответ: "
        + reference_answer
        + "\nОтвет кандидата: "
        + user_answer
        + "\nВерни только JSON. Кратко, по делу."
    )

    try:
        text = await llm.generate(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        data: dict[str, Any] = json.loads(text)
        percent = int(max(0, min(100, int(data.get("score_percent", 0)))))
        covered = [str(x) for x in data.get("covered_points", [])][:6]
        missed = [str(x) for x in data.get("missed_points", [])][:6]
        expl = str(data.get("techlead_explanation", "")).strip()
        if len(expl) > max_expl_len:
            expl = expl[: max_expl_len - 1] + "…"
        return percent, percent >= pass_threshold, expl, covered, missed
    except Exception:
        return 0, False, "Ответ не соответствует ожидаемым ключевым тезисам. Рекомендую повторить тему.", [], []
