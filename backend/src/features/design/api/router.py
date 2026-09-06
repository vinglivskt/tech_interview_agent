from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from src.core.config import Settings
from src.core.deps import decode_username_header
from src.db.writer import persist_design_answer
from src.features.chat.providers.ollama import OllamaClient
from src.features.design.domain.models import (
    DesignAnswerRequest,
    DesignAnswerResponse,
    DesignCategoryDTO,
    DesignConfigResponse,
    DesignHintRequest,
    DesignHintResponse,
    DesignResultsResponse,
    DesignScenarioBriefDTO,
    DesignScenarioDetailDTO,
    DesignStartRequest,
    DesignStartResponse,
)
from src.features.design.domain.services import DesignService, DesignSessionStore

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
    service = DesignService(settings, request.app.state.llm, _store_get())
    levels, scenarios, categories, total = await service.config()
    return DesignConfigResponse(
        levels=levels,  # type: ignore[arg-type]
        scenarios=[DesignScenarioBriefDTO(**s) for s in scenarios],
        categories=[DesignCategoryDTO(**c) for c in categories],
        total_scenarios=total,
        hint_penalty_percent=getattr(settings, "design_hint_penalty_percent", 10),
    )


@router.post("/design/start", response_model=DesignStartResponse)
async def start(request: Request, body: DesignStartRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    try:
        sess, scenario_info, step_info = await service.start(body.level, body.scenario_id, body.category, body.random)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DesignStartResponse(
        session_id=sess.session_id,
        total_steps=len(sess.steps_order),
        scenario=scenario_info,
        step=step_info,  # type: ignore[arg-type]
    )


@router.post("/design/answer", response_model=DesignAnswerResponse)
async def answer(
    request: Request,
    body: DesignAnswerRequest,
    background: BackgroundTasks,
    x_username: Annotated[str | None, Header(alias="X-Username")] = None,
):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    try:
        (
            score,
            rubric,
            covered,
            missed,
            expl,
            next_step,
            is_last,
            failure_questions,
            advanced_questions,
        ) = await service.answer(body.session_id, body.step_id, body.user_answer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    username = decode_username_header(x_username) or None
    if username:
        sess = _store_get().get(body.session_id)
        if sess is not None:
            try:
                scen = await service._scenario_by_id_for_session(sess)  # type: ignore[attr-defined]
                step_obj = next((st for st in scen.steps if st.id == body.step_id), None)
                step_title = step_obj.title if step_obj else ""
                scenario_id = scen.id
            except Exception:
                step_title = ""
                scenario_id = sess.scenario_id

            background.add_task(
                persist_design_answer,
                username=username,
                external_session_id=body.session_id,
                scenario_id=scenario_id,
                step_id=body.step_id,
                step_title=step_title,
                user_answer=body.user_answer,
                score_percent=score,
                rubric=rubric,
                pass_threshold=int(getattr(settings, "design_pass_threshold_percent", 50)),
                covered_points=list(covered or []),
                missed_points=list(missed or []),
                techlead_explanation=expl,
                hint_used=body.step_id in sess.hinted_steps,
                level=sess.level_requested,
            )

    return DesignAnswerResponse(
        score_percent=score,
        rubric=rubric,
        covered_points=covered,
        missed_points=missed,
        techlead_explanation=expl,
        next_step=next_step,  # type: ignore[arg-type]
        is_last=is_last,
        failure_questions=failure_questions,
        advanced_questions=advanced_questions,
    )


@router.post("/design/hint", response_model=DesignHintResponse)
async def hint(request: Request, body: DesignHintRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    try:
        text, penalty = await service.hint(body.session_id, body.step_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DesignHintResponse(hint=text, penalty_applied_percent=penalty)


@router.get("/design/results/{session_id}", response_model=DesignResultsResponse)
async def results(request: Request, session_id: str):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    try:
        summary, by_rubric, strengths, weaknesses, details, verdict = await service.results(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DesignResultsResponse(
        summary=summary,
        by_rubric=by_rubric,
        strengths=strengths,
        weaknesses=weaknesses,
        details=details,
        verdict_level=verdict,  # type: ignore[arg-type]
    )


@router.get("/design/scenarios/{scenario_id}", response_model=DesignScenarioDetailDTO)
async def scenario_detail(request: Request, scenario_id: str):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = DesignService(settings, llm, _store_get())
    detail = await service.scenario_detail(scenario_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    return DesignScenarioDetailDTO(**detail)
