"use client";

import { useCallback, useEffect, useState } from "react";
import {
  deletePlot,
  getPlotTimeline,
  listPlots,
  savePlot,
  scanAll,
  trackEvent,
  type AuthUser,
  type PlotTimeline,
  type ServerPlot,
  type TerraScore,
} from "@/lib/api";

// H4 — nhãn + màu cho kết quả mỗi cảnh báo trong dòng thời gian thửa.
const OUTCOME: Record<string, [string, string]> = {
  hit: ["✓ báo đúng", "var(--ok, #3ecb83)"],
  false_alarm: ["✗ báo bừa", "var(--bad, #e5705a)"],
  miss: ["⚠ bỏ sót", "var(--clay, #a0522c)"],
  pending: ["⏳ đang chờ chấm", "var(--dim, #66716a)"],
  expired: ["— hết hạn", "var(--dim, #66716a)"],
};

/**
 * H4 — DÒNG THỜI GIAN CỦA MỘT THỬA. Lý do để mở lại app vào ngày mai: một thửa
 * ĐANG ĐƯỢC TRÔNG COI, không phải một lần tra cứu rồi quên. Gộp vào một chỗ:
 * đã báo gì, hoá ra đúng hay hụt, và câu nào đang chờ trả lời — kể cả lần BỎ
 * SÓT (hồi cứu), vì giấu đi thì dòng thời gian chỉ còn là bảng thành tích.
 */
function PlotHistory({ plotId }: { plotId: number }) {
  const [tl, setTl] = useState<PlotTimeline | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    getPlotTimeline(plotId)
      .then((d) => live && setTl(d))
      .catch((e) => live && setErr((e as Error).message));
    return () => { live = false; };
  }, [plotId]);

  if (err) return <p className="pf-err" style={{ margin: "4px 0 10px" }}>{err}</p>;
  if (!tl) return <p className="pf-empty" style={{ margin: "4px 0 10px" }}>Đang tải lịch sử…</p>;

  return (
    <div style={{
      margin: "0 0 10px", padding: "8px 12px",
      background: "var(--surface-2, #f8faf7)", borderRadius: 6,
      border: "1px solid var(--line, #e8ece8)",
    }}>
      <p style={{ fontSize: 11.5, color: "var(--dim, #66716a)", margin: 0 }}>
        Đang trông coi từ {new Date(tl.watching_since).toLocaleDateString("vi-VN")}
        {" · "}<b style={{ color: "var(--ok, #3ecb83)" }}>{tl.tally.hit ?? 0} đúng</b>
        {" · "}<b style={{ color: "var(--clay, #a0522c)" }}>{tl.tally.miss ?? 0} sót</b>
        {" · "}<b style={{ color: "var(--bad, #e5705a)" }}>{tl.tally.false_alarm ?? 0} bừa</b>
        {" · "}{tl.tally.pending ?? 0} chờ
      </p>
      {tl.events.length === 0 ? (
        <p className="pf-empty" style={{ margin: "6px 0 0" }}>
          Chưa có cảnh báo nào cho thửa này trong {tl.window_days} ngày qua.
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
          {tl.events.map((e) => {
            const [lbl, color] = OUTCOME[e.outcome ?? "pending"] ?? OUTCOME.pending;
            return (
              <li key={e.alert_id} style={{ borderLeft: `2px solid ${color}`, paddingLeft: 9, margin: "8px 0" }}>
                <div style={{ fontSize: 11, color: "var(--dim, #66716a)" }}>
                  {new Date(e.at).toLocaleDateString("vi-VN")} · {e.module_id}
                  {!e.was_warned && (
                    <b style={{ color: "var(--clay, #a0522c)" }}> · HỒI CỨU (phần mềm đã bỏ sót)</b>
                  )}
                </div>
                <div style={{ fontSize: 13 }}>{e.headline}</div>
                <span style={{ fontSize: 11, fontWeight: 700, color }}>{lbl}</span>
                {e.verify_note && (
                  <span style={{ fontSize: 11, color: "var(--dim, #66716a)" }}> — {e.verify_note}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {tl.questions.length > 0 && (
        <p className="pf-empty" style={{ margin: "8px 0 0", color: "var(--clay, #a0522c)" }}>
          📩 {tl.questions.length} câu đang chờ bạn xác nhận — mở thửa (bấm vào để phân tích) để trả lời.
        </p>
      )}
    </div>
  );
}

const GRADE_COLOR: Record<string, string> = {
  A: "#2E9E67",
  B: "#3aa0a0",
  C: "#B07A2E",
  D: "#C2412E",
};

export default function Portfolio({
  user,
  coord,
  area,
  terra,
  onLoad,
}: {
  user: AuthUser | null;
  coord: { lat: number; lon: number } | null;
  area?: number;
  terra: TerraScore | null;
  onLoad: (lat: number, lon: number) => void;
}) {
  const [plots, setPlots] = useState<ServerPlot[]>([]);
  const [exporting, setExporting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);   // H4 — thửa đang mở lịch sử

  const refresh = useCallback(async () => {
    if (!user) {
      setPlots([]);
      return;
    }
    try {
      setPlots(await listPlots());
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function addCurrent() {
    if (!coord || !terra) return;
    const name =
      window.prompt(
        "Tên thửa đất:",
        `Thửa (${coord.lat.toFixed(3)}, ${coord.lon.toFixed(3)})`,
      ) || `Thửa (${coord.lat.toFixed(3)}, ${coord.lon.toFixed(3)})`;
    setBusy(true);
    setErr(null);
    try {
      await savePlot(name, coord.lat, coord.lon, area, terra.score, terra.grade);
      trackEvent("save_plot");                        // N6
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setBusy(true);
    try {
      await deletePlot(id);
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function exportReport() {
    if (!coord) return;
    setExporting(true);
    try {
      const scan = await scanAll(coord.lat, coord.lon, area);
      const w = window.open("", "_blank");
      if (w) {
        w.document.write(buildReportHtml(scan, area));
        w.document.close();
        w.focus();
        setTimeout(() => w.print(), 400);
      }
    } catch {
      alert("Không tạo được báo cáo (kiểm tra backend).");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="portfolio">
      <div className="pf-head">📁 Danh mục thửa đất</div>

      {coord && (
        <div className="pf-actions">
          <button onClick={addCurrent} disabled={!terra || !user || busy}>
            💾 Lưu thửa đang xem
          </button>
          <button className="ghost" onClick={exportReport} disabled={exporting}>
            {exporting ? "Đang tạo…" : "🖨️ Xuất báo cáo"}
          </button>
        </div>
      )}

      {err && <p className="pf-err">{err}</p>}

      {!user && (
        <p className="pf-empty">
          Đăng nhập để lưu thửa đất — dữ liệu nằm trên máy chủ nên đồng bộ mọi
          thiết bị, không mất khi xóa trình duyệt.
        </p>
      )}

      {user && plots.length === 0 && (
        <p className="pf-empty">
          Chưa lưu thửa nào. Phân tích một vị trí rồi bấm “Lưu thửa đang xem” để
          so sánh nhiều mảnh đất.
        </p>
      )}

      {plots.map((p) => (
        <div key={p.id}>
          <div className="pf-item">
            <button className="pf-load" onClick={() => onLoad(p.lat, p.lon)}>
              <span
                className="pf-grade"
                style={{ background: GRADE_COLOR[p.grade ?? ""] ?? "#5a6b73" }}
              >
                {p.grade ?? "—"}
              </span>
              <span className="pf-info">
                <span className="pf-name">{p.name}</span>
                <span className="pf-meta">
                  {p.score ?? "—"}/100 · {p.lat.toFixed(3)}, {p.lon.toFixed(3)}
                  {p.area_ha ? ` · ${p.area_ha} ha` : ""}
                </span>
              </span>
            </button>
            {/* H4 — mở/đóng dòng thời gian của thửa này */}
            <button
              className="pf-del"
              onClick={() => setOpenId(openId === p.id ? null : p.id)}
              title={openId === p.id ? "Ẩn lịch sử" : "Lịch sử thửa (đã báo gì, đúng/hụt)"}
              style={{ opacity: openId === p.id ? 1 : 0.75 }}
            >
              📜
            </button>
            <button
              className="pf-del"
              onClick={() => remove(p.id)}
              disabled={busy}
              title="Xóa"
            >
              ✕
            </button>
          </div>
          {openId === p.id && <PlotHistory plotId={p.id} />}
        </div>
      ))}
    </div>
  );
}

function esc(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
}

function buildReportHtml(scan: any, area?: number): string {
  const t = scan.terrascore;
  const rows = scan.modules
    .map(
      (m: any) => `
      <tr>
        <td>${esc(m.icon)} ${esc(m.name)}</td>
        <td class="lvl ${m.risk_level}">${
          { safe: "An toàn", warning: "Cảnh báo", danger: "Nguy hiểm" }[
            m.risk_level as string
          ] ?? "—"
        }</td>
        <td>${
          m.is_real
            ? "🛰️ Dữ liệu thật"
            : m.risk_level === "unknown"
              ? "⏳ Chưa đưa số"
              : "🧪 Ước lượng vật lý"
        }</td>
        <td>${esc(m.headline)}</td>
      </tr>`,
    )
    .join("");
  const alerts = scan.alerts
    .map((m: any) => `<li><b>${esc(m.name)}:</b> ${esc(m.headline)} → ${esc(m.recommendation)}</li>`)
    .join("");
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8">
  <title>Báo cáo TerraTwin</title>
  <style>
    body{font-family:system-ui,Segoe UI,Roboto,sans-serif;color:#122;margin:32px;line-height:1.5}
    h1{margin:0 0 2px}.sub{color:#567;margin:0 0 16px}
    .score{display:inline-block;border:3px solid ${GRADE_COLOR[t.grade] ?? "#567"};color:${GRADE_COLOR[t.grade] ?? "#567"};border-radius:50%;width:70px;height:70px;text-align:center;line-height:66px;font-size:24px;font-weight:800;vertical-align:middle}
    .sum{display:inline-block;margin-left:14px;vertical-align:middle}
    table{border-collapse:collapse;width:100%;margin-top:14px;font-size:13px}
    th,td{border:1px solid #dde;padding:6px 8px;text-align:left}th{background:#f3f6f8}
    .lvl.safe{color:#2E9E67}.lvl.warning{color:#B07A2E}.lvl.danger{color:#C2412E;font-weight:700}
    ul{font-size:13px}.foot{color:#789;font-size:11px;margin-top:20px}
    @media print{body{margin:12mm}}
  </style></head><body>
  <h1>◵ Báo cáo TerraTwin — Hồ sơ thửa đất</h1>
  <p class="sub">Vị trí ${scan.location.lat.toFixed(4)}, ${scan.location.lon.toFixed(4)}${
    area ? ` · diện tích ${area} ha` : ""
  } · lập ${new Date(scan.generated_at).toLocaleString("vi-VN")}</p>
  <div><span class="score">${t.score}</span><span class="sum"><b>TerraScore hạng ${t.grade}</b><br>${esc(
    t.summary,
  )}</span></div>
  <h3>Cảnh báo cần chú ý (từ dữ liệu thật)</h3>
  <ul>${alerts || "<li>Không có cảnh báo từ dữ liệu thật.</li>"}</ul>
  <h3>Toàn cảnh mọi mũi nhọn</h3>
  <table><thead><tr><th>Module</th><th>Mức</th><th>Nguồn</th><th>Nhận định</th></tr></thead>
  <tbody>${rows}</tbody></table>
  <p class="foot">Nguồn dữ liệu thật: Open-Meteo (dự báo + lịch sử ERA5), GloFAS lưu lượng sông,
  Open-Meteo Marine, NASA POWER, DEM Open-Meteo.
  🧪 = ước lượng vật lý có tham số giải thích được, chờ hiệu chỉnh bằng số đo thực địa.
  ⏳ = chưa đưa con số (chờ ảnh Sentinel, hoặc vị trí ngoài phạm vi vùng của mô-đun).
  Kết quả kèm sai số, không đảm bảo 100%.</p>
  </body></html>`;
}
