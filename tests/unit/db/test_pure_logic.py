"""Unit tests for pure-Python helpers in the DB layer.

Здесь нет ни сессий, ни движка — только чистые функции, чтобы тесты были
мгновенными и не требовали внешних сервисов.
"""

from __future__ import annotations

import pytest
from src.core.deps import decode_username_header
from src.db.models import AnswerCategory, Feature
from src.db.repository import (
    StatsBreakdown,
    categorize,
    normalize_username,
)


class TestNormalizeUsername:
    def test_basic(self) -> None:
        assert normalize_username("Alex") == ("alex", "Alex")

    def test_with_spaces(self) -> None:
        assert normalize_username("  Alex  ") == ("alex", "Alex")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize_username("")
        with pytest.raises(ValueError):
            normalize_username("   ")

    def test_case_insensitive(self) -> None:
        assert normalize_username("ALEX") == ("alex", "ALEX")
        assert normalize_username("alEx") == ("alex", "alEx")

    def test_display_name_preserved(self) -> None:
        # Display name остаётся как ввели, а username приводится к lower
        assert normalize_username("Алёна")[0] == "алёна"
        assert normalize_username("Алёна")[1] == "Алёна"


class TestUsernameHeader:
    def test_decodes_unicode_name_from_http_safe_header(self) -> None:
        assert (
            decode_username_header("%D0%98%D0%B2%D0%B0%D0%BD%20%D0%9F%D0%B5%D1%82%D1%80%D0%BE%D0%B2") == "Иван Петров"
        )


class TestCategorize:
    def test_zero_is_incorrect(self) -> None:
        assert categorize(0, 50) is AnswerCategory.INCORRECT

    def test_negative_is_incorrect(self) -> None:
        assert categorize(-5, 50) is AnswerCategory.INCORRECT

    def test_below_threshold_is_partial(self) -> None:
        assert categorize(49, 50) is AnswerCategory.PARTIAL
        assert categorize(1, 50) is AnswerCategory.PARTIAL

    def test_at_threshold_is_correct(self) -> None:
        assert categorize(50, 50) is AnswerCategory.CORRECT

    def test_above_threshold_is_correct(self) -> None:
        assert categorize(99, 50) is AnswerCategory.CORRECT
        assert categorize(100, 50) is AnswerCategory.CORRECT

    def test_threshold_zero_one_is_correct(self) -> None:
        # При threshold=0 даже минимальный положительный score считается CORRECT.
        # score=0 — всегда INCORRECT (нет правильной части в ответе).
        assert categorize(1, 0) is AnswerCategory.CORRECT
        assert categorize(0, 0) is AnswerCategory.INCORRECT

    def test_threshold_100_only_full(self) -> None:
        assert categorize(99, 100) is AnswerCategory.PARTIAL
        assert categorize(100, 100) is AnswerCategory.CORRECT


class TestStatsBreakdown:
    def test_accuracy_with_partial(self) -> None:
        bd = StatsBreakdown(feature=Feature.QUIZ, total=10, correct=6, partial=2, incorrect=2)
        # (6 + 0.5*2) / 10 = 70%
        assert bd.accuracy_percent == 70.0

    def test_accuracy_only_correct(self) -> None:
        bd = StatsBreakdown(feature=Feature.QUIZ, total=10, correct=10, partial=0, incorrect=0)
        assert bd.accuracy_percent == 100.0
        assert bd.pass_rate_percent == 100.0

    def test_accuracy_only_incorrect(self) -> None:
        bd = StatsBreakdown(feature=Feature.QUIZ, total=10, correct=0, partial=0, incorrect=10)
        assert bd.accuracy_percent == 0.0
        assert bd.pass_rate_percent == 0.0

    def test_empty(self) -> None:
        bd = StatsBreakdown(feature=Feature.CHAT, total=0, correct=0, partial=0, incorrect=0)
        assert bd.accuracy_percent == 0.0
        assert bd.pass_rate_percent == 0.0
        assert bd.to_dict() == {
            "feature": "chat",
            "total": 0,
            "correct": 0,
            "partial": 0,
            "incorrect": 0,
            "accuracy_percent": 0.0,
            "pass_rate_percent": 0.0,
        }

    def test_to_dict(self) -> None:
        bd = StatsBreakdown(feature=Feature.SOBES, total=4, correct=2, partial=1, incorrect=1)
        out = bd.to_dict()
        assert out["feature"] == "sobes"
        assert out["total"] == 4
        assert out["correct"] == 2
        assert out["partial"] == 1
        assert out["incorrect"] == 1
        # accuracy = (2 + 0.5) / 4 = 0.625 -> 62.5%
        assert out["accuracy_percent"] == 62.5
        assert out["pass_rate_percent"] == 75.0


class TestFeatureEnum:
    def test_values(self) -> None:
        assert Feature.CHAT.value == "chat"
        assert Feature.QUIZ.value == "quiz"
        assert Feature.SOBES.value == "sobes"
        assert Feature.DESIGN.value == "design"

    def test_str_compare(self) -> None:
        # StrEnum должен сравниваться со строками
        assert Feature.QUIZ == "quiz"


class TestAnswerCategoryEnum:
    def test_values(self) -> None:
        assert AnswerCategory.CORRECT.value == "correct"
        assert AnswerCategory.PARTIAL.value == "partial"
        assert AnswerCategory.INCORRECT.value == "incorrect"


class TestDeclineDetector:
    """Проверяет, что явный отказ отвечать всегда даёт 0% независимо от LLM."""

    def test_explicit_dont_know(self) -> None:
        from src.features.sobes.domain.scoring import _is_decline

        assert _is_decline("не знаю") is True
        assert _is_decline("Не знаю") is True
        assert _is_decline("Не знаю.") is True
        assert _is_decline("  не знаю  ") is True
        assert _is_decline("не помню") is True
        assert _is_decline("забыл") is True
        assert _is_decline("затрудняюсь") is True
        assert _is_decline("пас") is True
        assert _is_decline("skip") is True
        assert _is_decline("пропусти") is True
        assert _is_decline("без понятия") is True
        assert _is_decline("хз") is True
        assert _is_decline("не в курсе") is True
        assert _is_decline("спроси следующий") is True
        assert _is_decline("следующий вопрос") is True

    def test_real_answer_is_not_decline(self) -> None:
        from src.features.sobes.domain.scoring import _is_decline

        assert _is_decline("через threading и multiprocessing") is False
        assert _is_decline("использовать SELECT FOR UPDATE") is False
        assert _is_decline("async SQLAlchemy ускоряет, потому что неблокирующие запросы") is False
        assert _is_decline("name mangling — это _ClassName__attr") is False

    def test_empty_and_punctuation(self) -> None:
        from src.features.sobes.domain.scoring import _is_decline

        assert _is_decline("") is True
        assert _is_decline("   ") is True
        assert _is_decline("???") is True
        assert _is_decline("...") is True
        # «хм» / «эээ» — буквенный текст, может быть размышлением вслух, не считаем отказом
        assert _is_decline("хм") is False
        assert _is_decline("эээ") is False

    def test_decline_response_shape(self) -> None:
        from src.features.sobes.domain.scoring import _decline_response

        percent, counted, expl, covered, missed = _decline_response(600)
        assert percent == 0
        assert counted is False
        assert expl
        assert covered == []
        assert missed == ["кандидат не дал ответа на вопрос"]

    def test_decline_skips_llm_call(self) -> None:
        """Интеграционная проверка: при decline-ответе LLM вообще не вызывается."""
        from src.features.sobes.domain.scoring import score_free_answer

        called = {"n": 0}

        class NoCallLLM:
            async def generate(self, messages, **kwargs):
                called["n"] += 1
                return "{}"

        async def run() -> tuple[int, bool, str, list[str], list[str]]:
            return await score_free_answer(
                NoCallLLM(),  # type: ignore[arg-type]
                question_text="q",
                reference_answer="r",
                user_answer="не знаю",
                pass_threshold=50,
                max_expl_len=600,
            )

        import asyncio

        percent, counted, _expl, covered, missed = asyncio.run(run())
        assert called["n"] == 0, "LLM must not be called for decline responses"
        assert percent == 0
        assert counted is False
        assert covered == []
        assert missed == ["кандидат не дал ответа на вопрос"]
