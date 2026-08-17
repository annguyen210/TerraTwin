"use client";

import { useEffect, useState } from "react";
import {
  runWhatIf,
  WHATIF_MODULES,
  type WhatIfResult,
} from "@/lib/api";

const RISK_COLOR: Record<string, string> = {
  safe: "#2E9E67",
  warning: "#B07A2E",
  danger: "#C2412E",
};

export default function WhatIf({
  moduleId,
  lat,
  lon,
}: {
  moduleId: string;
  lat: number;
  lon: number;
}) {
  const [data, setData] = useState<WhatIfResult | null>(null);
  const [loading, setLoading] = useState(false);

  const eligible = WHATIF_MODULES.includes(moduleId);

  useEffect(() => {
    if (!eligible) {
      setData(null);
      return;
    }
    let alive = true;
    setLoading(true);
    runWhatIf(moduleId, lat, lon)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [moduleId, lat, lon, eligible]);

  if (!eligible) return null;

  const max = data
    ? Math.max(
        ...data.scenarios.flatMap((s) => s.series.map((p) => p.value)),
        data.warning,
        1,
      )
    : 1;

  return (
    <div className="whatif">
      <div className="wi-head">🔮 Kịch bản song song — điều gì xảy ra NẾU…?</div>
      {loading && <p className="hint">Đang mô phỏng các tương lai…</p>}
      {data && (
        <>
          <p className="wi-note">{data.note}</p>
          <div className="wi-scenarios">
            {data.scenarios.map((s) => {
              const danger = s.peak >= data.warning;
              return (
                <div key={s.label} className="wi-sc">
                  <div className="wi-sc-top">
                    <span className="wi-sc-label">{s.label}</span>
                    <span
                      className="wi-sc-peak"
                      style={{
                        color: danger ? RISK_COLOR.danger : RISK_COLOR.safe,
                      }}
                    >
                      đỉnh {s.peak}
                      {data.unit === "%" ? "%" : ""}
                    </span>
                  </div>
                  <div className="wi-bars">
                    {s.series.map((p) => (
                      <div
                        key={p.day}
                        className="wi-bar"
                        title={`${p.date}: ${p.value}`}
                        style={{
                          height: `${(p.value / max) * 100}%`,
                          background: RISK_COLOR[p.risk] ?? "#5a6b73",
                        }}
                      />
                    ))}
                  </div>
                  {s.first_danger_date && (
                    <div className="wi-sc-danger">
                      ⚠️ Vượt ngưỡng nguy hiểm từ {s.first_danger_date.slice(5)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <p className="wi-foot">
            Ngưỡng: an toàn &lt;{data.safe} · cảnh báo {data.safe}–{data.warning} ·
            nguy hiểm ≥{data.warning}
          </p>
        </>
      )}
    </div>
  );
}
