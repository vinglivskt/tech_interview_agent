from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.config import Settings
from app.features.chat.providers.ollama import OllamaClient

from ..domain.models import (
    DesignAnswerRequest,
    DesignAnswerResponse,
    DesignConfigResponse,
    DesignHintRequest,
    DesignHintResponse,
    DesignResultsResponse,
    DesignStartRequest,
    DesignStartResponse,
)
from ..domain.scenarios import load_scenarios
from ..domain.services import DesignService, DesignSessionStore

router = APIRouter()

_store: DesignSessionStore | None = None


def _store_get() -> DesignSessionStore:
    global _store
    if _store is None:
        _store = DesignSessionStore()
    return _store


@router.get("/design/config", response_model=DesignConfigResponse)
async def config(request: Request):
    settings: Settings = request.app.state.settings
    scens = load_scenarios(settings)
    scenarios = [{"id": s.id, "title": s.title, "level": s.level} for s in scens]
    return DesignConfigResponse(
        levels=getattr(settings, "design_levels", ["junior", "middle", "senior"]),
        scenarios=scenarios,
        hint_penalty_percent=getattr(settings, "design_hint_penalty_percent", 10),
    )


@router.post("/design/start", response_model=DesignStartResponse)
async def start(request: Request, body: DesignStartRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    try:
        sess, scenario_info, step_info = await service.start(body.level, body.scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DesignStartResponse(
        session_id=sess.session_id,
        total_steps=len(sess.steps_order),
        scenario=scenario_info,
        step=step_info,  # type: ignore[arg-type]
    )


@router.post("/design/answer", response_model=DesignAnswerResponse)
async def answer(request: Request, body: DesignAnswerRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    try:
        score, rubric, covered, missed, expl, next_step, is_last = await service.answer(
            body.session_id, body.step_id, body.user_answer
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DesignAnswerResponse(
        score_percent=score,
        rubric=rubric,
        covered_points=covered,
        missed_points=missed,
        techlead_explanation=expl,
        next_step=next_step,  # type: ignore[arg-type]
        is_last=is_last,
    )


@router.post("/design/hint", response_model=DesignHintResponse)
async def hint(request: Request, body: DesignHintRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    try:
        text, penalty = await service.hint(body.session_id, body.step_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DesignHintResponse(hint=text, penalty_applied_percent=penalty)


@router.get("/design/results/{session_id}", response_model=DesignResultsResponse)
async def results(request: Request, session_id: str):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    try:
        summary, by_rubric, strengths, weaknesses, details, verdict = service.results(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return DesignResultsResponse(
        summary=summary,
        by_rubric=by_rubric,
        strengths=strengths,
        weaknesses=weaknesses,
        details=details,
        verdict_level=verdict,  # type: ignore[arg-type]
    )
