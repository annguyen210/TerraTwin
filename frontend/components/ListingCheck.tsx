"use client";

/**
 * KIỂM CHỨNG TIN ĐĂNG (GĐ3 kế hoạch tổng) — dán nội dung tin đăng bán đất, từng câu khẳng định được đặt cạnh
 * số đo của thửa: Khớp / Mâu thuẫn / Không đủ dữ liệu. Chỉ nhận chữ người dùng tự dán; không lưu nội dung.
 */
import { useState } from "react";
import { FileSearch } from "lucide-react";
import { issueDossier, listingCheck, type ListingCheckResult } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const V: Record<string, { cls: string; vi: string; en: string }> = {
  consistent: { cls: "lc-ok", vi: "Khớp", en: "Consistent" },
  contradicted: { cls: "lc-bad", vi: "Mâu thuẫn", en: "Contradicted" },
  insufficient: { cls: "lc-na", vi: "Không đủ dữ liệu", en: "Not enough data" },
};

export default function ListingCheck({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [text, setText] = useState("");
  const [r, setR] = useState<ListingCheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [issuing, setIssuing] = useState(false);

  async function toDossier() {
    // GĐ3 — phát hành Hồ sơ đất số kèm kết quả đối chiếu (máy chủ chạy lại; nguyên văn tin không được lưu).
    setIssuing(true); setErr(null);
    try {
      const d = await issueDossier(lat, lon, null, [], text);
      window.location.href = `/h/${d.id}?moi=1`;
    } catch (e) { setErr((e as Error).message); setIssuing(false); }
  }

  async function run() {
    setBusy(true); setErr(null);
    try { setR(await listingCheck(text, lat, lon)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <section className="lc">
      <div className="wh-head">
        <FileSearch size={18} aria-hidden="true" />
        <h3>{t("Kiểm chứng tin đăng bán đất", "Check a land listing")}</h3>
      </div>
      <label className="pk-field">{t("Dán nội dung tin đăng (vd \"đất cao ráo, không bao giờ ngập, gần sông\")",
                                     "Paste the listing text (e.g. \"high ground, never floods, near the river\")")}
        <textarea rows={4} maxLength={5000} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="gn-actions">
        <button className="bat-btn" onClick={run} disabled={busy || text.trim().length < 3}>
          {busy ? t("Đang đối chiếu…", "Checking…") : t("Đối chiếu với số đo", "Compare with measurements")}</button>
      </div>
      {err && <p className="bat-err">{err}</p>}
      {r && (r.claims.length === 0 ? (
        <p className="doc-note">{t("Không thấy câu khẳng định nào kiểm được (ngập, cao ráo, gần sông/biển, bằng phẳng, sạt lở, thổ cư, nước ngọt).",
                                   "No checkable claims found (flooding, high ground, near river/sea, flat, landslides, residential, fresh water).")}</p>
      ) : (
        <>
          <p className="wh-sum">{t(`${r.counts.contradicted || 0} mâu thuẫn · ${r.counts.consistent || 0} khớp · ${r.counts.insufficient || 0} không đủ dữ liệu`,
                                   `${r.counts.contradicted || 0} contradicted · ${r.counts.consistent || 0} consistent · ${r.counts.insufficient || 0} not enough data`)}</p>
          <ul className="lc-list">
            {r.claims.map((c, i) => (
              <li key={i} className={V[c.verdict].cls}>
                <div><span className="lc-tag">{t(V[c.verdict].vi, V[c.verdict].en)}</span><b>{c.label}</b> — <q>{c.sentence}</q></div>
                <p>{t("Dữ liệu ghi nhận", "The data shows")}: {c.evidence}{c.source ? ` (${c.source})` : ""}</p>
              </li>
            ))}
          </ul>
          <p className="eu-src">{r.note}</p>
          <div className="gn-actions">
            <button className="bat-btn ghost" onClick={toDossier} disabled={issuing}>
              {issuing ? t("Đang phát hành…", "Issuing…") : t("Đưa kết quả vào Hồ sơ đất số ký số", "Add the result to a signed land dossier")}</button>
          </div>
        </>
      ))}
    </section>
  );
}
