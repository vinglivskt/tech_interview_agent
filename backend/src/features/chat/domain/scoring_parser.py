"""Парсер оценки из текста ответа чат-ассистента.

Чат-ассистент (см. ``prompts/chat/system.md``) выдаёт оценку в формате:

    Оценка:
    • Понимание: X/5
    • Глубина: X/5
    • Точность: X/5
    • Уровень: junior / middle- / middle / middle+ / senior

Парсер извлекает эти поля и превращает их в ``score_percent`` по правилам:
- Если пользователь явно отказался отвечать (``не знаю`` и т.п.) → ``score_percent=0``.
- Если оценки нет (ассистент опустил блок оценки, как при «не знаю» в чат-промте) → ``None``.
- Если оценка есть → ``score_percent`` = среднее трёх метрик × 20 (шкала 0–100).
  Уровень ``junior`` дополнительно понижает оценку, ``senior`` — повышает.
"""

from __future__ import annotations

import re
from typing import Any

from src.features.sobes.domain.scoring import _is_decline

# Регулярки для блока «Оценка:». Ищем в любом регистре, по строкам.
_UNDERSTANDING_RE = re.compile(r"поним\w*:\s*(\d)\s*/\s*5", re.IGNORECASE | re.UNICODE)
_DEPTH_RE = re.compile(r"глубин\w*:\s*(\d)\s*/\s*5", re.IGNORECASE | re.UNICODE)
_ACCURACY_RE = re.compile(r"точност\w*:\s*(\d)\s*/\s*5", re.IGNORECASE | re.UNICODE)
_LEVEL_RE = re.compile(r"уровень:\s*([a-zа-яё+\-\s]+?)(?:\n|$)", re.IGNORECASE | re.UNICODE)

_LEVEL_BONUS: dict[str, int] = {
    "junior": -10,
    "middle-": -3,
    "middle": 0,
    "middle+": 5,
    "senior": 10,
}
# Порядок важен — ищем более специфичные значения (middle+ / middle-) раньше, чем middle.
_LEVEL_ORDER: tuple[str, ...] = ("middle-", "middle+", "junior", "senior", "middle")


def _clip(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def parse_assistant_grade(assistant_text: str) -> dict[str, Any] | None:
    """Извлекает оценку из текста ассистента. Возвращает None, если блок не найден."""
    if not assistant_text:
        return None
    understanding = _UNDERSTANDING_RE.search(assistant_text)
    depth = _DEPTH_RE.search(assistant_text)
    accuracy = _ACCURACY_RE.search(assistant_text)
    level_match = _LEVEL_RE.search(assistant_text)

    if not (understanding and depth and accuracy):
        return None

    try:
        u = int(understanding.group(1))
        d = int(depth.group(1))
        a = int(accuracy.group(1))
    except (ValueError, IndexError):
        return None

    if not all(0 <= x <= 5 for x in (u, d, a)):
        return None

    level_raw = level_match.group(1).strip().lower() if level_match else "middle"
    level = "middle"
    for key in _LEVEL_ORDER:
        if key in level_raw:
            level = key
            break

    # Базовая оценка: среднее × 20 (шкала 0–100).
    base = round((u + d + a) / 3.0 * 20)
    score = _clip(base + _LEVEL_BONUS[level])

    return {
        "score_percent": score,
        "comprehension": u,
        "depth": d,
        "accuracy": a,
        "level": level,
    }


def grade_user_response(
    user_message: str,
    assistant_text: str,
    *,
    pass_threshold: int,
) -> dict[str, Any]:
    """Итоговая оценка пары user/assistant.

    Возвращает словарь с полями:
    - ``score_percent``: 0–100.
    - ``category``: "correct" / "partial" / "incorrect".
    - ``is_decline``: True, если пользователь явно отказался отвечать.
    - ``has_grade``: True, если в ответе ассистента был распознан блок оценки.
    - остальные поля — из парсера, если блок найден.
    """
    from src.db.repository import categorize  # локальный импорт, чтобы не зациклиться

    if _is_decline(user_message):
        return {
            "score_percent": 0,
            "category": "incorrect",
            "is_decline": True,
            "has_grade": False,
            "comprehension": None,
            "depth": None,
            "accuracy": None,
            "level": None,
        }

    parsed = parse_assistant_grade(assistant_text)
    if parsed is None:
        # Ассистент не выставил оценку (например, режим «не знаю» по chat-промту).
        # Считаем такой ответ как «нет оценки» — INCORRECT, чтобы пользователь
        # видел, что засчитано ничего не было.
        return {
            "score_percent": 0,
            "category": "incorrect",
            "is_decline": False,
            "has_grade": False,
            "comprehension": None,
            "depth": None,
            "accuracy": None,
            "level": None,
        }

    return {
        "score_percent": parsed["score_percent"],
        "category": categorize(parsed["score_percent"], pass_threshold).value,
        "is_decline": False,
        "has_grade": True,
        "comprehension": parsed["comprehension"],
        "depth": parsed["depth"],
        "accuracy": parsed["accuracy"],
        "level": parsed["level"],
    }


__all__ = ["parse_assistant_grade", "grade_user_response"]
