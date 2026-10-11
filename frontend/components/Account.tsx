"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { login, register, setToken, type AuthUser, type LoginError } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { ChevronDown, LayoutDashboard, LogIn, LogOut, UserRound } from "lucide-react";

const ROLE_VI: Record<string, string> = { admin: "Quản trị", coop: "Hợp tác xã", user: "Người dùng" };
const ROLE_EN: Record<string, string> = { admin: "Admin", coop: "Co-op", user: "User" };

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
  const [otpNeeded, setOtpNeeded] = useState(false);   // GĐ7 — tài khoản bật hai lớp
  const [otp, setOtp] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r =
        mode === "login"
          ? await login(email.trim(), password, otpNeeded ? otp.trim() : undefined)
          : await register(email.trim(), password, name.trim());
      setToken(r.access_token);
      onAuth(r.user);
      setOpen(false);
      setPassword("");
      setOtp("");
      setOtpNeeded(false);
    } catch (e) {
      if ((e as LoginError).otpRequired) setOtpNeeded(true);
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken(null);
    onAuth(null);
  }

  if (user) return <AccountMenu user={user} onLogout={logout} />;

  if (!open) {
    return (
      <div className="acct">
        <button className="acct-in" onClick={() => setOpen(true)}>
          <LogIn size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Đăng nhập", "Log in")}
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
      {mode === "login" && otpNeeded && (
        <input
          inputMode="numeric"
          autoComplete="one-time-code"
          aria-label={t("Mã xác thực hai lớp", "Two-factor code")}
          placeholder={t("Mã 6 số trong ứng dụng Authenticator (hoặc mã khôi phục)", "6-digit code from your Authenticator app (or a recovery code)")}
          value={otp}
          onChange={(e) => setOtp(e.target.value)}
          maxLength={32}
          required
          autoFocus
        />
      )}
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


/** Bấm tên tài khoản → menu: ai đang đăng nhập, vai trò (nói bằng lời), Tài khoản của tôi, Quản trị (nếu có quyền), Đăng xuất. */
function AccountMenu({ user, onLogout }: { user: AuthUser; onLogout: () => void }) {
  const { t, lang } = useLang();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  const role = user.role ?? "user";
  return (
    <div className="acct acct-menu-wrap" ref={box}>
      <button type="button" className="acct-who acct-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className={`acct-dot role-${role}`} />
        <span className="acct-mail" title={user.email}>{user.name || user.email}</span>
        {role !== "user" && <span className={`acct-role role-${role}`}>{(lang === "en" ? ROLE_EN : ROLE_VI)[role] ?? role}</span>}
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div className="acct-menu" role="menu">
          <div className="acct-menu-head">
            <b>{user.name || t("(chưa đặt tên)", "(no name)")}</b>
            <span>{user.email}</span>
            <small>{t("Vai trò", "Role")}: {(lang === "en" ? ROLE_EN : ROLE_VI)[role] ?? role}
              {" · "}{user.email_verified ? t("email đã xác thực", "email verified") : t("email chưa xác thực", "email not verified")}
              {" · "}{user.totp_enabled ? t("hai lớp: bật", "2FA: on") : t("hai lớp: chưa bật", "2FA: off")}</small>
          </div>
          <Link href="/tai-khoan" role="menuitem" className="acct-menu-item" onClick={() => setOpen(false)}>
            <UserRound size={16} aria-hidden="true" /> {t("Tài khoản của tôi — thông tin, dữ liệu, lịch sử", "My account — details, data, history")}</Link>
          {(role === "admin" || role === "coop") && (
            <Link href="/admin" role="menuitem" className="acct-menu-item" onClick={() => setOpen(false)}>
              <LayoutDashboard size={16} aria-hidden="true" /> {role === "admin" ? t("Trang quản trị", "Admin page") : t("Hợp tác xã", "Co-op")}</Link>
          )}
          <button type="button" role="menuitem" className="acct-menu-item" onClick={() => { setOpen(false); onLogout(); }}>
            <LogOut size={16} aria-hidden="true" /> {t("Đăng xuất", "Log out")}</button>
        </div>
      )}
    </div>
  );
}
