import React from "react";
import { Button } from "@/components/ui";
import { IconStats } from "@/components/ui/icons";

interface Props {
  onClick: () => void;
}

export const StatsButton: React.FC<Props> = ({ onClick }) => (
  <Button variant="secondary" onClick={onClick}>
    <IconStats size={16} /> Статистика ответов
  </Button>
);

export default StatsButton;
