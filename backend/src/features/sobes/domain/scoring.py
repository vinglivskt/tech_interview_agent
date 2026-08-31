from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.features.chat.providers.ollama import OllamaClient

# Путь к файлу промпта
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts" / "sobes" / "scoring.md"

# Паттерны явного отказа отвечать. Совпадение считается по нормализованной строке
# (без регистра, схлопнув пробелы и убрав знаки препинания в конце).
# Это страховка от ситуации, когда LLM-as-judge завышает оценку за фразы вроде
# «не знаю», «забыл», «пас», «skip» и т.п. — такие ответы должны получать 0%.
_DECLINE_PATTERNS: tuple[str, ...] = (
    r"^\s*не\s+зна(ю|ет|ем|ешь|ете)\b.*$",
    r"^\s*не\s+помн(ю|ит|им|ишь|ите)\b.*$",
    r"^\s*не\s+помню\s+как\b.*$",
    r"^\s*забыл(\s|$).*$",
    r"^\s*забыл[аи]?(\s|$).*$",
    r"^\s*затрудня(юсь|ешься|емся)\b.*$",
    r"^\s*пас\s*$",
    r"^\s*pass\s*$",
    r"^\s*skip\s*$",
    r"^\s*пропусти\s*$",
    r"^\s*спроси\s+следующ(ий|ую)\s*$",
    r"^\s*следующий\s+вопрос\s*$",
    r"^\s*без\s+понятия\s*$",
    r"^\s*понятия\s+не\s+име(ю|ет)\s*$",
    r"^\s*хз\s*$",
    r"^\s*не\s+в\s+курсе\s*$",
    r"^\s*не\s+помню\s+как\s+называется\s*$",
)
_DECLINE_RE = re.compile("|".join(_DECLINE_PATTERNS), re.IGNORECASE | re.UNICODE)
# Ответ короче 3 не-буквенных символов после схлопывания пробелов тоже считается пустым.
_NON_WORD_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)


def _is_decline(user_answer: str) -> bool:
    """True, если ответ — явный отказ отвечать или пустой шум."""
    raw = (user_answer or "").strip()
    if not raw:
        return True
    # Убираем повторяющиеся пробелы и финальные знаки препинания
    normalized = re.sub(r"\s+", " ", raw).rstrip(" .!?…,")
    if not normalized:
        return True
    if _NON_WORD_ONLY.match(normalized):
        return True
    if _DECLINE_RE.match(normalized):
        return True
    return False


def _decline_response(max_expl_len: int) -> tuple[int, bool, str, list[str], list[str]]:
    """Стандартный ответ при явном отказе: 0%, INCORRECT, без вызова LLM."""
    expl = (
        "Кандидат не ответил на вопрос. Чтобы получить зачёт, нужно дать хотя бы частичное объяснение своими словами."
    )
    if len(expl) > max_expl_len:
        expl = expl[: max_expl_len - 1] + "…"
    return 0, False, expl, [], ["кандидат не дал ответа на вопрос"]


def _load_scoring_prompt() -> str:
    """Загружает промпт для оценки ответов."""
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Prompt file not found: {_PROMPT_PATH}. Please ensure prompts/sobes/scoring.md exists."
        ) from None


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
    Перед LLM применяется детектор явного отказа: «не знаю», «забыл», пустой ответ и т.п.
    автоматически получают 0% без вызова модели.
    """
    if _is_decline(user_answer):
        return _decline_response(max_expl_len)

    template = _load_scoring_prompt()
    system = (
        template.replace("{question}", question_text)
        .replace("{reference}", reference_answer)
        .replace("{user_answer}", user_answer)
    )
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
