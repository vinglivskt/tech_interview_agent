# tech_interview_agent

Личный помощник для подготовки к техническим собеседованиям в формате реального интервью. Прогоняет вас через четыре режима — тестирование, устное собеседование, системный дизайн и свободный диалог — и оценивает каждый ответ глазами LLM-эксперта. Стэк: **Python 3.12 / FastAPI + Qdrant (RAG) + Ollama + PostgreSQL** на бэкенде и **React 18 / Vite / TypeScript** на фронтенде.

---

## Возможности

- **Четыре режима подготовки** в одном приложении, единая статистика по пользователям.
- **RAG по вашей базе вопросов** — ответы подкрепляются релевантными фрагментами из `interview_questions.docx`, которые можно обновлять вручную (авто-переиндексация).
- **Работает локально и офлайн-совместимо**: вся генерация идёт через вашу локальную Ollama, данные хранятся в ваших контейнерах.
- **Библиотека из ~130 карточек системного дизайна** по 19 категориям и трём уровням, с автогенерацией интервью-лесенки.
- **Персистентная статистика** по каждому пользователю в PostgreSQL — прогресс, слабые места, история ответов.

---

## Быстрый старт

### Docker (рекомендуется)

```bash
docker compose up --build
```

Откройте `http://localhost:3000` — фронтенд с hot reload. Требуется запущенная **Ollama** на хосте (см. [Зависимости](#зависимости)).

### Только бэкенд (без dev-фронта)

```bash
docker compose up api qdrant postgres --build
```

API будет на `http://localhost:8000` (документация OpenAPI — `http://localhost:8000/docs`).

### Локальная разработка (без Docker)

```bash
# Терминал 1 — бэкенд
make dev-backend            # http://localhost:8000

# Терминал 2 — фронтенд
make dev-frontend           # http://localhost:3000
```

Vite проксирует `/api/*` на `http://localhost:8000` (задаётся через `VITE_API_URL` в `frontend/vite.config.ts`).

### Hot reload через Docker

```bash
docker compose watch
```

- **Бэкенд**: изменения в `backend/src` → авто-рестарт uvicorn
- **Фронтенд**: изменения в `frontend/src` → HMR через Vite
- **Промпты**: изменения в `backend/prompts` → синхронизируются в контейнер

---

## Зависимости

| Зависимость | Назначение | Где запускать |
|---|---|---|
| **Ollama** | Локальная LLM (генерация) + эмбеддинги (RAG) | На хосте (`http://localhost:11434`) |
| **Docker** | Сервисы `api`, `qdrant`, `postgres`, `frontend` | docker compose |
| **uv** | Python-зависимости/запуск бэкенда | Хост (для локальной разработки) |
| **Node.js 22+** | Фронтенд | Хост или контейнер |

### Установка Ollama

```bash
brew install ollama           # macOS
ollama pull qwen2.5:7b        # модель LLM (задаётся через OLLAMA_MODEL)
ollama pull nomic-embed-text  # модель эмбеддингов (задаётся через OLLAMA_EMBED_MODEL)
```

> Для Ollama в Docker на macOS/Windows: Docker Desktop → Settings → Resources → Network → включите `host.docker.internal`, чтобы контейнер `api` мог достучаться до Ollama на хосте.

---

## Режимы работы

| Режим | Что делает | Оценка |
|---|---|---|
| **Тестирование** (`quiz`) | Выбор из 4 вариантов ответа. Может быть сгенерирован на лету или извлечён из базы. | Бинарная (верно/неверно) + пояснение |
| **Собеседование** (`sobes`) | Свободный ответ текстом на открытый вопрос. Показывается подсказка по теме, «сухие» вопросы обогащаются LLM. | Проценты по критериям (Понимание, Глубина, Точность) + разбор техлида (усвоенные/упущенные пункты) |
| **Системный дизайн** (`design`) | Пошаговое интервью: High-level архитектура, датамодель, масштабирование, компромиссы. | Проценты по рубрике + вердикт уровня (junior/middle/senior) |
| **Интервью / диалог** (`chat`) | Свободный диалог: задаёте любой вопрос — ассистент анализирует ваш ответ и даёт эталон из RAG. Можно получить случайный вопрос из базы. | Разбор + оценка, без строгого скоринга |

Все режимы пишут прогресс в PostgreSQL, ассистент идентифицирует пользователя по заголовку `X-Username`.

---

## Архитектура

### Компоненты

```
                          ┌──────────────────────────────────────────────┐
                          │                 Ollama (хост)                │
                          │   LLM: qwen2.5:7b   Embed: nomic-embed-text  │
                          └───────────────┬──────────────────────────────┘
                                          │ :11434
        Браузер ──► :3000 ──► ┌───────────▼───────────┐
        (React)           /api│        api:8000        │
                             │  FastAPI + RAG (uvicorn)│
                             └───┬────────┬────────────┘
                                 │ vec    │ stats
                          ┌──────▼──┐   ┌──▼──────────┐
                          │ Qdrant  │   │ PostgreSQL  │
                          │ :6333   │   │ :5433→5432  │
                          └─────────┘   └─────────────┘
```

### Сервисы Docker Compose

| Сервис | Порт | Описание |
|---|---|---|
| `qdrant` | 6333 (REST), 6334 (gRPC) | Векторная БД для RAG |
| `postgres` | 5433 (хост) → 5432 (контейнер) | Статистика ответов, пользователи, сессии, библиотека дизайна |
| `api` | 8000 | FastAPI бэкенд (uvicorn) + Alembic-миграции |
| `frontend` | 3000 | Vite dev server (проксирует `/api` на `api:8000`) |

### Поток данных

- **RAG**: `interview_questions.docx` → нарезка на фрагменты → эмбеддинги через Ollama → индексация в Qdrant. При запросе бэкенд достаёт top-K релевантных фрагментов и передаёт их LLM вместе с ответом пользователя.
- **Старт приложения** (`lifespan` в `main.py`): проверяет доступность Ollama и Qdrant, создаёт коллекцию, инициализирует PostgreSQL (в т.ч. авто-создание таблиц), запускает фоновую индексацию docx и сид библиотеки системного дизайна, затем периодически переиндексирует docx (по умолчанию каждый час).
- **Устойчивость к отказам**: если Qdrant или PostgreSQL недоступны — API всё равно поднимается и отвечает для конфигурации и случайных вопросов, а зависимые эндпоинты возвращают понятную ошибку.

---

## Структура проекта

```
tech_interview_agent/
├─ backend/
│  ├─ Dockerfile            # Python 3.12 + uv, только API
│  ├─ alembic/              # миграции PostgreSQL (env.py, versions/)
│  ├─ alembic.ini
│  ├─ prompts/              # промпты для LLM (см. раздел «Промпты»)
│  │  ├─ chat/{system,question}.md
│  │  ├─ quiz/{enrich_question,wrong_answers}.md
│  │  ├─ sobes/{classification,scoring}.md
│  │  └─ design/{scenarios,library}.yaml
│  └─ src/
│     ├─ main.py            # точка входа, lifespan, CORS, роутеры
│     ├─ config.py          # настройки (Settings из .env)
│     ├─ core/              # базовые интерфейсы, депсы, логгер
│     ├─ db/                # SQLAlchemy модели, движок, writer-логика
│     └─ features/
│        ├─ chat/           # RAG-диалог (Интервью)
│        ├─ quiz/           # Тестирование
│        ├─ sobes/          # Устное собеседование
│        ├─ design/         # Системный дизайн
│        └─ stats/          # Статистика пользователя
│
├─ frontend/
│  ├─ Dockerfile           # multi-stage (node build → nginx prod)
│  ├─ nginx.conf           # прокси /api/ → backend
│  ├─ vite.config.ts       # dev proxy /api → localhost:8000
│  └─ src/
│     ├─ components/
│     │  ├─ features/      # chat, quiz, sobes, design, _shared
│     │  └─ ui/            # Button, Card, Markdown, Spinner
│     ├─ services/api.ts   # API клиент
│     └─ styles/
│
├─ tests/                   # unit + integration (pytest, см. «Тесты»)
├─ docker-compose.yml
├─ Makefile
└─ pyproject.toml
```

---

## Настройки через `.env`

Перед запуском скопируйте пример настроек (при наличии) или создайте `.env` в корне проекта. Все переменные читаются из окружения или `.env` (`Settings` в `config.py`). Значения по умолчанию подходят для Docker.

### LLM / Ollama

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` (в Docker Compose — `http://host.docker.internal:11434`) | URL Ollama |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Модель LLM |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Модель эмбеддингов |
| `OLLAMA_TIMEOUT_SEC` | `120` | Таймаут запросов к Ollama (сек) |
| `LLM_TEMPERATURE` | `0.7` | Творческость генерации (0–2) |
| `LLM_MAX_TOKENS` | `1024` | Макс. токенов на ответ |
| `EMBEDDING_DIM` | `768` | Размерность эмбеддингов модели |
| `EMBEDDING_BATCH_SIZE` | `16` | Размер батча при векторизации |

### Qdrant

| Переменная | По умолчанию | Описание |
|---|---|---|
| `QDRANT_URL` | `http://qdrant:6333` | URL Qdrant |
| `QDRANT_COLLECTION` | `interview_qa` | Коллекция Qdrant |
| `QDRANT_SHARD_NUMBER` | `2` | Число шардов коллекции |
| `QDRANT_REPLICATION_FACTOR` | `1` | Фактор репликации |
| `INTERVIEW_TOP_K` | `5` | Сколько фрагментов доставать из RAG |
| `RAG_SCORE_THRESHOLD` | `0.5` | Порог cosine similarity (ниже — хит отбрасывается) |
| `RAG_HIGH_SCORE_THRESHOLD` | `0.85` | Высокий порог для приведения источника |
| `VECTORIZATION_MAX_CHUNK_CHARS` | `1000` | Макс. длина фрагмента текста |
| `VECTORIZATION_OVERLAP` | `100` | Перекрытие соседних фрагментов |

### PostgreSQL и индексирование

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://interview:interview@postgres:5432/interview` | Подключение к PostgreSQL |
| `DATABASE_ECHO` | `false` | Логировать SQL-запросы |
| `DATABASE_AUTO_CREATE` | `true` | Авто-создание таблиц при старте (для dev/MVP) |
| `INTERVIEW_DOCX_PATH` | `/app/src/interview_questions.docx` | Файл вопросов (база RAG) |
| `INGEST_STATE_PATH` | `data/interview_ingest_state.json` | Файл состояния индексации (хеш/время) |
| `INGEST_INTERVAL_HOURS` | `1` | Период проверки обновления docx (часы) |
| `SYSTEM_PROMPT_PATH` | `/app/prompts/chat/system.md` | Системный промпт чата |
| `DESIGN_SCENARIOS_PATH` | `prompts/design/scenarios.yaml` | Детальные сценарии (со steps) |
| `DESIGN_LIBRARY_PATH` | `prompts/design/library.yaml` | Библиотека тем (сид в PostgreSQL) |

### Режимы собеседования и дизайна

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SOBES_PASS_THRESHOLD_PERCENT` | `50` | Порог засчёта ответа в % |
| `SOBES_CACHE_PATH` | `data/sobes_index.json` | Кэш классифицированной базы QA |
| `SOBES_MAX_EXPLANATION_LEN` | `600` | Макс. длина пояснения техлида |
| `SOBES_SHOW_TOPIC_HINT` | `true` | Показывать подсказку по теме перед ответом |
| `SOBES_ENRICH_QUESTIONS` | `true` | Обогащать «сухие» вопросы через LLM |
| `DESIGN_PASS_THRESHOLD_PERCENT` | `50` | Порог засчёта шага дизайна в % |
| `DESIGN_HINT_PENALTY_PERCENT` | `10` | Штраф за подсказку в % |
| `DESIGN_MAX_EXPLANATION_LEN` | `600` | Макс. длина объяснения дизайн-интервью |
| `DESIGN_RAG_TOP_K` | `4` | Сколько фрагментов RAG подмешивать в оценку |
| `DESIGN_MAX_TOKENS` | `800` | Макс. токенов при оценке дизайна |
| `CORS_ALLOW_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000` | Разрешённые origin (через запятую или `*`) |

---

## Makefile

```bash
make help               # список доступных команд
make install            # установить Python (uv) + Node зависимости
make dev-backend        # запустить бэкенд (uvicorn --reload, :8000)
make dev-frontend       # запустить фронтенд (vite dev, :3000)
make build-frontend     # собрать фронтенд в backend/static/
make test               # запустить все тесты (pytest)
make lint               # ruff + tsc --noEmit
make clean              # удалить артефакты сборки
make db-migrate         # применить Alembic-миграции (upgrade head)
make db-revision        # создать новую миграцию  (msg="...")
```

---

## Промпты

LLM-промпты хранятся в `backend/prompts/` в формате Markdown, конфигурации сценариев — в YAML. Всё редактируется без пересборки образа (в `docker compose watch` — автоматически синхронизируется).

| Файл | Назначение |
|---|---|
| `chat/system.md` | Системный промпт диалога: игрока ответа, эталон, оценка |
| `chat/question.md` | Формирование случайного вопроса к диалогу |
| `quiz/wrong_answers.md` | Генерация правдоподобных неправильных вариантов |
| `quiz/enrich_question.md` | Обогащение «сухого» вопроса квиза |
| `sobes/classification.md` | Классификация ответа (верно/частично/неверно) |
| `sobes/scoring.md` | Оценка по критериям (Понимание, Глубина, Точность) |
| `design/scenarios.yaml` | Детальные сценарии системного дизайна (полные лесенки интервью со `steps`) |
| `design/library.yaml` | Библиотека тем системного дизайна: ~130 карточек по 19 категориям и 3 уровням |

---

## Системный дизайн: как устроены сценарии

### Два источника тем

- **`library.yaml`** — библиотека из **~130 карточек** по 19 категориям (kafka, cache, streaming, etc.) и уровням `junior`/`middle`/`senior`. При старте приложение загружает её в PostgreSQL (`design_scenarios`) — карточки видны в `GET /api/design/config`.
- **`scenarios.yaml`** — детальные сценарии с **готовыми шагами интервью** (`steps`): например, `url-shortener`, `news-feed`, `object-storage`. Если id совпадает с карточкой библиотеки — детальный сценарий перекрывает (override) карточку из БД.

### Построение интервью-лесенки

Сессия строится динамически (`build_dynamic_steps`):

- **Есть `evolution`** (прогрессия архитектуры, напр. `static-cdn`):
  `clarify → evolve-1 → … → evolve-N → failure (→ advanced для senior)` — короткая лесенка по уровням эволюции.
- **Нет эволюции** (универсальная полная лесенка):
  `clarify → hla (архитектура) → data (датамодель) → scale (масштабирование) → tradeoffs (компромиссы) → failure (→ advanced для senior)`.
- **Детальные сценарии** из `scenarios.yaml` используют свои явные `steps`.

Шаги генерируются с учётом контекста карточки: `topics` подставляются в HLA, `constraints` — в датамодель, `baseline_load` — в блок масштабирования.

---

## API эндпоинты

Все эндпоинты под префиксом `/api`. Эндпоинты статистики требуют заголовок `X-Username`. Интерактивная документация — `http://localhost:8000/docs`.

### Система и пользователь

```bash
# Health-check
curl http://localhost:8000/api/health

# Профиль текущего пользователя
curl http://localhost:8000/api/users/me -H "X-Username: alex"
```

### Статистика

```bash
# Сводка по всем 4 режимам
curl http://localhost:8000/api/stats/overview -H "X-Username: alex"

# Статистика по одному режиму (quiz|sobes|design|chat)
curl http://localhost:8000/api/stats/quiz -H "X-Username: alex"

# Ответы с фильтром (quiz/sobes/design)
curl 'http://localhost:8000/api/stats/quiz/answers?only_incorrect=true&limit=20' -H "X-Username: alex"

# Диалоговые пары (chat)
curl 'http://localhost:8000/api/stats/chat/pairs?limit=20' -H "X-Username: alex"

# Удалить статистику режима
curl -X DELETE http://localhost:8000/api/stats/quiz -H "X-Username: alex"
```

**Категории ответов:** `correct` — правильный; `partial` — частично правильный (sobes/design, `0 < score < pass_threshold`); `incorrect` — неправильный.

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

# Есть ли вопрос в базе (docx)?
curl 'http://localhost:8000/api/interview/question-exists?q=GIL'

# Случайный вопрос из базы
curl http://localhost:8000/api/interview/random-question
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

# Результаты сессии
curl http://localhost:8000/api/quiz/results/{session_id}
```

### Собеседование

```bash
# Доступные темы и уровни
curl http://localhost:8000/api/sobesedovanie/config

# Старт интервью (уровень + темы)
curl -X POST http://localhost:8000/api/sobesedovanie/start \
  -H "Content-Type: application/json" \
  -d '{"level": "middle", "topics": ["python", "db"]}'

# Ответ на вопрос
curl -X POST http://localhost:8000/api/sobesedovanie/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question_id": "...", "user_answer": "..."}'

# Пропустить / повторить вопрос
curl -X POST http://localhost:8000/api/sobesedovanie/skip \
  -H "Content-Type: application/json" -d '{"session_id": "...", "question_id": "..."}'
curl -X POST http://localhost:8000/api/sobesedovanie/repeat \
  -H "Content-Type: application/json" -d '{"session_id": "...", "question_id": "..."}'

# Результаты сессии
curl http://localhost:8000/api/sobesedovanie/results/{session_id}
```

### Системный дизайн

```bash
# Список уровней, тем, категорий
curl http://localhost:8000/api/design/config

# Карточка конкретного сценария (полное описание)
curl http://localhost:8000/api/design/scenarios/{scenario_id}

# Случайная тема уровня senior (без ручного выбора)
curl -X POST http://localhost:8000/api/design/start \
  -H "Content-Type: application/json" -d '{"level": "senior", "random": true}'

# Случайная тема из категории Kafka
curl -X POST http://localhost:8000/api/design/start \
  -H "Content-Type: application/json" -d '{"level": "middle", "category": "kafka", "random": true}'

# Ручной выбор конкретного сценария
curl -X POST http://localhost:8000/api/design/start \
  -H "Content-Type: application/json" -d '{"level": "middle", "scenario_id": "url-shortener"}'

# Ответ на шаг интервью
curl -X POST http://localhost:8000/api/design/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "step_id": "...", "user_answer": "..."}'

# Подсказка по шагу (с штрафом к оценке)
curl -X POST http://localhost:8000/api/design/hint \
  -H "Content-Type: application/json" -d '{"session_id": "...", "step_id": "..."}'

# Результаты сессии (вердикт уровня)
curl http://localhost:8000/api/design/results/{session_id}
```

---

## Данные в PostgreSQL

Таблицы создаются Alembic-миграциями (`backend/alembic/versions/`). Основные модели (`db/models.py`):

| Таблица | Назначение |
|---|---|
| `users` | Пользователи по нормализованному имени |
| `feature_sessions` | Сессии по режимам (chat/quiz/sobes/design) |
| `quiz_answers` | Ответы на тесты |
| `sobes_answers` | Ответы собеседования (с категорией, баллами, разбором) |
| `design_answers` | Ответы на шаги дизайна (с рубрикой, баллами, вердиктом) |
| `chat_messages` | Сообщения диалога |
| `api_request_logs` | Лог запросов для отладки/аналитики |
| `design_scenarios` | Библиотека карточек системного дизайна (сид из `library.yaml`) |

---

## Тесты

```bash
make test            # pytest (единый вызов)
uv run pytest tests/ -v
```

- **`tests/unit/`** — парсеры, scoring-логика, доменные сервисы, репозитории (по папкам фич).
- **`tests/integration/`** — API-роутеры всех режимов, контракты ответов, статистика.
- Фикстуры — в `tests/fixtures/` (тестовый docx, сценарии, fallback-промпт).

Фронтенд (в `frontend/`): **vitest** для unit, **Playwright** для e2e (`npm run test:e2e`).

---

## FAQ

**Какие сервисы нужно запустить вручную?**
Ollama обязательно. Всё остальное (`qdrant`, `postgres`, `api`, `frontend`) поднимается `docker compose up`.

**`docker compose watch` не работает?**
- Требуется Docker Compose v2.24+: `docker compose version`
- В Docker Desktop включите experimental features

**Фронт не подключается к API?**
- Vite проксирует `/api/*` на `api:8000` через `VITE_API_URL`
- В локальной разработке (без Docker) — на `localhost:8000`

**Как обновить базу вопросов (RAG)?**
Замените `backend/src/interview_questions.docx` и перезапустите приложение (авто-ingest при старте), либо дождитесь периодической переиндексации (`INGEST_INTERVAL_HOURS`).

**Как изменить промпт?**
Отредактируйте файл в `backend/prompts/`. В `docker compose watch` изменения подхватятся автоматически.

**Как добавить новый сценарий дизайна?**
- Полные сценарии интервью (со шагами `steps`) — добавьте элемент массива `scenarios` в `backend/prompts/design/scenarios.yaml`.
- Простые карточки тем (шаги строятся автоматически, тема доступна в `GET /api/design/config`) — добавьте элемент в `backend/prompts/design/library.yaml`. При следующем старте приложение загрузит её в PostgreSQL.

**Статистика не сохраняется?**
Проверьте, что передан заголовок `X-Username`, PostgreSQL доступен и попробуйте `make db-migrate`, если таблицы не созданы автоматически.
