import pytest
from fastapi.testclient import TestClient

from app.main import app


class DummyLLM:
    async def ping(self):
        return True

    async def generate(self, *_, **__):
        return "Ответ от LLM"

    async def embed(self, texts):
        return [[0.0] * 768 for _ in texts]


class DummyVector:
    async def ping(self):
        return True

    async def ensure_collection(self):
        return None

    async def search(self, *_, **__):
        return []

    async def upsert(self, *_, **__):
        return None


@pytest.fixture
def client(monkeypatch):
    # Patch the lifespan contextmanager used by the app, so startup doesn't hit real Ollama/Qdrant.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.settings = type(
            "S",
            (),
            {
                "chat_max_message_length": 4000,
                "cors_allow_origins": ["*"],
                "session_store_max_sessions": 10,
                "session_history_limit": 20,
                "ingest_interval_hours": 9999,
                "interview_top_k": 5,
            },
        )()
        _app.state.llm = DummyLLM()
        _app.state.qdrant = DummyVector()
        from app.features.chat.domain.services import SessionStore

        _app.state.sessions = SessionStore(
            max_sessions=10,
            max_messages_per_session=20,
            ttl_seconds=60,
        )
        yield

    app.router.lifespan_context = _lifespan

    with TestClient(app) as client:
        yield client


def test_chat_success(client):
    resp = client.post("/api/chat", json={"message": "Привет", "session_id": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Ответ от LLM"
    assert data["meta"]["used_rag"] is False
