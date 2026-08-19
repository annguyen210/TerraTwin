"use client";

/**
 * C04 Time-Lapse — rủi ro của chính thửa này đã đổi thế nào qua 10 năm.
 *
 * Vẽ cột chứ không vẽ đường: người dùng cần thấy NĂM NÀO chạm ngưỡng nguy hiểm,
 * và cột tô màu theo mức trả lời câu đó ngay từ cái nhìn đầu tiên. Một đường
 * cong mượt trông đẹp hơn nhưng phải dò trục mới biết năm nào vượt ngưỡng.
 */

import { useState } from "react";
import { runTimeLapse, type TimeLapseResult } from "@/lib/api";

const HAZARDS = [
  { id: "flood", name: "Lũ / ngập" },
  { id: "drought", name: "Hạn" },
  { id: "wildfire", name: "Cháy rừng" },
  { id: "landslide", name: "Sạt lở" },
];

const COLOR: Record<string, string> = {
  danger: "#C2412E",
  warning: "#B07A2E",
  safe: "#2E9E67",
};

const TREND: Record<string, { icon: string; text: string; color: string }> = {
  worsening: { icon: "↗", text: "đang xấu đi", color: "#C2412E" },
  improving: { icon: "↘", text: "đang tốt lên", color: "#2E9E67" },
  stable: { icon: "→", text: "gần như không đổi", color: "#9fb2bf" },
};

export default function TimeLapse({
  moduleId,
  lat,
  lon,
}: {
  moduleId: string;
  lat: number;
  lon: number;
}) {
  // Module đang chọn có thể không phải hiểm họa (vd. điện mặt trời) — khi đó
  // mặc định về lũ thay vì hiện lỗi 404 khó hiểu.
  const initial = HAZARDS.some((h) => h.id === moduleId) ? moduleId : "flood";
  const [mid, setMid] = useState(initial);
  const [data, setData] = useState<TimeLapseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(id: string) {
    setBusy(true);
    setErr(null);
    setData(null);
    try {
      setData(await runTimeLapse(id, lat, lon, 10));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const max = data?.frames?.length
    ? Math.max(...data.frames.map((f) => f.peak), data.warning ?? 70)
    : 100;
  const tr = data?.trend ? TREND[data.trend] : null;

  return (
    <div className="pan">
      <div className="pan-head">⏳ Tua 10 năm — rủi ro thửa này đã đổi thế nào</div>

      <div className="pan-controls">
        <select value={mid} onChange={(e) => setMid(e.target.value)}>
          {HAZARDS.map((h) => (
            <option key={h.id} value={h.id}>
              {h.name}
            </option>
          ))}
        </select>
        <button className="pan-go" disabled={busy} onClick={() => run(mid)}>
          {busy ? "Đang chạy 10 năm…" : "Tua lại"}
        </button>
      </div>

      {err && <p className="pan-err">⚠️ {err}</p>}

      {data?.available && data.frames && (
        <>
          <p className="pan-line">{data.headline}</p>

          {tr && (
            <p className="tl-trend" style={{ color: tr.color }}>
              {tr.icon} Xu thế {tr.text} ({data.trend_change! > 0 ? "+" : ""}
              {data.trend_change} {data.unit}) · trung bình{" "}
              {data.early_mean} → {data.late_mean}
            </p>
          )}

          <div className="tl-chart">
            {data.frames.map((f) => (
              <div key={f.year} className="tl-col" title={`${f.year}: ${f.peak} ${data.unit}`}>
                <div className="tl-bar-wrap">
                  <div
                    className="tl-bar"
                    style={{
                      height: `${Math.max(3, (f.peak / max) * 100)}%`,
                      background: COLOR[f.risk_level] ?? "#5fcb8e",
                    }}
                  />
                </div>
                <span className="tl-year">{String(f.year).slice(2)}</span>
              </div>
            ))}
          </div>

          <div className="tl-legend">
            <span>
              <i style={{ background: COLOR.safe }} /> an toàn
            </span>
            <span>
              <i style={{ background: COLOR.warning }} /> cảnh báo
            </span>
            <span>
              <i style={{ background: COLOR.danger }} /> nguy hiểm
            </span>
          </div>

          <p className="pan-caveat">{data.caveat}</p>
          <p className="pan-method">{data.method}</p>
        </>
      )}
    </div>
  );
}
