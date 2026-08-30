/**
 * UI-регресс тесты на 4 показанных бага.
 *
 * Эти тесты требуют поднятого браузера (chromium). Если в среде нет
 * возможности запустить браузер, используйте regressions-api.spec.ts —
 * он покрывает те же баги через API.
 *
 *   Bug A — Quiz: варианты ответа видны с текстом (не пустые лейблы).
 *   Bug B — Sobes: state сбрасывается при start (нет чужих разборов).
 *   Bug C — Chat: ответ ассистента в .markdown-обёртке.
 *   Bug C2 — текст не вылезает за контейнер.
 */

import { test, expect, type Page } from "@playwright/test";

const TEST_USERNAME = `regression_ui_${Date.now()}`;

async function setUsername(page: Page, name: string) {
  await page.addInitScript((n: string) => {
    localStorage.setItem("interview-agent:username", n);
  }, name);
}

test.describe("Bug A: Quiz UI", () => {
  test("4 варианта отображаются с непустым текстом", async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");

    await page.getByText("Тестирование").first().click();
    await page.getByRole("button", { name: /Начать тест/ }).click();
    await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 15000 });

    const radios = page.locator('input[type="radio"]');
    await expect(radios).toHaveCount(4);

    // До фикса лейблы были пустыми (opt.text === undefined).
    const labels = page.locator("label");
    const count = await labels.count();
    let nonEmpty = 0;
    for (let i = 0; i < count; i++) {
      const txt = (await labels.nth(i).textContent()) ?? "";
      if (txt.trim().length > 0) nonEmpty++;
    }
    expect(nonEmpty).toBeGreaterThanOrEqual(4);
  });

  test("submit ответа НЕ даёт 422", async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");

    const failed: string[] = [];
    page.on("response", (resp) => {
      if (resp.status() === 422 && resp.url().includes("/quiz/answer")) {
        failed.push(resp.url());
      }
    });

    await page.getByText("Тестирование").first().click();
    await page.getByRole("button", { name: /Начать тест/ }).click();
    await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 15000 });
    await page.locator('input[type="radio"]').first().click({ force: true });
    await page.getByRole("button", { name: /Далее/ }).click();

    await expect(page.getByText(/Вопрос 1 из 20/)).toBeHidden({ timeout: 15000 });
    expect(failed).toEqual([]);
  });
});

test.describe("Bug B: Sobes UI state reset", () => {
  test("после Design в Sobes не остаётся чужих меток", async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");

    // Сначала заходим в Design и возвращаемся
    await page.getByText("Системный дизайн").first().click();
    await page.getByRole("button", { name: /На главную/ }).click();

    // Теперь Sobes
    await page.getByText("Собеседование").first().click();
    await page.getByRole("button", { name: /Начать собеседование/ }).click();

    await expect(page.getByText(/Вопрос №?\d+/)).toBeVisible({ timeout: 15000 });

    // Метки Design не должны присутствовать
    expect(await page.getByText(/News Feed/).count()).toBe(0);
    expect(await page.getByText(/Шаг 1/).count()).toBe(0);
  });
});

test.describe("Bug C: Chat рендерит ответ как Markdown", () => {
  test("ответ ассистента появляется в .markdown", async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");

    await page.getByText("Интервью").first().click();
    await expect(page.locator("text=/Вопрос №\\d+/")).toBeVisible({ timeout: 15000 });

    await page.locator("textarea").first().fill("Кратко что такое list comprehension?");
    await page.getByRole("button", { name: /Отправить/ }).click();

    const markdown = page.locator(".markdown").last();
    await expect(markdown).toBeVisible({ timeout: 60000 });
    const txt = (await markdown.textContent()) ?? "";
    expect(txt.trim()).not.toBe("");
    expect(txt).not.toBe("Ответ ассистента появится здесь.");
  });
});

test.describe("Bug C2: CSS overflow контракт", () => {
  test(".output имеет overflow-wrap и word-break", async () => {
    const fs = await import("fs");
    const path = await import("path");
    const cssPath = path.resolve(__dirname, "../src/components/features/chat/chat.module.css");
    expect(fs.existsSync(cssPath)).toBe(true);
    const css = fs.readFileSync(cssPath, "utf-8");
    expect(css).toMatch(/\.output\s*\{[^}]*overflow-wrap\s*:\s*anywhere/);
    expect(css).toMatch(/\.output\s*\{[^}]*word-break\s*:\s*break-word/);
  });
});
