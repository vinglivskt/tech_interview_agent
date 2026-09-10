# План: Переработка фронтенда — темы, дизайн-система, шрифты и анимации

> Цель: навести порядок во внешнем виде без единой поломки в логике приложения
> (Chat / Quiz / Sobes / Design / Stats / WelcomeModal работают как раньше).

## Контекст и ограничения (обязательно сохранить)

Фронтенд: React 18 + Vite + TypeScript + CSS Modules (Vite хэширует классы).
Архитектура уже соблюдает паттерн **Container/Presentation** (`index.tsx` + `presentation.tsx` + hook `useX.ts`) — сохраняем его, меняем только представление и стили.

Тестовые контракты, которые НЕЛЬЗЯ трогать:

| Контракт | Где | Почему важно |
|---|---|---|
| Текст кнопок: «Начать тест», «Далее →», «Начать собеседование», «Начать проектирование», «Отправить», «На главную», «Задать свой вопрос», «Получить ответ», «Отмена», «Следующий вопрос», «Сохранить в Word» | presentation | Playwright e2e ищет по имени роли |
| `role="dialog"`, placeholder `/Алексей/`, кнопка «Начать» | WelcomeModal | e2e welcome-модалки |
| localStorage-ключ `interview-agent:username` | UserContext | e2e задаёт имя через init-script |
| Текст `Вопрос №—` / `/Вопрос №\d+/`, `Вопрос 1 из 20`, `Шаг 1 из` | chat/quiz/sobes/design | e2e |
| `data-testid="design-scenario-list"`, `role="button"`, класс `styles.selected`, текст карточек сценариев | design | unit-тест `design-setup.test.tsx` |
| CSS-правило `.output { ... overflow-wrap: anywhere; word-break: break-word; }` | chat.module.css | e2e читает исходник |
| Элемент с классом `markdown` в DOM | Markdown | e2e `.markdown` |
| `input[type="radio"]` (4 штуки) | quiz | e2e |
| Семантические классы CSS-модулей, используемые в `presentation.tsx` | все `.module.css` | имена классов должны остаться |

Кнопки/блоки остаются на своих местах, состояние (useChat/useQuiz/useSobes/useDesign) не трогаем вообще.

## Что делаем

### 1. Дизайн-токены и темы — `src/styles/globals.css`
- Вводятся семантические CSS-переменные: поверхности (`--bg`, `--panel`, `--bg-soft`),
  текст (`--text`, `--muted`, `--text-soft`), бренд/акцент (`--accent`, `--accent-hover`,
  `--accent-soft`, `--accent-border`, `--focus-ring`), статусы (`--success`, `--warning`,
  `--danger` + их «мягкие» фоны и тексты), код (`--code-bg`, `--code-text`, `--pre-bg`),
  тени (`--shadow-sm/md/lg`), радиусы, шрифтовые токены (`--font-ui`, `--font-mono`).
- `:root` = **светлая** тема (дефолт/возможен просмотр до загрузки JS),
  `[data-theme="dark"]` = **тёмная** (текущая палитра приложения сохраняется как dark).
- `color-scheme: light/dark` — нативные элементы (скроллбары, select, date) подстраиваются.
- Тёмные «жёстко зашитые» цвета (#fff, #0b1018, #fef2f2, #16a34a и т.п.) заменяются токенами.
- Типографика: уточнённая системная стек-функция, `--font-mono`, `--font-heading`,
  числовой `font-variant-numeric: tabular-nums` для метрик.
- Анимации: `fadeInUp`, `scaleIn`, `shimmer`, уважение к `prefers-reduced-motion`.
- Плавный «переход темы» через transition на поверхностях.

### 2. Тема-механизм — `src/components/state/ThemeContext.tsx`
- `ThemeProvider` + `useTheme()`.
- Приоритет темы: `localStorage("interview-agent:theme")` → `prefers-color-scheme`.
- Применяет `data-theme` на `<html>`, обновляет `<meta name="theme-color">`.
- Слушает системные изменения темы, пока пользователь не выбрал свою.
- Без SSR-ломки; изменения идемпотентны (StrictMode-safe).

### 3. Защита от «flash» — `frontend/index.html`
- Инлайн-скрипт в `<head>`: до первой отрисовки читает сохранённую тему или системную
  и сразу ставит `data-theme` на `<html>`.
- Добавляем `<meta name="theme-color">`.

### 4. Переключатель темы — `src/components/ui/ThemeToggle/`
- Кнопка-«пилюля» с иконками солнца/луны (inline SVG), скользящим «бегунком».
- Доступность: `aria-pressed`, `aria-label`, фокус-кольцо, работа с клавиатуры.
- Ставится:
  - в `FeatureHeader` (все экраны фич: chat/quiz/sobes/design),
  - в шапку `StatsView`,
  - на домашний экран `App` (правый верхний угол),
  - в оверлей `WelcomeModal` (до входа в систему тоже можно сменить тему).

### 5. Обновление UI-примитивов
- **Button** — вариации через токены, hover/active-состояния, focus-visible-кольцо, тени, анимация нажатия.
- **Card** — hoverable-карточка: подъём, тень, плавные переходы.
- **Spinner** — токены, плавность, reduced-motion.
- **Markdown** — в `Markdown/index.tsx` добавить литеральный класс `markdown` рядом с модульным
  (исправляет e2e-контракт `.markdown`); стили кода/цитат/ссылок на токенах обеих тем.
- **WelcomeModal** — поверхности/ошибки на токенах (сейчас жёстко белые), анимация появления, фокус-стили.

### 6. Обновление CSS фич (chat/quiz/sobes/design + StatsView)
- Все цвета → токены (тёмная и светлая темы работают автоматически).
- Кастомные select (стрелка-chevron), аккуратные радио-варианты ответов (с сохранением
  реальных `input[type=radio]`), улучшенные состояния выбора (`.selected`).
- Ховеры карточек/опций/тем: подъём + тень; прогресс-бары: сглаженный «shimmer» и переход ширины.
- Появление экранов по смене представления (лёгкий fade/translate на `.container`).
- В `chat.module.css` сохраняется контракт `.output { overflow-wrap: anywhere; word-break: break-word; }`.

### 7. Верификация
1. `npm run typecheck`
2. `npm run lint`
3. `npm run test` (vitest) — в т.ч. `design-setup.test.tsx`
4. (если доступен бэкенд) `npm run test:e2e` — полный fly-through всех режимов.

## Что НЕ делаем
- НЕ меняем hooks и containers (вся бизнес-логика untouched).
- НЕ меняем тексты, role/data-testid, идентификаторы полей ввода.
- НЕ трогаем API-слой и заголовки.
- НЕ подключаем внешние шрифты/CDN — стек полностью системный (офлайн-safe).