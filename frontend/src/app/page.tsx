"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  MODEL_AUTO,
  createSession,
  deleteSession,
  devLogin,
  getToken,
  listMessages,
  listProviders,
  listSessions,
  sendMessage,
  shortModelLabel,
  sortSessions,
  updateSession,
  type Message,
  type Session,
} from "@/lib/api";
import { MessageBody } from "@/components/MessageBody";
import styles from "./page.module.css";

function appendAssistantMessage(
  messages: Message[],
  data: { message_id?: string; content: string; pii_redacted: boolean; is_error?: boolean }
): Message[] {
  return [
    ...messages,
    {
      id: data.message_id || crypto.randomUUID(),
      role: "assistant",
      content: data.content,
      pii_redacted: data.pii_redacted,
      blocked: false,
      is_error: data.is_error,
      attachment_names: [],
      created_at: new Date().toISOString(),
    },
  ];
}

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
  const [models, setModels] = useState<string[]>([]);
  const [modelStrategy, setModelStrategy] = useState<string>("manual");
  const [modelChoice, setModelChoice] = useState<string>(MODEL_AUTO);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => bottomRef.current?.scrollIntoView({ behavior: "smooth" });

  const balancingEnabled = modelStrategy !== "manual" && models.length > 1;

  const applySessionUpdate = useCallback((updated: Session) => {
    setSessions((prev) => sortSessions(prev.map((s) => (s.id === updated.id ? updated : s))));
    setActiveSession((prev) => (prev?.id === updated.id ? updated : prev));
  }, []);

  const loadSessions = useCallback(async () => {
    const data = sortSessions(await listSessions());
    setSessions(data);
    setActiveSession((prev) => {
      if (prev) return data.find((s) => s.id === prev.id) ?? data[0] ?? null;
      return data[0] ?? null;
    });
  }, []);

  const loadMessages = useCallback(async (sessionId: string) => {
    const data = await listMessages(sessionId);
    setMessages(data);
  }, []);

  useEffect(() => {
    const init = async () => {
      if (!getToken()) await devLogin();
      setAuthenticated(true);
      await loadSessions();
      try {
        const info = await listProviders();
        const available = info.models?.length ? info.models : [];
        setModels(available);
        const strategy = info.strategy || "manual";
        setModelStrategy(strategy);
        if (strategy !== "manual" && available.length > 1) {
          setModelChoice(MODEL_AUTO);
        } else if (available.length > 0) {
          const preferred =
            info.default_model && available.includes(info.default_model)
              ? info.default_model
              : available[0];
          setModelChoice(preferred);
        }
      } catch {
        /* providers list is best-effort */
      }
    };
    init().catch(console.error);
  }, [loadSessions]);

  useEffect(() => {
    if (activeSession) loadMessages(activeSession.id);
  }, [activeSession, loadMessages]);

  useEffect(scrollToBottom, [messages, streaming]);

  const handleNewChat = async () => {
    const session = await createSession();
    setSessions((s) => sortSessions([session, ...s]));
    setActiveSession(session);
    setMessages([]);
    setBlockAlert(null);
    setStatus(null);
  };

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Excluir este chat?")) return;
    await deleteSession(sessionId);
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== sessionId);
      if (activeSession?.id === sessionId) {
        setActiveSession(next[0] ?? null);
        setMessages([]);
      }
      return next;
    });
  };

  const handleTogglePin = async (session: Session, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = await updateSession(session.id, { pinned: !session.pinned });
    applySessionUpdate(updated);
  };

  const startRename = (session: Session, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingSessionId(session.id);
    setEditingTitle(session.title);
  };

  const commitRename = async (sessionId: string) => {
    const title = editingTitle.trim();
    setEditingSessionId(null);
    if (!title) return;
    const updated = await updateSession(sessionId, { title });
    applySessionUpdate(updated);
  };

  const handleSessionTitleFromStream = (title?: string) => {
    if (!title || !activeSession) return;
    const updated = { ...activeSession, title, updated_at: new Date().toISOString() };
    applySessionUpdate(updated);
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

    const selectedModel =
      modelChoice === MODEL_AUTO || !modelChoice ? undefined : modelChoice;

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
          setMessages((m) => appendAssistantMessage(m, data));
          if (data.pii_redacted) setStatus("PII foi redigido antes do envio ao LLM");
          handleSessionTitleFromStream(data.title);
          setStreaming("");
          loadSessions().catch(console.error);
        },
        (err) => {
          setMessages((m) =>
            appendAssistantMessage(m, {
              content: err,
              pii_redacted: false,
              is_error: true,
            })
          );
          setStreaming("");
        },
        undefined,
        selectedModel
      );

      if (result.blocked && result.reasons) {
        setBlockAlert(result.reasons);
        setMessages((m) =>
          m.map((msg) => (msg.id === userMsg.id ? { ...msg, blocked: true } : msg))
        );
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Erro ao enviar";
      setMessages((m) =>
        appendAssistantMessage(m, { content: message, pii_redacted: false, is_error: true })
      );
    } finally {
      setLoading(false);
    }
  };

  if (!authenticated) {
    return <div className={styles.loading}>Conectando...</div>;
  }

  return (
    <div className={styles.layout}>
      <aside className={`${styles.sidebar} ${sidebarCollapsed ? styles.sidebarCollapsed : ""}`}>
        <div className={styles.sidebarHeader}>
          <div className={styles.sidebarTopRow}>
            {!sidebarCollapsed && <h1>Secure Chat</h1>}
            <button
              type="button"
              className={styles.collapseBtn}
              onClick={() => setSidebarCollapsed((c) => !c)}
              title={sidebarCollapsed ? "Expandir barra lateral" : "Recolher barra lateral"}
              aria-label={sidebarCollapsed ? "Expandir barra lateral" : "Recolher barra lateral"}
            >
              {sidebarCollapsed ? "»" : "«"}
            </button>
          </div>
          <button className={styles.newChatBtn} onClick={handleNewChat} title="Novo chat">
            {sidebarCollapsed ? "+" : "+ Novo chat"}
          </button>
          {!sidebarCollapsed && models.length > 0 && (
            <label className={styles.modelSelect}>
              <span>Modelo</span>
              <select value={modelChoice} onChange={(e) => setModelChoice(e.target.value)}>
                {balancingEnabled && <option value={MODEL_AUTO}>Automático</option>}
                {models.map((m) => (
                  <option key={m} value={m} title={m}>
                    {shortModelLabel(m)}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <nav className={styles.sessionList}>
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`${styles.sessionRow} ${activeSession?.id === s.id ? styles.active : ""}`}
            >
              {editingSessionId === s.id && !sidebarCollapsed ? (
                <input
                  className={styles.sessionRenameInput}
                  value={editingTitle}
                  autoFocus
                  onChange={(e) => setEditingTitle(e.target.value)}
                  onBlur={() => commitRename(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename(s.id);
                    if (e.key === "Escape") setEditingSessionId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <button
                  type="button"
                  className={styles.sessionItem}
                  onClick={() => setActiveSession(s)}
                  title={s.title}
                >
                  {s.pinned && <span className={styles.pinIcon}>📌</span>}
                  <span className={styles.sessionTitle}>
                    {sidebarCollapsed ? s.title.charAt(0).toUpperCase() : s.title}
                  </span>
                </button>
              )}
              {!sidebarCollapsed && editingSessionId !== s.id && (
                <div className={styles.sessionActions}>
                  <button
                    type="button"
                    className={`${styles.sessionActionBtn} ${s.pinned ? styles.pinned : ""}`}
                    onClick={(e) => handleTogglePin(s, e)}
                    title={s.pinned ? "Desafixar" : "Fixar no topo"}
                  >
                    📌
                  </button>
                  <button
                    type="button"
                    className={styles.sessionActionBtn}
                    onClick={(e) => startRename(s, e)}
                    title="Renomear"
                  >
                    ✏️
                  </button>
                  <button
                    type="button"
                    className={styles.sessionActionBtn}
                    onClick={(e) => handleDeleteSession(s.id, e)}
                    title="Excluir"
                  >
                    🗑
                  </button>
                </div>
              )}
            </div>
          ))}
        </nav>
        {!sidebarCollapsed && (
          <footer className={styles.sidebarFooter}>
            <span className={styles.badge}>PII redact ativo</span>
          </footer>
        )}
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
              className={`${styles.message} ${m.role === "user" ? styles.user : styles.assistant} ${m.is_error ? styles.errorMessage : ""}`}
            >
              <div className={styles.messageMeta}>
                {m.role === "user" ? "Você" : m.is_error ? "Erro" : "Assistente"}
                {m.pii_redacted && <span className={styles.piiBadge}>PII redigido</span>}
                {m.blocked && <span className={styles.blockBadge}>Bloqueado</span>}
              </div>
              <div className={styles.messageContent}>
                <MessageBody content={m.content} markdown={m.role === "assistant" && !m.is_error} />
              </div>
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
              <div className={styles.messageContent}>
                <MessageBody content={streaming} markdown />
              </div>
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
