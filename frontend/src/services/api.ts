const API_BASE = "/api";

let _username: string | null = null;

export function setApiUsername(name: string | null): void {
  _username = name && name.trim() ? name.trim() : null;
}

export function getApiUsername(): string | null {
  return _username;
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (_username) {
    // HTTP headers must contain only ISO-8859-1 characters.  User names can
    // contain Cyrillic and other Unicode characters, so transport them as
    // percent-encoded UTF-8 and decode them on the API side.
    headers["X-Username"] = encodeURIComponent(_username);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// Chat API
export const chatApi = {
  send: (message: string, sessionId?: string, questionType?: "answer" | "direct_question") =>
    request<{ answer: string; meta: Record<string, unknown> }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId, question_type: questionType }),
    }),

  saveQA: (question: string, correctAnswer: string, sessionId?: string) =>
    request<{ status: "saved" | "skipped"; number?: number }>("/interview/save-qa", {
      method: "POST",
      body: JSON.stringify({ question, correct_answer: correctAnswer, session_id: sessionId }),
    }),

  getRandomQuestion: () => request<{ number: number; question: string; total: number }>("/interview/random-question"),
};

// Quiz API
export const quizApi = {
  start: (level: "junior" | "middle" | "senior") =>
    request<{
      session_id: string;
      question_id: string;
      question_text: string;
      // Бэкенд отдаёт варианты как простой массив строк.
      options: string[];
      question_number: number;
      total_questions: number;
    }>("/quiz/start", {
      method: "POST",
      body: JSON.stringify({ level }),
    }),

  answer: (sessionId: string, questionId: string, selectedIndex: number) =>
    request<{
      is_correct: boolean;
      correct_index: number;
      explanation: string;
      next_question: {
        session_id: string;
        question_id: string;
        question_text: string;
        options: string[];
        question_number: number;
        total_questions: number;
      } | null;
      is_last: boolean;
    }>("/quiz/answer", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        question_id: questionId,
        selected_index: selectedIndex,
      }),
    }),

  getResults: (sessionId: string) =>
    request<{
      total_score: number;
      total_questions: number;
      level: string;
      results: {
        question_text: string;
        user_answer: string;
        correct_answer: string;
        is_correct: boolean;
        explanation: string;
      }[];
    }>(`/quiz/results/${sessionId}`),
};

// Sobes API
export const sobesApi = {
  getConfig: () =>
    request<{
      topics: string[];
      counts_by_level: Record<string, [number, number]>;
      pass_threshold: number;
    }>("/sobesedovanie/config"),

  start: (level: "junior" | "middle" | "senior", topics: string[]) =>
    request<{
      session_id: string;
      question: {
        id: string;
        number: number;
        text: string;
        topic: string;
        level: string;
        difficulty_score: number;
        topic_hint?: string;
      };
      total_planned: number;
    }>("/sobesedovanie/start", {
      method: "POST",
      body: JSON.stringify({ level, topics }),
    }),

  answer: (sessionId: string, questionId: string, userAnswer: string) =>
    request<{
      score_percent: number;
      is_counted: boolean;
      techlead_explanation: string;
      covered_points: string[];
      missed_points: string[];
      next_question: {
        id: string;
        number: number;
        text: string;
        topic: string;
        level: string;
        difficulty_score: number;
        topic_hint?: string;
      } | null;
      is_last: boolean;
    }>("/sobesedovanie/answer", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        question_id: questionId,
        user_answer: userAnswer,
      }),
    }),

  getResults: (sessionId: string) =>
    request<{
      level_requested: string;
      verdict_level: string;
      summary: string;
      summary_detail?: { counted: number; total: number; avg_percent: number };
      strengths: string[];
      weaknesses: string[];
      details: {
        question_text: string;
        topic: string;
        score_percent: number;
        explanation: string;
      }[];
    }>(`/sobesedovanie/results/${sessionId}`),

  skip: (sessionId: string) =>
    request<{
      next_question: {
        id: string;
        number: number;
        text: string;
        topic: string;
        level: string;
        difficulty_score: number;
        topic_hint?: string;
      } | null;
      is_last: boolean;
    }>("/sobesedovanie/skip", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),

  repeat: (sessionId: string) =>
    request<{
      question: {
        id: string;
        number: number;
        text: string;
        topic: string;
        level: string;
        difficulty_score: number;
        topic_hint?: string;
      };
    }>("/sobesedovanie/repeat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),
};

// Design API
export const designApi = {
  getConfig: () =>
    request<{
      levels: string[];
      scenarios: { id: string; title: string; level: string; summary: string }[];
      hint_penalty_percent: number;
    }>("/design/config"),

  start: (level: string, scenarioId: string) =>
    request<{
      session_id: string;
      total_steps: number;
      scenario: { id: string; title: string; level: string };
      step: {
        id: string;
        title: string;
        prompt: string;
      };
    }>("/design/start", {
      method: "POST",
      body: JSON.stringify({ level, scenario_id: scenarioId }),
    }),

  answer: (sessionId: string, stepId: string, userAnswer: string) =>
    request<{
      score_percent: number;
      rubric: string[];
      covered_points: string[];
      missed_points: string[];
      techlead_explanation: string;
      next_step: {
        id: string;
        title: string;
        prompt: string;
      } | null;
      is_last: boolean;
    }>("/design/answer", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        step_id: stepId,
        user_answer: userAnswer,
      }),
    }),

  getHint: (sessionId: string, stepId: string) =>
    request<{
      hint: string;
      penalty_applied_percent: number;
    }>("/design/hint", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, step_id: stepId }),
    }),

  getResults: (sessionId: string) =>
    request<{
      summary: string;
      summary_detail?: { passed: number; steps: number; avg_percent: number };
      by_rubric: Record<string, number>;
      strengths: string[];
      weaknesses: string[];
      verdict_level: string;
      details: {
        title: string;
        user_answer: string;
        score_percent: number;
        explanation: string;
      }[];
    }>(`/design/results/${sessionId}`),
};

// Stats API
export interface StatsBreakdown {
  feature: string;
  total: number;
  correct: number;
  partial: number;
  incorrect: number;
  accuracy_percent: number;
  pass_rate_percent: number;
}

export interface QuizAnswerRow {
  id: string;
  category: "correct" | "partial" | "incorrect";
  question_text: string;
  user_answer: string;
  correct_answer: string;
  is_correct: boolean;
  explanation: string;
  level?: string;
  answered_at: string;
}

export interface SobesAnswerRow {
  id: string;
  category: "correct" | "partial" | "incorrect";
  question_text: string;
  topic: string;
  user_answer: string;
  reference_answer: string;
  score_percent: number;
  is_counted: boolean;
  techlead_explanation: string;
  covered_points: string[];
  missed_points: string[];
  level?: string;
  answered_at: string;
}

export interface DesignAnswerRow {
  id: string;
  category: "correct" | "partial" | "incorrect";
  scenario_id: string;
  step_id: string;
  step_title: string;
  user_answer: string;
  score_percent: number;
  rubric: Record<string, number>;
  techlead_explanation: string;
  covered_points: string[];
  missed_points: string[];
  hint_used: boolean;
  level?: string;
  answered_at: string;
}

export const statsApi = {
  me: () =>
    request<{
      id: string;
      username: string;
      display_name: string;
      created_at: string;
      last_seen_at: string;
    }>("/users/me"),

  overview: () =>
    request<{
      user: { id: string; username: string; display_name: string };
      features: Record<string, StatsBreakdown>;
    }>("/stats/overview"),

  forFeature: (feature: string) => request<StatsBreakdown>(`/stats/${feature}`),

  clearFeature: (feature: string) =>
    request<{ feature: string; deleted: number; status: string }>(`/stats/${feature}`, {
      method: "DELETE",
    }),

  quizAnswers: (opts: { onlyIncorrect?: boolean; onlyPartial?: boolean; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.onlyIncorrect) params.set("only_incorrect", "true");
    if (opts.onlyPartial) params.set("only_partial", "true");
    if (opts.limit) params.set("limit", String(opts.limit));
    const q = params.toString();
    return request<{ feature: string; answers: QuizAnswerRow[]; limit: number; offset: number }>(
      `/stats/quiz/answers${q ? `?${q}` : ""}`,
    );
  },

  sobesAnswers: (opts: { onlyIncorrect?: boolean; onlyPartial?: boolean; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.onlyIncorrect) params.set("only_incorrect", "true");
    if (opts.onlyPartial) params.set("only_partial", "true");
    if (opts.limit) params.set("limit", String(opts.limit));
    const q = params.toString();
    return request<{ feature: string; answers: SobesAnswerRow[]; limit: number; offset: number }>(
      `/stats/sobes/answers${q ? `?${q}` : ""}`,
    );
  },

  designAnswers: (opts: { onlyIncorrect?: boolean; onlyPartial?: boolean; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.onlyIncorrect) params.set("only_incorrect", "true");
    if (opts.onlyPartial) params.set("only_partial", "true");
    if (opts.limit) params.set("limit", String(opts.limit));
    const q = params.toString();
    return request<{ feature: string; answers: DesignAnswerRow[]; limit: number; offset: number }>(
      `/stats/design/answers${q ? `?${q}` : ""}`,
    );
  },

  chatPairs: (limit = 10) =>
    request<{
      feature: string;
      pairs: Array<{ user_message: string; assistant_answer: string; created_at: string }>;
      total: number;
    }>(`/stats/chat/answers?limit=${limit}`),
};
