"use client";

import { useState } from "react";
import { runHeatmap, WHATIF_MODULES, type HeatmapResult } from "@/lib/api";

export default function Heatmap({
  moduleId,
  lat,
  lon,
  onResult,
}: {
  moduleId: string;
  lat: number;
  lon: number;
  onResult: (h: HeatmapResult | null) => void;
}) {
  const [data, setData] = useState<HeatmapResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [side, setSide] = useState(7);
  const [radius, setRadius] = useState(8);

  const eligible = WHATIF_MODULES.includes(moduleId);
  if (!eligible) return null;

  async function run() {
    setLoading(true);
    setErr(null);
    try {
      const d = await runHeatmap(moduleId, lat, lon, side, radius);
      setData(d);
      onResult(d);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function clear() {
    setData(null);
    onResult(null);
  }

  return (
    <div className="heat">
      <div className="heat-head">🗺️ Bản đồ nhiệt rủi ro quanh thửa</div>

      <div className="heat-controls">
        <label>
          Lưới
          <select value={side} onChange={(e) => setSide(Number(e.target.value))}>
            {[5, 7, 9, 11].map((n) => (
              <option key={n} value={n}>
                {n}×{n}
              </option>
            ))}
          </select>
        </label>
        <label>
          Bán kính
          <select value={radius} onChange={(e) => setRadius(Number(e.target.value))}>
            {[3, 5, 8, 15, 25].map((n) => (
              <option key={n} value={n}>
                {n} km
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="heat-actions">
        <button onClick={run} disabled={loading}>
          {loading ? "Đang quét lưới…" : "Quét vùng"}
        </button>
        {data && (
          <button className="ghost" onClick={clear}>
            Xóa lớp
          </button>
        )}
      </div>

      {err && <p className="err">{err}</p>}

      {data && (
        <>
          <p className="heat-line">{data.headline}</p>
          <div className="heat-legend">
            <span>
              <i style={{ background: "#2E9E67" }} /> an toàn
            </span>
            <span>
              <i style={{ background: "#B07A2E" }} /> cảnh báo
            </span>
            <span>
              <i style={{ background: "#C2412E" }} /> nguy hiểm
            </span>
          </div>
          {!data.calibrated && (
            <p className="heat-warn">
              ⚠️ Chưa hiệu chuẩn được theo khí hậu vùng — con số có thể báo động
              nhiều hơn thực tế.
            </p>
          )}
          <p className="heat-caveat">{data.caveat}</p>
          {data.cached && <p className="heat-caveat">Kết quả lấy từ bộ nhớ đệm.</p>}
        </>
      )}
    </div>
  );
}
