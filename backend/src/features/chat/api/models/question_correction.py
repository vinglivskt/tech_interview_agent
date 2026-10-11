from pydantic import BaseModel, Field


class SuggestQuestionCorrectionRequest(BaseModel):
    number: int = Field(..., ge=1)
    llm_answer: str = Field(..., min_length=1, max_length=12000)


class SaveQuestionCorrectionRequest(BaseModel):
    original_question: str = Field(..., min_length=1, max_length=4000)
    question: str = Field(..., min_length=1, max_length=4000)
