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

    # --- LLM поведения/промпт ---
    system_prompt_path: str = Field(
        default="/app/prompts/chat/system.md",
        description="Путь к файлу системного промпта (markdown)",
    )
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1024, ge=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_url: str = Field(default="http://localhost:11434", description="URL локального Ollama API")
    ollama_model: str = Field(default="qwen2.5:7b", description="LLM для интервью-ассистента")
    ollama_embed_model: str = Field(default="nomic-embed-text", description="Модель эмбеддингов в Ollama")
    ollama_timeout_sec: float = Field(default=120.0, gt=0, description="Таймаут запросов к Ollama (сек)")
    embedding_dim: int = Field(default=768, ge=1, description="Размерность эмбеддингов текущей модели")
    embedding_batch_size: int = Field(default=16, ge=1, description="Размер батча при векторизации")

    qdrant_url: str = Field(default="http://localhost:6333", description="URL Qdrant")
    qdrant_collection: str = Field(default="interview_qa", description="Коллекция Qdrant")
    qdrant_shard_number: int = Field(default=2, ge=1, description="Число шардов при создании коллекции")
    qdrant_replication_factor: int = Field(default=1, ge=1, description="Фактор репликации")

    vectorization_max_chunk_chars: int = Field(default=1000, ge=1, description="Макс. длина фрагмента")
    vectorization_overlap: int = Field(default=100, ge=0, description="Перекрытие соседних фрагментов")

    interview_docx_path: str = Field(
        default="/app/app/interview_questions.docx",
        description="Путь к docx-файлу с вопросами и ответами",
    )
    ingest_state_path: str = Field(
        default="data/interview_ingest_state.json",
        description="Путь к файлу состояния индексации (хеш и время обновления)",
    )
    ingest_interval_hours: float = Field(default=1.0, gt=0, description="Период проверки обновления файла")
    interview_top_k: int = Field(default=5, ge=1, le=20, description="Сколько фрагментов доставать из Qdrant")

    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8000", "http://127.0.0.1:8000"],
        description="Список разрешённых origin для CORS",
    )
    chat_max_message_length: int = Field(default=4000, ge=1, description="Макс. длина сообщения пользователя")
    session_history_limit: int = Field(default=20, ge=2, description="Сколько последних сообщений хранить в сессии")
    session_store_max_sessions: int = Field(default=1000, ge=1, description="Макс. число сессий в памяти")

    # --- Режим «собеседование» ---
    sobes_topics: list[str] = Field(
        default_factory=lambda: [
            "python",
            "db",
            "networks",
            "brokers",
            "os",
            "algorithms",
            "patterns",
            "testing",
            "devops",
            "security",
            "other",
        ],
        description="Поддерживаемые темы собеседования",
    )
    sobes_counts_by_level: dict[str, list[int]] = Field(
        default_factory=lambda: {
            "junior": [15, 18],
            "middle": [18, 22],
            "senior": [22, 25],
        },
        description="Диапазоны количества вопросов по уровням (min,max)",
    )
    sobes_pass_threshold_percent: int = Field(default=50, ge=0, le=100, description="Порог засчёта ответа в процентах")
    sobes_cache_path: str = Field(
        default="data/sobes_index.json",
        description="Путь к кэшу классифицированной базы QA",
    )
    sobes_max_explanation_len: int = Field(default=600, ge=50, description="Максимальная длина пояснения техлида")
    sobes_show_topic_hint: bool = Field(default=True, description="Показывать краткую подсказку по теме перед ответом")
    sobes_topic_hints: dict[str, str] = Field(
        default_factory=lambda: {
            "python": "вспомни различия list/tuple/set/dict, мутабельность, ссылки vs копии, areas: GIL, ООП, итераторы/генераторы",
            "db": "базовые типы индексов, нормальные формы, транзакции и уровни изоляции, explain/анализ запросов",
            "networks": "TCP vs UDP, 3-way handshake, TLS, HTTP/2 и keep-alive, пулы соединений",
            "brokers": "pub/sub vs queue, at-least-once/at-most-once/exactly-once, партиции и оффсеты",
            "os": "процессы/потоки, планировщик, межпроцессное взаимодействие, файловые дескрипторы",
            "algorithms": "сложности O(), структуры данных: хеш-таблица, дерево, граф, очередь, стек",
            "patterns": "SOLID, зависимости, фабрики, стратегия, адаптер, фасад и их уместность",
            "testing": "пирамиды тестирования, фикстуры, мок/стаб, given-when-then, изоляция",
            "devops": "контейнеры, базовые сети docker, CI/CD, мониторинг и алерты",
            "security": "OWASP Top 10, инъекции, XSS/CSRF, хранение секретов",
            "other": "уточни контекст и ожидаемый уровень глубины ответа",
        },
        description="Подсказки по темам для режима собеседования",
    )

    # --- Режим «системный дизайн» ---
    design_levels: list[str] = Field(
        default_factory=lambda: ["junior", "middle", "senior"],
        description="Доступные уровни сценариев системного дизайна",
    )
    design_hint_penalty_percent: int = Field(default=10, ge=0, le=100)
    design_pass_threshold_percent: int = Field(default=50, ge=0, le=100)
    design_max_explanation_len: int = Field(default=600, ge=50)
    design_scenarios_path: str = Field(
        default="prompts/design/scenarios.yaml",
        description="Путь к YAML-файлу со сценариями системного дизайна",
    )
    design_max_tokens: int = Field(default=800, ge=1)

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
        raise TypeError("cors_allow_origins must be a list[str] or comma-separated string")

    @field_validator("interview_docx_path", "ingest_state_path", "design_scenarios_path", mode="before")
    @classmethod
    def _strip_paths(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _validate_settings(self) -> "Settings":
        if self.vectorization_overlap >= self.vectorization_max_chunk_chars:
            raise ValueError("VECTORIZATION_OVERLAP must be less than VECTORIZATION_MAX_CHUNK_CHARS")
        if "*" in self.cors_allow_origins and len(self.cors_allow_origins) > 1:
            raise ValueError("CORS wildcard cannot be combined with explicit origins")
        return self


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр ``Settings``."""
    return Settings()
