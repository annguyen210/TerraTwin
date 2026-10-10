"use client";

/**
 * LỊCH SỬ NƯỚC NHÌN XUYÊN MÂY (GĐ2 kế hoạch tổng) — dải thời gian 2017 → nay cho đúng thửa, từ ảnh radar
 * Sentinel-1: mỗi chấm là một ĐỢT nước phủ đã ĐO (không phải dự báo). Chỉ hiện khi cổng kiểm chứng đạt.
 * Lần đầu đọc vài trăm cảnh (~2 phút, chạy nền) — người dùng bấm mới chạy, không tự tốn hạn mức.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Waves } from "lucide-react";
import { waterPoll, waterScene, waterStart, waterStatus, type WaterHistoryResult, type WaterScene } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const COVER_COLOR: Record<string, string> = { "≥50%": "#1d5e87", "25–50%": "#3d8fc4", "10–25%": "#8cc3e6" };

function Chart({ r }: { r: WaterHistoryResult }) {
  const { t } = useLang();
  const W = 640, H = 120, pad = 6;
  const t0 = Date.parse(r.first), t1 = Date.parse(r.last);
  const x = (d: string) => pad + ((Date.parse(d) - t0) / Math.max(1, t1 - t0)) * (W - 2 * pad);
  const y = (db: number) => pad + ((-3 - Math.max(-27, Math.min(-3, db))) / 24) * (H - 2 * pad);
  const line = r.series.map(([d, p50]) => `${x(d).toFixed(1)},${y(p50).toFixed(1)}`).join(" ");
  const years = [];
  for (let yr = new Date(t0).getFullYear(); yr <= new Date(t1).getFullYear(); yr++) years.push(yr);
  return (
    <svg viewBox={`0 0 ${W} ${H + 18}`} className="wh-chart" role="img"
         aria-label={t(`Tán xạ radar VV theo thời gian, ${r.n_events} đợt nước phủ`, `Radar VV backscatter over time, ${r.n_events} water events`)}>
      <rect x={pad} y={y(-18)} width={W - 2 * pad} height={H - pad - y(-18)} fill="currentColor" opacity=".06" />
      <line x1={pad} x2={W - pad} y1={y(-18)} y2={y(-18)} stroke="currentColor" strokeDasharray="4 4" opacity=".45" />
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.2" opacity=".75" />
      {r.events.map((e) => (
        <rect key={e.start} x={x(e.start) - 3} width={Math.max(6, x(e.end) - x(e.start) + 6)} y={pad} height={H - 2 * pad}
              fill={COVER_COLOR[e.peak_cover] || "#3d8fc4"} opacity=".35" rx="2" />
      ))}
      {years.map((yr) => {
        const d = `${yr}-01-01`;
        if (Date.parse(d) < t0) return null;
        return <text key={yr} x={x(d)} y={H + 14} fontSize="10" textAnchor="middle" fill="currentColor" opacity=".7">{yr}</text>;
      })}
    </svg>
  );
}

/** Mỗi năm: cảnh "ướt nhất" của chính thửa (trung vị VV thấp nhất) — thanh kéo 2017 → nay trên bản đồ. */
function wettestByYear(r: WaterHistoryResult): { year: number; date: string; p50: number }[] {
  const by = new Map<number, { year: number; date: string; p50: number }>();
  for (const [d, p50] of r.series) {
    const y = Number(d.slice(0, 4));
    const cur = by.get(y);
    if (!cur || p50 < cur.p50) by.set(y, { year: y, date: d, p50 });
  }
  return [...by.values()].sort((a, b) => a.year - b.year);
}

/** Cảnh ướt nhất (trung vị VV thấp nhất) TRONG một đợt nước — ảnh đáng xem nhất của đợt đó. */
export function wettestOfEvent(r: WaterHistoryResult, dates: string[]): string {
  const p50 = new Map(r.series.map(([d, v]) => [d, v] as [string, number]));
  return dates.reduce((best, d) => ((p50.get(d) ?? 0) < (p50.get(best) ?? 0) ? d : best), dates[0]);
}

function MapScrubber({ r, lat, lon, onScene, focus }: { r: WaterHistoryResult; lat: number; lon: number;
                                                         onScene: (s: WaterScene | null) => void; focus?: { date: string; n: number } | null }) {
  const { t } = useLang();
  const years = useMemo(() => wettestByYear(r), [r]);
  const [i, setI] = useState<number | null>(null);
  const [day, setDay] = useState<string | null>(null);        // ngày đang hiện: theo năm (thanh kéo) hoặc theo đợt (bấm)
  const [scene, setScene] = useState<WaterScene | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const wet = new Set(r.events.flatMap((e) => (e.dates ?? [e.start])));

  useEffect(() => () => onScene(null), [onScene]);
  useEffect(() => { if (i != null) setDay(years[i].date); }, [i, years]);
  useEffect(() => {                                            // bấm một đợt trong danh sách → đúng ngày đó
    if (!focus) return;
    setI(null);                                                // thanh kéo nhả ra; ngày do đợt quyết định
    setDay(focus.date);
  }, [focus]);
  useEffect(() => {
    if (day == null) return;
    let live = true;
    setBusy(true); setErr(null);
    waterScene(lat, lon, day)
      .then((s) => { if (live) { setScene(s); onScene(s); } })
      .catch((e) => live && setErr((e as Error).message))
      .finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [day, lat, lon, onScene]);

  if (!years.length) return null;
  const cur = day == null ? null : { date: day };
  const yearIdx = day == null ? years.length - 1 : Math.max(0, years.findIndex((y) => y.year === Number(day.slice(0, 4))));
  return (
    <div className="wh-scrub">
      <label htmlFor="wh-year"><b>{t("Xem trên bản đồ", "Show on the map")}</b> — {t("kéo theo năm: mỗi năm lấy cảnh radar ướt nhất của thửa",
        "drag by year: each year shows the plot's wettest radar scene")}</label>
      <input id="wh-year" type="range" min={0} max={years.length - 1} step={1} value={i ?? yearIdx}
             aria-valuetext={cur ? cur.date : undefined}
             onChange={(e) => setI(Number(e.target.value))} onPointerDown={() => i == null && setI(years.length - 1)} />
      <div className="wh-years" aria-hidden="true">{years.map((y) => <span key={y.year}>{String(y.year).slice(2)}</span>)}</div>
      {cur && <p className="wh-scene">{busy ? t("Đang tải ảnh radar…", "Loading radar image…")
        : scene ? <>{t(`Ảnh radar ngày ${scene.date}`, `Radar image of ${scene.date}`)}{wet.has(cur.date) ? t(" — nằm trong một đợt nước phủ của thửa", " — inside one of the plot's water events") : ""}.{" "}
          <button type="button" className="wh-off" onClick={() => { setI(null); setDay(null); setScene(null); onScene(null); }}>{t("Tắt lớp radar", "Hide radar layer")}</button></> : null}</p>}
      {day == null && <button type="button" className="bat-btn ghost" onClick={() => setI(years.length - 1)}>{t("Hiện lớp radar", "Show radar layer")}</button>}
      {scene && <p className="eu-src">{scene.legend} {scene.attribution}.</p>}
      {err && <p className="bat-err">{err}</p>}
    </div>
  );
}

export default function WaterHistory({ lat, lon, onScene }: { lat: number; lon: number; onScene?: (s: WaterScene | null) => void }) {
  const { t } = useLang();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [r, setR] = useState<WaterHistoryResult | null>(null);
  const [prog, setProg] = useState<{ done: number; total: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [focus, setFocus] = useState<{ date: string; n: number } | null>(null);   // đợt nước đang xem trên bản đồ

  useEffect(() => { waterStatus().then((s) => setEnabled(s.enabled)).catch(() => setEnabled(false)); }, []);
  useEffect(() => { setR(null); setErr(null); setProg(null); return () => { if (timer.current) clearTimeout(timer.current); }; }, [lat, lon]);

  async function run() {
    setBusy(true); setErr(null); setProg(null);
    try {
      const j = await waterStart(lat, lon);
      if (j.state === "done" && j.result) { setR(j.result); setBusy(false); return; }
      const id = j.job_id!;
      const tick = async () => {
        try {
          const s = await waterPoll(id);
          if (s.progress) setProg(s.progress);
          if (s.state === "done" && s.result) { setR(s.result); setBusy(false); return; }
          if (s.state === "error") { setErr(s.message || t("Việc chạy nền lỗi.", "Background job failed.")); setBusy(false); return; }
          timer.current = setTimeout(tick, 3000);
        } catch (e) { setErr((e as Error).message); setBusy(false); }
      };
      timer.current = setTimeout(tick, 2500);
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  }

  const summary = useMemo(() => {
    if (!r || !r.available) return null;
    const last = r.events[r.events.length - 1];
    return r.n_events === 0
      ? t(`Không thấy đợt nước phủ nào trong ${r.n_scenes} cảnh radar từ ${r.first.slice(0, 4)}.`,
          `No water events in ${r.n_scenes} radar scenes since ${r.first.slice(0, 4)}.`)
      : t(`Nước đã phủ ${r.n_events} đợt từ ${r.first.slice(0, 4)} (${r.n_scenes} cảnh radar), gần nhất ${last.start}.`,
          `Water covered the plot ${r.n_events} times since ${r.first.slice(0, 4)} (${r.n_scenes} radar scenes), most recently ${last.start}.`);
  }, [r, t]);

  if (!enabled) return null;
  return (
    <section className="wh">
      <div className="wh-head">
        <Waves size={18} aria-hidden="true" />
        <h3>{t("Lịch sử nước nhìn xuyên mây", "Water history through clouds")}</h3>
        <span className="wh-badge">{t("radar · đo thật", "radar · measured")}</span>
      </div>
      {!r && (
        <div className="wh-start">
          <p>{t("Đọc toàn bộ ảnh radar Sentinel-1 từ 2017 của đúng thửa này — radar nhìn xuyên mây, kể cả giữa cơn bão.",
                "Read every Sentinel-1 radar image since 2017 for this exact plot — radar sees through clouds, even mid-storm.")}</p>
          <button className="bat-btn" onClick={run} disabled={busy}>
            {busy ? (prog ? t(`Đang đọc ${prog.done}/${prog.total} cảnh…`, `Reading ${prog.done}/${prog.total} scenes…`)
                          : t("Đang chuẩn bị… (~2 phút lần đầu)", "Preparing… (~2 min the first time)"))
                  : t("Xem lịch sử nước", "Show water history")}
          </button>
        </div>
      )}
      {err && <p className="bat-err">{err}</p>}
      {r && !r.available && <p className="doc-note">{r.message}</p>}
      {r && r.available && (
        <>
          <p className="wh-sum"><b>{summary}</b></p>
          <Chart r={r} />
          {onScene && <MapScrubber r={r} lat={lat} lon={lon} onScene={onScene} focus={focus} />}
          <p className="eu-src">{t("Đường: trung vị tán xạ VV (dB); vạch đứt: ngưỡng nước −18 dB; khối xanh: đợt nước phủ.",
                                   "Line: median VV backscatter (dB); dashed: −18 dB water threshold; blue blocks: water events.")}</p>
          {r.events.length > 0 && (
            <ol className="wh-list">
              {r.events.slice().reverse().map((e) => (
                <li key={e.start}>
                  <b>{e.start === e.end ? e.start : `${e.start} → ${e.end}`}</b>
                  <span>{t(`phủ ${e.peak_cover} thửa`, `${e.peak_cover} of plot covered`)} · {t(`${e.n_scenes} cảnh`, `${e.n_scenes} scenes`)} · {t("VV thấp nhất", "min VV")} {e.min_p50_db} dB</span>
                  {onScene && <button type="button" className="wh-off" onClick={() => setFocus({ date: wettestOfEvent(r, e.dates ?? [e.start]), n: Date.now() })}>
                    {t("Xem ảnh radar trên bản đồ", "Show radar image on the map")}</button>}
                </li>
              ))}
            </ol>
          )}
          <p className="eu-src">{r.method}</p>
          <p className="doc-note">{r.limits}</p>
        </>
      )}
    </section>
  );
}
