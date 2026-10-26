"use client";

/**
 * GĐ7 — XÁC THỰC HAI LỚP (TOTP). Quét QR bằng Google Authenticator / Microsoft Authenticator / 2FAS…, nhập
 * mã đang hiện để bật; nhận 8 mã khôi phục dùng một lần (chỉ hiện MỘT lần). Tắt cần cả mật khẩu lẫn mã.
 */
import { useState } from "react";
import { twoFaDisable, twoFaEnable, twoFaSetup, type AuthUser, type TwoFaSetup } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function TwoFactor({ user }: { user: AuthUser }) {
  const { t } = useLang();
  const [on, setOn] = useState(user.totp_enabled === true);
  const [setup, setSetup] = useState<TwoFaSetup | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  // Chép / tải mã khôi phục: chép tay 8 mã dễ sai một ký tự — đúng lúc mất điện thoại mới biết.
  const codesText = () => `TerraTwin — mã khôi phục hai lớp (${user.email}), mỗi mã dùng MỘT lần:\n${(codes ?? []).join("\n")}\n`;
  async function copy(text: string, what: string) {
    try { await navigator.clipboard.writeText(text); setCopied(what); } catch { setCopied(null); }
  }
  function saveCodes() {
    const url = URL.createObjectURL(new Blob([codesText()], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = "terratwin-ma-khoi-phuc.txt"; a.click(); URL.revokeObjectURL(url);
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true); setErr(null);
    try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="tf" style={{ marginTop: 16 }}>
      <h4>🔐 {t("Xác thực hai lớp", "Two-factor authentication")} — {on ? t("ĐANG BẬT", "ON") : t("đang tắt", "off")}</h4>
      <p className="tf-note">{t("Đăng nhập cần thêm mã 6 số đổi mỗi 30 giây trên điện thoại. Bắt buộc với tài khoản quản trị; nên bật với tài khoản doanh nghiệp.",
                                "Logging in also needs a 6-digit code that changes every 30 seconds on your phone. Required for admin accounts; recommended for business accounts.")}</p>
      {err && <p className="ws-err">⚠️ {err}</p>}

      {codes && (
        <div className="tf-codes" role="status">
          <b>{t("Mã khôi phục — lưu ngay, chỉ hiện một lần:", "Recovery codes — save now, shown only once:")}</b>
          <ul>{codes.map((c) => <li key={c}><code>{c}</code></li>)}</ul>
          <p className="ws-row">
            <button type="button" className="bat-btn ghost" onClick={() => copy(codesText(), "codes")}>{t("Chép 8 mã", "Copy 8 codes")}</button>
            <button type="button" className="bat-btn ghost" onClick={saveCodes}>{t("Tải tệp .txt", "Download .txt")}</button>
            {copied === "codes" && <small role="status">{t("Đã chép — dán vào nơi an toàn (không phải điện thoại đang dùng mã).", "Copied — paste somewhere safe (not the phone holding the codes).")}</small>}
          </p>
          <small>{t("Mỗi mã dùng được một lần khi mất điện thoại.", "Each code works once if you lose your phone.")}</small>
        </div>
      )}

      {!on && !setup && (
        <button type="button" className="bat-btn" disabled={busy} onClick={() => run(async () => setSetup(await twoFaSetup()))}>
          {t("Bật xác thực hai lớp", "Turn on two-factor")}</button>
      )}

      {!on && setup && (
        <div className="tf-setup">
          {setup.qr && <img src={setup.qr} width={168} height={168} alt={t("Mã QR để quét bằng ứng dụng Authenticator", "QR code to scan with your Authenticator app")} />}
          <div>
            <p>{t("1. Quét mã QR bằng ứng dụng Authenticator (hoặc nhập khoá:", "1. Scan the QR with your Authenticator app (or enter the key:")} <code className="tf-secret">{setup.secret}</code>)</p>
            {/* Đang mở trang này NGAY trên điện thoại có Authenticator thì không quét được màn hình của chính nó. */}
            <p className="ws-row">
              <a className="bat-btn ghost" href={setup.otpauth_uri}>{t("Đang dùng điện thoại? Mở thẳng ứng dụng Authenticator", "On your phone? Open the Authenticator app directly")}</a>
              <button type="button" className="bat-btn ghost" onClick={() => copy(setup.secret, "key")}>{t("Chép khoá", "Copy key")}</button>
              {copied === "key" && <small role="status">{t("Đã chép khoá — dán vào Authenticator (Thêm → Nhập khoá thiết lập).", "Key copied — paste it into Authenticator (Add → Enter a setup key).")}</small>}
            </p>
            <label className="pk-field">{t("2. Nhập mã 6 số đang hiện", "2. Enter the 6-digit code shown")}
              <input inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code} onChange={(e) => setCode(e.target.value)} />
            </label>
            <button type="button" className="bat-btn" disabled={busy || code.trim().length < 6}
                    onClick={() => run(async () => { const r = await twoFaEnable(code.trim()); setCodes(r.recovery_codes); setOn(true); setSetup(null); setCode(""); })}>
              {t("Xác nhận và bật", "Confirm and turn on")}</button>
          </div>
        </div>
      )}

      {on && (
        <details className="tf-off">
          <summary>{t("Tắt xác thực hai lớp", "Turn off two-factor")}</summary>
          <label className="pk-field">{t("Mật khẩu", "Password")}
            <input type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} /></label>
          <label className="pk-field">{t("Mã 6 số hoặc mã khôi phục", "6-digit code or recovery code")}
            <input inputMode="numeric" autoComplete="one-time-code" maxLength={32} value={code} onChange={(e) => setCode(e.target.value)} /></label>
          <button type="button" className="bat-btn ghost" disabled={busy || !pw || code.trim().length < 6}
                  onClick={() => run(async () => { await twoFaDisable(pw, code.trim()); setOn(false); setPw(""); setCode(""); setCodes(null); })}>
            {t("Tắt", "Turn off")}</button>
        </details>
      )}
    </div>
  );
}
