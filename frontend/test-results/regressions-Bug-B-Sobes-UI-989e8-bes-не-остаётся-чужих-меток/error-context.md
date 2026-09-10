# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: regressions.spec.ts >> Bug B: Sobes UI state reset >> после Design в Sobes не остаётся чужих меток
- Location: tests/e2e/regressions.spec.ts:70:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText(/Вопрос №?\d+/)
Expected: visible
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 15000ms
  - waiting for getByText(/Вопрос №?\d+/)
  - Target page, context or browser has been closed

```

```yaml
- banner:
  - button "← На главную"
  - heading "Собеседование" [level=1]
  - button "Переключить тему"
  - button "📊 Статистика ответов"
- paragraph: Выберите уровень и темы. Система подберёт вопросы по темам и будет двигаться от простого к сложному.
- text: Уровень
- combobox "Уровень":
  - option "Junior"
  - option "Middle" [selected]
  - option "Senior"
- text: "Темы ✓ python ✓ db ✓ networks ✓ brokers ✓ os ✓ algorithms ✓ patterns ✓ testing ✓ devops ✓ security ✓ other Вопросов: junior 15–18, middle 18–22, senior 22–25. Порог засчёта: 50%"
- button "Готовим вопросы…" [disabled]
```

# Test source

```ts
  1   | /**
  2   |  * UI-регресс тесты на 4 показанных бага.
  3   |  *
  4   |  * Эти тесты требуют поднятого браузера (chromium). Если в среде нет
  5   |  * возможности запустить браузер, используйте regressions-api.spec.ts —
  6   |  * он покрывает те же баги через API.
  7   |  *
  8   |  *   Bug A — Quiz: варианты ответа видны с текстом (не пустые лейблы).
  9   |  *   Bug B — Sobes: state сбрасывается при start (нет чужих разборов).
  10  |  *   Bug C — Chat: ответ ассистента в .markdown-обёртке.
  11  |  *   Bug C2 — текст не вылезает за контейнер.
  12  |  */
  13  | 
  14  | import { test, expect, type Page } from "@playwright/test";
  15  | 
  16  | const TEST_USERNAME = `regression_ui_${Date.now()}`;
  17  | 
  18  | async function setUsername(page: Page, name: string) {
  19  |   await page.addInitScript((n: string) => {
  20  |     localStorage.setItem("interview-agent:username", n);
  21  |   }, name);
  22  | }
  23  | 
  24  | test.describe("Bug A: Quiz UI", () => {
  25  |   test("4 варианта отображаются с непустым текстом", async ({ page }) => {
  26  |     await setUsername(page, TEST_USERNAME);
  27  |     await page.goto("/");
  28  | 
  29  |     await page.getByText("Тестирование").first().click();
  30  |     await page.getByRole("button", { name: /Начать тест/ }).click();
  31  |     await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 15000 });
  32  | 
  33  |     const radios = page.locator('input[type="radio"]');
  34  |     await expect(radios).toHaveCount(4);
  35  | 
  36  |     // До фикса лейблы были пустыми (opt.text === undefined).
  37  |     const labels = page.locator("label");
  38  |     const count = await labels.count();
  39  |     let nonEmpty = 0;
  40  |     for (let i = 0; i < count; i++) {
  41  |       const txt = (await labels.nth(i).textContent()) ?? "";
  42  |       if (txt.trim().length > 0) nonEmpty++;
  43  |     }
  44  |     expect(nonEmpty).toBeGreaterThanOrEqual(4);
  45  |   });
  46  | 
  47  |   test("submit ответа НЕ даёт 422", async ({ page }) => {
  48  |     await setUsername(page, TEST_USERNAME);
  49  |     await page.goto("/");
  50  | 
  51  |     const failed: string[] = [];
  52  |     page.on("response", (resp) => {
  53  |       if (resp.status() === 422 && resp.url().includes("/quiz/answer")) {
  54  |         failed.push(resp.url());
  55  |       }
  56  |     });
  57  | 
  58  |     await page.getByText("Тестирование").first().click();
  59  |     await page.getByRole("button", { name: /Начать тест/ }).click();
  60  |     await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 15000 });
  61  |     await page.locator('input[type="radio"]').first().click({ force: true });
  62  |     await page.getByRole("button", { name: /Далее/ }).click();
  63  | 
  64  |     await expect(page.getByText(/Вопрос 1 из 20/)).toBeHidden({ timeout: 15000 });
  65  |     expect(failed).toEqual([]);
  66  |   });
  67  | });
  68  | 
  69  | test.describe("Bug B: Sobes UI state reset", () => {
  70  |   test("после Design в Sobes не остаётся чужих меток", async ({ page }) => {
  71  |     await setUsername(page, TEST_USERNAME);
  72  |     await page.goto("/");
  73  | 
  74  |     // Сначала заходим в Design и возвращаемся
  75  |     await page.getByText("Системный дизайн").first().click();
  76  |     await page.getByRole("button", { name: /На главную/ }).click();
  77  | 
  78  |     // Теперь Sobes
  79  |     await page.getByText("Собеседование").first().click();
  80  |     await page.getByRole("button", { name: /Начать собеседование/ }).click();
  81  | 
> 82  |     await expect(page.getByText(/Вопрос №?\d+/)).toBeVisible({ timeout: 15000 });
      |                                                  ^ Error: expect(locator).toBeVisible() failed
  83  | 
  84  |     // Метки Design не должны присутствовать
  85  |     expect(await page.getByText(/News Feed/).count()).toBe(0);
  86  |     expect(await page.getByText(/Шаг 1/).count()).toBe(0);
  87  |   });
  88  | });
  89  | 
  90  | test.describe("Bug C: Chat рендерит ответ как Markdown", () => {
  91  |   test("ответ ассистента появляется в .markdown", async ({ page }) => {
  92  |     await setUsername(page, TEST_USERNAME);
  93  |     await page.goto("/");
  94  | 
  95  |     await page.getByText("Интервью").first().click();
  96  |     await expect(page.locator("text=/Вопрос №\\d+/")).toBeVisible({ timeout: 15000 });
  97  | 
  98  |     await page.locator("textarea").first().fill("Кратко что такое list comprehension?");
  99  |     await page.getByRole("button", { name: /Отправить/ }).click();
  100 | 
  101 |     const markdown = page.locator(".markdown").last();
  102 |     await expect(markdown).toBeVisible({ timeout: 60000 });
  103 |     const txt = (await markdown.textContent()) ?? "";
  104 |     expect(txt.trim()).not.toBe("");
  105 |     expect(txt).not.toBe("Ответ ассистента появится здесь.");
  106 |   });
  107 | });
  108 | 
  109 | test.describe("Bug C2: CSS overflow контракт", () => {
  110 |   test(".output имеет overflow-wrap и word-break", async () => {
  111 |     const fs = await import("fs");
  112 |     const path = await import("path");
  113 |     const cssPath = path.resolve(__dirname, "../src/components/features/chat/chat.module.css");
  114 |     expect(fs.existsSync(cssPath)).toBe(true);
  115 |     const css = fs.readFileSync(cssPath, "utf-8");
  116 |     expect(css).toMatch(/\.output\s*\{[^}]*overflow-wrap\s*:\s*anywhere/);
  117 |     expect(css).toMatch(/\.output\s*\{[^}]*word-break\s*:\s*break-word/);
  118 |   });
  119 | });
  120 | 
```