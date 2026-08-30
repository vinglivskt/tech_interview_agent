from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

SobesLevel = Literal["junior", "middle", "senior"]


class SobesStartRequest(BaseModel):
    level: SobesLevel = Field(default="middle", description="Целевой уровень кандидата")
    topics: list[str] | None = Field(default=None, description="Приоритетные темы (опционально)")


class SobesQuestionDTO(BaseModel):
    id: str
    number: int
    text: str
    topic: str
    level: SobesLevel
    difficulty_score: float = Field(ge=0.0, le=1.0)
    topic_hint: str | None = None


class SobesStartResponse(BaseModel):
    session_id: str
    question: SobesQuestionDTO
    total_planned: int


class SobesAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    user_answer: str


class SobesAnswerResponse(BaseModel):
    score_percent: int = Field(ge=0, le=100)
    is_counted: bool
    techlead_explanation: str
    covered_points: list[str]
    missed_points: list[str]
    next_question: SobesQuestionDTO | None = None
    is_last: bool


class SobesResultsResponse(BaseModel):
    level_requested: SobesLevel
    verdict_level: SobesLevel
    summary: dict
    strengths: list[str]
    weaknesses: list[str]
    by_topic: list[dict]
    details: list[dict]


class SobesSkipRequest(BaseModel):
    session_id: str


class SobesSkipResponse(BaseModel):
    next_question: SobesQuestionDTO | None = None
    is_last: bool


class SobesRepeatRequest(BaseModel):
    session_id: str


class SobesRepeatResponse(BaseModel):
    question: SobesQuestionDTO


@dataclass
class SobesQuestion:
    id: str
    number: int
    text: str
    topic: str
    level: str
    difficulty_score: float
    text_enriched: str | None = None  # обогащённый вариант вопроса (отложенно заполняется LLM)


@dataclass
class SobesAnswerRecord:
    question_id: str
    question_text: str
    topic: str
    user_answer: str
    score_percent: int
    is_counted: bool
    techlead_explanation: str
    covered_points: list[str] = field(default_factory=list)
    missed_points: list[str] = field(default_factory=list)


@dataclass
class SobesSession:
    session_id: str
    level_requested: str
    planned_total: int
    questions: list[SobesQuestion]
    current_index: int = 0
    answers: list[SobesAnswerRecord] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
