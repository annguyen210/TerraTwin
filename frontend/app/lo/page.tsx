"use client";

/**
 * LÔ HÀNG — doanh nghiệp ghép một lô xuất khẩu từ các đợt nhập của từng vườn (mã hồ sơ
 * vườn + số kg). TerraTwin kiểm từng vườn (chữ ký, mức sàng lọc, giám sát) và CÂN BẰNG
 * KHỐI LƯỢNG (kg ≤ diện tích × năng suất trần, cộng dồn mọi lô cùng vụ, kể cả của doanh
 * nghiệp khác) rồi phát hành CHỨNG THƯ LÔ HÀNG (gốc Merkle đã ký) + tờ khai DDS nháp.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { BadgeCheck, Download, Package, Trash2 } from "lucide-react";
import Account from "@/components/Account";
import {
  fetchMe, getToken, lotCertify, lotCreate, lotDelete, lotDownload, lotFromSet, lotGet, lotUpdate, lotsList,
  type AuthUser, type Lot, type LotDelivery,
} from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

const COMMODITIES: [string, string, string][] = [
  ["coffee", "Cà phê", "Coffee"], ["rubber", "Cao su", "Rubber"], ["cocoa", "Ca cao", "Cocoa"], ["wood", "Gỗ", "Wood"], ["other", "Khác", "Other"],
];

type Row = LotDelivery & { ref?: string; level?: string };

function parseRows(text: string): Row[] {
  return text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).map((l) => {
    const [id, kg, date, ...ack] = l.split(/[,;\t]/).map((x) => x.trim());
    return { dossier_id: id, kg: Number((kg || "").replace(",", ".")), date: date || null, review_ack: ack.join(", ") || null };
  }).filter((r) => r.dossier_id && !/^ma|dossier/i.test(r.dossier_id));
}

export default function LotsPage() {
  const { t } = useLang();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [lots, setLots] = useState<Lot[]>([]);
  const [cur, setCur] = useState<Lot | null>(null);
  const [ref, setRef] = useState("");
  const [commodity, setCommodity] = useState("coffee");
  const [season, setSeason] = useState(() => { const y = new Date().getFullYear(); return `${y}/${String((y + 1) % 100).padStart(2, "0")}`; });
  const [operator, setOperator] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => { const r = await lotsList(); setLots(r.lots); }, []);

  useEffect(() => {
    if (!getToken()) return;
    fetchMe().then((u) => { setUser(u); refresh().catch(() => {}); }).catch(() => setUser(null));
    const setId = new URLSearchParams(window.location.search).get("set");
    if (setId) lotFromSet(setId).then((r) => {
      setRef(r.ref); setCommodity(r.commodity || "coffee"); setOperator(r.operator || "");
      setRows(r.rows.map((x) => ({ dossier_id: x.dossier_id, kg: 0, ref: x.ref, level: x.level })));
    }).catch((e) => setErr(e.message));
  }, [refresh]);

  function load(l: Lot) {
    setCur(l); setRef(l.ref); setCommodity(l.commodity); setSeason(l.season); setOperator(l.operator);
    setRows(l.deliveries.map((d) => ({ ...d, ref: l.checks.rows?.find((r) => r.dossier_id === d.dossier_id)?.ref })));
  }

  async function save() {
    setBusy(true); setErr(null);
    const body = { ref, commodity, season, operator, deliveries: rows.filter((r) => r.kg > 0).map(({ dossier_id, kg, date, review_ack }) => ({ dossier_id, kg, date: date || null, review_ack: review_ack || null })) };
    try {
      const l = cur ? await lotUpdate(cur.id, body) : await lotCreate(body);
      load(l); refresh().catch(() => {});
      if (l.errors?.length) setErr(l.errors.join(" · "));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  async function certify() {
    if (!cur) return;
    setBusy(true); setErr(null);
    try { const r = await lotCertify(cur.id); load(r.lot); refresh().catch(() => {}); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  const chk = cur?.checks;
  const byId = Object.fromEntries((chk?.rows ?? []).map((r) => [r.dossier_id, r]));
  const locked = cur?.state === "certified";

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions"><LangToggle /><Account user={user} onAuth={setUser} /></div>
      </header>
      <main className="bat-wrap eu-wrap">
        <div>
          <p className="eu-eyebrow">{t("Lô hàng · cân bằng khối lượng · chứng thư Merkle", "Lots · mass balance · Merkle certificate")}</p>
          <h1>{t("Ghép lô hàng từ các vườn đã có hồ sơ", "Build a lot from plots with dossiers")}</h1>
          <p className="doc-lede">{t(
            "Mỗi đợt nhập là một mã hồ sơ vườn và số kg. TerraTwin chặn vườn chưa đạt sàng lọc và vườn khai vượt năng suất trần (cộng dồn mọi lô cùng vụ, kể cả của doanh nghiệp khác — một vườn bán cho hai nơi vẫn chỉ có một sức sản xuất), rồi phát hành chứng thư lô hàng ký số và tờ khai DDS nháp.",
            "Each delivery is a plot dossier ID and a quantity in kg. TerraTwin blocks plots that didn't pass screening and plots declared above the yield cap (summed across every lot in the season, including other companies' — a plot sold twice still has one capacity), then issues a signed lot certificate and a draft DDS.")}</p>
        </div>
        {!user ? (
          <p className="doc-note">{t("Đăng nhập (nút trên cùng) để ghép lô hàng — danh sách nhà cung cấp là bí mật kinh doanh, chỉ bạn xem được.",
            "Sign in (top button) to build lots — the supplier list is a trade secret, visible only to you.")}</p>
        ) : (
          <>
            <section className="bat-card">
              <div className="bat-row bat-between">
                <h2><Package size={18} aria-hidden="true" className="ui-ic" /> {cur ? t(`Lô ${cur.ref || cur.id}`, `Lot ${cur.ref || cur.id}`) : t("Lô hàng mới", "New lot")}
                  {locked && <span className="eu-badge eu-low"><BadgeCheck size={14} aria-hidden="true" /> {t("Đã có chứng thư", "Certified")}</span>}</h2>
                {cur && <button className="bat-btn ghost" onClick={() => { setCur(null); setRows([]); setRef(""); }}>{t("Lô mới", "New lot")}</button>}
              </div>
              <div className="eu-fields">
                <label>{t("Mã lô", "Lot ref")}<input className="bat-input" disabled={locked} value={ref} maxLength={80} onChange={(e) => setRef(e.target.value)} placeholder="EX-2026-001" /></label>
                <label>{t("Nông sản", "Commodity")}
                  <select className="bat-input" disabled={locked} value={commodity} onChange={(e) => setCommodity(e.target.value)}>
                    {COMMODITIES.map(([k, vi, en]) => <option key={k} value={k}>{t(vi, en)}</option>)}
                  </select></label>
                <label>{t("Vụ", "Season")}<input className="bat-input" disabled={locked} value={season} maxLength={16} onChange={(e) => setSeason(e.target.value)} /></label>
                <label>{t("Doanh nghiệp", "Operator")}<input className="bat-input" disabled={locked} value={operator} maxLength={160} onChange={(e) => setOperator(e.target.value)} /></label>
              </div>
              {!locked && (
                <>
                  <label className="eu-fields-1">{t("Dán đợt nhập: mỗi dòng “mã hồ sơ, kg, ngày (YYYY-MM-DD)”", "Paste deliveries: one per line “dossier ID, kg, date (YYYY-MM-DD)”")}
                    <textarea className="bat-csv" rows={4} value={paste} onChange={(e) => setPaste(e.target.value)} placeholder={"3scihq2x5sk6, 2500, 2026-12-10\nk7m2p9qwx4ab, 1800, 2026-12-11"} />
                  </label>
                  <div className="bat-row">
                    <button className="bat-btn ghost" disabled={!paste.trim()} onClick={() => { setRows([...rows, ...parseRows(paste)]); setPaste(""); }}>{t("Thêm vào bảng", "Add to table")}</button>
                  </div>
                </>
              )}
              {rows.length > 0 && (
                <div className="bat-table-wrap">
                  <table className="bat-table">
                    <thead><tr><th>{t("Hồ sơ vườn", "Plot dossier")}</th><th>kg</th><th>{t("Ngày nhập", "Date")}</th><th>{t("Kiểm", "Check")}</th><th>{t("Ghi chú xem xét (vườn “cần xem lại”)", "Review note (“needs review” plots)")}</th><th></th></tr></thead>
                    <tbody>
                      {rows.map((r, i) => {
                        const c = byId[r.dossier_id];
                        return (
                          <tr key={`${r.dossier_id}-${i}`} className={c?.status === "blocked" ? "bat-failed" : ""}>
                            <td><Link href={`/h/${r.dossier_id}`}>{r.dossier_id}</Link><small>{c?.ref ?? r.ref ?? ""}{c?.area_ha ? ` · ${c.area_ha} ha` : ""}{c?.level ? ` · ${c.level}` : ""}</small></td>
                            <td><input className="bat-input eu-num" disabled={locked} inputMode="decimal" value={r.kg || ""} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, kg: Number(e.target.value.replace(",", ".")) } : x))} /></td>
                            <td><input className="bat-input eu-num" disabled={locked} value={r.date ?? ""} placeholder="YYYY-MM-DD" onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, date: e.target.value } : x))} /></td>
                            <td>{c ? <span className={`eu-badge ${c.status === "ok" ? "eu-low" : c.status === "warning" ? "eu-review" : "eu-high"}`}>{c.status === "ok" ? t("Đạt", "OK") : c.status === "warning" ? t("Lưu ý", "Warning") : t("Bị chặn", "Blocked")}</span> : "—"}
                              {c?.cap_kg ? <small>{t("vụ này", "season")} {c.season_kg?.toLocaleString("vi-VN")} / {t("trần", "cap")} {c.cap_kg.toLocaleString("vi-VN")} kg</small> : null}
                              {c?.notes.map((n, k) => <small key={k}>{n}</small>)}</td>
                            <td><input className="bat-input" disabled={locked} value={r.review_ack ?? ""} maxLength={300} placeholder={t("vd: đã xem ảnh thực địa, cà phê che bóng", "e.g. field photos checked, shaded coffee")} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, review_ack: e.target.value } : x))} /></td>
                            <td>{!locked && <button className="bat-btn ghost danger" aria-label={t("Bỏ dòng", "Remove row")} onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={14} aria-hidden="true" /></button>}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {chk?.headline && <p className={`bat-head ${chk.certifiable ? "eu-ok-line" : "eu-err-txt"}`}>{chk.headline}</p>}
              {err && <p className="bat-err">{err}</p>}
              <div className="bat-row">
                {!locked && <button className="bat-btn ghost" disabled={busy || !rows.some((r) => r.kg > 0)} onClick={save}>{busy ? t("Đang kiểm…", "Checking…") : t("Lưu & kiểm cân bằng khối lượng", "Save & check mass balance")}</button>}
                {!locked && cur && <button className="bat-btn" disabled={busy || !chk?.certifiable} onClick={certify}><BadgeCheck size={15} aria-hidden="true" className="ui-ic" /> {t("Phát hành chứng thư lô hàng", "Issue lot certificate")}</button>}
                {cur && <button className="bat-btn ghost" onClick={() => lotDownload(cur.id, "dds").catch((e) => setErr(e.message))}><Download size={15} aria-hidden="true" className="ui-ic" /> {t("Tờ khai DDS nháp (.json)", "Draft DDS (.json)")}</button>}
                {cur && <button className="bat-btn ghost" onClick={() => lotDownload(cur.id, "geojson").catch((e) => setErr(e.message))}><Download size={15} aria-hidden="true" className="ui-ic" /> {t("GeoJSON vị trí cả lô", "GeoJSON for the lot")}</button>}
                {cur?.certificate_id && <Link className="bat-btn" href={`/h/${cur.certificate_id}`}>{t("Mở chứng thư", "Open the certificate")}</Link>}
                {cur && !locked && <button className="bat-btn ghost danger" onClick={async () => { await lotDelete(cur.id).catch((e) => setErr(e.message)); setCur(null); setRows([]); refresh().catch(() => {}); }}>{t("Xoá bản nháp", "Delete draft")}</button>}
              </div>
            </section>
            {lots.length > 0 && (
              <section className="bat-card">
                <h2>{t("Các lô hàng", "Lots")}</h2>
                <ul className="bat-runs">
                  {lots.map((l) => (
                    <li key={l.id}>
                      <button className="doc-link-btn" onClick={() => lotGet(l.id).then(load).catch((e) => setErr(e.message))}>{l.ref || l.id}</button>
                      <small>{l.season} · {l.state === "certified" ? t("đã có chứng thư", "certified") : t("bản nháp", "draft")}{l.checks?.headline ? ` · ${l.checks.headline}` : ""}</small>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
