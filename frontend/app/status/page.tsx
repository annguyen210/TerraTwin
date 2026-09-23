"use client";

/**
 * P5 — trạng thái hệ thống CÔNG KHAI, không cần đăng nhập. /api/health đã có
 * sẵn từ N1 (banner SMTP ở /forgot) nhưng chưa ai xem được nó ở dạng người đọc
 * được — trang này chỉ trình bày lại, không thêm logic mới phía máy chủ.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { getHealth, type HealthStatus } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

function when(iso: string | null | undefined, lang: "vi" | "en"): string {
  if (!iso) return lang === "vi" ? "chưa từng" : "never";
  return new Date(iso).toLocaleString(lang === "vi" ? "vi-VN" : "en-US", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function StatusPage() {
  const { t, lang } = useLang();
  const [h, setH] = useState<HealthStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [at, setAt] = useState<Date | null>(null);

  function load() {
    getHealth().then((r) => { setH(r); setAt(new Date()); setErr(null); })
      .catch((e) => setErr(e.message));
  }
  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);   // tự làm mới mỗi phút — không cần bấm
    return () => clearInterval(id);
  }, []);

  const ok = h?.status === "ok";

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions"><LangToggle /><Link href="/" className="doc-home">{t("← Về trang chính", "← Home")}</Link></div>
      </header>

      <main className="doc-body" style={{ maxWidth: 640 }}>
        <h1>{t("Trạng thái hệ thống", "System status")}</h1>

        {err && (
          <p className="ws-err">
            ⚠️ {t("Không tải được trạng thái — có thể máy chủ đang khởi động lại (gói miễn phí ngủ sau 15 phút không dùng).",
                  "Couldn't load status — the server may be cold-starting (free tier sleeps after 15 min idle).")}
          </p>
        )}
        {!h && !err && <p className="ws-hint">{t("Đang tải…", "Loading…")}</p>}

        {h && (
          <>
            <div style={{
              display: "flex", alignItems: "center", gap: 10, margin: "16px 0",
              padding: "14px 18px", borderRadius: 12,
              background: ok ? "rgba(62,203,131,.08)" : "rgba(224,164,74,.08)",
              border: `1px solid ${ok ? "rgba(62,203,131,.3)" : "rgba(224,164,74,.3)"}`,
            }}>
              <span style={{ fontSize: 22 }}>{ok ? "✅" : "⚠️"}</span>
              <b style={{ fontSize: "1.05rem" }}>
                {ok ? t("Mọi thứ bình thường", "All systems normal")
                    : t("Đang suy giảm — xem chi tiết bên dưới", "Degraded — see details below")}
              </b>
            </div>

            <table className="ws-table">
              <tbody>
                <tr>
                  <td>{t("Rà soát cảnh báo gần nhất", "Last alert sweep")}</td>
                  <td>{when(h.radar.last_sweep_at, lang)}</td>
                </tr>
                <tr>
                  <td>{t("Gửi email (quên mật khẩu, xác thực)", "Email delivery (reset, verification)")}</td>
                  <td>{h.email.smtp_configured
                    ? t("✅ hoạt động", "✅ working")
                    : t("⚠️ chưa cấu hình — xem /forgot", "⚠️ not configured — see /forgot")}</td>
                </tr>
                <tr>
                  <td>{t("Nguồn dữ liệu hết hạn mức", "Data sources over quota")}</td>
                  <td>{h.quota.exhausted.length === 0
                    ? t("không có", "none")
                    : h.quota.exhausted.join(", ")}</td>
                </tr>
                <tr>
                  <td>{t("Số mô-đun đang chạy", "Modules running")}</td>
                  <td>{h.modules}</td>
                </tr>
              </tbody>
            </table>

            <p className="ws-hint" style={{ marginTop: 14 }}>
              {t("Hạn mức nguồn dữ liệu tự đặt lại sau vài giờ — không phải máy chủ chết.",
                 "Data-source quotas reset within hours on their own — not a server outage.")}
              {" "}{t("Nguồn dữ liệu miễn phí có thể bị chặn tạm thời khi cả hệ thống dùng chung vượt hạn mức ngày.",
                      "Free data sources can be rate-limited temporarily when shared daily quotas are exceeded.")}
            </p>
          </>
        )}

        {at && (
          <p className="ws-hint" style={{ marginTop: 20 }}>
            {t("Cập nhật lúc", "Updated at")} {at.toLocaleTimeString(lang === "vi" ? "vi-VN" : "en-US")}
            {" · "}
            <button className="doc-link-btn" onClick={load}>{t("làm mới", "refresh")}</button>
          </p>
        )}
      </main>
    </div>
  );
}
