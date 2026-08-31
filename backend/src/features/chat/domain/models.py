# tech_interview_agent/app/features/chat/domain/models.py
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """
    Сообщение чата (роль и текст).
    """

    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    """
    Запрос пользователя к ассистенту (текст и идентификатор сессии).
    """

    message: str = Field(..., min_length=1, description="Текст запроса пользователя")
    session_id: str = Field(default="default", min_length=1, description="Идентификатор диалога")
    question_type: Literal["answer", "direct_question"] = Field(
        default="answer",
        description="'answer' — Evaluate формат (Проверь мой ответ...). 'direct_question' — прямой ответ на вопрос.",
    )
