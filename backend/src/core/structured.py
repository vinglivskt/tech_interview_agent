"""Pydantic-схемы структурного вывода (structured output) для LLM-скоринга.

Уровень B LangChain-сценария: вместо ручного ``json.loads`` + ретраев LLM
получает JSON-схему (Ollama structured output API) и возвращает уже
валидированный Pydantic-объект. Валидация рубрик, лимитов списков и клампов
перенесена сюда из ``parse_score``/sobes-парсинга; legacy-парсеры остаются
фолбэком и используют ту же эталонную логику.

Схемы не зависят от сети и тестируются офлайн. Используются вместе с
``OllamaClient.generate_structured`` (обёртка над ``ChatOllama.with_structured_output``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, TypeAdapter, field_validator

# Ключи рубрики дизайна — совместимость со статистикой и промптами (не менять).
RUBRIC_KEYS = frozenset({"reqs", "arch", "data", "scale", "tradeoffs"})
MAX_POINTS = 6

__all__ = [
    "ClassificationBatch",
    "ClassificationRow",
    "DesignScore",
    "ScoreResult",
]


def _clamp_0_100(value: object) -> int:
    """Те же границы, что в legacy-парсерах: 0..100, без жёсткой ошибки на диапазон."""
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
    """Оценка шага системного дизайна: баллы + рубрика + пункты + пояснение.

    ``rubric`` обязан содержать ровно ключи requis…/tradeoffs — иначе validation
    error, и вызывающий код фолбэчит на legacy-ретраи (то же, что ``parse_score``).
    """

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

    def to_legacy_tuple(
        self, max_expl_len: int
    ) -> tuple[int, dict[str, int], list[str], list[str], str]:
        """Превращает валидированный объект в кортеж формата ``parse_score``."""
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


# Батч классификаций: тип, который `with_structured_output` умеет конвертировать
# в JSON-схему массива и парсить обратно в ``list[ClassificationRow]``.
ClassificationBatch = TypeAdapter(list[ClassificationRow])