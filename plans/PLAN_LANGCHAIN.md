# План внедрения LangChain (структурный вывод + сплиттер)

> **Цель:** взять из LangChain 4 точечных сценария, которые решают реальные боли,
> без миграции ядра LLM/RAG-слоя. Главное: надёжный JSON у скоринг-вызовов —
> LLM получает JSON-схему (structured output API Ollama) и возвращает уже
> валидированный Pydantic-объект вместо ручного `json.loads` + ретраев.
>
> **Подход:** два уровня, как в экологическом плане (секция 5):
> **1A** — `format: "json"` у скоринг-вызовов (одна строка, работает всегда);
> **1B** — `OllamaClient.generate_structured` через `ChatOllama.with_structured_output`
> за флагом `LLM_STRUCTURED_OUTPUT` (default `false`), с безусловным фолбэком
> на legacy-парсинг. Валидация рубрик переносится в Pydantic
> (`src/core/structured.py`), `parse_score` остаётся эталоном-фолбэком.
>
> Сплиттер (`RecursiveCharacterTextSplitter` внутри `chunk_text`) — сценарий 3,
> контракт и сигнатура не меняются. Сценарий 2 (`ChatOllama` в теле
> `generate`) и 4 (`QdrantVectorStore` + загрузчики) — вне текущей фазы
> (см. «Отклонения»).

---

## 1. Сценарии и точки

| Сценарий | Уровень | Точки | Что делает |
|---|---|---|---|
| JSON-режим Ollama | 1A | `sobes/scoring.py`, `sobes/classification.py`, `design/graph.py` | `format: "json"` в payload скоринг-вызовов |
| Structured output | 1B | те же 3 точки + `OllamaClient.generate_structured` | JSON-схема + Pydantic-валидация, фолбэк на legacy |
| Сплиттер | 3 | `chat/domain/vectorization.py` | `RecursiveCharacterTextSplitter` вместо ручной нарезки |
| ChatOllama в `generate` | 2 | — | вынесен (нужен только для токенов, см. Отклонения) |
| QdrantVectorStore + загрузчики | 4 | — | вынесен (только при 2+ форматах базы) |

Схемы (в `src/core/structured.py`), куда перенесена валидация из legacy-парсеров:

- `ScoreResult` — sobes-скоринг: `score_percent` (кламп 0..100), списки пунктов (до 6),
  `techlead_explanation`;
- `DesignScore` — дизайн-скоринг: та же схема + `rubric` ровно с ключами
  `reqs/arch/data/scale/tradeoffs` (кроме него — validation error → фолбэк);
- `ClassificationRow` + `ClassificationBatch = TypeAdapter(list[ClassificationRow])` —
  пакетная классификация (тема/уровень/сложность).

---

## 2. Целевая архитектура

```
   скоринг-вызовы (sobes / design / classification)
        │
        ├─ LLM_STRUCTURED_OUTPUT=true  ───►  OllamaClient.generate_structured(messages, schema, ...)
        │                                       ├─ langsmith tracing_context (metadata/tags)      ← как generate
        │                                       │
        │                                       ├─ ChatOllama.with_structured_output(schema, method="json_schema")
        │                                       │    -> валидированный Pydantic-объект (или None при ошибке)
        │                                       └─ фолбэк: legacy generate(format="json") + ручной парсинг
        └─ иначе ────────────────────────────►  OllamaClient.generate(..., format="json")
                                                    -> json.loads + retry (прежнее поведение)

   RAG: chunk_text(text) ─────────────────► RecursiveCharacterTextSplitter(chunk_size, chunk_overlap, separators)
                                              + прежняя «склейка» кусков до максимума (тот же контракт)
```

Ключевые решения:

- **Никаких сетевых побочных эффектов офлайн**: `generate_structured` строит цепь
  лениво (первый вызов), `LLM_STRUCTURED_OUTPUT=false` — декларированная конфигурация
  по умолчанию, ровно прежний путь `generate` + парсинг.
- **Pydantic-схема = единый эталон валидации**: и для structured-пути (валидирует
  чайн), и для legacy (валидаторы доступны, но legacy сейчас читает результаты
  через старые `json.loads`/`parse_score` — они не удалены). Это совместимо со
  статистикой и промптами.
- **Фолбэк is-best-effort в дизайне**: structured пытается на каждой итерации
  ретрай-цикла; при `None` — одна legacy-попытка `generate(format="json")` +
  `parse_score`. Итог: structured улучшает парсинг, но никогда не ухудшает
  деградацию (та остаётся на прежнем коде).

---

## 3. Настройки

```python
# src/config.py
llm_structured_output: bool = Field(default=False, ...)  # master-выключатель 1B
```

`.env.example`:

```
LLM_STRUCTURED_OUTPUT=false
```

Зависимости (`pyproject.toml`, прямые):

- `langchain-ollama` — `ChatOllama.with_structured_output`;
- `langchain-text-splitters` — `RecursiveCharacterTextSplitter`.

`langchain-core` уже был транзитивной зависимостью (через `langgraph`/`langsmith`).

---

## 4. Шаги внедрения

1. **Зависимости:** `uv add langchain-ollama langchain-text-splitters`.
2. **Настройки:** `llm_structured_output` в `config.py`; блок `# LangChain` в `.env.example`.
3. **Схемы:** новый `backend/src/core/structured.py` — `ScoreResult`, `DesignScore`,
   `ClassificationRow`, `ClassificationBatch` (валидация перенесена из `parse_score`
   и sobes-парсера: клампы 0..100, лимит 6 пунктов, ровно 5 ключей рубрики).
4. **Клиент:** `OllamaClient` — `generate_structured(messages, *, schema, temperature,
   max_tokens, metadata, tags)` + `_get_structured_chain` (ленивая `ChatOllama`,
   кеш по схеме) + `_structured_ainvoke` (возвращает `None` при ошибке).
   Трейс LangSmith — тот же `tracing_context` + `traceable(name="llm.generate_structured")`.
   `LLMGateway` (Protocol) документирует опциональный `generate_structured`.
5. **Точки вызова:**
   - `sobes/scoring.py::score_free_answer(..., use_structured=False)` — structured →
     фолбэк; legacy + `format="json"`;
   - `sobes/classification.py::classify_batch(..., use_structured=False)` — то же
     через `ClassificationBatch`; вложенный фолбэк по строкам;
   - `design/graph.py::score_step(..., use_structured=False)` — structured внутри
     ретрай-цикла; фолбэк `generate(format="json")` + `parse_score`; нода передаёт
     `settings.llm_structured_output`.
   - `sobes/services.py` — прокидывает `use_structured` из настроек в оба места.
6. **Сплиттер:** `chunk_text` делегирует нарезку `RecursiveCharacterTextSplitter`
   сепараторами `["\n\n", "\n", ". ", " "]` и сохраняет прежнюю склейку. Валидация
   аргументов и контракт не меняются.
7. **Тесты:** `tests/unit/test_langchain.py` (см. ниже).
8. **Полный прогон:** `uv run pytest tests/ -q` (регрессия 173+) + ruff на новых строках.
9. **Документация:** план с итогом внедрения; README.

**Откат:** `LLM_STRUCTURED_OUTPUT=false` (default) возвращает прежний путь
`generate + json.loads + ретраи`. Единственный несъёмный код — схемы
(`core/structured.py`) и splitter внутри `chunk_text` (контракт того же поведения).
Удаление тривиально: вернуть старую `chunk_text`.

---

## 5. Тесты (`tests/unit/test_langchain.py`, 26)

### Pydantic-схемы
- `ScoreResult`: кламп `score_percent` (150→100, −5→0), кап списков до 6,
  строкификация пунктов, дефолты, разбор из JSON-совместимого входа.
- `DesignScore`: валидная рубрика → `to_legacy_tuple` (усечение объяснения);
  кламп значений рубрики; неверный набор ключей → `ValidationError`.
- `ClassificationRow`/`ClassificationBatch`: нормализация уровня (junior/middle/senior,
  иначе «middle»), кламп `difficulty_score`, `TypeAdapter`-разбор массива.

### 1A — `format: "json"`
- фейк-`http.post`: `generate(..., format="json")` кладёт `format` в payload;
  без kwargs — ключа нет.

### 1B — гейт `generate_structured`
- fейк-чейн в `_get_structured_chain`: возвращает валидированную модель;
- сломанный чейн → `None` (без проброса исключения наружу).

### Ветки в точках вызова (фейк-LLM со спай-логом)
- `score_free_answer(use_structured=True)`: structured-путь, `generate` не вызывается,
  в `generate_structured` ушли `schema=ScoreResult`, `tags=["scoring"]`, `metadata`;
- фолбэк: `generate_structured → None` → `generate(format="json")` отдаёт результат;
- legacy-путь (`use_structured=False`): `format="json"` в kwargs, structured не зовётся;
- `score_step`: structured-путь (`DesignScore`), фолбэк при `None` → `format="json"`;
- `classify_batch`: structured-путь через `ClassificationBatch`, фильтр topics → "other",
  legacy-путь с `format="json"`.

### Сценарий 3 — `chunk_text`
- пустой ввод → `[]`, короткий текст → как есть, длинный → все чанки ≤ лимита,
  склейка параграфов работает, невалидные аргументы → `ValueError`.

### Регрессия
- Все старые тесты (173) остаются зелёными: фейки принимают `**kwargs`,
  `use_structured` по умолчанию `False`, сигнатуры сохранены.

---

## 6. DoD и чек-лист

- [x] `langchain-ollama`, `langchain-text-splitters` — прямые зависимости
- [x] `src/config.py`: `llm_structured_output` (default `false`)
- [x] `.env.example`: блок LangChain
- [x] `src/core/structured.py`: схемы + валидация (клампы/капы/рубрика) — офлайн-тесты
- [x] `OllamaClient.generate_structured` + трейс LangSmith + `LLMGateway` Protocol
- [x] `format="json"` на всех скоринг-вызовах (sobes/design/classification)
- [x] `use_structured` прокинут из настроек (sobes-сервис, нода дизайна) с фолбэком
- [x] `chunk_text` через `RecursiveCharacterTextSplitter` (контракт сохранён)
- [x] юнит-тесты (26 новых); полный `pytest` зелёный (199); ruff чист на новых/изменённых строках
- [x] план дополнен итогом; README обновлён

---

## 7. Что реально внедрено (итог)

| Файл | Что сделано |
|---|---|
| `pyproject.toml`/`uv.lock` | `langchain-ollama 1.1.0`, `langchain-text-splitters 1.1.2` — прямые зависимости |
| `backend/src/core/structured.py` (новый) | Pydantic-схемы `ScoreResult`/`DesignScore`/`ClassificationRow` + `ClassificationBatch` (`TypeAdapter`); валидация из `parse_score`: кламп 0..100, лимит 6 пунктов, ровно 5 ключей рубрики |
| `backend/src/config.py` | `llm_structured_output` (default `false`) |
| `.env.example` | блок `# LangChain` |
| `backend/src/features/chat/providers/ollama.py` | `format="json"` passthrough (1A); `generate_structured(...)` (1B): ленивая `ChatOllama.with_structured_output(method="json_schema")`, кеш цепей, `None` при сбое, LangSmith-трейс `llm.generate_structured` |
| `backend/src/core/interfaces/llm.py` | Protocol: задокументирован опциональный `generate_structured` |
| `backend/src/features/sobes/domain/scoring.py` | `score_free_answer(..., use_structured=False)`: structured → фолбэк; legacy + `format="json"` |
| `backend/src/features/sobes/domain/classification.py` | `classify_batch(..., use_structured=False)`: `ClassificationBatch`, пошаговый фолбэк по строкам; legacy + `format="json"` |
| `backend/src/features/design/domain/graph.py` | `score_step(..., use_structured=False)`: `DesignScore` в ретрай-цикле; фолбэк `generate(format="json")`; нода передаёт флаг из настроек |
| `backend/src/features/sobes/domain/services.py` | `use_structured` из настроек в scoring и классификацию |
| `backend/src/features/chat/domain/vectorization.py` | `chunk_text` через `RecursiveCharacterTextSplitter` (сепараторы абзац/строка/предложение) + прежняя склейка; валидация и контракт сохранены |
| `tests/unit/test_langchain.py` (новый, 26) | схемы, гейт `generate_structured`, ветки scoring/design/classification, format-json payload, `chunk_text` |

### Отклонения от плана

1. **Сценарий 2 (`ChatOllama` в теле `generate`) не реализован** — он нужен только
   для usage-метрик в LangSmith-трейсах; structured-путь уже использует `ChatOllama`
   (значит, токены есть в его трейсах). Полная замена тела `generate` рискованна
   (контроль над payload/паттерны), отложена до явной потребности.
2. **Сценарий 4 (`QdrantVectorStore` + загрузчики) не реализован** — по плану это
   только при расширении базы вопросов (2+ форматов). Текущий `ingest.py`
   (docx, sha256-дедуп, state-файл) работает и покрыт тестами.
3. **`parse_score`/sobes-парсинг не удалены** — схемы стали эталоном валидации,
   но legacy-парсеры остаются рабочим фолбэком и совместимы со статистикой и
   промптами (как и задумывалось в экологическом плане).
4. **Pydantic-клампы в схемах «мягкие»** (не ошибки) — чтобы structured-путь не
   ломался на диапазонах (0..100, 6 пунктов): жёсткая ошибка остаётся только для
   неверной рубрики (как и в `parse_score`).

### Как включить

```bash
# .env
LLM_STRUCTURED_OUTPUT=true
```

При включении скоринг-вызовы идут через JSON-схему Ollama
(`ChatOllama.with_structured_output`); при сбое модели/сети — автоматический
фолбэк на `generate(format="json")` + ручной парсинг с ретраями.

`format: "json"` у скоринг-вызовов (1A) работает **всегда**, независимо от флага.

### Проверка

```bash
uv run pytest tests/ -q              # 199 passed (было 173 + 26 новых)
uv run ruff check backend/src/ tests/  # новых замечаний в изменённых строках нет
```

Оставшиеся замечания ruff — пред-существующий legacy вне хунков этой интеграции
(`sobes/scoring.py:53` SIM103 — детектор отказа; `sobes/services.py:91` S110 —
обработка кэша), их не трогали.