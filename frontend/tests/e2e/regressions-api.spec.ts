/**
 * Регресс-тесты на 4 показанных бага через API (без браузера).
 *
 * Эти тесты проверяют контракты HTTP API, на которых держится фронт.
 * Они не требуют поднятого UI и могут запускаться в CI как первая линия защиты.
 *
 *   Bug A — Quiz: options контракт list[str].
 *   Bug B — Sobes: /start возвращает DTO с непустым text.
 *   Bug C — Chat: /api/chat возвращает Markdown в answer.
 *   Bug C2 — проверяется статически (CSS-контракт) в regressions-ui.spec.ts.
 */

import { test, expect } from "@playwright/test";

const TEST_USERNAME = `regression_api_${Date.now()}`;

test.describe("Bug A: Quiz options контракт", () => {
  test("/quiz/start возвращает options: list[str] из 4 непустых элементов", async ({ request }) => {
    const r = await request.post("http://127.0.0.1:8000/api/quiz/start", {
      data: { level: "middle" },
      headers: { "X-Username": `${TEST_USERNAME}_a` },
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(Array.isArray(body.options)).toBe(true);
    expect(body.options).toHaveLength(4);
    for (const opt of body.options) {
      expect(typeof opt).toBe("string");
      expect(opt.trim().length).toBeGreaterThan(0);
    }
  });

  test(
    "/quiz/answer принимает selected_index и возвращает next_question с тем же контрактом",
    async ({ request }) => {
      const start = await request.post("http://127.0.0.1:8000/api/quiz/start", {
        data: { level: "middle" },
        headers: { "X-Username": `${TEST_USERNAME}_a2` },
      });
      const sBody = await start.json();
      const ans = await request.post("http://127.0.0.1:8000/api/quiz/answer", {
        data: {
          session_id: sBody.session_id,
          question_id: sBody.question_id,
          selected_index: 0,
        },
        headers: { "X-Username": `${TEST_USERNAME}_a2` },
      });
      expect(ans.status()).toBe(200);
      const ansBody = await ans.json();
      expect(ansBody.next_question).toBeTruthy();
      expect(Array.isArray(ansBody.next_question.options)).toBe(true);
      expect(ansBody.next_question.options).toHaveLength(4);
    },
    { timeout: 60000 },
  );
});

test.describe("Bug B: Sobes start DTO контракт", () => {
  test(
    "/sobesedovanie/start возвращает question.text непустым",
    async ({ request }) => {
      const r = await request.post("http://127.0.0.1:8000/api/sobesedovanie/start", {
        data: { level: "middle", topics: ["python"] },
        headers: { "X-Username": `${TEST_USERNAME}_b` },
      });
      expect(r.ok()).toBeTruthy();
      const body = await r.json();
      expect(body.session_id).toMatch(/^sobes_/);
      expect(typeof body.total_planned).toBe("number");
      expect(body.question).toBeTruthy();
      expect(typeof body.question.text).toBe("string");
      expect(body.question.text.trim().length).toBeGreaterThan(0);
      expect(["junior", "middle", "senior"]).toContain(body.question.level);
      expect(typeof body.question.difficulty_score).toBe("number");
    },
    { timeout: 90000 },
  );

  test(
    "/sobesedovanie/answer возвращает next_question с тем же контрактом",
    async ({ request }) => {
      const start = await request.post("http://127.0.0.1:8000/api/sobesedovanie/start", {
        data: { level: "middle", topics: ["python"] },
        headers: { "X-Username": `${TEST_USERNAME}_b2` },
      });
      const sBody = await start.json();
      const ans = await request.post("http://127.0.0.1:8000/api/sobesedovanie/answer", {
        data: {
          session_id: sBody.session_id,
          question_id: sBody.question.id,
          user_answer: "Тестовый ответ про GIL и многопоточность",
        },
        headers: { "X-Username": `${TEST_USERNAME}_b2` },
      });
      expect(ans.status()).toBe(200);
      const body = await ans.json();
      if (body.next_question) {
        expect(typeof body.next_question.text).toBe("string");
        expect(body.next_question.text.trim().length).toBeGreaterThan(0);
      }
    },
    { timeout: 60000 },
  );
});

test.describe("Bug C: Chat возвращает непустой answer (Markdown)", () => {
  test("/api/chat возвращает непустую строку в answer", async ({ request }) => {
    const r = await request.post("http://127.0.0.1:8000/api/chat", {
      data: { message: "Привет, кратко что такое list comprehension?", session_id: "test_regression_chat" },
      headers: { "X-Username": `${TEST_USERNAME}_c` },
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(typeof body.answer).toBe("string");
    expect(body.answer.trim().length).toBeGreaterThan(0);
  });
});

test.describe("Smoke: ручки статистики и пользователя", () => {
  test("/users/me создаёт и возвращает пользователя", async ({ request }) => {
    const r = await request.get("http://127.0.0.1:8000/api/users/me", {
      headers: { "X-Username": `${TEST_USERNAME}_smoke` },
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(body.username).toBe(`${TEST_USERNAME}_smoke`);
  });

  test("/stats/overview возвращает 4 фичи", async ({ request }) => {
    const r = await request.get("http://127.0.0.1:8000/api/stats/overview", {
      headers: { "X-Username": `${TEST_USERNAME}_smoke` },
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(body.features).toHaveProperty("quiz");
    expect(body.features).toHaveProperty("sobes");
    expect(body.features).toHaveProperty("design");
    expect(body.features).toHaveProperty("chat");
  });

  test("/stats/overview без X-Username отдаёт 400", async ({ request }) => {
    const r = await request.get("http://127.0.0.1:8000/api/stats/overview");
    expect(r.status()).toBe(400);
  });

  test("/stats/quiz возвращает агрегаты", async ({ request }) => {
    const r = await request.get("http://127.0.0.1:8000/api/stats/quiz", {
      headers: { "X-Username": `${TEST_USERNAME}_smoke` },
    });
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(body).toMatchObject({
      feature: "quiz",
      total: expect.any(Number),
      correct: expect.any(Number),
      incorrect: expect.any(Number),
    });
  });
});
