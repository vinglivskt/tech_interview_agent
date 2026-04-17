# FastAPI + Ollama + Qdrant RAG (Python Interview Assistant)

# Вопросы по собеседованиям — одни из лучших источников для подготовки. Но как быстро найти нужный ответ в длинном документе? Этот проект — FastAPI-приложение, которое превращает ваш `.docx` с вопросами/ответами в векторную базу Qdrant и позволяет общаться с ней через RAG-чат.

## Что делает

1. При запуске читает файл `INTERVIEW_DOCX_PATH`.
2. Считает SHA-256 файла и сравнивает с последним успешным ingest.
3. Если файл изменился:
   - парсит пары вопрос/ответ,
   - разбивает на фрагменты,
   - векторизует (Ollama embeddings),
   - перезаписывает точки `kind=interview_qa` в Qdrant.
4. В чате модель проводит техскрин и ссылается на номера ответов из базы.

## Важно по сценарию

- Источник знаний: ваш файл `Топ вопросов на собеседовании Python.docx`.
- При ответе ассистент должен указывать источник:
  `Источник: ответ №N` или `Источники: ответы №N1, №N2`.
- В API добавлен `session_id` для сохранения контекста интервью между сообщениями.

## API

- `GET /` — фронт с полем ввода.
- `GET /api/health` — статус API/Qdrant.
- `POST /api/chat` — запрос в интервью-ассистент.

Пример запроса:

```json
{
  "session_id": "my-session-1",
  "message": "Проведи техскрин по async Python"
}
```

Пример ответа:

```json
{
  "answer": "… Источник: ответ №12",
  "meta": {
    "used_rag": true,
    "retrieved_chunks": 5,
    "answer_numbers": [12, 27]
  }
}
```

## Переменные окружения

| Переменная                      | Назначение                               |
| ------------------------------- | ---------------------------------------- |
| `OLLAMA_URL`                    | URL API Ollama                           |
| `OLLAMA_MODEL`                  | Чат-модель (например `qwen2.5:7b`)       |
| `OLLAMA_EMBED_MODEL`            | Модель эмбеддингов в Ollama              |
| `OLLAMA_TIMEOUT_SEC`            | Таймаут запросов к Ollama                |
| `QDRANT_URL`                    | URL Qdrant                               |
| `QDRANT_COLLECTION`             | Коллекция (`interview_qa`)               |
| `QDRANT_SHARD_NUMBER`           | Число шардов при создании                |
| `QDRANT_REPLICATION_FACTOR`     | Репликация                               |
| `EMBEDDING_DIM`                 | Размерность эмбеддингов                  |
| `EMBEDDING_BATCH_SIZE`          | Батч эмбеддингов                         |
| `VECTORIZATION_MAX_CHUNK_CHARS` | Макс. размер чанка                       |
| `VECTORIZATION_OVERLAP`         | Перекрытие чанков                        |
| `INTERVIEW_DOCX_PATH`           | Путь к исходному docx                    |
| `INGEST_STATE_PATH`             | JSON-состояние ingest (хеш файла)        |
| `INGEST_INTERVAL_HOURS`         | Частота проверки изменений файла         |
| `INTERVIEW_TOP_K`               | Сколько фрагментов вытаскивать из Qdrant |

## Запуск локально

```bash
copy .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Запуск в Docker Compose

В `.env` обязательно задайте:

- `OLLAMA_URL` (для Docker обычно `http://host.docker.internal:11434`)
- `OLLAMA_MODEL`
- `OLLAMA_EMBED_MODEL`
- `DOCX_SOURCE_PATH_HOST` — путь на хосте до вашего `.docx`

Потом:

```bash
docker compose up --build
```

Доступ:

- API/Frontend: `http://localhost:8000`
- Qdrant Dashboard: `http://localhost:6333/dashboard`
