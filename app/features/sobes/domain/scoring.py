from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.features.chat.providers.ollama import OllamaClient

# Путь к файлу промпта
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts" / "sobes" / "scoring.md"


def _load_scoring_prompt() -> str:
    """Загружает промпт для оценки ответов."""
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Prompt file not found: {_PROMPT_PATH}. Please ensure prompts/sobes/scoring.md exists."
        )


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
    template = _load_scoring_prompt()
    system = template.format(question=question_text, reference=reference_answer, user_answer=user_answer)
    user = "Верни только JSON. Кратко, по делу."

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
