"use client";

import { useEffect, useState } from "react";
import {
  getBacktests,
  runBacktest,
  type BacktestEvent,
  type BacktestResult,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function Backtest() {
  const { t, lang } = useLang();
  const [events, setEvents] = useState<BacktestEvent[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [res, setRes] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getBacktests()
      .then(setEvents)
      .catch(() => setEvents([]));
  }, [lang]);

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
      <div className="bt-head">🔬 {t("Bằng chứng “biết trước” — kiểm chứng bằng thiên tai lịch sử THẬT",
                                     "“Early warning” evidence — validated on REAL historical disasters")}</div>
      <p className="bt-sub">
        {t("Chạy đúng mô hình cảnh báo trên dữ liệu thời tiết quá khứ (Open-Meteo Archive/ERA5). Xem model có báo trước trận thật hay không, và trước mấy ngày.",
           "Runs the same alert model on past weather (Open-Meteo Archive/ERA5). See whether it warned of the real event, and how many days ahead.")}
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

      {loading && <p className="hint">{t("Đang tải dữ liệu lịch sử thật…", "Loading real historical data…")}</p>}

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
                    {t("ngày báo trước", "days early")}
                    <br />
                    <small>{t("mức CẢNH BÁO", "at WARNING")}</small>
                  </span>
                </div>
              )}
              {res.lead_days != null && (
                <div className="bt-lead">
                  <b>{res.lead_days}</b>
                  <span>
                    {t("ngày báo trước", "days early")}
                    <br />
                    <small>{t("mức NGUY HIỂM", "at DANGER")}</small>
                  </span>
                </div>
              )}
            </div>
          )}

          {(res.alarm_rate || res.alarm_rate_warning) && (
            <div className="bt-far">
              <b>{t("Tỉ lệ báo động tại điểm này (10 năm ERA5):", "Alarm rate at this point (10y ERA5):")}</b>{" "}
              {res.alarm_rate_warning && (
                <>{t("cảnh báo", "warning")} {res.alarm_rate_warning.alarm_rate_pct}%</>
              )}
              {res.alarm_rate && (
                <> · {t("nguy hiểm", "danger")} {res.alarm_rate.alarm_rate_pct}%</>
              )}
              <div className="bt-far-note">
                {t("Lead time chỉ có nghĩa khi đi kèm con số này — một model luôn hét “nguy hiểm” cũng bắt trúng mọi thảm họa nổi tiếng.",
                   "Lead time only matters alongside this number — a model that always screams “danger” also catches every famous disaster.")}
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
              <i style={{ background: "#B07A2E" }} /> ≥ {t("cảnh báo", "warning")} (
              {res.threshold_warning})
            </span>
            <span>
              <i style={{ background: "#C2412E" }} /> ≥ {t("nguy hiểm", "danger")} ({res.threshold})
            </span>
            <span className="bt-event-mark">▲ {t("sự kiện thật:", "real event:")} {res.event_date}</span>
          </div>
          <p className="bt-note">
            {res.note} · {t("Địa hình:", "Terrain:")} {res.terrain} · {t("Nguồn:", "Source:")} {res.data_source}
          </p>
        </div>
      )}

      {res && !res.available && (
        <p className="err">{res.message}</p>
      )}
    </div>
  );
}
