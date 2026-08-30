# План внедрения пользовательской статистики ответов

> Цель: добавить PostgreSQL для персистентного хранения истории ответов пользователя по всем 4 режимам работы, идентификацию пользователя по имени при старте, и UI-вкладку «Статистика ответов» в каждом из режимов.

---

## 0. Резюме требований (как я их понял)

1. **При старте приложения** — приветственная надпись и запрос имени пользователя. Имя используется как ключ для всей персистентной истории.
2. **PostgreSQL** поднимается в `docker-compose.yml` как отдельный сервис. Бэкенд ходит в него через **SQLAlchemy 2.x (async)** + asyncpg.
3. **Для каждого режима (chat, quiz, sobes, design)** сохраняем:
   - **полностью правильные** (`is_correct == True` для quiz, `is_counted == True` для sobes, `score_percent >= pass_threshold` для design),
   - **частично правильные** (`score_percent > 0, но < pass_threshold` для sobes/design; для quiz частично не применимо — там бинарная оценка, см. §3.2),
   - **неправильные** (всё, что не подошло под первые две категории).
4. **Кнопка «Статистика ответов»** в каждом из 4 режимов открывает отдельную вкладку с агрегированной статистикой: сколько правильных / частично правильных / неправильных + список последних неправильных ответов с разбором от агента.
5. **При повторном запуске** — по имени восстанавливается история, и пользователь может просмотреть свои прошлые ошибки и проработать их.

---

## 1. Архитектура решения

```mermaid
graph LR
  subgraph Browser
    UI[React UI: 4 режима + кнопка Статистика + модал Имени]
  end
  subgraph Docker Compose
    FE[frontend: Vite dev :3000]
    API[api: FastAPI :8000]
    DB[(postgres:16 :5432)]
    QDRANT[(qdrant:6333)]
  end
  subgraph Host
    OLLAMA[Ollama :11434]
  end

  UI <--> FE
  FE <-->|/api/*| API
  API <-->|asyncpg| DB
  API <-->|http| QDRANT
  API <-->|http| OLLAMA
```

- **PostgreSQL** — хранение пользователей, сессий, ответов и агрегированной статистики.
- **SQLAlchemy 2.x async + Alembic** — модели, миграции, репозитории.
- **Имя пользователя** сохраняется в `localStorage` (frontend) и передаётся во все API как `X-Username` (или параметр `username`). Бэкенд при первом обращении создаёт запись `User` (case-insensitive unique нормализованное имя).

---

## 2. Этапы внедрения

### Этап 1 — Подготовка инфраструктуры (Docker + зависимости)

1. Добавить сервис `postgres:16-alpine` в `docker-compose.yml`:
   - переменные `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`,
   - том `postgres_data`,
   - healthcheck `pg_isready`,
   - сервис `api` -> `depends_on: postgres: condition: service_healthy`.
2. Добавить `psycopg[binary]` и `sqlalchemy[asyncio]>=2.0.36` в `pyproject.toml`.
3. Добавить `alembic>=1.13` (dev-dep) и `pytest-asyncio` (если отсутствует) для тестов миграций.
4. В `core/config.py` добавить настройки БД:
   - `database_url` (`postgresql+asyncpg://...`, по умолчанию `postgresql+asyncpg://interview:interview@postgres:5432/interview`),
   - `database_echo` (флаг),
   - валидация через `field_validator`.
5. Обновить `.env.example` (если есть) и README.

### Этап 2 — Слой данных (SQLAlchemy модели + миграции)

Создать модуль `backend/src/db/`:
- `db/database.py` — `engine`, `AsyncSessionLocal`, `get_session()` (FastAPI dependency).
- `db/base.py` — `Base` (DeclarativeBase).
- `db/models.py` — ORM-модели (см. §3).
- `db/repository.py` — репозитории для чтения/записи.
- `db/init.py` — создание engine, настройка пула.

Инициализация Alembic:
- `alembic init backend/alembic` с конфигурацией под async URL.
- Первая миграция `0001_init_users_sessions_answers.py` — таблицы `users`, `feature_sessions`, `answers`, `quiz_answers`, `sobes_answers`, `design_answers` (см. §3).
- В `main.py` lifespan вызвать `await create_all_if_missing()` или `alembic upgrade head` через subprocess.

### Этап 3 — Схема БД

#### 3.1 Общие таблицы

```text
users
  id            UUID PK
  username      TEXT UNIQUE NOT NULL  -- нормализованное (strip + lower)
  display_name  TEXT NOT NULL         -- как ввёл пользователь
  created_at    TIMESTAMPTZ
  last_seen_at  TIMESTAMPTZ
```

```text
feature_sessions
  id            UUID PK
  user_id       UUID FK -> users.id (ON DELETE CASCADE)
  feature       TEXT  -- 'chat' | 'quiz' | 'sobes' | 'design'
  external_id   TEXT  -- session_id, который выдаёт сервис (quiz_xxx, sobes_xxx, design_xxx)
  level         TEXT  -- junior/middle/senior (NULL для chat)
  meta          JSONB -- произвольные метаданные (например, scenario_id для design)
  started_at    TIMESTAMPTZ
  ended_at      TIMESTAMPTZ
  UNIQUE (feature, external_id)
```

#### 3.2 Таблицы ответов (по одной на режим, чтобы не плодить JSON-блобы)

**quiz_answers**
```text
  id              UUID PK
  session_id      UUID FK -> feature_sessions.id
  user_id         UUID FK -> users.id
  question_text   TEXT
  user_answer     TEXT
  correct_answer  TEXT
  is_correct      BOOLEAN
  -- для quiz у нас бинарная оценка, частичной нет — но сохраняем
  -- степень «близости» через объяснение
  explanation     TEXT
  answered_at     TIMESTAMPTZ
```

> **Нюанс**: в quiz есть только `is_correct`. Пользователь сказал «частично правильный» — для quiz такой категории формально нет, но мы будем считать её как `is_correct = false`. В UI подсветим отдельной плашкой «В этом режиме только правильно/неправильно». Это нужно явно отразить в плане.

**sobes_answers**
```text
  id                    UUID PK
  session_id            UUID FK
  user_id               UUID FK
  question_text         TEXT
  topic                 TEXT
  user_answer           TEXT
  reference_answer      TEXT
  score_percent         INT  (0..100)
  is_counted            BOOLEAN   -- пересекает pass_threshold
  category              TEXT      -- 'correct' | 'partial' | 'incorrect' (вычисляется)
  techlead_explanation  TEXT
  covered_points        JSONB
  missed_points         JSONB
  answered_at           TIMESTAMPTZ
```

> Категория вычисляется по правилу:
> - `correct` если `is_counted == true` ИЛИ `score_percent >= sobes_pass_threshold_percent`,
> - `partial` если `0 < score_percent < sobes_pass_threshold_percent`,
> - `incorrect` если `score_percent == 0` (или пустой `user_answer` после `skip`).

**design_answers**
```text
  id                    UUID PK
  session_id            UUID FK
  user_id               UUID FK
  scenario_id           TEXT
  step_id               TEXT
  step_title            TEXT
  user_answer           TEXT
  score_percent         INT
  rubric                JSONB   -- {reqs, arch, data, scale, tradeoffs}
  category              TEXT    -- 'correct' | 'partial' | 'incorrect'
  covered_points        JSONB
  missed_points         JSONB
  techlead_explanation  TEXT
  hint_used             BOOLEAN
  answered_at           TIMESTAMPTZ
```

> Категория для design аналогично sobes.

**chat_answers** (опционально, для полноты картины)
```text
  id            UUID PK
  user_id       UUID FK
  session_key   TEXT  -- внутренний session_id чата
  user_message  TEXT
  assistant_answer TEXT
  meta          JSONB
  answered_at   TIMESTAMPTZ
```
> **Важно**: в чате нет «правильно/неправильно» в строгом смысле. Учтём это в UI: для chat-режима кнопка «Статистика» показывает только историю диалогов (последние N пар вопрос-ответ) и счётчик сообщений, без деления на правильно/неправильно. Это надо явно проговорить пользователю.

#### 3.3 Индексы

- `users.username` UNIQUE
- `answers (user_id, feature, answered_at DESC)` — для агрегатов по пользователю
- `feature_sessions (user_id, feature, started_at DESC)`

### Этап 4 — Слой репозиториев

`backend/src/db/repository.py`:
- `UsersRepository`: `get_or_create(username) -> User`
- `AnswersRepository`:
  - `add_quiz_answer(...)`
  - `add_sobes_answer(...)`
  - `add_design_answer(...)`
  - `add_chat_message(...)`
  - `get_user_stats(user_id, feature) -> dict` — агрегаты (counts by category)
  - `list_recent_answers(user_id, feature, limit, only_incorrect=True) -> list[AnswerRow]`

Агрегаты считаются одним SQL-запросом:
```sql
SELECT category, COUNT(*) FROM sobes_answers
WHERE user_id = $1 GROUP BY category;
```

### Этап 5 — Интеграция в существующие сервисы

#### 5.1 Идентификация пользователя

- В `chat/api/router.py` — добавить dependency `current_user(request)`:
  - читает заголовок `X-Username` (или query/body — для всех запросов),
  - приводит к нормализованному виду,
  - вызывает `UsersRepository.get_or_create`,
  - кладёт `user.id` в `request.state.user_id` (или в `app.state` для текущего запроса).
- Та же dependency подключается во все 4 роутера.

#### 5.2 Сохранение ответов

В местах, где формируется «запись об ответе»:
- `quiz/services.py::submit_answer` — после создания `QuizAnswerRecord` вызвать `AnswersRepository.add_quiz_answer(...)`. Для этого в сервис надо пробросить `db_session`.
- `sobes/services.py::answer` — после `SobesAnswerRecord` вызвать `AnswersRepository.add_sobes_answer(...)`.
- `design/services.py::answer` — после `DesignStepRecord` вызвать `AnswersRepository.add_design_answer(...)`.
- `chat/services.py::run_chat` — после каждого цикла `user/assistant` сохранять в `chat_answers`.

> Чтобы не ломать существующие in-memory `SessionStore`, добавим **неблокирующее** сохранение через `BackgroundTasks` или fire-and-forget корутину с собственным `AsyncSession`. Для простоты — `BackgroundTasks` (FastAPI) с `Depends(get_session)`.

#### 5.3 Новые эндпоинты статистики

```
GET  /api/users/me                  -> { id, username, display_name }
GET  /api/stats/{feature}           -> { feature, total, correct, partial, incorrect, accuracy_percent }
GET  /api/stats/{feature}/answers   -> список последних ответов (с фильтром category=incorrect)
GET  /api/stats/overview            -> сводка по всем 4 режимам
```

Все эндпоинты требуют `X-Username`.

### Этап 6 — Frontend

#### 6.1 Глобальный стор пользователя

- `frontend/src/state/UserContext.tsx`:
  - `username: string | null`,
  - `displayName: string | null`,
  - `setUsername(name)` — нормализует и сохраняет в `localStorage`,
  - `clearUsername()`.
- При первом запуске, если `localStorage` пуст, показываем **WelcomeModal** с полем ввода имени. Без имени вход в режимы закрыт (кнопки в карточках дизейблятся, либо показывается «введите имя»).
- Имя пробрасывается во все запросы через обёртку в `services/api.ts`:
  ```ts
  fetch(`${API_BASE}${endpoint}`, { headers: { "X-Username": username ?? "" } })
  ```

#### 6.2 Кнопка «Статистика ответов» в каждом режиме

В каждом из контейнеров (`ChatContainer`, `QuizContainer`, `SobesContainer`, `DesignContainer`) в верхней панели добавить кнопку **«📊 Статистика ответов»**, которая переключает локальный view на новый `StatsView`.

`StatsView`:
- заголовок «Статистика ответов — {modeName}»,
- три плашки: «Правильно: N», «Частично правильно: M», «Неправильно: K»,
- общая точность (`%` правильных + половина частичных — настраивается),
- список «Последние неправильные ответы» (раскрывающиеся карточки с разбором от агента).

Для **chat**: вместо правильно/неправильно — счётчик сообщений и последние 10 пар user/assistant.

#### 6.3 Стили

Переиспользуем существующие CSS Modules + компонент `Card`. Дополнительные цвета:
- правильно — `#22c55e`,
- частично — `#eab308`,
- неправильно — `#ef4444`.

### Этап 7 — Тестирование

#### 7.1 Юнит-тесты
- `tests/unit/db/test_repositories.py` — работа репозиториев с in-memory SQLite (async aiosqlite) или testcontainers-postgres.
- `tests/unit/test_user_dependency.py` — нормализация имени, get_or_create.

#### 7.2 Интеграционные тесты
- `tests/integration/test_stats_endpoints.py` — поднимаем FastAPI + Postgres, проверяем:
  - после прохождения quiz ответы сохранились,
  - `GET /api/stats/quiz` возвращает правильные счётчики,
  - `GET /api/stats/quiz/answers?category=incorrect` возвращает неправильные.
- Аналогичные тесты для sobes/design.

#### 7.3 Локальная проверка вручную
1. `docker compose up --build`
2. Открыть `localhost:3000`, ввести имя `testuser1`.
3. Пройти quiz, набрать 12/20 (mixed).
4. Открыть «Статистика» → увидеть 12 правильно, 8 неправильно.
5. Сделать sobes на middle, на 1 вопрос ответить полностью, на 2 — частично, на 3 — пусто/неправильно.
6. Открыть «Статистика sobes» → увидеть категории.
7. Перезапустить браузер / очистить сессию → имя восстанавливается из localStorage; статистика доступна.

### Этап 8 — Документация

- Обновить `README.md`: добавить блок про Postgres, `DATABASE_URL`, новые эндпоинты.
- Добавить раздел «Пользовательская статистика» с описанием категорий.
- Обновить `Makefile`: добавить `make db-migrate` (запуск alembic).

---

## 3. Детальное описание 4 режимов и что мы в них сохраняем

### 3.1 Chat (свободный диалог)
- **Текущая модель оценки**: нет «правильности». Это RAG-диалог, где пользователь сам оценивает релевантность.
- **Что сохраняем**: каждое сообщение пользователя и ответ ассистента (в `chat_answers`).
- **Статистика**:
  - счётчик сообщений,
  - средняя длина ответа LLM,
  - топ-N последних диалогов.
- **«Разбор агента» после ответа**: не применимо в классическом смысле. Но в этом режиме мы можем показывать **«историю ошибок»** только для других режимов.

### 3.2 Quiz (тест с вариантами)
- **Текущая модель**: `is_correct: bool` — индекс выбранного варианта совпал с `correct_index`.
- **Категории**:
  - `correct` (`is_correct == true`),
  - `incorrect` (`is_correct == false`).
  - Частично правильных в quiz нет — это бинарная оценка.
- **«Разбор агента»**: `explanation` (уже есть в `QuizAnswerRecord`), который объясняет, почему выбранный ответ правильный или нет. Сохраняем в `quiz_answers.explanation`.

### 3.3 Sobes (свободные ответы, устное собеседование)
- **Текущая модель**: LLM оценивает ответ по 0..100% (`score_percent`), `is_counted` (>= `pass_threshold_percent`), `covered_points` / `missed_points`, `techlead_explanation`.
- **Категории** (вычисляем в `add_sobes_answer`):
  - `correct`: `is_counted == true` или `score_percent >= pass_threshold`,
  - `partial`: `0 < score_percent < pass_threshold`,
  - `incorrect`: `score_percent == 0` или пользователь `skip` (сохраняем `user_answer = '<skipped>'`, `score_percent = 0`, `category = 'incorrect'`).
- **«Разбор агента»**: `techlead_explanation`, `covered_points`, `missed_points`, эталонный ответ — всё это уже есть и кладётся в `sobes_answers`.

### 3.4 Design (системный дизайн по шагам)
- **Текущая модель**: на каждом шаге сценария LLM возвращает `score_percent`, `rubric` (5 полей 0..100), `covered_points`, `missed_points`, `techlead_explanation`. Есть `hint_used`.
- **Категории** (аналогично sobes):
  - `correct`: `score_percent >= pass_threshold_percent`,
  - `partial`: `0 < score_percent < pass_threshold_percent`,
  - `incorrect`: `score_percent == 0` или ответ пустой.
- **«Разбор агента»**: `techlead_explanation` + `covered_points` + `missed_points` — кладём в `design_answers`.

---

## 4. Структура файлов после внедрения

```
backend/
├─ Dockerfile
├─ alembic/                       # NEW
│  ├─ env.py
│  ├─ versions/
│  │  └─ 0001_init.py            # NEW
│  └─ script.py.mako
├─ alembic.ini                    # NEW
├─ src/
│  ├─ main.py                     # обновить lifespan: подключение к БД
│  ├─ config.py                   # DATABASE_URL
│  ├─ db/                         # NEW
│  │  ├─ __init__.py
│  │  ├─ database.py
│  │  ├─ base.py
│  │  ├─ models.py
│  │  └─ repository.py
│  ├─ core/
│  │  └─ deps.py                  # NEW: current_user dependency
│  └─ features/
│     ├─ chat/api/router.py       # + статистика, + X-Username
│     ├─ quiz/api/router.py       # + запись в БД, + статистика
│     ├─ sobes/api/router.py      # + запись в БД, + статистика
│     └─ design/api/router.py     # + запись в БД, + статистика

frontend/src/
├─ App.tsx                        # добавить кнопку "Статистика" + WelcomeModal
├─ components/
│  ├─ ui/StatsCard.tsx            # NEW
│  ├─ ui/WelcomeModal.tsx         # NEW
│  ├─ state/UserContext.tsx       # NEW
│  └─ features/
│     ├─ chat/   {Container, StatsView}
│     ├─ quiz/   {Container, StatsView}
│     ├─ sobes/  {Container, StatsView}
│     └─ design/ {Container, StatsView}
└─ services/api.ts                # X-Username header
```

---

## 5. Ключевые технические решения и нюансы

1. **Имя пользователя — case-insensitive, trim**.
   Нормализация на бэке: `username = name.strip().lower()`. `display_name` хранится отдельно для приветствия.
2. **Идентификация по имени — soft auth**.
   Это не полноценная аутентификация, а метка для группировки данных. В плане фиксируем, что для production нужно будет добавить OAuth/пароли, но в MVP достаточно имени.
3. **Коллизии имён**: `username` UNIQUE. Если введённое имя занято — загружаем существующего пользователя (без пароля это MVP; в README отметим как ограничение).
4. **Сохранение ответов — неблокирующее**: используем `BackgroundTasks` FastAPI, чтобы UI не ждал записи в БД.
5. **Аналитика — простой SQL aggregation**. Без тяжёлых OLAP-кубов. На 100k ответов агрегаты < 50 мс.
6. **Категоризация** выполняется на стороне Python (в `AnswersRepository.add_*`), а не в SQL — проще поддерживать и тестировать.
7. **Миграции** — Alembic; на старте контейнера `api` команда `alembic upgrade head` запускается автоматически через `entrypoint` (или доп. команду в `docker-compose.yml`).
8. **Healthcheck БД** в lifespan: если Postgres недоступен — API стартует, но эндпоинты статистики возвращают 503.
9. **Удаление/анонимизация**: позже можно добавить `DELETE /api/users/me`, сейчас — out of scope.
10. **Тесты**: используем `pytest-asyncio` + `testcontainers[postgres]` (или `aiosqlite` для лёгких юнит-тестов).

---

## 6. План разработки по шагам (что я буду делать после вашего «go»)

| # | Что делаю | Файлы |
|---|---|---|
| 1 | Добавляю Postgres в `docker-compose.yml`, переменные окружения, healthcheck | `docker-compose.yml`, `README.md` |
| 2 | Добавляю зависимости (`sqlalchemy[asyncio]`, `psycopg[binary]`, `alembic`) | `pyproject.toml` |
| 3 | Расширяю `Settings` (`database_url`, `database_echo`) | `backend/src/core/config.py` |
| 4 | Делаю слой `db/` (engine, Base, models, repository) | `backend/src/db/*` |
| 5 | Инициализирую Alembic, пишу первую миграцию | `backend/alembic/*`, `backend/alembic.ini` |
| 6 | Делаю dependency `current_user` и подключаю во все роутеры | `backend/src/core/deps.py`, роутеры |
| 7 | Встраиваю запись ответов в quiz/sobes/design/chat (через BackgroundTasks) | `backend/src/features/*/domain/services.py`, `*/api/router.py` |
| 8 | Делаю новые эндпоинты статистики | новый роутер `backend/src/features/stats/api/router.py` |
| 9 | Подключаю миграции в `lifespan` | `backend/src/main.py` |
| 10 | Добавляю `UserContext` + `WelcomeModal` на фронте | `frontend/src/components/state/*`, `frontend/src/components/ui/WelcomeModal.tsx` |
| 11 | Добавляю `X-Username` в `api.ts` | `frontend/src/services/api.ts` |
| 12 | Делаю `StatsView` для каждого из 4 режимов | `frontend/src/components/features/*/StatsView.tsx` |
| 13 | Кнопка «Статистика ответов» в каждом контейнере | контейнеры фичей |
| 14 | Обновляю README | `README.md` |
| 15 | Пишу тесты | `tests/unit/db/*`, `tests/integration/test_stats_*` |
| 16 | Прогоняю `make test`, `make lint`, `docker compose up --build` и снимаю скриншот-логи | — |

---

## 7. Что **не входит** в MVP (но зафиксируем как TODO)

- Аутентификация (пароли/OAuth).
- Экспорт статистики в CSV/JSON.
- Сравнение пользователей друг с другом (leaderboard).
- Графики прогресса по дням/неделям (только суммарные счётчики).
- Ручное удаление конкретного ответа из истории.

---

## 8. Открытые вопросы (нужна ваша валидация)

1. **Частично правильный для quiz** — в текущей модели бинарно. Подтверждаете, что в UI для quiz показываем только две категории (правильно/неправильно), а «частично» доступно только для sobes/design?
2. **Коллизии имён** — если два человека ввели «alex», их статистика сольётся. Для MVP это ок? Или добавим суффикс (дату, hash) при коллизии?
3. **Кнопка «Статистика» в chat** — в чате нет правильности. Сделать отдельный вид статистики (история сообщений + счётчик) или убрать кнопку из чата?
4. **Когда сохранять ответ**: после каждого ответа пользователя или только по завершении сессии? Я предлагаю после каждого (чтобы при крэше ничего не потерялось).

Жду вашего «go» (или правок) — после этого начну по шагам из §6.