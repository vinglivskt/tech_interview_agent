# План: внедрение LangChain / LangGraph / LangSmith в tech_interview_agent

> Документ анализирует текущую архитектуру проекта (FastAPI + Qdrant + Ollama + PostgreSQL)
> и отвечает на вопрос: какая из технологий LangChain-экосистемы целесообразна,
> что она даст конкретно нашему проекту, как и в каком порядке внедрять.

---

## 1. Резюме (TL;DR)

| Технология | Рекомендация | Главная польза для проекта |
|---|---|---|
| **LangGraph** | ✅ Внедрять (приоритет №1) | Заменить ручные state-машины режимов **design** и **sobes** на граф с персистентным состоянием в PostgreSQL. Сессии переживают рестарт API. |
| **LangSmith** | ✅ Внедрять (приоритет №2) | Трассировка всех LLM-вызовов + регрессионные эвалы для промптов. Сейчас правка промптов — «вслепую»: непонятно, как изменение влияет на скоринг. |
| **LangChain** | ⚠️ Частично (точечно) | Четыре конкретных сценария: (1) **structured output** вместо ручных JSON-парсеров/ретраев, (2) `ChatOllama` под нашим `LLMGateway` (usage-метрики для LangSmith), (3) **RecursiveCharacterTextSplitter** вместо самописного `chunk_text`, (4) загрузчики + `QdrantVectorStore` при расширении форматов базы. Полная миграция — не нужна. |

> **Статус на текущий момент:** LangGraph (приоритет №1) и LangSmith (приоритет №2) уже
> внедрены — см. `plans/PLAN_LANGGRAPH_DESIGN.md` и `plans/PLAN_LANGSMITH.md`. LangFlow
> исключён из документа; ниже — детальный разбор сценариев LangChain.

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

## 5. LangChain — ⚠️ точечно, но с конкретными сценариями

### 5.1 Позиция: не миграция, а 4 точечных сценария

Проект уже имеет собственные `LLMGateway`, `EmbeddingGateway`, `VectorStoreGateway`
(`backend/src/core/interfaces/*`), рабочий `OllamaClient`, `QdrantService`, `chunk_text`.
Заменять их на LangChain-эквиваленты ради абстракций — нет смысла: это новый слой
зависимостей при неизменной функциональности.

Но есть **4 конкретных сценария**, где отдельный кирпич LangChain решает реальную боль.
Ниже — по каждому: что болит, что взять, before/after, когда делать.

### 5.2 Сценарий 1 — структурный вывод (structured output) вместо JSON-ретраев [приоритет]

**Боль.** `score_free_answer` (`sobes/domain/scoring.py:77-122`), `parse_score`
(`design/domain/graph.py:136-176`) и `classify_batch` (`sobes/domain/classification.py:38-89`)
делают хрупкий `json.loads` + ручные ретраи + dict-валидацию. По сути мы переписываем
`with_structured_output`, который в LangChain уже готов.

**Два уровня решения:**

**Уровень A — без LangChain (самый дешёвый).** Модель qwen2.5:7b поддерживает
JSON-режим Ollama. Достаточно в `OllamaClient.generate` прокинуть `format: "json"`
для скоринг-вызовов — модель гарантированно вернёт JSON, и ретраи почти перестают
срабатывать:

```python
# today: json.loads(raw) + try/except + 3 ретрая «верни только JSON»
# проще: llm.generate(..., format="json") → payload["format"] = "json"
```

**Уровень B — через LangChain (`langchain-ollama`).** `with_structured_output(schema)`
возвращает **уже валидированный pydantic-объект** — ретраи-петля не нужна, деградация
в «0%» происходит реже:

```python
from langchain_ollama import ChatOllama
from pydantic import BaseModel


class DesignScore(BaseModel):
    score_percent: int
    rubric: dict[str, int]
    covered_points: list[str]
    missed_points: list[str]
    techlead_explanation: str


llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_url, temperature=0.2)
structured = llm.with_structured_output(DesignScore, method="json_schema")
parsed = await structured.ainvoke(messages)  # pydantic-объект, без json.loads
```

⚠️ Схема рубрик (`{reqs, arch, data, scale, tradeoffs}`, `0..100`, границы длин) всё равно
требует валидации: переносим её в pydantic `field_validator` ровно из сегодняшнего
`parse_score` (+ тесты). Сам `parse_score` не удаляем — он остаётся фолбэком и
схемой разбора для LangSmith-эвалов.

**Вывод по сценарию:** начинать с Уровня A (одна строка в скоринг-вызовах), Уровень B —
когда захотим убрать ручные ретраи насовсем. Точки: `sobes/domain/scoring.py`,
`design/domain/graph.py`, `sobes/domain/classification.py`.

### 5.3 Сценарий 2 — `ChatOllama` под нашим `LLMGateway` (usage-метрики) [опционально]

**Боль.** Сейчас ответ — просто строка: в LangSmith-трейсе видно latency, но не видно
сколько токенов потрачено/получено (`usage_metadata`).

**Что взять.** Интерфейс `LLMGateway` — уже точка интеграции, меняем только тело
`OllamaClient.generate` на `ChatOllama` из `langchain-ollama`:

```python
from langchain_ollama import ChatOllama


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        ...
        self._chat = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_url.rstrip("/"),
            temperature=settings.ollama_temperature,  # если есть в настройках
            num_predict=max_tokens_default,
        )

    async def generate(self, messages, *, temperature=None, max_tokens=None, metadata=None, tags=None, **kwargs):
        result = await self._chat.ainvoke(messages)
        return result.content
```

Плюсы: `usage_metadata` (токены) попадает в LangSmith-трейс, стандартные типы сообщений,
меньше собственного HTTP-кода. Минусы: ещё одна обёртка поверх `httpx`; формат Ollama
меняется быстрее, чем адаптеры LangChain; риск потерять тонкий контроль над payload.
Эмбеддинги при желании — `OllamaEmbeddings`.

**Вывод:** делать только когда понадобится точная метрика токенов (цены/аналитика).
Контракты роутеров и `LLMGateway` не меняются.

### 5.4 Сценарий 3 — `RecursiveCharacterTextSplitter` для RAG [опционально]

**Боль.** Самописный `chunk_text` (`chat/domain/vectorization.py`) работает и покрыт
тестами, но плохо режет русские абзацы/списки и не настраивается на ходу.

**Что взять.** Когда появятся новые источники или захочется сепараторы
(абзац → строки → предложения):

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=["\n\n", "\n", ". ", " "],
)
chunks = splitter.split_text(text)
```

⚠️ Сохранить контракт и сигнатуру `chunk_text` — «обернуть», а не «заменить»: внутри
функции использовать сплиттер, наружу отдавать тот же список кусков. Тесты не меняются.

**Вывод:** низкий приоритет, делать вместе со сценарием 4.

### 5.5 Сценарий 4 — загрузчики и `QdrantVectorStore` для новых форматов [опционально]

**Боль.** `ingest.py` (docx→Qdrant, sha256-дедуп) завязан на один формат docx, слой кастомный.

**Что взять.** Если база вопросов расширится (pdf, html, markdown, разметка):

```python
from langchain_community.document_loaders import Docx2txtLoader  # или PyPDFLoader/TextLoader
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore

docs = Docx2txtLoader(settings.interview_docx_path).load()
pieces = RecursiveCharacterTextSplitter(chunk_size=..., chunk_overlap=...).split_documents(docs)
QdrantVectorStore.from_documents(
    pieces, OllamaEmbeddings(model=settings.ollama_embed_model, base_url=settings.ollama_url),
    url=settings.qdrant_url, collection_name=settings.qdrant_collection,
)
```

Единый пайплайн загрузчиков + сплиттеров + vectorstore реально окупается при 2+ форматах.
Дедуп по sha256 и state-файл индекса (`ingest_state.json`) остаются нашими — их в LangChain
нет, навешиваем после `from_documents`. Существующие `QdrantService` и индексацию не
переписываем, пока не появятся новые форматы. Для гибрида (vector + BM25) — Qdrant умеет
фильтры поверх того же вектора, но у нас уже есть score-пороги в `run_chat`, отдельная итерация.

**Вывод:** мигрировать только при расширении форматов.

### 5.6 Порядок и усилия

| Сценарий | Когда делать | Усилия | Риск | Файлы |
|---|---|---|---|---|
| 1A. `format: "json"` в `generate` | сейчас (в связке со скорингом/LangSmith) | 0.5 дня | низкий | `ollama.py`, скоринг-вызовы |
| 1B. `with_structured_output` | когда надоест руками дёргать ретраи | 1–2 дня | средний | `scoring.py`, `graph.py`, `classification.py` |
| 2. `ChatOllama` под `LLMGateway` | когда нужны токены в трейсах LangSmith | 1 день | низкий | `ollama.py` |
| 3. Сплиттер | вместе со сценарием 4 | 0.5 дня | низкий | `vectorization.py` |
| 4. Загрузчики + vectorstore | при 2+ форматах базы | 2–3 дня | средний | `ingest.py`, `qdrant.py` |

**Итого по LangChain:** максимальная польза при минимальном бюджете — сценарий 1
(уровень A — день без новых зависимостей). Уровень B и варианты 2–4 — по мере появления
реальной потребности. Зависимости добавлять точечно под сценарий:
`langchain-ollama` (1B, 2), `langchain_text_splitters` (3), `langchain-qdrant` +
`langchain-community` (4).

---

## 6. Рекомендуемый план внедрения (по фазам)

> **Статус:** Фазы 1 (LangSmith) и 2 (LangGraph для design) **выполнены** — см.
> `plans/PLAN_LANGSMITH.md` и `plans/PLAN_LANGGRAPH_DESIGN.md`. Ниже — исходные вехи
> для контекста и блок LangChain (Фаза 5) на будущее.

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

### Фаза 5 — LangChain точечно (опционально, когда появится потребность)
- [ ] 1A. `OllamaClient.generate` → `format: "json"` для скоринг-вызовов
      (`sobes/scoring.py`, `design/graph.py`, `sobes/classification.py`) — надёжный JSON.
- [ ] 1B. `with_structured_output(ScoreSchema)` вместо ручных ретраев/`json.loads`
      (валидацию рубрик перенести в pydantic `field_validator` из `parse_score`).
- [ ] 2. `ChatOllama` под нашим `LLMGateway` — если нужны token usage в LangSmith-трейсах.
- [ ] 3. `RecursiveCharacterTextSplitter` внутри `chunk_text` (контракт/тесты не менять).
- [ ] 4. `QdrantVectorStore` + загрузчики — только при 2+ форматах базы вопросов.
- Результат: надёжный структурный вывод и, опционально, единый пайплайн источников.

---

## 7. Большой вопрос: не перебор ли это?

Честный ответ: **проект самодостаточен**, и весь LangStack не обязателен. Приоритет:
- Обязательно ценно: **LangGraph + checkpointer** (решает реальную боль — потерю сессий
  при рестарте и нечитаемое ветвление дизайна) и **JSON-режим Ollama** (чинит хрупкий JSON).
- Сильно помогает итерациям: **LangSmith** (наблюдаемость + эвалы промптов).
- Не обязательно: полный **LangChain** — но 4 точечных сценария из раздела 5 дают
  конкретную пользу без миграции ядра.

Если хочется минимализма — порядок «Фаза 2 → JSON-mode → Фаза 1» даст 80% ценности
при минимальном росте зависимостей.

---

## 8. Карта «где что применить» по файлам

| Файл проекта | Технология | Изменение |
|---|---|---|
| `backend/src/features/chat/providers/ollama.py` | LangChain (точечно) | `format:"json"` для скоринг-вызовов; опционально `ChatOllama` на месте тела `generate` (токены в трейсах) |
| `backend/src/features/design/domain/graph.py` | LangGraph + LangChain (опц.) | граф (`parse_score`, `score_step`) уже реализован; опционально `with_structured_output(DesignScore)` вместо ретраев |
| `backend/src/features/design/domain/services.py` | LangGraph | `DesignService` → `StateGraph` (реализовано; проверка состояния через checkpointer/`thread_id`) |
| `backend/src/features/design/domain/scenarios.py` | LangGraph | шаги сценария → ноды/рёбра графа (существующие `Step` сохраняются) |
| `backend/src/features/sobes/domain/services.py` | LangGraph (опц.) | линейный граф со checkpointer |
| `backend/src/features/sobes/domain/scoring.py` | LangChain/JSON-mode | `format:"json"`; опционально `with_structured_output(ScoreSchema)` вместо `json.loads` + ретраи |
| `backend/src/features/sobes/domain/classification.py` | LangChain/JSON-mode | то же + пакетный structured output (`classify_batch`) |
| `backend/src/training/langsmith_eval.py` | LangSmith | скэффолд эвалов уже реализован; датасеты из `sobes_answers`/`design_answers` |
| `backend/src/features/chat/domain/vectorization.py` | LangChain (опц.) | `RecursiveCharacterTextSplitter` внутри `chunk_text` (без смены контракта) |
| `backend/src/features/chat/domain/ingest.py` | LangChain (опц.) | `QdrantVectorStore` + docx/pdf/html загрузчики при 2+ форматах |
| `backend/src/features/chat/domain/services.py` | LangGraph (опц.) | `run_chat` → граф `retrieve→answer→verify→grade` |
| `backend/src/core/interfaces/*` | — | не менять; шлюзы остаются точкой интеграции |
| `backend/src/core/langsmith.py` | LangSmith | шлюз трассировки реализован (флаг + `traceable`/`tracing_context`) |
| `docker-compose.yml` | LangSmith | опционально self-hosted сервис (по умолчанию офлайн) |
| `backend/prompts/*` | LangSmith | подключаем к эвалам и трейсингу |