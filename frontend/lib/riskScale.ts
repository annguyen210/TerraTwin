// HAI THANG KHÁC NHAU cho `risk_level`.
//
// Với mô-đun hiểm hoạ (threat=true) — lũ, hạn, sạt lở… — danger nghĩa là sắp
// có chuyện xấu, và màu đỏ là đúng. Với mô-đun thông tin/cơ hội (threat=false)
// — điện mặt trời, năng suất, carbon, rủi ro mua đất… — cùng giá trị "danger"
// chỉ là "kém trên thang của chính nó": đo ở Huế, điện mặt trời hiện NGUY HIỂM
// màu đỏ chỉ vì bức xạ trung bình 4,22 kWh/m²/ngày. Người xem đọc màu đỏ là
// nguy hiểm, không đọc chú thích. Nên thang thông tin có NHÃN riêng
// (phù hợp / trung bình / kém) và MÀU trung tính — không đỏ, không vàng cam.

export type Level = { vi: string; en: string; color: string };

const UNKNOWN: Level = { vi: "—", en: "—", color: "#5a6b73" };

const HAZARD: Record<string, Level> = {
  safe: { vi: "An toàn", en: "Safe", color: "#2E9E67" },
  warning: { vi: "Cảnh báo", en: "Warning", color: "#B07A2E" },
  danger: { vi: "Nguy hiểm", en: "Danger", color: "#C2412E" },
};

const FIT: Record<string, Level> = {
  safe: { vi: "Phù hợp", en: "Good fit", color: "#4A7FB0" },
  warning: { vi: "Trung bình", en: "Average", color: "#7C8A96" },
  danger: { vi: "Kém", en: "Poor", color: "#9A8B78" },
};

export function levelOf(risk: string | undefined, threat: boolean | undefined = true): Level {
  const scale = threat === false ? FIT : HAZARD;
  return (risk && scale[risk]) || UNKNOWN;
}

// Lớp CSS cho ô lưới toàn cảnh (Answer.tsx): hiểm hoạ giữ bad/warn/ok, thông
// tin dùng fit-* (màu trung tính trong globals.css).
export function toneOf(risk: string, threat: boolean | undefined = true): string | undefined {
  if (threat === false) {
    return { safe: "fit-good", warning: "fit-mid", danger: "fit-poor" }[risk];
  }
  return { safe: "ok", warning: "warn", danger: "bad" }[risk];
}

export const TONE_HEX: Record<string, string> = {
  bad: "#C2412E", warn: "#B07A2E", ok: "#2E9E67", pending: "#3aa0a0", wait: "#5a6b73",
  "fit-good": FIT.safe.color, "fit-mid": FIT.warning.color, "fit-poor": FIT.danger.color,
};
