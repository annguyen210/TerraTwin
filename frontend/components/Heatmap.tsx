"use client";

import { useEffect, useState } from "react";
import { runHeatmap, WHATIF_MODULES, type HeatmapResult } from "@/lib/api";
import { useLang } from "@/lib/i18n";

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
  const { t } = useLang();
  const [data, setData] = useState<HeatmapResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [side, setSide] = useState(7);
  const [radius, setRadius] = useState(8);
  // Kiểm A–Z lần 2 (22/11/2026): lần đầu ở thửa mới ~37 giây sau một vòng xoay câm. Thời gian nằm ở việc tải mưa cho cả
  // lưới (1–2 lượt gọi đa toạ độ) + khí hậu 10 năm của tâm lưới, KHÔNG phải tính từng ô — nên không có "n/49 ô" thật để
  // báo. Báo đúng điều đang xảy ra + số giây đã chờ; 3 thửa demo được tính sẵn (cron /api/climate/warm).
  const [giay, setGiay] = useState(0);
  useEffect(() => {
    if (!loading) { setGiay(0); return; }
    const id = setInterval(() => setGiay((g) => g + 1), 1000);
    return () => clearInterval(id);
  }, [loading]);

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
      <div className="heat-head">🗺️ {t("Bản đồ nhiệt rủi ro quanh thửa", "Risk heatmap around this plot")}</div>

      <div className="heat-controls">
        <label>
          {t("Lưới", "Grid")}
          <select value={side} onChange={(e) => setSide(Number(e.target.value))}>
            {[5, 7, 9, 11].map((n) => (
              <option key={n} value={n}>
                {n}×{n}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("Bán kính", "Radius")}
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
          {loading ? t("Đang quét lưới…", "Scanning grid…") : t("Quét vùng", "Scan area")}
        </button>
        {loading && (
          <span className="heat-wait" role="status">
            {t(`Đang tải mưa 7 ngày cho ${side * side} ô và khí hậu 10 năm của vùng · đã chờ ${giay} giây. Lần đầu ở vùng mới thường 30–40 giây; lần sau dưới 1 giây.`,
               `Loading 7-day rain for ${side * side} cells and this area's 10-year climate · ${giay}s so far. The first time in a new area usually takes 30–40 s; after that under 1 s.`)}
          </span>
        )}
        {data && (
          <button className="ghost" onClick={clear}>
            {t("Xóa lớp", "Clear layer")}
          </button>
        )}
      </div>

      {err && <p className="err">{err}</p>}

      {data && (
        <>
          <p className="heat-line">{data.headline}</p>
          <div className="heat-legend">
            <span>
              <i style={{ background: "#2E9E67" }} /> {t("an toàn", "safe")}
            </span>
            <span>
              <i style={{ background: "#B07A2E" }} /> {t("cảnh báo", "warning")}
            </span>
            <span>
              <i style={{ background: "#C2412E" }} /> {t("nguy hiểm", "danger")}
            </span>
          </div>
          {!data.calibrated && (
            <p className="heat-warn">
              ⚠️ {t("Chưa hiệu chuẩn được theo khí hậu vùng — con số có thể báo động nhiều hơn thực tế.",
                    "Not yet calibrated to regional climate — numbers may over-alarm compared to reality.")}
            </p>
          )}
          <p className="heat-caveat">{data.caveat}</p>
          {data.cached && <p className="heat-caveat">{t("Kết quả lấy từ bộ nhớ đệm.", "Result served from cache.")}</p>}
        </>
      )}
    </div>
  );
}
