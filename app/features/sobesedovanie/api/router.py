from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.config import Settings
from app.features.chat.providers.ollama import OllamaClient

from ..domain.models import (
    SobesAnswerRequest,
    SobesAnswerResponse,
    SobesQuestionDTO,
    SobesResultsResponse,
    SobesStartRequest,
    SobesStartResponse,
)
from ..domain.services import SobesService, SobesSessionStore

router = APIRouter()

_s_store: SobesSessionStore | None = None


def _store() -> SobesSessionStore:
    global _s_store
    if _s_store is None:
        _s_store = SobesSessionStore()
    return _s_store


@router.post("/sobesedovanie/start", response_model=SobesStartResponse)
async def start(request: Request, body: SobesStartRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = SobesService(settings, llm, _store())
    try:
        sess, q = await service.start(body.level, body.topics)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return SobesStartResponse(session_id=sess.session_id, question=q, total_planned=sess.planned_total)


@router.post("/sobesedovanie/answer", response_model=SobesAnswerResponse)
async def answer(request: Request, body: SobesAnswerRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = SobesService(settings, llm, _store())

    try:
        percent, counted, expl, covered, missed, next_q, is_last = await service.answer(
            body.session_id, body.question_id, body.user_answer
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    next_q_dto: SobesQuestionDTO | None = None
    if next_q is not None:
        next_q_dto = SobesQuestionDTO(
            id=next_q.id,
            number=next_q.number,
            text=next_q.text,
            topic=next_q.topic,
            level=next_q.level,  # type: ignore[arg-type]
            difficulty_score=next_q.difficulty_score,
        )

    return SobesAnswerResponse(
        score_percent=percent,
        is_counted=counted,
        techlead_explanation=expl,
        covered_points=covered,
        missed_points=missed,
        next_question=next_q_dto,
        is_last=is_last,
    )


@router.get("/sobesedovanie/results/{session_id}", response_model=SobesResultsResponse)
async def results(request: Request, session_id: str):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = SobesService(settings, llm, _store())
    try:
        level_req, verdict, summary, strengths, weaknesses, by_topic, details = service.results(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return SobesResultsResponse(
        level_requested=level_req,  # type: ignore[arg-type]
        verdict_level=verdict,  # type: ignore[arg-type]
        summary=summary,
        strengths=strengths,
        weaknesses=weaknesses,
        by_topic=by_topic,
        details=details,
    )
