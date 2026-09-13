"""Скэффолд регрессионных эвалов скоринга в LangSmith.

Трассировка (фаза 1) пишет каждый LLM-вызов в LangSmith. Этот модуль — задел
фазы 4 экосистемного плана: учит из реальных записей ответов (design/sobes) собирать
датасет «кейс → ожидаемая оценка техлида» и выгружать его в LangSmith для прогона
эвалов после правок промптов скоринга.

Функции разделены на «чистые» (офлайн-тестируемые, без сети) и тонкий pusher поверх
``langsmith.Client``-совместимого объекта (в тестах — фейк).
"""

from __future__ import annotations

from typing import Any

SCORING_DATASET_NAME = "scoring-regression"
SCORING_DATASET_DESCRIPTION = (
    "Регрессионные тесты скоринга (LLM-as-judge): кейс -> ожидаемая оценка техлида."
)


def build_scoring_examples(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Собирает примеры датасета из записей ответов (design/sobes формы).

    Каждая запись → пара ``inputs``/``outputs``:
      inputs:  feature, question, reference, user_answer
      outputs: score_percent, explanation

    Записи без вопроса/ответа пропускаются; лишние ключи не переносятся.
    """
    examples: list[dict[str, Any]] = []
    for rec in records:
        if not rec:
            continue
        question = (
            rec.get("question_text")
            or rec.get("question")
            or rec.get("step_title")
            or ""
        ).strip()
        user_answer = str(rec.get("user_answer") or "").strip()
        if not question or not user_answer:
            continue
        reference = (
            rec.get("reference_answer") or rec.get("step_expectations") or ""
        )
        explanation = (
            rec.get("techlead_explanation") or rec.get("explanation") or ""
        )
        examples.append(
            {
                "inputs": {
                    "feature": rec.get("feature"),
                    "question": question,
                    "reference": str(reference),
                    "user_answer": user_answer,
                },
                "outputs": {
                    "score_percent": rec.get("score_percent"),
                    "explanation": str(explanation),
                },
            }
        )
    return examples


def push_scoring_dataset(
    client: Any,
    *,
    records: list[dict[str, Any]],
    dataset_name: str = SCORING_DATASET_NAME,
) -> dict[str, Any]:
    """Создаёт (или дополняет существующий) датасет и выгружает примеры.

    ``client`` — объект, совместимый с ``langsmith.Client`` (create_dataset,
    read_dataset, create_example). Возвращает сводку по выгрузке.
    """
    examples = build_scoring_examples(records)
    try:
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description=SCORING_DATASET_DESCRIPTION,
        )
    except Exception:
        dataset = client.read_dataset(dataset_name=dataset_name)

    created = 0
    for ex in examples:
        client.create_example(
            inputs=ex["inputs"],
            outputs=ex["outputs"],
            dataset_id=dataset.id,
        )
        created += 1

    return {
        "dataset_name": dataset_name,
        "dataset_id": getattr(dataset, "id", None),
        "examples": created,
    }