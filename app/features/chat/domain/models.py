# tech_interview_agent/app/features/chat/domain/models.py
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Текст запроса пользователя")
    session_id: str = Field(default="default", min_length=1, description="Идентификатор диалога")
