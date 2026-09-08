"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { resetPassword } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

export default function ResetPage() {
  const { t } = useLang();
  const params = useParams();
  const token = Array.isArray(params.token) ? params.token[0] : (params.token ?? "");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (pw.length < 8 || busy) { setMsg(t("Mật khẩu cần tối thiểu 8 ký tự, có cả chữ và số.", "Password needs at least 8 chars, letters + numbers.")); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await resetPassword(token, pw);
      setMsg(r.message); setDone(true);
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
        <h1>{t("Đặt lại mật khẩu", "Reset password")}</h1>
        {done ? (
          <>
            <p className="auth-msg">✅ {msg}</p>
            <div className="doc-cta"><Link href="/" className="doc-btn">{t("Đăng nhập", "Sign in")}</Link></div>
          </>
        ) : (
          <>
            <p className="doc-lede">{t("Nhập mật khẩu mới (tối thiểu 8 ký tự, có chữ và số).", "Enter a new password (min 8 chars, letters + numbers).")}</p>
            <div className="auth-form">
              <input type="password" placeholder={t("Mật khẩu mới", "New password")} value={pw}
                     onChange={(e) => setPw(e.target.value)}
                     onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
              <button className="doc-btn" onClick={submit} disabled={busy}>
                {busy ? "…" : t("Đặt lại mật khẩu", "Reset password")}
              </button>
            </div>
            {msg && <p className="auth-msg">{msg}</p>}
          </>
        )}
      </article>
    </div>
  );
}
