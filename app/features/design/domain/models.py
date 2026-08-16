from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

DesignLevel = Literal["junior", "middle", "senior"]


class DesignConfigResponse(BaseModel):
    levels: list[DesignLevel]
    scenarios: list[dict]  # {id,title,level}
    hint_penalty_percent: int


class DesignStartRequest(BaseModel):
    level: DesignLevel
    scenario_id: Optional[str] = None


class DesignStepDTO(BaseModel):
    id: str = Field(..., description="идентификатор шага")
    title: str
    prompt: str


class DesignStartResponse(BaseModel):
    session_id: str
    total_steps: int
    scenario: dict  # {id,title,level,summary}
    step: DesignStepDTO


class DesignAnswerRequest(BaseModel):
    session_id: str
    step_id: str
    user_answer: str


class DesignAnswerResponse(BaseModel):
    score_percent: int
    rubric: dict[str, int] = Field(default_factory=dict)
    covered_points: list[str] = Field(default_factory=list)
    missed_points: list[str] = Field(default_factory=list)
    techlead_explanation: str
    next_step: DesignStepDTO | None = None
    is_last: bool = False


class DesignHintRequest(BaseModel):
    session_id: str
    step_id: str


class DesignHintResponse(BaseModel):
    hint: str
    penalty_applied_percent: int


class DesignResultsResponse(BaseModel):
    summary: dict
    by_rubric: dict
    strengths: list[str]
    weaknesses: list[str]
    details: list[dict]
    verdict_level: DesignLevel
