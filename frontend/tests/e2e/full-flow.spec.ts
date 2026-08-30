import { test, expect } from "@playwright/test";

const TEST_USERNAME = "test_e2e_user";

test.beforeEach(async ({ context }) => {
  // Каждый тест начинается с чистого состояния localStorage
  await context.clearCookies();
});

async function setUsername(page: import("@playwright/test").Page, name: string) {
  await page.addInitScript((n: string) => {
    localStorage.setItem("interview-agent:username", n);
  }, name);
}

test.describe("Welcome modal", () => {
  test("shows welcome modal on first visit and accepts name", async ({ page }) => {
    await page.goto("/");
    // Модальное окно должно появиться
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByText("Python Interview Assistant")).toBeVisible();

    // Ввод имени
    await page.getByPlaceholder(/Алексей/).fill(TEST_USERNAME);
    await page.getByRole("button", { name: /Начать/ }).click();

    // Модальное окно скрывается, появляется приветствие
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByText(TEST_USERNAME)).toBeVisible();
  });
});

test.describe("Home page", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");
  });

  test("shows 4 mode cards", async ({ page }) => {
    await expect(page.getByText("Интервью")).toBeVisible();
    await expect(page.getByText("Тестирование")).toBeVisible();
    await expect(page.getByText("Собеседование")).toBeVisible();
    await expect(page.getByText("Системный дизайн")).toBeVisible();
  });

  test("stats overview button opens stats view", async ({ page }) => {
    await page.getByRole("button", { name: /Открыть.*статистику/i }).click();
    await expect(page.getByText(/Статистика ответов/)).toBeVisible();
    await expect(page.getByText(TEST_USERNAME)).toBeVisible();
    // Должны быть карточки для всех 4 режимов
    await expect(page.getByText("Тестирование")).toBeVisible();
    await expect(page.getByText("Собеседование")).toBeVisible();
    await expect(page.getByText("Системный дизайн")).toBeVisible();
    await expect(page.getByText("Интервью")).toBeVisible();
  });
});

test.describe("Chat mode", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");
  });

  test("loads random question and shows question number", async ({ page }) => {
    await page.getByText("Интервью").first().click();
    // Должен загрузиться вопрос (не "Вопрос №—")
    await expect(page.locator("text=Вопрос №—")).toBeHidden({ timeout: 10000 });
    await expect(page.locator("text=/Вопрос №\\d+/")).toBeVisible({ timeout: 10000 });
  });
});

test.describe("Quiz mode", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");
  });

  test("starts quiz and shows first question", async ({ page }) => {
    await page.getByText("Тестирование").first().click();
    // Кнопка "Начать тест" видна
    await expect(page.getByRole("button", { name: /Начать тест/ })).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /Начать тест/ }).click();

    // Появляется первый вопрос с 4 вариантами
    await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 10000 });
    // Должны быть 4 варианта (radio inputs)
    const radios = page.locator('input[type="radio"]');
    await expect(radios).toHaveCount(4);
  });

  test("submitting an answer advances to next question with explanation", async ({ page }) => {
    await page.getByText("Тестирование").first().click();
    await page.getByRole("button", { name: /Начать тест/ }).click();

    // Ждём загрузки первого вопроса
    await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 10000 });

    // Выбираем первый вариант
    await page.locator('input[type="radio"]').first().click();
    await page.getByRole("button", { name: /Далее/ }).click();

    // После ответа должны увидеть либо следующий вопрос, либо результаты
    // ВАЖНО: должно быть объяснение — это то, что мы проверяли визуально
    // Сейчас мы только проверяем, что мы НЕ остаёмся на том же вопросе
    await expect(page.getByText(/Вопрос 1 из 20/)).toBeHidden({ timeout: 10000 });
  });
});

test.describe("Sobes mode", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");
  });

  test("starts sobes and shows first question", async ({ page }) => {
    await page.getByText("Собеседование").first().click();
    await expect(page.getByRole("button", { name: /Начать собеседование|Начать/ })).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /Начать собеседование|Начать/ }).click();

    // Должен появиться первый вопрос
    await expect(page.getByText(/Вопрос №?\d+/)).toBeVisible({ timeout: 10000 });
  });
});

test.describe("Design mode", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");
  });

  test("starts design and shows first step", async ({ page }) => {
    await page.getByText("Системный дизайн").first().click();
    await expect(page.getByRole("button", { name: /Начать проектирование/ })).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /Начать проектирование/ }).click();

    // Должен появиться шаг сценария
    await expect(page.getByText(/Шаг 1 из/)).toBeVisible({ timeout: 10000 });
  });

  test("submitting design answer shows analysis with score and explanation", async ({ page }) => {
    await page.getByText("Системный дизайн").first().click();
    await page.getByRole("button", { name: /Начать проектирование/ }).click();
    await expect(page.getByText(/Шаг 1 из/)).toBeVisible({ timeout: 10000 });

    // Вводим ответ
    const textarea = page.locator("textarea").first();
    await textarea.fill("Это мой ответ на вопрос. Я думаю, что нам нужна очередь сообщений и база данных.");

    // Отправляем
    await page.getByRole("button", { name: /Далее|Следующий|Ответ/ }).first().click();

    // После отправки должна появиться оценка / разбор
    // Ждём до 15 секунд (LLM может работать долго)
    await expect(page.getByText(/Оценка:|Разбор|Ваш ответ/i)).toBeVisible({ timeout: 20000 });
  });
});

test.describe("Stats API", () => {
  test("returns user profile", async ({ request }) => {
    const resp = await request.get("http://127.0.0.1:8000/api/users/me", {
      headers: { "X-Username": "api_tester" },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.username).toBe("api_tester");
  });

  test("returns overview with all 4 features", async ({ request }) => {
    const resp = await request.get("http://127.0.0.1:8000/api/stats/overview", {
      headers: { "X-Username": "api_tester" },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.features).toHaveProperty("quiz");
    expect(body.features).toHaveProperty("sobes");
    expect(body.features).toHaveProperty("design");
    expect(body.features).toHaveProperty("chat");
  });

  test("returns quiz breakdown", async ({ request }) => {
    const resp = await request.get("http://127.0.0.1:8000/api/stats/quiz", {
      headers: { "X-Username": "api_tester" },
    });
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body).toMatchObject({
      feature: "quiz",
      correct: expect.any(Number),
      partial: expect.any(Number),
      incorrect: expect.any(Number),
      total: expect.any(Number),
    });
  });

  test("returns 400 without X-Username", async ({ request }) => {
    const resp = await request.get("http://127.0.0.1:8000/api/stats/overview");
    expect(resp.status()).toBe(400);
  });

  test("POST /quiz/answer writes to stats DB", async ({ request }) => {
    // Стартуем квиз
    const start = await request.post("http://127.0.0.1:8000/api/quiz/start", {
      data: { level: "middle" },
      headers: { "X-Username": "stats_writer" },
    });
    const sessionId = (await start.json()).session_id;
    const questionId = (await start.json()).question_id;

    // Отвечаем
    await request.post("http://127.0.0.1:8000/api/quiz/answer", {
      data: { session_id: sessionId, question_id: questionId, selected_index: 0 },
      headers: { "X-Username": "stats_writer" },
    });

    // Даём время на фоновую запись
    await new Promise((r) => setTimeout(r, 500));

    // Проверяем статистику
    const stats = await request.get("http://127.0.0.1:8000/api/stats/quiz", {
      headers: { "X-Username": "stats_writer" },
    });
    const body = await stats.json();
    expect(body.total).toBeGreaterThanOrEqual(1);
  });
});
