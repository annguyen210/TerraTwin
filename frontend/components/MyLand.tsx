"use client";

/**
 * "Thửa của tôi" — trang chủ cho người ĐÃ đăng nhập.
 *
 * VÌ SAO CẦN CHO "PHỔ CẬP". Một công cụ người ta phải NHỚ mở thì mở vài lần rồi
 * quên. Một thứ TỰ CANH đất và báo trước khi có chuyện thì người ta mở mỗi ngày
 * — và không rời được. Backend đã có Radar quét nền + kho cảnh báo; màn này đưa
 * đúng thứ đó lên đầu: "TerraTwin đang canh N thửa của bạn, đây là việc sắp tới".
 *
 * Chỉ hiện khi đã đăng nhập VÀ có thửa đã lưu — nếu chưa, để màn "đất của bạn ở
 * đâu" dẫn người dùng phân tích + lưu trước.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ackAlert,
  listAlerts,
  listPlots,
  runRadar,
  type AlertRow,
  type AuthUser,
  type ServerPlot,
} from "@/lib/api";

const GRADE_COLOR: Record<string, string> = {
  A: "#2E9E67", B: "#3aa0a0", C: "#B07A2E", D: "#C2412E",
};
const RISK_COLOR: Record<string, string> = {
  danger: "#C2412E", warning: "#B07A2E", safe: "#2E9E67",
};

export default function MyLand({
  user,
  onOpen,
}: {
  user: AuthUser | null;
  onOpen: (lat: number, lon: number, label: string) => void;
}) {
  const [plots, setPlots] = useState<ServerPlot[]>([]);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [scanning, setScanning] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      const [p, a] = await Promise.all([
        listPlots().catch(() => []),
        listAlerts(true).catch(() => []),
      ]);
      setPlots(p);
      setAlerts(a);
    } finally {
      setLoaded(true);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function scanNow() {
    setScanning(true);
    try {
      await runRadar();
      await refresh();
    } catch {
      /* im lặng — nút này chỉ là tiện, hỏng không được chặn màn */
    } finally {
      setScanning(false);
    }
  }

  async function ack(id: number) {
    setAlerts((xs) => xs.filter((a) => a.id !== id));
    try {
      await ackAlert(id);
    } catch {
      refresh();
    }
  }

  // Chưa đăng nhập, hoặc đăng nhập nhưng chưa lưu thửa nào → nhường màn Start.
  if (!user || (loaded && plots.length === 0)) return null;
  if (!loaded) return null;

  const plotName = (id: number | null) =>
    plots.find((p) => p.id === id)?.name ?? "một thửa";

  return (
    <div className="myland">
      <div className="ml-head">
        <div>
          <b>🛡️ TerraTwin đang canh {plots.length} thửa của bạn</b>
          <p className="ml-brief">
            ☀️{" "}
            {new Date().toLocaleDateString("vi-VN", { weekday: "long", day: "numeric", month: "numeric" })}
            {" · "}
            {alerts.length ? (
              <b style={{ color: "var(--warn)" }}>{alerts.length} cảnh báo mới cần xem</b>
            ) : (
              <b style={{ color: "var(--ok)" }}>tất cả thửa đang an toàn</b>
            )}
          </p>
          <p className="ml-brief-sub">Tự quét nền và báo trước khi có rủi ro — bạn không cần nhớ mở.</p>
        </div>
        <button onClick={scanNow} disabled={scanning}>
          {scanning ? "Đang quét…" : "Quét lại ngay"}
        </button>
      </div>

      {alerts.length > 0 && (
        <div className="ml-alerts">
          <span className="ml-cap">⚠️ {alerts.length} việc sắp tới cần chú ý</span>
          {alerts.map((a) => (
            <div
              key={a.id}
              className="ml-alert"
              style={{ borderLeftColor: RISK_COLOR[a.risk_level] ?? "#5a6b73" }}
            >
              <div className="ml-alert-top">
                <span className="ml-alert-plot">{plotName(a.plot_id)}</span>
                <button className="ml-ack" onClick={() => ack(a.id)}>đã xem</button>
              </div>
              <p className="ml-alert-head">{a.headline}</p>
              {a.recommendation && <p className="ml-alert-do">→ {a.recommendation}</p>}
            </div>
          ))}
        </div>
      )}

      {alerts.length === 0 && (
        <p className="ml-calm">✅ Chưa có rủi ro mới ở các thửa đã lưu. Yên tâm — có gì TerraTwin sẽ báo.</p>
      )}

      <span className="ml-cap">Thửa của bạn</span>
      <div className="ml-plots">
        {plots.map((p) => (
          <button
            key={p.id}
            className="ml-plot"
            onClick={() => onOpen(p.lat, p.lon, p.name)}
          >
            <span
              className="ml-grade"
              style={{ background: GRADE_COLOR[p.grade ?? ""] ?? "#5a6b73" }}
            >
              {p.grade ?? "—"}
            </span>
            <span className="ml-plot-info">
              <span className="ml-plot-name">{p.name}</span>
              <span className="ml-plot-meta">
                {p.lat.toFixed(3)}, {p.lon.toFixed(3)}
                {p.area_ha ? ` · ${p.area_ha} ha` : ""}
              </span>
            </span>
            <span className="ml-open">mở →</span>
          </button>
        ))}
      </div>

      <div className="ml-or"><span>hoặc xem một thửa mới</span></div>
    </div>
  );
}
