"""Юнит-тесты для question_enricher: проверяем эвристику, очистку,
поведение enrich_question с моком LLM и fallback при сбоях."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from src.features.quiz.domain.question_enricher import (
    _clean_enriched_text,
    _is_sane_question,
    _looks_like_dry_question,
    enrich_question,
)

# ---------- вспомогательные моки и фабрики ----------


class _StubLLM:
    """Минимальный мок OllamaClient — отвечает заранее заданной строкой или ошибкой."""

    def __init__(self, reply: str | None = None, raise_exc: Exception | None = None) -> None:
        self._reply = reply
        self._raise = raise_exc
        self.calls: list[list[dict[str, str]]] = []

    async def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.calls.append(messages)
        if self._raise is not None:
            raise self._raise
        assert self._reply is not None
        return self._reply


def _run(coro):
    """Запускает корутину в синхронном pytest без pytest-asyncio."""
    return asyncio.run(coro)


# ---------- эвристика «сухой вопрос» ----------


class TestDryQuestionHeuristic:
    """Проверяем, что обогащаем только действительно сухие формулировки."""

    @pytest.mark.parametrize(
        "question",
        [
            "Что такое Unit of Work в SQLAlchemy?",
            "Что такое GIL?",
            "Механизм очистки памяти в Python",
            "Что такое индекс в БД?",
            "Какие есть уровни изоляции транзакций?",
        ],
    )
    def test_dry_questions_pass(self, question: str) -> None:
        assert _looks_like_dry_question(question) is True, question

    @pytest.mark.parametrize(
        "question",
        [
            # длинный развёрнутый вопрос
            "Расскажи, как SQLAlchemy понимает, что объект изменился, и в какой момент эти изменения реально попадают в базу.",
            # вопрос уже содержит направление «как»
            "Как Python решает, когда освободить память занятого объекта?",
            # вопрос с «почему»
            "Почему GIL снижает производительность CPU-bound задач в Python?",
            # вопрос с «когда»
            "Когда стоит выбирать multiprocessing вместо threading?",
        ],
    )
    def test_already_rich_questions_are_skipped(self, question: str) -> None:
        assert _looks_like_dry_question(question) is False, question


# ---------- очистка ответа LLM ----------


class TestCleanEnrichedText:
    """Убираем кавычки, префиксы, мусор."""

    def test_strips_double_quotes(self) -> None:
        assert _clean_enriched_text('"А какой смысл?"') == "А какой смысл?"

    def test_strips_prefix_then_inner_quote(self) -> None:
        assert _clean_enriched_text('Вопрос: "А какой смысл?"') == "А какой смысл?"

    def test_strips_prefix_case_insensitive(self) -> None:
        assert _clean_enriched_text("переформулированный вопрос: Готово?") == "Готово?"

    def test_keeps_plain_text(self) -> None:
        assert _clean_enriched_text("Готово?") == "Готово?"


# ---------- проверка адекватности ----------


class TestIsSaneQuestion:
    def test_accepts_normal_question(self) -> None:
        assert _is_sane_question("Что такое GIL и как он влияет на потоки?") is True

    def test_rejects_too_long(self) -> None:
        assert _is_sane_question("А " + ("очень " * 100) + "?") is False

    def test_rejects_without_question_mark(self) -> None:
        assert _is_sane_question("Просто утверждение без вопроса") is False

    def test_rejects_without_cyrillic(self) -> None:
        assert _is_sane_question("Just an English question?") is False

    def test_rejects_empty(self) -> None:
        assert _is_sane_question("") is False


# ---------- основной сценарий enrich_question ----------


class TestEnrichQuestion:
    """Проверяем поведение с моком LLM."""

    def test_returns_enriched_when_llm_returns_good_text(self) -> None:
        llm = _StubLLM(reply="Что такое GIL в CPython и как он влияет на CPU-bound потоки?")
        out = _run(
            enrich_question(
                llm,
                "Что такое GIL?",
                "GIL — блокировка интерпретатора CPython, мешающая потокам выполнять байткод одновременно.",
            )
        )
        assert out == "Что такое GIL в CPython и как он влияет на CPU-bound потоки?"
        assert len(llm.calls) == 1
        user_msg = llm.calls[0][1]["content"]
        assert "Что такое GIL?" in user_msg
        assert "GIL — блокировка" in user_msg

    def test_strips_quotes_from_llm_reply(self) -> None:
        llm = _StubLLM(reply="«Что такое GIL и зачем он нужен?»")
        out = _run(enrich_question(llm, "Что такое GIL?", "GIL — блокировка интерпретатора."))
        assert out == "Что такое GIL и зачем он нужен?"

    def test_strips_prefix_from_llm_reply(self) -> None:
        llm = _StubLLM(reply="Вопрос: Что такое GIL и где он применяется?")
        out = _run(enrich_question(llm, "Что такое GIL?", "GIL — блокировка интерпретатора."))
        assert out == "Что такое GIL и где он применяется?"

    def test_fallback_when_llm_raises(self) -> None:
        llm = _StubLLM(raise_exc=RuntimeError("ollama down"))
        original = "Что такое GIL?"
        out = _run(enrich_question(llm, original, "GIL — блокировка интерпретатора."))
        assert out == original
        # LLM всё-таки была вызвана — мы пытались
        assert len(llm.calls) == 1

    def test_fallback_when_llm_returns_garbage(self) -> None:
        # LLM вернула строку без вопросительного знака
        llm = _StubLLM(reply="Это вообще не вопрос, а утверждение")
        original = "Что такое GIL?"
        out = _run(enrich_question(llm, original, "GIL — блокировка интерпретатора."))
        assert out == original

    def test_skips_already_rich_questions_without_calling_llm(self) -> None:
        llm = _StubLLM(reply="Любой текст — нас не должны вызвать")
        rich_question = "Расскажи, как Python решает, когда освободить память объекта?"
        out = _run(enrich_question(llm, rich_question, "Python использует счётчик ссылок и сборщик мусора."))
        assert out == rich_question
        # LLM не вызывали — вопрос и так развёрнутый
        assert llm.calls == []

    def test_skips_when_answer_too_short(self) -> None:
        llm = _StubLLM(reply="Новый вопрос?")
        original = "Что такое GIL?"
        out = _run(enrich_question(llm, original, "GIL."))
        assert out == original
        assert llm.calls == []

    def test_skips_when_answer_empty(self) -> None:
        llm = _StubLLM(reply="Новый вопрос?")
        original = "Что такое GIL?"
        out = _run(enrich_question(llm, original, ""))
        assert out == original
        assert llm.calls == []

    def test_preserves_key_terms_from_original_question(self) -> None:
        """Регрессия: модель обязана сохранить ключевые термины из исходного вопроса."""
        llm = _StubLLM(
            reply="Что такое Unit of Work в SQLAlchemy и в какой момент его накопленные изменения попадают в БД?"
        )
        out = _run(
            enrich_question(
                llm,
                "Что такое Unit of Work в SQLAlchemy?",
                "Unit of Work — паттерн SQLAlchemy для отслеживания изменений объектов в сессии.",
            )
        )
        assert "Unit of Work" in out
        assert "SQLAlchemy" in out


# ---------- интеграция эвристик через enrich_question ----------


class TestEnrichQuestionIntegration:
    """Сквозные проверки fallback'ов при разных типах плохих ответов LLM."""

    def test_fallback_when_llm_returns_only_prefix(self) -> None:
        llm = _StubLLM(reply="Вопрос:")
        original = "Что такое GIL?"
        out = _run(enrich_question(llm, original, "GIL — блокировка интерпретатора."))
        assert out == original

    def test_fallback_when_llm_returns_only_quotes(self) -> None:
        llm = _StubLLM(reply='""')
        original = "Что такое GIL?"
        out = _run(enrich_question(llm, original, "GIL — блокировка интерпретатора."))
        assert out == original
