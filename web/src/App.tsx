import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

const GATEWAY = "http://localhost:8080";

interface Thinking {
  stage: string;
  content: string;
}

interface Message {
  id: number;
  question: string;
  imagePreview?: string;   // 用户上传图片的预览(data-uri,显示在问题气泡里)
  thinkings: Thinking[];
  answer: string;
  done: boolean;
  expanded: boolean;
}

function normalizeMath(text: string): string {
  return text
    .replace(/\\\[/g, "$$$$")
    .replace(/\\\]/g, "$$$$")
    .replace(/\\\(/g, "$")
    .replace(/\\\)/g, "$");
}

let nextId = 1;

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [solving, setSolving] = useState(false);
  // 待发送的图片:dataUri 用于预览,base64 用于上传(纯 base64,不带前缀)
  const [pendingImage, setPendingImage] = useState<{ dataUri: string; base64: string } | null>(null);

  const fileRef = useRef<HTMLInputElement | null>(null);   // 隐藏的文件选择框
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const updateLast = (updater: (m: Message) => Message) => {
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const copy = [...prev];
      copy[copy.length - 1] = updater(copy[copy.length - 1]);
      return copy;
    });
  };

  // 选择图片:读成 dataUri(预览)+ 纯 base64(上传)
  const handlePickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const dataUri = reader.result as string;            // data:image/png;base64,xxxx
      const base64 = dataUri.split(",")[1] ?? "";          // 去掉前缀,纯 base64
      setPendingImage({ dataUri, base64 });
    };
    reader.readAsDataURL(file);
    e.target.value = "";   // 允许再次选同一文件
  };

  // 发送:POST + fetch 读流(支持带图;EventSource 只能 GET 所以换 fetch)
  const handleSend = async () => {
    const text = input.trim();
    if ((!text && !pendingImage) || solving) return;

    const msg: Message = {
      id: nextId++,
      question: text || "(图片题目)",
      imagePreview: pendingImage?.dataUri,
      thinkings: [],
      answer: "",
      done: false,
      expanded: true,
    };
    setMessages((prev) => [...prev, msg]);
    const imageBase64 = pendingImage?.base64 ?? "";
    setInput("");
    setPendingImage(null);
    setSolving(true);

    try {
      const resp = await fetch(`${GATEWAY}/api/solve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, image: imageBase64 }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      // 手动读流并按 SSE 格式解析(data: {...}\n\n)
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE 事件以空行分隔;可能一次到达多个事件,也可能半个,用 buffer 累积
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";   // 最后一段可能不完整,留到下次
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data: ")) continue;
          const chunk = JSON.parse(line.slice(6)) as {
            type: string; stage: string; content: string;
          };
          handleChunk(chunk);
        }
      }
    } catch (err) {
      updateLast((m) => ({ ...m, answer: m.answer + `\n\n[错误] ${String(err)}`, done: true }));
    } finally {
      setSolving(false);
    }
  };

  const handleChunk = (chunk: { type: string; stage: string; content: string }) => {
    if (chunk.type === "thinking") {
      updateLast((m) => ({
        ...m,
        thinkings: [...m.thinkings, { stage: chunk.stage, content: chunk.content }],
      }));
    } else if (chunk.type === "token") {
      updateLast((m) => ({ ...m, answer: m.answer + chunk.content }));
    } else if (chunk.type === "done") {
      updateLast((m) => ({ ...m, done: true, expanded: false }));
    } else if (chunk.type === "error") {
      updateLast((m) => ({ ...m, answer: m.answer + `\n\n[错误] ${chunk.content}`, done: true }));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleExpand = (id: number) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, expanded: !m.expanded } : m))
    );
  };

  const jumpTo = (id: number) => {
    document.getElementById(`msg-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="app">
      <header className="topbar">snap-solver · 拍照搜题</header>

      <div className="body">
        <main className="chat">
          {messages.length === 0 && <div className="empty">输入一道题,或上传题目照片,开始解题</div>}

          {messages.map((m) => (
            <div key={m.id} id={`msg-${m.id}`} className="round">
              <div className="user-row">
                <div className="user-bubble">
                  {m.imagePreview && <img src={m.imagePreview} className="user-image" alt="题目图片" />}
                  {m.question}
                </div>
              </div>

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

        {messages.length > 0 && (
          <nav className="sidenav">
            {messages.map((m) => (
              <div key={m.id} className="nav-node" title={m.question} onClick={() => jumpTo(m.id)}>
                <span className="nav-dot" />
                <span className="nav-label">{m.question}</span>
              </div>
            ))}
          </nav>
        )}
      </div>

      {/* 底部:Claude 风格输入框 */}
      <footer className="inputarea">
        <div className="inputbox">
          {/* 已选图片缩略图(可移除) */}
          {pendingImage && (
            <div className="image-preview">
              <img src={pendingImage.dataUri} alt="待发送图片" />
              <button className="image-remove" onClick={() => setPendingImage(null)}>×</button>
            </div>
          )}

          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入题目,或点击 + 上传题目照片…"
            disabled={solving}
            rows={1}
          />

          <div className="inputbox-bottom">
            {/* 左下:+ 添加图片 */}
            <button className="plus-btn" onClick={() => fileRef.current?.click()} disabled={solving} title="添加图片">
              +
            </button>
            <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={handlePickImage} />

            {/* 右下:发送 */}
            <button className="send-btn" onClick={handleSend} disabled={solving || (!input.trim() && !pendingImage)}>
              {solving ? "解题中…" : "发送"}
            </button>
          </div>
        </div>
        <div className="disclaimer">snap-solver 由 AI 驱动,可能会出错,请核对关键步骤。</div>
      </footer>
    </div>
  );
}

export default App;
