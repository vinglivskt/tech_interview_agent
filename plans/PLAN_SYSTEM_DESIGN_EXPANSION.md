# Расширение режима «Системный дизайн» — план (PostgreSQL)

## Цель
Превратить режим из трёх сценариев в полноценный тренажёр с большой библиотекой
кейсов (≈70+), единой «лестницей шагов», эволюцией архитектуры по уровням и
возможностью выбрать сценарий руками либо случайно по уровню/категории.

## Источник истины — PostgreSQL

Сценарии храним в таблице `design_scenarios`. YAML `scenarios.yaml` остаётся
как override-слой для детальных сценариев с `steps` (URL Shortener и т.п.).
Все «новые» сценарии добавляются **YAML-файлом `backend/prompts/design/library.yaml`**
(файл-дамп), который читается при старте через `seed_design_scenarios_from_file()`
и вставляется через `INSERT … ON CONFLICT DO UPDATE` по уникальному ключу `(id)`.

> История: план изначально предполагал SQL-дамп `library.sql`, но реализация
> пошла через существующую универсальную функцию `load_design_scenarios_seed`,
> которая парсит YAML/JSON. Поэтому файл называется `library.yaml` и содержит
> YAML-массив `scenarios:`. Сейчас в нём 118 тем по всем 19 категориям.

## Схема `design_scenarios`

```sql
CREATE TABLE design_scenarios (
    id                  TEXT PRIMARY KEY,           -- 'url-shortener', 'kafka-outbox' …
    title               TEXT NOT NULL,
    level               TEXT NOT NULL,              -- junior | middle | senior
    category            TEXT NOT NULL,              -- basics, read-heavy, realtime, …
    primary_pattern     TEXT NOT NULL DEFAULT '',   -- cache-aside, idempotency, fanout, …
    summary             TEXT NOT NULL,
    requirements        JSONB NOT NULL DEFAULT '[]',
    nfr                 JSONB NOT NULL DEFAULT '[]',
    constraints         JSONB NOT NULL DEFAULT '[]',
    baseline_load       JSONB NOT NULL DEFAULT '{}',
    topics              JSONB NOT NULL DEFAULT '[]',
    tags                JSONB NOT NULL DEFAULT '[]',
    steps               JSONB NOT NULL DEFAULT '[]',         -- [{id,title,prompt,…}]
    acceptance_criteria JSONB NOT NULL DEFAULT '[]',
    evolution           JSONB NOT NULL DEFAULT '[]',         -- [{id,name,summary,diagram,prompts}]
    failure_questions   JSONB NOT NULL DEFAULT '[]',
    advanced_questions  JSONB NOT NULL DEFAULT '[]',
    is_detailed         BOOLEAN NOT NULL DEFAULT FALSE,      -- у YAML-сценариев true
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_design_scenarios_level     ON design_scenarios(level);
CREATE INDEX ix_design_scenarios_category  ON design_scenarios(category);
CREATE INDEX ix_design_scenarios_pattern   ON design_scenarios(primary_pattern);
```

`is_detailed = true` означает, что сценарий содержит полные `steps` и его
можно «проходить». У сценариев из SQL обычно `steps` пустые — это карточка
темы с `evolution`, `failure_questions` и `advanced_questions`. При выборе
такого сценария сервис генерирует динамические шаги по эволюции.

## Репозиторий `DesignScenariosRepository`

```python
class DesignScenariosRepository:
    async def list_brief(level=None, category=None) -> list[dict]
    async def get(id) -> Scenario | None
    async def get_random(level=None, category=None, exclude_ids=()) -> Scenario | None
    async def upsert_many(rows: list[dict]) -> int   # для seed из SQL
```

## Выбор сценария при старте

`POST /api/design/start` теперь принимает:

```json
{
  "level": "middle",
  "scenario_id": "url-shortener",     // опционально
  "category": "realtime",             // опционально
  "random": true                      // опционально: случайный по уровню/категории
}
```

Правила выбора (по приоритету):
1. Если задан `scenario_id` — берём его (id может быть из YAML или из БД).
2. Иначе если `random=true` — случайный по `(level, category?)`, исключая уже
   пройденные пользователем (`design_answers.scenario_id` последних N).
3. Иначе первый по уровню, как сейчас.

## Динамические шаги

Если у сценария `steps` пустые, `DesignService` строит шаги из эволюции:
- Шаг 1 — `clarify` (уточнение требований, опираясь на summary/requirements).
- Шаги 2..N — по `evolution[i].prompts` (вопросы интервьюера по каждому уровню).
- Финальный шаг — `failure_questions`: «Ответьте, что произойдёт, если …».
- Для senior — добавляется шаг `advanced` из `advanced_questions`.

Рубрика и expected_points берутся дефолтные (`reqs`, `arch`, `data`, `scale`,
`tradeoffs` по 0.2). LLM вольна оценивать по контексту шага.

## API изменения

- `GET /api/design/config` → + `categories: [{id, title, count}]`,
  + `total_scenarios: int`.
- `POST /api/design/start` → + `category?`, `random?`.
- `GET /api/design/scenarios/{id}` → детальная карточка (для превью).
- `DesignAnswerResponse` → + `evolution?: [Level]`,
  `failure_questions?: [str]` (для UI).

## Frontend

- `presentation.tsx`: на экране выбора сценария — секции по категориям
  (аккордеон), счётчик тем, кнопка «Случайный по уровню».
- На экране шага — раскрывающийся блок «Эволюция архитектуры»
  (ascii-схемы из `evolution[*].diagram`), `failure_questions` показываются
  на финальном шаге как «вопросы на подумать».
- Типы `types.ts` расширяем под новые поля.

## Файлы

- `backend/src/db/models.py` → + `DesignScenario` ORM-модель.
- `backend/src/db/repository.py` → + `DesignScenariosRepository`.
- `backend/src/db/writer.py` → + `seed_design_scenarios_from_file(path)`.
- `backend/src/features/design/domain/scenarios.py` →
  добавляем `scenario_from_db_row()`, сохраняем `load_scenarios()` для
  override-слоя YAML.
- `backend/src/features/design/domain/services.py` →
  `DesignService` тянет из БД (через репозиторий) с fallback на YAML.
  Метод `start(level, scenario_id, category, random)`.
  Генерация динамических шагов для «карточек тем».
- `backend/src/features/design/api/router.py` →
  новые эндпоинты, передача параметров.
- `backend/src/features/design/domain/models.py` → DTO.
- `backend/src/main.py` → вызывает seed из SQL при первом старте.
- `backend/prompts/design/library.yaml` → **новый** — большой YAML-дамп (118 тем).
- `README.md` → обновляем раздел «Системный дизайн».
- `tests/` → `test_design_repository.py`, `test_design_library_seed.py`,
  `test_design_dynamic_steps.py`, обновляем `test_design_api.py`.

## Критерии готовности

- `make test` зелёный;
- `ruff` + `pyright` без ошибок;
- При первом старте БД заполняется ≥ 70 сценариев из `library.yaml` (фактически 118);
- `GET /api/design/config` возвращает ≥ 12 категорий;
- `POST /api/design/start {level, random:true}` каждый раз выдаёт
  разный сценарий подходящего уровня;
- `POST /api/design/start {level, category:"realtime", random:true}`
  выдаёт случайный realtime-сценарий;
- Сценарии без `steps` проходятся через динамические шаги по эволюции.

## Статус RAG (открыто)

В `config.py` уже есть `design_rag_top_k` и `design_ingest_state_path`, но в
`DesignService.answer()` RAG-подмешивание **не реализовано** — темы выбираются
напрямую из PostgreSQL (`design_scenarios`) по уровню/категории/рандому без
векторного поиска. Для callback-подмешивания контекста темы в оценку ответа
требуется:
- найти/создать коллекцию в Qdrant и ингостировать карточки тем (`library.yaml`);
- прокинуть `QdrantService` в `DesignService` и добавить поиск в `answer()`.

Это отдельная доработка, не блокирующая выбор и прохождение тем из БД.