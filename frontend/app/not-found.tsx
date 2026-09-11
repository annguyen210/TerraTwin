"use client";

/**
 * P5 — TRANG 404. Trước đây gõ sai URL (hoặc link cũ) rơi vào trang trắng mặc
 * định của Next, lạc lõng khỏi sản phẩm. Trang này giữ người dùng trong mạch
 * TerraTwin và chỉ đường về, song ngữ.
 */
import Link from "next/link";
import { useLang } from "@/lib/i18n";

const wrap: React.CSSProperties = {
  minHeight: "72vh", display: "flex", flexDirection: "column",
  alignItems: "center", justifyContent: "center", textAlign: "center",
  padding: "40px 24px", gap: 14,
};

export default function NotFound() {
  const { t } = useLang();
  return (
    <main style={wrap}>
      <Link href="/" style={{ fontWeight: 700, fontSize: 18, textDecoration: "none", color: "var(--pine, #1f5137)" }}>
        ◵ TerraTwin
      </Link>
      <div style={{ fontSize: 60, fontWeight: 800, lineHeight: 1, color: "var(--pine, #1f5137)" }}>404</div>
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
        {t("Không có trang này", "This page doesn't exist")}
      </h1>
      <p style={{ maxWidth: 440, color: "var(--muted, #66716a)", margin: 0 }}>
        {t("Liên kết có thể đã cũ hoặc gõ sai. Về trang đầu để chọn thửa đất và kiểm tra rủi ro.",
           "The link may be old or mistyped. Head home to pick a plot and check its risks.")}
      </p>
      <Link href="/" style={{
        marginTop: 6, padding: "10px 20px", borderRadius: 6, fontWeight: 600,
        background: "var(--pine, #1f5137)", color: "#fff", textDecoration: "none",
      }}>
        {t("← Về trang đầu", "← Back home")}
      </Link>
    </main>
  );
}
