"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { verifyEmail } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

export default function VerifyEmailPage() {
  const { t } = useLang();
  const params = useParams();
  const token = Array.isArray(params.token) ? params.token[0] : (params.token ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    if (!token) return;
    verifyEmail(token)
      .then((r) => { setMsg(r.message); setOk(true); })
      .catch((e) => { setMsg((e as Error).message); setOk(false); });
  }, [token]);

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions"><LangToggle /><Link href="/" className="doc-home">{t("← Về trang chính", "← Home")}</Link></div>
      </header>
      <article className="doc-body" style={{ maxWidth: 460 }}>
        <h1>{t("Xác thực email", "Verify email")}</h1>
        {ok === null && <p className="doc-lede">{t("Đang xác thực…", "Verifying…")}</p>}
        {ok === true && (
          <>
            <p className="auth-msg">✅ {msg}</p>
            <div className="doc-cta"><Link href="/" className="doc-btn">{t("Về trang chính", "Go home")}</Link></div>
          </>
        )}
        {ok === false && (
          <>
            <p className="auth-msg">❌ {msg}</p>
            <p className="doc-lede">
              {t("Liên kết có thể đã hết hạn (24 giờ) hoặc đã dùng rồi. Đăng nhập rồi mở trang tài khoản để gửi lại.",
                 "The link may have expired (24 hours) or was already used. Sign in and open the account page to resend it.")}
            </p>
          </>
        )}
      </article>
    </div>
  );
}
