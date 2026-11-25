/**
 * Nhận giọng nói ngay trong trình duyệt (Web Speech API) — không gửi âm thanh lên máy chủ TerraTwin, không tốn phí.
 * Chrome/Edge trên Android & máy tính hỗ trợ tiếng Việt (vi-VN); trình duyệt không hỗ trợ thì trả null và nơi gọi ẩn
 * nút micro. Dùng chung cho chế độ thực địa (FieldMode) và trợ lý (Copilot).
 */
export type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
};

export function getRecognition(lang: "vi" | "en" = "vi"): SpeechRecognitionLike | null {
  if (typeof window === "undefined") return null;
  const Ctor = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
  if (!Ctor) return null;
  const r: SpeechRecognitionLike = new Ctor();
  r.lang = lang === "en" ? "en-US" : "vi-VN";
  r.continuous = false;
  r.interimResults = true;
  return r;
}

/** Ghép văn bản từ sự kiện onresult (cả phần tạm và phần đã chốt). */
export function transcriptOf(e: any): { text: string; final: boolean } {
  let text = "";
  let final = false;
  for (let i = 0; i < e.results.length; i++) {
    text += e.results[i][0].transcript;
    if (e.results[i].isFinal) final = true;
  }
  return { text: text.trim(), final };
}
