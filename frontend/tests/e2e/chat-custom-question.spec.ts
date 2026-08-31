/**
 * Тесты для функциональности «Задать свой вопрос» в режиме Интервью (chat).
 *
 * Покрывает:
 *   - Кнопка «Задать свой вопрос» видна на экране.
 *   - Клик открывает режим ввода своего вопроса.
 *   - Ввод вопроса + «Получить ответ» → ответ ассистента.
 *   - Кнопка «Отмена» возвращает к обычному режиму.
 *   - После ответа работает кнопка «Сохранить в Word».
 */

import { test, expect, type Page } from "@playwright/test";

const TEST_USERNAME = `chat_custom_${Date.now()}`;

async function setUsername(page: Page, name: string) {
  await page.addInitScript((n: string) => {
    localStorage.setItem("interview-agent:username", n);
  }, name);
}

test.describe("Chat: Задать свой вопрос", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");
    // Переходим в режим Интервью
    await page.getByText("Интервью").first().click();
    // Ждём загрузки вопроса (может быть случайный)
    await expect(page.getByText(/Вопрос №/).or(page.getByText(/Загружаем вопрос/))).toBeVisible({ timeout: 15000 });
  });

  test("кнопка «Задать свой вопрос» отображается на экране", async ({ page }) => {
    const btn = page.getByRole("button", { name: /Задать свой вопрос/ });
    await expect(btn).toBeVisible();
  });

  test("клик открывает режим ввода своего вопроса", async ({ page }) => {
    await page.getByRole("button", { name: /Задать свой вопрос/ }).click();

    // Появляется поле ввода
    await expect(page.getByPlaceholder(/Какие типы тестов/)).toBeVisible();
    // Кнопки «Получить ответ» и «Отмена»
    await expect(page.getByRole("button", { name: /^Получить ответ$/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Отмена$/ })).toBeVisible();
    // Обычный вопрос скрыт
    await expect(page.getByText(/Вопрос №/).first()).not.toBeVisible();
  });

  test("кнопка «Получить ответ» заблокирована при пустом поле", async ({ page }) => {
    await page.getByRole("button", { name: /Задать свой вопрос/ }).click();
    const submitBtn = page.getByRole("button", { name: /^Получить ответ$/ });
    await expect(submitBtn).toBeDisabled();

    // После ввода — разблокируется
    await page.getByPlaceholder(/Какие типы тестов/).fill("Что такое event loop?");
    await expect(submitBtn).toBeEnabled();
  });

  test("«Отмена» возвращает к обычному режиму", async ({ page }) => {
    await page.getByRole("button", { name: /Задать свой вопрос/ }).click();
    await page.getByRole("button", { name: /^Отмена$/ }).click();

    // Возвращается обычный режим
    await expect(page.getByRole("button", { name: /Задать свой вопрос/ })).toBeVisible();
    await expect(page.getByPlaceholder(/Какие типы тестов/)).not.toBeVisible();
  });

  test(
    "полный flow: задать вопрос → получить ответ ассистента",
    async ({ page }) => {
      await page.getByRole("button", { name: /Задать свой вопрос/ }).click();

      const customQ = "Что такое GIL в Python?";
      await page.getByPlaceholder(/Какие типы тестов/).fill(customQ);
      await page.getByRole("button", { name: /^Получить ответ$/ }).click();

      // Ждём ответа ассистента
      await expect(page.getByText(/Ответ ассистента/).or(page.getByText(customQ))).toBeVisible({ timeout: 60000 });

      // После ответа доступна кнопка «Сохранить в Word»
      const saveBtn = page.getByRole("button", { name: /Сохранить в Word/ });
      await expect(saveBtn).toBeVisible({ timeout: 10000 });
    },
    { timeout: 120000 },
  );

  test(
    "после ответа на свой вопрос можно перейти к следующему случайному",
    async ({ page }) => {
      await page.getByRole("button", { name: /Задать свой вопрос/ }).click();

      await page.getByPlaceholder(/Какие типы тестов/).fill("Что такое async/await?");
      await page.getByRole("button", { name: /^Получить ответ$/ }).click();

      // Ждём ответа
      await expect(page.getByText(/Ответ ассистента/).or(page.getByText("Что такое async"))).toBeVisible({ timeout: 60000 });

      // Кнопка «Следующий вопрос» должна появиться
      const nextBtn = page.getByRole("button", { name: /Следующий вопрос/ });
      await expect(nextBtn).toBeVisible({ timeout: 5000 });
    },
    { timeout: 120000 },
  );
});
