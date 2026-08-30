import React from "react";
import { Button } from "@/components/ui";

interface Props {
  onClick: () => void;
}

export const StatsButton: React.FC<Props> = ({ onClick }) => (
  <Button variant="secondary" onClick={onClick}>
    📊 Статистика ответов
  </Button>
);

export default StatsButton;
