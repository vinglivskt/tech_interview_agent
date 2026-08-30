# tech_interview_agent

FastAPI-приложение «интервью-ассистент» с RAG (Qdrant) и генерацией ответов через LLM (Ollama). Фронтенд на React (Vite).

---

## Быстрый старт

### Docker (рекомендуется)

```bash
docker compose up --build
```

Откройте `http://localhost:3000` — фронтенд с hot reload.

### Только бэкенд (без dev-фронта)

```bash
docker compose up api qdrant --build
```

API будет на `http://localhost:8000`.

### Локальная разработка (без Docker)

```bash
# Терминал 1 — бэкенд
make dev-backend            # http://localhost:8000

# Терминал 2 — фронтенд
make dev-frontend           # http://localhost:3000
```

Vite проксирует `/api/*` на `http://localhost:8000` (см. `VITE_API_URL` в `frontend/vite.config.ts`).

### Hot reload через Docker

```bash
docker compose watch
```

- **Бэкенд**: изменения в `backend/src` → авто-рестарт uvicorn
- **Фронтенд**: изменения в `frontend/src` → HMR через Vite
- **Промпты**: изменения в `backend/prompts` → синхронизируются в контейнер

---

### Сервисы Docker Compose

| Сервис | Порт | Описание |
|---|---|---|
| `qdrant` | 6333, 6334 | Векторная БД |
| `postgres` | 5433 (хост) → 5432 (контейнер) | PostgreSQL — статистика ответов по пользователям |
| `api` | 8000 | FastAPI бэкенд (uvicorn) |
| `frontend` | 3000 | Vite dev server (проксирует `/api` на `api:8000`) |

> Хост-порт 5433 используется только для отбного подключения (`psql -h localhost -p 5433`).
> Внутри docker-сети `api` подключается к `postgres:5432` по имени сервиса.

### Схема запросов

```
Браузер → localhost:3000 (frontend)
                │
                └─ /api/* → api:8000 (Vite proxy в dev)
                              │
                              └─ /api/* → qdrant:6333 (vector search)
                              └─ POST /api/embeddings → Ollama (host.docker.internal:11434)
```

---

## Настройки через `.env`

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
| `DATABASE_URL` | `postgresql+asyncpg://interview:interview@postgres:5432/interview` | Подключение к PostgreSQL |
| `DATABASE_ECHO` | `false` | Логировать SQL-запросы |

> Для Ollama на хосте с macOS/Windows: Docker Desktop → Settings → Resources → Network → включите `host.docker.internal`.

---

## Структура проекта

```
tech_interview_agent/
├─ backend/
│  ├─ Dockerfile            # Python + uv, только API
│  ├─ src/                  # Python код (FastAPI)
│  │  ├─ main.py            # точка входа, lifespan
│  │  ├─ config.py          # настройки (Settings)
│  │  ├─ core/              # базовые интерфейсы, исключения
│  │  └─ features/          # фичи (chat, quiz, sobes, design)
│  │     ├─ chat/           # RAG-чат
│  │     ├─ quiz/           # Тестирование
│  │     ├─ sobes/          # Устное собеседование
│  │     └─ design/         # Системный дизайн
│  └─ prompts/              # промпты для LLM
│     ├─ chat/system.md
│     ├─ quiz/wrong_answers.md
│     ├─ sobes/
│     │  ├─ classification.md
│     │  └─ scoring.md
│     └─ design/scenarios.yaml
│
├─ frontend/
│  ├─ Dockerfile            # multi-stage (node build → nginx prod)
│  ├─ nginx.conf            # прокси /api/ → backend
│  ├─ vite.config.ts        # dev proxy /api → localhost:8000
│  └─ src/                  # React приложение
│     ├─ components/
│     │  ├─ features/       # chat, quiz, sobes, design
│     │  └─ ui/             # Button, Card, Markdown, Spinner
│     ├─ services/api.ts    # API клиент
│     └─ styles/
│
├─ tests/                   # 37 тестов
├─ docker-compose.yml
├─ Makefile                 # удобные команды для разработки
└─ pyproject.toml
```

---

## Makefile

```bash
make help               # список доступных команд
make install            # установить Python + Node зависимости
make dev-backend        # запустить бэкенд (uvicorn --reload)
make dev-frontend       # запустить фронтенд (vite dev)
make build-frontend     # собрать frontend → backend/static/
make test               # запустить все тесты
make lint               # ruff + tsc
make clean              # удалить артефакты сборки
```

---

## Промпты и конфигурация

LLM-промпты хранятся в `backend/prompts/` в формате Markdown. Конфигурации сценариев — в YAML.

| Файл | Назначение |
|---|---|
| `chat/system.md` | Системный промпт RAG-чата |
| `quiz/wrong_answers.md` | Генерация неправильных вариантов |
| `sobes/classification.md` | Классификация вопросов |
| `sobes/scoring.md` | Оценка ответов |
| `design/scenarios.yaml` | Сценарии системного дизайна |

---

## API эндпоинты

Все эндпоинты под префиксом `/api`. Эндпоинты статистики требуют заголовок `X-Username` с именем пользователя (имя нормализуется и сохраняется в БД).

### Пользователь и статистика

```bash
# Профиль текущего пользователя
curl http://localhost:8000/api/users/me -H "X-Username: alex"

# Сводка по всем 4 режимам
curl http://localhost:8000/api/stats/overview -H "X-Username: alex"

# Статистика по одному режиму
curl http://localhost:8000/api/stats/quiz -H "X-Username: alex"

# Список ответов с фильтром
curl 'http://localhost:8000/api/stats/quiz/answers?only_incorrect=true&limit=20' -H "X-Username: alex"
```

Категории ответов:
- **correct** — правильный ответ (`is_correct == true` для quiz, `score_percent >= pass_threshold` для sobes/design);
- **partial** — частично правильный (только для sobes/design, где `0 < score_percent < pass_threshold`);
- **incorrect** — неправильный.

В чате категорий нет — там сохраняется только история сообщений.

### Чат

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

### Собеседование (свободные ответы)

```bash
# Старт
curl -X POST http://localhost:8000/api/sobesedovanie/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle", "topics": ["python", "db"]}'

# Ответ
curl -X POST http://localhost:8000/api/sobesedovanie/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question_id": "...", "user_answer": "..."}'
```

### Системный дизайн

```bash
curl -X POST http://localhost:8000/api/design/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle", "scenario_id": "url-shortener"}'
```

---

## Тесты

```bash
make test
# или
uv run pytest tests/ -v
```

**37 тестов**: unit + интеграционные.

---

## FAQ

**Q: `docker compose watch` не работает?**
- Требуется Docker Compose v2.24+: `docker compose version`
- В Docker Desktop включите experimental features

**Q: Фронт не подключается к API?**
- Vite проксирует `/api/*` на `api:8000` через `VITE_API_URL` (см. `docker-compose.yml`)
- В локальной разработке (без Docker) — на `localhost:8000`

**Q: Как обновить базу вопросов?**
- Замените `interview_questions.docx` и перезапустите приложение (авто-ingest).

**Q: Как изменить промпт?**
- Отредактируйте файл в `backend/prompts/`. В `docker compose watch` изменения подхватятся автоматически.

**Q: Как добавить новый сценарий дизайна?**
- Добавьте элемент в массив `scenarios` в `backend/prompts/design/scenarios.yaml`.
