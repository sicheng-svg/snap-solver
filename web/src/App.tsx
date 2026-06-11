// src/App.tsx —— 主界面:左侧会话列表 | 中间对话流 | 右侧消息导航。
// 未登录显示 Login;登录后加载会话列表;切换会话加载历史;解题带真实 session_id。
import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import Login from "./Login";
import * as api from "./api";

interface Thinking { stage: string; content: string; }
interface Message {
  id: number;
  question: string;
  imagePreview?: string;
  thinkings: Thinking[];
  answer: string;
  done: boolean;
  expanded: boolean;
}

function normalizeMath(text: string): string {
  return text
    .replace(/\\\[/g, "$$$$").replace(/\\\]/g, "$$$$")
    .replace(/\\\(/g, "$").replace(/\\\)/g, "$");
}

// 历史行(user/assistant 独立行)配对成 UI 轮次(一问一答一组)
function rowsToMessages(rows: api.DbMessage[]): Message[] {
  const out: Message[] = [];
  for (const r of rows) {
    if (r.role === "user") {
      out.push({ id: r.id, question: r.content, thinkings: [], answer: "", done: true, expanded: false });
    } else {
      let th: Thinking[] = [];
      if (r.thinking_json) {
        try {
          th = (JSON.parse(r.thinking_json) as { stage: string; content: string }[])
            .map((t) => ({ stage: t.stage, content: t.content }));
        } catch { /* 解析失败就不显示思考 */ }
      }
      const last = out[out.length - 1];
      if (last && last.answer === "") { last.answer = r.content; last.thinkings = th; }
      else out.push({ id: r.id, question: "", thinkings: th, answer: r.content, done: true, expanded: false });
    }
  }
  return out;
}

let nextLocalId = 1_000_000; // 本地新消息的临时 id,避开历史 id

export default function App() {
  const [token, setTokenState] = useState<string | null>(api.getToken());
  const [username, setUsername] = useState<string>(localStorage.getItem("username") ?? "用户");
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [sessions, setSessions] = useState<api.Session[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [solving, setSolving] = useState(false);
  const [pendingImage, setPendingImage] = useState<{ dataUri: string; base64: string } | null>(null);

  const fileRef = useRef<HTMLInputElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const logout = useCallback(() => {
    api.clearToken();
    localStorage.removeItem("username");
    setTokenState(null);
    setUserMenuOpen(false);
    setSessions([]); setCurrentId(null); setMessages([]);
  }, []);

  // 统一错误处理:401 → 登出
  const guard = useCallback(async <T,>(p: Promise<T>): Promise<T | null> => {
    try { return await p; }
    catch (e) {
      if (e instanceof api.AuthError) { logout(); return null; }
      throw e;
    }
  }, [logout]);

  // 登录后加载会话列表
  useEffect(() => {
    if (!token) return;
    guard(api.listSessions()).then((list) => { if (list) setSessions(list); });
  }, [token, guard]);

  // 切换会话:加载历史
  const switchSession = async (id: number) => {
    if (solving) return;
    setCurrentId(id);
    const rows = await guard(api.listMessages(id));
    if (rows) setMessages(rowsToMessages(rows));
  };

  const newSession = async () => {
    if (solving) return;
    const s = await guard(api.createSession());
    if (!s) return;
    setSessions((prev) => [s, ...prev]);
    setCurrentId(s.id);
    setMessages([]);
  };

  const removeSession = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation(); // 别触发切换
    if (solving) return;
    const ok = await guard(api.deleteSession(id).then(() => true));
    if (!ok) return;
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (currentId === id) { setCurrentId(null); setMessages([]); }
  };

  const updateLast = (updater: (m: Message) => Message) => {
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const copy = [...prev];
      copy[copy.length - 1] = updater(copy[copy.length - 1]);
      return copy;
    });
  };

  const handlePickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const dataUri = reader.result as string;
      setPendingImage({ dataUri, base64: dataUri.split(",")[1] ?? "" });
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const handleSend = async () => {
    const text = input.trim();
    if ((!text && !pendingImage) || solving) return;

    // 没选会话就先自动建一个
    let sid = currentId;
    if (sid === null) {
      const s = await guard(api.createSession());
      if (!s) return;
      setSessions((prev) => [s, ...prev]);
      setCurrentId(s.id);
      sid = s.id;
    }

    setMessages((prev) => [...prev, {
      id: nextLocalId++,
      question: text || "(图片题目)",
      imagePreview: pendingImage?.dataUri,
      thinkings: [], answer: "", done: false, expanded: true,
    }]);
    const imageBase64 = pendingImage?.base64 ?? "";
    setInput(""); setPendingImage(null); setSolving(true);

    try {
      await api.solveStream(text, imageBase64, sid, (chunk) => {
        if (chunk.type === "thinking") {
          updateLast((m) => ({ ...m, thinkings: [...m.thinkings, { stage: chunk.stage, content: chunk.content }] }));
        } else if (chunk.type === "token") {
          updateLast((m) => ({ ...m, answer: m.answer + chunk.content }));
        } else if (chunk.type === "done") {
          updateLast((m) => ({ ...m, done: true, expanded: false }));
        } else if (chunk.type === "error") {
          updateLast((m) => ({ ...m, answer: m.answer + `\n\n[错误] ${chunk.content}`, done: true }));
        }
      });
      // 首问可能改了标题:刷新会话列表
      const list = await guard(api.listSessions());
      if (list) setSessions(list);
    } catch (e) {
      if (e instanceof api.AuthError) { logout(); return; }
      updateLast((m) => ({ ...m, answer: m.answer + `\n\n[错误] ${String(e)}`, done: true }));
    } finally {
      setSolving(false);
    }
  };

  const toggleExpand = (id: number) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, expanded: !m.expanded } : m)));
  };
  const jumpTo = (id: number) => {
    document.getElementById(`msg-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // 未登录 → 登录页
  if (!token) {
    return <Login onLogin={(t, name) => {
      api.setToken(t);
      localStorage.setItem("username", name);
      setUsername(name);
      setTokenState(t);
    }} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <span>snap-solver · 拍照搜题</span>
      </header>

      <div className="body">
        {/* 左侧:会话列表(通到底) */}
        <aside className="sidebar">
          <button className="new-session" onClick={newSession}>+ 新建会话</button>
          <div className="session-list">
            {sessions.map((s) => (
              <div key={s.id}
                   className={`session-item ${s.id === currentId ? "active" : ""}`}
                   onClick={() => switchSession(s.id)} title={s.title}>
                <span className="session-title">{s.title}</span>
                <span className="session-del" onClick={(e) => removeSession(s.id, e)}>×</span>
              </div>
            ))}
          </div>
          <div className="user-area" onClick={() => setUserMenuOpen((v) => !v)}>
            {userMenuOpen && (
              <div className="user-menu" onClick={(e) => { e.stopPropagation(); logout(); }}>
                退出登录
              </div>
            )}
            <span className="avatar">{username.slice(0, 1).toUpperCase()}</span>
            <span className="user-name">{username}</span>
          </div>
        </aside>

        {/* 中间列:对话区 + 输入框 */}
        <div className="chat-col">
        <main className="chat">
          {messages.length === 0 && (
            <div className="empty">{currentId === null ? "新建或选择一个会话,开始解题" : "这个会话还没有消息"}</div>
          )}
          {messages.map((m) => (
            <div key={m.id} id={`msg-${m.id}`} className="round">
              {m.question && (
                <div className="user-row">
                  <div className="user-bubble">
                    {m.imagePreview && <img src={m.imagePreview} className="user-image" alt="题目图片" />}
                    {m.question}
                  </div>
                </div>
              )}
              {m.thinkings.length > 0 && (
                <div className="thinking-box">
                  <div className="thinking-head" onClick={() => toggleExpand(m.id)}>
                    <span>{m.done ? "思考过程" : "思考中…"}</span>
                    <span className="thinking-toggle">{m.expanded ? "收起 ▲" : "展开 ▼"}</span>
                  </div>
                  {m.expanded && (
                    <div className="thinking-list">
                      {m.thinkings.map((t, i) => (
                        <div key={i} className="thinking-item">
                          <span className="thinking-stage">{t.stage}</span> {t.content}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {m.answer && (
                <div className="answer">
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                    {normalizeMath(m.answer)}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </main>
        {/* 底部输入 */}
        <footer className="inputarea">
          <div className="inputbox">
            {pendingImage && (
              <div className="image-preview">
                <img src={pendingImage.dataUri} alt="待发送图片" />
                <button className="image-remove" onClick={() => setPendingImage(null)}>×</button>
              </div>
            )}
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="输入题目,或点击 + 上传题目照片…"
              disabled={solving}
              rows={1}
            />
            <div className="inputbox-bottom">
              <button className="plus-btn" onClick={() => fileRef.current?.click()} disabled={solving} title="添加图片">+</button>
              <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={handlePickImage} />
              <button className="send-btn" onClick={handleSend} disabled={solving || (!input.trim() && !pendingImage)}>
                {solving ? "解题中…" : "发送"}
              </button>
            </div>
          </div>
          <div className="disclaimer">snap-solver 由 AI 驱动,可能会出错,请核对关键步骤。</div>
        </footer>
        </div>

        {/* 右侧:消息导航 */}
        {messages.length > 0 && (
          <nav className="sidenav">
            {messages.filter((m) => m.question).map((m) => (
              <div key={m.id} className="nav-node" title={m.question} onClick={() => jumpTo(m.id)}>
                <span className="nav-dot" />
                <span className="nav-label">{m.question}</span>
              </div>
            ))}
          </nav>
        )}
      </div>

    </div>
  );
}