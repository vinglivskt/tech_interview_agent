"""Предлагает чёткую формулировку вопроса на основе ответа LLM."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.core.interfaces.llm import LLMGateway


class QuestionRewrite(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question", mode="before")
    @classmethod
    def _strip_question(cls, value: object) -> str:
        question = str(value or "").strip()
        if not question:
            raise ValueError("Предложенная формулировка вопроса пуста")
        return question


async def suggest_question_rewrite(
    llm: LLMGateway,
    *,
    number: int,
    question: str,
    llm_answer: str,
) -> str:
    """Возвращает один ясный вариант вопроса, не меняя его технический смысл."""
    result = await llm.generate_structured(
        [
            {
                "role": "system",
                "content": (
                    "Ты редактор вопросов для технических собеседований. Перепиши исходный вопрос "
                    "в ясную, грамматически законченную и естественную формулировку на русском "
                    "языке. Сохрани исходную техническую тему и проверяемые знания. Ответ LLM "
                    "используй только как контекст, чтобы понять, о чём спрашивали; не превращай "
                    "ответ в новый вопрос и не добавляй требования, на которые исходный вопрос "
                    "не намекал. Удали обрывки, дубли и неуместную формулу, если она не является "
                    "частью предмета вопроса. Верни один короткий связный вопрос без номера, "
                    "пояснений и кавычек."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Номер вопроса: {number}\n"
                    f"Исходный вопрос: {question.strip()}\n\n"
                    f"Ответ ассистента на этот вопрос:\n{llm_answer.strip()}"
                ),
            },
        ],
        schema=QuestionRewrite,
        temperature=0.2,
        max_tokens=300,
        metadata={"feature": "chat", "kind": "question-rewrite", "question_number": number},
        tags=["question-rewrite"],
    )
    if result is None:
        raise RuntimeError("Не удалось получить исправленную формулировку от модели")
    return result.question
