import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.settings = type(
            "S",
            (),
            {
                "sobes_topics": ["python", "db"],
                "sobes_counts_by_level": {"junior": [15, 18], "middle": [18, 22], "senior": [22, 25]},
                "sobes_pass_threshold_percent": 50,
                # required by other parts
                "cors_allow_origins": ["*"],
                "chat_max_message_length": 4000,
                "session_store_max_sessions": 10,
                "session_history_limit": 20,
                "ingest_interval_hours": 9999,
            },
        )()

        class Dummy:
            async def ping(self):
                return True

        _app.state.llm = Dummy()
        _app.state.qdrant = Dummy()
        yield

    app.router.lifespan_context = _lifespan

    with TestClient(app) as client:
        yield client


def test_sobes_config(client):
    r = client.get("/api/sobesedovanie/config")
    assert r.status_code == 200
    data = r.json()
    assert data["topics"] == ["python", "db"]
    assert data["counts_by_level"]["senior"] == [22, 25]
    assert data["pass_threshold"] == 50
