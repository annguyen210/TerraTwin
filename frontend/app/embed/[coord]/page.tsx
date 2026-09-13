"use client";

/**
 * M3 — WIDGET NHÚNG. Một thẻ rủi ro gọn cho website khác nhúng qua <iframe>:
 *   <iframe src="https://terratwin-web.onrender.com/embed/16.46,107.59"
 *           width="320" height="220" style="border:0"></iframe>
 *
 * Không có app chrome, không đăng nhập, chỉ TerraScore + mức rủi ro cao nhất +
 * link về bản đầy đủ. Đây là kênh phân phối: mỗi trang nhúng là một cửa vào.
 * URL chỉ chứa TOẠ ĐỘ (dữ liệu về ĐẤT, không về người) — công khai an toàn.
 */
import { useEffect, useState } from "react";
import { scanAll, type ScanResult } from "@/lib/api";

const GRADE: Record<string, string> = {
  A: "#2E9E67", B: "#3aa0a0", C: "#B07A2E", D: "#C2412E",
};
const RISK: Record<string, [string, string]> = {
  danger: ["Nguy hiểm", "#C2412E"],
  warning: ["Cảnh báo", "#B07A2E"],
  safe: ["An toàn", "#2E9E67"],
};

export default function EmbedPage({ params }: { params: { coord: string } }) {
  const nums = decodeURIComponent(params.coord).match(/-?\d+(\.\d+)?/g) || [];
  const lat = parseFloat(nums[0] ?? "");
  const lon = parseFloat(nums[1] ?? "");
  const valid = Number.isFinite(lat) && Number.isFinite(lon);
  const [d, setD] = useState<ScanResult | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    if (!valid) { setErr(true); return; }
    let live = true;
    scanAll(lat, lon).then((r) => live && setD(r)).catch(() => live && setErr(true));
    return () => { live = false; };
  }, [lat, lon, valid]);

  const site = process.env.NEXT_PUBLIC_SITE_URL || "https://terratwin-web.onrender.com";
  const full = `${site}/plot/${lat},${lon}`;

  const wrap: React.CSSProperties = {
    fontFamily: "system-ui, sans-serif", padding: 14, boxSizing: "border-box",
    border: "1px solid #d7ddd8", borderRadius: 10, background: "#fff", color: "#0f1411",
    height: "100%", display: "flex", flexDirection: "column", gap: 8,
  };

  if (err) return <div style={wrap}><b>◵ TerraTwin</b><p style={{ margin: 0, fontSize: 13, color: "#66716a" }}>Toạ độ không hợp lệ.</p></div>;
  if (!d) return <div style={wrap}><b>◵ TerraTwin</b><p style={{ margin: 0, fontSize: 13, color: "#66716a" }}>Đang kiểm rủi ro…</p></div>;

  const topRisk = d.alerts.some((a) => a.risk_level === "danger") ? "danger"
    : d.alerts.some((a) => a.risk_level === "warning") ? "warning" : "safe";
  const [riskLabel, riskColor] = RISK[topRisk];
  const g = d.terrascore.grade;

  return (
    <a href={full} target="_blank" rel="noopener" style={{ textDecoration: "none", color: "inherit", display: "block", height: "100%" }}>
      <div style={wrap}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <b style={{ fontSize: 14 }}>◵ TerraTwin</b>
          <span style={{ fontSize: 11, color: "#66716a" }}>{lat.toFixed(3)}, {lon.toFixed(3)}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 54, height: 54, borderRadius: "50%", border: `3px solid ${GRADE[g] ?? "#567"}`,
            color: GRADE[g] ?? "#567", display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", fontWeight: 800, flexShrink: 0 }}>
            <span style={{ fontSize: 18, lineHeight: 1 }}>{d.terrascore.score}</span>
            <span style={{ fontSize: 9 }}>/100</span>
          </div>
          <div>
            <div style={{ fontWeight: 700, color: GRADE[g] ?? "#567" }}>TerraScore hạng {g}</div>
            <div style={{ fontSize: 13 }}>Rủi ro 7 ngày tới:{" "}
              <b style={{ color: riskColor }}>{riskLabel}</b></div>
          </div>
        </div>
        <div style={{ marginTop: "auto", fontSize: 11, color: "#66716a" }}>
          Dữ liệu vệ tinh & khí hậu thật · bấm để xem đầy đủ →
        </div>
      </div>
    </a>
  );
}
