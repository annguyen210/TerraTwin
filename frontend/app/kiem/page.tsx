"use client";

/**
 * KIỂM OFFLINE — thả tệp hồ sơ (.json tải từ /h/<mã>) hoặc bằng chứng thuộc lô hàng vào
 * đây: trình duyệt TỰ kiểm bằng WebCrypto, không gửi tệp đi đâu, không cần máy chủ
 * TerraTwin còn sống. Đây là thứ cho nhà nhập khẩu EU, ngân hàng, kiểm toán viên.
 */

import { useState } from "react";
import Link from "next/link";
import { FileCheck2, ShieldCheck, Upload } from "lucide-react";
import AppShell from "@/components/AppShell";
import { useLang } from "@/lib/i18n";
import { leafHash, verifyDossierOffline, verifyInclusion, type CheckLine, type DossierFile } from "@/lib/verify";

type Result = { kind: "dossier" | "lot_proof"; title: string; lines: CheckLine[]; summary?: string };

export default function OfflineVerify() {
  const { t } = useLang();
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cert, setCert] = useState<DossierFile | null>(null);
  // Kiểm A–Z 24/11/2026: trang đầu hứa "Kiểm một hồ sơ — mã, QR hoặc tệp JSON" mà trang này chỉ nhận tệp. Dán mã hoặc
  // đường link (kể cả link đọc từ QR bằng camera điện thoại) → mở trang hồ sơ, giữ nguyên phần sau dấu # nếu có.
  const [code, setCode] = useState("");
  const [codeErr, setCodeErr] = useState<string | null>(null);
  function openCode() {
    const raw = code.trim();
    const m = raw.match(/\/h\/([A-Za-z0-9_-]{6,40})(\/the)?([?#].*)?$/) ?? raw.match(/^([A-Za-z0-9_-]{6,40})$/);
    if (!m) {
      setCodeErr(t("Không đọc được mã — dán mã hồ sơ (12 ký tự) hoặc cả đường link /h/…", "Can't read that — paste the dossier code (12 characters) or the whole /h/… link"));
      return;
    }
    setCodeErr(null);
    window.location.href = `/h/${m[1]}${m[3] ?? ""}`;
  }

  async function onFile(f: File | undefined) {
    setErr(null); setRes(null);
    if (!f) return;
    let doc: Record<string, unknown>;
    try { doc = JSON.parse(await f.text()); } catch { setErr(t("Tệp không phải JSON hợp lệ.", "The file is not valid JSON.")); return; }
    if (doc.proof && doc.facts) {
      const d = doc as unknown as DossierFile;
      const lines = await verifyDossierOffline(d, t);
      const facts = d.facts as { kind?: string; plot?: { ref?: string }; lot?: { ref?: string } };
      if (facts.kind === "lot_certificate") setCert(d);
      setRes({ kind: "dossier", lines,
        title: facts.kind === "eudr_plot" ? t(`Hồ sơ vườn EUDR · ${facts.plot?.ref ?? d.id}`, `EUDR plot dossier · ${facts.plot?.ref ?? d.id}`)
          : facts.kind === "lot_certificate" ? t(`Chứng thư lô hàng · ${facts.lot?.ref || d.id}`, `Lot certificate · ${facts.lot?.ref || d.id}`)
            : t(`Hồ sơ đất số · ${d.id}`, `Land dossier · ${d.id}`) });
      return;
    }
    if (doc.leaf_data && doc.proof && doc.root) {
      const p = doc as unknown as { leaf_data: string; leaf: { dossier_id: string; entry_hash: string; kg: number };
                                     leaf_index: number; tree_size: number; root: string; proof: string[]; lot_certificate: string };
      const lines: CheckLine[] = [];
      let parsed: { dossier_id?: string; entry_hash?: string; kg?: number } = {};
      try { parsed = JSON.parse(p.leaf_data); } catch { /* sai định dạng */ }
      const fieldsOk = parsed.dossier_id === p.leaf.dossier_id && parsed.entry_hash === p.leaf.entry_hash && Number(parsed.kg) === Number(p.leaf.kg);
      lines.push({ id: "leaf", ok: fieldsOk, label: fieldsOk ? t("Lá khớp mã hồ sơ, mã mục sổ và số kg ghi trong bằng chứng", "Leaf matches the dossier ID, entry hash and kg in the proof")
        : t("Lá KHÔNG khớp các trường ghi trong bằng chứng", "Leaf does NOT match the fields in the proof") });
      const lh = Array.from(await leafHash(new TextEncoder().encode(p.leaf_data))).map((b) => b.toString(16).padStart(2, "0")).join("");
      const inc = await verifyInclusion(lh, p.leaf_index, p.tree_size, p.proof, p.root);
      lines.push({ id: "path", ok: inc, label: inc ? t(`Đường kiểm toán Merkle hợp lệ: lá #${p.leaf_index + 1}/${p.tree_size} dẫn đúng tới gốc ${p.root.slice(0, 16)}… (${p.proof.length} mã băm)`,
        `Merkle audit path valid: leaf #${p.leaf_index + 1}/${p.tree_size} leads to root ${p.root.slice(0, 16)}… (${p.proof.length} hashes)`)
        : t("Đường kiểm toán Merkle SAI", "Merkle audit path INVALID") });
      if (cert) {
        const root = (cert.facts as { merkle?: { root?: string } }).merkle?.root;
        lines.push({ id: "cert", ok: root === p.root, label: root === p.root
          ? t("Gốc khớp chứng thư lô hàng đã ký (tệp chứng thư đã kiểm ở trên)", "Root matches the signed lot certificate (checked above)")
          : t("Gốc KHÁC gốc trong chứng thư lô hàng đã thả", "Root DIFFERS from the dropped lot certificate") });
      } else {
        lines.push({ id: "cert", ok: null, label: t("Thả thêm tệp chứng thư lô hàng (.json) để đối chiếu gốc với nội dung đã ký.",
          "Also drop the lot certificate (.json) to compare the root with the signed content.") });
      }
      setRes({ kind: "lot_proof", title: t(`Bằng chứng thuộc lô · vườn ${p.leaf.dossier_id} · ${p.leaf.kg} kg`, `Lot inclusion proof · plot ${p.leaf.dossier_id} · ${p.leaf.kg} kg`), lines });
      return;
    }
    setErr(t("Không nhận ra tệp: cần tệp hồ sơ TerraTwin hoặc bằng chứng thuộc lô.", "Unrecognised file: need a TerraTwin dossier or a lot inclusion proof."));
  }

  const allOk = res?.lines.every((l) => l.ok === true);
  return (
    <AppShell>
      <main className="bat-wrap eu-wrap tt-reveal">
        <div>
          <p className="eu-eyebrow">{t("Kiểm offline · không cần tin máy chủ", "Offline check · no need to trust the server")}</p>
          <h1>{t("Kiểm hồ sơ ngay trong trình duyệt", "Verify a dossier in your browser")}</h1>
          <p className="doc-lede">{t(
            "Thả tệp hồ sơ (.json tải từ trang hồ sơ) hoặc bằng chứng thuộc lô hàng. Trình duyệt tự băm SHA-256, kiểm chữ ký Ed25519 và đường kiểm toán Merkle. Tệp không rời khỏi máy bạn; tắt mạng vẫn kiểm được.",
            "Drop a dossier file (.json downloaded from a dossier page) or a lot inclusion proof. Your browser hashes with SHA-256 and checks the Ed25519 signature and Merkle audit path. The file never leaves your device; it works offline.")}</p>
        </div>
        <section className="bat-card">
          <label className="eu-drop">
            <Upload size={22} aria-hidden="true" />
            <b>{t("Chọn hoặc thả tệp .json", "Choose or drop a .json file")}</b>
            <small>{t("Hồ sơ vườn, hồ sơ đất số, chứng thư lô hàng, bằng chứng thuộc lô", "Plot dossier, land dossier, lot certificate, lot inclusion proof")}</small>
            <input id="verify-file" type="file" accept="application/json,.json" onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
          {err && <p className="bat-err">{err}</p>}
          <form className="kv-code" onSubmit={(e) => { e.preventDefault(); openCode(); }}>
            <label htmlFor="verify-code">{t("Hoặc dán mã hồ sơ / đường link (quét QR bằng camera điện thoại rồi dán link)",
              "Or paste a dossier code / link (scan the QR with your phone camera, then paste the link)")}</label>
            <div className="kv-row">
              <input id="verify-code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" spellCheck={false}
                     placeholder={t("vd. 7KQ2M9XW4TJA hoặc …/h/7KQ2M9XW4TJA", "e.g. 7KQ2M9XW4TJA or …/h/7KQ2M9XW4TJA")} />
              <button type="submit" className="bat-btn" disabled={!code.trim()}>{t("Mở hồ sơ", "Open dossier")}</button>
            </div>
            {codeErr && <p className="bat-err">{codeErr}</p>}
          </form>
        </section>
        {res && (
          <section className={`bat-card eu-verify ${allOk ? "ok" : "bad"}`}>
            <h2>{allOk ? <ShieldCheck size={18} aria-hidden="true" className="ui-ic" /> : <FileCheck2 size={18} aria-hidden="true" className="ui-ic" />} {res.title}</h2>
            <ul className="eu-checks">
              {res.lines.map((l) => <li key={l.id} className={l.ok === true ? "ok" : l.ok === false ? "bad" : "unk"}>{l.ok === true ? "✓" : l.ok === false ? "✗" : "?"} {l.label}</li>)}
            </ul>
            <p className="eu-src">{allOk
              ? t("Mọi phép kiểm đạt, chạy hoàn toàn trong trình duyệt. Còn một bước nên làm khi có mạng: so mã khoá với danh sách khoá công khai của TerraTwin.",
                  "Every check passed, entirely in your browser. One step to do when online: compare the key ID with TerraTwin's public key list.")
              : t("Có phép kiểm không đạt hoặc chưa kiểm được — đừng dựa vào nội dung khi chưa làm rõ.",
                  "Some checks failed or could not run — don't rely on the content until resolved.")}</p>
          </section>
        )}
        <section className="bat-card">
          <h2>{t("Kiểm thế nào", "How it checks")}</h2>
          <ul className="eu-reasons">
            <li>{t("Nội dung: SHA-256 của đúng chuỗi đã băm lúc phát hành phải bằng facts_hash.", "Content: SHA-256 of the exact string hashed at issuance must equal facts_hash.")}</li>
            <li>{t("Mục sổ: SHA-256(lược đồ | số thứ tự | mã | thời điểm | facts_hash | prev_hash) phải bằng entry_hash; prev_hash nối vào hồ sơ trước.", "Registry entry: SHA-256(schema | seq | ID | time | facts_hash | prev_hash) must equal entry_hash; prev_hash links to the previous dossier.")}</li>
            <li>{t("Chữ ký: Ed25519 trên entry_hash bằng khoá công khai kèm tệp.", "Signature: Ed25519 over entry_hash with the public key in the file.")}</li>
            <li>{t("Bằng chứng thuộc lô: băm lá (tiền tố 0x00), đi theo đường kiểm toán (tiền tố 0x01) tới gốc Merkle — RFC 6962/9162.", "Lot inclusion: hash the leaf (0x00 prefix), follow the audit path (0x01 prefix) to the Merkle root — RFC 6962/9162.")}</li>
          </ul>
        </section>
      </main>
    </AppShell>
  );
}
