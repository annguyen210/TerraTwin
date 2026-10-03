"use client";

/**
 * GIẤY CHỨNG NHẬN QUYỀN SỬ DỤNG ĐẤT — phần "hợp pháp" của EUDR.
 * Chụp sổ: có khoá AI thì máy tự đọc các trường; không có thì nhập tay — phần đối chiếu
 * (diện tích ↔ ranh đo, mục đích sử dụng, thời hạn, tên chủ) chạy y hệt. Ảnh KHÔNG lưu:
 * chỉ SHA-256 của ảnh đi vào hồ sơ.
 */

import { useState } from "react";
import { Camera, FileSearch } from "lucide-react";
import { landdocCheck, landdocExtract, type LandDocCheck, type LandDocFields, type LandDocInput } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const CODES: [string, string][] = [
  ["CLN", "Đất trồng cây lâu năm"], ["LUC", "Đất chuyên trồng lúa nước"], ["BHK", "Đất bằng trồng cây hàng năm khác"],
  ["NHK", "Đất nương rẫy trồng cây hàng năm khác"], ["NTS", "Đất nuôi trồng thuỷ sản"], ["RSX", "Đất rừng sản xuất"],
  ["RPH", "Đất rừng phòng hộ"], ["RDD", "Đất rừng đặc dụng"], ["ONT", "Đất ở tại nông thôn"],
];

export default function LandDocForm({ areaHa, producer, onChange }: {
  areaHa: number | null; producer: string; onChange: (v: LandDocInput | null) => void;
}) {
  const { t } = useLang();
  const [f, setF] = useState<LandDocFields>({});
  const [sha, setSha] = useState<string | null>(null);
  const [source, setSource] = useState("manual");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [chk, setChk] = useState<LandDocCheck | null>(null);

  const set = (k: keyof LandDocFields, v: string) => { const n = { ...f, [k]: v || null }; setF(n); setChk(null); onChange(null); };

  async function read(file: File | undefined) {
    if (!file) return;
    setBusy(true); setMsg(null);
    try {
      const r = await landdocExtract(file);
      setF(r.fields); setSha(r.image_sha256); setSource(r.source);
      setMsg(t("AI đã đọc xong — KIỂM LẠI từng trường với sổ trước khi đối chiếu.", "The AI has read it — CHECK every field against the certificate before cross-checking."));
    } catch (e) {
      const err = e as Error & { imageSha256?: string };
      if (err.imageSha256) setSha(err.imageSha256);
      setMsg(`${err.message} ${t("Bạn vẫn nhập tay được bên dưới.", "You can still type it in below.")}`);
    } finally { setBusy(false); }
  }

  async function check() {
    setBusy(true); setMsg(null);
    try {
      const r = await landdocCheck(f, areaHa, producer);
      setChk(r);
      onChange({ fields: f, image_sha256: sha, source });
    } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="eu-landdoc">
      <div className="bat-row">
        <label className="bat-btn ghost">
          <Camera size={15} aria-hidden="true" className="ui-ic" /> {busy ? t("Đang đọc…", "Reading…") : t("Chụp / chọn ảnh sổ (AI đọc)", "Photo of the certificate (AI reads it)")}
          <input type="file" hidden accept="image/jpeg,image/png,image/webp" capture="environment" onChange={(e) => read(e.target.files?.[0])} />
        </label>
        <small>{t("Cần đăng nhập và khoá AI trên máy chủ. Ảnh không lưu, chỉ lưu mã băm.", "Needs sign-in and an AI key on the server. The photo is not stored, only its hash.")}</small>
      </div>
      {msg && <p className="doc-note">{msg}</p>}
      <div className="eu-fields">
        <label>{t("Thửa đất số", "Parcel no.")}<input className="bat-input" value={f.so_thua ?? ""} onChange={(e) => set("so_thua", e.target.value)} /></label>
        <label>{t("Tờ bản đồ số", "Map sheet no.")}<input className="bat-input" value={f.to_ban_do ?? ""} onChange={(e) => set("to_ban_do", e.target.value)} /></label>
        <label>{t("Diện tích (m²)", "Area (m²)")}<input className="bat-input" inputMode="decimal" value={f.dien_tich_m2 ?? ""} onChange={(e) => set("dien_tich_m2", e.target.value)} /></label>
        <label>{t("Mục đích sử dụng", "Land use")}
          <select className="bat-input" value={f.ma_muc_dich ?? ""} onChange={(e) => set("ma_muc_dich", e.target.value)}>
            <option value="">{t("— chọn ký hiệu —", "— choose code —")}</option>
            {CODES.map(([c, n]) => <option key={c} value={c}>{c} · {n}</option>)}
          </select>
        </label>
        <label>{t("Thời hạn (YYYY-MM-DD hoặc “lâu dài”)", "Term (YYYY-MM-DD or “lâu dài”)")}<input className="bat-input" value={f.thoi_han ?? ""} onChange={(e) => set("thoi_han", e.target.value)} /></label>
        <label>{t("Tên người sử dụng đất", "Holder name")}<input className="bat-input" value={f.ten_chu ?? ""} onChange={(e) => set("ten_chu", e.target.value)} /></label>
      </div>
      <div className="bat-row">
        <button className="bat-btn ghost" disabled={busy || !(f.dien_tich_m2 || f.ma_muc_dich)} onClick={check}>
          <FileSearch size={15} aria-hidden="true" className="ui-ic" /> {t("Đối chiếu với ranh đo", "Cross-check with the boundary")}
        </button>
        {chk && <span className={`eu-badge ${chk.verdict === "ok" ? "eu-low" : chk.verdict === "review" ? "eu-review" : "eu-high"}`}>{chk.label}</span>}
      </div>
      {chk && (
        <ul className="eu-checks">
          {chk.checks.map((c) => <li key={c.id} className={c.ok === true ? "ok" : c.ok === false ? "bad" : "unk"}>{c.ok === true ? "✓" : c.ok === false ? "✗" : "?"} {c.label}</li>)}
        </ul>
      )}
      {chk && <p className="eu-src">{t("Đã đối chiếu — sẽ đi kèm hồ sơ khi phát hành (máy chủ đối chiếu lại, tên chủ được ẩn bằng cam kết băm).",
        "Cross-checked — it will be attached when issuing (the server re-checks; the holder name is hidden behind a hash commitment).")}</p>}
    </div>
  );
}
