import pytest

from app.features.chat.domain.services import SessionStore


@pytest.fixture
def store():
    return SessionStore(max_sessions=2, max_messages_per_session=3, ttl_seconds=10)


def test_save_and_get(store):
    store.save("s1", [{"role": "user", "content": "hi"}])
    assert store.get("s1") == [{"role": "user", "content": "hi"}]


def test_ttl_pruning(store, monkeypatch):
    # фиксируем "текущее время" на момент сохранения
    monkeypatch.setattr("time.time", lambda: 1000)
    store.save("s1", [{"role": "user", "content": "a"}])

    # перематываем время вперёд за предел TTL
    monkeypatch.setattr("time.time", lambda: 1000 + 20)
    assert store.get("s1") == []
