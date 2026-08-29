export interface SobesConfig {
  topics: string[];
  counts_by_level: Record<string, [number, number]>;
  pass_threshold: number;
}

export interface SobesQuestion {
  id: string;
  number: number;
  text: string;
  topic: string;
  level: string;
  topic_hint?: string;
}

export interface SobesAnswer {
  score_percent: number;
  is_counted: boolean;
  techlead_explanation: string;
  covered_points: string[];
  missed_points: string[];
  next_question: SobesQuestion | null;
  is_last: boolean;
}

export interface SobesResults {
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
}

export type SobesView = "setup" | "question" | "answer" | "results";
