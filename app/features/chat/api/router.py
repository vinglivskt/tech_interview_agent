# tech_interview_agent/app/features/chat/api/router.py
import random
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.features.chat.api.models.save_qa_request import SaveQARequest
from app.features.chat.domain.docx_repository import question_exists, save_question_answer
from app.features.chat.domain.interview_docx import load_interview_qa
from app.features.chat.domain.models import ChatRequest
from app.features.chat.domain.services import SessionStore, run_chat

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


@router.get("/interview/random-question")
async def random_question_endpoint(request: Request):
    """
    Возвращает случайный вопрос из docx-базы интервью.
    Формат ответа:
    {
        "number": int,
        "question": str,
        "total": int
    }
    """
    settings = request.app.state.settings
    docx_path = Path(settings.interview_docx_path)
    if not docx_path.exists():
        raise HTTPException(status_code=500, detail=f"Файл не найден: {docx_path}")

    items = load_interview_qa(docx_path)
    if not items:
        raise HTTPException(status_code=500, detail="В базе нет вопросов")

    qa = random.choice(items)
    return {"number": qa.number, "question": qa.question, "total": len(items)}
