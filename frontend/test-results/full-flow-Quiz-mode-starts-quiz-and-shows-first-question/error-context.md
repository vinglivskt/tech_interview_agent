# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: full-flow.spec.ts >> Quiz mode >> starts quiz and shows first question
- Location: tests/e2e/full-flow.spec.ts:78:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText(/Вопрос 1 из 20/)
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for getByText(/Вопрос 1 из 20/)

```

```yaml
- banner:
  - button "← На главную"
  - heading "Тестирование" [level=1]
  - button "📊 Статистика ответов"
- paragraph: Выберите уровень сложности и начните тест из 20 вопросов
- text: Уровень
- combobox "Уровень":
  - option "Junior (лёгкие вопросы)"
  - option "Middle (средние вопросы)" [selected]
  - option "Senior (сложные вопросы)"
- button "Начать тест"
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
  21  |     await expect(page.getByText("Python Interview Assistant")).toBeVisible();
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
> 85  |     await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 10000 });
      |                                                    ^ Error: expect(locator).toBeVisible() failed
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
  122 |   });
  123 | });
  124 | 
  125 | test.describe("Design mode", () => {
  126 |   test.beforeEach(async ({ page }) => {
  127 |     await setUsername(page, TEST_USERNAME);
  128 |     await page.goto("/");
  129 |   });
  130 | 
  131 |   test("starts design and shows first step", async ({ page }) => {
  132 |     await page.getByText("Системный дизайн").first().click();
  133 |     await expect(page.getByRole("button", { name: /Начать проектирование/ })).toBeVisible({ timeout: 10000 });
  134 |     await page.getByRole("button", { name: /Начать проектирование/ }).click();
  135 | 
  136 |     // Должен появиться шаг сценария
  137 |     await expect(page.getByText(/Шаг 1 из/)).toBeVisible({ timeout: 10000 });
  138 |   });
  139 | 
  140 |   test("submitting design answer shows analysis with score and explanation", async ({ page }) => {
  141 |     await page.getByText("Системный дизайн").first().click();
  142 |     await page.getByRole("button", { name: /Начать проектирование/ }).click();
  143 |     await expect(page.getByText(/Шаг 1 из/)).toBeVisible({ timeout: 10000 });
  144 | 
  145 |     // Вводим ответ
  146 |     const textarea = page.locator("textarea").first();
  147 |     await textarea.fill("Это мой ответ на вопрос. Я думаю, что нам нужна очередь сообщений и база данных.");
  148 | 
  149 |     // Отправляем
  150 |     await page.getByRole("button", { name: /Далее|Следующий|Ответ/ }).first().click();
  151 | 
  152 |     // После отправки должна появиться оценка / разбор
  153 |     // Ждём до 15 секунд (LLM может работать долго)
  154 |     await expect(page.getByText(/Оценка:|Разбор|Ваш ответ/i)).toBeVisible({ timeout: 20000 });
  155 |   });
  156 | });
  157 | 
  158 | test.describe("Stats API", () => {
  159 |   test("returns user profile", async ({ request }) => {
  160 |     const resp = await request.get("http://127.0.0.1:8000/api/users/me", {
  161 |       headers: { "X-Username": "api_tester" },
  162 |     });
  163 |     expect(resp.ok()).toBeTruthy();
  164 |     const body = await resp.json();
  165 |     expect(body.username).toBe("api_tester");
  166 |   });
  167 | 
  168 |   test("returns overview with all 4 features", async ({ request }) => {
  169 |     const resp = await request.get("http://127.0.0.1:8000/api/stats/overview", {
  170 |       headers: { "X-Username": "api_tester" },
  171 |     });
  172 |     expect(resp.ok()).toBeTruthy();
  173 |     const body = await resp.json();
  174 |     expect(body.features).toHaveProperty("quiz");
  175 |     expect(body.features).toHaveProperty("sobes");
  176 |     expect(body.features).toHaveProperty("design");
  177 |     expect(body.features).toHaveProperty("chat");
  178 |   });
  179 | 
  180 |   test("returns quiz breakdown", async ({ request }) => {
  181 |     const resp = await request.get("http://127.0.0.1:8000/api/stats/quiz", {
  182 |       headers: { "X-Username": "api_tester" },
  183 |     });
  184 |     expect(resp.ok()).toBeTruthy();
  185 |     const body = await resp.json();
```