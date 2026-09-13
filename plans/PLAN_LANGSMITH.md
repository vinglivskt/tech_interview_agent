# План внедрения LangSmith (трассировка LLM-вызовов + эвалы)

> **Цель:** сделать отладку и правку промптов «видящей». Каждый вызов LLM (8 точек в 4 фичах)
> пишется в LangSmith как run с метаданными (фича, session_id, шаг), а правка промптов
> скоринга перестаёт быть слепой: к концу фазы появляется проверяемый **скэффолд
> регрессионного эвала** (выгрузка реальных пар «ответ → оценка» в датасет + прогон).
>
> **Подход:** общий шлюз трассировки на уровне `OllamaClient.generate` — **контракты API
> не меняются**, публичный интерфейс `generate` получает два опциональных параметра
> (`metadata`, `tags`), тестовые фейки (`**kwargs`) не ломаются.
>
> `langsmith 0.12.4` уже присутствует в `uv.lock` (транзитивная через `langchain-core`);
> задача добавляет его **прямой зависимостью** и использует `traceable` + `tracing_context`.

---

## 1. Что трассируем (8 точек вызова LLM)

| # | Файл:строка | Фича | temperature | Семантика вызова → метаданные |
|---|---|---|---|---|
| 1 | `features/design/domain/graph.py:236` | design | 0.2 | скоринг шага → `feature=design, scenario_id, step_id, session_id` |
| 2 | `features/chat/domain/services.py:249` | chat | по умолч. | ответ ассистента → `feature=chat, session_id, question_type`, tag `answer` |
| 3 | `features/chat/domain/services.py:258` | chat | по умолч. | рерайт ответа при CJK → тот же контекст, tag `rus-rewrite` |
| 4 | `features/chat/domain/services.py:293` | chat | по умолч. | self-check/verified → тот же контекст, tag `self-check` |
| 5 | `features/quiz/domain/quiz_generator.py:76` | quiz | 0.8 / 300 | генерация неправильных ответов → `feature=quiz, kind=wrong-answers` |
| 6 | `features/quiz/domain/question_enricher.py:150` | quiz | 0.4 / 200 | обогащение вопроса → `feature=quiz, kind=enricher` |
| 7 | `features/sobes/domain/classification.py:59` | sobes | 0.1 | классификация ответа → `feature=sobes, kind=classification` |
| 8 | `features/sobes/domain/scoring.py:105` | sobes | 0.2 / 600 | скоринг свободного ответа → `feature=sobes, session_id, topic`, tag `scoring` |

Эмбеддинги (`OllamaClient.embed`) **не трассируем** — это не LLM-вызов в смысле «промпта».

---

## 2. Целевая архитектура

```
  8 точек вызова LLM (chat/sobes/quiz/design)
       │   llm.generate(messages, temperature=..., metadata={feature, session_id, ...}, tags=[...])
       ▼
  OllamaClient.generate                          <- публичный интерфейс (обновляем Protocol LLMGateway)
       │
       ├─ трассировка выключена ─► self._raw_generate(...)      // ровно прежнее поведение
       │
       └─ трассировка включена ─► with tracing_context(metadata, tags):
                                    traced_generate(...)         // traceable(name="llm.generate", run_type="llm")
                                                                    project=langsmith_project
                                                                    детали вызова уходят в LangSmith
                ▲
                │
        src/core/langsmith.py (шлюз)
          - tracing_ready(settings)     // флаг + наличие LANGSMITH_API_KEY
          - make_traced_generate(raw, settings, base_metadata, base_tags)  // traceable-обёртка или None
```

Ключевая механика SDK (проверена по коду `langsmith/run_helpers.py`):
- статичные `metadata`/`tags` задаются на декораторе `traceable(...)`;
- **per-call** `metadata`/`tags` подмешиваются через `tracing_context()` (строки
  `_setup_run` 1658–1702: `_context._METADATA`/`_context._TAGS` мержатся в run);
- если трассировка не включена (`tracing_is_enabled()` false) — `traceable` возвращает
  исходную функцию без сети и без ворнингов (no-op, строка 1633).

### Настройки (добавляем в `src/config.py`)

```python
langsmith_tracing: bool = Field(default=False, ...)      # master-выключатель
langsmith_project: str = Field(default="tech-interview-agent", ...)
```

Плюс переменные окружения SDK (документируем в `.env.example` / README, читаются самим
SDK из `os.environ`, в код не заносятся):

```
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_ENDPOINT=http://localhost:1984
# LANGSMITH_TRACING=true  — тут не нужно: код сам ставит, когда включён флаг + есть ключ
```

**Гейт включения** (`tracing_ready`): трассировка реально работает, только если
`langsmith_tracing=true` **и** задан `LANGSMITH_API_KEY` (или `LANGCHAIN_API_KEY`).
Если флаг включён, а ключа нет — логируем warning и продолжаем как раньше (никаких
сетевых попыток / задержек). Это защищает офлайн-first режим проекта.

---

## 2.1 Как это работает простыми словами (с примером)

Раньше каждый раз, когда приложение разговаривало с LLM (оценивало ответ кандидата,
писало ответ в чате, генерировало варианты вопросов), мы **ничего не видели**: ни входов,
ни выходов, ни метрик. Если промпт скоринга завышал оценки — единственная диагностика
— таблица `api_request_logs` без деталей промпта.

**Теперь каждый LLM-вызов проходит через «прозрачное окно» LangSmith.** Контракты кода,
обрабатывающего ответы, не меняются: всё делает обёртка внутри `OllamaClient.generate`.

Что происходит при каждом вызове:

```
1. В коде (напр. роутер чата) формулируется вызов:
       await llm.generate(messages, metadata={"feature":"chat","session_id":"..."}, tags=["answer"])

2. Внутри OllamaClient.generate:
   - если трассировка включена (flaq + ключ): SDK LangSmith сам записывает run:
         name:      llm.generate, run_type: llm
         metadata:  {feature: chat, session_id: s1, provider: ollama, model: qwen2.5:7b}
         tags:      [answer, llm]
         inputs:    [{"role":"system","content":"..."},{"role":"user","content":"..."}]
         outputs:   {"text": "Ответ ассистента..."}
   - если выключена (или нет ключа): вызов идёт напрямую — тот же HTTP к Ollama,
     ровно как раньше (без сети, без задержек).
```

**Живой пример:** голос дизайн-интервью (скоринг шага):

```
curl -X POST localhost:8000/api/design/answer \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"design_url-shortener_1a2b3c4d","step_id":"data","user_answer":"Хранилище — PostgreSQL..."}'
```

В LangSmith вы увидите **один run**:

| Поле | Значение |
|---|---|
| name | `llm.generate` |
| run_type | `llm` |
| inputs | system + user промпт (сценарий + ответ кандидата) |
| outputs | `{"score_percent":80, "rubric":{...}, "covered_points":[...]}` |
| latency | ~340 ms |
| metadata | `feature=design, scenario_id=url-shortener, step_id=data, session_id=..., model=qwen2.5:7b` |
| tags | `[llm, scoring]` |

Сразу видно: какой промпт ушёл, что ответила LLM, какой JSON получился, сколько заняло.
Если что-то сломалось (JSON невалиден, оценка 0) — открываете run и видите точную
причину: системный/пользовательский промпт, ответ модели и ошибку.

**Eval-скэффолд** (раздел 3) добавляет возможность строить из накопленных данных
датасеты и прогонять промпты в «защитном режиме» перед продом.

---

## 3. Eval-скэффолд (Фаза 4 экологического плана — задел)

Новый модуль `backend/src/training/langsmith_eval.py` (пакета `training` ещё нет — создаём):

- `build_scoring_examples(records) -> list[dict]` — **чистая функция**: реальные строки
  из БД (design answer / sobes answer) превращает в пары
  `{"inputs": {feature, question, reference, user_answer}, "outputs": {score_percent, explanation}}`.
  Офлайн-юнит-тестируется без сети.
- `push_scoring_dataset(client, *, dataset_name, records) -> dict` — тонкий pusher:
  `create_dataset` + `create_example` для каждого примера через переданный
  LangSmith-`Client` (в тестах — фейковый client, проверяем только вызовы).

Полноценный прогон эвалов (`langsmith.evaluation.evaluate` + judge-промпт) **не входит**
в эту фазу: он требует живого LangSmith-сервера и накопленных данных — вынесен отдельным
шагом после внедрения трассировки.

---

## 4. Шаги внедрения

1. **Зависимость:** `uv add langsmith` (прямая).
2. **Настройки:** `langsmith_tracing`, `langsmith_project` в `src/config.py`;
   блок `# LangSmith` в `.env.example`; короткий абзац в README.
3. **Шлюз:** новый `backend/src/core/langsmith.py` — `tracing_ready` + `make_traced_generate`.
4. **Клиент:** `OllamaClient.generate` принимает `metadata`/`tags`; в `__init__`
   собираем `self._traced = make_traced_generate(...)`; при вызове — `tracing_context(...)`
   или прямой `_raw_generate`. Обновляем `core/interfaces/llm.py` (Protocol) и док-строку.
5. **8 точек вызова:** прокидываем `metadata=`/`tags=`:
   - chat: `run_chat` получает опциональный `metadata=` от роутера (`session_id`, `question_type`)
     и добавляет `kind`→tags на 3 своих вызова (249/258/293);
   - sobes: `score_free_answer(..., metadata=)` от `services.answer()` (`session_id`, `topic`);
     `classification.py` — локальный `metadata={"feature":"sobes","kind":"classification"}`;
   - quiz: локальные `metadata` в `quiz_generator`/`question_enricher`;
   - design: нода графа передаёт `session_id` в `score_step` → `metadata` на вызове 236.
6. **Эвалы:** пакет `backend/src/training/` + `langsmith_eval.py` (п.3).
7. **Тесты:** юниты (п.5).
8. **Полный прогон:** `uv run pytest tests/ -q` (регрессия 158+) + `uv run ruff check backend/ tests/`.
9. **Документация плана:** секции «как работает простыми словами» и «итог внедрения».

**Откат:** флаг `langsmith_tracing=false` (default) полностью возвращает прежнее поведение;
единственный несъёмный код — 3 небольших модуля (шлюз, eval-скэффолд).

---

## 5. Тесты

### New `tests/unit/test_langsmith_gate.py`
- `tracing_ready`: выкл по флагу; выкл при флаге без ключа (+warning); вкл при флаге+ключе.
- `make_traced_generate`: возвращает `None` при выключенной трассировке (**никаких сетей**);
  при включённой — возвращает обёртку (мок `traceable`: проверяем `name=`, `run_type=`,
  `project_name=`, статичные `metadata`/`tags` и что возвращён именно wrapper).
- `OllamaClient.generate`:
  - трассировка выключена → вызывается `_raw_generate` без `metadata`/`tags` (фейк-http;
    payload без лишних ключей);
  - трассировка включена (мок `tracing_context` + фейк `_traced`) → в контекст ушли
    `metadata` (feature/session_id + provider/model) и `tags`, результат совпадает.
- `run_chat` (fейк-llm): при вызове с `metadata=` — `llm.generate` получает `metadata=`/`tags=`
  на всех трёх ветках (обычный ответ / CJK-рерайт / self-check). **Ноль регрессий** для
  вызова без `metadata` (по умолчанию `None`).
- `score_free_answer` / design `score_step`: фейк-llm перехватывает kwargs — проверяем
  `metadata`/`tags`.
### New `tests/unit/test_langsmith_eval.py`
- `build_scoring_examples` из сырых записей (design + sobes формы) → корректные
  inputs/outputs, нет лишних ключей, пустой вход → `[]`.
- `push_scoring_dataset` с **фейковым client**: создан dataset + примеры, возвращены
  `dataset_id`/`examples`.
### Регрессия
- Полный прогон `uv run pytest tests/ -q` — все старые тесты (158) зелёные: фейки LLM
  принимают `**kwargs`, новых аргументов на старых путях нет.

---

## 6. DoD и чек-лист

- [x] `langsmith` — прямая зависимость в `pyproject.toml`/`uv.lock`
- [x] `src/config.py`: `langsmith_tracing`, `langsmith_project` (default off)
- [x] `.env.example`: блок LangSmith (ключ/endpoint/флаг/проект)
- [x] `src/core/langsmith.py`: `tracing_ready` + `make_traced_generate` (None при выкл., warning без ключа)
- [x] `OllamaClient.generate` (metadata/tags; tracing_context) + `LLMGateway` Protocol
- [x] `metadata`/`tags` на всех 8 точках вызова (chat, sobes, quiz, design) без изменения контрактов API
- [x] `src/training/langsmith_eval.py`: чистая `build_scoring_examples` + `push_scoring_dataset`
- [x] юнит-тесты гейта и эвалов; полный `pytest` зелёный (173); `ruff` чист на новых/изменённых строках
- [x] план дополнен: «как работает простыми словами (с примером)» + «итог внедрения»

---

## 7. Что реально внедрено (итог)

| Файл | Что сделано |
|---|---|
| `backend/src/core/langsmith.py` (новый) | шлюз: `tracing_ready` (флаг + ключ, warning без ключа), `make_traced_generate` (ленивый импорт `traceable`, `None` при выкл.) |
| `backend/src/features/chat/providers/ollama.py` | `_raw_generate` (прежний HTTP), `generate` получил `metadata`/`tags`; при выкл. — прежний прямой вызов, при вкл. — `tracing_context(metadata, tags)` + `_traced_generate` |
| `backend/src/core/interfaces/llm.py` | Protocol `generate` (metadata/tags задокументированы) |
| `backend/src/config.py` | `langsmith_tracing` (default `false`), `langsmith_project` (default `tech-interview-agent`) |
| `.env.example` | блок `# LangSmith` (флаг/проект/ключ/endpoint) |
| `pyproject.toml`/`uv.lock` | `langsmith 0.12.4` — прямая зависимость |
| 8 точек вызова в 4 фичах | `chat/api/router.py` → `run_chat`(metadata: feature/session_id/question_type); `chat/domain/services.py` (tags: `answer`/`rus-rewrite`/`self-check`); `sobes/.../scoring.py` (metadata: feature/kind/topic/session_id, tag `scoring`); `sobes/.../classification.py` (`kind=classification`); `quiz/quiz_generator.py` (`kind=wrong-answers`); `quiz/question_enricher.py` (`kind=enricher`); `design/domain/graph.py` (`score_step(session_id=...)` → metadata feature/scenario_id/step_id[/session_id], tag `scoring`) |
| `backend/src/training/langsmith_eval.py` (новый) | `build_scoring_examples` (чистый) + `push_scoring_dataset` (тонкий pusher) |
| `tests/unit/test_langsmith_gate.py` (новый, 11) | гейт, сборка обёртки, generate untraced/traced, `run_chat` 3 ветки + без metadata, design/sobes metadata |
| `tests/unit/test_langsmith_eval.py` (новый, 4) | builder (design+sobes, пропуск неполных), pusher (создание/повторное использование датасета, фейк-client) |

### Отклонения от плана

1. **Per-call `metadata`/`tags` передаются через `langsmith.tracing_context`**, а не через
   kwargs вызова: в SDK `metadata`/`tags` из kwargs обёртки в сам run не попадают
   (см. `run_helpers.py` — они не читаются из аргументов вызываемого fn). Итог тот же,
   что в эскизе, но реализация честнее к SDK.
2. **Гейт требует API-ключ + флаг** (а не только флаг) — страховка от попыток ходить
   в сеть «вслепую» и тянуть latency в офлайн-режиме.
3. **`langsmith.project env` ставим сами** (`LANGSMITH_PROJECT`) — чтобы проект не зависел
   от ошибочно пустого окружения.
4. **Полноценный eval-раннер НЕ реализован** (`langsmith.evaluation.evaluate`): нужен
   живой сервер + накопленные данные. Реализован только проверяемый скэффолд
   (датасет + builder). Это сознательный объëм фазы 4.

### Как включить

```bash
# docker-compose: развернуть self-hosted LangSmith (не входит в эту фазу) ИЛИ
# использовать облачный проект.
# В .env:
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=tech-interview-agent
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_ENDPOINT=http://localhost:1984
```

### Проверка

```bash
uv run pytest tests/ -q            # 173 passed (было 158 + 15 новых)
uv run ruff check backend/src/core/langsmith.py backend/src/training/langsmith_eval.py tests/unit/test_langsmith_gate.py tests/unit/test_langsmith_eval.py   # all passed
```

Без `LANGSMITH_API_KEY` трассировка не включается (union-тест) — проект остается
офлайн-first; единственные пред-существующие замечания ruff в легаси-файлах не трогались.