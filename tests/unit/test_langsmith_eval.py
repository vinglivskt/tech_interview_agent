from types import SimpleNamespace

from src.training.langsmith_eval import (
    SCORING_DATASET_NAME,
    build_scoring_examples,
    push_scoring_dataset,
)


def _design_record():
    return {
        "feature": "design",
        "step_title": "Data Storage",
        "step_expectations": "Выбор хранилищ",
        "user_answer": "PostgreSQL + Redis",
        "score_percent": 80,
        "techlead_explanation": "Логично.",
    }


def _sobes_record():
    return {
        "feature": "sobes",
        "question_text": "Что такое GIL?",
        "reference_answer": "Глобальная блокировка",
        "user_answer": "Один поток выполняет байткод",
        "score_percent": 60,
        "explanation": "Частично верно.",
    }


def test_build_scoring_examples_design_and_sobes():
    [design_ex, sobes_ex] = build_scoring_examples([_design_record(), _sobes_record()])
    assert design_ex["inputs"]["feature"] == "design"
    assert design_ex["inputs"]["question"] == "Data Storage"
    assert design_ex["inputs"]["reference"] == "Выбор хранилищ"
    assert design_ex["outputs"]["score_percent"] == 80
    assert design_ex["outputs"]["explanation"] == "Логично."
    assert set(design_ex["inputs"]) == {"feature", "question", "reference", "user_answer"}
    assert set(design_ex["outputs"]) == {"score_percent", "explanation"}

    assert sobes_ex["inputs"]["question"] == "Что такое GIL?"
    assert sobes_ex["outputs"]["score_percent"] == 60


def test_build_scoring_examples_skips_incomplete():
    records = [
        _sobes_record(),
        {"feature": "sobes", "question_text": "Пустой ответ", "user_answer": ""},
        {"feature": "sobes", "user_answer": "нет вопроса"},
        None,
        {},
    ]
    examples = build_scoring_examples(records)
    assert len(examples) == 1


def test_push_scoring_dataset_uses_examples():
    dataset = SimpleNamespace(id="ds-1")
    created: list[tuple] = []
    calls: list[tuple] = []

    class FakeClient:
        def create_dataset(self, dataset_name=None, description=None):
            calls.append(("create_dataset", dataset_name, description))
            return dataset

        def read_dataset(self, dataset_name=None):
            raise AssertionError("not expected")

        def create_example(self, **kwargs):
            created.append((kwargs["inputs"], kwargs["outputs"], kwargs["dataset_id"]))

    result = push_scoring_dataset(
        FakeClient(),
        records=[_design_record(), _sobes_record()],
    )
    assert calls[0][1] == SCORING_DATASET_NAME
    assert result["dataset_id"] == "ds-1"
    assert result["examples"] == 2
    assert len(created) == 2
    assert created[0][2] == "ds-1"


def test_push_scoring_dataset_reuses_existing():
    dataset = SimpleNamespace(id="ds-2")

    class FakeClient:
        def create_dataset(self, **kwargs):
            raise RuntimeError("already exists")

        def read_dataset(self, dataset_name=None):
            assert dataset_name == SCORING_DATASET_NAME
            return dataset

        def create_example(self, **kwargs):
            return None

    result = push_scoring_dataset(FakeClient(), records=[_sobes_record()])
    assert result["dataset_id"] == "ds-2"
    assert result["examples"] == 1