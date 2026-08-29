import React from "react";
import styles from "./Spinner.module.css";

interface SpinnerProps {
  size?: "small" | "medium" | "large";
  className?: string;
}

export const Spinner: React.FC<SpinnerProps> = ({ size = "medium", className = "" }) => {
  return (
    <div className={`${styles.spinner} ${styles[size]} ${className}`}>
      <div className={styles.inner} />
    </div>
  );
};

export default Spinner;
