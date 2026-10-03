"use client";

/**
 * CHỨNG THƯ LÔ HÀNG trên trang /h/<mã>: gốc Merkle của các hồ sơ vườn trong lô, tổng
 * khối lượng, kết quả cân bằng khối lượng. Danh sách nhà cung cấp KHÔNG công khai —
 * thay vào đó ai biết mã một vườn thì kiểm được vườn đó có thuộc lô không, ngay trong
 * trình duyệt (đường kiểm toán Merkle, RFC 9162).
 */

import { useState } from "react";
import { lotProof, type LotCertificateFacts, type LotProof } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { leafHash, verifyInclusion } from "@/lib/verify";

export default function LotCertificateView({ f, certId }: { f: LotCertificateFacts; certId: string }) {
  const { t } = useLang();
  const [did, setDid] = useState("");
  const [res, setRes] = useState<{ ok: boolean; p?: LotProof; msg: string } | null>(null);
  const L = f.lot;

  async function check() {
    setRes(null);
    try {
      const p = await lotProof(certId, did.trim());
      const lh = Array.from(await leafHash(new TextEncoder().encode(p.leaf_data))).map((b) => b.toString(16).padStart(2, "0")).join("");
      const inPath = await verifyInclusion(lh, p.leaf_index, p.tree_size, p.proof, p.root);
      const ok = inPath && p.root === f.merkle.root;
      setRes({ ok, p, msg: ok
        ? t(`Vườn ${p.leaf.dossier_id} THUỘC lô này với ${p.leaf.kg.toLocaleString("vi-VN")} kg — trình duyệt đã tự kiểm ${p.proof.length} mã băm tới gốc đã ký.`,
            `Plot ${p.leaf.dossier_id} IS in this lot with ${p.leaf.kg.toLocaleString("en-GB")} kg — your browser checked ${p.proof.length} hashes up to the signed root.`)
        : t("Bằng chứng KHÔNG dẫn tới gốc trong chứng thư đã ký.", "The proof does NOT lead to the root in the signed certificate.") });
    } catch (e) {
      setRes({ ok: false, msg: (e as Error).message });
    }
  }

  function downloadProof() {
    if (!res?.p) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(res.p, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url; a.download = `terratwin-bang-chung-${res.p.leaf.dossier_id}.json`; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="dos-grid">
        <section>
          <h2>{t("Lô hàng", "Lot")}</h2>
          <ul className="dos-list">
            <li><span>{t("Mã lô", "Lot ref")}</span><b>{L.ref || "—"}</b></li>
            <li><span>{t("Nông sản", "Commodity")}</span><b>{L.commodity_label} · HS {L.hs_code}</b></li>
            <li><span>{t("Vụ", "Season")}</span><b>{L.season || "—"}</b></li>
            <li><span>{t("Doanh nghiệp", "Operator")}</span><b>{L.operator || "—"}</b></li>
            <li><span>{t("Khối lượng", "Quantity")}</span><b>{L.quantity_kg.toLocaleString("vi-VN")} kg</b></li>
            <li><span>{t("Số vườn · diện tích", "Plots · area")}</span><b>{L.n_plots} · {L.area_ha} ha</b></li>
            <li><span>{t("Quốc gia sản xuất", "Country of production")}</span><b>{L.country_of_production}</b></li>
          </ul>
        </section>
        <section>
          <h2>{t("Cây Merkle", "Merkle tree")} <span className="eu-class">{t("TÍNH LẠI ĐƯỢC", "RECOMPUTABLE")}</span></h2>
          <p className="dos-note"><code className="eu-hash">{f.merkle.root}</code></p>
          <p className="dos-src">{f.merkle.algorithm} · {f.merkle.size} {t("lá", "leaves")} · {f.merkle.leaf}</p>
          <p className="dos-src">{t("Cân bằng khối lượng:", "Mass balance:")} {f.mass_balance.rule}
            {f.mass_balance.yield_cap_t_ha ? ` (${f.mass_balance.yield_cap_t_ha} t/ha)` : ""}</p>
          <p className="dos-src">{t("Kết quả sàng lọc các vườn:", "Plot screening results:")} {Object.entries(f.checks.by_level).map(([k, v]) => `${k} ${v}`).join(" · ")}
            {f.checks.n_warning ? ` · ${f.checks.n_warning} ${t("vườn có ghi chú xem xét", "plots with a review note")}` : ""}</p>
        </section>
      </div>
      <section className="dos-noprint">
        <h2>{t("Kiểm một vườn có thuộc lô này không", "Check whether a plot is in this lot")}</h2>
        <p className="dos-src">{t("Danh sách nhà cung cấp không công khai. Nhập mã hồ sơ vườn (in trên hồ sơ của nông hộ): trình duyệt tự kiểm đường kiểm toán Merkle tới gốc đã ký ở trên.",
          "The supplier list is not public. Enter a plot dossier ID (printed on the farmer's dossier): your browser checks the Merkle audit path up to the signed root above.")}</p>
        <div className="bat-row">
          <input className="bat-input" id="lot-check-did" value={did} onChange={(e) => setDid(e.target.value)} placeholder={t("Mã hồ sơ vườn, vd 3scihq2x5sk6", "Plot dossier ID, e.g. 3scihq2x5sk6")} maxLength={16} />
          <button className="bat-btn" disabled={did.trim().length < 6} onClick={check}>{t("Kiểm", "Check")}</button>
          {res?.ok && <button className="bat-btn ghost" onClick={downloadProof}>{t("Tải bằng chứng (.json)", "Download proof (.json)")}</button>}
        </div>
        {res && <p className={`dos-verify-inline ${res.ok ? "ok" : "bad"}`}>{res.ok ? "✓" : "✗"} {res.msg}</p>}
      </section>
      <section>
        <p className="dos-disclaimer">{f.disclaimer}</p>
      </section>
    </>
  );
}
