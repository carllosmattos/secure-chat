const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("secure_chat_token");
}

export function setToken(token: string) {
  localStorage.setItem("secure_chat_token", token);
}

async function apiFetch(path: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res;
}

export async function devLogin() {
  const res = await apiFetch("/api/auth/dev-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

export interface Session {
  id: string;
  title: string;
  mode: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: string;
  content: string;
  pii_redacted: boolean;
  blocked: boolean;
  attachment_names: string[];
  created_at: string;
}

export async function listSessions(): Promise<Session[]> {
  const res = await apiFetch("/api/sessions");
  return res.json();
}

export async function createSession(title = "New chat"): Promise<Session> {
  const res = await apiFetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return res.json();
}

export async function listMessages(sessionId: string): Promise<Message[]> {
  const res = await apiFetch(`/api/sessions/${sessionId}/messages`);
  return res.json();
}

export interface SendMessageResult {
  blocked?: boolean;
  reasons?: string[];
  findings_summary?: string[];
  stream?: boolean;
}

export async function sendMessage(
  sessionId: string,
  content: string,
  files: File[],
  onToken: (text: string) => void,
  onDone: (data: { content: string; pii_redacted: boolean }) => void,
  onError: (msg: string) => void
): Promise<SendMessageResult> {
  const token = getToken();
  const form = new FormData();
  form.append("content", content);
  for (const f of files) form.append("files", f);

  const res = await fetch(`${API_URL}/api/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  const contentType = res.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    const data = await res.json();
    if (data.blocked) return data;
    throw new Error(data.detail || "Unexpected response");
  }

  if (!res.ok || !res.body) {
    throw new Error("Failed to send message");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let eventType = "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        try {
          const data = JSON.parse(raw);
          if (eventType === "token" && data.text) onToken(data.text);
          if (eventType === "done") onDone(data);
          if (eventType === "error") onError(data.message);
        } catch {
          /* ignore parse errors */
        }
      }
    }
  }

  return { stream: true };
}
