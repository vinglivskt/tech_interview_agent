from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.features.chat.domain.interview_docx import InterviewQA
from app.features.chat.providers.ollama import OllamaClient


@dataclass
class ClassifiedQA:
    number: int
    question: str
    answer: str
    topic: str
    level: str  # junior|middle|senior
    difficulty_score: float  # 0..1


# Путь к файлу промпта
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "prompts" / "sobes" / "classification.md"


def _load_classification_prompt(topics: list[str]) -> str:
    """Загружает и подставляет темы в промпт классификации."""
    try:
        template = _PROMPT_PATH.read_text(encoding="utf-8")
        return template.replace("{topics}", ", ".join(topics))
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Prompt file not found: {_PROMPT_PATH}. Please ensure prompts/sobes/classification.md exists."
        ) from None


async def classify_batch(
    llm: OllamaClient,
    items: list[InterviewQA],
    topics: list[str],
) -> list[ClassifiedQA]:
    """
    Классифицирует список QA по темам/уровню через LLM. Возвращает безопасно распарсенный список.
    При ошибках — деградирует к topic="other", level="middle", difficulty_score=0.5.
    """
    if not items:
        return []

    system = _load_classification_prompt(topics)

    # Собираем компактный вход
    examples = [{"number": it.number, "question": it.question, "answer": it.answer[:400]} for it in items]

    user = (
        "Классифицируй список вопросов по темам и уровню. Верни JSON-массив тех же размеров, "
        "без лишних полей, порядок сохраняй. Важно: только JSON.\n" + json.dumps(examples, ensure_ascii=False)
    )

    try:
        text = await llm.generate(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
        )
        data = json.loads(text)
        out: list[ClassifiedQA] = []
        for i, it in enumerate(items):
            try:
                row = data[i]
                topic = str(row.get("topic", "other"))
                level = str(row.get("level", "middle"))
                diff = float(row.get("difficulty_score", 0.5))
                if topic not in topics:
                    topic = "other"
                if level not in ("junior", "middle", "senior"):
                    level = "middle"
                diff = min(1.0, max(0.0, diff))
                out.append(
                    ClassifiedQA(
                        number=it.number,
                        question=it.question,
                        answer=it.answer,
                        topic=topic,
                        level=level,
                        difficulty_score=diff,
                    )
                )
            except Exception:
                out.append(
                    ClassifiedQA(
                        number=it.number,
                        question=it.question,
                        answer=it.answer,
                        topic="other",
                        level="middle",
                        difficulty_score=0.5,
                    )
                )
        return out
    except Exception:
        return [
            ClassifiedQA(
                number=it.number,
                question=it.question,
                answer=it.answer,
                topic="other",
                level="middle",
                difficulty_score=0.5,
            )
            for it in items
        ]
