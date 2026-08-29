import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.src.main import app


class DummyLLM:
    async def ping(self):
        return True

    async def generate(self, messages, **kwargs):
        # Detect classification vs scoring by system prompt
        system = messages[0]["content"].lower() if messages else ""
        user = messages[-1]["content"] if messages else ""
        if "классификатор" in system:
            # Extract JSON array from the user content
            m = re.search(r"(\[.*\])", user, re.S)
            arr = []
            if m:
                try:
                    arr = json.loads(m.group(1))
                except Exception:
                    arr = []
            out = []
            for it in arr:
                out.append(
                    {
                        "number": it.get("number", 0),
                        "topic": "python",
                        "level": "middle",
                        "difficulty_score": 0.3,
                    }
                )
            return json.dumps(out, ensure_ascii=False)
        else:
            # scoring
            return json.dumps(
                {
                    "score_percent": 80,
                    "covered_points": ["ключ 1", "ключ 2"],
                    "missed_points": ["деталь"],
                    "techlead_explanation": "Ответ в целом верный, но не хватает деталей.",
                },
                ensure_ascii=False,
            )

    async def embed(self, texts):
        return [[0.0] * 768 for _ in texts]


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Patch lifespan to avoid real services and to provide settings for sobes
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.settings = type(
            "S",
            (),
            {
                # base
                "chat_max_message_length": 4000,
                "cors_allow_origins": ["*"],
                "session_store_max_sessions": 10,
                "session_history_limit": 20,
                "ingest_interval_hours": 9999,
                "interview_top_k": 5,
                # sobes config
                "sobes_topics": ["python", "db", "networks", "brokers", "other"],
                "sobes_counts_by_level": {"junior": [2, 3], "middle": [3, 4], "senior": [4, 5]},
                "sobes_pass_threshold_percent": 50,
                "sobes_cache_path": str(tmp_path / "sobes_cache.json"),
                "sobes_max_explanation_len": 300,
                # docx
                "interview_docx_path": str(Path(__file__).resolve().parents[1] / "fixtures" / "test_interview_questions.docx"),
            },
        )()
        _app.state.llm = DummyLLM()

        # qdrant не используется в sobes API, но оставим мок для других роутов
        class DummyVector:
            async def ping(self):
                return True

            async def ensure_collection(self):
                return None

            async def search(self, *_, **__):
                return []

        _app.state.qdrant = DummyVector()
        yield

    app.router.lifespan_context = _lifespan

    with TestClient(app) as client:
        yield client


def test_sobes_flow(client):
    # 1) start
    r = client.post("/api/sobesedovanie/start", json={"level": "middle"})
    assert r.status_code == 200
    data = r.json()
    assert "session_id" in data and "question" in data
    session_id = data["session_id"]
    q = data["question"]
    assert q["text"]

    # 2) answer
    r2 = client.post(
        "/api/sobesedovanie/answer",
        json={
            "session_id": session_id,
            "question_id": q["id"],
            "user_answer": "мой ответ",
        },
    )
    assert r2.status_code == 200
    a = r2.json()
    assert 0 <= a["score_percent"] <= 100
    assert isinstance(a["techlead_explanation"], str)

    # 3) results
    r3 = client.get(f"/api/sobesedovanie/results/{session_id}")
    assert r3.status_code == 200
    res = r3.json()
    assert "summary" in res and "verdict_level" in res
