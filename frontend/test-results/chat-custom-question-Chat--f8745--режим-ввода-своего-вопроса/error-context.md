# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: chat-custom-question.spec.ts >> Chat: Задать свой вопрос >> клик открывает режим ввода своего вопроса
- Location: tests/e2e/chat-custom-question.spec.ts:37:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText(/Вопрос №/).or(getByText(/Загружаем вопрос/))
Expected: visible
Error: strict mode violation: getByText(/Вопрос №/).or(getByText(/Загружаем вопрос/)) resolved to 2 elements:
    1) <div class="_questionBadge_d2tz0_23">Вопрос №—</div> aka getByText('Вопрос №—')
    2) <p>Загружаем вопрос…</p> aka getByText('Загружаем вопрос…')

Call log:
  - Expect "toBeVisible" with timeout 15000ms
  - waiting for getByText(/Вопрос №/).or(getByText(/Загружаем вопрос/))

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - button "← На главную" [ref=e5] [cursor=pointer]
    - heading "Интервью" [level=1] [ref=e7]
    - generic [ref=e8]:
      - button "Переключить тему" [ref=e9] [cursor=pointer]
      - button "📊 Статистика ответов" [ref=e19] [cursor=pointer]
  - paragraph [ref=e20]: Вверху — текущий вопрос. Ниже — поле для вашего ответа и результаты проверки.
  - generic [ref=e21]:
    - generic [ref=e22]: Вопрос №—
    - paragraph [ref=e29]: Загружаем вопрос…
  - button "Задать свой вопрос" [disabled] [ref=e31]
  - generic [ref=e32]: Ваш ответ
  - textbox "Ваш ответ" [disabled] [ref=e33]:
    - /placeholder: Ваш ответ… (Ctrl/Cmd+Enter — отправить)
  - generic [ref=e34]:
    - button "Отправить" [disabled] [ref=e35]
    - generic [ref=e37]: Генерация вопроса…
  - status [ref=e38]: Ответ ассистента появится здесь.
  - generic [ref=e39]:
    - button "💾 Сохранить" [disabled] [ref=e40]
    - button "Следующий вопрос" [disabled] [ref=e41]
```

# Test source

```ts
  1   | /**
  2   |  * Тесты для функциональности «Задать свой вопрос» в режиме Интервью (chat).
  3   |  *
  4   |  * Покрывает:
  5   |  *   - Кнопка «Задать свой вопрос» видна на экране.
  6   |  *   - Клик открывает режим ввода своего вопроса.
  7   |  *   - Ввод вопроса + «Получить ответ» → ответ ассистента.
  8   |  *   - Кнопка «Отмена» возвращает к обычному режиму.
  9   |  *   - После ответа работает кнопка «Сохранить в Word».
  10  |  */
  11  | 
  12  | import { test, expect, type Page } from "@playwright/test";
  13  | 
  14  | const TEST_USERNAME = `chat_custom_${Date.now()}`;
  15  | 
  16  | async function setUsername(page: Page, name: string) {
  17  |   await page.addInitScript((n: string) => {
  18  |     localStorage.setItem("interview-agent:username", n);
  19  |   }, name);
  20  | }
  21  | 
  22  | test.describe("Chat: Задать свой вопрос", () => {
  23  |   test.beforeEach(async ({ page }) => {
  24  |     await setUsername(page, TEST_USERNAME);
  25  |     await page.goto("/");
  26  |     // Переходим в режим Интервью
  27  |     await page.getByText("Интервью").first().click();
  28  |     // Ждём загрузки вопроса (может быть случайный)
> 29  |     await expect(page.getByText(/Вопрос №/).or(page.getByText(/Загружаем вопрос/))).toBeVisible({ timeout: 15000 });
      |                                                                                     ^ Error: expect(locator).toBeVisible() failed
  30  |   });
  31  | 
  32  |   test("кнопка «Задать свой вопрос» отображается на экране", async ({ page }) => {
  33  |     const btn = page.getByRole("button", { name: /Задать свой вопрос/ });
  34  |     await expect(btn).toBeVisible();
  35  |   });
  36  | 
  37  |   test("клик открывает режим ввода своего вопроса", async ({ page }) => {
  38  |     await page.getByRole("button", { name: /Задать свой вопрос/ }).click();
  39  | 
  40  |     // Появляется поле ввода
  41  |     await expect(page.getByPlaceholder(/Какие типы тестов/)).toBeVisible();
  42  |     // Кнопки «Получить ответ» и «Отмена»
  43  |     await expect(page.getByRole("button", { name: /^Получить ответ$/ })).toBeVisible();
  44  |     await expect(page.getByRole("button", { name: /^Отмена$/ })).toBeVisible();
  45  |     // Обычный вопрос скрыт
  46  |     await expect(page.getByText(/Вопрос №/).first()).not.toBeVisible();
  47  |   });
  48  | 
  49  |   test("кнопка «Получить ответ» заблокирована при пустом поле", async ({ page }) => {
  50  |     await page.getByRole("button", { name: /Задать свой вопрос/ }).click();
  51  |     const submitBtn = page.getByRole("button", { name: /^Получить ответ$/ });
  52  |     await expect(submitBtn).toBeDisabled();
  53  | 
  54  |     // После ввода — разблокируется
  55  |     await page.getByPlaceholder(/Какие типы тестов/).fill("Что такое event loop?");
  56  |     await expect(submitBtn).toBeEnabled();
  57  |   });
  58  | 
  59  |   test("«Отмена» возвращает к обычному режиму", async ({ page }) => {
  60  |     await page.getByRole("button", { name: /Задать свой вопрос/ }).click();
  61  |     await page.getByRole("button", { name: /^Отмена$/ }).click();
  62  | 
  63  |     // Возвращается обычный режим
  64  |     await expect(page.getByRole("button", { name: /Задать свой вопрос/ })).toBeVisible();
  65  |     await expect(page.getByPlaceholder(/Какие типы тестов/)).not.toBeVisible();
  66  |   });
  67  | 
  68  |   test(
  69  |     "полный flow: задать вопрос → получить ответ ассистента",
  70  |     async ({ page }) => {
  71  |       await page.getByRole("button", { name: /Задать свой вопрос/ }).click();
  72  | 
  73  |       const customQ = "Что такое GIL в Python?";
  74  |       await page.getByPlaceholder(/Какие типы тестов/).fill(customQ);
  75  |       await page.getByRole("button", { name: /^Получить ответ$/ }).click();
  76  | 
  77  |       // Ждём ответа ассистента
  78  |       await expect(page.getByText(/Ответ ассистента/).or(page.getByText(customQ))).toBeVisible({ timeout: 60000 });
  79  | 
  80  |       // После ответа доступна кнопка «Сохранить в Word»
  81  |       const saveBtn = page.getByRole("button", { name: /Сохранить в Word/ });
  82  |       await expect(saveBtn).toBeVisible({ timeout: 10000 });
  83  |     },
  84  |     { timeout: 120000 },
  85  |   );
  86  | 
  87  |   test(
  88  |     "после ответа на свой вопрос можно перейти к следующему случайному",
  89  |     async ({ page }) => {
  90  |       await page.getByRole("button", { name: /Задать свой вопрос/ }).click();
  91  | 
  92  |       await page.getByPlaceholder(/Какие типы тестов/).fill("Что такое async/await?");
  93  |       await page.getByRole("button", { name: /^Получить ответ$/ }).click();
  94  | 
  95  |       // Ждём ответа
  96  |       await expect(page.getByText(/Ответ ассистента/).or(page.getByText("Что такое async"))).toBeVisible({ timeout: 60000 });
  97  | 
  98  |       // Кнопка «Следующий вопрос» должна появиться
  99  |       const nextBtn = page.getByRole("button", { name: /Следующий вопрос/ });
  100 |       await expect(nextBtn).toBeVisible({ timeout: 5000 });
  101 |     },
  102 |     { timeout: 120000 },
  103 |   );
  104 | });
  105 | 
```