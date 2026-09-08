"use client";

import { useState } from "react";
import { login, register, setToken, type AuthUser } from "@/lib/api";

export default function Account({
  user,
  onAuth,
}: {
  user: AuthUser | null;
  onAuth: (u: AuthUser | null) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r =
        mode === "login"
          ? await login(email.trim(), password)
          : await register(email.trim(), password, name.trim());
      setToken(r.access_token);
      onAuth(r.user);
      setOpen(false);
      setPassword("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken(null);
    onAuth(null);
  }

  if (user) {
    return (
      <div className="acct">
        <div className="acct-who">
          <span className="acct-dot" />
          <span className="acct-mail" title={user.email}>
            {user.name || user.email}
          </span>
        </div>
        <button className="acct-out" onClick={logout}>
          Đăng xuất
        </button>
      </div>
    );
  }

  if (!open) {
    return (
      <div className="acct">
        <button className="acct-in" onClick={() => setOpen(true)}>
          🔐 Đăng nhập để lưu thửa đất
        </button>
        <p className="acct-hint">
          Chưa đăng nhập vẫn phân tích được — chỉ không lưu được danh mục.
        </p>
      </div>
    );
  }

  return (
    <form className="acct acct-form" onSubmit={submit}>
      <div className="acct-tabs">
        <button
          type="button"
          className={mode === "login" ? "on" : ""}
          onClick={() => setMode("login")}
        >
          Đăng nhập
        </button>
        <button
          type="button"
          className={mode === "register" ? "on" : ""}
          onClick={() => setMode("register")}
        >
          Đăng ký
        </button>
      </div>

      {mode === "register" && (
        <input
          placeholder="Tên của bạn"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={120}
        />
      )}
      <input
        type="email"
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />
      <input
        type="password"
        placeholder={mode === "register" ? "Mật khẩu (≥8 ký tự, có chữ và số)" : "Mật khẩu"}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        minLength={mode === "register" ? 8 : undefined}
      />
      {mode === "login" && (
        <a className="acct-forgot" href="/forgot">Quên mật khẩu?</a>
      )}
      {err && <p className="acct-err">{err}</p>}
      <div className="acct-actions">
        <button type="submit" disabled={busy}>
          {busy ? "Đang xử lý…" : mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
        </button>
        <button type="button" className="ghost" onClick={() => setOpen(false)}>
          Đóng
        </button>
      </div>
    </form>
  );
}
