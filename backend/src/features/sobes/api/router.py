from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from src.core.config import Settings
from src.core.deps import decode_username_header
from src.db.writer import persist_sobes_answer
from src.features.chat.providers.ollama import OllamaClient
from src.features.sobes.domain.models import (
    SobesAnswerRequest,
    SobesAnswerResponse,
    SobesQuestionDTO,
    SobesRepeatRequest,
    SobesRepeatResponse,
    SobesResultsResponse,
    SobesSkipRequest,
    SobesSkipResponse,
    SobesStartRequest,
    SobesStartResponse,
)
from src.features.sobes.domain.services import SobesService, SobesSessionStore

router = APIRouter()


@router.get("/sobesedovanie/config")
async def get_config(request: Request):
    settings: Settings = request.app.state.settings
    return {
        "topics": settings.sobes_topics,
        "counts_by_level": settings.sobes_counts_by_level,
        "pass_threshold": settings.sobes_pass_threshold_percent,
    }


def _build_qdto(settings, q) -> SobesQuestionDTO:
    """Строит DTO из SobesQuestion, используя обогащённый текст если он есть."""
    text = getattr(q, "text_enriched", None) or q.text
    return SobesQuestionDTO(
        id=q.id,
        number=q.number,
        text=text,
        topic=q.topic,
        level=q.level,  # type: ignore[arg-type]
        difficulty_score=q.difficulty_score,
        topic_hint=(
            getattr(settings, "sobes_topic_hints", {}).get(q.topic)
            if getattr(settings, "sobes_show_topic_hint", True)
            else None
        ),
    )


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
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # q приходит из сервиса как SobesQuestionDTO; защищаемся, если кто-то вернул dataclass.
    q_dto = q if isinstance(q, SobesQuestionDTO) else _build_qdto(settings, q)
    return SobesStartResponse(
        session_id=sess.session_id,
        question=q_dto,
        total_planned=sess.planned_total,
    )


@router.post("/sobesedovanie/answer", response_model=SobesAnswerResponse)
async def answer(
    request: Request,
    body: SobesAnswerRequest,
    background: BackgroundTasks,
    x_username: Annotated[str | None, Header(alias="X-Username")] = None,
):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = SobesService(settings, llm, _store())

    try:
        percent, counted, expl, covered, missed, next_q, is_last = await service.answer(
            body.session_id, body.question_id, body.user_answer
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    next_q_dto: SobesQuestionDTO | None = None
    if next_q is not None:
        next_q_dto = _build_qdto(settings, next_q)

    # Сохраняем в статистику (фоновая задача)
    username = decode_username_header(x_username) or None
    if username:
        # Ищем текущий вопрос в сессии до инкремента current_index
        from src.features.sobes.domain.services import SobesSession  # noqa: F401

        sess = _store().get(body.session_id)
        cur_text = body.user_answer
        cur_topic = ""
        cur_ref = ""
        cur_level: str | None = None
        if sess is not None:
            cur_level = sess.level_requested
            idx = max(0, sess.current_index - 1)
            if 0 <= idx < len(sess.questions):
                q = sess.questions[idx]
                cur_text = q.text
                cur_topic = q.topic
            # Референсный ответ достаём через тот же путь, что и сервис
            try:
                from src.features.sobes.domain.repository import load_qa

                all_qa, _ = load_qa(settings)
                ref_obj = next(
                    (
                        x
                        for x in all_qa
                        if x.number == (sess.questions[idx].number if 0 <= idx < len(sess.questions) else -1)
                    ),
                    None,
                )
                if ref_obj is not None:
                    cur_ref = ref_obj.answer
            except Exception:
                pass

        background.add_task(
            persist_sobes_answer,
            username=username,
            external_session_id=body.session_id,
            question_text=cur_text,
            topic=cur_topic or "other",
            user_answer=body.user_answer,
            reference_answer=cur_ref,
            score_percent=percent,
            is_counted=counted,
            pass_threshold=int(getattr(settings, "sobes_pass_threshold_percent", 50)),
            techlead_explanation=expl,
            covered_points=list(covered or []),
            missed_points=list(missed or []),
            level=cur_level,
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SobesResultsResponse(
        level_requested=level_req,  # type: ignore[arg-type]
        verdict_level=verdict,  # type: ignore[arg-type]
        summary=summary,
        strengths=strengths,
        weaknesses=weaknesses,
        by_topic=by_topic,
        details=details,
    )


@router.post("/sobesedovanie/skip", response_model=SobesSkipResponse)
async def skip(request: Request, body: SobesSkipRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = SobesService(settings, llm, _store())
    try:
        next_q, is_last = service.skip(body.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    next_q_dto: SobesQuestionDTO | None = None
    if next_q is not None:
        next_q_dto = _build_qdto(settings, next_q)
    return SobesSkipResponse(next_question=next_q_dto, is_last=is_last)


@router.post("/sobesedovanie/repeat", response_model=SobesRepeatResponse)
async def repeat(request: Request, body: SobesRepeatRequest):
    settings: Settings = request.app.state.settings
    llm: OllamaClient = request.app.state.llm
    service = SobesService(settings, llm, _store())
    try:
        cur = service.repeat(body.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    qdto = _build_qdto(settings, cur)
    return SobesRepeatResponse(question=qdto)
