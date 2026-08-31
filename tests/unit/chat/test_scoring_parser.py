"""Тесты парсера оценки из ответа чат-ассистента."""

from __future__ import annotations

from src.features.chat.domain.scoring_parser import (
    grade_user_response,
    parse_assistant_grade,
)


class TestParseAssistantGrade:
    def test_full_grade_block(self) -> None:
        text = (
            "Краткий правильный ответ: foo.\n\n"
            "Развёрнутое объяснение: bar.\n\n"
            "Оценка:\n"
            "• Понимание: 4/5\n"
            "• Глубина: 3/5\n"
            "• Точность: 5/5\n"
            "• Уровень: middle+\n"
            "\nИсточник: ответ №33"
        )
        parsed = parse_assistant_grade(text)
        assert parsed is not None
        assert parsed["comprehension"] == 4
        assert parsed["depth"] == 3
        assert parsed["accuracy"] == 5
        assert parsed["level"] == "middle+"
        # ((4+3+5)/3)*20 + 5 (middle+ бонус) = 80 + 5 = 85
        assert parsed["score_percent"] == 85

    def test_junior_lowers_score(self) -> None:
        text = "Оценка:\n• Понимание: 4/5\n• Глубина: 4/5\n• Точность: 4/5\n• Уровень: junior\n"
        parsed = parse_assistant_grade(text)
        assert parsed is not None
        # 80 - 10 (junior штрап) = 70
        assert parsed["score_percent"] == 70
        assert parsed["level"] == "junior"

    def test_senior_raises_score(self) -> None:
        text = "Оценка:\n• Понимание: 4/5\n• Глубина: 4/5\n• Точность: 4/5\n• Уровень: senior\n"
        parsed = parse_assistant_grade(text)
        assert parsed is not None
        # 80 + 10 (senior бонус) = 90
        assert parsed["score_percent"] == 90

    def test_missing_block_returns_none(self) -> None:
        # Чат-промт говорит: «Если пользователь НЕ знает ответ — не оценивай».
        text = "Правильный ответ: name mangling — это _ClassName__attr. Объясняю..."
        assert parse_assistant_grade(text) is None

    def test_partial_block_returns_none(self) -> None:
        text = "Оценка:\n• Понимание: 3/5\n"
        assert parse_assistant_grade(text) is None

    def test_invalid_numbers_clamped(self) -> None:
        text = "Оценка:\n• Понимание: 9/5\n• Глубина: 3/5\n• Точность: 4/5\n"
        assert parse_assistant_grade(text) is None

    def test_empty_returns_none(self) -> None:
        assert parse_assistant_grade("") is None


class TestGradeUserResponse:
    def test_decline_returns_zero(self) -> None:
        result = grade_user_response(
            user_message="не знаю",
            assistant_text="",
            pass_threshold=50,
        )
        assert result["score_percent"] == 0
        assert result["category"] == "incorrect"
        assert result["is_decline"] is True
        assert result["has_grade"] is False

    def test_partial_answer_with_grade(self) -> None:
        text = "Оценка:\n• Понимание: 3/5\n• Глубина: 2/5\n• Точность: 3/5\n• Уровень: middle-\n"
        # ((3+2+3)/3)*20 + (-3) (middle- штрап) = 53 - 3 = 50
        # При threshold=50 это проходит как CORRECT.
        result = grade_user_response(
            user_message="через трединг",
            assistant_text=text,
            pass_threshold=50,
        )
        assert result["score_percent"] == 50
        assert result["category"] == "correct"
        assert result["is_decline"] is False
        assert result["has_grade"] is True

    def test_high_grade_above_threshold(self) -> None:
        text = "Оценка:\n• Понимание: 5/5\n• Глубина: 5/5\n• Точность: 5/5\n• Уровень: senior\n"
        result = grade_user_response(
            user_message="развёрнутый ответ",
            assistant_text=text,
            pass_threshold=50,
        )
        assert result["score_percent"] == 100
        assert result["category"] == "correct"

    def test_no_grade_block_is_incorrect(self) -> None:
        # Ассистент не выставил оценку (chat-промт «не оценивай»).
        # Берём нешаблонную фразу, чтобы не спутать с явным отказом.
        result = grade_user_response(
            user_message="расскажи подробнее про индексы",
            assistant_text="Подробно объяснил без блока оценки.",
            pass_threshold=50,
        )
        assert result["score_percent"] == 0
        assert result["category"] == "incorrect"
        assert result["has_grade"] is False
        assert result["is_decline"] is False

    def test_below_threshold_is_partial(self) -> None:
        text = "Оценка:\n• Понимание: 2/5\n• Глубина: 2/5\n• Точность: 2/5\n• Уровень: middle\n"
        result = grade_user_response(
            user_message="очень слабый ответ",
            assistant_text=text,
            pass_threshold=50,
        )
        # (2+2+2)/3*20 = 40 → PARTIAL (< 50)
        assert result["score_percent"] == 40
        assert result["category"] == "partial"

    def test_real_user_scenario_dont_know(self) -> None:
        """Пользователь: «забыл если честно». Ожидаем INCORRECT."""
        result = grade_user_response(
            user_message="забыл если честно",
            assistant_text="Тут нет прямого ответа, поэтому без оценки.",
            pass_threshold=50,
        )
        assert result["category"] == "incorrect"
        assert result["is_decline"] is True

    def test_real_user_scenario_partial_deadlock(self) -> None:
        """SELECT FOR UPDATE — частично правильный, как в жалобе."""
        text = "Оценка:\n• Понимание: 3/5\n• Глубина: 2/5\n• Точность: 3/5\n• Уровень: middle\n"
        result = grade_user_response(
            user_message="select for update можно использовать и блокировать записи",
            assistant_text=text,
            pass_threshold=50,
        )
        # ((3+2+3)/3)*20 + 0 = 53 → CORRECT
        assert result["score_percent"] == 53
        assert result["category"] == "correct"
