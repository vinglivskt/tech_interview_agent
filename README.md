# tech_interview_agent

Подготовка к техническому собеседованию в формате реального интервью. Четыре режима работы: тестирование, устное собеседование, системный дизайн и диалог с ассистентом. Бэкенд на FastAPI + Qdrant (RAG) + Ollama, фронтенд на React (Vite).

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

## Режимы работы

| Режим | Описание |
|---|---|
| **Тестирование** | Выбор из 4 вариантов ответа. LLM оценивает с учётом правдоподобности неправильных. |
| **Собеседование** | Свободный ответ текстом. LLM оценивает по критериям (Понимание, Глубина, Точность) и выставляет уровень. |
| **Системный дизайн** | Пошаговый сценарий (URL Shortener, Chat, etc.). Оценивается структура ответа и полнота. |
| **Интервью** | Диалог с ассистентом. Задаёте вопрос — получаете разбор + оценку вашего ответа. Можно задать свой вопрос или получить случайный из базы. |

---

## Архитектура

### Сервисы Docker Compose

| Сервис | Порт | Описание |
|---|---|---|
| `qdrant` | 6333, 6334 | Векторная БД для RAG |
| `postgres` | 5433 (хост) → 5432 (контейнер) | PostgreSQL — статистика ответов по пользователям |
| `api` | 8000 | FastAPI бэкенд (uvicorn) |
| `frontend` | 3000 | Vite dev server (проксирует `/api` на `api:8000`) |

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
| `DESIGN_SCENARIOS_PATH` | `/app/prompts/design/scenarios.yaml` | Детальные сценарии дизайна (со steps) |
| `DESIGN_LIBRARY_PATH` | `/app/prompts/design/library.yaml` | Библиотека тем дизайна (seed в PostgreSQL при старте) |
| `DATABASE_URL` | `postgresql+asyncpg://interview:interview@postgres:5432/interview` | Подключение к PostgreSQL |
| `DATABASE_ECHO` | `false` | Логировать SQL-запросы |

> Для Ollama на хосте с macOS/Windows: Docker Desktop → Settings → Resources → Network → включите `host.docker.internal`.

---

## Структура проекта

```
tech_interview_agent/
├─ backend/
│  ├─ Dockerfile            # Python + uv, только API
│  ├─ src/
│  │  ├─ main.py           # точка входа, lifespan
│  │  ├─ config.py         # настройки (Settings)
│  │  ├─ core/             # базовые интерфейсы, исключения
│  │  └─ features/
│  │     ├─ chat/          # RAG-диалог (Интервью)
│  │     ├─ quiz/          # Тестирование
│  │     ├─ sobes/         # Устное собеседование
│  │     ├─ design/        # Системный дизайн
│  │     └─ stats/         # Статистика пользователя
│  └─ prompts/             # промпты для LLM
│     ├─ chat/system.md
│     ├─ quiz/wrong_answers.md
│     ├─ sobes/
│     │  ├─ classification.md
│     │  └─ scoring.md
│     └─ design/
│        ├─ scenarios.yaml  # детальные сценарии со steps (url-shortener, news-feed, object-storage)
│        └─ library.yaml    # библиотека из ~120 тем системного дизайна (загружается в PostgreSQL)
│
├─ frontend/
│  ├─ Dockerfile           # multi-stage (node build → nginx prod)
│  ├─ nginx.conf          # прокси /api/ → backend
│  ├─ vite.config.ts       # dev proxy /api → localhost:8000
│  └─ src/
│     ├─ components/
│     │  ├─ features/      # chat, quiz, sobes, design, _shared
│     │  └─ ui/           # Button, Card, Markdown, Spinner
│     ├─ services/api.ts  # API клиент
│     └─ styles/
│
├─ tests/                  # unit + integration
├─ docker-compose.yml
├─ Makefile
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

## Промпты

LLM-промпты хранятся в `backend/prompts/` в формате Markdown. Конфигурации сценариев — в YAML.

| Файл | Назначение |
|---|---|
| `chat/system.md` | Системный промпт диалога: разбор ответа пользователя, эталонный ответ, оценка |
| `quiz/wrong_answers.md` | Генерация неправдоподобных неправильных вариантов |
| `sobes/classification.md` | Классификация ответа (верно/частично/неверно) |
| `sobes/scoring.md` | Оценка по критериям (Понимание, Глубина, Точность) |
| `design/scenarios.yaml` | Детальные сценарии системного дизайна (полные интервью-лесенки со steps) |
| `design/library.yaml` | Библиотека тем системного дизайна: ~120 карточек по 19 категориям и 3 уровням |

---

## API эндпоинты

Все эндпоинты под префиксом `/api`. Эндпоинты статистики требуют заголовок `X-Username`.

### Пользователь и статистика

```bash
# Профиль текущего пользователя
curl http://localhost:8000/api/users/me -H "X-Username: alex"

# Сводка по всем 4 режимам
curl http://localhost:8000/api/stats/overview -H "X-Username: alex"

# Статистика по одному режиму
curl http://localhost:8000/api/stats/quiz -H "X-Username: alex"

# Ответы с фильтром (quiz/sobes/design)
curl 'http://localhost:8000/api/stats/quiz/answers?only_incorrect=true&limit=20' -H "X-Username: alex"

# Диалоговые пары (chat)
curl 'http://localhost:8000/api/stats/chat/pairs?limit=20' -H "X-Username: alex"
```

**Категории ответов:**
- **correct** — правильный;
- **partial** — частично правильный (только sobes/design, `0 < score < pass_threshold`);
- **incorrect** — неправильный.

### Чат (Интервью)

```bash
# Свободный вопрос (любой текст — не обязательно из базы)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Что такое GIL?", "session_id": "test"}'

# Сохранение пары вопрос/ответ в docx
curl -X POST http://localhost:8000/api/interview/save-qa \
  -H "Content-Type: application/json" \
  -d '{"question": "Что такое GIL?", "correct_answer": "...", "session_id": "test"}'
```

### Квиз (Тестирование)

```bash
# Старт сессии
curl -X POST http://localhost:8000/api/quiz/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle"}'

# Ответ на вопрос
curl -X POST http://localhost:8000/api/quiz/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question_id": "...", "selected_index": 0}'
```

### Собеседование

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

Темы берутся из двух источников:
- `library.yaml` — библиотека из ~120 карточек по 19 категориям и уровням `junior`/`middle`/`senior`.
  При старте приложение загружает её в PostgreSQL (`design_scenarios`). В `GET /api/design/config`
  карточки видны в списке тем и категорий.
- `scenarios.yaml` — детальные сценарии с готовыми шагами интервью (`steps`). Если id совпадает
  с карточкой библиотеки — детальный сценарий перекрывает карточку (например, `url-shortener`).

Сценарий можно выбрать вручную (`scenario_id`), либо получить случайный по уровню и категории:
`{"level": "middle", "category": "kafka", "random": true}`. Случайный выбор идёт из PostgreSQL
(сначала по фильтру уровня/категории, при пустом результате — fallback на YAML-слой).
Если у карточки нет готовых шагов — сессия строится по «лесенке»: `clarify → evolve-1..N → failure
(→ advanced для senior)`.

```bash
# Случайная тема уровня senior (без ручного выбора)
curl -X POST http://localhost:8000/api/design/start \
  -H "Content-Type: application/json" \
  -d '{"level": "senior", "random": true}'

# Случайная тема из категории Kafka
curl -X POST http://localhost:8000/api/design/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle", "category": "kafka", "random": true}'

# Ручной выбор конкретного сценария
curl -X POST http://localhost:8000/api/design/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle", "scenario_id": "url-shortener"}'

# Ответ на шаг
curl -X POST http://localhost:8000/api/design/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "step_id": "...", "user_answer": "..."}'
```

Список всех тем и категорий: `GET /api/design/config` (у детальных сценариев `is_detailed: true`).

---

## Тесты

```bash
make test
# или
uv run pytest tests/ -v
```

Unit-тесты для парсеров, scoring-логики, API-роутеров.

---

## FAQ

**`docker compose watch` не работает?**
- Требуется Docker Compose v2.24+: `docker compose version`
- В Docker Desktop включите experimental features

**Фронт не подключается к API?**
- Vite проксирует `/api/*` на `api:8000` через `VITE_API_URL`
- В локальной разработке (без Docker) — на `localhost:8000`

**Как обновить базу вопросов?**
- Замените `interview_questions.docx` и перезапустите приложение (авто-ingest).

**Как изменить промпт?**
- Отредактируйте файл в `backend/prompts/`. В `docker compose watch` изменения подхватятся автоматически.

**Как добавить новый сценарий дизайна?**
- Полные сценарии интервью (со шагами `steps`) — добавьте элемент в массив `scenarios` в `backend/prompts/design/scenarios.yaml`.
- Простые карточки тем (шаги строятся автоматически, тема доступна в `GET /api/design/config`) — добавьте элемент в `backend/prompts/design/library.yaml`. При следующем старте приложение загрузит её в PostgreSQL.
