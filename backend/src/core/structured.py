"""Pydantic-схемы, используемые LangChain structured output для LLM-скоринга.

Провайдеры возвращают валидированные модели вместо текстового JSON. Сетевые
ошибки обрабатываются в вызывающей фиче безопасной деградацией.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Ключи рубрики дизайна — совместимость со статистикой и промптами (не менять).
RUBRIC_KEYS = frozenset({"reqs", "arch", "data", "scale", "tradeoffs"})
MAX_POINTS = 6

__all__ = [
    "ClassificationBatch",
    "ClassificationRow",
    "DesignScore",
    "ScoreResult",
    "WrongAnswers",
]


def _clamp_0_100(value: object) -> int:
    """Ограничивает числовую оценку диапазоном 0..100."""
    return max(0, min(100, int(value or 0)))


def _strings_only(value: object) -> list[str]:
    """Тот же срез, что в sobes-скоринге: до MAX_POINTS строк."""
    items = value if isinstance(value, list) else []
    return [str(item) for item in items][:MAX_POINTS]


class ScoreResult(BaseModel):
    """Оценка свободного ответа (sobes): баллы + пункты + пояснение техлида."""

    score_percent: int = Field(default=0)
    covered_points: list[str] = Field(default_factory=list)
    missed_points: list[str] = Field(default_factory=list)
    techlead_explanation: str = Field(default="")

    @field_validator("score_percent", mode="before")
    @classmethod
    def _clamp_score(cls, value: object) -> int:
        return _clamp_0_100(value)

    @field_validator("covered_points", "missed_points", mode="before")
    @classmethod
    def _cap_points(cls, value: object) -> list[str]:
        return _strings_only(value)

    @field_validator("techlead_explanation", mode="before")
    @classmethod
    def _stringify_explanation(cls, value: object) -> str:
        return str(value or "")


class DesignScore(BaseModel):
    """Оценка шага системного дизайна: баллы + рубрика + пункты + пояснение."""

    score_percent: int = Field(default=0)
    rubric: dict[str, int] = Field(default_factory=dict)
    covered_points: list[str] = Field(default_factory=list)
    missed_points: list[str] = Field(default_factory=list)
    techlead_explanation: str = Field(default="")

    @field_validator("score_percent", mode="before")
    @classmethod
    def _clamp_score(cls, value: object) -> int:
        return _clamp_0_100(value)

    @field_validator("rubric", mode="before")
    @classmethod
    def _validate_rubric(cls, value: object) -> dict[str, int]:
        if not isinstance(value, dict) or set(value) != RUBRIC_KEYS:
            raise ValueError(
                "Неверная рубрика: ожидаются ключи reqs/arch/data/scale/tradeoffs"
            )
        return {key: _clamp_0_100(val) for key, val in value.items()}

    @field_validator("covered_points", "missed_points", mode="before")
    @classmethod
    def _cap_points(cls, value: object) -> list[str]:
        return _strings_only(value)

    @field_validator("techlead_explanation", mode="before")
    @classmethod
    def _stringify_explanation(cls, value: object) -> str:
        return str(value or "")

    def to_scoring_tuple(
        self, max_expl_len: int
    ) -> tuple[int, dict[str, int], list[str], list[str], str]:
        """Преобразует модель в кортеж, который ожидают текущие API и статистика."""
        explanation = self.techlead_explanation.strip()[:max_expl_len]
        return (
            self.score_percent,
            dict(self.rubric),
            self.covered_points,
            self.missed_points,
            explanation,
        )


class ClassificationRow(BaseModel):
    """Классификация одного QA: тема / уровень / сложность.

    Заполняется LLM; номер/вопрос/ответ пользователь берёт из исходного списка.
    """

    topic: str = Field(default="other")
    level: str = Field(default="middle")
    difficulty_score: float = Field(default=0.5)

    @field_validator("topic", mode="before")
    @classmethod
    def _stringify_topic(cls, value: object) -> str:
        return str(value or "other")

    @field_validator("level", mode="before")
    @classmethod
    def _normalize_level(cls, value: object) -> str:
        level = str(value or "middle")
        return level if level in ("junior", "middle", "senior") else "middle"

    @field_validator("difficulty_score", mode="before")
    @classmethod
    def _clamp_difficulty(cls, value: object) -> float:
        return min(1.0, max(0.0, float(value or 0.5)))


class ClassificationBatch(BaseModel):
    """Батч классификаций; объектная оболочка совместима с JSON Schema API."""

    items: list[ClassificationRow] = Field(default_factory=list)


class WrongAnswers(BaseModel):
    """Три неправильных варианта для вопроса квиза."""

    items: list[str] = Field(min_length=3, max_length=3)
