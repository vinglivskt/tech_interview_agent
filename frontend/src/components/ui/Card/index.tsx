import React from "react";
import styles from "./Card.module.css";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  hoverable?: boolean;
}

export const Card: React.FC<CardProps> = ({ children, className = "", onClick, hoverable = false }) => {
  if (onClick) {
    return (
      <div
        className={`${styles.card} ${styles.interactive} ${hoverable ? styles.hoverable : ""} ${className}`}
        onClick={onClick}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onClick();
          }
        }}
        role="button"
        tabIndex={0}
      >
        {children}
      </div>
    );
  }
  return (
    <div className={`${styles.card} ${hoverable ? styles.hoverable : ""} ${className}`}>
      {children}
    </div>
  );
};

export default Card;
