"use client";

/**
 * KIỂM ẢNH RUỘNG NGAY TRÊN MÁY (nâng cấp 25/11/2026) — Edge AI: mô hình SegFormer "nước trong ảnh thực địa" (bản v2 đã qua
 * cổng, cùng mô hình máy chủ dùng) chạy bằng onnxruntime-web trong trình duyệt qua public/fieldcheck.js. Ảnh KHÔNG rời
 * máy; sau lần tải đầu (~27 MB) chạy được cả khi mất sóng (service worker giữ mô hình; trang offline.html cũng dùng được).
 */
import { useEffect, useState } from "react";
import { Camera } from "lucide-react";
import { useLang } from "@/lib/i18n";

type R = { ratio: number; ms: number; offline: boolean };
declare global {
  interface Window { ttFieldCheck?: (f: File) => Promise<R>; ttFieldCheckReady?: () => Promise<boolean> }
}

function loadScript(): Promise<void> {
  if (window.ttFieldCheck) return Promise.resolve();
  return new Promise((ok, bad) => {
    const s = document.createElement("script");
    s.src = "/fieldcheck.js";
    s.onload = () => ok();
    s.onerror = () => bad(new Error("fieldcheck.js"));
    document.head.appendChild(s);
  });
}

export default function PhotoCheckLocal() {
  const { t } = useLang();
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState<"" | "dl" | "run">("");
  const [r, setR] = useState<R | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    // Đã tải trước đây? (kho đệm AI của service worker) → coi như sẵn sàng, không tải lại.
    caches?.open("terratwin-ai-v1").then((c) => c.match("/models/field_water.onnx")).then((hit) => setReady(!!hit)).catch(() => {});
  }, []);

  async function download() {
    setBusy("dl"); setErr(null);
    try { await loadScript(); await window.ttFieldCheckReady!(); setReady(true); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(""); }
  }

  async function run(f: File) {
    setBusy("run"); setErr(null); setR(null);
    try { await loadScript(); setR(await window.ttFieldCheck!(f)); setReady(true); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(""); }
  }

  return (
    <section className="lc2 pcl">
      <div className="wh-head">
        <Camera size={18} aria-hidden="true" />
        <h3>{t("Kiểm ảnh ruộng ngay trên máy", "Check a field photo on your device")}</h3>
        <span className="wh-badge lc2-badge">{t("AI trên máy · không cần mạng", "on-device AI · works offline")}</span>
      </div>
      <p className="doc-note">{t("Chụp ảnh ruộng: AI cho biết bao nhiêu phần ảnh là nước, chạy NGAY trên điện thoại — ảnh không gửi đi đâu. Tải AI về máy một lần (~27 MB, nên dùng Wi-Fi), sau đó dùng được cả khi mất sóng.",
                                 "Take a field photo: the AI tells how much of it is water, running ON your phone — the photo goes nowhere. Download the AI once (~27 MB, Wi-Fi recommended), then it works even without signal.")}</p>
      <div className="pcl-row">
        {!ready && (
          <button type="button" className="bat-btn ghost" onClick={download} disabled={!!busy}>
            {busy === "dl" ? t("Đang tải AI…", "Downloading AI…") : t("Tải AI về máy", "Download AI to device")}
          </button>
        )}
        <label className="bat-btn">
          {busy === "run" ? t("Đang phân tích…", "Analysing…") : t("📷 Chụp / chọn ảnh", "📷 Take / choose photo")}
          <input type="file" accept="image/*" capture="environment" hidden disabled={!!busy}
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) run(f); e.target.value = ""; }} />
        </label>
      </div>
      {r && (
        <p className="wh-sum" role="status">
          <b>{Math.round(r.ratio * 100)}%</b> {t("diện tích ảnh là nước", "of the photo is water")} · {r.ms} ms{r.offline ? t(" · đang mất mạng", " · offline") : ""}.{" "}
          {t("Tín hiệu tham khảo, không phải kết luận ngập.", "A reference signal, not a flood verdict.")}
        </p>
      )}
      {err && <p className="bat-err">{t("Chưa chạy được: ", "Could not run: ")}{err}</p>}
    </section>
  );
}
