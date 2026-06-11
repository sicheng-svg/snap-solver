// src/api.ts —— 后端请求封装:token 管理 + 统一鉴权 + 各 API。
// 所有组件都通过这里和后端打交道,不直接写 fetch(类比后端的 client 层)。

export const GATEWAY = "http://localhost:8080";

// ---- token 管理(localStorage)----
export function getToken(): string | null {
  return localStorage.getItem("token");
}
export function setToken(t: string) {
  localStorage.setItem("token", t);
}
export function clearToken() {
  localStorage.removeItem("token");
}

// 401 时抛这个,App 捕获后登出回登录页
export class AuthError extends Error {}

// 统一封装:自动带 Bearer 头、401 抛 AuthError、解析 JSON 错误信息
async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(`${GATEWAY}${path}`, { ...init, headers });
  if (resp.status === 401) {
    clearToken();
    throw new AuthError("登录已失效");
  }
  return resp;
}

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error ?? `HTTP ${resp.status}`);
  return data as T;
}

// ---- 类型(对齐后端返回)----
export interface Session {
  id: number;
  title: string;
  updated_at: string;
}
export interface DbMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  image_path: string | null;
  thinking_json: string | null;
}

// ---- 认证 ----
export async function register(username: string, password: string): Promise<string> {
  const resp = await fetch(`${GATEWAY}/api/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await jsonOrThrow<{ token: string }>(resp);
  return data.token;
}
export async function login(username: string, password: string): Promise<string> {
  const resp = await fetch(`${GATEWAY}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await jsonOrThrow<{ token: string }>(resp);
  return data.token;
}

// ---- 会话 ----
export async function listSessions(): Promise<Session[]> {
  return jsonOrThrow(await authFetch("/api/sessions"));
}
export async function createSession(): Promise<Session> {
  return jsonOrThrow(await authFetch("/api/sessions", { method: "POST" }));
}
export async function deleteSession(id: number): Promise<void> {
  await jsonOrThrow(await authFetch(`/api/sessions/${id}`, { method: "DELETE" }));
}
export async function listMessages(sessionId: number): Promise<DbMessage[]> {
  return jsonOrThrow(await authFetch(`/api/sessions/${sessionId}/messages`));
}

// ---- 解题(流式):POST + 手动读流,带鉴权头 ----
export async function solveStream(
  text: string,
  imageBase64: string,
  sessionId: number,
  onChunk: (c: { type: string; stage: string; content: string }) => void,
): Promise<void> {
  const resp = await authFetch("/api/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, image: imageBase64, session_id: sessionId }),
  });
  if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      onChunk(JSON.parse(line.slice(6)));
    }
  }
}