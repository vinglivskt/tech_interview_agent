# FastAPI + Qdrant RAG (Python Interview Assistant)

Приложение превращает личный `.docx` файл с вопросами/ответами по собеседованиям в
векторную базу и использует её как источник в RAG-чате.

## Что делает

1. При запуске читает файл `INTERVIEW_DOCX_PATH`.
2. Считает SHA-256 файла и сравнивает с последним успешным ingest.
3. Если файл изменился:
   - парсит пары вопрос/ответ,
   - разбивает на фрагменты,
   - векторизует (OpenAI embeddings),
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
    "tool_calls": 1,
    "retrieved_chunks": 5,
    "answer_numbers": [12, 27]
  }
}
```

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `OPENAI_API_KEY` | Ключ OpenAI |
| `QDRANT_URL` | URL Qdrant |
| `QDRANT_COLLECTION` | Коллекция (`interview_qa`) |
| `QDRANT_SHARD_NUMBER` | Число шардов при создании |
| `QDRANT_REPLICATION_FACTOR` | Репликация |
| `EMBEDDING_MODEL` | Модель эмбеддингов |
| `EMBEDDING_BATCH_SIZE` | Батч эмбеддингов |
| `VECTORIZATION_MAX_CHUNK_CHARS` | Макс. размер чанка |
| `VECTORIZATION_OVERLAP` | Перекрытие чанков |
| `INTERVIEW_DOCX_PATH` | Путь к исходному docx |
| `INGEST_STATE_PATH` | JSON-состояние ingest (хеш файла) |
| `INGEST_INTERVAL_HOURS` | Частота проверки изменений файла |
| `INTERVIEW_TOP_K` | Сколько фрагментов вытаскивать из Qdrant |

## Запуск локально

```bash
copy .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ручная индексация:

```bash
uv run ingest-interview
```

## Запуск в Docker Compose

В `.env` обязательно задайте:

- `OPENAI_API_KEY`
- `DOCX_SOURCE_PATH_HOST` — путь на хосте до вашего `.docx`

Потом:

```bash
docker compose up --build
```

Доступ:

- API/Frontend: `http://localhost:8000`
- Qdrant Dashboard: `http://localhost:6333/dashboard`
