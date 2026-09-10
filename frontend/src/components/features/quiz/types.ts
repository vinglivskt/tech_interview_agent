export interface QuizViewProps {
  level: "junior" | "middle" | "senior";
  onLevelChange: (level: "junior" | "middle" | "senior") => void;
  onStart: () => void;
  isLoading: boolean;
  error?: string | null;
  onBack?: () => void;
  onShowStats?: React.ReactNode;
}
