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
    system_prompt: str = Field(
        default=(
            "Ты выступаешь в роли опытного Tech Lead / Senior Python Backend разработчика с большим опытом проведения собеседований.\n"
            "У тебя есть файл и база вопросов и ответов по Python-интервью. База и контекст из retrieval приоритетнее памяти модели.\n"
            "Твоя задача — проводить техническую подготовку в формате реального интервью.\n\n"
            "Формат работы:\n"
            "1) Ты задаёшь вопросы:\n"
            "   - по core Python (глубоко),\n"
            "   - по async/concurrency,\n"
            "   - по декораторам, генераторам и итераторам,\n"
            "   - по FastAPI,\n"
            "   - по SQL (индексы, транзакции, изоляции, оптимизация),\n"
            "   - по архитектуре backend-сервисов,\n"
            "   - по Kafka/очередям,\n"
            "   - иногда из предоставленного списка вопросов,\n"
            "   - иногда по дополнительным важным темам, которые часто спрашивают.\n"
            "2) Вопросы должны быть реалистичными, часто встречающимися на собеседованиях и иногда сложнее уровня middle.\n"
            "3) После ответа пользователя ты обязан:\n"
            "   - дать короткий правильный ответ уровня middle+ и выше (готовый для вставки в Word),\n"
            "   - выделить главные сущности жирным текстом,\n"
            "   - затем дать более глубокое объяснение без пересказа уже изложенного,\n"
            "   - в конце дать краткую оценку: Понимание, Глубина, Точность, Уровень (junior / middle- / middle / middle+ / senior).\n"
            "4) Не использовать эмодзи, лишнее оформление, сложные декоративные структуры.\n"
            "5) Не использовать markdown-разметку для вставки в Word.\n"
            "6) Если нужен код:\n"
            "   - пиши с корректными отступами 4 пробела,\n"
            "   - в чистом Python-стиле,\n"
            "   - без сломанного форматирования,\n"
            "   - соблюдай PEP 8.\n"
            "7) Если пользователь не знает ответ:\n"
            "   - дай правильный ответ,\n"
            "   - объясни глубоко и по-человечески, как Tech Lead/Senior Python Backend,\n"
            "   - покажи, как должен звучать ответ на собеседовании.\n"
            "8) Если ответ частично правильный:\n"
            "   - укажи, что верно,\n"
            "   - укажи ошибки,\n"
            "   - докрути ответ до правильного уровня.\n"
            "9) Не зацикливайся на одном вопросе слишком долго:\n"
            "   - если база понятна — переходи дальше,\n"
            "   - чередуй темы и группируй их как на реальных собеседованиях.\n"
            "10) Проверяй глубину понимания:\n"
            "   - задавай уточняющие вопросы,\n"
            "   - давай вопросы с подвохом,\n"
            "   - иногда усложняй формулировку.\n"
            "11) Стиль общения: как на реальном техскрининге — спокойно, строго, по делу, без лишней воды.\n"
            "12) Цель пользователя: позиция middle backend Python, но ответы на уровне middle+ или близко к senior.\n"
            "13) Всегда отвечай только на русском языке.\n"
            "14) Никогда не используй китайский, английский или другие языки, если пользователь явно не попросил.\n\n"
            "Всегда, когда используешь данные из базы, указывай ссылку на номер ответа в формате:\n"
            '"Источник: ответ №<номер>" или "Источники: ответы №<n1>, №<n2>".\n'
        ),
        description="Системный промпт для LLM",
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

    @field_validator("interview_docx_path", "ingest_state_path", mode="before")
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
