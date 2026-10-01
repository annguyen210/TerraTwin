"use client";

/**
 * THẨM ĐỊNH HÀNG LOẠT — dán / tải CSV nhiều thửa → bảng rủi ro cả danh mục.
 *
 * Cho cán bộ tín dụng, hợp tác xã, bảo hiểm: họ không mở từng thửa trên bản đồ.
 * Máy chủ chạy nền (hàng đợi bền), trang hỏi tiến độ; kết quả lưu theo tài
 * khoản để mở lại, tải CSV (mở được bằng Excel), hoặc xoá.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  batchTemplateUrl, deleteBatch, downloadBatchCsv, getBatch, getToken, listBatches, submitBatch,
  type BatchRow, type BatchRowError, type BatchRunInfo, type BatchState,
} from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";
import { levelOf } from "@/lib/riskScale";

const RANK: Record<string, number> = { danger: 0, warning: 1, safe: 2, unknown: 3 };
const LAND_VI: Record<string, [string, string]> = {
  built: ["Xây dựng", "Built-up"], crop: ["Trồng trọt", "Cropland"], tree: ["Cây xanh", "Trees"],
  water: ["Mặt nước", "Water"], open: ["Đất trống / cỏ", "Open land"], mixed: ["Hỗn hợp", "Mixed"],
  unknown: ["Chưa rõ", "Unknown"],
};

export default function BatchPage() {
  const { t, lang } = useLang();
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [csv, setCsv] = useState("");
  const [title, setTitle] = useState("");
  const [submitErr, setSubmitErr] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<BatchRowError[]>([]);
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState<BatchRunInfo[]>([]);
  const [current, setCurrent] = useState<BatchState | null>(null);
  const [maxRows, setMaxRows] = useState(50);

  const refreshRuns = useCallback(async () => {
    const r = await listBatches();
    setRuns(r.runs);
    if (r.max_rows) setMaxRows(r.max_rows);
    return r;
  }, []);

  useEffect(() => {
    const ok = Boolean(getToken());
    setAuthed(ok);
    if (!ok) return;
    refreshRuns().then((r) => {
      if (r.active) setCurrent({ id: r.active.id, state: r.active.state as BatchState["state"], progress: r.active.progress });
      else if (r.runs[0]) getBatch(r.runs[0].id).then(setCurrent).catch(() => {});
    }).catch((e) => setSubmitErr(e.message));
  }, [refreshRuns]);

  // Đang chạy → hỏi tiến độ. Chính các lượt hỏi giữ máy chủ gói free không ngủ.
  useEffect(() => {
    if (!current || (current.state !== "queued" && current.state !== "running")) return;
    const id = setInterval(async () => {
      try {
        const s = await getBatch(current.id);
        setCurrent(s);
        if (s.state === "done") refreshRuns().catch(() => {});
      } catch { /* thử lại ở nhịp sau */ }
    }, 3000);
    return () => clearInterval(id);
  }, [current, refreshRuns]);

  async function submit() {
    setBusy(true);
    setSubmitErr(null);
    setRowErrors([]);
    try {
      const r = await submitBatch(csv, title);
      setRowErrors(r.errors);
      setCurrent({ id: r.job_id, state: "queued", progress: { done: 0, total: r.rows, current: "" } });
    } catch (e) {
      setSubmitErr((e as Error).message);
      setRowErrors((e as Error & { rowErrors?: BatchRowError[] }).rowErrors ?? []);
    } finally {
      setBusy(false);
    }
  }

  const rows = useMemo(() => [...(current?.rows ?? [])].sort((a, b) =>
    (RANK[a.risk_level] ?? 9) - (RANK[b.risk_level] ?? 9) || (a.score ?? 999) - (b.score ?? 999)),
  [current?.rows]);
  const s = current?.summary;
  const land = (g: string | null) => { const v = LAND_VI[g ?? "unknown"] ?? LAND_VI.unknown; return lang === "en" ? v[1] : v[0]; };

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions"><LangToggle /></div>
      </header>

      <main className="bat-wrap">
        <h1>{t("Thẩm định hàng loạt", "Batch appraisal")}</h1>
        <p className="doc-lede">{t(
          `Dán hoặc tải lên bảng toạ độ nhiều thửa (tối đa ${maxRows} thửa mỗi lần). Mỗi thửa được kiểm loại đất thật (ESA WorldCover), rủi ro hiện tại từ dữ liệu thật và mười năm hiểm hoạ — rồi gộp thành bảng rủi ro cả danh mục.`,
          `Paste or upload a table of plot coordinates (up to ${maxRows} per run). Each plot gets its real land type (ESA WorldCover), current risk from real data and ten years of hazards — then everything is rolled up into a portfolio risk table.`)}</p>

        {authed === false && (
          <p className="doc-note">{t("Cần đăng nhập — kết quả là danh mục của tổ chức bạn, chỉ bạn xem được. ",
                                     "Sign in required — results are your organisation's portfolio, visible only to you. ")}
            <Link href="/">{t("Về trang chính để đăng nhập", "Go to the home page to sign in")}</Link></p>
        )}

        {authed && (
          <>
            <section className="bat-card">
              <div className="bat-row">
                <input id="batch-title" className="bat-input" placeholder={t("Tên danh mục (tuỳ chọn), vd: Khoản vay Q4", "Portfolio name (optional), e.g. Q4 loans")}
                       value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
                <label className="bat-btn ghost">
                  {t("Chọn tệp CSV", "Choose CSV file")}
                  <input id="batch-file" type="file" accept=".csv,text/csv" hidden
                         onChange={async (e) => { const f = e.target.files?.[0]; if (f) setCsv(await f.text()); }} />
                </label>
                <a className="bat-btn ghost" href={batchTemplateUrl()}>{t("Tải tệp mẫu", "Download template")}</a>
              </div>
              <textarea id="batch-csv" className="bat-csv" rows={7} spellCheck={false} value={csv}
                        onChange={(e) => setCsv(e.target.value)}
                        placeholder={"ma,lat,lon,area_ha\nKV-001,16.4600,107.5900,0.3\nKV-002,10.4000,105.2000,1.5"} />
              <div className="bat-row">
                <button className="bat-btn" disabled={busy || !csv.trim()} onClick={submit}>
                  {busy ? t("Đang gửi…", "Submitting…") : t("Thẩm định danh mục", "Appraise portfolio")}
                </button>
                <small>{t("Nhận cột ma/lat/lon/area_ha hoặc vi_do/kinh_do/dien_tich; dấu , hoặc ; (Excel tiếng Việt).",
                          "Accepts ma/lat/lon/area_ha or vi_do/kinh_do/dien_tich; comma or semicolon (Vietnamese Excel).")}</small>
              </div>
              {submitErr && <p className="bat-err">{submitErr}</p>}
              {rowErrors.length > 0 && (
                <ul className="bat-rowerr">
                  {rowErrors.slice(0, 20).map((e) => <li key={e.line}>{t("Dòng", "Line")} {e.line}: {e.message}</li>)}
                </ul>
              )}
            </section>

            {current && (current.state === "queued" || current.state === "running") && (
              <section className="bat-card">
                <b>{t("Đang thẩm định…", "Appraising…")}</b>
                <div className="bat-bar"><span style={{ width: `${current.progress?.total ? (100 * current.progress.done) / current.progress.total : 3}%` }} /></div>
                <small>{current.progress?.done ?? 0}/{current.progress?.total ?? "?"} {t("thửa", "plots")}
                  {current.progress?.current ? ` · ${current.progress.current}` : ""}
                  {current.progress?.phase === "paused_quota" &&
                    <> · <b>{t("đang TẠM DỪNG: nguồn dữ liệu miễn phí báo quá hạn mức — tự chạy tiếp khi thông",
                               "PAUSED: a free data source reports its quota exceeded — resumes automatically")}</b></>}</small>
                <p className="bat-keepopen">{t(
                  "Giữ trang này mở tới khi xong. Máy chủ gói miễn phí ngủ sau 15 phút không có ai truy cập; nếu bạn đóng trang, lô sẽ dừng và tự chạy tiếp từ thửa dở khi bạn mở lại trang này.",
                  "Keep this page open until it finishes. The free-tier server sleeps after 15 minutes with no visitors; if you close the page the batch pauses and resumes from the last plot when you reopen this page.")}</p>
              </section>
            )}
            {current?.state === "error" && <p className="bat-err">{current.message ?? current.error}</p>}

            {current?.state === "done" && s && (
              <section className="bat-card">
                <div className="bat-row bat-between">
                  <h2>{current.title || t("Kết quả thẩm định", "Appraisal result")}</h2>
                  <div className="bat-row">
                    <button className="bat-btn ghost" onClick={() => downloadBatchCsv(current.id).catch((e) => setSubmitErr(e.message))}>{t("Tải CSV", "Download CSV")}</button>
                    <button className="bat-btn ghost danger" onClick={async () => {
                      await deleteBatch(current.id).catch((e) => setSubmitErr(e.message));
                      setCurrent(null); refreshRuns().catch(() => {});
                    }}>{t("Xoá", "Delete")}</button>
                  </div>
                </div>
                <p className="bat-head">{s.headline}</p>
                <div className="bat-tiles">
                  <div><b>{s.n_ok}</b><span>{t("thửa đã thẩm định", "plots appraised")}{s.n_failed ? ` · ${s.n_failed} ${t("lỗi", "failed")}` : ""}</span></div>
                  <div><b>{s.at_risk_pct ?? "—"}%</b><span>{t("có mối đe doạ thật", "face a real threat")}</span></div>
                  <div><b>{s.at_risk_ha} / {s.total_ha} ha</b><span>{t("diện tích chịu rủi ro", "area at risk")}</span></div>
                  <div><b>{s.history_10y_plots.flood ?? 0}</b><span>{t("thửa từng ngập trong 10 năm", "plots flooded in 10 years")}</span></div>
                </div>
                <div className="bat-dist" aria-label={t("Phân bố mức rủi ro", "Risk distribution")}>
                  {(["danger", "warning", "safe", "unknown"] as const).map((k) => s.by_risk[k] ? (
                    <span key={k} style={{ flex: s.by_risk[k], background: levelOf(k).color }}
                          title={`${lang === "en" ? levelOf(k).en : levelOf(k).vi}: ${s.by_risk[k]}`} />) : null)}
                </div>
                <p className="bat-legend">
                  {Object.entries(s.by_land).map(([g, n]) => `${land(g)} ${n}`).join(" · ")}
                  {s.top_drivers.length > 0 && <> · {t("mối đe doạ hay gặp", "common threats")}: {s.top_drivers.map(([d, n]) => `${d} (${n})`).join(", ")}</>}
                </p>
                <div className="bat-table-wrap">
                  <table className="bat-table">
                    <thead><tr>
                      <th>{t("Mã", "Ref")}</th><th>{t("Loại đất", "Land")}</th><th>{t("Rủi ro", "Risk")}</th>
                      <th>{t("Điểm", "Score")}</th><th>{t("Đe doạ", "Threats")}</th>
                      <th>{t("Ngập 10 năm", "Floods 10y")}</th><th>{t("Hạn 10 năm", "Droughts 10y")}</th><th></th>
                    </tr></thead>
                    <tbody>
                      {rows.map((r: BatchRow, i) => {
                        const lv = levelOf(r.risk_level);
                        return (
                          <tr key={`${r.ref}-${i}`} className={r.error ? "bat-failed" : ""}>
                            <td><b>{r.ref}</b><small>{r.lat.toFixed(4)}, {r.lon.toFixed(4)}{r.area_ha ? ` · ${r.area_ha} ha` : ""}</small></td>
                            <td>{r.land_label ?? land(r.land_group)}</td>
                            <td><span className="bat-badge" style={{ background: lv.color }}>{lang === "en" ? lv.en : lv.vi}</span></td>
                            <td>{r.score ?? "—"}{r.grade ? ` · ${r.grade}` : ""}</td>
                            <td>{r.error ?? (r.drivers.join(", ") || "—")}</td>
                            <td className="num">{r.history_10y.flood ?? "—"}</td>
                            <td className="num">{r.history_10y.drought ?? "—"}</td>
                            <td><Link href={`/plot/${r.lat.toFixed(5)},${r.lon.toFixed(5)}`}>{t("Sổ tay", "Passport")}</Link></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {runs.length > 0 && (
              <section className="bat-card">
                <h2>{t("Các lần thẩm định trước", "Previous appraisals")}</h2>
                <ul className="bat-runs">
                  {runs.map((r) => (
                    <li key={r.id}>
                      <button className="doc-link-btn" onClick={() => getBatch(r.id).then(setCurrent).catch((e) => setSubmitErr(e.message))}>
                        {r.title || r.id.slice(0, 8)}
                      </button>
                      <small>{new Date(r.created_at).toLocaleString(lang === "en" ? "en-GB" : "vi-VN")} · {r.n_rows} {t("thửa", "plots")}{r.headline ? ` · ${r.headline}` : ""}</small>
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
