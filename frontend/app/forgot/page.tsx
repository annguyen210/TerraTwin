"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { forgotPassword, getHealth } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

const SUPPORT_URL = "https://github.com/annguyen210/TerraTwin/issues";

export default function ForgotPage() {
  const { t } = useLang();
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // N1 — SMTP chưa cấu hình thì nút này KHÔNG hoạt động dù vẫn trả 200 (cố ý,
  // chống dò email) — phải nói trước, không để người dùng chờ một email không
  // bao giờ tới rồi mới biết.
  const [smtpDown, setSmtpDown] = useState(false);

  useEffect(() => {
    getHealth().then((h) => setSmtpDown(!h.email.smtp_configured)).catch(() => {});
  }, []);

  async function submit() {
    if (!email.trim() || busy) return;
    setBusy(true); setMsg(null); setDevLink(null);
    try {
      const r = await forgotPassword(email.trim());
      setMsg(r.message);
      if (r.dev_link) setDevLink(r.dev_link);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions"><LangToggle /><Link href="/" className="doc-home">{t("← Về trang chính", "← Home")}</Link></div>
      </header>
      <article className="doc-body" style={{ maxWidth: 460 }}>
        <h1>{t("Quên mật khẩu", "Forgot password")}</h1>
        <p className="doc-lede">
          {t("Nhập email tài khoản — chúng tôi sẽ gửi liên kết đặt lại (hết hạn sau 1 giờ).",
             "Enter your account email — we'll send a reset link (expires in 1 hour).")}
        </p>
        {smtpDown && (
          <p className="auth-dev" role="alert">
            {t("⚠️ Máy chủ hiện CHƯA gửi được email. Nút dưới vẫn bấm được nhưng sẽ " +
               "không có thư nào tới hộp thư của bạn. Dùng đường liên hệ dự phòng: ",
               "⚠️ The server currently CANNOT send email. The button below still " +
               "works but no message will reach your inbox. Use this fallback contact: ")}
            <a href={SUPPORT_URL} target="_blank" rel="noreferrer">{SUPPORT_URL}</a>
          </p>
        )}
        <div className="auth-form">
          <input type="email" placeholder="email@..." value={email}
                 onChange={(e) => setEmail(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
          <button className="doc-btn" onClick={submit} disabled={busy}>
            {busy ? "…" : t("Gửi liên kết đặt lại", "Send reset link")}
          </button>
        </div>
        {msg && <p className="auth-msg">{msg}</p>}
        {devLink && (
          <p className="auth-dev">
            {t("(Chế độ dev — chưa cấu hình email) Liên kết đặt lại:", "(Dev mode — SMTP not set) Reset link:")}{" "}
            <Link href={devLink.replace(/^https?:\/\/[^/]+/, "")}>{t("mở", "open")}</Link>
          </p>
        )}
        <footer className="doc-foot"><Link href="/">{t("Đăng nhập", "Sign in")}</Link><span>·</span><Link href="/help">{t("Trợ giúp", "Help")}</Link></footer>
      </article>
    </div>
  );
}
