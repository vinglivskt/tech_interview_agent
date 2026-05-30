# tech_interview_agent/app/features/chat/api/router.py
from fastapi import APIRouter, HTTPException, Request

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
