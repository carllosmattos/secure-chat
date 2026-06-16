"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSession,
  devLogin,
  getToken,
  listMessages,
  listSessions,
  sendMessage,
  type Message,
  type Session,
} from "@/lib/api";
import styles from "./page.module.css";

export default function ChatPage() {
  const [authenticated, setAuthenticated] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [blockAlert, setBlockAlert] = useState<string[] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => bottomRef.current?.scrollIntoView({ behavior: "smooth" });

  const loadSessions = useCallback(async () => {
    const data = await listSessions();
    setSessions(data);
    if (data.length && !activeSession) setActiveSession(data[0]);
  }, [activeSession]);

  const loadMessages = useCallback(async (sessionId: string) => {
    const data = await listMessages(sessionId);
    setMessages(data);
  }, []);

  useEffect(() => {
    const init = async () => {
      if (!getToken()) await devLogin();
      setAuthenticated(true);
      await loadSessions();
    };
    init().catch(console.error);
  }, [loadSessions]);

  useEffect(() => {
    if (activeSession) loadMessages(activeSession.id);
  }, [activeSession, loadMessages]);

  useEffect(scrollToBottom, [messages, streaming]);

  const handleNewChat = async () => {
    const session = await createSession();
    setSessions((s) => [session, ...s]);
    setActiveSession(session);
    setMessages([]);
    setBlockAlert(null);
  };

  const handleSend = async () => {
    if (!activeSession || !input.trim() || loading) return;
    setLoading(true);
    setBlockAlert(null);
    setStatus(null);
    setStreaming("");

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input,
      pii_redacted: false,
      blocked: false,
      attachment_names: files.map((f) => f.name),
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    const text = input;
    const attached = [...files];
    setInput("");
    setFiles([]);

    try {
      let accumulated = "";
      const result = await sendMessage(
        activeSession.id,
        text,
        attached,
        (token) => {
          accumulated += token;
          setStreaming(accumulated);
        },
        (data) => {
          setMessages((m) => [
            ...m,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: data.content,
              pii_redacted: data.pii_redacted,
              blocked: false,
              attachment_names: [],
              created_at: new Date().toISOString(),
            },
          ]);
          if (data.pii_redacted) setStatus("PII foi redigido antes do envio ao LLM");
          setStreaming("");
        },
        (err) => setStatus(`Erro: ${err}`)
      );

      if (result.blocked && result.reasons) {
        setBlockAlert(result.reasons);
        setMessages((m) =>
          m.map((msg) => (msg.id === userMsg.id ? { ...msg, blocked: true } : msg))
        );
      }
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Erro ao enviar");
    } finally {
      setLoading(false);
    }
  };

  if (!authenticated) {
    return <div className={styles.loading}>Conectando...</div>;
  }

  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h1>Secure Chat</h1>
          <button className={styles.newChatBtn} onClick={handleNewChat}>
            + Novo chat
          </button>
        </div>
        <nav className={styles.sessionList}>
          {sessions.map((s) => (
            <button
              key={s.id}
              className={`${styles.sessionItem} ${activeSession?.id === s.id ? styles.active : ""}`}
              onClick={() => setActiveSession(s)}
            >
              {s.title}
            </button>
          ))}
        </nav>
        <footer className={styles.sidebarFooter}>
          <span className={styles.badge}>PII redact ativo</span>
        </footer>
      </aside>

      <main className={styles.main}>
        {blockAlert && (
          <div className={styles.blockAlert}>
            <strong>Credencial bloqueada</strong>
            <ul>
              {blockAlert.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {status && <div className={styles.statusBanner}>{status}</div>}

        <div className={styles.messages}>
          {messages.map((m) => (
            <div
              key={m.id}
              className={`${styles.message} ${m.role === "user" ? styles.user : styles.assistant}`}
            >
              <div className={styles.messageMeta}>
                {m.role === "user" ? "Você" : "Assistente"}
                {m.pii_redacted && <span className={styles.piiBadge}>PII redigido</span>}
                {m.blocked && <span className={styles.blockBadge}>Bloqueado</span>}
              </div>
              <div className={styles.messageContent}>{m.content}</div>
              {m.attachment_names.length > 0 && (
                <div className={styles.attachments}>
                  {m.attachment_names.map((n) => (
                    <span key={n} className={styles.attachmentChip}>
                      📎 {n}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {streaming && (
            <div className={`${styles.message} ${styles.assistant}`}>
              <div className={styles.messageMeta}>Assistente</div>
              <div className={styles.messageContent}>{streaming}</div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className={styles.composer}>
          {files.length > 0 && (
            <div className={styles.fileList}>
              {files.map((f) => (
                <span key={f.name} className={styles.attachmentChip}>
                  📎 {f.name}
                  <button
                    type="button"
                    onClick={() => setFiles((fs) => fs.filter((x) => x.name !== f.name))}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className={styles.composerRow}>
            <label className={styles.attachBtn}>
              📎
              <input
                type="file"
                multiple
                hidden
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
              />
            </label>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Digite sua mensagem..."
              rows={2}
              disabled={loading}
            />
            <button className={styles.sendBtn} onClick={handleSend} disabled={loading || !input.trim()}>
              {loading ? "..." : "Enviar"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
