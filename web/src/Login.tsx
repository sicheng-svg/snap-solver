// src/Login.tsx —— 登录/注册页。成功后把 token 和 username 一起交给 App。
import { useState } from "react";
import { login, register } from "./api";

interface Props {
  onLogin: (token: string, username: string) => void;
}

export default function Login({ onLogin }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const name = username.trim();
    if (!name || !password) return;
    setBusy(true);
    setError("");
    try {
      const token = mode === "login" ? await login(name, password) : await register(name, password);
      onLogin(token, name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>snap-solver</h1>
        <p className="login-sub">拍照搜题 · {mode === "login" ? "登录" : "注册"}</p>
        <input placeholder="用户名" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input placeholder="密码(至少 6 位)" type="password" value={password}
               onChange={(e) => setPassword(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && submit()} />
        {error && <div className="login-error">{error}</div>}
        <button className="login-btn" onClick={submit} disabled={busy}>
          {busy ? "请稍候…" : mode === "login" ? "登录" : "注册并登录"}
        </button>
        <div className="login-switch" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
          {mode === "login" ? "没有账号?注册一个" : "已有账号?去登录"}
        </div>
      </div>
    </div>
  );
}