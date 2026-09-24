"use client";

import { useEffect, useState } from "react";
import {
  getProbability,
  runAnomaly,
  runExplain,
  runGoalSeek,
  runTimeMachine,
  WHATIF_MODULES,
  type AnomalyResult,
  type ExplainResult,
  type GoalSeekResult,
  type ProbForecast,
  type TimeMachineResult,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

type Tab = "explain" | "goal" | "time" | "anomaly";

const TABS: { id: Tab; label_vi: string; label_en: string; hazardOnly: boolean }[] = [
  { id: "explain", label_vi: "🧠 Vì sao", label_en: "🧠 Why", hazardOnly: true },
  { id: "goal", label_vi: "🎯 Cần gì để an toàn", label_en: "🎯 What it takes to be safe", hazardOnly: true },
  { id: "time", label_vi: "⏳ Xác suất từ lịch sử", label_en: "⏳ Probability from history", hazardOnly: true },
  { id: "anomaly", label_vi: "📈 Bất thường", label_en: "📈 Anomalies", hazardOnly: false },
];

const LEVEL_COLOR: Record<string, string> = {
  normal: "#2E9E67",
  notable: "#3aa0a0",
  anomaly: "#B07A2E",
  extreme: "#C2412E",
};

function Loading() {
  const { t } = useLang();
  return <p className="hint">{t("Đang tính…", "Computing…")}</p>;
}

function Unavailable({ msg }: { msg?: string }) {
  const { t } = useLang();
  return <p className="in-empty">{msg ?? t("Chưa có dữ liệu cho mục này.", "No data for this yet.")}</p>;
}

/* ---------- S07 Causal Explain ---------- */
function ExplainView({ d }: { d: ExplainResult }) {
  const { t } = useLang();
  if (!d.available) return <Unavailable msg={d.message} />;
  const max = Math.max(...d.factors.map((f) => f.contribution), 1);
  return (
    <>
      <p className="in-head">{d.headline}</p>
      {d.factors.map((f) => (
        <div key={f.factor} className="in-factor">
          <div className="in-factor-top">
            <span>{f.factor}</span>
            <b>{f.share_pct}%</b>
          </div>
          <div className="in-track">
            <div
              className="in-fill"
              style={{ width: `${Math.max(0, (f.contribution / max) * 100)}%` }}
            />
          </div>
          <div className="in-note">
            {t("Bỏ yếu tố này → chỉ số còn", "Remove this factor → the index would be")} {f.peak_without}. {f.note}
          </div>
        </div>
      ))}
      <p className="in-foot">
        {d.terrain} · {t("ngày mưa lớn nhất", "wettest day")} {d.wettest_day?.date.slice(5)} (
        {d.wettest_day?.precip_mm} mm)
      </p>
      <p className="in-method">{d.method}</p>
    </>
  );
}

/* ---------- S03 Goal-Seek ---------- */
function GoalView({ d }: { d: GoalSeekResult }) {
  const { t } = useLang();
  if (!d.available) return <Unavailable msg={d.message} />;
  return (
    <>
      <p className="in-head">{d.headline}</p>
      {d.levers.map((l) => (
        <div
          key={l.lever}
          className="in-lever"
          style={{ borderLeftColor: l.feasible ? "#2E9E67" : "#C2412E" }}
        >
          <div className="in-lever-top">
            {l.lever} {l.feasible ? "" : `· ${t("không đủ một mình", "not enough on its own")}`}
          </div>
          <div className="in-lever-ans">{l.answer}</div>
        </div>
      ))}
      {d.combined && (
        <div className="in-lever" style={{ borderLeftColor: "#B07A2E" }}>
          <div className="in-lever-top">{t("Phương án kết hợp", "Combined option")}</div>
          <div className="in-lever-ans">{d.combined.answer}</div>
        </div>
      )}
      <p className="in-method">{d.method}</p>
    </>
  );
}

/* ---------- S02 Time Machine ---------- */
function TimeView({ d }: { d: TimeMachineResult }) {
  const { t } = useLang();
  if (!d.available) return <Unavailable msg={d.message} />;
  const max = Math.max(...d.members.map((m) => m.peak), d.threshold_warning ?? 70, 1);
  return (
    <>
      <p className="in-head">{d.headline}</p>
      <div className="in-prob">
        <div className="in-prob-big">{d.prob_danger_pct}%</div>
        <div className="in-prob-txt">
          {t("khả năng vượt ngưỡng nguy hiểm", "chance of exceeding the danger threshold")}
          <br />
          <small>
            {d.from_year}–{d.to_year} · P10 {d.p10} · P50 {d.p50} · P90 {d.p90}
          </small>
        </div>
      </div>
      <div className="in-years">
        {d.members.map((m) => (
          <div
            key={m.year}
            className="in-year"
            title={`${m.year}: ${t("đỉnh", "peak")} ${m.peak}, ${t("mưa", "rain")} ${m.rain_total_mm} mm`}
          >
            <div className="in-year-track">
              <div
                className="in-year-bar"
                style={{
                  height: `${(m.peak / max) * 100}%`,
                  background: m.danger ? "#C2412E" : m.warning ? "#B07A2E" : "#2E9E67",
                }}
              />
            </div>
            <span className="in-year-lbl">{String(m.year).slice(2)}</span>
          </div>
        ))}
      </div>
      <p className="in-foot">
        {t("Xấu nhất", "Worst")} {d.worst_year?.year} ({t("đỉnh", "peak")} {d.worst_year?.peak}) · {t("nhẹ nhất", "mildest")}{" "}
        {d.best_year?.year} ({t("đỉnh", "peak")} {d.best_year?.peak})
      </p>
      <p className="in-method">{d.method}</p>
    </>
  );
}

/* ---------- C10 Anomaly ---------- */
function AnomalyView({ d }: { d: AnomalyResult }) {
  const { t } = useLang();
  if (!d.available) return <Unavailable msg={d.message} />;
  return (
    <>
      <p className="in-head">{d.headline}</p>
      {d.metrics.map((m) => (
        <div key={m.key} className="in-metric">
          <div className="in-metric-top">
            <span>{m.label}</span>
            <b style={{ color: LEVEL_COLOR[m.level] }}>
              {m.current} {m.unit}
            </b>
          </div>
          <div className="in-metric-sub">
            {t("TB cùng kỳ", "Same-period average")} {m.normal_mean} {m.unit} · {t("cao hơn", "higher than")} {m.percentile}% {t("số năm", "of years")}
            {m.z_score != null && <> · z={m.z_score}</>}
          </div>
        </div>
      ))}
      <p className="in-foot">
        {t("Nền khí hậu", "Climate baseline")} {d.from_year}–{d.to_year} ({d.years} {t("năm", "years")}) {t("tại chính toạ độ này", "for this exact coordinate")}
      </p>
      <p className="in-method">{d.method}</p>
    </>
  );
}

/* ---------- A3 Dự báo xác suất từ tổ hợp (dải quạt P10–P90 + câu tiếng người) ---------- */
function ForecastProbability({ moduleId, lat, lon }: {
  moduleId: string; lat: number; lon: number;
}) {
  const { t } = useLang();
  const [d, setD] = useState<ProbForecast | null>(null);
  useEffect(() => {
    let alive = true;
    setD(null);
    getProbability(moduleId, lat, lon).then((r) => alive && setD(r)).catch(() => {});
    return () => { alive = false; };
  }, [moduleId, lat, lon]);

  if (!d || !d.available || d.p10 == null || d.p90 == null) return null;
  // Dải 0..100 chỉ số; đánh dấu vùng P10–P90 và điểm P50. Ngưỡng 40/70 vẽ mờ.
  const clamp = (x: number) => Math.max(0, Math.min(100, x));
  const left = clamp(d.p10), right = clamp(d.p90), mid = clamp(d.p50 ?? 0);
  const warn = (d.prob_exceed_warning ?? 0);
  const tone = warn >= 50 ? "#C2412E" : warn >= 20 ? "#B07A2E" : "#2E9E67";
  return (
    <div style={{ margin: "0 0 12px", padding: "11px 14px", borderRadius: 8,
      background: "var(--surface-2, #f8faf7)", border: "1px solid var(--line, #d7ddd8)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10 }}>
        <b style={{ fontSize: 13.5 }}>🎲 {t("Xác suất 7 ngày tới", "7-day probability")}</b>
        <span style={{ fontSize: 11, color: "var(--muted,#66716a)" }}>{d.members} {t("thành viên tổ hợp", "ensemble members")}</span>
      </div>
      <p style={{ margin: "5px 0 8px", fontSize: 14, fontWeight: 600, color: tone }}>{d.sentence}</p>
      {/* dải quạt */}
      <div style={{ position: "relative", height: 12, borderRadius: 99,
        background: "var(--line-2, #e8ece8)", overflow: "hidden" }}>
        {/* ngưỡng nguy hiểm 70 */}
        <div style={{ position: "absolute", left: "70%", top: 0, bottom: 0, width: 1, background: "#C2412E", opacity: .4 }} />
        {/* dải P10–P90 */}
        <div style={{ position: "absolute", left: `${left}%`, width: `${Math.max(2, right - left)}%`,
          top: 0, bottom: 0, background: tone, opacity: .5 }} />
        {/* P50 */}
        <div style={{ position: "absolute", left: `calc(${mid}% - 1px)`, top: -2, bottom: -2, width: 2, background: tone }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--muted,#66716a)", marginTop: 3 }}>
        <span>P10 {d.p10}</span><span>P50 {d.p50}</span><span>P90 {d.p90}</span>
      </div>
    </div>
  );
}

export default function Insights({
  moduleId,
  lat,
  lon,
}: {
  moduleId: string;
  lat: number;
  lon: number;
}) {
  const { t, lang } = useLang();
  const isHazard = WHATIF_MODULES.includes(moduleId);
  const tabs = TABS.filter((tb) => !tb.hazardOnly || isHazard);
  const [tab, setTab] = useState<Tab>(isHazard ? "explain" : "anomaly");
  const [data, setData] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tabs.some((tb) => tb.id === tab)) setTab(isHazard ? "explain" : "anomaly");
  }, [isHazard]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    setData(null);
    const call =
      tab === "explain"
        ? runExplain(moduleId, lat, lon)
        : tab === "goal"
          ? runGoalSeek(moduleId, lat, lon)
          : tab === "time"
            ? runTimeMachine(moduleId, lat, lon)
            : runAnomaly(lat, lon);
    call
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setErr(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [tab, moduleId, lat, lon]);

  return (
    <div className="insights">
      <div className="in-head-row">🔬 {t("Phân tích sâu", "Deep analysis")}</div>
      {/* A3 — xác suất 7 ngày tới, nổi bật trên cùng vì đó là số quyết định. */}
      {isHazard && <ForecastProbability moduleId={moduleId} lat={lat} lon={lon} />}
      <div className="in-tabs">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            className={tab === tb.id ? "on" : ""}
            onClick={() => setTab(tb.id)}
          >
            {lang === "en" ? tb.label_en : tb.label_vi}
          </button>
        ))}
      </div>
      {loading && <Loading />}
      {err && <p className="err">{err}</p>}
      {!loading && !err && data != null && (
        <>
          {tab === "explain" && <ExplainView d={data as ExplainResult} />}
          {tab === "goal" && <GoalView d={data as GoalSeekResult} />}
          {tab === "time" && <TimeView d={data as TimeMachineResult} />}
          {tab === "anomaly" && <AnomalyView d={data as AnomalyResult} />}
        </>
      )}
    </div>
  );
}
