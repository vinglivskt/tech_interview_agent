import React from "react";

type IconProps = { size?: number; className?: string };

const base = (size: number, className: string | undefined, children: React.ReactNode) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    {children}
  </svg>
);

export const IconHome: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
    </>
  ));

export const IconChat: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 1 1 16.1-3.8z" />
  ));

export const IconQuiz: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="m9 11.5 2 2 4-4" />
    </>
  ));

export const IconSobes: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <path d="M12 19v4" />
    </>
  ));

export const IconArch: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M21 8 12 3 3 8v8l9 5 9-5z" />
      <path d="M3 8l9 5 9-5" />
      <path d="M12 13v8" />
    </>
  ));

export const IconStats: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M18 20V10" />
      <path d="M12 20V4" />
      <path d="M6 20v-6" />
    </>
  ));

export const IconProgress: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M23 6l-9.5 9.5-5-5L1 18" />
      <path d="M17 6h6v6" />
    </>
  ));

export const IconQuestion: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </>
  ));

export const IconScenario: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M12 18v-6" />
      <path d="M9 15h6" />
    </>
  ));

export const IconArrowRight: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </>
  ));

export const IconArrowLeft: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M19 12H5" />
      <path d="m11 6-6 6 6 6" />
    </>
  ));

export const IconSave: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="m7 10 5 5 5-5" />
      <path d="M12 15V3" />
    </>
  ));

export const IconBulb: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.4 1 2.3h6c0-.9.4-1.8 1-2.3A7 7 0 0 0 12 2z" />
      <path d="M9 18h6" />
      <path d="M10 22h4" />
    </>
  ));

export const IconCheck: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m9 12 2 2 4-4" />
    </>
  ));

export const IconWarn: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="m10.3 3.7-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3.3l-8-14a2 2 0 0 0-3.4 0z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </>
  ));

export const IconError: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </>
  ));

export const IconTrash: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
    </>
  ));

export const IconTerminal: React.FC<IconProps> = ({ size = 18, className }) =>
  base(size, className, (
    <>
      <path d="m4 17 6-5-6-5" />
      <path d="M12 19h8" />
    </>
  ));