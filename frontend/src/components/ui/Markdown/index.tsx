import React from 'react';
import ReactMarkdown from 'react-markdown';
import styles from './Markdown.module.scss';

interface MarkdownProps {
  content: string;
  className?: string;
}

export const Markdown: React.FC<MarkdownProps> = ({ content, className = '' }) => {
  return (
    <div className={`${styles.markdown} ${className}`}>
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
};

export default Markdown;
