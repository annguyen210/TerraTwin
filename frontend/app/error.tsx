"use client";

/**
 * P5 — RANH GIỚI LỖI (500). Khi một trang ném lỗi lúc render, Next thay toàn bộ
 * bằng màn trắng nếu không có tệp này. Trang này bắt lỗi đó, xin lỗi thành thật,
 * cho nút thử lại (reset) và đường về — thay vì để người dùng đối diện màn trắng
 * không biết chuyện gì. KHÔNG phô chi tiết kỹ thuật ra ngoài.
 */
import { useEffect } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";

const wrap: React.CSSProperties = {
  minHeight: "72vh", display: "flex", flexDirection: "column",
  alignItems: "center", justifyContent: "center", textAlign: "center",
  padding: "40px 24px", gap: 14,
};

export default function Error({ error, reset }: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useLang();
  useEffect(() => {
    // Ghi ra console để còn lần theo được; không hiện cho người dùng.
    console.error("TerraTwin render error:", error);
  }, [error]);

  return (
    <main style={wrap}>
      <Link href="/" style={{ fontWeight: 700, fontSize: 18, textDecoration: "none", color: "var(--pine, #1f5137)" }}>
        ◵ TerraTwin
      </Link>
      <div style={{ fontSize: 52, lineHeight: 1 }}>⚠️</div>
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
        {t("Có gì đó trục trặc", "Something went wrong")}
      </h1>
      <p style={{ maxWidth: 460, color: "var(--muted, #66716a)", margin: 0 }}>
        {t("Trang này gặp lỗi khi hiển thị. Bạn thử lại được — dữ liệu của bạn không mất.",
           "This page hit an error while rendering. You can retry — your data is safe.")}
      </p>
      <div style={{ display: "flex", gap: 10, marginTop: 6, flexWrap: "wrap", justifyContent: "center" }}>
        <button onClick={() => reset()} style={{
          padding: "10px 20px", borderRadius: 6, fontWeight: 600, border: "none", cursor: "pointer",
          background: "var(--pine, #1f5137)", color: "#fff",
        }}>
          {t("↻ Thử lại", "↻ Try again")}
        </button>
        <Link href="/" style={{
          padding: "10px 20px", borderRadius: 6, fontWeight: 600, textDecoration: "none",
          border: "1px solid var(--line, #d7ddd8)", color: "var(--ink, #0f1411)",
        }}>
          {t("Về trang đầu", "Back home")}
        </Link>
      </div>
      {error?.digest && (
        <p style={{ fontSize: 11, color: "var(--muted, #66716a)", marginTop: 8 }}>
          {t("Mã lỗi", "Error code")}: {error.digest}
        </p>
      )}
    </main>
  );
}
