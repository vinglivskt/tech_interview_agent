export interface DesignConfig {
  levels: string[];
  scenarios: { id: string; title: string; level: string }[];
  hint_penalty_percent: number;
}

export interface DesignStep {
  id: string;
  title: string;
  prompt: string;
}

export interface DesignScenario {
  id: string;
  title: string;
  level: string;
}

export interface DesignAnswer {
  score_percent: number;
  rubric: string[];
  covered_points: string[];
  missed_points: string[];
  techlead_explanation: string;
  next_step: DesignStep | null;
  is_last: boolean;
}

export interface DesignResults {
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
}

export type DesignView = "setup" | "question" | "answer" | "results";
