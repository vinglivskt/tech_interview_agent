import { expect, test } from "@playwright/test";

test("loads an interview question for a Cyrillic user name", async ({ page }) => {
  let usernameHeader = "";
  await page.route("**/api/interview/random-question", async (route) => {
    usernameHeader = route.request().headers()["x-username"] ?? "";
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ number: 7, question: "Что такое GIL?", total: 1 }),
    });
  });

  await page.goto("/");
  await page.getByLabel("Ваше имя").fill("Иван Петров");
  await page.getByRole("button", { name: "Начать" }).click();
  await page.getByText("Интервью").last().click();

  await expect(page.getByText("Что такое GIL?")).toBeVisible();
  expect(usernameHeader).toBe(encodeURIComponent("Иван Петров"));
});

test("sends the displayed question together with the candidate answer", async ({ page }) => {
  let chatMessage = "";
  await page.route("**/api/interview/random-question", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ number: 101, question: "Итератор и генератор", total: 1 }),
    });
  });
  await page.route("**/api/chat", async (route) => {
    chatMessage = JSON.parse(route.request().postData() ?? "{}").message;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ answer: "Разбор ответа", meta: {} }),
    });
  });

  await page.goto("/");
  await page.getByLabel("Ваше имя").fill("Иван");
  await page.getByRole("button", { name: "Начать" }).click();
  await page.getByText("Интервью").last().click();
  await page.getByLabel("Ваш ответ").fill("штука полезная");
  await page.getByRole("button", { name: "Отправить" }).click();

  await expect(page.getByText("Разбор ответа")).toBeVisible();
  expect(chatMessage).toContain("Вопрос: Итератор и генератор");
  expect(chatMessage).toContain("Мой ответ: штука полезная");
});
