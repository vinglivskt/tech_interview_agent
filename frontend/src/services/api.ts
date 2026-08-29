const API_BASE = '/api';

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// Chat API
export const chatApi = {
  health: () => request<{ status: string; qdrant: boolean; ollama_available: boolean }>('/chat/health'),

  send: (message: string, sessionId?: string) =>
    request<{ answer: string; meta: Record<string, unknown> }>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId }),
    }),

  saveQA: (question: string, correctAnswer: string, sessionId?: string) =>
    request<{ status: string }>('/interview/save-qa', {
      method: 'POST',
      body: JSON.stringify({ question, correct_answer: correctAnswer, session_id: sessionId }),
    }),

  getRandomQuestion: () =>
    request<{ number: number; question: string; total: number }>('/interview/random-question'),
};

// Quiz API
export const quizApi = {
  start: (level: 'junior' | 'middle' | 'senior') =>
    request<import('@/types').QuizQuestion>('/quiz/start', {
      method: 'POST',
      body: JSON.stringify({ level }),
    }),

  answer: (sessionId: string, questionId: string, selectedIndex: number) =>
    request<import('@/types').QuizAnswerResponse>('/quiz/answer', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, question_id: questionId, selected_index: selectedIndex }),
    }),

  getResults: (sessionId: string) =>
    request<import('@/types').QuizResultsResponse>(`/quiz/results/${sessionId}`),
};

// Sobes API
export const sobesApi = {
  getConfig: () => request<import('@/types').SobesConfigResponse>('/sobesedovanie/config'),

  start: (level: 'junior' | 'middle' | 'senior', topics: string[]) =>
    request<import('@/types').SobesStartResponse>('/sobesedovanie/start', {
      method: 'POST',
      body: JSON.stringify({ level, topics }),
    }),

  answer: (sessionId: string, questionId: string, userAnswer: string) =>
    request<import('@/types').SobesAnswerResponse>('/sobesedovanie/answer', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, question_id: questionId, user_answer: userAnswer }),
    }),

  getResults: (sessionId: string) =>
    request<import('@/types').SobesResultsResponse>(`/sobesedovanie/results/${sessionId}`),

  skip: (sessionId: string) =>
    request<import('@/types').SobesSkipResponse>('/sobesedovanie/skip', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }),

  repeat: (sessionId: string) =>
    request<import('@/types').SobesRepeatResponse>('/sobesedovanie/repeat', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }),
};

// Design API
export const designApi = {
  getConfig: () => request<import('@/types').DesignConfigResponse>('/design/config'),

  start: (level: string, scenarioId: string) =>
    request<import('@/types').DesignStartResponse>('/design/start', {
      method: 'POST',
      body: JSON.stringify({ level, scenario_id: scenarioId }),
    }),

  answer: (sessionId: string, stepId: string, userAnswer: string) =>
    request<import('@/types').DesignAnswerResponse>('/design/answer', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, step_id: stepId, user_answer: userAnswer }),
    }),

  getHint: (sessionId: string, stepId: string) =>
    request<import('@/types').DesignHintResponse>('/design/hint', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, step_id: stepId }),
    }),

  getResults: (sessionId: string) =>
    request<import('@/types').DesignResultsResponse>(`/design/results/${sessionId}`),
};
