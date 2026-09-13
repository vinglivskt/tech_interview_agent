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
  - `set_entry_point(step_ids[0])`, линейные `add_edge`/`add_conditional_edges` до END;
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
- `_scenario_by_id_for_session` оставляем для роутера; внутренне переиспользует кэш.
- `DesignSession`/`DesignSessionStore` **остаются** публічным дескриптором (тесты и роутер
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
- `create_design_checkpointer()`: при `design_checkpointer == "postgres"` и доступной БД —
  `AsyncPostgresSaver.from_conn_string(dsn)` + `await saver.setup()`; при ошибке/флаге memory —
  `MemorySaver()`. Возвращает вместе с `close()` для shutdown.
- В `shutdown`: закрыть async-генератор Postgres-севера/пула.

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