import type {
  DesignConfigResponse,
  DesignStep,
  DesignScenarioInfo,
  DesignAnswerResponse,
  DesignResultsResponse,
} from '@/types';

export type DesignView = 'setup' | 'question' | 'answer' | 'results';

export interface DesignState {
  view: DesignView;
  config: DesignConfigResponse | null;
  level: string;
  selectedScenarioId: string | null;
  sessionId: string | null;
  scenario: DesignScenarioInfo | null;
  currentStep: DesignStep | null;
  stepIndex: number;
  totalSteps: number;
  userAnswer: string;
  lastAnswer: DesignAnswerResponse | null;
  hint: string | null;
  results: DesignResultsResponse | null;
  isLoading: boolean;
  error: string | null;
}

export interface DesignSetupViewProps {
  config: DesignConfigResponse | null;
  level: string;
  selectedScenarioId: string | null;
  onLevelChange: (level: string) => void;
  onScenarioSelect: (scenarioId: string) => void;
  onStart: () => void;
  onBack: () => void;
  isLoading: boolean;
  error: string | null;
}

export interface DesignQuestionViewProps {
  scenario: DesignScenarioInfo;
  step: DesignStep;
  stepIndex: number;
  totalSteps: number;
  userAnswer: string;
  hint: string | null;
  onAnswerChange: (answer: string) => void;
  onSubmit: () => void;
  onGetHint: () => void;
  onBack: () => void;
  isLoading: boolean;
}

export interface DesignAnswerViewProps {
  scenario: DesignScenarioInfo;
  step: DesignStep;
  stepIndex: number;
  totalSteps: number;
  userAnswer: string;
  answer: DesignAnswerResponse;
  onNext: () => void;
  onBack: () => void;
}

export interface DesignResultsViewProps {
  results: DesignResultsResponse;
  onRestart: () => void;
  onBack: () => void;
}
