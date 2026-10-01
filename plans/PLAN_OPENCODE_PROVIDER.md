# План внедрения OpenCode Zen как переключателя провайдера LLM

> **Цель:** переключать генерацию LLM между Ollama (локально) и OpenCode Zen
> (облако) флагом в `.env`. При недоступной Ollama генерация автоматически
> падает на Zen. Эмбеддинги для RAG **всегда** считаются в Ollama, потому что
> Zen их не отдаёт.
>
> **Статус: внедрено и проверено на живом API.** Чат через Zen работает
> (`HTTP 200` на `/api/chat` с `space-bunny-free`).

---

## 1. Установленные эмпирически факты о Zen

Все утверждения ниже проверены `curl` с реальным ключом, а не взяты из
догадок. Первоначальные предположения плана были ошибочны и исправлены.

| Факт | Значение |
|---|---|
| Базовый URL | `https://opencode.ai/zen/v1` (**не** `api.opencode.ai`) |
| Каталог моделей | `GET /zen/v1/models` → 85 моделей |
| Эмбеддинги | `POST /zen/v1/embeddings` → **404**. Эндпоинта нет |
| Эндпоинты чата | `/chat/completions` (OpenAI-совместимый), `/messages` (Anthropic), `/responses` |
| Авторизация | `Authorization: Bearer $OPENCODE_KEY` |
| Free-tier | Почти все «free» модели → **403 `FreeTierError`** при прямом API |
| Рабочая бесплатная модель | **`space-bunny-free`** → HTTP 200 |
| Платные модели | Без пополнения баланса → **402** `Insufficient account funds` |

### Кто НЕ работает через прямой API (проверено, все 403/400)

`big-pickle`, `jev-1.13-free`, `muse-spark-1.3-contributor-free`,
`muse-spark-1.2-contributor-free`, `mimo-v2.6-flash-free`, `mimo-v2.5-free`,
`longcat-2.5-preview-free`, `ling-3.0-flash-fin-free`, `nemotron-3-ultra-free`,
`nemotron-3.5-lightning-free`, `fledge-alpha-free`, `deepseek-v4-flash-free`.

Причина по документации: эти модели бесплатны **внутри OpenCode** и
используются для сбора отзывов. Из чужого процесса через API они недоступны.

### Reasoning-бюджет — главная причина «не всегда доходят вопросы»

Zen-модели — reasoning-модели: часть `max_tokens` уходит на внутренние
размышления, и `message.content` приходит **пустым**. Замеры для
`space-bunny-free` на реальном вопросе собеседования:

| `max_tokens` | `content` | usage |
|---|---|---|
| 40 | `''` (пусто) | reasoning съел весь бюджет |
| 512 | `'Да.'` | 43 из 45 completion-токенов — reasoning |
| 1024 | пусто / обрыв | **908** thinking-токенов, `finish_reason=length` |
| 1024 + `reasoning_effort=low` | 652 символа | **33** thinking-токена, `finish_reason=stop` |

Ключевой параметр — **`reasoning_effort`**. Замер latency:

| Запрос | Время | thinking-токены | content |
|---|---|---|---|
| без `reasoning_effort` | **14.1s** | 908 | finish=length, почти пусто |
| `reasoning_effort="low"` | **4.1s** | 33 | finish=stop, нормальный ответ |

`reasoning_effort="none"` и `thinking: {"type": "disabled"}` провайдер
отклоняет с HTTP 400 (`invalid_request_error`).

Реализация:
- `_MIN_MAX_TOKENS = 1024` — приподнимает маленький бюджет вызывающего кода
  (а он передаёт 200/300/600 в `question_enricher.py:153`,
  `quiz_generator.py:79`, `sobes/scoring.py:120,141`);
- `OPENCODE_REASONING_EFFORT=low` (дефолт `low`) — убирает и пустые ответы,
  и 14-секундные задержки;
- `_rejects_param()` — если модель не принимает параметр (HTTP 400 с
  `invalid`/`unsupported` и упоминанием `reasoning_effort`), запрос
  автоматически повторяется без него, один раз;
- пустой content больше не возвращается молча — это `RuntimeError` с
  actionable-текстом.

Сквозная задержка `/api/chat` после фикса: 5.9–10.5s против 14s+ и пустых ответов.

---

## 2. Архитектура

```
main.py: lifespan
   │
   ├── settings.llm_provider == "opencode" ──► OpenCodeClient   (генерация)
   └── settings.llm_provider == "ollama"  ──► OllamaClient
                                                  │
                                        ping() == False?
                                                  │
                                          да ─────┴──► close() → OpenCodeClient
                                                   нет ──► OllamaClient (прежний путь)

Qdrant/ingest ──► CompositeLLMClient(llm=<выбранный>, embedder=OllamaClient)
                     generate*  → llm        (Zen или Ollama)
                     embed      → embedder    (всегда Ollama)
```

Ключевое решение: `embed` **не** в `OpenCodeClient` вообще. Эмбеддинги
изолированы в отдельном поле `Settings.embed_provider` (в данный момент
единственное допустимое значение — `ollama`), потому что Zen эмбеддингов
не предоставляет.

`CompositeLLMClient` решает ровно то, что делает фолбэк генерации
бесполезным для RAG: когда Ollama выключена, `/api/chat` ещё отвечает
(через Zen), но ingest и поиск по векторам — нет. Разделение делает это
ошибкой конфигурации с понятным логом, а не 500 внутри поиска.

---

## 3. Настройки

### `backend/src/config.py`

```python
llm_provider: Literal["ollama", "opencode"] = "ollama"
opencode_key: str = ""
opencode_url: str = "https://opencode.ai/zen/v1"
opencode_model: str = "space-bunny-free"
opencode_timeout_sec: float = 120.0
opencode_reasoning_effort: str = "low"
embed_provider: Literal["ollama"] = "ollama"
```

`opencode_embed_model`, `opencode_embed_dim`, `OPENCODE_EMBED_*` из раннего
черновика плана **удалены**: они описывали несуществующий `/embeddings`.

### `.env` / `.env.example` / `docker-compose.yml`

```
LLM_PROVIDER=ollama
OPENCODE_KEY=oc_sk_...
OPENCODE_URL=https://opencode.ai/zen/v1
OPENCODE_MODEL=space-bunny-free
OPENCODE_TIMEOUT_SEC=120
OPENCODE_REASONING_EFFORT=low
```

---

## 4. Что внедрено

| Файл | Что сделано |
|---|---|
| `backend/src/config.py` | Поля `llm_provider`, `opencode_*`, `embed_provider` |
| `backend/src/features/chat/providers/opencode.py` | `OpenCodeClient`: `ping`, `generate`, `generate_structured`, `close`. Без `embed` |
| `backend/src/features/chat/providers/composite.py` | `CompositeLLMClient`: `generate*` → llm, `embed` → embedder |
| `backend/src/features/chat/providers/__init__.py` | Экспорт клиентов |
| `backend/src/main.py` | Фабрика провайдера, fallback генерации на Zen, отдельный Ollama-embedder для Qdrant |
| `.env.example`, `docker-compose.yml`, `.env` | Переменные `LLM_PROVIDER` и `OPENCODE_*` |
| `backend/src/main.py` | `_log_ingest_failure()` — сбой индексации при выключенной Ollama логируется одной actionable-строкой без traceback; неожиданные ошибки сохраняют traceback |
| `tests/unit/test_opencode_provider.py` | 34 юнита: бюджет токенов, пустой ответ, `reasoning_effort` и его retry |
| `tests/unit/test_ingest_failure_logging.py` | 3 юнита: разделение ожидаемого/неожиданного сбоя индексации |

### Обработка ошибок

`_HINTS` превращают коды в actionable-сообщения:

- **401** → «проверьте `OPENCODE_KEY`»
- **402** → «нет средств, пополните баланс либо используйте `space-bunny-free`»
- **403** → «free-tier модель недоступна для прямого API, используйте
  `space-bunny-free`»
- **404** → «неверный `OPENCODE_URL` или модели нет в каталоге»
- HTTP 200 с не-JSON телом → «проверьте `OPENCODE_URL`» (ловит
  `api.opencode.ai`, отдающий `Not Found`)

---

## 5. Проверка

```bash
uv run pytest tests/unit/ -q     # 202 passed
uv run ruff check backend/src/features/chat/providers/ backend/src/config.py
docker compose up -d --build --force-recreate api
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Привет! Ответь одним коротким предложением."}'
```

Фактический ответ Zen:

```json
{"answer":"Привет! Готов ответить.","meta":{"used_rag":false,...}}
```

---

## 6. Открытые ограничения

1. **Без Ollama не работает RAG.** Zen эмбеддингов не даёт. Генерация
   выживает, индексация docx и поиск по векторам — нет. Лог при старте:
   `Ollama недоступна (...) — эмбеддингов не будет`.
2. **Бесплатный тариф ограничен одной моделью.** `space-bunny-free` —
   единственная проверенная рабочая free-модель для прямого API; наличие
   остальных может меняться. Проверка одной командой описана в §1.
3. **`ping()` проверяет только `/models`** и не видит 402/403 по конкретной
   модели. Fallback срабатывает по недоступности Ollama, а не по балансу Zen.
4. **Structured output требует `langchain-openai`**, которого нет в
   зависимостях. Пока путь не включён — идёт фолбэк на `generate()` +
   ручной парсинг. Для включения: `uv add langchain-openai`.
5. **Runtime-фолбэк Zen → Ollama не реализован.** Есть только стартовый
   выбор и стартовый фолбэк Ollama → Zen.
6. **Сбой индексации при выключенной Ollama** — теперь одна строка WARNING
   вместо ~60 строк traceback в логе при каждом старте. Состояние не
   изменилось: RAG требует Ollama.
7. **`tests/integration/test_lang_integrations.py` не собирается** —
   pre-existing `ImportError: cannot import name 'ClassifyWarehouse'`. Не
   связано с этой задачей.

---

## 7. Как переключить

```bash
# Zen приоритетно
LLM_PROVIDER=opencode

# Ollama, но с автоматическим фолбэком генерации на Zen, если она выключена
LLM_PROVIDER=ollama

# Только Ollama (текущее поведение проекта по умолчанию)
# — поднять Ollama, иначе генерация уйдёт на Zen
```

Для стабильной работы с RAG Ollama должна быть запущена. Для гарантированно
бесплатной генерации — `OPENCODE_MODEL=space-bunny-free`.