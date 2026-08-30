# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: full-flow.spec.ts >> Welcome modal >> shows welcome modal on first visit and accepts name
- Location: tests/e2e/full-flow.spec.ts:17:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Python Interview Assistant')
Expected: visible
Error: strict mode violation: getByText('Python Interview Assistant') resolved to 2 elements:
    1) <h1 class="_title_1vxkf_21">🐍 Python Interview Assistant</h1> aka getByRole('heading', { name: '🐍 Python Interview Assistant' })
    2) <h1 class="_heroTitle_qqonh_15">Python Interview Assistant</h1> aka getByRole('heading', { name: 'Python Interview Assistant', exact: true })

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText('Python Interview Assistant')

```

# Page snapshot

```yaml
- generic [ref=e2]:
  - dialog [ref=e3]:
    - generic [ref=e4]:
      - heading "🐍 Python Interview Assistant" [level=1] [ref=e5]
      - paragraph [ref=e6]: Личный помощник для подготовки к собеседованиям по Python.
      - paragraph [ref=e7]: Чтобы мы могли сохранять вашу статистику ответов между сессиями — представьтесь. Это нужно для того, чтобы вы могли вернуться и посмотреть, над какими темами стоит поработать ещё.
      - generic [ref=e8]:
        - generic [ref=e9]: Ваше имя
        - textbox "Ваше имя" [active] [ref=e10]:
          - /placeholder: Например, Алексей
        - button "Начать" [ref=e11] [cursor=pointer]
      - paragraph [ref=e12]: Имя используется только как ключ для группировки ваших ответов. Без пароля и регистрации.
  - generic [ref=e14]:
    - generic [ref=e15]:
      - heading "Python Interview Assistant" [level=1] [ref=e16]
      - paragraph [ref=e17]: Выберите режим работы
    - generic [ref=e18]:
      - generic [ref=e19] [cursor=pointer]:
        - generic [ref=e20]: 💬
        - heading "Интервью" [level=3] [ref=e21]
        - paragraph [ref=e22]: Свободный диалог с ассистентом. Задавайте вопросы, получайте ответы с ссылками на базу знаний.
      - generic [ref=e23] [cursor=pointer]:
        - generic [ref=e24]: 📝
        - heading "Тестирование" [level=3] [ref=e25]
        - paragraph [ref=e26]: 20 вопросов с вариантами ответов. Проверьте свои знания и узнайте свой уровень.
      - generic [ref=e27] [cursor=pointer]:
        - generic [ref=e28]: 🎯
        - heading "Собеседование" [level=3] [ref=e29]
        - paragraph [ref=e30]: 15–25 вопросов по темам, свободные ответы, оценка в процентах и финальный вердикт.
      - generic [ref=e31] [cursor=pointer]:
        - generic [ref=e32]: 🏗️
        - heading "Системный дизайн" [level=3] [ref=e33]
        - paragraph [ref=e34]: Проектируйте систему пошагово и получите оценку по архитектурной рубрике.
```

# Test source

```ts
  1   | import { test, expect } from "@playwright/test";
  2   | 
  3   | const TEST_USERNAME = "test_e2e_user";
  4   | 
  5   | test.beforeEach(async ({ context }) => {
  6   |   // Каждый тест начинается с чистого состояния localStorage
  7   |   await context.clearCookies();
  8   | });
  9   | 
  10  | async function setUsername(page: import("@playwright/test").Page, name: string) {
  11  |   await page.addInitScript((n: string) => {
  12  |     localStorage.setItem("interview-agent:username", n);
  13  |   }, name);
  14  | }
  15  | 
  16  | test.describe("Welcome modal", () => {
  17  |   test("shows welcome modal on first visit and accepts name", async ({ page }) => {
  18  |     await page.goto("/");
  19  |     // Модальное окно должно появиться
  20  |     await expect(page.getByRole("dialog")).toBeVisible();
> 21  |     await expect(page.getByText("Python Interview Assistant")).toBeVisible();
      |                                                                ^ Error: expect(locator).toBeVisible() failed
  22  | 
  23  |     // Ввод имени
  24  |     await page.getByPlaceholder(/Алексей/).fill(TEST_USERNAME);
  25  |     await page.getByRole("button", { name: /Начать/ }).click();
  26  | 
  27  |     // Модальное окно скрывается, появляется приветствие
  28  |     await expect(page.getByRole("dialog")).toBeHidden();
  29  |     await expect(page.getByText(TEST_USERNAME)).toBeVisible();
  30  |   });
  31  | });
  32  | 
  33  | test.describe("Home page", () => {
  34  |   test.beforeEach(async ({ page }) => {
  35  |     await setUsername(page, TEST_USERNAME);
  36  |     await page.goto("/");
  37  |   });
  38  | 
  39  |   test("shows 4 mode cards", async ({ page }) => {
  40  |     await expect(page.getByText("Интервью")).toBeVisible();
  41  |     await expect(page.getByText("Тестирование")).toBeVisible();
  42  |     await expect(page.getByText("Собеседование")).toBeVisible();
  43  |     await expect(page.getByText("Системный дизайн")).toBeVisible();
  44  |   });
  45  | 
  46  |   test("stats overview button opens stats view", async ({ page }) => {
  47  |     await page.getByRole("button", { name: /Открыть.*статистику/i }).click();
  48  |     await expect(page.getByText(/Статистика ответов/)).toBeVisible();
  49  |     await expect(page.getByText(TEST_USERNAME)).toBeVisible();
  50  |     // Должны быть карточки для всех 4 режимов
  51  |     await expect(page.getByText("Тестирование")).toBeVisible();
  52  |     await expect(page.getByText("Собеседование")).toBeVisible();
  53  |     await expect(page.getByText("Системный дизайн")).toBeVisible();
  54  |     await expect(page.getByText("Интервью")).toBeVisible();
  55  |   });
  56  | });
  57  | 
  58  | test.describe("Chat mode", () => {
  59  |   test.beforeEach(async ({ page }) => {
  60  |     await setUsername(page, TEST_USERNAME);
  61  |     await page.goto("/");
  62  |   });
  63  | 
  64  |   test("loads random question and shows question number", async ({ page }) => {
  65  |     await page.getByText("Интервью").first().click();
  66  |     // Должен загрузиться вопрос (не "Вопрос №—")
  67  |     await expect(page.locator("text=Вопрос №—")).toBeHidden({ timeout: 10000 });
  68  |     await expect(page.locator("text=/Вопрос №\\d+/")).toBeVisible({ timeout: 10000 });
  69  |   });
  70  | });
  71  | 
  72  | test.describe("Quiz mode", () => {
  73  |   test.beforeEach(async ({ page }) => {
  74  |     await setUsername(page, TEST_USERNAME);
  75  |     await page.goto("/");
  76  |   });
  77  | 
  78  |   test("starts quiz and shows first question", async ({ page }) => {
  79  |     await page.getByText("Тестирование").first().click();
  80  |     // Кнопка "Начать тест" видна
  81  |     await expect(page.getByRole("button", { name: /Начать тест/ })).toBeVisible({ timeout: 10000 });
  82  |     await page.getByRole("button", { name: /Начать тест/ }).click();
  83  | 
  84  |     // Появляется первый вопрос с 4 вариантами
  85  |     await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 10000 });
  86  |     // Должны быть 4 варианта (radio inputs)
  87  |     const radios = page.locator('input[type="radio"]');
  88  |     await expect(radios).toHaveCount(4);
  89  |   });
  90  | 
  91  |   test("submitting an answer advances to next question with explanation", async ({ page }) => {
  92  |     await page.getByText("Тестирование").first().click();
  93  |     await page.getByRole("button", { name: /Начать тест/ }).click();
  94  | 
  95  |     // Ждём загрузки первого вопроса
  96  |     await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 10000 });
  97  | 
  98  |     // Выбираем первый вариант
  99  |     await page.locator('input[type="radio"]').first().click();
  100 |     await page.getByRole("button", { name: /Далее/ }).click();
  101 | 
  102 |     // После ответа должны увидеть либо следующий вопрос, либо результаты
  103 |     // ВАЖНО: должно быть объяснение — это то, что мы проверяли визуально
  104 |     // Сейчас мы только проверяем, что мы НЕ остаёмся на том же вопросе
  105 |     await expect(page.getByText(/Вопрос 1 из 20/)).toBeHidden({ timeout: 10000 });
  106 |   });
  107 | });
  108 | 
  109 | test.describe("Sobes mode", () => {
  110 |   test.beforeEach(async ({ page }) => {
  111 |     await setUsername(page, TEST_USERNAME);
  112 |     await page.goto("/");
  113 |   });
  114 | 
  115 |   test("starts sobes and shows first question", async ({ page }) => {
  116 |     await page.getByText("Собеседование").first().click();
  117 |     await expect(page.getByRole("button", { name: /Начать собеседование|Начать/ })).toBeVisible({ timeout: 10000 });
  118 |     await page.getByRole("button", { name: /Начать собеседование|Начать/ }).click();
  119 | 
  120 |     // Должен появиться первый вопрос
  121 |     await expect(page.getByText(/Вопрос №?\d+/)).toBeVisible({ timeout: 10000 });
```