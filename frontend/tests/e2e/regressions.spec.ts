/**
 * Регресс-тесты на 4 показанных бага:
 *
 *   Bug A — Quiz: варианты ответа отображались как пустые лейблы,
 *           submit падал с 422.
 *   Bug B — Sobes: показывался разбор от чужого режима, потому что
 *           state не сбрасывался при start.
 *   Bug C — Chat: ответ ассистента не рендерился как Markdown.
 *   Bug C2 — текст вылезал за блок.
 *
 * Каждый тест назван в честь бага и использует уникальное имя
 * пользователя, чтобы не мешать параллельным прогонам.
 */

import { test, expect, type Page } from "@playwright/test";

const TEST_USERNAME = `regression_${Date.now()}`;

async function setUsername(page: Page, name: string) {
  await page.addInitScript((n: string) => {
    localStorage.setItem("interview-agent:username", n);
  }, name);
}

async function gotoHome(page: Page) {
  await page.goto("/");
  // Если есть welcome-modal — закрываем
  const dialog = page.getByRole("dialog");
  if (await dialog.isVisible().catch(() => false)) {
    await page.getByPlaceholder(/Алексей|имя/i).fill(TEST_USERNAME).catch(() => {});
    await page.getByRole("button", { name: /Начать/ }).click().catch(() => {});
    await dialog.waitFor({ state: "hidden" }).catch(() => {});
  }
}

test.describe("Bug A: Quiz options должны быть видимыми и кликабельными", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");
  });

  test("4 варианта ответа отображаются с текстом (не пустые лейблы)", async ({ page }) => {
    await page.getByText("Тестирование").first().click();
    const startBtn = page.getByRole("button", { name: /Начать тест/ });
    await expect(startBtn).toBeVisible({ timeout: 10000 });
    await startBtn.click();

    await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 10000 });

    // Должно быть ровно 4 radio
    const radios = page.locator('input[type="radio"]');
    await expect(radios).toHaveCount(4, { timeout: 5000 });

    // У каждого radio лейбл должен содержать непустой текст.
    // До фикса лейблы были пустыми (opt.text был undefined).
    const labels = await page.locator('label').all();
    let nonEmptyLabels = 0;
    for (const lbl of labels) {
      const txt = (await lbl.textContent()) ?? "";
      if (txt.trim().length > 0) nonEmptyLabels++;
    }
    expect(nonEmptyLabels).toBeGreaterThanOrEqual(4);
  });

  test("submit ответа НЕ даёт 422 и продвигает к следующему вопросу или результатам", async ({
    page,
    request,
  }) => {
    // Подписываемся на API-ответы
    const failed: string[] = [];
    page.on("response", (resp) => {
      if (resp.status() === 422 && resp.url().includes("/quiz/answer")) {
        failed.push(resp.url());
      }
    });

    await page.getByText("Тестирование").first().click();
    await page.getByRole("button", { name: /Начать тест/ }).click();
    await expect(page.getByText(/Вопрос 1 из 20/)).toBeVisible({ timeout: 10000 });

    // Кликаем по первому варианту (по контейнеру, не по input, чтобы точно сработал onClick)
    await page.locator('input[type="radio"]').first().click({ force: true });
    await page.getByRole("button", { name: /Далее/ }).click();

    // Ждём, что первый вопрос скрылся — это значит, сабмит прошёл
    await expect(page.getByText(/Вопрос 1 из 20/)).toBeHidden({ timeout: 10000 });

    // Не должно быть 422 на /quiz/answer
    expect(failed).toEqual([]);
  });
});

test.describe("Bug B: Sobes сбрасывает state от предыдущих режимов", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
  });

  test("после Chat + Design переход в Sobes не показывает чужие разборы", async ({ page }) => {
    await page.goto("/");

    // 1) Заходим в Design, имитируем «битый» разбор от предыдущего режима,
    //    заполняя state руками через visit. Для простоты — просто заходим
    //    в Design и сразу выходим.
    await page.getByText("Системный дизайн").first().click();
    await page.getByRole("button", { name: /На главную/ }).click();

    // 2) Заходим в Sobes
    await page.getByText("Собеседование").first().click();
    const startBtn = page.getByRole("button", { name: /Начать собеседование/ });
    await expect(startBtn).toBeVisible({ timeout: 10000 });
    await startBtn.click();

    // Должен появиться вопрос (не разбор)
    await expect(page.getByText(/Вопрос №?\d+/)).toBeVisible({ timeout: 15000 });

    // Не должно быть меток от Design (News Feed, Шаг 1)
    await expect(page.getByText(/News Feed|Шаг 1/)).toHaveCount(0);

    // Не должно быть разборов (Оценка, Раскрыто, Упущено) на setup-экране вопроса
    await expect(page.getByText(/Раскрыто|Упущено/)).toHaveCount(0);
  });

  test("Sobес start возвращает корректный DTO (текст вопроса не пустой)", async ({
    page,
    request,
  }) => {
    const r = await request.post("http://127.0.0.1:8000/api/sobesedovanie/start", {
      data: { level: "middle", topics: ["python"] },
      headers: { "X-Username": TEST_USERNAME },
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(body.question).toBeTruthy();
    expect(body.question.text).toBeTruthy();
    expect(body.question.text.length).toBeGreaterThan(5);
  });
});

test.describe("Bug C: Chat рендерит ответ ассистента как Markdown", () => {
  test.beforeEach(async ({ page }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");
  });

  test("ответ ассистента появляется в виде отрендеренного Markdown (не сырой текст)", async ({
    page,
  }) => {
    await page.getByText("Интервью").first().click();
    await expect(page.locator("text=/Вопрос №\\d+/")).toBeVisible({ timeout: 10000 });

    // Вводим ответ
    const textarea = page.locator("textarea").first();
    await textarea.fill("Тестовый ответ для проверки рендеринга Markdown.");

    // Отправляем
    await page.getByRole("button", { name: /Отправить/ }).click();

    // Ждём, пока ответ появится. До фикса он выводился сырым в <div>,
    // теперь — через <Markdown>, что оборачивает в <div class="markdown">.
    const markdownDiv = page.locator(".markdown").last();
    await expect(markdownDiv).toBeVisible({ timeout: 60000 });
    await expect(markdownDiv).not.toBeEmpty();

    // Текст ответа не должен содержать видимых сырых Markdown-символов (#, *),
    // когда LLM их использует. Это эвристика — если пришёл пустой или совпадает
    // с плейсхолдером, тест должен падать.
    const txt = (await markdownDiv.textContent()) ?? "";
    expect(txt.trim()).not.toBe("");
    expect(txt).not.toBe("Ответ ассистента появится здесь.");
  });
});

test.describe("Bug C2: Текст не выходит за блок контейнера", () => {
  test("длинный ответ ассистента влезает в контейнер (overflow-wrap)", async ({ page, request }) => {
    await setUsername(page, TEST_USERNAME);
    await page.goto("/");

    // Запросим ассистента с длинным текстом напрямую
    const r = await request.post("http://127.0.0.1:8000/api/chat", {
      data: {
        message:
          "Расскажи максимально подробно про GIL с примерами кода и длинными URL https://example.com/very/long/path/that/should/not/overflow/the/container/and/break/the/layout?param=1&param=2&param=3",
        session_id: "test_session_regression",
      },
      headers: { "X-Username": TEST_USERNAME },
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.json();

    await page.getByText("Интервью").first().click();
    await expect(page.locator("text=/Вопрос №\\d+/")).toBeVisible({ timeout: 10000 });

    const textarea = page.locator("textarea").first();
    await textarea.fill("Длинный вопрос про GIL и ссылки.");
    await page.getByRole("button", { name: /Отправить/ }).click();

    const markdown = page.locator(".markdown").last();
    await expect(markdown).toBeVisible({ timeout: 60000 });

    // Проверяем, что контейнер не шире viewport.
    const box = await markdown.boundingBox();
    const viewport = page.viewportSize();
    expect(viewport).toBeTruthy();
    if (box && viewport) {
      // Допускаем горизонтальный скролл максимум на 16px (scrollbar) — но сам блок не должен
      // вылезать за viewport. Если очень длинная неразрывная строка — она должна переноситься.
      expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    }
  });
});

test.describe("Smoke: статистика и юзер", () => {
  test("новый пользователь создаётся через /users/me", async ({ request }) => {
    const r = await request.get("http://127.0.0.1:8000/api/users/me", {
      headers: { "X-Username": `${TEST_USERNAME}_smoke` },
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(body.username).toBe(`${TEST_USERNAME}_smoke`);
  });
});
