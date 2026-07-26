from pydantic import BaseModel, Field


class SaveQARequest(BaseModel):
    """
    Запрос на сохранение вопроса/ответа в docx.
    question — текст вопроса (то, что спросил пользователь),
    correct_answer — правильный ответ агента,
    session_id — идентификатор сессии (опционально).
    """

    question: str = Field(..., min_length=1, description="Текст вопроса для сохранения")
    correct_answer: str = Field(..., min_length=1, description="Правильный ответ")
    session_id: str = Field(default="default", min_length=1, description="Идентификатор диалога")
