# LangChain — фактическая реализация

Этот документ заменяет первоначальный план интеграции. LangChain является обязательным транспортным и структурным слоем для LLM-вызовов; отдельного legacy-пути генерации напрямую через HTTP больше нет.

## Что использует приложение

- `ChatOllama` обслуживает обычные и структурированные вызовы Ollama.
- `ChatOpenAI` обслуживает OpenCode Zen через OpenAI-совместимый API.
- `OllamaEmbeddings` считает эмбеддинги для RAG независимо от выбранного провайдера генерации.
- `RecursiveCharacterTextSplitter` нарезает документы на чанки для индексации.
- `ScoreResult`, `DesignScore` и `ClassificationBatch` задают Pydantic-формы ответов там, где нужны данные с конкретными полями.
- `WrongAnswers` задаёт список из трёх неверных вариантов для генератора квиза.

## Поведение при ошибках

Скоринг, классификация и генерация неправильных вариантов квиза используют `with_structured_output` всегда. Если вызов завершился ошибкой или схема не прошла валидацию, провайдер возвращает `None`, а вызывающая функция использует безопасную деградацию. Системный дизайн повторяет structured-вызов до трёх раз перед стандартной ошибкой оценки. Прямого HTTP/JSON-парсинга как запасного генеративного маршрута нет.

Обычные текстовые функции вызывают LangChain-модель через `ainvoke()`. HTTP-клиенты в адаптерах используются только для проверок доступности (`ping`) и не вызывают API генерации. Эмбеддинги также обёрнуты интеграцией LangChain.

## Основные точки кода

- `backend/src/features/chat/providers/ollama.py` — `ChatOllama`, `OllamaEmbeddings` и общий Ollama-адаптер.
- `backend/src/features/chat/providers/opencode.py` — `ChatOpenAI` для OpenCode Zen.
- `backend/src/core/structured.py` и `backend/src/features/sobes/domain/` — схемы, скоринг и классификация.
- `backend/src/features/design/domain/graph.py` — structured-оценка шагов дизайн-интервью.
- `backend/src/features/chat/domain/vectorization.py` — разделение текстов для RAG.

## Настройки и зависимости

Переключателя `LLM_STRUCTURED_OUTPUT` больше нет: структурированный путь обязателен для задач скоринга и классификации. LangSmith tracing остаётся независимой настройкой и не влияет на выбор LangChain-провайдера.

Прямые зависимости: `langchain-ollama`, `langchain-openai`, `langchain-text-splitters`; `langchain-core` используется их базовыми интерфейсами.
