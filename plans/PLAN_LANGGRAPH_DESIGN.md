# План внедрения LangGraph в режим «Системный дизайн»

> **Цель:** заменить ручную state-машину `DesignService` (`current_index`, `steps_order`,
> `hinted_steps`, in-memory `DesignSessionStore`) на граф LangGraph с перезапускаемым
> состоянием (checkpoint) — **без изменения API-контракта** `/api/design/*` и фронтенда.
>
> **Подход:** stateful graph с `interrupt()` на каждом шаге. Каждый `POST /design/answer` =
> `graph.ainvoke(Command(resume=answer), config)`; `thread_id` = `session_id`.
>
> LangGraph уже установлен: `langgraph==1.2.11`, `langgraph-checkpoint-postgres==3.1.2`
> (с потянутыми `langchain-core`, `langsmith`, `psycopg-pool`).

---

## 1. Что заменяется (текущее состояние)

| Компонент | Сейчас | Станет |
|---|---|---|
| Сессии дизайна | `DesignSessionStore` — `OrderedDict` с TTL в памяти, mutable `current_index/steps_order/hinted_steps/answers` | Checkpoint-состояние графа (`thread_id`), персистентное при `postgres`-чекпоинтере |
| Переходы между шагами | императивно в `DesignService.answer` (`backend/src/features/design/domain/services.py:436-540`) | рёбра графа + ноды каждого шага |
| Ветвление «лесенки» | `build_dynamic_steps` собирает шаги заранее | шаги сценария становятся нодами графа |
| Ожидание ответа кандидата | нет — фронт сам знает текущий шаг; сервер валидирует `_assert_current_step` | `interrupt()` внутри ноды — граф сам «замирает» на текущем шаге |
| Подсказка | `hint()` помечает `sess.hinted_steps` | `graph.aupdate_state({"hints": [step_id]})` |
| Оценка ответа | `_parse_score` + ретраи в `answer()` | та же логика скоринга, вынесена в ноду графа |

Не меняются: промпты, JSON-схема оценки, штраф за подсказку, деградация при невалидном
JSON, формулы `results()` и вердикта уровня, контракты роутера/фронта.

---

## 2. Целевая архитектура

```
представленческий слой (роутер /design/*)         <-- без изменений
                       │
                       ▼
             DesignService  (фасад, контракты ответов те же)
                       │       │
              ┌────────┘       └─►  DesignSessionStore (дескриптор-зеркало:
              │                    scenario_id, level, steps_order — для persist-роутера)
              ▼
    Компилированный StateGraph (кэш по scenario_id)
    ┌────────────────────────────────────────────────────────┐
    │  clarify → hla → data → scale → tradeoffs → failure    │
    │                (→ advanced для senior)                 │
    │  каждая нода: interrupt() ─ ждёт ответ кандидата ─      │
    │  → скоринг через LLM (ретраи+JSON) → штраф за подсказку │
    │  → обновление state → маршрут к следующей ноде / END    │
    └────────────────────────────────────────────────────────┘
                       │
                       ▼
               Checkpointer (thread_id = session_id)
        MemorySaver (default)  |  AsyncPostgresSaver (опт., DESIGN_CHECKPOINTER=postgres)
```

**Состояние графа (TypedDict):**

```python
class DesignGraphState(TypedDict, total=False):
    session_id: str
    scenario_id: str
    level: str
    step_ids: list[str]                    # финальная «лесенка» сценария
    idx: int                               # число отвеченных шагов
    steps_answer_total: int                # len(step_ids)
    answers: Annotated[list[dict], add]    # рекорды {step_id, score_percent, rubric, covered, missed, expl, hint_used}
    hints: Annotated[list[str], add]       # шаги, где была использована подсказка
    last_result: dict | None               # результат последнего ответа (для API)
```

---

## 2.1 Как это работает простыми словами (с примером)

Раньше шаг интервью хранился «в голове» сервера: `current_index` в in-memory словаре
`DesignSessionStore`, и фронт каждый раз сам «знал», какой шаг следующий.

Теперь само интервью — это **граф состояний** (LangGraph). Каждый шаг — отдельная
«станция» (нода). Дойдя до станции, граф **замирает** (вызов `interrupt()`) и ждёт, пока
кандидат ответит. Прислали ответ — граф «просыпается», оценивает ответ (тот же LLM‑скоринг
с ретраями и штрафом за подсказку), записывает результат в состояние и едет на следующую
станцию. Никто не «помнит», какой шаг был — состояние хранится в **чекпоинтере**
(`thread_id = session_id`), а не в глобальном словаре.

Всё состояние — это один объект, который видно целиком:

```
{
  "session_id": "design_url-shortener_1a2b3c4d",
  "scenario_id": "url-shortener",
  "level": "junior",
  "step_ids": ["clarify","hla","data","scale","api","tradeoffs"],
  "idx": 2,                      # отвечено 2 шага → текущий = step_ids[2] = "data"
  "answers": [ {...}, {...} ],   # результаты шагов
  "hints": ["clarify"],          # подсказки, где были использованы
  "last_result": { "score_percent": 80, "...": "..." }
}
```

**Живой пример (обычная цепочка запросов):**

```bash
# 1. Начали интервью → граф доехал до первого interrupt()
curl -X POST localhost:8000/api/design/start \
  -H 'Content-Type: application/json' \
  -d '{"level":"junior","scenario_id":"url-shortener"}'
#   → 200
#     session_id: "design_url-shortener_1a2b3c4d"
#     step:       {"id":"clarify","title":"Уточнение требований", ...}
#
#     state: step_ids=[...6 шагов...], idx=0
#            [clarify*]  ← граф «замер» тут (звёздочка = интерrupt)

# 2. Ответили → граф проснулся, оценил, поехал дальше
curl -X POST localhost:8000/api/design/answer \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"design_url-shortener_1a2b3c4d",
       "step_id":"clarify","user_answer":"Зафиксирую допущения..."}'
#   → 200  { score_percent:80, rubric:{reqs:80,...,tradeoffs:50},
#            next_step:{"id":"hla","title":"High-Level архитектура", ...},
#            is_last:false, ... }
#
#     state: idx=1 → текущий стал step_ids[1] = "hla"
#            [clarify] → [hla*]  ← снова «замер»

# 3. Подсказка (если нужно)  → просто дописывает шаг в hints + return штраф
curl -X POST localhost:8000/api/design/hint \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"design_url-shortener_1a2b3c4d","step_id":"hla"}'
#   → 200  { hint:"...", penalty_applied_percent:10 }
#     state: hints=["hla"]  (на следующем ответе LLM-балл минус 10)

# 4. И так до последнего шага tradeoffs → is_last:true, граф доезжает до END
curl -X POST localhost:8000/api/design/answer \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"design_url-shortener_1a2b3c4d",
       "step_id":"tradeoffs","user_answer":"Компромиссы..."}'
#   → 200 { score_percent:70, ..., is_last:true, next_step:null, ... }

# 5. Итоги — просто читаем answers из состояния графа
curl localhost:8000/api/design/results/design_url-shortener_1a2b3c4d
#   → 200 { summary:{steps:6,passed:4,avg_percent:72}, verdict_level:"middle", ... }

# 6. С `DESIGN_CHECKPOINTER=postgres` интервью переживает рестарт API:
docker compose restart api
curl localhost:8000/api/design/results/design_url-shortener_1a2b3c4d   # снова 200
# и можно продолжить отвечать на тот же session_id — состояние из БД, а не из памяти.
```

Ключевое: **фронт и контракты `/api/design/*` не поменялись** — та же структура JSON, те же
коды ошибок («Можно отвечать только на текущий шаг сценария» → 404). Изменилось только то,
**где** хранится состояние шага (чекпоинтер графа вместо словаря в памяти процесса).

---

## 3. Шаги внедрения

### Шаг 1. Зависимости (сделано)
```bash
uv add "langgraph>=0.2.60" "langgraph-checkpoint-postgres>=2.0.0"
```
Установилось: `langgraph 1.2.11`, `langgraph-checkpoint-postgres 3.1.2`,
`langchain-core 1.6.3`, `psycopg-pool 3.3.1`.

### Шаг 2. Настройки — `backend/src/core/config.py`
- `design_checkpointer: Literal["memory", "postgres"] = "postgres"` — тип чекпоинтера.
  При `postgres` недоступности на старте — безопасный фолбэк на `MemorySaver`
  (проект изначально устойчив к отсутствию БД).
- `design_graph_max_cache` — лимит кэша компилированных графов (небольшой, ~64).

### Шаг 3. Новый модуль графа — `backend/src/features/design/domain/graph.py`
Содержит всё, что относится к графу:

- `DesignGraphState` (из п.2).
- `format_step_info(scenario, step, *, first) -> dict` — перенос `DesignService._step_info`.
- `parse_score(text, max_expl_len) -> tuple[...]` — перенос `DesignService._parse_score`
  (не меняя JSON-схему и ограничения).
- `async score_step(llm, settings, scenario, step, user_answer, history, hints) -> DesignGradedStep`:
  собирает тот же system/user-промпт, что и текущий `DesignService.answer`, делает
  ретраи (до 3, с сообщением «Предыдущий ответ невалиден…»), применяет штраф за подсказку,
  деградирует на ошибке.
- `make_step_node(step, scenario, settings, llm) -> Node` — фабрика асинхронной ноды:
  ```python
  async def node(state) -> dict:
      user_answer = interrupt("Ответ кандидата")   # пауза графа на этом шаге
      graded = await score_step(...)
      nxt = state["idx"] + 1
      is_last = nxt >= state["steps_answer_total"]
      return {
          "answers": [graded.record],
          "idx": nxt,
          "last_result": { # score, rubric, covered, missed, expl, hint_used,
                           # next_step (dict) или None, is_last,
                           # failure_questions, advanced_questions },
      }
  ```
  `next_step` строится из `scenario.steps[nxt]` через `format_step_info`.
- `build_design_graph(scenario, settings, llm, checkpointer) -> CompiledStateGraph`:
  - для каждого шага — `add_node(step.id, make_step_node(...))`;
  - `add_edge(START, steps[0].id)`, линейные `add_edge` между шагами и до END
    (лесенка всегда линейная, поэтому `add_conditional_edges` не нужны);
  - `compile(checkpointer=checkpointer)`.
- `DesignGradedStep` — dataclass-результат скоринга; плюс сборка DTO `last_result`.

### Шаг 4. `DesignService` — `backend/src/features/design/domain/services.py`
- Конструктор: `__init__(settings, llm, store=None, db_session_factory=None, checkpointer=None)`.
  Кэш графов: `self._graphs: dict[str, CompiledStateGraph]` и `self._scenarios: dict[str, Scenario]`.
- `start()`: без изменений выбирает сценарий (`pick_scenario`) и `build_dynamic_steps`,
  компилирует граф (`_graph_for(scenario)`), создаёт `session_id`, вызывает
  `await graph.ainvoke(initial_state, {"configurable": {"thread_id": session_id}})` —
  граф останавливается на `interrupt()` первого шага. Возвращает `(DesignSession-дескриптор,
  scenario_info, step_info)` как раньше; дескриптор сохраняется в `self._store` (для роутера).
- `answer()`: `aget_state` → текущий шаг = `step_ids[idx]`; валидирует совпадение
  `step_id` (та же ошибка «Можно отвечать только на текущий шаг сценария» и «Все шаги уже
  отвечены»); `await graph.ainvoke(Command(resume=user_answer), config)`; возвращает кортеж
  из `state["last_result"]` — **та же сигнатура, что раньше**.
- `hint()`: `aupdate_state(config, {"hints": [step_id]})` (только если шага ещё нет),
  возвращает `(step.hint, penalty)`.
- `results()`: читает `answers` из состояния; формулы средних/рубрики/вердикта —
  без изменений.
- `_scenario_by_id_for_session` удалён; для роутера добавлен `step_persist_context(session_id, step_id)`
  (возвращает `{scenario_id, step_title, hint_used, level}` из состояния графа).
- `DesignSession`/`DesignSessionStore` **остаются** публичным дескриптором (тесты и роутер
  их читают), но mutable-поля перестают быть источником истины.

### Шаг 5. Роутер — `backend/src/features/design/api/router.py`
- Фабрика сервиса: `DesignService(settings, llm, _store_get(), checkpointer=
  getattr(request.app.state, "design_checkpointer", None))` — во всех эндпоинтах.
- Контракты `DesignAnswerResponse/DesignStartResponse/...` и прочее — без изменений.

### Шаг 6. `backend/src/main.py` (lifespan)
- После инициализации PostgreSQL создать чекпоинтер:
  ```python
  checkpointer = await create_design_checkpointer(settings)   # postgres или memory
  app.state.design_checkpointer = checkpointer
  ```
- `create_design_checkpointer()` → `(checkpointer, async_close)`: при
  `design_checkpointer == "postgres"` и доступной БД — `AsyncPostgresSaver.from_conn_string(dsn)`
  + `await saver.setup()`; при ошибке/флаге memory — `(MemorySaver(), None)`.
- В `shutdown`: вызвать `async_close()` (закрывает async-генератор Postgres-севера/пула).

### Шаг 7. README (опционально, для консистентности)
- Строка в разделе настроек: `DESIGN_CHECKPOINTER` (`memory|postgres`).

---

## 4. Тестирование

### 4.1 Новые unit-тесты графа — `tests/unit/design/test_design_graph.py`
Чистый `graph.py`, чекпоинтер `MemorySaver`, DummyLLM (как в `tests/unit/design/conftest.py`):

1. `test_start_pauses_on_first_step` — после старта `next()` графа указывает на первую ноду.
2. `test_full_flow_resumes_through_all_steps` — ответы по всем шагам; последний даёт `is_last=True`,
   `next_step=None`.
3. `test_hint_update_affects_scoring` — `aupdate_state({"hints":["clarify"]})` до ответа →
   штраф 10 применён (LLM вернул 80 → 70).
4. `test_retry_on_invalid_json` — DummyLLM: первый вызов `"not json"`, второй валидный → 2 вызова.
5. `test_degrade_when_llm_always_invalid` — LLM всегда невалидный → score 0 + fallback-объяснение.
6. `test_sessions_are_independent` — два thread_id не пересекаются по answers/hints.
7. `test_state_resumed_after_restart_with_same_checkpointer` — новый compile на том же
   `MemorySaver` + тот же thread_id восстанавливает answers (моделирует «рестарт»).
8. `test_rejects_answer_for_non_current_step` — resume не-текущего шага → ValueError.

### 4.2 Новые тесты сервиса — `tests/unit/design/test_design_service_graph.py`
Поверх `DesignService` с `MemorySaver` (повторяем поведенческие проверки текущего API):
9. `test_start_returns_descriptor_and_first_step` — `sess.steps_order`, `scenario_id`, `step_info`.
10. `test_answer_hint_penalty_and_next_step` — ответ после подсказки → 70, `next_step={"id":"hla",...}`.
11. `test_results_verdict_and_rubric` — после полного прохода — summary/verdict как раньше.
12. `test_answer_unknown_step_404_contract` — ValueError («текущий шаг»).

### 4.3 Регрессия (существующие тесты)
- `tests/unit/design/*` (`conftest.py`, `test_design_library.py`, `test_design_service_db_factory.py`).
- `tests/integration/test_design_api.py` (включая `test_design_rejects_answer_for_non_current_step`).
- `tests/integration/stats/test_stats_api.py` — статистика по design (persist-path роутера).

### 4.4 Запуск
```bash
make test                    # весь pytest
uv run pytest tests/unit/design/ -v
uv run pytest tests/integration/test_design_api.py -v
make lint                    # ruff + tsc --noEmit (фронт не менялся, но проверяем контракт типов)
```

### 4.5 Ручная проверка (End-to-End)
```bash
docker compose up --build          # + Ollama на хосте
# /api/design/start
# /api/design/hint  →  контракт {hint, penalty_applied_percent}
# /api/design/answer → 200, score = LLM − 10 (если hint), next_step, is_last
# /api/design/results/{id} → summary + verdict
# Рестарт API (docker compose restart api) → тот же session_id с DESIGN_CHECKPOINTER=postgres
#   продолжает интервью с того же шага.
```

---

## 5. Критерии завершённости (Definition of Done)

1. **API-контракт сохранён:** все `GET/POST /api/design/*` отвечают той же структурой JSON,
   что и до внедрения (ответы DTO-моделей не менялись). Фронтенд не требует правок.
2. **LangGraph — реальный исполнитель:** сессии дизайна хранят состояние в чекпоинтере
   (`thread_id = session_id`); `answer`/`hint`/`results` работают через `ainvoke`/`aupdate_state`/
   `aget_state`, а не через mutable `DesignSession`.
3. **Поведение без регрессий:**
   - ретраи невалидного JSON (≤3) и деградация скоринга — работают;
   - штраф за подсказку применяется до балла в ответе и в статистике;
   - ответ не на текущий шаг → 404 «Можно отвечать только на текущий шаг сценария»;
   - `results()`: `summary/avg_percent`, `by_rubric`, `strengths/weaknesses`, `verdict_level` —
     формулы прежние.
4. **Persist-путь статистики жив:** `persist_design_answer` (scenario_id, step_title,
   hint_used, level) пишется как раньше.
5. **Персистентность сессий (по желанию):** при `DESIGN_CHECKPOINTER=postgres` интервью
   переживает рестарт API; при `memory` в рамках процесса — как текущее поведение.
6. **Тесты:** новые unit-тесты графа/сервиса зелёные; вся регрессия зелёная:
   `make test`, `make lint`.
7. **Нет новых «молчаливых» зависимостей от недоступной БД:** старт работает без PostgreSQL
   (фолбэк на MemorySaver).

---

## 6. Риски и откат

| Риск | Мититация |
|---|---|
| LangGraph-вёрсия меняет API | зафиксировали точные версии; интерфейс `interrupt/Command` проверен на 1.2.11 |
| Потеря памяти сессий при фолбэке на MemorySaver | равно текущему поведению; опт-in `postgres` даёт персистентность |
| Двойной источник истины (checkpoint + дескриптор) | дескриптор только для роутера (persist) и тестов; все запросы состояния идут через граф |
| Сбой Postgres-чекпоинтера на старте | тёплый фолбэк на `MemorySaver` + warning в лог |
| Откат | revert коммита: сервис возвращается в старое состояние без миграций данных (чекпоинт-таблица не используется при `memory`) |

---

## 7. Чек-лист внедрения

- [x] Шаг 1: зависимости (готово)
- [x] Шаг 2: `config.py` — `design_checkpointer`
- [x] Шаг 3: `graph.py` — граф/ноды/скоринг (+ `create_design_checkpointer`)
- [x] Шаг 4: `services.py` — фасад поверх графа (+ кодирование scenario_id в session_id)
- [x] Шаг 5: `router.py` — проброс чекпоинтера + persist-контекст из графа
- [x] Шаг 6: `main.py` — создание чекпоинтера в lifespan
- [x] Тесты 4.1–4.2 новые (`test_design_graph.py`, `test_design_service_graph.py`)
- [x] Регрессия 4.3, `make test` (158 passed)
- [x] `make lint` (ruff: мои файлы чистые; пред-существующие замечания не трогали)
- [x] README: `DESIGN_CHECKPOINTER`, `.env.example`

---

## 8. Итог внедрения — что реально сделано

### 8.1 Файлы (изменено/создано)

| Файл | Что сделано |
|---|---|
| `backend/src/features/design/domain/graph.py` | **новый модуль.** `DesignGraphState`, `DesignGradedStep`, `format_step_info`, `parse_score`, `score_step` (ретраи ≤3, штраф, деградация), `make_step_node` (нода с `interrupt()`), `build_design_graph` (линейные рёбра START→шаги→END, `compile(checkpointer=...)`), `create_design_checkpointer` (postgres с фолбэком на memory). |
| `backend/src/features/design/domain/services.py` | `DesignService` стал фасадом над графом: `start` → `graph.ainvoke(initial, config)`; `answer` → `Command(resume=...)`; `hint` → `aupdate_state({"hints":[...]})`; `results` → читает `answers` из состояния. Добавлены `_graph_for` (кэш), `_session_state`, `_current_step_id`, `step_persist_context`. |
| `backend/src/features/design/api/router.py` | фабрика `_service(request)` с `checkpointer=app.state.design_checkpointer`; persist-контекст для `persist_design_answer` берётся из `service.step_persist_context(...)`. |
| `backend/src/main.py` | в lifespan создаётся `app.state.design_checkpointer` через `create_design_checkpointer(settings)`; на shutdown закрывается. |
| `backend/src/core/config.py` | поля `design_checkpointer: Literal["memory","postgres"]="postgres"`, `design_graph_max_cache: int = 64`. |
| `tests/unit/design/test_design_graph.py` | **новый** — 22 теста: `format_step_info`, `parse_score`, `score_step` (ретрай/штраф), полный граф-фло, `aupdate_state` подсказки, пустые шаги, фолбэк чекпоинтера. |
| `tests/unit/design/test_design_service_graph.py` | **новый** — 12 тестов: start/answer/hint/results, 404-контракты, resume между двумя инстансами на одном чекпоинтере, `step_persist_context`. |
| `README.md`, `.env.example` | документированы `DESIGN_CHECKPOINTER`, `DESIGN_GRAPH_MAX_CACHE`. |

### 8.2 Отклонения от первоначального плана (осознанные)

- **`session_id` теперь содержит scenario_id**: формат `design_{scenario_id}_{8 hex}`.
  Нужно, чтобы после рестарта API (postgres-чекпоинтер, in-memory регистр сессий обнулился)
  можно было восстановить сценарий из только `session_id` (`_scenario_id_from_session`).
- **`_scenario_by_id_for_session` удалён** вместо «оставить для роутера». Роутер больше не
  читает mutable `DesignSession`; для persist-пути добавлен граф-метод `step_persist_context(...)`,
  который отдаёт `{scenario_id, step_title, hint_used, level}` из состояния графа.
- **`create_design_checkpointer` возвращает кортеж** `(checkpointer, async_close)` — `AsyncPostgresSaver`
  создаётся через `asynccontextmanager.from_conn_string`, поэтому те же `__aenter__/__aexit__` используются
  и для закрытия пула на shutdown.
- Старт графа — `add_edge(START, steps[0].id)` (не `set_entry_point`), линейные переходы
  `add_edge(prev, nxt)` без `add_conditional_edges` — лесенка всегда линейная.
- `DesignSessionStore` остался только как дескриптор для `start()`/роутера; источник истины
  состояния — чекпоинтер графа.

### 8.3 Как проверить руками (без docker)

```bash
make test                     # 158 passed (включая всю регрессию + 34 новых теста дизайна)
uv run ruff check backend/src/features/design/ backend/src/core/config.py tests/unit/design/
# → только пред-существующие замечания (SIM105 в main.py не из этого внедрения)
```