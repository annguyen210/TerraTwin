"use client";

/**
 * CÀI LÊN MÀN HÌNH CHÍNH (2/11/2026) — mở trên điện thoại thì mời cài TerraTwin như một ứng dụng (PWA đã có sẵn:
 * manifest + sw.js). Android/Chrome: dùng đúng hộp thoại cài của trình duyệt (sự kiện beforeinstallprompt). iPhone/iPad
 * Safari không có hộp thoại đó → chỉ hướng dẫn "Chia sẻ → Thêm vào MH chính". Đã cài (chạy standalone), đang nằm
 * trong khung nhúng, hoặc người dùng đã tắt trong 30 ngày → không hiện. Không gửi gì đi đâu.
 */
import { useEffect, useState } from "react";
import { Download, Share, X } from "lucide-react";
import { useLang } from "@/lib/i18n";

type BIPEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

const KEY = "tt-install-dismissed";
const QUIET_MS = 30 * 24 * 3600 * 1000;

function dismissedRecently(): boolean {
  try { const v = Number(localStorage.getItem(KEY) || 0); return Date.now() - v < QUIET_MS; } catch { return false; }
}

function standalone(): boolean {
  return window.matchMedia?.("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

export default function InstallApp() {
  const { t } = useLang();
  const [evt, setEvt] = useState<BIPEvent | null>(null);
  const [ios, setIos] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (standalone() || window.self !== window.top || dismissedRecently()) return;
    const onPrompt = (e: Event) => { e.preventDefault(); setEvt(e as BIPEvent); setOpen(true); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    const ua = navigator.userAgent;
    const isIos = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
    const safari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (isIos && safari) { setIos(true); timer = setTimeout(() => setOpen(true), 6000); }   // để người dùng nhìn trang trước
    const onInstalled = () => setOpen(false);
    window.addEventListener("appinstalled", onInstalled);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); window.removeEventListener("appinstalled", onInstalled); if (timer) clearTimeout(timer); };
  }, []);

  function dismiss() {
    setOpen(false);
    try { localStorage.setItem(KEY, String(Date.now())); } catch { /* chế độ riêng tư */ }
  }

  async function install() {
    if (!evt) return;
    await evt.prompt();
    const r = await evt.userChoice.catch(() => null);
    setEvt(null);
    if (r?.outcome === "accepted") setOpen(false); else dismiss();
  }

  if (!open || (!evt && !ios)) return null;
  return (
    <div className="tt-install" role="dialog" aria-label={t("Cài TerraTwin lên màn hình chính", "Install TerraTwin on your home screen")}>
      <span className="tt-logo" aria-hidden="true"><span /></span>
      <div className="tt-install-t">
        <b>{t("Cài TerraTwin như một ứng dụng", "Install TerraTwin as an app")}</b>
        {ios
          ? <small>{t("Bấm ", "Tap ")}<Share size={13} aria-label={t("Chia sẻ", "Share")} />{t(" ở thanh dưới Safari, rồi chọn \"Thêm vào MH chính\".", " in Safari's toolbar, then \"Add to Home Screen\".")}</small>
          : <small>{t("Mở nhanh từ màn hình chính, toàn màn hình, không cần cửa hàng ứng dụng.", "Opens fast from your home screen, full screen, no app store needed.")}</small>}
      </div>
      {!ios && <button type="button" className="tt-install-go" onClick={install}><Download size={15} aria-hidden="true" /> {t("Cài", "Install")}</button>}
      <button type="button" className="tt-install-x" onClick={dismiss} aria-label={t("Để sau", "Not now")}><X size={16} aria-hidden="true" /></button>
    </div>
  );
}
