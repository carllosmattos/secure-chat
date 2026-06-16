"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSession,
  deleteSession,
  devLogin,
  getToken,
  listMessages,
  listSessions,
  sendMessage,
  updateSession,
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
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeSessionIdRef = useRef<string | null>(null);

  const scrollToBottom = () => bottomRef.current?.scrollIntoView({ behavior: "smooth" });

  const resetChatView = useCallback(() => {
    setMessages([]);
    setStreaming("");
    setStatus(null);
    setBlockAlert(null);
    setInput("");
    setFiles([]);
  }, []);

  const loadSessions = useCallback(async (selectId?: string) => {
    const data = await listSessions();
    setSessions(data);
    if (selectId) {
      const found = data.find((s) => s.id === selectId);
      if (found) setActiveSession(found);
    } else if (data.length && !activeSessionIdRef.current) {
      setActiveSession(data[0]);
    }
  }, []);

  const loadMessages = useCallback(async (sessionId: string) => {
    const data = await listMessages(sessionId);
    if (activeSessionIdRef.current === sessionId) {
      setMessages(data);
    }
  }, []);

  useEffect(() => {
    activeSessionIdRef.current = activeSession?.id ?? null;
  }, [activeSession]);

  useEffect(() => {
    const init = async () => {
      if (!getToken()) await devLogin();
      setAuthenticated(true);
      await loadSessions();
    };
    init().catch(console.error);
  }, [loadSessions]);

  useEffect(() => {
    if (activeSession) {
      resetChatView();
      loadMessages(activeSession.id);
    }
  }, [activeSession?.id, loadMessages, resetChatView]);

  useEffect(scrollToBottom, [messages, streaming]);

  const handleSelectSession = (session: Session) => {
    if (session.id === activeSession?.id) return;
    setActiveSession(session);
  };

  const handleNewChat = async () => {
    const session = await createSession();
    setSessions((s) => [session, ...s]);
    setActiveSession(session);
  };

  const handleRename = async (sessionId: string) => {
    const title = editTitle.trim();
    if (!title) {
      setEditingSessionId(null);
      return;
    }
    const updated = await updateSession(sessionId, title);
    setSessions((s) => s.map((item) => (item.id === sessionId ? updated : item)));
    if (activeSession?.id === sessionId) setActiveSession(updated);
    setEditingSessionId(null);
  };

  const handleDelete = async (sessionId: string) => {
    if (!confirm("Excluir este chat?")) return;
    await deleteSession(sessionId);
    const remaining = sessions.filter((s) => s.id !== sessionId);
    setSessions(remaining);
    if (activeSession?.id === sessionId) {
      setActiveSession(remaining[0] ?? null);
      if (!remaining.length) resetChatView();
    }
  };

  const handleSend = async () => {
    if (!activeSession || !input.trim() || loading) return;
    const sessionId = activeSession.id;
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
        sessionId,
        text,
        attached,
        (token) => {
          if (activeSessionIdRef.current !== sessionId) return;
          accumulated += token;
          setStreaming(accumulated);
        },
        (data) => {
          if (activeSessionIdRef.current !== sessionId) return;
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
          if (data.session_title) {
            setSessions((s) =>
              s.map((item) =>
                item.id === sessionId ? { ...item, title: data.session_title! } : item
              )
            );
            setActiveSession((current) =>
              current?.id === sessionId ? { ...current, title: data.session_title! } : current
            );
          }
        },
        (err) => {
          if (activeSessionIdRef.current === sessionId) setStatus(`Erro: ${err}`);
        }
      );

      if (activeSessionIdRef.current !== sessionId) return;

      if (result.blocked && result.reasons) {
        setBlockAlert(result.reasons);
        setMessages((m) =>
          m.map((msg) => (msg.id === userMsg.id ? { ...msg, blocked: true } : msg))
        );
      }
    } catch (err) {
      if (activeSessionIdRef.current === sessionId) {
        setStatus(err instanceof Error ? err.message : "Erro ao enviar");
      }
    } finally {
      if (activeSessionIdRef.current === sessionId) setLoading(false);
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
            <div
              key={s.id}
              className={`${styles.sessionRow} ${activeSession?.id === s.id ? styles.active : ""}`}
            >
              {editingSessionId === s.id ? (
                <input
                  className={styles.sessionEditInput}
                  value={editTitle}
                  autoFocus
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={() => handleRename(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleRename(s.id);
                    if (e.key === "Escape") setEditingSessionId(null);
                  }}
                />
              ) : (
                <button
                  className={styles.sessionItem}
                  onClick={() => handleSelectSession(s)}
                  onDoubleClick={() => {
                    setEditingSessionId(s.id);
                    setEditTitle(s.title);
                  }}
                >
                  {s.title}
                </button>
              )}
              <div className={styles.sessionActions}>
                <button
                  type="button"
                  className={styles.sessionActionBtn}
                  title="Renomear"
                  onClick={() => {
                    setEditingSessionId(s.id);
                    setEditTitle(s.title);
                  }}
                >
                  ✎
                </button>
                <button
                  type="button"
                  className={styles.sessionActionBtn}
                  title="Excluir"
                  onClick={() => handleDelete(s.id)}
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </nav>
        <footer className={styles.sidebarFooter}>
          <span className={styles.badge}>PII redact ativo</span>
        </footer>
      </aside>

      <main className={styles.main}>
        {!activeSession ? (
          <div className={styles.emptyState}>
            <p>Nenhum chat selecionado.</p>
            <button className={styles.newChatBtn} onClick={handleNewChat}>
              Criar novo chat
            </button>
          </div>
        ) : (
          <>
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
                <button
                  className={styles.sendBtn}
                  onClick={handleSend}
                  disabled={loading || !input.trim()}
                >
                  {loading ? "..." : "Enviar"}
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
