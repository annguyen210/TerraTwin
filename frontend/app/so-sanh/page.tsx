"use client";

/**
 * SO SÁNH THỬA (GĐ6 · năng lực 7) — đặt 2–4 thửa cạnh nhau trên một màn. Người phân vân giữa hai mảnh đất
 * quyết định ở đây. Mỗi hàng đánh dấu giá trị thuận lợi nhất theo RIÊNG tiêu chí đó (có dấu ✓, không chỉ
 * bằng màu); không có điểm tổng, không khuyên mua. Điện thoại: mỗi tiêu chí thành một thẻ 2×2, không cuộn ngang.
 *
 * Nguồn danh sách: ?p=lat,lon,tên|lat,lon,tên (từ "Thửa của tôi") hoặc danh sách đã thêm từ Sổ tay thửa.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { comparePlots, type CompareResult } from "@/lib/api";
import { useLang } from "@/lib/i18n";

type Pt = { lat: number; lon: number; name?: string };
const KEY = "tt-compare";

function parse(q: string | null): Pt[] {
  if (!q) return [];
  return q.split("|").map((s) => {
    const [a, b, ...n] = s.split(",");
    return { lat: parseFloat(a), lon: parseFloat(b), name: n.join(",").trim() || undefined };
  }).filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon)).slice(0, 4);
}

function readSaved(): Pt[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]").slice(0, 4); } catch { return []; }
}
function save(pts: Pt[]) {
  try { localStorage.setItem(KEY, JSON.stringify(pts)); } catch { /* chế độ riêng tư: bỏ qua */ }
}

export default function ComparePage() {
  const { t, lang } = useLang();
  const [pts, setPts] = useState<Pt[] | null>(null);
  const [r, setR] = useState<CompareResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [add, setAdd] = useState("");

  useEffect(() => {
    const fromUrl = parse(new URLSearchParams(window.location.search).get("p"));
    setPts(fromUrl.length ? fromUrl : readSaved());
  }, []);

  useEffect(() => {
    if (!pts) return;
    save(pts);
    if (pts.length < 2) { setR(null); return; }
    let live = true;
    setBusy(true); setErr(null);
    comparePlots(pts).then((x) => live && setR(x)).catch((e) => live && setErr(e.message))
      .finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [pts, lang]);

  function addPoint() {
    const m = add.match(/-?\d+(\.\d+)?/g);
    if (!m || m.length < 2 || !pts) return;
    const p = { lat: parseFloat(m[0]), lon: parseFloat(m[1]) };
    if (pts.some((x) => Math.abs(x.lat - p.lat) < 1e-5 && Math.abs(x.lon - p.lon) < 1e-5)) return;
    setPts([...pts, p].slice(0, 4));
    setAdd("");
  }

  const fmt = (v: number | string | null, unit: string) =>
    v == null ? "—" : typeof v === "number" ? `${Number.isInteger(v) ? v : v.toFixed(1)}${unit}` : v;

  return (
    <AppShell>
      <main className="cmp-wrap">
        <p className="dos-eyebrow">{t("SO SÁNH THỬA · TERRATWIN", "PLOT COMPARISON · TERRATWIN")}</p>
        <h1>{t("So sánh thửa đất", "Compare plots")}</h1>
        <p className="cmp-lede">{t("Đặt 2–4 thửa cạnh nhau bằng cùng một bộ số đo. Dán toạ độ để thêm thửa.",
                                   "Put 2–4 plots side by side with the same measurements. Paste coordinates to add a plot.")}</p>

        <div className="cmp-add">
          <label className="sr-only" htmlFor="cmp-in">{t("Toạ độ thửa (vĩ độ, kinh độ)", "Plot coordinates (lat, lon)")}</label>
          <input id="cmp-in" value={add} onChange={(e) => setAdd(e.target.value)} placeholder="16.4637, 107.5909"
                 onKeyDown={(e) => e.key === "Enter" && addPoint()} disabled={(pts?.length ?? 0) >= 4} />
          <button className="bat-btn" onClick={addPoint} disabled={(pts?.length ?? 0) >= 4 || !add.trim()}>{t("Thêm thửa", "Add plot")}</button>
        </div>

        {pts && pts.length < 2 && <p className="doc-note">{t("Cần ít nhất 2 thửa. Chọn trong \"Thửa của tôi\" hoặc bấm \"So sánh\" ở Sổ tay thửa.",
                                                            "Need at least 2 plots. Pick them in \"My plots\" or press \"Compare\" on a Land Passport.")}</p>}
        {busy && <p className="doc-note">{t("Đang lấy số đo cho từng thửa…", "Fetching measurements for each plot…")}</p>}
        {err && <p className="bat-err">{err}</p>}

        {r && (
          <div className="cmp-table" role="table" aria-label={t("Bảng so sánh thửa", "Plot comparison table")}
               style={{ ["--n" as string]: r.columns.length }}>
            <div className="cmp-row cmp-headrow" role="row">
              <div className="cmp-label" role="columnheader">{t("Tiêu chí", "Criterion")}</div>
              {r.columns.map((c, i) => (
                <div key={i} className="cmp-col" role="columnheader">
                  <b>{c.name}</b>
                  <Link href={`/plot/${c.lat},${c.lon}`}>{c.lat.toFixed(4)}, {c.lon.toFixed(4)}</Link>
                  {!c.water_read && <small>{t("Chưa đọc lịch sử nước — mở Sổ tay thửa", "Water history not read — open the passport")}</small>}
                  <button type="button" className="cmp-x" aria-label={t(`Bỏ ${c.name}`, `Remove ${c.name}`)}
                          onClick={() => setPts((pts ?? []).filter((_, j) => j !== i))}>×</button>
                </div>
              ))}
            </div>
            {r.rows.map((row) => (
              <div key={row.key} className="cmp-row" role="row">
                <div className="cmp-label" role="rowheader">{row.label}<small>{row.source}</small></div>
                {row.values.map((v, i) => {
                  const best = row.best?.includes(i);
                  return (
                    <div key={i} role="cell" className={`cmp-cell${best ? " cmp-best" : ""}`}>
                      <small className="cmp-colname">{r.columns[i].name}</small>
                      <span>{fmt(v, row.unit)}{best && <span className="cmp-tick" aria-label={t("thuận lợi nhất theo tiêu chí này", "most favourable on this criterion")}> ✓</span>}</span>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        )}
        {r && <p className="dos-src">{r.note}</p>}
      </main>
    </AppShell>
  );
}
