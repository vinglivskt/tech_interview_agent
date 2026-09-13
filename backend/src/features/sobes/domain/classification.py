from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.core.structured import ClassificationBatch
from src.features.chat.domain.interview_docx import InterviewQA
from src.features.chat.providers.ollama import OllamaClient


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
    *,
    use_structured: bool = False,
) -> list[ClassifiedQA]:
    """
    Классифицирует список QA по темам/уровню через LLM. Возвращает безопасно распарсенный список.
    При ошибках — деградирует к topic="other", level="middle", difficulty_score=0.5.

    ``use_structured=True`` использует LangChain structured output
    (``OllamaClient.generate_structured`` c ``ClassificationBatch``); при сбое —
    фолбэк на ``generate(format="json")`` + позиционный парсинг.
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

    metadata = {"feature": "sobes", "kind": "classification"}
    try:
        if use_structured and hasattr(llm, "generate_structured"):
            rows = await llm.generate_structured(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                schema=ClassificationBatch,
                temperature=0.1,
                metadata=metadata,
                tags=["classification"],
            )
            if rows is not None:
                out: list[ClassifiedQA] = []
                for i, it in enumerate(items):
                    row = rows[i] if i < len(rows) else None
                    topic = row.topic if row else "other"
                    if topic not in topics:
                        topic = "other"
                    out.append(
                        ClassifiedQA(
                            number=it.number,
                            question=it.question,
                            answer=it.answer,
                            topic=topic,
                            level=row.level if row else "middle",
                            difficulty_score=row.difficulty_score if row else 0.5,
                        )
                    )
                return out
        text = await llm.generate(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            metadata=metadata,
            tags=["classification"],
            format="json",
        )
        data = json.loads(text)
        out = []
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
