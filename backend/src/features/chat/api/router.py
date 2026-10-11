# tech_interview_agent/app/features/chat/api/router.py
import asyncio
import logging
import random
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from src.core.deps import decode_username_header
from src.db.writer import persist_chat_message
from src.features.chat.api.models.question_correction import (
    SaveQuestionCorrectionRequest,
    SuggestQuestionCorrectionRequest,
)
from src.features.chat.api.models.save_qa_request import SaveQARequest
from src.features.chat.domain.docx_repository import (
    question_exists,
    replace_question,
    save_question_answer,
)
from src.features.chat.domain.ingest import sync_interview_index
from src.features.chat.domain.interview_docx import load_interview_qa
from src.features.chat.domain.models import ChatRequest
from src.features.chat.domain.question_rewriter import suggest_question_rewrite
from src.features.chat.domain.services import SessionStore, run_chat

router = APIRouter()
logger = logging.getLogger(__name__)


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
    background: BackgroundTasks,
    x_username: Annotated[str | None, Header(alias="X-Username")] = None,
):
    """
    Эндпоинт для общения с ассистентом.
    Проверяет длину сообщения, сохраняет историю, вызывает LLM и возвращает ответ.
    Если передан `X-Username`, обе реплики (пользователя и ассистента) пишутся в статистику.
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
        question_type=body.question_type,
        metadata={"feature": "chat", "session_id": session_id, "question_type": body.question_type},
    )

    new_history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    sessions.save(session_id, new_history)

    # Запись в статистику (фоновая задача)
    username = decode_username_header(x_username) or None
    if username:
        # Для прямых вопросов пользователя не оцениваем (это не ответ на вопрос из RAG).
        # Помечаем в meta как kind=custom_question и не пишем score_percent/comprehension/...
        stats_meta = None
        if isinstance(meta, dict) and body.question_type == "direct_question":
            stats_meta = {
                "kind": "custom_question",
                "used_rag": meta.get("used_rag", False),
                "suggest_save": meta.get("suggest_save", False),
                "answer_numbers": meta.get("answer_numbers", []),
            }
        elif isinstance(meta, dict):
            stats_meta = meta

        background.add_task(
            persist_chat_message,
            username=username,
            session_key=session_id,
            role="user",
            content=message,
            meta=None,
        )
        background.add_task(
            persist_chat_message,
            username=username,
            session_key=session_id,
            role="assistant",
            content=answer,
            meta=stats_meta,
        )

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


@router.post("/interview/question/suggest-correction")
async def suggest_question_correction_endpoint(
    request: Request,
    body: SuggestQuestionCorrectionRequest,
):
    """Предлагает исправленную формулировку для вопроса из DOCX."""
    docx_path = Path(request.app.state.settings.interview_docx_path)
    if not await asyncio.to_thread(docx_path.exists):
        raise HTTPException(status_code=500, detail=f"Файл не найден: {docx_path}")
    items = await asyncio.to_thread(load_interview_qa, docx_path)
    qa = next((item for item in items if item.number == body.number), None)
    if qa is None:
        raise HTTPException(status_code=404, detail=f"Вопрос №{body.number} не найден")
    try:
        suggestion = await suggest_question_rewrite(
            request.app.state.llm,
            number=qa.number,
            question=qa.question,
            llm_answer=body.llm_answer,
        )
    except Exception as exc:
        logger.exception("Не удалось предложить редакцию вопроса №%d", body.number)
        raise HTTPException(
            status_code=502, detail="Не удалось подготовить вариант вопроса"
        ) from exc
    return {"number": qa.number, "original_question": qa.question, "suggestion": suggestion}


@router.put("/interview/question/{number}")
async def replace_question_endpoint(
    request: Request,
    number: int,
    body: SaveQuestionCorrectionRequest,
):
    """Сохраняет исправленный текст в существующую запись DOCX и обновляет RAG."""
    settings = request.app.state.settings
    docx_path = Path(settings.interview_docx_path)
    try:
        result = await asyncio.to_thread(
            replace_question,
            docx_path,
            number,
            body.question,
            expected_question=body.original_question,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result["status"] == "updated":
        try:
            await sync_interview_index(settings, request.app.state.qdrant)
        except Exception:
            logger.exception(
                "DOCX обновлён, но не удалось синхронизировать RAG после правки вопроса №%d",
                number,
            )
            result["index_status"] = "stale"
        else:
            result["index_status"] = "updated"
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
