from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from src.core.config import Settings
from src.core.deps import decode_username_header
from src.db.writer import persist_design_answer, seed_design_scenarios_from_file
from src.features.design.api.models import SaveDesignScenarioRequest
from src.features.design.domain.library_repository import append_design_scenario
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


def _service(request: Request) -> DesignService:
    return DesignService(
        request.app.state.settings,
        request.app.state.llm,
        _store_get(),
        checkpointer=getattr(request.app.state, "design_checkpointer", None),
    )


@router.post("/design/library/scenarios")
async def save_library_scenario(request: Request, body: SaveDesignScenarioRequest):
    """Сохраняет новый сценарий в YAML-библиотеку и сразу добавляет его в PostgreSQL."""
    settings: Settings = request.app.state.settings
    library_path = Path(settings.design_library_path)
    try:
        result = await append_design_scenario(
            library_path,
            title=body.title,
            summary=body.summary,
            level=body.level,
            category=body.category,
            requirements=body.requirements,
            nfr=body.nfr,
            constraints=body.constraints,
            acceptance_criteria=body.acceptance_criteria,
            topics=body.topics,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result["status"] == "saved":
        try:
            await seed_design_scenarios_from_file(library_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Сценарий сохранён в YAML, но не добавлен в базу данных") from exc
    return result


@router.get("/design/config", response_model=DesignConfigResponse)
async def config(request: Request):
    settings: Settings = request.app.state.settings
    service = _service(request)
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
    service = _service(request)
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
    service = _service(request)
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
        try:
            ctx = await service.step_persist_context(body.session_id, body.step_id)
        except Exception:
            ctx = None
        if ctx is not None:
            background.add_task(
                persist_design_answer,
                username=username,
                external_session_id=body.session_id,
                scenario_id=ctx["scenario_id"],
                step_id=body.step_id,
                step_title=ctx["step_title"],
                user_answer=body.user_answer,
                score_percent=score,
                rubric=rubric,
                pass_threshold=int(getattr(settings, "design_pass_threshold_percent", 50)),
                covered_points=list(covered or []),
                missed_points=list(missed or []),
                techlead_explanation=expl,
                hint_used=ctx["hint_used"],
                level=ctx["level"],
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
    service = _service(request)
    try:
        text, penalty = await service.hint(body.session_id, body.step_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DesignHintResponse(hint=text, penalty_applied_percent=penalty)


@router.get("/design/results/{session_id}", response_model=DesignResultsResponse)
async def results(request: Request, session_id: str):
    service = _service(request)
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
    service = _service(request)
    detail = await service.scenario_detail(scenario_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Сценарий не найден")
    return DesignScenarioDetailDTO(**detail)
