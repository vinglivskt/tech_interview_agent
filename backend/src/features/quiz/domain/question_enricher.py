# Обогащение «сухих» вопросов из базы QA: превращение их в развёрнутые вопросы
# в стиле Tech Lead на основе имеющегося ответа.
from __future__ import annotations

import logging
from pathlib import Path

from src.features.chat.providers.ollama import OllamaClient

logger = logging.getLogger(__name__)

# Путь к файлу промпта (рядом с другими промптами квиза)
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts" / "quiz" / "enrich_question.md"


def _load_enrich_prompt() -> str:
    """Загружает промпт для обогащения вопросов."""
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Prompt file not found: {_PROMPT_PATH}. Please ensure prompts/quiz/enrich_question.md exists."
        ) from None


_ENRICH_SYSTEM_PROMPT = _load_enrich_prompt()


def _looks_like_dry_question(question: str) -> bool:
    """
    Эвристика: стоит ли вообще пытаться обогащать вопрос.

    Сухими считаются короткие вопросы, которые звучат как определение/название темы
    без уточнений. Если вопрос уже развёрнутый и содержит конкретику — пропускаем,
    чтобы не сломать формулировку и не тратить вызов LLM.
    """
    q = question.strip().rstrip("?.!")
    # Слишком длинный вопрос — скорее всего уже развёрнутый
    if len(q) > 120:
        return False
    # Содержит «как», «зачем», «почему», «когда» — уже есть направление мысли
    lower = q.lower()
    if any(token in lower for token in ("как ", "зачем", "почему", "когда ", "что будет", "в чём ", "чем ")):
        return False
    # Содержит вопросительный знак — уже есть конкретика
    if q.count("?") >= 1:
        return False
    return True


# Пары обрамляющих кавычек, которые модель может случайно добавить.
_QUOTE_PAIRS = (
    ('"', '"'),
    ("'", "'"),
    ("«", "»"),
)

_PREFIXES = (
    "Переформулированный вопрос:",
    "Переформулированный:",
    "Новый вопрос:",
    "Вопрос:",
    "вопрос:",
    "Q:",
    "q:",
)


def _strip_matching_quotes(text: str) -> str:
    """Снимает пару обрамляющих кавычек (если они есть)."""
    if len(text) < 2:
        return text
    for open_q, close_q in _QUOTE_PAIRS:
        if text.startswith(open_q) and text.endswith(close_q):
            return text[len(open_q) : -len(close_q)].strip()
    return text


def _clean_enriched_text(raw: str) -> str:
    """
    Очищает ответ LLM от типичного мусора: кавычек, префиксов, переносов.
    Возвращает одну строку — готовый вопрос.
    """
    text = raw.strip()
    # Сначала снимаем обрамляющие кавычки (на случай, если LLM обернула ответ)
    text = _strip_matching_quotes(text)
    # Убираем типичные префиксы вида «Вопрос:», «Q:», «Переформулированный вопрос:»
    lower = text.lower()
    for prefix in _PREFIXES:
        if lower.startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
            # После префикса может остаться обрамляющая кавычка
            text = _strip_matching_quotes(text)
            break
    return text.strip()


def _is_sane_question(text: str) -> bool:
    """Простейшая проверка адекватности переформулированного вопроса."""
    if not text:
        return False
    # Не даём модели сломать длину
    if len(text) > 400:
        return False
    # Должен заканчиваться на ? (вопрос) — иначе это уже не вопрос
    stripped = text.rstrip()
    if not stripped.endswith("?"):
        return False
    # Должен содержать хоть какие-то русские буквы
    has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in text)
    return has_cyrillic


async def enrich_question(
    llm: OllamaClient,
    question: str,
    answer: str,
) -> str:
    """
    Переформулирует «сухой» вопрос из базы в развёрнутый вопрос в стиле Tech Lead,
    опираясь на имеющийся ответ. Не раскрывает сам ответ и не даёт прямых подсказок.

    :param llm: клиент LLM (OllamaClient)
    :param question: исходный вопрос из базы
    :param answer: эталонный ответ из базы (для контекста)
    :return: обогащённый вопрос, либо исходный — если эвристика/LLM решили не трогать
    """
    # Пустой/слишком большой ответ — нет материала для обогащения
    answer_clean = (answer or "").strip()
    if not answer_clean or len(answer_clean) < 20:
        return question

    # Эвристика: если вопрос уже развёрнутый — не трогаем
    if not _looks_like_dry_question(question):
        return question

    user_prompt = (
        f"Вопрос из базы:\n{question.strip()}\n\n"
        f"Ответ из базы:\n{answer_clean}\n\n"
        "Переформулируй вопрос так, как задал бы техлид на собеседовании. "
        "Не раскрывай ответ. Верни только одну строку с вопросом."
    )

    messages = [
        {"role": "system", "content": _ENRICH_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = await llm.generate(messages, temperature=0.4, max_tokens=200)
        cleaned = _clean_enriched_text(raw)
        if _is_sane_question(cleaned):
            logger.debug("Вопрос обогащён: '%s' -> '%s'", question, cleaned)
            return cleaned
        logger.debug("Обогащение отклонено проверкой: '%s'", cleaned[:120])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось обогатить вопрос через LLM: %s", exc)

    # Fallback — отдаём исходный вопрос
    return question
