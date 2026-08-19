"use client";

import { useState } from "react";
import { scanAll, type ScanResult, type ScanModule } from "@/lib/api";

const RISK_COLOR: Record<string, string> = {
  safe: "#2E9E67",
  warning: "#B07A2E",
  danger: "#C2412E",
  unknown: "#5a6b73",
  not_implemented: "#5a6b73",
};
const RISK_LABEL: Record<string, string> = {
  safe: "An toàn",
  warning: "Cảnh báo",
  danger: "Nguy hiểm",
  unknown: "—",
  not_implemented: "—",
};

export default function Overview({
  lat,
  lon,
  area,
  onSelectModule,
}: {
  lat: number;
  lon: number;
  area?: number;
  onSelectModule?: (id: string) => void;
}) {
  const [data, setData] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setErr(null);
    try {
      setData(await scanAll(lat, lon, area));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="overview">
      <button className="scan-btn" onClick={run} disabled={loading}>
        {loading ? "Đang quét 14 module…" : "🛰️ Quét toàn cảnh thửa đất (14 module)"}
      </button>
      {err && <p className="err">{err}</p>}

      {data && (
        <>
          <div className="ov-alerts">
            <div className="ov-alerts-head">
              {data.alerts.length > 0
                ? `⚠️ ${data.alerts.length} cảnh báo (dữ liệu thật) cần chú ý`
                : "✅ Không có cảnh báo từ dữ liệu thật"}
            </div>
            {data.alerts.map((m) => (
              <div
                key={m.id}
                className="ov-alert"
                style={{ borderLeftColor: RISK_COLOR[m.risk_level] }}
                onClick={() => onSelectModule?.(m.id)}
              >
                <div className="ov-alert-top">
                  <span>{m.icon} {m.name}</span>
                  <span
                    className="ov-alert-lvl"
                    style={{ color: RISK_COLOR[m.risk_level] }}
                  >
                    {RISK_LABEL[m.risk_level]}
                  </span>
                </div>
                <div className="ov-alert-head">{m.headline}</div>
                <div className="ov-alert-rec">→ {m.recommendation}</div>
              </div>
            ))}
          </div>

          <div className="ov-grid-head">
            Toàn bộ 14 module · 🛰️ dữ liệu thật · 🧪 ước lượng vật lý · ⏳ chưa
            đưa số (chờ ảnh Sentinel / ngoài phạm vi vùng)
          </div>
          <div className="ov-grid">
            {data.modules.map((m) => (
              <button
                key={m.id}
                className="ov-tile"
                style={{ borderColor: RISK_COLOR[m.risk_level] }}
                onClick={() => onSelectModule?.(m.id)}
                title={m.headline}
              >
                <span className="ov-tile-ic">{m.icon}</span>
                <span className="ov-tile-nm">{m.name}</span>
                <span
                  className="ov-tile-lvl"
                  style={{ background: RISK_COLOR[m.risk_level] }}
                >
                  {RISK_LABEL[m.risk_level]}
                </span>
                <span className="ov-tile-src">
                  {m.is_real ? "🛰️" : m.risk_level === "unknown" ? "⏳" : "🧪"}
                </span>
              </button>
            ))}
          </div>
          <p className="ov-foot">
            Quét lúc {new Date(data.generated_at).toLocaleString("vi-VN")} ·{" "}
            {Math.round(data.real_data_ratio * 100)}% hiểm họa dùng dữ liệu thật
          </p>
          {data.skipped_heavy && data.skipped_heavy.length > 0 && (
            <p className="ov-skipped">
              Không chạy trong lượt toàn cảnh:{" "}
              {data.skipped_heavy.map((id) => (
                <button key={id} onClick={() => onSelectModule?.(id)}>
                  {id}
                </button>
              ))}{" "}
              — mô-đun này quét cả một vùng nên mất khoảng mười giây, mở riêng
              khi cần.
            </p>
          )}
        </>
      )}
    </div>
  );
}
