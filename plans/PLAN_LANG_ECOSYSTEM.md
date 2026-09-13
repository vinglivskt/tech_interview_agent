# План: внедрение LangChain / LangGraph / LangSmith в tech_interview_agent

> Документ анализирует текущую архитектуру проекта (FastAPI + Qdrant + Ollama + PostgreSQL)
> и отвечает на вопрос: какая из четырёх технологий LangChain-экосистемы целесообразна,
> что она даст конкретно нашему проекту, как и в каком порядке внедрять.

---

## 1. Резюме (TL;DR)

| Технология | Рекомендация | Главная польза для проекта |
|---|---|---|
| **LangGraph** | ✅ Внедрять (приоритет №1) | Заменить ручные state-машины режимов **design** и **sobes** на граф с персистентным состоянием в PostgreSQL. Сессии переживают рестарт API. |
| **LangSmith** | ✅ Внедрять (приоритет №2) | Трассировка всех LLM-вызовов + регрессионные эвалы для промптов. Сейчас правка промптов — «вслепую»: непонятно, как изменение влияет на скоринг. |
| **LangChain** | ⚠️ Частично (точечно) | Только отдельные кирпичи: JSON-режим Ollama + structured output вместо ручных парсеров/ретраев, сплиттер вместо самописного `chunk_text`. Полная миграция — не нужна. |
| **LangFlow** | ❌ Не использовать | Визуальный конструктор, не нужен ни как рантайм, ни как инструмент: проекту не подходит ни по архитектуре, ни по способу работы с промптами. |

---

## 2. Что уже есть в проекте (стартовая точка)

Проект уже сам по себе является мини-LangGraph/LangChain:

- **Своя абстракция над LLM** — `LLMGateway` (`backend/src/core/interfaces/llm.py`) и реализация `OllamaClient` (`backend/src/features/chat/providers/ollama.py`) поверх `httpx`. Это аналог `ChatOllama` из LangChain.
- **Свои RAG-слои** — `QdrantService` (`backend/src/features/chat/infrastructure/qdrant.py`), самописный `chunk_text` (`backend/src/features/chat/domain/vectorization.py`), индексация docx→Qdrant с sha256-дедупом (`ingest.py`). Аналог LangChain `QdrantVectorStore` + `TextSplitter` + загрузчиков документов.
- **Ручные state-машины** для всех 4 режимов — in-memory `OrderedDict` с TTL и `current_index`:
  - `DesignSessionStore` + `DesignSession.current_index/steps_order/hinted_steps` (`backend/src/features/design/domain/services.py:36-80`, `DesignService.answer` идёт по шагам «лесенки»).
  - `SobesSessionStore` + `SobesSession.current_index/question_id` (`backend/src/features/sobes/domain/services.py:36-65`).
  - `QuizSessionStore` (`backend/src/features/quiz/domain/services.py`).
  - `SessionStore` для чата (`backend/src/features/chat/domain/services.py:96-124`).
- **LLM-as-judge скоринг** с ручным парсером JSON и ретраями: `score_free_answer` (`sobes/domain/scoring.py:77-122`), `_parse_score` (`design/domain/services.py:401-434`), `classify_batch` (`sobes/domain/classification.py`).
- **Промпты** — внешние markdown/yaml в `backend/prompts/` (редактируются без пересборки).
- **Статистика** — PostgreSQL (SQLAlchemy async + Alembic), таблица `api_request_logs` для отладки.

**Ключевые боли, на которые «ложатся» технологии:**
1. Сессии в памяти → теряются при рестарте API (перезапустил сервис — дизайн-интервью обнулилось).
2. Скоринг-промпты правятся «вслепую» — нет ни трейсов, ни бенчмарков.
3. JSON-парсинг ответов LLM хрупкий (ретраи пошиты в код, модель не использует JSON-режим Ollama).
4. Ветвление «лесенки» дизайна (эволюция / всегда-шаги / failure / advanced) зашито в императивном коде.

---

## 3. LangGraph — ✅ внедрять (приоритет №1)

### Почему именно он

LangGraph — это фреймворк для **графовых, stateful-процессов** с персистентностью. Наш режим
«Системный дизайн» — буквально учебный пример такого процесса:

```
clarify → (hla → data → scale → tradeoffs) ИЛИ (evolve-1 → … → evolve-N)
        → failure → advanced(только senior)
```

Сейчас это состояние + переходы руками: `current_index`, `steps_order`, `hinted_steps`,
`answers[]`, условное ветвление в `build_dynamic_steps` (`design/domain/scenarios.py:243-427`)
и императивная логика «если последний шаг — верни следующий» в `DesignService.answer`
(`design/domain/services.py:436-540`). Каждый шаг — отдельный HTTP-запрос, между шагами
происходит ручная синхронизация in-memory стора.

### Что даст конкретно

| Проблема сейчас | Что даст LangGraph |
|---|---|
| Сессии исчезают при рестарте API (in-memory TTL-стор) | **Checkpointer в PostgreSQL** (он у нас уже есть в стеке) — состояние интервью переживает перезапуск, сессию можно возобновить |
| Ветвление «лесенки» размазано по двум файлам | **Граф**: явные ноды (`clarify`, `hla`, `data`, `scale`, `tradeoffs`, `failure`, `advanced`) и conditional-edges, которые читаются как блок-схема |
| Состояние хранится в дата-классе + dict `scenario_meta` | **Typed Dict/State** с одним источником правды на узел |
| Валидация «можно отвечать только на текущий шаг» — ручной `_assert_current_step` | Граф сам не даст «перепрыгнуть» шаг (маршрутизация по текущему состоянию) |
| История/счётчики для статистики собираются вручную | В state можно держать `answers[]`, rubric-аккумуляторы, вердикт — как поля графа |

### Как внедрить (схема)

Не переписывая API. Контракты роутера (`POST /design/start` → `POST /design/answer` →
`GET /design/results`) и ответы фронту остаются прежними — меняется только «машина» внутри
`DesignService`.

```python
# Эскиз: StateGraph для design-режима
class DesignState(TypedDict, total=False):
    session_id: str
    scenario_id: str
    level: str
    step_id: str
    step_title: str
    user_answer: str
    hints_used: list[str]
    answers: list[dict]          # step_id, score, rubric, covered, missed, expl
    next_step: dict | None       # то, что сейчас строит _step_info()
    is_last: bool

def route_after_step(state: DesignState) -> str:
    # аналог: is_last → END, иначе следующий step_id из шагов сценария
    ...

builder = StateGraph(DesignState)
for step in scenario.steps:                     # собираем из тех же YAML/dynamic steps
    builder.add_node(step.id, score_one_step)   # нода = существующая LLM-оценка шага
builder.set_entry_point(scenario.steps[0].id)
builder.add_conditional_edges(
    scenario.steps[-1].id, route_after_step,
    {name: name for name in scenario.steps} | {"__end__": END},
)
graph = builder.compile(checkpointer=PostgresSaver(pg_engine))
```

Каждый `POST /design/answer` = `graph.invoke({...amendment}, config={"thread_id": session_id})`.
Нода `score_one_step` внутри — это текущая функция из `DesignService.answer` (промпт + retry +
`_parse_score`), выделенная в чистый шаг графа.

### Так же (опционально, фаза позже)

- **sobes** — цикл «пока следующий вопрос: классификация → обогащение → скоринг → next»
  (`SobesService.answer`, `sobes/domain/services.py:184-243`) — тоже граф, но с линейной
  маршрутизацией. Выгода меньше, чем у design, но Checkpointer решит ту же проблему
  персистентности сессий.
- **chat** — RAG-цикл (`run_chat`, `chat/domain/services.py:127-357`) можно обернуть в граф
  с нодами `retrieve → build_context → generate → verify → grade`. Низкий приоритет.

### Честные минусы

- Внедрение потребует аккуратного рефакторинга `DesignService` (сессии, скоринг, статистика).
- У нас шаг за шагом — это отдельные HTTP-запросы, а не один агентный цикл, поэтому
  HITL-interrupts (`interrupt()`) почти не нужны; ценность именно в state+checkpoint+routing.
- Дополнительная зависимость `langgraph`.

---

## 4. LangSmith — ✅ внедрять (приоритет №2)

### Почему

Это **observability + eval** для LLM-приложений. Сейчас:

- правка `backend/prompts/*.md` — слепой поиск: не видно ни входов/выходов, ни «где сломалось»;
- единственная отладка — таблица `api_request_logs` (бинарник без деталей промптов);
- `score_free_answer` и `_parse_score` молча деградируют в «0%» при сбое парсинга —
  без трейса непонятно, модель ли виновата или парсер;
- скоринг у нас LLM-as-judge в **4 режимах и 6+ промптах** — самый частый источник
  «завышенных/заниженных» оценок, и это надо измерять.

### Что даст конкретно

1. **Трейсинг каждого LLM-вызова** — видно system/user промпт, ответ, токены, latency,
   код фичи, session_id. Сразу видно: какие вопросы RAG не находит, где JSON падает,
   какие ответы скоринг занижает/завышает.
2. **Регрессионные эвалы при правке промптов** — LangSmith позволяет собрать датасет
   (вопрос, эталонный разбор техлида, ожидаемая оценка) и прогнать его после каждого
   изменения `sobes/scoring.md` или `design` промпта. Правка перестаёт быть «вслепую».
3. **Сбор датасета автоматически** — реальные пары «ответ пользователя → оценка/вердикт»
   из PostgreSQL можно выгружать в LangSmith и использовать как бенчмарк.
4. **Feedback loops** — можно метить плохие разборы и дообучаться на них.

### Как внедрить

Самый дешёвый и безопасный шаг из всего плана — обёртка вокруг `OllamaClient.generate`:

```python
# Эскиз: трассировка без переписывания кода
@traceable(name="llm.generate", metadata={"feature": ..., "session_id": ...})
async def _generate_traced(self, messages, **kw):
    return await self._inner_generate(messages, **kw)
```

Либо подключить `@traceable`/`wrap_openai` на уровне шлюза `LLMGateway` — тогда все 4 режима
сразу покрываются. Правка одного файла, контракты API не меняются.

### Формат развёртывания

- **Self-hosted LangSmith** (OSS, контейнер) — вписывается в наш `docker compose` как
  дополнительный сервис, проект остаётся локальным/офлайн-совместимым. Рекомендую именно этот
  вариант, т.к. проект позиционируется как офлайн-first.
- **Облачный LangSmith** — быстрее подключить, но требует интернет и аккаунт.

### Честные минусы

- Self-hosted LangSmith — достаточно тяжёлый сервис (Postgres/Redis внутри, несколько
  контейнеров), для личного проекта это избыточно, но оправдано удобством настройки промптов.
- Если не планируете дальше итерировать промпты — ценность ниже.

---

## 5. LangChain — ⚠️ частично (точечно)

### Полная миграция — НЕ нужна

Проект уже имеет собственные `LLMGateway`, `EmbeddingGateway`, `VectorStoreGateway`
(`backend/src/core/interfaces/*`), рабочий `OllamaClient`, `QdrantService`, `chunk_text`.
Заменять их на LangChain-эквиваленты ради абстракций — нет смысла: это новый незнакомый
слой зависимостей при неизменной функциональности. Маленький проект — решать это можно.

### Что из LangChain взять точечно — реальная польза

**a) Structured output вместо ручных JSON-парсеров и ретраев (самое ценное).**

Сейчас `score_free_answer` (`sobes/domain/scoring.py:77-122`) и `_parse_score`
(`design/domain/services.py:401-434`) делают хрупкий `json.loads` + ручные ретраи,
а `classify_batch` — позиционный доступ `data[i]`. Model (qwen2.5:7b) поддерживает
**JSON-режим Ollama** (`format: "json"`), что само по себе почти устраняет проблему парсинга.

```python
# Сегодня: ретраи и json.loads вручную
# Проще: включить JSON-режим в OllamaClient.generate (format="json")
# и/или использовать pydantic-модель ответа вместо dict-валидации.
```

Практический шаг без LangChain: расширить `OllamaClient.generate` ключом `format: "json"`
для скоринг-вызовов — парсинг станет надёжнее, ретраи можно выкинуть. Если авторитетно
нужен именно LangChain — использовать `with_structured_output(pydantic_structure)` из
`langchain-ollama`, но для 2-3 точек это скорее роскошь.

**b) Сплиттер** — `RecursiveCharacterTextSplitter` взамен самописного `chunk_text`
(`chat/domain/vectorization.py`). Наша версия работает и покрыта тестами; замена даст
настраиваемые сепараторы (абзацы/строки), но это низкоприоритетный «косметический» апгрейд.

**c) Загрузчик docx / интеграция Qdrant** — встроенная `QdrantVectorStore` и docx-лоадеры
заменяют `ingest.py` + `QdrantService`. Опять же, наш слой уже работает; миграция оправдана
только если планируются другие форматы базы вопросов (pdf, html, разметка) — тогда единый
интерфейс загрузчиков и сплиттеров реально окупится.

### Итого по LangChain

- Точечно: **JSON-режим Ollama для скоринга** (это можно сделать даже без ядра LangChain).
- Если расширять источники знаний (не только docx) — тогда полноценный `langchain`-слой
  загрузчиков + сплиттеров + vectorstore становится оправданным.
- Полная замена `OllamaClient`/`QdrantService` на LangChain — отложить, не блокер.

---

## 6. LangFlow — ❌ не использовать

**Почему не подходит:**

1. **Визуальный low-code конструктор поверх LangChain/LangGraph** — это инструмент
   прототипирования, а не рантайм для FastAPI-приложения. Наш бэкенд — детерминированный
   код с типами, тестами и контрактами API; «переносить» его в карточки/канаты на не
   реализовать качественно.
2. **Наш скоринг слишком специфичен** (строгая JSON-схема, рубрики, штрафы за подсказки,
   деклайнеры отказов) — такие вещи в визуальной UI-машине держать больно и непрозрачно.
3. **Ещё один сервис** в docker compose (отдельный API + frontend, тяжёлый), без пользы
   для конечного пользователя. Проект сейчас офлайн-first и минималистичный.
4. Промпты в проекте — markdown-файлы, обновляются без пересборки и через `docker compose
   watch`. LangFlow привязал бы их к своей базе и интерфейсу.

**Единственный сценарий, где LangFlow можно рассмотреть** — песочница для быстрого
прототипирования нового режима перед написанием кода. Но для личного проекта это
необязательно.

---

## 7. Рекомендуемый план внедрения (по фазам)

Фазы независимы: каждую можно делать отдельно и откатить без потери остальных.

### Фаза 1 — LangSmith-трассировка (1–2 дня, низкий риск)
- [ ] Поднять self-hosted LangSmith сервисом в `docker-compose.yml` (или включить cloud).
- [ ] Обернуть `OllamaClient.generate`/`embed` в `@traceable` с метаданными
      (`feature`, `session_id`, `mode`).
- [ ] Добавить `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT` (variable) в `.env`.
- [ ] Проверить, что видны вызовы всех 4 режимов; наладить фильтры по фиче.
- Результат: видно каждый скоринг, каждый RAG-промах, каждый JSON-фейл.

### Фаза 2 — LangGraph для design-режима (3–5 дней, средний риск)
- [ ] Ввести узел-шлюз `OllamaClient`: добавить `format: "json"` для скоринг-вызовов
      (уменьшит фейлы парсинга внутри нод).
- [ ] Описать `DesignState` (типизированный dict).
- [ ] Собрать граф из нод сценария (шаги из YAML/БД через существующие
      `Scenario.steps`/`build_dynamic_steps`), добавить conditional-маршрутизацию
      (эволюция / рlus-final / только senior → advanced).
- [ ] Вынести текущую логику `DesignService.answer` в ноду `score_one_step` (без изменения
      промптов и `_parse_score`).
- [ ] Подключить `PostgresSaver` как checkpointer (используем уже имеющийся PostgreSQL).
      `thread_id = session_id` — сессия переживает рестарт API.
- [ ] Сохранить API-контракты `/design/*` без изменений; адаптировать `results()` на чтение
      state вместо `DesignSession`.
- [ ] Покрыть регрессионные тесты: старт → отвечать → подсказка со штрафом → результаты.
- Результат: персистентные сессии дизайна + явный граф вместо ручной лесенки.

### Фаза 3 — LangGraph для sobes и чата (2–3 дня, низкий риск, опционально)
- [ ] sobes: линейный граф «answer → enrich next → next», checkpointer для сессий.
- [ ] chat: ноды `retrieve → answer → verify → grade` (обёртка над существующим `run_chat`).
- Результат: единообразные графы всех режимов, единый механизм персистентности.

### Фаза 4 — Эвалы скоринга в LangSmith (2–3 дня, когда накопятся данные)
- [ ] Выгрузить реальные пары «вопрос + ответ + оценка» из `sobes_answers`/`design_answers`.
- [ ] Собрать датасет в LangSmith с ожидаемой категорией/баллами (референсы брать руками
      на выборке из 20–50 примеров).
- [ ] Прогнать эвалы после каждой правки `backend/prompts/*` — фиксировать регрессии.
- Результат: правка промптов становится управляемой и измеримой.

---

## 8. Большой вопрос: не перебор ли это?

Честный ответ: **проект самодостаточен**, и весь LangStack не обязателен. Приоритет:
- Обязательно ценно: **LangGraph + checkpointer** (решает реальную боль — потерю сессий
  при рестарте и нечитаемое ветвление дизайна) и **JSON-режим Ollama** (чинит хрупкий JSON).
- Сильно помогает итерациям: **LangSmith** (наблюдаемость + эвалы промптов).
- Не обязательно: полный **LangChain** (слой заменяет работающий код), **LangFlow** (не нужен).

Если хочется минимализма — порядок «Фаза 2 → JSON-mode → Фаза 1» даст 80% ценности
при минимальном росте зависимостей.

---

## 9. Карта «где что применить» по файлам

| Файл проекта | Технология | Изменение |
|---|---|---|
| `backend/src/features/chat/providers/ollama.py` | LangChain (точечно) | `format:"json"` для скоринг-вызовов; опционально `ChatOllama` |
| `backend/src/features/design/domain/services.py` | LangGraph | `DesignService` → `StateGraph` + `PostgresSaver` |
| `backend/src/features/design/domain/scenarios.py` | LangGraph | шаги сценария → ноды/рёбра графа (существующие `Step` сохраняются) |
| `backend/src/features/sobes/domain/services.py` | LangGraph (опц.) | линейный граф со checkpointer |
| `backend/src/features/sobes/domain/scoring.py` | LangChain/JSON-mode | структурный вывод вместо ручного `json.loads` + ретраи |
| `backend/src/features/sobes/domain/classification.py` | LangChart/JSON-mode | то же + пакетный structured output |
| `backend/src/features/chat/domain/vectorization.py` | LangChain (опц.) | `RecursiveCharacterTextSplitter` |
| `backend/src/features/chat/domain/ingest.py` | LangChain (опц.) | docx loader → единый пайплайн загрузки |
| `backend/src/features/chat/domain/services.py` | LangGraph (опц.) | `run_chat` → граф `retrieve→answer→verify→grade` |
| `backend/src/core/interfaces/*` | — | не менять; шлюзы остаются точкой интеграции |
| `docker-compose.yml` | LangSmith | self-hosted sercice (если выбран локальный вариант) |
| `backend/prompts/*` | LangSmith | подключаем к эвалам и трейсингу |