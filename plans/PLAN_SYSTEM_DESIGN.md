# Режим «Системный дизайн» — спецификация формата

Цель: имитировать реальный системный дизайн‑раунд. Пользователь пошагово проектирует систему, отвечает в свободной форме, получает оценку по рубрике и финальную сводку.

---

## 1) Формат сценариев (источник заданий)

Сценарии храним в YAML/JSON (любой), один файл с массивом сценариев. Предпочтительно: `app/prompts/design/scenarios.yaml`.

Схема сценария:
- `id: string` — уникальный идентификатор (kebab-case)
- `title: string` — название (например, «URL Shortener»)
- `level: "junior" | "middle" | "senior"` — базовый уровень сложности
- `summary: string` — краткое описание задачи
- `requirements: string[]` — функциональные требования (списком)
- `nfr: string[]` — нефункциональные: SLO/SLA, latency, availability, cost и т.п.
- `constraints: string[]` — явные ограничения (например, «нет транзакций между сервисами»)
- `baseline_load: { rps?: number, dau?: number, qps?: number, storage_gb?: number }` — ориентиры нагрузки (опционально)
- `topics: string[]` — целевые темы (кэш, БД, очереди, консистентность, API, мониторинг, и т.п.)
- `steps: Step[]` — шаги «лестницы» (см. ниже)
- `acceptance_criteria: string[]` — что обязательо должно прозвучать к концу дизайна

Схема шага Step:
- `id: string` — уникальный id шага внутри сценария
- `title: string` — заголовок шага (например, «Уточнение требований»)
- `prompt: string` — текст задания пользователю
- `expected_points: string[]` — ключевые пункты, которых ждём в ответе (используются для оценки/hints)
- `rubric_weights: { reqs?: number, arch?: number, data?: number, scale?: number, tradeoffs?: number }` — веса для этого шага (0..1, суммарно ≈1)
- `hint: string` — краткая подсказка по шагу (опционально, для кнопки «Подсказка»)

Пример (YAML):
```yaml
- id: url-shortener
  title: URL Shortener
  level: junior
  summary: Проектирование сервиса сокращения ссылок
  requirements:
    - генерировать короткую ссылку по длинной
    - редиректить по короткой
    - счётчик переходов
  nfr:
    - низкая латентность чтения
    - высокая доступность
  constraints:
    - уникальность коротких ссылок
  baseline_load:
    rps: 1500
  topics: [api, db, cache, consistency, monitoring]
  steps:
    - id: clarify
      title: Уточнение требований
      prompt: Сформулируй и уточни функциональные/нефункциональные требования, границы системы
      expected_points:
        - перечислил явные функциональные требования
        - выделил нефункциональные (latency, availability)
        - уточнил границы и ограничения
      rubric_weights: { reqs: 0.6, tradeoffs: 0.4 }
      hint: Начни с функциональных требований и SLO, затем зафиксируй ограничения
    - id: hla
      title: High-level архитектура
      prompt: Опиши основные компоненты и взаимодействия
      expected_points:
        - входной API и балансировщик
        - приложение/шардинг/реплики
        - хранилище ключ→значение и/или SQL, кэш перед БД
      rubric_weights: { arch: 0.7, scale: 0.3 }
      hint: Набросай блок-схему: API → App → Cache → DB, где и зачем нужен кэш
  acceptance_criteria:
    - чёткая HLA со слоями и кэшем
    - понимание компромиссов консистентности
```

---

## 2) Поток (UX) и шаги

- Уровень выбирается пользователем: junior/middle/senior
- Сценарий подбирается автоматически по уровню (или пользователь выбирает из списка)
- Шаги (пример лестницы):
  1) Уточнение требований (clarify)
  2) High-level архитектура (hla)
  3) Датамодель/хранилища (data)
  4) Масштабирование, кэш/очереди, отказоустойчивость (scale)
  5) API/контракты и идемпотентность (api)
  6) Узкие места и trade-offs (tradeoffs)
- На каждом шаге: свободный ответ → LLM‑оценка (JSON) → краткое объяснение «как техлид»
- Кнопка «Подсказка» — показывает `hint`, снижает итоговый балл шага на N% (например, 10)
- Итог: агрегированный отчёт по рубрике + вердикт уровня «system design»

---

## 3) Рубрика и оценка

Базовые категории (используются как поля в JSON‑оценке):
- `reqs` — работа с требованиями/границами
- `arch` — high-level архитектура и корректность взаимодействий
- `data` — датамодель, БД, индексы, консистентность
- `scale` — масштабирование, отказоустойчивость, кэш, очереди, мониторинг, SRE аспекты
- `tradeoffs` — компромиссы, риски, осознанные решения

Вес шага задаётся через `rubric_weights` в сценарии. Суммарный финальный процент — средневзвешенное по шагам (порог засчёта шага — ≥ 50%).

---

## 4) Формат JSON‑ответов LLM (строгий)

Оценка шага (strict JSON):
```json
{
  "score_percent": 0,                   
  "rubric": {                          
    "reqs": 0, "arch": 0, "data": 0, "scale": 0, "tradeoffs": 0
  },
  "covered_points": ["..."],          
  "missed_points": ["..."],           
  "techlead_explanation": "..."       
}
```
Правила:
- только указанные поля; `score_percent` — целое 0..100
- `rubric` — целые 0..100 по имеющимся ключам (пропущенные считать 0)
- `covered_points`/`missed_points` — до 6 кратких пунктов
- `techlead_explanation` — не более `design_max_explanation_len` символов

Подсказка (strict JSON) — если решим генерировать подсказку через LLM:
```json
{ "hint": "очень краткая подсказка по текущему шагу" }
```

---

## 5) API‑контракты

- `GET /api/design/config`
  - Выход: `{ levels: ["junior","middle","senior"], scenarios: [{id,title,level}], hint_penalty_percent: number }`

- `POST /api/design/start`
  - Вход: `{ level: "junior|middle|senior", scenario_id?: string }`
  - Выход: `{ session_id: string, total_steps: number, scenario: { id,title,level,summary }, step: { id,title,prompt } }`

- `POST /api/design/answer`
  - Вход: `{ session_id: string, step_id: string, user_answer: string }`
  - Выход: `{
      score_percent: number,
      rubric: { reqs?: number, arch?: number, data?: number, scale?: number, tradeoffs?: number },
      covered_points: string[],
      missed_points: string[],
      techlead_explanation: string,
      next_step?: { id,title,prompt },
      is_last: boolean
    }`

- `POST /api/design/hint`
  - Вход: `{ session_id: string, step_id: string }`
  - Выход: `{ hint: string, penalty_applied_percent: number }`

- `GET /api/design/results/{session_id}`
  - Выход: `{
      summary: { steps: number, passed: number, avg_percent: number },
      by_rubric: { reqs: number, arch: number, data: number, scale: number, tradeoffs: number },
      strengths: string[],
      weaknesses: string[],
      details: [ { step_id, title, score_percent, rubric, explanation } ],
      verdict_level: "junior|middle|senior"
    }`

---

## 6) Состояние сессии (в памяти)

`sessions[session_id]`:
- `scenario_id: string`
- `level_requested: string`
- `steps_order: string[]`
- `current_index: number`
- `answers: array` элементов:
  - `{ step_id, user_answer, score_percent, rubric, covered_points, missed_points, techlead_explanation, hint_used?: boolean }`

Правила:
- При `hint_used` к `score_percent` шага применяется штраф `design_hint_penalty_percent` (урезается, но не ниже 0)

---

## 7) Конфигурация (`app/core/config.py`)

Добавить поля:
- `design_levels: ["junior","middle","senior"]` — доступные уровни
- `design_hint_penalty_percent: number` — штраф за подсказку, по умолчанию 10
- `design_pass_threshold_percent: number` — ≥50 по аналогии с собеседованием
- `design_max_explanation_len: number` — 600 (по аналогии)
- `design_scenarios_path: string` — путь к YAML/JSON с заданиями

---

## 8) Фронтенд (минимальный интерфейс)

- Карточка «Системный дизайн» на главной
- Экран настроек: выбрать уровень и сценарий (или «любой подходящий»)
- Экран шага:
  - Заголовок шага, текст задания
  - Кнопки: «Подсказка» (с предупреждением о штрафе), «Ответить»
  - Плашка: оценка шага (процент), краткое объяснение техлида, списки covered/missed
  - Прогресс: «Шаг X из N» + прогресс‑бар
- Экран результатов: сводка, by_rubric, сильные/слабые, детали, вердикт

---

## 9) Поведение вердикта уровня

- Подход аналогичен «Собеседованию», но с поправкой на рубрику:
  - ≤ 60%: junior
  - 60–80%: middle
  - > 80%: senior
- Учитывать долю «пройденных» шагов (score_percent шага ≥ design_pass_threshold_percent)

---

## 10) Валидность JSON от LLM

- Жёсткая схема, повторный запрос при невалидном JSON (до 2–3 попыток) с подсказкой «верни только JSON строго по схеме»
- Трим объяснения по `design_max_explanation_len`

---

## 11) Следующие шаги реализации

1) Заложить slice `app/features/design` (api/domain) + prompts (`app/prompts/design/*`)
2) Добавить конфиги (см. п.7)
3) Подготовить 3 сценария (по одному на уровень) в YAML
4) Реализовать сессии: start → answer → hint → results
5) Интегрировать фронтенд с шагами, прогрессом и оценкой
6) Интеграционные тесты: mock LLM, happy-path + невалидный JSON (ретраи)

---

При необходимости могу сразу зашить стартовые сценарии (URL Shortener, News Feed, Object Storage) и каркас API/фронта по этой спецификации.