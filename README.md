# tech_interview_agent — Vertical Slice Architecture (VSA)

Проект: FastAPI‑приложение «интервью‑ассистент» с RAG (Qdrant) и генерацией ответов через LLM (Ollama).

После миграции проект организован в стиле **Vertical‑Slice Architecture**: каждая фича живёт в своём «слайсе» и содержит всё необходимое (API → Domain → Providers → Infrastructure).

---

## Быстрый старт

### 1) Установка зависимостей

Проект использует `pyproject.toml`.

```bash
python3 -m pip install -e .
python3 -m pip install pytest
```

### 2) Запуск приложения

```bash
uvicorn app.main:app --reload
```

Откройте:

- `GET /` — фронтенд (`static/index.html`)
- `GET /api/health` — healthcheck
- `POST /api/chat` — чат

### 3) Запуск тестов

```bash
python3 -m pytest -q
```

---

## Структура проекта (после VSA‑миграции)

```
tech_interview_agent/
├─ app/
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ logger.py
│  │  ├─ exceptions.py
│  │  └─ interfaces/
│  │     ├─ llm.py
│  │     ├─ embeddings.py
│  │     └─ vectorstore.py
│  │
│  ├─ features/
│  │  └─ chat/
│  │     ├─ api/
│  │     │  └─ router.py
│  │     ├─ domain/
│  │     │  ├─ models.py
│  │     │  ├─ services.py
│  │     │  ├─ ingest.py
│  │     │  ├─ interview_docx.py
│  │     │  └─ vectorization.py
│  │     ├─ providers/
│  │     │  └─ ollama.py
│  │     └─ infrastructure/
│  │        └─ qdrant.py
│  │
│  ├─ shared/
│  │  ├─ dto/
│  │  ├─ enums/
│  │  └─ utils/
│  │
│  └─ main.py
│
├─ static/
├─ tests/
│  ├─ unit/
│  └─ integration/
└─ pyproject.toml
```

### Как читать слои

- **API** (`app/features/<feature>/api`) — FastAPI роутеры, валидация запросов/ответов, коды ошибок.
- **Domain** (`.../domain`) — бизнес‑логика фичи, DTO/модели домена, use‑cases.
- **Providers** (`.../providers`) — внешние провайдеры (LLM: Ollama/OpenAI/…); обычно HTTP‑клиенты.
- **Infrastructure** (`.../infrastructure`) — инфраструктура хранения/очередей/БД (Qdrant/Pg/Kafka/…)
- **Core** (`app/core`) — общие вещи: конфиг, логгер, интерфейсы (Protocol), исключения.
- **Shared** (`app/shared`) — общие утилиты/DTO, которые реально используются более чем одной фичей.

---

## Точка входа: `app/main.py`

`app/main.py` специально держится «тонким»:

1. Создаёт `FastAPI`.
2. В `lifespan`:
   - загружает `settings`
   - поднимает `llm` и `vectorstore`
   - выполняет первичный ingest (`sync_interview_index`)
   - запускает периодический ingest в фоне
   - кладёт зависимости в `app.state` (чтобы роутеры могли их брать через `request.app.state`)
3. Подключает роутеры фич: `app.include_router(chat_router, prefix="/api")`
4. Отдаёт статику.

---

## Фича `chat`

### API: `app/features/chat/api/router.py`

Эндпоинты:

- `GET /api/health`
  - проверяет доступность Qdrant и LLM.

- `POST /api/chat`
  - тело запроса:
    ```json
    {
      "message": "Привет",
      "session_id": "default"
    }
    ```
  - ответ:
    ```json
    {
      "answer": "...",
      "meta": {
        "used_rag": true,
        "retrieved_chunks": 5,
        "answer_numbers": [1, 2]
      }
    }
    ```

### Domain: `app/features/chat/domain/services.py`

Ключевой use‑case: `run_chat(...)`.

Алгоритм (упрощённо):

1. Делает retrieval из векторного стора (Qdrant):
   - получает эмбеддинг запроса
   - ищет топ‑K релевантных чанков
2. Собирает `system_prompt`:
   - базовый промпт берётся из `Settings.system_prompt`
   - добавляет RAG‑контекст и список найденных номеров ответов
3. Вызывает LLM через `llm.generate(messages)`.
4. Возвращает `answer` и `meta`.

### Ingest: `app/features/chat/domain/ingest.py`

`sync_interview_index(settings, qdrant)`:

- считает sha256 `.docx`
- если хеш не изменился — пропускает ingest
- иначе:
  - парсит docx (`interview_docx.py`)
  - режет на чанки (`vectorization.py`)
  - upsert в Qdrant
  - удаляет устаревшие точки по `doc_hash`
  - сохраняет state в `data/interview_ingest_state.json`

---

## Интерфейсы (Protocol)

Интерфейсы лежат в `app/core/interfaces/` и позволяют:

- легко мокать зависимости в тестах
- менять провайдера без переписывания доменной логики

### `LLMGateway` (`app/core/interfaces/llm.py`)

Минимальный контракт генерации:

- `ping() -> bool`
- `generate(messages, temperature?, max_tokens?, **kwargs) -> str`

### `EmbeddingGateway` (`app/core/interfaces/embeddings.py`)

Отдельный контракт для эмбеддингов:

- `embed(texts: list[str]) -> list[list[float]]`

### `VectorStoreGateway` (`app/core/interfaces/vectorstore.py`)

- `ensure_collection()`
- `upsert(vectors, payloads)`
- `search(query_vector, top_k)`
- `ping()`

---

## Конфигурация

Все настройки — в `app/config.py` (источник), а `app/core/config.py` — новый «официальный» путь импорта.

Главное:

- `SYSTEM_PROMPT` теперь хранится в `Settings.system_prompt`
- параметры генерации: `llm_temperature`, `llm_max_tokens`

Настройки читаются из `.env` (см. `SettingsConfigDict`).

---

## Как добавить новую фичу

1. Создать структуру:
   - `app/features/<feature>/api/router.py`
   - `app/features/<feature>/domain/...`
   - `app/features/<feature>/providers/...`
   - `app/features/<feature>/infrastructure/...`
2. В `app/main.py` добавить:
   - импорт роутера
   - `app.include_router(..., prefix="/api")`
3. Если нужны зависимости — инициализировать их в `lifespan` и положить в `app.state`.

---

## Примечания

- Папка `app/services` удалена, вся логика разнесена по slice‑модулям.
- Интеграционные тесты используют моки (`DummyLLM`, `DummyVector`) и подменяют lifespan приложения.

---

## Архитектурная схема

```mermaid
flowchart TD
    User[Пользователь] -->|HTTP| FastAPI[FastAPI (app.main)]
    FastAPI -->|/api/chat| ChatRouter[Chat API Router]
    ChatRouter -->|use-case| RunChat[run_chat (services.py)]
    RunChat -->|RAG| Qdrant[QdrantService]
    RunChat -->|LLM| Ollama[OllamaClient]
    Qdrant <--> Ollama
    RunChat -->|docx ingest| Ingest[Ingest/Docx Parser]
```

---

## Примеры запросов к API

### Проверка состояния

```bash
curl http://localhost:8000/api/health
```

### Диалог с ассистентом

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Что такое GIL в Python?", "session_id": "default"}'
```

Пример ответа:

```json
{
  "answer": "GIL (Global Interpreter Lock) — это механизм CPython, ...",
  "meta": {
    "used_rag": true,
    "retrieved_chunks": 3,
    "answer_numbers": [12, 15]
  }
}
```

---

## FAQ

**Q: Почему не запускается Ollama или Qdrant?**

- Проверьте, что сервисы Ollama и Qdrant запущены и доступны по адресам из `.env`.

**Q: Как обновить базу вопросов?**

- Просто замените docx-файл и дождитесь автоматического ingest (или перезапустите приложение).

**Q: Как добавить новую тему для интервью?**

- Добавьте вопросы/ответы в docx-файл, они будут автоматически проиндексированы.

**Q: Как изменить системный промпт?**

- Измените переменную `system_prompt` в `.env` или настройках.

---

## Контакты

- Вопросы и предложения: [your-email@example.com]
- Issues и баги: через GitHub Issues
