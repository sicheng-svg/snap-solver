import { useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css"; // KaTeX 样式(必须 import,否则公式没样式)

const GATEWAY = "http://localhost:8080";

interface Thinking {
  stage: string;
  content: string;
}

// LLM 常用 \(...\) 和 \[...\] 作公式分隔符,但 remark-math 默认认 $...$ 和 $$...$$。
// 这里把前者转成后者,保证公式能被识别渲染。
function normalizeMath(text: string): string {
  return text
    .replace(/\\\[/g, "$$$$") // \[ -> $$
    .replace(/\\\]/g, "$$$$") // \] -> $$
    .replace(/\\\(/g, "$")    // \( -> $
    .replace(/\\\)/g, "$");   // \) -> $
}

function App() {
  const [input, setInput] = useState("");
  const [thinkings, setThinkings] = useState<Thinking[]>([]);
  const [answer, setAnswer] = useState("");
  const [solving, setSolving] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const handleSend = () => {
    const text = input.trim();
    if (!text || solving) return;

    setThinkings([]);
    setAnswer("");
    setSolving(true);

    const url = `${GATEWAY}/api/solve?text=${encodeURIComponent(text)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (event) => {
      const chunk = JSON.parse(event.data) as {
        type: string;
        stage: string;
        content: string;
      };

      if (chunk.type === "thinking") {
        setThinkings((prev) => [...prev, { stage: chunk.stage, content: chunk.content }]);
      } else if (chunk.type === "token") {
        setAnswer((prev) => prev + chunk.content);
      } else if (chunk.type === "done") {
        es.close();
        setSolving(false);
      } else if (chunk.type === "error") {
        setAnswer((prev) => prev + `\n[错误] ${chunk.content}`);
        es.close();
        setSolving(false);
      }
    };

    es.onerror = () => {
      es.close();
      setSolving(false);
    };
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: 20, fontFamily: "sans-serif" }}>
      <h1>snap-solver 拍照搜题</h1>

      {/* 思考过程区 */}
      {thinkings.length > 0 && (
        <div style={{ background: "#f5f5f5", padding: 12, borderRadius: 8, marginBottom: 16 }}>
          <div style={{ fontWeight: "bold", marginBottom: 8, color: "#666" }}>思考过程</div>
          {thinkings.map((t, i) => (
            <div key={i} style={{ fontSize: 14, color: "#666", marginBottom: 4 }}>
              [{t.stage}] {t.content}
            </div>
          ))}
        </div>
      )}

      {/* 回答区:渲染 markdown + 公式 */}
      {answer && (
        <div
          className="answer"
          style={{ background: "#fff", padding: "12px 20px", border: "1px solid #eee", borderRadius: 8, marginBottom: 16, lineHeight: 1.7 }}
        >
          <ReactMarkdown
            remarkPlugins={[remarkMath]}
            rehypePlugins={[rehypeKatex]}
          >
            {normalizeMath(answer)}
          </ReactMarkdown>
        </div>
      )}

      {/* 输入区 */}
      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入题目,如:求 lim(x->0) sinx/x 的值"
          disabled={solving}
          style={{ flex: 1, padding: 10, fontSize: 16, borderRadius: 8, border: "1px solid #ccc" }}
        />
        <button
          onClick={handleSend}
          disabled={solving}
          style={{ padding: "10px 20px", fontSize: 16, borderRadius: 8, border: "none", background: solving ? "#ccc" : "#185FA5", color: "#fff", cursor: solving ? "default" : "pointer" }}
        >
          {solving ? "解题中…" : "发送"}
        </button>
      </div>
    </div>
  );
}

export default App;
