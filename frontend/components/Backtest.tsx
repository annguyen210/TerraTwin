"use client";

import { useEffect, useState } from "react";
import {
  getBacktests,
  runBacktest,
  type BacktestEvent,
  type BacktestResult,
} from "@/lib/api";

export default function Backtest() {
  const [events, setEvents] = useState<BacktestEvent[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [res, setRes] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getBacktests()
      .then(setEvents)
      .catch(() => setEvents([]));
  }, []);

  async function run(id: string) {
    setActive(id);
    setLoading(true);
    setRes(null);
    try {
      setRes(await runBacktest(id));
    } catch {
      setRes(null);
    } finally {
      setLoading(false);
    }
  }

  if (events.length === 0) return null;

  const max = res?.series
    ? Math.max(...res.series.map((p) => p.value), res.threshold ?? 70, 1)
    : 1;

  return (
    <div className="backtest">
      <div className="bt-head">🔬 Bằng chứng “biết trước” — kiểm chứng bằng thiên tai lịch sử THẬT</div>
      <p className="bt-sub">
        Chạy đúng mô hình cảnh báo trên dữ liệu thời tiết quá khứ (Open-Meteo
        Archive/ERA5). Xem model có báo trước trận thật hay không, và trước mấy ngày.
      </p>
      <div className="bt-events">
        {events.map((e) => (
          <button
            key={e.id}
            className={`bt-ev ${e.id === active ? "on" : ""}`}
            onClick={() => run(e.id)}
          >
            {e.label}
          </button>
        ))}
      </div>

      {loading && <p className="hint">Đang tải dữ liệu lịch sử thật…</p>}

      {res && res.available && (
        <div className="bt-result">
          <div className={`bt-verdict ${res.success ? "ok" : "no"}`}>
            {res.verdict}
          </div>
          {res.lead_days != null && res.success && (
            <div className="bt-lead">
              <b>{res.lead_days}</b>
              <span>ngày báo trước</span>
            </div>
          )}
          <div className="bt-chart">
            {res.series?.map((p) => (
              <div
                className="bt-bar-wrap"
                key={p.date}
                title={`${p.date}: chỉ số ${p.value} · mưa ${p.precip} mm`}
              >
                <div
                  className="bt-bar"
                  style={{
                    height: `${(p.value / max) * 100}%`,
                    background: p.danger ? "#C2412E" : "#3aa0a0",
                  }}
                />
                <span className="bt-bar-label">{p.date.slice(5)}</span>
              </div>
            ))}
          </div>
          <div className="bt-legend">
            <span><i style={{ background: "#C2412E" }} /> ≥ ngưỡng nguy hiểm ({res.threshold})</span>
            <span className="bt-event-mark">▲ sự kiện thật: {res.event_date}</span>
          </div>
          <p className="bt-note">
            {res.note} · Địa hình: {res.terrain} · Nguồn: {res.data_source}
          </p>
        </div>
      )}

      {res && !res.available && (
        <p className="err">{res.message}</p>
      )}
    </div>
  );
}
