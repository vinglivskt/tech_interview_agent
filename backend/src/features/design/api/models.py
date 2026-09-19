from pydantic import BaseModel, Field


class SaveDesignScenarioRequest(BaseModel):
    """Данные нового сценария для YAML-библиотеки системного дизайна."""

    title: str = Field(..., min_length=3, max_length=200)
    summary: str = Field(..., min_length=10, max_length=4000)
    level: str = Field(..., pattern="^(junior|middle|senior)$")
    category: str = Field(default="basics", min_length=1, max_length=64)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    nfr: list[str] = Field(default_factory=list, max_length=20)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=20)
    topics: list[str] = Field(default_factory=list, max_length=20)
