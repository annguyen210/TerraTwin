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
import { useLang } from "@/lib/i18n";

const HAZARDS: { id: string; vi: string; en: string }[] = [
  { id: "flood", vi: "Lũ / ngập", en: "Flood" },
  { id: "drought", vi: "Hạn", en: "Drought" },
  { id: "wildfire", vi: "Cháy rừng", en: "Wildfire" },
  { id: "landslide", vi: "Sạt lở", en: "Landslide" },
];

const COLOR: Record<string, string> = {
  danger: "#C2412E",
  warning: "#B07A2E",
  safe: "#2E9E67",
};

const TREND: Record<string, { icon: string; vi: string; en: string; color: string }> = {
  worsening: { icon: "↗", vi: "đang xấu đi", en: "worsening", color: "#C2412E" },
  improving: { icon: "↘", vi: "đang tốt lên", en: "improving", color: "#2E9E67" },
  stable: { icon: "→", vi: "gần như không đổi", en: "nearly unchanged", color: "#9fb2bf" },
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
  const { t } = useLang();
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
      <div className="pan-head">⏳ {t("Tua 10 năm — rủi ro thửa này đã đổi thế nào", "10-year rewind — how this plot's risk has changed")}</div>

      <div className="pan-controls">
        <select value={mid} onChange={(e) => setMid(e.target.value)}>
          {HAZARDS.map((h) => (
            <option key={h.id} value={h.id}>
              {t(h.vi, h.en)}
            </option>
          ))}
        </select>
        <button className="pan-go" disabled={busy} onClick={() => run(mid)}>
          {busy ? t("Đang chạy 10 năm…", "Running 10 years…") : t("Tua lại", "Rewind again")}
        </button>
      </div>

      {err && <p className="pan-err">⚠️ {err}</p>}

      {data?.available && data.frames && (
        <>
          <p className="pan-line">{data.headline}</p>

          {tr && (
            <p className="tl-trend" style={{ color: tr.color }}>
              {tr.icon} {t("Xu thế", "Trend")} {t(tr.vi, tr.en)} ({data.trend_change! > 0 ? "+" : ""}
              {data.trend_change} {data.unit}) · {t("trung bình", "average")}{" "}
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
              <i style={{ background: COLOR.safe }} /> {t("an toàn", "safe")}
            </span>
            <span>
              <i style={{ background: COLOR.warning }} /> {t("cảnh báo", "warning")}
            </span>
            <span>
              <i style={{ background: COLOR.danger }} /> {t("nguy hiểm", "danger")}
            </span>
          </div>

          <p className="pan-caveat">{data.caveat}</p>
          <p className="pan-method">{data.method}</p>
        </>
      )}
    </div>
  );
}
