"use client";

/**
 * M2 — ONBOARDING 3 bước cho người mở LẦN ĐẦU.
 *
 * Khác Story (tour 90 giây dùng Huế làm ví dụ): đây là chỉ đường NGẮN cho chính
 * người dùng bắt tay làm — chọn thửa → xem kết quả → bật cảnh báo. Hiện đúng một
 * lần (cờ localStorage), bỏ qua được ngay. Không chặn thao tác: chỉ là lớp phủ
 * mờ giải thích ba việc, đóng là vào dùng ngay.
 */
import { useEffect, useState } from "react";
import { useLang } from "@/lib/i18n";

const KEY = "tt_onboarded_v1";

export default function Onboarding() {
  const { t } = useLang();
  const [show, setShow] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    try { if (!localStorage.getItem(KEY)) setShow(true); } catch { /* */ }
  }, []);

  function close() {
    try { localStorage.setItem(KEY, "1"); } catch { /* */ }
    setShow(false);
  }

  if (!show) return null;

  const steps = [
    { icon: "📍", title: t("1. Chọn thửa của bạn", "1. Pick your plot"),
      body: t("Bấm một địa điểm mẫu, gõ tên xã/huyện, dán toạ độ GPS, hoặc bấm thẳng vào bản đồ.",
              "Tap a sample place, type a commune name, paste GPS coordinates, or click the map directly.") },
    { icon: "🔬", title: t("2. Xem kết quả", "2. See the result"),
      body: t("TerraTwin kiểm toàn bộ rủi ro 7 ngày tới cho đúng thửa đó — hiệu chuẩn riêng, kèm việc cần làm.",
              "TerraTwin checks every risk for the next 7 days for that exact plot — calibrated to it, with actions.") },
    { icon: "🛡️", title: t("3. Bật cảnh báo", "3. Turn on alerts"),
      body: t("Đăng nhập và lưu thửa — TerraTwin tự canh nền và báo TRƯỚC khi có rủi ro, bạn không cần nhớ mở.",
              "Log in and save the plot — TerraTwin watches in the background and warns you BEFORE risk hits.") },
  ];
  const s = steps[step];
  const last = step === steps.length - 1;

  return (
    <div onClick={close} style={{
      position: "fixed", inset: 0, zIndex: 60, background: "rgba(8,11,9,.55)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        maxWidth: 400, width: "100%", background: "var(--surface, #fff)",
        color: "var(--ink, #0f1411)", borderRadius: 14, padding: "26px 24px",
        boxShadow: "0 20px 60px -20px rgba(0,0,0,.5)",
      }}>
        <div style={{ fontSize: 46, textAlign: "center" }}>{s.icon}</div>
        <h2 style={{ fontSize: 20, fontWeight: 800, textAlign: "center", margin: "8px 0 6px" }}>{s.title}</h2>
        <p style={{ textAlign: "center", color: "var(--muted, #66716a)", margin: "0 0 18px", lineHeight: 1.55 }}>{s.body}</p>
        <div style={{ display: "flex", justifyContent: "center", gap: 6, marginBottom: 16 }}>
          {steps.map((_, i) => (
            <span key={i} style={{ width: 7, height: 7, borderRadius: 99,
              background: i === step ? "var(--pine, #1f5137)" : "var(--line, #d7ddd8)" }} />
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "space-between", alignItems: "center" }}>
          <button onClick={close} style={{ padding: "8px 12px", border: "none", background: "none",
            color: "var(--muted, #66716a)", cursor: "pointer", fontSize: 13 }}>
            {t("Bỏ qua", "Skip")}
          </button>
          <button onClick={() => (last ? close() : setStep(step + 1))} style={{
            padding: "10px 22px", borderRadius: 8, border: "none", cursor: "pointer",
            background: "var(--pine, #1f5137)", color: "#fff", fontWeight: 700 }}>
            {last ? t("Bắt đầu", "Start") : t("Tiếp →", "Next →")}
          </button>
        </div>
      </div>
    </div>
  );
}
