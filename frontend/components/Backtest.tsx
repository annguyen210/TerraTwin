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
          {res.success && (
            <div className="bt-tiers">
              {res.lead_days_warning != null && (
                <div className="bt-lead">
                  <b>{res.lead_days_warning}</b>
                  <span>
                    ngày báo trước
                    <br />
                    <small>mức CẢNH BÁO</small>
                  </span>
                </div>
              )}
              {res.lead_days != null && (
                <div className="bt-lead">
                  <b>{res.lead_days}</b>
                  <span>
                    ngày báo trước
                    <br />
                    <small>mức NGUY HIỂM</small>
                  </span>
                </div>
              )}
            </div>
          )}

          {(res.alarm_rate || res.alarm_rate_warning) && (
            <div className="bt-far">
              <b>Tỉ lệ báo động tại điểm này (10 năm ERA5):</b>{" "}
              {res.alarm_rate_warning && (
                <>cảnh báo {res.alarm_rate_warning.alarm_rate_pct}%</>
              )}
              {res.alarm_rate && (
                <> · nguy hiểm {res.alarm_rate.alarm_rate_pct}%</>
              )}
              <div className="bt-far-note">
                Lead time chỉ có nghĩa khi đi kèm con số này — một model luôn hét
                “nguy hiểm” cũng bắt trúng mọi thảm họa nổi tiếng.
              </div>
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
                    background: p.danger
                      ? "#C2412E"
                      : p.warning
                        ? "#B07A2E"
                        : "#3aa0a0",
                  }}
                />
                <span className="bt-bar-label">{p.date.slice(5)}</span>
              </div>
            ))}
          </div>
          <div className="bt-legend">
            <span>
              <i style={{ background: "#B07A2E" }} /> ≥ cảnh báo (
              {res.threshold_warning})
            </span>
            <span>
              <i style={{ background: "#C2412E" }} /> ≥ nguy hiểm ({res.threshold})
            </span>
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
