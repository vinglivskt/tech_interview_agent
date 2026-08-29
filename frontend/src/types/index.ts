// API Types

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  answer: string;
  meta: Record<string, unknown>;
}

export interface SaveQARequest {
  question: string;
  correct_answer: string;
  session_id?: string;
}

export interface SaveQAResponse {
  status: 'saved' | 'skipped';
}

export interface RandomQuestionResponse {
  number: number;
  question: string;
  total: number;
}

// Quiz Types
export interface QuizOption {
  index: number;
  text: string;
}

export interface QuizQuestion {
  session_id: string;
  question_id: string;
  question_text: string;
  options: QuizOption[];
  question_number: number;
  total_questions: number;
}

export interface QuizStartRequest {
  level: 'junior' | 'middle' | 'senior';
}

export interface QuizAnswerRequest {
  session_id: string;
  question_id: string;
  selected_index: number;
}

export interface QuizAnswerResponse {
  is_correct: boolean;
  correct_index: number;
  explanation: string;
  next_question: QuizQuestion | null;
  is_last: boolean;
}

export interface QuizQuestionResult {
  question_text: string;
  user_answer: string;
  correct_answer: string;
  is_correct: boolean;
  explanation: string;
}

export interface QuizResultsResponse {
  total_score: number;
  total_questions: number;
  level: string;
  results: QuizQuestionResult[];
}

// Sobes Types
export interface SobesTopic {
  id: string;
  name: string;
}

export interface SobesConfigResponse {
  topics: SobesTopic[];
  counts_by_level: Record<string, number>;
  pass_threshold: number;
}

export interface SobesQuestion {
  id: string;
  number: number;
  text: string;
  topic: string;
  level: string;
  difficulty_score: number;
  topic_hint?: string;
}

export interface SobesStartRequest {
  level: 'junior' | 'middle' | 'senior';
  topics: string[];
}

export interface SobesStartResponse {
  session_id: string;
  question: SobesQuestion;
  total_planned: number;
}

export interface SobesAnswerRequest {
  session_id: string;
  question_id: string;
  user_answer: string;
}

export interface SobesAnswerResponse {
  score_percent: number;
  is_counted: boolean;
  techlead_explanation: string;
  covered_points: string[];
  missed_points: string[];
  next_question: SobesQuestion | null;
  is_last: boolean;
}

export interface SobesResultsResponse {
  level_requested: string;
  verdict_level: string;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  by_topic: Record<string, { covered: number; missed: number }>;
  details: Array<{
    question: string;
    user_answer: string;
    correct_answer: string;
    is_correct: boolean;
    explanation: string;
  }>;
}

export interface SobesSkipRequest {
  session_id: string;
}

export interface SobesSkipResponse {
  next_question: SobesQuestion | null;
  is_last: boolean;
}

export interface SobesRepeatRequest {
  session_id: string;
}

export interface SobesRepeatResponse {
  question: SobesQuestion;
}

// Design Types
export interface DesignScenario {
  id: string;
  title: string;
  level: string;
}

export interface DesignConfigResponse {
  levels: string[];
  scenarios: DesignScenario[];
  hint_penalty_percent: number;
}

export interface DesignStep {
  step_id: string;
  description: string;
  requirements: string[];
}

export interface DesignScenarioInfo {
  id: string;
  title: string;
  level: string;
}

export interface DesignStartRequest {
  level: string;
  scenario_id: string;
}

export interface DesignStartResponse {
  session_id: string;
  total_steps: number;
  scenario: DesignScenarioInfo;
  step: DesignStep;
}

export interface DesignAnswerRequest {
  session_id: string;
  step_id: string;
  user_answer: string;
}

export interface DesignAnswerResponse {
  score_percent: number;
  rubric: string[];
  covered_points: string[];
  missed_points: string[];
  techlead_explanation: string;
  next_step: DesignStep | null;
  is_last: boolean;
}

export interface DesignHintRequest {
  session_id: string;
  step_id: string;
}

export interface DesignHintResponse {
  hint: string;
  penalty_applied_percent: number;
}

export interface DesignResultsResponse {
  summary: string;
  by_rubric: Array<{ rubric: string; score: number }>;
  strengths: string[];
  weaknesses: string[];
  details: Array<{
    step: string;
    user_answer: string;
    score: number;
    explanation: string;
  }>;
  verdict_level: string;
}

// App Types
export type AppMode = 'home' | 'chat' | 'quiz' | 'sobes' | 'design';
