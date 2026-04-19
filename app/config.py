"""
Загрузка настроек приложения из переменных окружения и ``.env``.

Сценарий приложения: помощник по подготовке к Python собеседованиям на основе
RAG по файлу ``.docx`` (вопросы/ответы), который периодически обновляется вручную.
"""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация API, Qdrant, векторизации и источника docx."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_url: str = Field(
        default="http://localhost:11434", description="URL локального Ollama API"
    )
    ollama_model: str = Field(
        default="qwen2.5:7b", description="LLM для интервью-ассистента"
    )
    ollama_embed_model: str = Field(
        default="nomic-embed-text", description="Модель эмбеддингов в Ollama"
    )
    ollama_timeout_sec: float = Field(
        default=120.0, gt=0, description="Таймаут запросов к Ollama (сек)"
    )
    embedding_dim: int = Field(
        default=768, ge=1, description="Размерность эмбеддингов текущей модели"
    )
    embedding_batch_size: int = Field(
        default=16, ge=1, description="Размер батча при векторизации"
    )

    qdrant_url: str = Field(default="http://localhost:6333", description="URL Qdrant")
    qdrant_collection: str = Field(
        default="interview_qa", description="Коллекция Qdrant"
    )
    qdrant_shard_number: int = Field(
        default=2, ge=1, description="Число шардов при создании коллекции"
    )
    qdrant_replication_factor: int = Field(
        default=1, ge=1, description="Фактор репликации"
    )

    vectorization_max_chunk_chars: int = Field(
        default=1000, ge=1, description="Макс. длина фрагмента"
    )
    vectorization_overlap: int = Field(
        default=100, ge=0, description="Перекрытие соседних фрагментов"
    )

    interview_docx_path: str = Field(
        default="./Топ вопросов на собеседовании Python.docx",
        description="Путь к docx-файлу с вопросами и ответами",
    )
    ingest_state_path: str = Field(
        default="data/interview_ingest_state.json",
        description="Путь к файлу состояния индексации (хеш и время обновления)",
    )
    ingest_interval_hours: float = Field(
        default=1.0, gt=0, description="Период проверки обновления файла"
    )
    interview_top_k: int = Field(
        default=5, ge=1, le=20, description="Сколько фрагментов доставать из Qdrant"
    )

    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8000", "http://127.0.0.1:8000"],
        description="Список разрешённых origin для CORS",
    )
    chat_max_message_length: int = Field(
        default=4000, ge=1, description="Макс. длина сообщения пользователя"
    )
    session_history_limit: int = Field(
        default=20, ge=2, description="Сколько последних сообщений хранить в сессии"
    )
    session_store_max_sessions: int = Field(
        default=1000, ge=1, description="Макс. число сессий в памяти"
    )

    @field_validator(
        "ollama_url",
        "ollama_model",
        "ollama_embed_model",
        "qdrant_url",
        "qdrant_collection",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_cors_allow_origins(cls, value: str | list[str]) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
            return [item for item in items if item]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError(
            "cors_allow_origins must be a list[str] or comma-separated string"
        )

    @field_validator("interview_docx_path", "ingest_state_path", mode="before")
    @classmethod
    def _strip_paths(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _validate_settings(self) -> "Settings":
        if self.vectorization_overlap >= self.vectorization_max_chunk_chars:
            raise ValueError(
                "VECTORIZATION_OVERLAP must be less than VECTORIZATION_MAX_CHUNK_CHARS"
            )
        if "*" in self.cors_allow_origins and len(self.cors_allow_origins) > 1:
            raise ValueError("CORS wildcard cannot be combined with explicit origins")
        return self


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр ``Settings``."""
    return Settings()
