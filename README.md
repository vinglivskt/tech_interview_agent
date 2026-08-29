# tech_interview_agent

FastAPI-приложение «интервью-ассистент» с RAG (Qdrant) и генерацией ответов через LLM (Ollama). Фронтенд на React.

---

## Быстрый старт

### Docker (рекомендуется)

```bash
# Production сборка
docker compose up --build
```

Откройте: `http://localhost:3000` (фронтенд)

**Настройки через переменные окружения (`.env`):**

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OLLAMA_URL` | `http://host.docker.internal:11434` | URL Ollama |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Модель LLM |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Модель эмбеддингов |
| `OLLAMA_TIMEOUT_SEC` | `120` | Таймаут Ollama |
| `QDRANT_URL` | `http://qdrant:6333` | URL Qdrant |
| `QDRANT_COLLECTION` | `interview_qa` | Коллекция Qdrant |
| `INTERVIEW_DOCX_PATH` | `/app/src/interview_questions.docx` | Файл вопросов |
| `SYSTEM_PROMPT_PATH` | `/app/prompts/chat/system.md` | Системный промпт |
| `DESIGN_SCENARIOS_PATH` | `/app/prompts/design/scenarios.yaml` | Сценарии дизайна |

### Docker с Hot Reload (разработка)

```bash
# Запуск с авто-перезагрузкой при изменениях файлов
docker compose watch
```

Или вручную:
```bash
# Запуск с пересборкой при изменениях
docker compose up --build --watch
```

**Что происходит:**
- **Бэкенд**: изменения в `backend/src` → авто-рестарт uvicorn
- **Фронтенд**: изменения в `frontend/src` → hot reload через Vite
- **Промпты**: изменения в `backend/prompts` → синхронизируются в контейнер

### Если Ollama на хосте (не в Docker):
```bash
docker compose up
```

Для доступа к Ollama на хосте с MacOS/Windows: Docker Desktop → Settings → Resources → Network → добавьте `host.docker.internal`.

---

### Локальная разработка

#### Бэкенд
```bash
cd backend
pip install -r requirements.txt  # или uv sync
uvicorn src.main:app --reload --port 8000
```

#### Фронтенд
```bash
cd frontend
npm install
npm run dev  # http://localhost:3000
```

**API будет доступен на**: `http://localhost:8000`
**Фронтенд на**: `http://localhost:3000` (проксирует `/api/` на `localhost:8000`)

---

## Структура проекта

```
tech_interview_agent/
├─ backend/
│  ├─ Dockerfile
│  ├─ src/                    # Python код (FastAPI)
│  │  ├─ main.py              # точка входа, lifespan
│  │  ├─ config.py            # настройки (Settings)
│  │  ├─ core/               # базовые интерфейсы, исключения
│  │  └─ features/           # фичи (chat, quiz, sobes, design)
│  │     ├─ chat/            # RAG-чат
│  │     ├─ quiz/             # Тестирование
│  │     ├─ sobes/            # Устное собеседование
│  │     └─ design/          # Системный дизайн
│  ├─ static/
│  │  └─ index.html          # резервная копия оригинального UI
│  └─ prompts/                # промпты для LLM
│     ├─ chat/system.md
│     ├─ quiz/wrong_answers.md
│     ├─ sobes/
│     └─ design/scenarios.yaml
│
├─ frontend/
│  ├─ Dockerfile              # multi-stage build (node → nginx)
│  ├─ Dockerfile.dev          # dev build (Vite dev server)
│  ├─ nginx.conf             # прокси /api/ → backend:8000
│  ├─ src/                   # React приложение
│  │  ├─ components/         # UI компоненты
│  │  │  ├─ features/        # chat, quiz, sobes, design
│  │  │  └─ ui/             # Button, Card, Markdown, Spinner
│  │  ├─ services/api.ts      # API клиент
│  │  └─ styles/            # глобальные стили
│  └─ dist/                  # собранное приложение
│
├─ prompts → backend/prompts  # symlink для удобства
├─ docker-compose.yml
└─ tests/                    # 37 тестов
```

---

## Сервисы Docker Compose

| Сервис | Порт | Описание |
|---|---|---|
| `qdrant` | 6333, 6334 | Векторная БД |
| `api` | 8000 | FastAPI бэкенд (uvicorn с --reload) |
| `frontend` | 3000 | React приложение (Vite dev server) |

### Режимы работы

| Режим | Команда | Бэкенд | Фронтенд |
|---|---|---|---|
| Production | `docker compose up --build` | nginx + uvicorn | nginx (статика) |
| Development | `docker compose watch` | uvicorn --reload | Vite hot reload |

---

## Промпты и конфигурация

LLM-промпты хранятся в `backend/prompts/` в формате Markdown (MD). Конфигурации сценариев — в YAML.

### Структура промптов

```
backend/prompts/
├── chat/
│   └── system.md           # системный промпт для RAG-чата
├── quiz/
│   └── wrong_answers.md   # промпт для генерации неправильных вариантов
├── sobes/
│   ├── classification.md  # промпт для классификации вопросов
│   └── scoring.md        # промпт для оценки ответов
└── design/
    └── scenarios.yaml    # конфигурация сценариев (YAML)
```

### Редактирование промптов

- **Системный промпт чата**: `backend/prompts/chat/system.md`
- **Генерация неправильных ответов**: `backend/prompts/quiz/wrong_answers.md`
- **Классификация вопросов**: `backend/prompts/sobes/classification.md`
- **Оценка ответов**: `backend/prompts/sobes/scoring.md`
- **Сценарии дизайна**: `backend/prompts/design/scenarios.yaml`

---

## API эндпоинты

### Проверка здоровья
```bash
curl http://localhost:8000/api/health
```

### Чат с ассистентом
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Что такое GIL?", "session_id": "test"}'
```

### Квиз
```bash
# Старт
curl -X POST http://localhost:8000/api/quiz/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle"}'

# Ответ
curl -X POST http://localhost:8000/api/quiz/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question_id": "...", "selected_index": 0}'
```

### Собеседование
```bash
# Старт сессии
curl -X POST http://localhost:8000/api/sobes/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle", "topics": ["python", "db"]}'

# Ответ
curl -X POST http://localhost:8000/api/sobes/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question_id": "...", "user_answer": "..."}'
```

### Системный дизайн
```bash
# Старт
curl -X POST http://localhost:8000/api/design/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle"}'

# Ответ на шаг
curl -X POST http://localhost:8000/api/design/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "step_id": "...", "user_answer": "..."}'
```

---

## Тесты

```bash
pytest -q
```

Всего 37 тестов (интеграционные + unit).

---

## FAQ

**Q: docker compose watch не работает?**
- Убедитесь что используете Docker Compose v2.24+:`docker compose version`
- Если используете Docker Desktop, проверьте что experimental features включены

**Q: Не запускается Ollama или Qdrant?**
- Проверьте, что сервисы доступны по адресам из `.env`.

**Q: Как обновить базу вопросов?**
- Замените `interview_questions.docx` и перезапустите приложение (автоматический ingest).

**Q: Как изменить промпт?**
- Отредактируйте соответствующий файл в `backend/prompts/`.

**Q: Как добавить новый сценарий дизайна?**
- Добавьте новый элемент в массив `scenarios` в `backend/prompts/design/scenarios.yaml`.

**Q: Фронтенд не подключается к API?**
- Проверьте что docker-compose запущен и `frontend` зависит от `api`.
- API доступен внутри контейнера как `http://api:8000`.
