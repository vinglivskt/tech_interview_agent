import React from "react";
import styles from "./Button.module.css";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "success" | "danger";
  loading?: boolean;
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = "primary",
  loading = false,
  children,
  disabled,
  className = "",
  ...props
}) => {
  const variantClass = variant !== "primary" ? styles[variant] : "";
  return (
    <button className={`${styles.button} ${variantClass} ${className}`} disabled={disabled || loading} {...props}>
      {loading && <span className={styles.spinner} />}
      {children}
    </button>
  );
};

export default Button;
