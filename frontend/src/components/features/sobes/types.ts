import type {
  SobesQuestion,
  SobesConfigResponse,
  SobesAnswerResponse,
  SobesResultsResponse,
} from '@/types';

export type SobesView = 'setup' | 'question' | 'answer' | 'results';

export interface SobesState {
  view: SobesView;
  config: SobesConfigResponse | null;
  level: 'junior' | 'middle' | 'senior';
  selectedTopics: string[];
  sessionId: string | null;
  currentQuestion: SobesQuestion | null;
  userAnswer: string;
  lastAnswer: SobesAnswerResponse | null;
  results: SobesResultsResponse | null;
  isLoading: boolean;
  error: string | null;
}

export interface SobesSetupViewProps {
  config: SobesConfigResponse | null;
  level: 'junior' | 'middle' | 'senior';
  selectedTopics: string[];
  onLevelChange: (level: 'junior' | 'middle' | 'senior') => void;
  onTopicToggle: (topicId: string) => void;
  onStart: () => void;
  onBack: () => void;
  isLoading: boolean;
  error: string | null;
}

export interface SobesQuestionViewProps {
  question: SobesQuestion;
  userAnswer: string;
  onAnswerChange: (answer: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
  onRepeat: () => void;
  onBack: () => void;
  isLoading: boolean;
  questionNumber: number;
  totalPlanned: number;
}

export interface SobesAnswerViewProps {
  question: SobesQuestion;
  userAnswer: string;
  answer: SobesAnswerResponse;
  onNext: () => void;
  onBack: () => void;
}

export interface SobesResultsViewProps {
  results: SobesResultsResponse;
  onRestart: () => void;
  onBack: () => void;
}
