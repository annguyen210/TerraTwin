"use client";

/**
 * DÙNG THỬ 10 PHÚT — người ĐỊNH MUA đất và môi giới (30/10/2026).
 *
 * Câu giám khảo hỏi đầu tiên là "ai đang dùng?". Trang này là chỗ đo: ba việc thử theo đúng luồng "kiểm lời rao trước khi
 * xuống tiền" ở trang đầu, rồi phiếu 2 phút gửi vào cùng bảng góp ý thí điểm (/api/pilot/feedback, role buyer|broker) —
 * quản trị viên xem ở /admin → Góp ý thí điểm. Lời mời gửi kèm link này: docs/MOI_DUNG_THU.md.
 */
import { useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { sendPilotFeedback, type PilotFeedbackIn } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const BLANK: PilotFeedbackIn = { role: "buyer", ease: 0, trust: 0, would_use: "yes", hardest: "none",
  minutes: null, region: "", comment: "", contact: "", consent_contact: false, source: "web" };

export default function TryPage() {
  const { t } = useLang();
  const [f, setF] = useState<PilotFeedbackIn>(BLANK);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const set = <K extends keyof PilotFeedbackIn>(k: K, v: PilotFeedbackIn[K]) => setF((x) => ({ ...x, [k]: v }));

  const missing = !f.ease || !f.trust || (f.contact.trim() !== "" && !f.consent_contact);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (missing) return;
    setBusy(true); setMsg(null);
    try {
      const r = await sendPilotFeedback({ ...f, contact: f.consent_contact ? f.contact : "" });
      setMsg({ ok: true, text: r.message });
      setF(BLANK);
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const roles: [PilotFeedbackIn["role"], string][] = [["buyer", t("Tôi đang tìm mua / vừa mua đất", "I'm buying / just bought land")],
    ["broker", t("Môi giới đất", "Land broker")], ["other", t("Khác", "Other")]];
  const steps: [PilotFeedbackIn["hardest"], string][] = [["listing", t("Kiểm tin đăng", "Checking the listing")],
    ["water", t("Đọc lịch sử nước của thửa", "Reading the plot's water history")], ["none", t("Không bước nào", "None")]];

  return (
    <AppShell>
      <main className="doc-body" style={{ maxWidth: 680 }}>
        <div className="pp-badge">{t("DÙNG THỬ 10 PHÚT", "10-MINUTE TRIAL")}</div>
        <h1>{t("Thử kiểm một mảnh đất trước khi xuống tiền", "Try checking a plot before you pay")}</h1>
        <p className="doc-lede">{t(
          "Làm ba việc dưới đây, rồi điền phiếu 2 phút ở cuối trang. Góp ý thật — kể cả \"không dùng được\" — giúp chúng tôi sửa đúng chỗ.",
          "Do the three things below, then fill in the 2-minute form at the end. Honest feedback — including \"it didn't work for me\" — tells us what to fix.")}</p>
        <p className="doc-note">{t(
          "Lần đầu mở trong ngày có thể phải chờ khoảng 1 phút vì máy chủ miễn phí đang ngủ.",
          "The first visit of the day may take about a minute while the free server wakes up.")}</p>

        <section className="bat-card">
          <h2>{t("Ba việc thử", "Three things to try")}</h2>
          <ol>
            <li><b>{t("Tin rao mẫu (2 phút).", "Sample listing (2 min).")}</b>{" "}
              {t("Mở ", "Open the ")}<Link href="/">{t("trang đầu", "home page")}</Link>
              {t(", bấm \"Kiểm một tin đăng mẫu — ruộng ngập bão Yagi\". Xem câu nào trong tin bị tô đỏ, và vì sao.",
                 ", tap \"Check a sample listing — a field flooded by Typhoon Yagi\". See which claims turn red, and why.")}</li>
            <li><b>{t("Một tin rao thật (3 phút).", "A real listing (3 min).")}</b>{" "}
              {t("Lấy một tin bán đất bạn từng thấy (Zalo, Facebook, tờ rơi), mở đúng vị trí mảnh đất đó ở ",
                 "Take a land listing you've seen (Zalo, Facebook, a flyer), open that plot's location at ")}
              <Link href="/buyer">{t("Kiểm trước khi mua", "Check before buying")}</Link>
              {t(", rồi dán chữ của tin vào ô kiểm tin đăng.", ", then paste the listing's text into the listing check.")}</li>
            <li><b>{t("Một mảnh đất bạn biết rõ (3 phút).", "A plot you know well (3 min).")}</b>{" "}
              {t("Nhà, ruộng, quê của bạn: lịch sử nước TerraTwin đưa ra có khớp với điều bạn đã thấy ngoài đời không?",
                 "Your home, field or village: does TerraTwin's water history match what you've actually seen?")}</li>
          </ol>
        </section>

        <section className="bat-card pk-online">
          <h2>{t("Phiếu góp ý 2 phút", "2-minute feedback form")}</h2>
          <form onSubmit={submit} className="pk-formgrid">
            <fieldset><legend>{t("Bạn là", "You are")}</legend>
              {roles.map(([k, l]) => <label key={k}><input type="radio" name="role" checked={f.role === k} onChange={() => set("role", k)} /> {l}</label>)}
            </fieldset>
            <fieldset><legend>{t("Dễ dùng không? (1 rất khó · 5 rất dễ)", "Easy to use? (1 very hard · 5 very easy)")}</legend>
              {[1, 2, 3, 4, 5].map((n) => <label key={n} className="pk-num"><input type="radio" name="ease" checked={f.ease === n} onChange={() => set("ease", n)} /> {n}</label>)}
            </fieldset>
            <fieldset><legend>{t("Kết quả có khớp điều bạn biết ngoài đời không? (1 sai hẳn · 5 đúng hẳn)", "Did the result match what you know on the ground? (1 completely wrong · 5 exactly right)")}</legend>
              {[1, 2, 3, 4, 5].map((n) => <label key={n} className="pk-num"><input type="radio" name="trust" checked={f.trust === n} onChange={() => set("trust", n)} /> {n}</label>)}
            </fieldset>
            <fieldset><legend>{t("Lần tới định đặt cọc một mảnh đất, bạn có kiểm bằng TerraTwin trước không?", "Next time you're about to put down a deposit, would you check with TerraTwin first?")}</legend>
              {([["yes", t("Có", "Yes")], ["maybe", t("Có thể", "Maybe")], ["no", t("Không", "No")]] as [PilotFeedbackIn["would_use"], string][]).map(([k, l]) =>
                <label key={k}><input type="radio" name="would" checked={f.would_use === k} onChange={() => set("would_use", k)} /> {l}</label>)}
            </fieldset>
            <fieldset><legend>{t("Chỗ khó hiểu hoặc khó dùng nhất", "The hardest or most confusing part")}</legend>
              {steps.map(([k, l]) => <label key={k}><input type="radio" name="hardest" checked={f.hardest === k} onChange={() => set("hardest", k)} /> {l}</label>)}
            </fieldset>
            <label className="pk-field">{t("Điều cần sửa nhất — hoặc bạn sẵn lòng trả bao nhiêu cho một lần kiểm (không bắt buộc)",
                                          "What most needs fixing — or what you'd pay for one check (optional)")}
              <textarea maxLength={2000} rows={4} value={f.comment} onChange={(e) => set("comment", e.target.value)} />
            </label>
            <label className="pk-field">{t("Tỉnh, thành (không bắt buộc)", "Province (optional)")}
              <input type="text" maxLength={80} value={f.region} onChange={(e) => set("region", e.target.value)} />
            </label>
            <label className="pk-field">{t("Số điện thoại hoặc email nếu muốn được liên hệ lại (không bắt buộc)", "Phone or email if you want us to follow up (optional)")}
              <input type="text" maxLength={120} value={f.contact} onChange={(e) => set("contact", e.target.value)} />
            </label>
            <label className="pk-consent"><input type="checkbox" checked={f.consent_contact} onChange={(e) => set("consent_contact", e.target.checked)} />{" "}
              {t("Tôi đồng ý để TerraTwin liên hệ lại về góp ý này. Không đánh dấu thì thông tin liên hệ không được lưu.",
                 "I agree that TerraTwin may contact me about this feedback. If unticked, contact details are not stored.")}</label>
            {missing && <p className="doc-note">{!f.ease || !f.trust
              ? t("Chọn điểm cho hai câu \"dễ dùng\" và \"khớp ngoài đời\".", "Pick a score for \"easy to use\" and \"matches the ground\".")
              : t("Có ghi liên hệ thì đánh dấu đồng ý, hoặc xoá ô liên hệ.", "Tick consent, or clear the contact field.")}</p>}
            <button className="doc-btn" type="submit" disabled={busy || missing}>{busy ? t("Đang gửi…", "Sending…") : t("Gửi góp ý", "Send feedback")}</button>
            {msg && <p className={msg.ok ? "eu-ok-line" : "bat-err"} role="status">{msg.text}</p>}
          </form>
        </section>
        <p className="doc-note">{t("Không cần tài khoản. Phiếu không lưu địa chỉ IP; chỉ quản trị viên xem tổng hợp.",
                                   "No account needed. The form stores no IP address; only administrators see the summary.")}</p>
      </main>
    </AppShell>
  );
}
