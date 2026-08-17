"use client";

import { useEffect, useState } from "react";
import { scanAll, type TerraScore } from "@/lib/api";

type Plot = {
  id: string;
  name: string;
  lat: number;
  lon: number;
  area?: number;
  score: number;
  grade: string;
  savedAt: string;
};

const KEY = "terratwin_portfolio";
const GRADE_COLOR: Record<string, string> = {
  A: "#2E9E67",
  B: "#3aa0a0",
  C: "#B07A2E",
  D: "#C2412E",
};

function load(): Plot[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

function save(plots: Plot[]) {
  localStorage.setItem(KEY, JSON.stringify(plots));
}

export default function Portfolio({
  coord,
  area,
  terra,
  onLoad,
}: {
  coord: { lat: number; lon: number } | null;
  area?: number;
  terra: TerraScore | null;
  onLoad: (lat: number, lon: number) => void;
}) {
  const [plots, setPlots] = useState<Plot[]>([]);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    setPlots(load());
  }, []);

  function addCurrent() {
    if (!coord || !terra) return;
    const name =
      window.prompt(
        "Tên thửa đất:",
        `Thửa (${coord.lat.toFixed(3)}, ${coord.lon.toFixed(3)})`,
      ) || `Thửa (${coord.lat.toFixed(3)}, ${coord.lon.toFixed(3)})`;
    const p: Plot = {
      id: Date.now().toString(36),
      name,
      lat: coord.lat,
      lon: coord.lon,
      area,
      score: terra.score,
      grade: terra.grade,
      savedAt: new Date().toISOString(),
    };
    const next = [p, ...plots.filter((x) => !(x.lat === p.lat && x.lon === p.lon))];
    setPlots(next);
    save(next);
  }

  function remove(id: string) {
    const next = plots.filter((p) => p.id !== id);
    setPlots(next);
    save(next);
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

  const sorted = [...plots].sort((a, b) => b.score - a.score);

  return (
    <div className="portfolio">
      <div className="pf-head">📁 Danh mục thửa đất</div>
      {coord && (
        <div className="pf-actions">
          <button onClick={addCurrent} disabled={!terra}>
            💾 Lưu thửa đang xem
          </button>
          <button className="ghost" onClick={exportReport} disabled={exporting}>
            {exporting ? "Đang tạo…" : "🖨️ Xuất báo cáo"}
          </button>
        </div>
      )}
      {plots.length === 0 && (
        <p className="pf-empty">
          Chưa lưu thửa nào. Phân tích một vị trí rồi bấm “Lưu thửa đang xem” để
          so sánh nhiều mảnh đất.
        </p>
      )}
      {sorted.map((p) => (
        <div key={p.id} className="pf-item">
          <button className="pf-load" onClick={() => onLoad(p.lat, p.lon)}>
            <span
              className="pf-grade"
              style={{ background: GRADE_COLOR[p.grade] ?? "#5a6b73" }}
            >
              {p.grade}
            </span>
            <span className="pf-info">
              <span className="pf-name">{p.name}</span>
              <span className="pf-meta">
                {p.score}/100 · {p.lat.toFixed(3)}, {p.lon.toFixed(3)}
                {p.area ? ` · ${p.area} ha` : ""}
              </span>
            </span>
          </button>
          <button className="pf-del" onClick={() => remove(p.id)} title="Xóa">
            ✕
          </button>
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
        <td>${m.is_real ? "🛰️ Dữ liệu thật" : "🧪 Mô hình mẫu"}</td>
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
  <h3>Toàn bộ 14 module</h3>
  <table><thead><tr><th>Module</th><th>Mức</th><th>Nguồn</th><th>Nhận định</th></tr></thead>
  <tbody>${rows}</tbody></table>
  <p class="foot">Nguồn dữ liệu thật: Open-Meteo (dự báo + lịch sử ERA5), NASA POWER, DEM Open-Meteo.
  Module gắn 🧪 là mô hình mẫu (chờ ảnh Sentinel/khảo sát). Kết quả kèm sai số, không đảm bảo 100%.</p>
  </body></html>`;
}
