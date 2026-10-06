"use client";

/**
 * BỘ THÍ ĐIỂM cho hợp tác xã — tờ hướng dẫn in được (nông hộ, cán bộ HTX/doanh nghiệp),
 * phiếu góp ý giấy, và phiếu góp ý trực tuyến (POST /api/pilot/feedback).
 *
 * Tờ in dùng ĐÚNG nhãn nút đang có trong ứng dụng, để người cầm giấy nhìn thấy đúng chữ
 * trên màn hình. Đổi nhãn ở trang EUDR thì sửa cả ở đây.
 */

import AppShell from "@/components/AppShell";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken, sendPilotFeedback, type PilotFeedbackIn } from "@/lib/api";
import { useLang } from "@/lib/i18n";

type Sheet = "all" | "farmer" | "staff" | "form";

const SITE = "terratwin-web.onrender.com";

export default function PilotKitPage() {
  const { t } = useLang();
  const [only, setOnly] = useState<Sheet>("all");

  const print = (s: Sheet) => {
    setOnly(s);
    // Chờ React vẽ lại (ẩn các tờ không in) rồi mới mở hộp thoại in.
    setTimeout(() => { window.print(); setOnly("all"); }, 60);
  };

  return (
    <AppShell>
      <main className="doc-body pk-wrap" data-print={only}>
        <div className="pk-noprint">
          <h1>{t("Bộ thí điểm cho hợp tác xã", "Pilot kit for co-operatives")}</h1>
          <p className="doc-lede">{t(
            "Ba tờ in khổ A4 cho một buổi tập huấn: tờ cho nông hộ, tờ cho cán bộ HTX và đơn vị xuất khẩu, phiếu góp ý giấy. Phiếu góp ý trực tuyến ở cuối trang.",
            "Three A4 sheets for one training session: a farmer sheet, a sheet for co-op staff and exporters, and a paper feedback form. The online feedback form is at the bottom.")}</p>
          <div className="pk-actions">
            <button className="doc-btn" onClick={() => print("farmer")}>{t("In tờ nông hộ", "Print farmer sheet")}</button>
            <button className="doc-btn pk-btn2" onClick={() => print("staff")}>{t("In tờ cán bộ", "Print staff sheet")}</button>
            <button className="doc-btn pk-btn2" onClick={() => print("form")}>{t("In phiếu góp ý", "Print feedback form")}</button>
            <button className="doc-btn pk-btn2" onClick={() => print("all")}>{t("In cả bộ", "Print all")}</button>
          </div>
          <p className="doc-note">{t(
            "Tờ in bằng tiếng Việt vì dùng ở buổi tập huấn trong nước. Khi in, chọn khổ A4, tắt \"đầu trang và chân trang\".",
            "Sheets are in Vietnamese for local sessions. When printing, choose A4 and turn off \"headers and footers\".")}</p>
        </div>

        <FarmerSheet />
        <StaffSheet />
        <PaperForm />

        <div className="pk-noprint">
          <OnlineForm />
          <footer className="doc-foot">
            <Link href="/help">{t("Trợ giúp", "Help")}</Link>
            <span>·</span>
            <Link href="/eudr">EUDR</Link>
            <span>·</span>
            <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link>
          </footer>
        </div>
      </main>
    </AppShell>
  );
}

function Box({ n }: { n?: number }) {
  return <span className="pk-box" aria-hidden="true">{n ?? ""}</span>;
}

function FarmerSheet() {
  return (
    <section className="pk-sheet pk-farmer" lang="vi">
      <p className="pk-kicker">TerraTwin · Tờ cho nông hộ</p>
      <h2>Làm hồ sơ vườn để bán cà phê, cao su cho đại lý xuất sang châu Âu</h2>
      <p className="pk-lead">Từ 30/12/2026, người mua châu Âu cần biết vườn ở đâu và không phá rừng sau năm 2020. Làm một lần, dùng cho mọi đại lý. <b>Nông hộ không mất tiền.</b></p>
      <ol className="pk-steps">
        <li><Box /> Mở <b>{SITE}/eudr</b> trên điện thoại. Không cần cài ứng dụng, không cần tài khoản.</li>
        <li><Box /> Chọn <b>Một vườn</b> → <b>Đi bộ quanh vườn (GPS)</b>. Đi chậm sát mép vườn, về đúng chỗ bắt đầu. Mất sóng vẫn lưu trong máy.</li>
        <li><Box /> Bấm <b>Kiểm chuẩn EU + sàng lọc phá rừng</b>, chờ khoảng 1 phút. Kết quả là <b>Đạt sàng lọc</b>, <b>Cần xem lại</b> hoặc <b>Rủi ro phá rừng</b>.</li>
        <li><Box /> <b>Cần xem lại</b> không phải bị loại: cán bộ HTX sẽ cùng bạn xem ảnh vệ tinh và giấy tờ. Vườn cà phê có cây che bóng thường rơi vào đây.</li>
        <li><Box /> Bấm <b>Phát hành Hồ sơ vườn ký số</b>. Giữ <b>đường link đầy đủ</b>, chỉ đưa cho người bạn tin.</li>
        <li><Box /> Mở <b>Thẻ in A6</b>, in thẻ có mã QR, đưa cho đại lý khi bán hàng.</li>
        <li><Box /> Khi đại lý khai hàng từ vườn bạn: mở đường link đầy đủ, bấm <b>Xác nhận</b> đợt bạn thật sự đã bán, <b>Từ chối</b> đợt không đúng.</li>
      </ol>
      <div className="pk-note">
        <p><b>Cần nhớ</b></p>
        <ul>
          <li>Tên bạn không hiện công khai trên mã QR.</li>
          <li>Vườn dưới 4 ha vẫn nên đi ranh: kết quả sát hơn chỉ chấm một điểm.</li>
          <li>Sàng lọc không phải giấy chứng nhận. Ranh lệch 10–20 m là bình thường.</li>
        </ul>
      </div>
      <div className="pk-fill">
        <p>Mã hồ sơ: <span className="pk-line" /></p>
        <p>Ngày làm: <span className="pk-line pk-short" /> Cán bộ hỗ trợ: <span className="pk-line" /></p>
      </div>
    </section>
  );
}

function StaffSheet() {
  return (
    <section className="pk-sheet pk-staff" lang="vi">
      <p className="pk-kicker">TerraTwin · Tờ cho cán bộ HTX và đơn vị xuất khẩu</p>
      <h2>Chạy một buổi thí điểm: từ danh sách hộ tới lô hàng người mua tự kiểm được</h2>
      <p className="pk-sub">Trước buổi</p>
      <ul className="pk-list">
        <li>Lập danh sách hộ tham gia; dặn mang điện thoại đã bật định vị, sạc đầy pin.</li>
        <li>In đủ tờ nông hộ và phiếu góp ý. Mở trang web trước khoảng 2 phút: máy chủ miễn phí ngủ, dậy mất khoảng 1 phút.</li>
        <li>Đăng nhập tài khoản HTX để làm việc theo lô và nhập lại phiếu giấy.</li>
      </ul>
      <p className="pk-sub">Trong buổi</p>
      <ol className="pk-steps pk-steps-sm">
        <li><Box /> Hộ nào có tệp ranh sẵn: vào <b>EUDR → Cả lô (doanh nghiệp, HTX)</b>, tải GeoJSON, KML hoặc Excel, bấm <b>Sàng lọc phá rừng cả lô</b>. Hộ chưa có ranh: đi ranh theo tờ nông hộ.</li>
        <li><Box /> Với mỗi vườn <b>Cần xem lại</b>: xem ảnh trước và sau, gợi ý "rừng hay vườn cây", hỏi giấy tờ đất. Ghi lý do quyết định.</li>
        <li><Box /> Phát hành hồ sơ ký số cho từng vườn. Hồ sơ không xoá được, nên chỉ phát hành khi ranh đã đúng.</li>
        <li><Box /> Vào <b>{SITE}/lo</b>, ghép lô hàng từ các vườn đã có hồ sơ, nhập số kg. Lô vượt năng suất trần (cà phê 6 tấn/ha) sẽ bị chặn.</li>
        <li><Box /> Tải chứng thư lô, GeoJSON và nháp tờ khai DDS, gửi cho người mua.</li>
        <li><Box /> Người mua kiểm ở <b>{SITE}/kiem</b>: thả tệp chứng thư, trình duyệt tự kiểm, kể cả khi không có mạng.</li>
      </ol>
      <p className="pk-sub">Sau buổi: ghi lại để đo thí điểm</p>
      <table className="pk-table">
        <tbody>
          <tr><td>Số hộ tham gia</td><td><span className="pk-line pk-short" /></td><td>Số vườn Đạt sàng lọc</td><td><span className="pk-line pk-short" /></td></tr>
          <tr><td>Số phút trung bình mỗi hồ sơ</td><td><span className="pk-line pk-short" /></td><td>Số vườn Cần xem lại</td><td><span className="pk-line pk-short" /></td></tr>
          <tr><td>Số hồ sơ đại lý chấp nhận</td><td><span className="pk-line pk-short" /></td><td>Số phiếu góp ý thu được</td><td><span className="pk-line pk-short" /></td></tr>
        </tbody>
      </table>
      <p className="pk-small">Nhập lại phiếu góp ý giấy tại {SITE}/thi-diem, chọn "Phiếu giấy" (cần đăng nhập). Dữ liệu cá nhân: chỉ ghi cách liên hệ khi người đó đồng ý.</p>
    </section>
  );
}

function Scale() {
  return <span className="pk-scale">{[1, 2, 3, 4, 5].map((n) => <Box key={n} n={n} />)}</span>;
}

function PaperForm() {
  return (
    <section className="pk-sheet pk-form" lang="vi">
      <p className="pk-kicker">TerraTwin · Phiếu góp ý thí điểm</p>
      <h2>Bạn thấy công cụ làm hồ sơ vườn thế nào?</h2>
      <p className="pk-small">Không cần ghi tên. Khoanh hoặc đánh dấu vào ô.</p>
      <div className="pk-q"><p>1. Bạn là:</p><p><Box /> Nông hộ <Box /> Cán bộ HTX <Box /> Đơn vị xuất khẩu <Box /> Khác</p></div>
      <div className="pk-q"><p>2. Huyện, tỉnh (không bắt buộc): <span className="pk-line" /></p></div>
      <div className="pk-q"><p>3. Dễ dùng không? (1 = rất khó, 5 = rất dễ)</p><Scale /></div>
      <div className="pk-q"><p>4. Bạn tin kết quả sàng lọc không? (1 = không tin, 5 = rất tin)</p><Scale /></div>
      <div className="pk-q"><p>5. Làm xong một hồ sơ mất khoảng bao nhiêu phút? <span className="pk-line pk-short" /></p></div>
      <div className="pk-q"><p>6. Bước nào khó nhất?</p><p><Box /> Đi ranh <Box /> Sàng lọc <Box /> Phát hành hồ sơ <Box /> Ghép lô <Box /> Kiểm hồ sơ <Box /> Không bước nào</p></div>
      <div className="pk-q"><p>7. Bạn có dùng tiếp không?</p><p><Box /> Có <Box /> Có thể <Box /> Không</p></div>
      <div className="pk-q"><p>8. Điều cần sửa nhất:</p><span className="pk-line pk-full" /><span className="pk-line pk-full" /><span className="pk-line pk-full" /></div>
      <div className="pk-q"><p>9. Nếu muốn được liên hệ lại, ghi số điện thoại: <span className="pk-line" /></p>
        <p><Box /> Tôi đồng ý để TerraTwin liên hệ lại về góp ý này. Không đánh dấu thì cán bộ không nhập số điện thoại.</p></div>
    </section>
  );
}

function OnlineForm() {
  const { t } = useLang();
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => { setSignedIn(!!getToken()); }, []);   // đọc sau khi gắn để khỏi lệch lúc hydrate
  const blank: PilotFeedbackIn = { role: "farmer", ease: 0, trust: 0, would_use: "yes", hardest: "none",
    minutes: null, region: "", comment: "", contact: "", consent_contact: false, source: "web" };
  const [f, setF] = useState<PilotFeedbackIn>(blank);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const set = <K extends keyof PilotFeedbackIn>(k: K, v: PilotFeedbackIn[K]) => setF((x) => ({ ...x, [k]: v }));

  const missing = !f.ease || !f.trust || (f.contact.trim() !== "" && !f.consent_contact);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (missing) return;
    setBusy(true); setMsg(null);
    try {
      const r = await sendPilotFeedback({ ...f, contact: f.consent_contact ? f.contact : "" });
      setMsg({ ok: true, text: r.message });
      setF({ ...blank, source: f.source, role: f.role, region: f.region });   // nhập phiếu giấy tiếp cho nhanh
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const roles: [PilotFeedbackIn["role"], string][] = [["farmer", t("Nông hộ", "Farmer")], ["coop", t("Cán bộ HTX", "Co-op staff")],
    ["exporter", t("Đơn vị xuất khẩu", "Exporter")], ["other", t("Khác", "Other")]];
  const steps: [PilotFeedbackIn["hardest"], string][] = [["boundary", t("Đi ranh", "Boundary")], ["screen", t("Sàng lọc", "Screening")],
    ["dossier", t("Phát hành hồ sơ", "Issuing")], ["lot", t("Ghép lô", "Lots")], ["verify", t("Kiểm hồ sơ", "Verifying")], ["none", t("Không bước nào", "None")]];

  return (
    <section className="bat-card pk-online">
      <h2>{t("Gửi góp ý trực tuyến", "Send feedback online")}</h2>
      <form onSubmit={submit} className="pk-formgrid">
        {signedIn && (
          <fieldset><legend>{t("Nguồn phiếu", "Source")}</legend>
            <label><input type="radio" checked={f.source === "web"} onChange={() => set("source", "web")} /> {t("Tôi tự góp ý", "My own feedback")}</label>
            <label><input type="radio" checked={f.source === "paper"} onChange={() => set("source", "paper")} /> {t("Nhập lại phiếu giấy", "Entering a paper form")}</label>
          </fieldset>
        )}
        <fieldset><legend>{t("Bạn là", "You are")}</legend>
          {roles.map(([k, l]) => <label key={k}><input type="radio" name="role" checked={f.role === k} onChange={() => set("role", k)} /> {l}</label>)}
        </fieldset>
        <fieldset><legend>{t("Dễ dùng không? (1 rất khó · 5 rất dễ)", "Easy to use? (1 very hard · 5 very easy)")}</legend>
          {[1, 2, 3, 4, 5].map((n) => <label key={n} className="pk-num"><input type="radio" name="ease" checked={f.ease === n} onChange={() => set("ease", n)} /> {n}</label>)}
        </fieldset>
        <fieldset><legend>{t("Tin kết quả sàng lọc không? (1 không tin · 5 rất tin)", "Trust the screening result? (1 not at all · 5 fully)")}</legend>
          {[1, 2, 3, 4, 5].map((n) => <label key={n} className="pk-num"><input type="radio" name="trust" checked={f.trust === n} onChange={() => set("trust", n)} /> {n}</label>)}
        </fieldset>
        <fieldset><legend>{t("Bước khó nhất", "Hardest step")}</legend>
          {steps.map(([k, l]) => <label key={k}><input type="radio" name="hardest" checked={f.hardest === k} onChange={() => set("hardest", k)} /> {l}</label>)}
        </fieldset>
        <fieldset><legend>{t("Có dùng tiếp không?", "Would you keep using it?")}</legend>
          {([["yes", t("Có", "Yes")], ["maybe", t("Có thể", "Maybe")], ["no", t("Không", "No")]] as [PilotFeedbackIn["would_use"], string][]).map(([k, l]) =>
            <label key={k}><input type="radio" name="would" checked={f.would_use === k} onChange={() => set("would_use", k)} /> {l}</label>)}
        </fieldset>
        <label className="pk-field">{t("Số phút làm xong một hồ sơ (không bắt buộc)", "Minutes to finish one dossier (optional)")}
          <input type="number" min={0} max={600} inputMode="numeric" value={f.minutes ?? ""}
            onChange={(e) => set("minutes", e.target.value === "" ? null : Math.max(0, Math.min(600, Number(e.target.value))))} />
        </label>
        <label className="pk-field">{t("Huyện, tỉnh (không bắt buộc)", "District, province (optional)")}
          <input type="text" maxLength={80} value={f.region} onChange={(e) => set("region", e.target.value)} />
        </label>
        <label className="pk-field">{t("Điều cần sửa nhất", "What most needs fixing")}
          <textarea maxLength={2000} rows={4} value={f.comment} onChange={(e) => set("comment", e.target.value)} />
        </label>
        <label className="pk-field">{t("Số điện thoại hoặc email nếu muốn được liên hệ lại (không bắt buộc)", "Phone or email if you want us to follow up (optional)")}
          <input type="text" maxLength={120} value={f.contact} onChange={(e) => set("contact", e.target.value)} />
        </label>
        <label className="pk-consent"><input type="checkbox" checked={f.consent_contact} onChange={(e) => set("consent_contact", e.target.checked)} />{" "}
          {t("Tôi đồng ý để TerraTwin liên hệ lại về góp ý này. Không đánh dấu thì thông tin liên hệ không được lưu.",
             "I agree that TerraTwin may contact me about this feedback. If unticked, contact details are not stored.")}</label>
        {missing && <p className="doc-note">{!f.ease || !f.trust
          ? t("Chọn điểm cho hai câu \"dễ dùng\" và \"tin kết quả\".", "Pick a score for \"easy to use\" and \"trust\".")
          : t("Có ghi liên hệ thì đánh dấu đồng ý, hoặc xoá ô liên hệ.", "Tick consent, or clear the contact field.")}</p>}
        <button className="doc-btn" type="submit" disabled={busy || missing}>{busy ? t("Đang gửi…", "Sending…") : t("Gửi góp ý", "Send feedback")}</button>
        {msg && <p className={msg.ok ? "eu-ok-line" : "bat-err"} role="status">{msg.text}</p>}
      </form>
    </section>
  );
}
