# tech_interview_agent/app/features/chat/api/router.py
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..domain.docx_repository import question_exists, save_question_answer
from ..domain.models import ChatRequest
from ..domain.services import SessionStore, run_chat

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    """
    Эндпоинт для проверки состояния сервисов (Qdrant и LLM).
    Возвращает статус и доступность внешних сервисов.
    """
    q = request.app.state.qdrant
    return {
        "status": "ok",
        "qdrant": await q.ping(),
        "ollama_available": await request.app.state.llm.ping(),
    }


@router.post("/chat")
async def chat_endpoint(
    request: Request,
    body: ChatRequest,
):
    """
    Эндпоинт для общения с ассистентом.
    Проверяет длину сообщения, сохраняет историю, вызывает LLM и возвращает ответ.
    """
    settings = request.app.state.settings
    sessions: SessionStore = request.app.state.sessions
    session_id = body.session_id.strip() or "default"
    message = body.message.strip()

    # Проверяем длину сообщения пользователя
    if len(message) > settings.chat_max_message_length:
        raise HTTPException(
            status_code=400,
            detail=f"Длина сообщения превышает лимит {settings.chat_max_message_length}",
        )

    history = sessions.get(session_id)

    answer, meta = await run_chat(
        settings,
        request.app.state.llm,  # LLMGateway
        request.app.state.qdrant,  # VectorStoreGateway
        message,
        history,
        embedder=request.app.state.llm,  # EmbeddingGateway (OllamaClient implements embed)
    )

    new_history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    sessions.save(session_id, new_history)

    return {"answer": answer, "meta": meta}


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


@router.post("/interview/save-qa")
async def save_qa_endpoint(
    request: Request,
    body: SaveQARequest,
):
    """
    Эндпоинт для сохранения вопроса/ответа в docx-файл интервью.
    Если вопрос уже есть в файле — возвращает skipped.
    Если вопрос новый — дописывает его в конец таблицы и возвращает saved.
    """
    settings = request.app.state.settings
    docx_path = Path(settings.interview_docx_path)

    question = (body.question or "").strip()
    answer = (body.correct_answer or "").strip()

    if not question:
        raise HTTPException(status_code=400, detail="Поле 'question' обязательно")
    if not answer:
        raise HTTPException(status_code=400, detail="Поле 'correct_answer' обязательно")

    if not docx_path.exists():
        raise HTTPException(status_code=500, detail=f"Файл не найден: {docx_path}")

    result = save_question_answer(docx_path, question, answer)
    return result


@router.get("/interview/question-exists")
async def question_exists_endpoint(
    request: Request,
    question: str = "",
):
    """
    Проверяет, есть ли вопрос в docx-файле интервью.
    Возвращает {"exists": true/false}.
    """
    settings = request.app.state.settings
    docx_path = Path(settings.interview_docx_path)

    if not question.strip():
        raise HTTPException(status_code=400, detail="Параметр 'query' обязателен")

    exists = question_exists(docx_path, question)
    return {"exists": exists}
