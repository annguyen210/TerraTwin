"use client";

import { useState } from "react";
import { login, register, setToken, type AuthUser } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function Account({
  user,
  onAuth,
}: {
  user: AuthUser | null;
  onAuth: (u: AuthUser | null) => void;
}) {
  const { t } = useLang();
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
          {t("Đăng xuất", "Log out")}
        </button>
      </div>
    );
  }

  if (!open) {
    return (
      <div className="acct">
        <button className="acct-in" onClick={() => setOpen(true)}>
          🔐 {t("Đăng nhập để lưu thửa đất", "Log in to save plots")}
        </button>
        <p className="acct-hint">
          {t("Chưa đăng nhập vẫn phân tích được — chỉ không lưu được danh mục.",
             "You can analyze without logging in — you just can't save a portfolio.")}
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
          {t("Đăng nhập", "Log in")}
        </button>
        <button
          type="button"
          className={mode === "register" ? "on" : ""}
          onClick={() => setMode("register")}
        >
          {t("Đăng ký", "Sign up")}
        </button>
      </div>

      {mode === "register" && (
        <input
          placeholder={t("Tên của bạn", "Your name")}
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
        placeholder={mode === "register"
          ? t("Mật khẩu (≥8 ký tự, có chữ và số)", "Password (≥8 chars, letters + digits)")
          : t("Mật khẩu", "Password")}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        minLength={mode === "register" ? 8 : undefined}
      />
      {mode === "login" && (
        <a className="acct-forgot" href="/forgot">{t("Quên mật khẩu?", "Forgot password?")}</a>
      )}
      {err && <p className="acct-err">{err}</p>}
      <div className="acct-actions">
        <button type="submit" disabled={busy}>
          {busy ? t("Đang xử lý…", "Working…")
                : mode === "login" ? t("Đăng nhập", "Log in") : t("Tạo tài khoản", "Create account")}
        </button>
        <button type="button" className="ghost" onClick={() => setOpen(false)}>
          {t("Đóng", "Close")}
        </button>
      </div>
    </form>
  );
}
