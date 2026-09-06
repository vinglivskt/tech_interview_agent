from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DesignLevel = Literal["junior", "middle", "senior"]


class DesignCategoryDTO(BaseModel):
    id: str
    title: str
    count: int


class DesignScenarioBriefDTO(BaseModel):
    id: str
    title: str
    level: str
    category: str = ""
    primary_pattern: str = ""
    summary: str = ""
    is_detailed: bool = False


class DesignConfigResponse(BaseModel):
    levels: list[DesignLevel]
    scenarios: list[DesignScenarioBriefDTO]
    categories: list[DesignCategoryDTO]
    total_scenarios: int
    hint_penalty_percent: int


class DesignStartRequest(BaseModel):
    level: DesignLevel
    scenario_id: str | None = None
    category: str | None = None
    random: bool = False


class DesignStepDTO(BaseModel):
    id: str = Field(..., description="идентификатор шага")
    title: str
    prompt: str


class DesignEvolutionLevelDTO(BaseModel):
    id: str
    name: str
    summary: str
    diagram: str
    prompts: list[str] = Field(default_factory=list)


class DesignScenarioDetailDTO(BaseModel):
    id: str
    title: str
    level: str
    category: str
    primary_pattern: str
    summary: str
    requirements: list[str]
    nfr: list[str]
    constraints: list[str]
    topics: list[str]
    tags: list[str]
    baseline_load: dict = Field(default_factory=dict)
    acceptance_criteria: list[str]
    evolution: list[DesignEvolutionLevelDTO]
    failure_questions: list[str]
    advanced_questions: list[str]


class DesignStartResponse(BaseModel):
    session_id: str
    total_steps: int
    scenario: dict  # {id,title,level,summary,category,primary_pattern,evolution,failure_questions}
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
    # Расширения
    failure_questions: list[str] = Field(default_factory=list)
    advanced_questions: list[str] = Field(default_factory=list)


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
