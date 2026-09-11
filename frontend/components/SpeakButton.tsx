"use client";

/**
 * A10 — ĐỌC KẾT QUẢ RA TIẾNG. Đúng nhóm người dùng TerraTwin nhắm tới — nông dân,
 * người lớn tuổi, người đọc chữ khó — nghe được câu trả lời quan trọng hơn đọc.
 * Dùng Web Speech API có sẵn trong trình duyệt: không khoá, không mạng, không
 * gửi gì đi đâu. Tự chọn giọng tiếng Việt nếu máy có; không có thì ẩn nút (nói
 * thẳng bằng cách biến mất, không hứa một tính năng máy không chạy được).
 */
import { useEffect, useState } from "react";
import { useLang } from "@/lib/i18n";

export default function SpeakButton({ text, lang = "vi-VN" }: {
  text: string; lang?: string;
}) {
  const { t } = useLang();
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    setSupported(typeof window !== "undefined"
      && "speechSynthesis" in window
      && typeof window.SpeechSynthesisUtterance !== "undefined");
    // Dừng đọc khi rời trang/đổi kết quả.
    return () => { try { window.speechSynthesis?.cancel(); } catch { /* */ } };
  }, []);

  if (!supported) return null;

  function toggle() {
    const synth = window.speechSynthesis;
    if (speaking) { synth.cancel(); setSpeaking(false); return; }
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    u.rate = 0.98;
    // Ưu tiên giọng đúng ngôn ngữ nếu có.
    const v = synth.getVoices().find((x) => x.lang?.toLowerCase().startsWith(lang.slice(0, 2)));
    if (v) u.voice = v;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    setSpeaking(true);
    synth.speak(u);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={speaking ? t("Dừng đọc", "Stop reading") : t("Đọc kết quả ra tiếng", "Read result aloud")}
      title={speaking ? t("Dừng đọc", "Stop reading") : t("Đọc kết quả ra tiếng", "Read result aloud")}
      style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        padding: "5px 11px", borderRadius: 99, cursor: "pointer", fontSize: 12.5,
        fontWeight: 600, border: "1px solid var(--line, #d7ddd8)",
        background: speaking ? "var(--pine, #1f5137)" : "transparent",
        color: speaking ? "#fff" : "var(--pine, #1f5137)",
      }}
    >
      {speaking ? "⏹ " + t("Dừng", "Stop") : "🔊 " + t("Đọc", "Listen")}
    </button>
  );
}
