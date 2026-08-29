---
scenarios:
  - id: url-shortener
    title: URL Shortener
    level: junior
    summary: Продуктовая команда запускает публичный сервис коротких ссылок. Пользователь вставляет длинный URL, получает короткий адрес и по нему происходит редирект.
    requirements:
      - Создание короткой ссылки для длинного URL
      - Быстрый редирект по короткому коду
      - Базовая статистика переходов
    nfr:
      - p99 редиректа не более 100 мс
      - Высокая доступность чтений
    constraints:
      - Короткий код должен быть уникальным
      - Статистика может обновляться асинхронно
    baseline_load: "{ rps: 1500, dau: 100000, storage_gb: 100 }"
    topics: [api, db, cache, consistency, monitoring]
    steps:
      - id: clarify
        title: Уточнение требований
        prompt: Какие 5–8 вопросов вы зададите о продукте, масштабе, SLA и границах первой версии? После ответов кратко зафиксируйте свои допущения.
        expected_points: [Функциональные требования, SLO и доступность, границы и ограничения]
        rubric_weights: "{ reqs: 0.7, tradeoffs: 0.3 }"
        hint: Разделите требования на функциональные, NFR и то, что не входит в первую версию.
      - id: hla
        title: High-level архитектура
        prompt: Нарисуйте high-level схему и пройдите по write path (создание ссылки) и read path (редирект). Объясняйте назначение каждого компонента, а не только его название.
        expected_points: [API и балансировщик, stateless-приложение, кэш перед БД, отдельный поток статистики]
        rubric_weights: "{ arch: 0.7, scale: 0.3 }"
        hint: Начните со схемы Client → LB → App → Cache → DB и отдельно подумайте о событиях кликов.
      - id: data
        title: Датамодель и хранилище
        prompt: Какой именно ключ вы будете генерировать, где хранить mapping и как гарантировать уникальность? Покажите минимальную датамодель, индексы и модель консистентности.
        expected_points: [Маппинг short_code к URL, уникальный ключ или генератор ID, индекс/партиционирование, TTL или политика удаления]
        rubric_weights: "{ data: 0.8, tradeoffs: 0.2 }"
        hint: Покажите, как гарантируется уникальность кода и почему выбранное хранилище подходит read-heavy нагрузке.
      - id: scale
        title: Масштабирование и отказоустойчивость
        prompt: Нагрузка на редиректы выросла в 10 раз. Как меняются кэш, база и приложение? Что будет при падении кэша и какие метрики с алертами вы заведёте?
        expected_points: [Cache-aside и TTL, реплики и горизонтальное масштабирование, защита от cache stampede, метрики и алерты]
        rubric_weights: "{ scale: 0.8, tradeoffs: 0.2 }"
        hint: Назовите стратегию инвалидации кэша, деградацию при падении кэша и ключевые SLI.
      - id: api
        title: API и идемпотентность
        prompt: "Специфицируйте API создания и редиректа: методы, тела, статусы, валидация. Клиент повторил POST после таймаута — как исключите дубликат?"
        expected_points: [POST для создания, GET/redirect, HTTP-коды и валидация, idempotency key или семантика повторов]
        rubric_weights: "{ reqs: 0.3, arch: 0.3, tradeoffs: 0.4 }"
        hint: Продумайте поведение повторного POST после сетевого таймаута.
      - id: tradeoffs
        title: Узкие места и компромиссы
        prompt: Назовите три наиболее рискованных места дизайна. Сравните последовательный ID, случайный код и хеш URL и защитите свой выбор.
        expected_points: [Коллизии кодов, консистентность статистики, горячие ключи, стоимость и сложность эксплуатации]
        rubric_weights: "{ tradeoffs: 0.7, scale: 0.3 }"
        hint: Сравните последовательный ID, случайный код и хеш URL; у каждого есть цена.
    acceptance_criteria: [Чёткая HLA с кэшем, гарантия уникальности кода, понимание асинхронной статистики]

  - id: news-feed
    title: News Feed
    level: middle
    summary: У социальной сети миллионы активных пользователей. Нужна персональная хронологическая лента публикаций подписок; часть авторов имеет десятки миллионов подписчиков.
    requirements: [Создание публикаций, подписки, персональная лента, лайки и счётчики]
    nfr: [p99 чтения ленты не более 200 мс, высокая доступность, свежесть новых публикаций]
    constraints: [Допускается eventual consistency счётчиков, есть знаменитости с миллионами подписчиков]
    baseline_load: "{ rps: 10000, dau: 1000000, storage_gb: 5000 }"
    topics: [fanout, queues, cache, sharding, consistency, observability]
    steps:
      - id: clarify
        title: Уточнение требований
        prompt: "Что вы уточните про порядок ленты, свежесть нового поста, read/write ratio, pagination и границы MVP? Назовите допущения."
        expected_points: [Типы ленты, freshness и pagination, read/write ratio, границы продукта]
        rubric_weights: "{ reqs: 0.7, tradeoffs: 0.3 }"
        hint: Уточните модель подписок, порядок ленты и допустимую задержку появления поста.
      - id: hla
        title: High-level архитектура
        prompt: "Нарисуйте компоненты и отдельно проведите путь публикации и путь чтения ленты. Где появляются очередь и кэш — и зачем?"
        expected_points: [Сервис публикаций, граф подписок, feed service, очередь и кэш]
        rubric_weights: "{ arch: 0.7, scale: 0.3 }"
        hint: Отдельно опишите write path и read path.
      - id: data
        title: Данные и выдача ленты
        prompt: Опишите модели данных, ключи партиционирования, пагинацию и хранение ленты.
        expected_points: [Post и follow graph, cursor pagination, feed inbox/outbox, индексы и TTL]
        rubric_weights: "{ data: 0.8, tradeoffs: 0.2 }"
        hint: Подумайте, что хранится по user_id и как не получить offset-пагинацию на миллионах строк.
      - id: scale
        title: Масштабирование
        prompt: Разберите fanout-on-write и fanout-on-read, очереди, кэш и работу с celebrity users.
        expected_points: [Гибридный fanout, backpressure и retry, hot key защита, репликация и мониторинг]
        rubric_weights: "{ scale: 0.8, tradeoffs: 0.2 }"
        hint: Для знаменитостей пушить запись во все inbox обычно слишком дорого.
      - id: api
        title: API и надёжность
        prompt: Предложите API публикации и ленты, семантику повторов и обработку удаления.
        expected_points: [Idempotency key, cursor API, дедупликация событий, tombstone или удаление]
        rubric_weights: "{ arch: 0.3, reqs: 0.3, tradeoffs: 0.4 }"
        hint: Продумайте повтор публикации после таймаута клиента.
      - id: tradeoffs
        title: Компромиссы
        prompt: Объясните риски, стоимость и компромиссы решения.
        expected_points: [Свежесть против стоимости, консистентность, celebrity problem, сложность операций]
        rubric_weights: "{ tradeoffs: 0.7, scale: 0.3 }"
        hint: Сформулируйте, почему выбрали именно гибридный подход.
    acceptance_criteria: [Различает стратегии fanout, применяет cursor pagination, учитывает знаменитостей и eventual consistency]

  - id: object-storage
    title: Object Storage
    level: senior
    summary: Компания строит геораспределённое объектное хранилище, совместимое с базовыми операциями S3. Клиенты хранят архивы и медиаданные, включая очень большие объекты.
    requirements: [Загрузка и скачивание объектов, bucket и metadata, multipart upload, versioning]
    nfr: [11 девяток durability, высокая доступность, большие объекты и глобальная репликация]
    constraints: [Нет транзакций между metadata и blob storage, стоимость хранения важна]
    baseline_load: "{ rps: 30000, storage_gb: 10000000 }"
    topics: [metadata, replication, erasure-coding, consistency, api, sre]
    steps:
      - id: clarify
        title: Уточнение требований
        prompt: "Какие вопросы вы зададите о размере объектов, профиле чтения/записи, durability, RPO/RTO, consistency, регионах и цене?"
        expected_points: [Размер и типы операций, RPO/RTO и durability, consistency model, lifecycle и versioning]
        rubric_weights: "{ reqs: 0.7, tradeoffs: 0.3 }"
        hint: Разведите требования к control plane и data plane.
      - id: hla
        title: High-level архитектура
        prompt: Нарисуйте control plane, metadata plane и data plane. Пройдите загрузку и скачивание объекта от клиента до дисков.
        expected_points: [API gateway, metadata service, storage nodes, placement service, background repair]
        rubric_weights: "{ arch: 0.7, scale: 0.3 }"
        hint: Metadata и байты объекта должны масштабироваться независимо.
      - id: data
        title: Метаданные и размещение
        prompt: Опишите схему метаданных, размещение объектов, шардирование и согласованность.
        expected_points: [Bucket/object version metadata, partition key, placement map, quorum или consensus для metadata]
        rubric_weights: "{ data: 0.8, tradeoffs: 0.2 }"
        hint: Покажите, как найти все чанки объекта без глобального сканирования.
      - id: scale
        title: Надёжность и масштабирование
        prompt: Выберите replication/erasure coding, опишите repair, backpressure и наблюдаемость.
        expected_points: [Erasure coding или репликация, checksums и anti-entropy, retry и throttling, метрики durability]
        rubric_weights: "{ scale: 0.8, tradeoffs: 0.2 }"
        hint: Сравните цену, latency и сложность восстановления у репликации и EC.
      - id: api
        title: API и идемпотентность
        prompt: Опишите multipart upload, pre-signed URL, повтор запросов и удаление объектов.
        expected_points: [Upload ID и commit, idempotency, checksum/ETag, lifecycle deletion]
        rubric_weights: "{ reqs: 0.3, arch: 0.3, tradeoffs: 0.4 }"
        hint: Multipart upload должен переживать повтор одной части и незавершённые загрузки.
      - id: tradeoffs
        title: Компромиссы
        prompt: Сформулируйте отказные сценарии, риски и компромиссы решения.
        expected_points: [Split brain metadata, потеря региона, consistency против availability, стоимость egress и repair]
        rubric_weights: "{ tradeoffs: 0.7, scale: 0.3 }"
        hint: Выберите один сложный сбой и пройдите его по шагам.
    acceptance_criteria: [Разделяет metadata и data plane, обосновывает durability, учитывает repair и консистентность]
---

# Сценарии системного дизайна

## URL Shortener (junior)
Продуктовая команда запускает публичный сервис коротких ссылок.

## News Feed (middle)
У социальной сети миллионы активных пользователей.

## Object Storage (senior)
Компания строит геораспределённое объектное хранилище.
