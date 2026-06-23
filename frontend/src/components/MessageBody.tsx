"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./MessageBody.module.css";

type Props = {
  content: string;
  markdown?: boolean;
};

export function MessageBody({ content, markdown = false }: Props) {
  if (!markdown) {
    return <div className={styles.plain}>{content}</div>;
  }

  return (
    <div className={styles.markdown}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
