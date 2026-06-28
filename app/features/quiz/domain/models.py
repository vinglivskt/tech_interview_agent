# Pydantic-модели для quiz-режима.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Уровни сложности квиза
QuizLevel = Literal["junior", "middle", "senior"]


class QuizStartRequest(BaseModel):
    """
    Запрос на старт нового квиза.
    """

    level: QuizLevel = Field(
        default="middle",
        description="Уровень сложности вопросов (junior/middle/senior)",
    )


class QuizQuestionResponse(BaseModel):
    """
    Ответ с вопросом квиза (без указания правильного варианта).
    """

    session_id: str = Field(..., description="Идентификатор сессии квиза")
    question_id: str = Field(..., description="Уникальный идентификатор вопроса в сессии")
    question_text: str = Field(..., description="Текст вопроса")
    options: list[str] = Field(..., min_length=4, max_length=4, description="Четыре варианта ответа")
    question_number: int = Field(..., ge=1, description="Номер вопроса в квизе (1-based)")
    total_questions: int = Field(..., ge=1, description="Общее количество вопросов в квизе")


class QuizAnswerRequest(BaseModel):
    """
    Запрос на отправку ответа пользователя.
    """

    session_id: str = Field(..., min_length=1, description="Идентификатор сессии квиза")
    question_id: str = Field(..., min_length=1, description="Идентификатор вопроса")
    selected_index: int = Field(..., ge=0, le=3, description="Индекс выбранного варианта (0-3)")


class QuizAnswerResponse(BaseModel):
    """
    Ответ на отправку ответа: правильность, объяснение и следующий вопрос (если есть).
    """

    is_correct: bool = Field(..., description="Правильный ли ответ")
    correct_index: int = Field(..., ge=0, le=3, description="Индекс правильного ответа")
    explanation: str = Field(..., description="Объяснение правильного ответа")
    next_question: QuizQuestionResponse | None = Field(default=None, description="Следующий вопрос (если есть)")
    is_last: bool = Field(..., description="Был ли это последний вопрос в квизе")


class QuizQuestionResult(BaseModel):
    """
    Результат по одному вопросу квиза.
    """

    question_text: str = Field(..., description="Текст вопроса")
    user_answer: str = Field(..., description="Ответ пользователя (текст)")
    correct_answer: str = Field(..., description="Правильный ответ (текст)")
    is_correct: bool = Field(..., description="Правильный ли ответ")
    explanation: str = Field(..., description="Объяснение правильного ответа")


class QuizResultsResponse(BaseModel):
    """
    Итоговые результаты квиза.
    """

    total_score: int = Field(..., ge=0, description="Количество правильных ответов")
    total_questions: int = Field(..., ge=1, description="Общее количество вопросов")
    level: QuizLevel = Field(..., description="Уровень сложности")
    results: list[QuizQuestionResult] = Field(..., description="Результаты по каждому вопросу")
