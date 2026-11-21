// PHIẾU GÓP Ý THÍ ĐIỂM — phần kiểm "còn thiếu câu nào", dùng chung cho /dung-thu và /thi-diem (kiểm A–Z 21/11/2026).
// Bản cũ đặt sẵn would_use="yes", hardest="none": người chỉ chấm hai câu điểm rồi bấm gửi thì phiếu ghi "sẽ dùng" và
// "không có chỗ khó" — số liệu thí điểm bị lệch về phía tốt mà không ai chọn. Nay mọi câu chọn đều bắt đầu RỖNG và bắt
// buộc chọn; máy chủ cũng trả 422 nếu thiếu (backend/app/routes_pilot.py).
import type { PilotFeedbackIn } from "./api";

export type FeedbackDraft = Omit<PilotFeedbackIn, "would_use" | "hardest"> & {
  would_use: PilotFeedbackIn["would_use"] | "";
  hardest: PilotFeedbackIn["hardest"] | "";
};

export type Missing = "ease" | "trust" | "would_use" | "hardest" | "consent";

export function blankFeedback(role: PilotFeedbackIn["role"]): FeedbackDraft {
  return { role, ease: 0, trust: 0, would_use: "", hardest: "", minutes: null, region: "", comment: "", contact: "",
    consent_contact: false, source: "web" };
}

export function missingFields(f: FeedbackDraft): Missing[] {
  const m: Missing[] = [];
  if (!f.ease) m.push("ease");
  if (!f.trust) m.push("trust");
  if (!f.would_use) m.push("would_use");
  if (!f.hardest) m.push("hardest");
  if (f.contact.trim() !== "" && !f.consent_contact) m.push("consent");
  return m;
}

/** Phiếu đã đủ → kiểu gửi đi được (hết chuỗi rỗng). Thiếu thì trả null — KHÔNG điền hộ giá trị nào. */
export function toSubmit(f: FeedbackDraft): PilotFeedbackIn | null {
  if (missingFields(f).length) return null;
  return { ...f, would_use: f.would_use as PilotFeedbackIn["would_use"], hardest: f.hardest as PilotFeedbackIn["hardest"],
    contact: f.consent_contact ? f.contact : "" };
}

// trustLabel: /thi-diem hỏi "tin kết quả sàng lọc", /dung-thu hỏi "khớp ngoài đời" — cùng trường `trust`.
export function missingMessage(m: Missing[], t: (vi: string, en: string) => string,
                               trustLabel: [string, string] = ["\"khớp ngoài đời\"", "\"matches the ground\""]): string {
  if (!m.length) return "";
  if (m.length === 1 && m[0] === "consent")
    return t("Có ghi liên hệ thì đánh dấu đồng ý, hoặc xoá ô liên hệ.", "Tick consent, or clear the contact field.");
  const names: Record<Exclude<Missing, "consent">, [string, string]> = {
    ease: ["\"dễ dùng\"", "\"easy to use\""],
    trust: trustLabel,
    would_use: ["\"có dùng không\"", "\"would you use it\""],
    hardest: ["\"chỗ khó nhất\"", "\"hardest part\""],
  };
  const q = m.filter((x): x is Exclude<Missing, "consent"> => x !== "consent");
  return t(`Còn thiếu câu: ${q.map((x) => names[x][0]).join(", ")}.`, `Still to answer: ${q.map((x) => names[x][1]).join(", ")}.`)
    + (m.includes("consent") ? " " + t("Có ghi liên hệ thì đánh dấu đồng ý, hoặc xoá ô liên hệ.", "Tick consent, or clear the contact field.") : "");
}
