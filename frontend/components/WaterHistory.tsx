"use client";

/**
 * LỊCH SỬ NƯỚC NHÌN XUYÊN MÂY (GĐ2 kế hoạch tổng) — dải thời gian 2017 → nay cho đúng thửa, từ ảnh radar
 * Sentinel-1: mỗi chấm là một ĐỢT nước phủ đã ĐO (không phải dự báo). Chỉ hiện khi cổng kiểm chứng đạt.
 * TỰ ĐỌC khi mở thửa (báo cáo kiểm toàn bộ 12/10/2026, mục 4): đã có trong cache thì hiện ngay; chưa có thì xếp
 * hàng chạy nền với thanh tiến độ — người dùng xem phần khác trong lúc chờ, không phải bấm rồi ngồi đợi.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Waves } from "lucide-react";
import { getToken, waterConfirm, waterConfirmations, waterPoll, waterScene, waterStart, waterStatus, waterUnet, type WaterUnet,
         type WaterAnswer, type WaterConfirmCount, type WaterHistoryResult, type WaterScene } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const COVER_COLOR: Record<string, string> = { "≥50%": "#1d5e87", "25–50%": "#3d8fc4", "10–25%": "#8cc3e6" };
const OUT_COLOR = "#9aa86b";      // đợt NGOÀI mùa lũ (thường nước tưới / nuôi trồng) — tô khác màu đợt trong mùa lũ

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
              fill={e.season === "out" ? OUT_COLOR : COVER_COLOR[e.peak_cover] || "#3d8fc4"} opacity={e.season === "out" ? ".45" : ".35"} rx="2" />
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
  const [unet, setUnet] = useState<WaterUnet | null>(null);
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
  useEffect(() => {                                            // U-Net chỉ hỏi cho ngày nằm trong một đợt nước
    setUnet(null);
    if (day == null || !wet.has(day)) return;
    let live = true, tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    // Bản 3 đọc 7 cảnh radar + 7 lượt U-Net: lần đầu máy chủ chạy NỀN (đo ~21 s, lâu hơn khi bận) và trả pending → hỏi lại, tối đa ~4 phút.
    const ask = () => waterUnet(lat, lon, day).then((u) => {
      if (!live) return;
      if (u.pending && ++tries < 24) { setUnet(u); timer = setTimeout(ask, (u.retry_after_s ?? 10) * 1000); }
      else setUnet(u.pending ? null : u);
    }).catch(() => live && setUnet(null));
    ask();
    return () => { live = false; if (timer) clearTimeout(timer); };
  }, [day, lat, lon]);  // eslint-disable-line react-hooks/exhaustive-deps

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
      {unet?.pending && <p className="wh-scene" role="status">{t("Học sâu (U-Net radar, tham khảo): đang đọc 7 cảnh radar của thửa — lần đầu mất vài chục giây…",
        "Deep learning (radar U-Net, reference): reading 7 radar scenes of the plot — the first time takes a few tens of seconds…")}</p>}
      {unet?.available && unet.share != null && (
        <p className="wh-scene">{t(`Học sâu (U-Net radar, tham khảo): ~${Math.round(unet.share * 100)}% khung thửa là nước`,
          `Deep learning (radar U-Net, reference): ~${Math.round(unet.share * 100)}% of the plot window is water`)}
          {unet.baseline != null && t(` (mùa khô thường ~${Math.round(unet.baseline * 100)}%)`, ` (dry season usually ~${Math.round(unet.baseline * 100)}%)`)}
          {" — "}
          <b>{unet.confirmed ? t("xác nhận đợt này", "confirms this event") : t("không xác nhận", "does not confirm")}</b>.</p>
      )}
      {scene && <p className="eu-src">{scene.legend} {scene.attribution}.</p>}
      {err && <p className="bat-err">{err}</p>}
    </div>
  );
}

/** "Ruộng bạn có ngập đợt này không?" — sự thật mặt đất cho TỪNG đợt radar. Chỉ người đăng nhập trả lời (một người một
 *  câu mỗi đợt, bấm lại là sửa); ai cũng thấy SỐ ĐẾM. Câu "Có" ở đợt ngoài mùa lũ thành ca kiểm thật cho lớp mùa lũ sau. */
function ConfirmEvent({ lat, lon, start, count, onSaved }: { lat: number; lon: number; start: string;
  count?: WaterConfirmCount; onSaved: (start: string, a: WaterAnswer, msg: string) => void }) {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const logged = typeof window !== "undefined" && !!getToken();
  const n = count ? count.yes + count.no + count.unsure : 0;
  const tally = n > 0 ? t(`${n} người đã trả lời: ${count!.yes} có ngập · ${count!.no} không`, `${n} answered: ${count!.yes} flooded · ${count!.no} not`)
                      : null;
  async function send(a: WaterAnswer) {
    setBusy(true); setErr(null);
    try { const r = await waterConfirm(lat, lon, start, a); onSaved(start, a, r.message); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }
  const opts: [WaterAnswer, string][] = [["yes", t("Có ngập", "Flooded")], ["no", t("Không", "No")], ["unsure", t("Không rõ", "Not sure")]];
  if (!logged && !tally) return null;              // chưa đăng nhập: lời mời nằm MỘT lần trên danh sách
  return (
    <div className="wh-confirm">
      {logged && (
        <>
          <span>{t("Ruộng có ngập đợt này không?", "Was the field flooded this time?")}</span>
          {opts.map(([a, label]) => (
            <button key={a} type="button" disabled={busy} aria-pressed={count?.mine === a}
                    className={`wh-cf${count?.mine === a ? " on" : ""}`} onClick={() => send(a)}>{label}</button>
          ))}
        </>
      )}
      {tally && <small>{tally}</small>}
      {err && <small className="bat-err">{err}</small>}
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

  const gen = useRef(0);                                        // đổi thửa giữa chừng → bỏ kết quả của thửa cũ
  const started = useRef<number>(0);                            // lúc bắt đầu đọc — hiện thời gian thật, không hứa suông
  // Thời gian chạy của CHÍNH lượt đọc trên máy chủ (elapsed_s) — mở trang khi lượt đọc đã chạy dở (người khác / tab
  // khác đã bắt đầu) thì đồng hồ của trang này sẽ sai nếu chỉ đếm từ lúc mở.
  const jobEl = useRef<{ el: number; at: number } | null>(null);
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [busy]);

  useEffect(() => { waterStatus().then((s) => setEnabled(s.enabled)).catch(() => setEnabled(false)); }, []);

  async function run() {
    const my = ++gen.current;
    if (timer.current) clearTimeout(timer.current);
    started.current = Date.now();
    jobEl.current = null;
    setBusy(true); setErr(null); setProg(null);
    try {
      const j = await waterStart(lat, lon);
      if (my !== gen.current) return;
      if (j.state === "done" && j.result) { setR(j.result); setBusy(false); return; }
      const id = j.job_id!;
      const tick = async () => {
        try {
          const s = await waterPoll(id);
          if (my !== gen.current) return;
          if (s.state === "running" && s.elapsed_s != null) jobEl.current = { el: s.elapsed_s, at: Date.now() };
          if (s.progress) setProg(s.progress);
          if (s.state === "done" && s.result) { setR(s.result); setBusy(false); return; }
          if (s.state === "error") { setErr(s.message || t("Việc chạy nền lỗi.", "Background job failed.")); setBusy(false); return; }
          timer.current = setTimeout(tick, 3000);
        } catch (e) { if (my === gen.current) { setErr((e as Error).message); setBusy(false); } }
      };
      timer.current = setTimeout(tick, 2500);
    } catch (e) { if (my === gen.current) { setErr((e as Error).message); setBusy(false); } }
  }

  const [counts, setCounts] = useState<Record<string, WaterConfirmCount>>({});
  const [thanks, setThanks] = useState<string | null>(null);
  useEffect(() => {                                            // có lịch sử (≥ 1 đợt) → đọc số xác nhận của thửa
    setCounts({}); setThanks(null);
    if (!r || !r.available || r.events.length === 0) return;
    let live = true;
    waterConfirmations(lat, lon).then((x) => live && setCounts(x.events)).catch(() => {});
    return () => { live = false; };
  }, [r, lat, lon]);
  function saved(start: string, a: WaterAnswer, msg: string) {
    setThanks(msg);
    waterConfirmations(lat, lon).then((x) => setCounts(x.events))
      .catch(() => setCounts((c) => ({ ...c, [start]: { ...(c[start] ?? { yes: 0, no: 0, unsure: 0 }), mine: a } })));
  }

  useEffect(() => {                                            // mở thửa (hoặc đổi thửa) → tự đọc
    setR(null); setErr(null); setProg(null); setFocus(null);
    if (enabled) run();
    return () => { gen.current++; if (timer.current) clearTimeout(timer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lat, lon, enabled]);

  const summary = useMemo(() => {
    if (!r || !r.available) return null;
    const last = r.events[r.events.length - 1];
    if (r.flood_season && r.n_events > 0) {
      const fs = r.flood_season;
      return t(`${r.n_in} đợt nước TRONG mùa lũ (tháng ${fs.text}) · ${r.n_out} đợt ngoài mùa lũ${r.n_out ? ` (${r.out_note})` : ""} — từ ${r.first.slice(0, 4)}, ${r.n_scenes} cảnh radar.`,
               `${r.n_in} water event(s) IN the flood season (months ${fs.text}) · ${r.n_out} outside${r.n_out ? ` (${r.out_note})` : ""} — since ${r.first.slice(0, 4)}, ${r.n_scenes} radar scenes.`);
    }
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
      {!r && busy && (
        <div className="wh-start" aria-live="polite">
          <p>{t("Đang tự đọc toàn bộ ảnh radar Sentinel-1 từ 2017 của đúng thửa này (radar nhìn xuyên mây). Thửa mới thường mất khoảng 1 phút (đo 18/10/2026: ~460 cảnh trong ~40 giây), lâu hơn khi nguồn ảnh bận — cứ xem các phần khác, xong sẽ tự hiện.",
                "Reading every Sentinel-1 radar image since 2017 for this exact plot (radar sees through clouds). A new plot usually takes about a minute (measured 18/10/2026: ~460 scenes in ~40 s), longer when the image source is busy — keep browsing, it appears by itself.")}</p>
          <div className="wh-prog" role="progressbar" aria-valuemin={0} aria-valuemax={prog?.total ?? 100}
               aria-valuenow={prog?.done ?? 0} aria-label={t("Tiến độ đọc ảnh radar", "Radar read progress")}>
            <span style={{ width: `${prog && prog.total ? Math.max(4, Math.round((prog.done / prog.total) * 100)) : 4}%` }} />
          </div>
          <small>{(() => {
            const el = Math.max(0, Math.round(jobEl.current ? jobEl.current.el + (Date.now() - jobEl.current.at) / 1000
                                                           : (Date.now() - started.current) / 1000));
            const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
            // Ước lượng phần còn lại theo TỐC ĐỘ THẬT của lượt này (sau ≥ 40 cảnh mới đủ tin), không theo con số cố định.
            const left = prog && prog.done >= 40 && el > 0 ? Math.round(((prog.total - prog.done) * el) / prog.done) : null;
            return (prog ? t(`Đã đọc ${prog.done}/${prog.total} cảnh radar`, `Read ${prog.done}/${prog.total} radar scenes`)
                         : t("Đang xếp hàng / tìm cảnh radar…", "Queued / finding radar scenes…"))
              + t(` · đã chạy ${mmss(el)}`, ` · ${mmss(el)} elapsed`)
              + (left != null ? t(` · còn khoảng ${mmss(left)}`, ` · about ${mmss(left)} left`) : "");
          })()}</small>
        </div>
      )}
      {err && <p className="bat-err">{err}</p>}
      {!r && !busy && err && (
        <button className="bat-btn ghost" onClick={run}>{t("Thử đọc lại lịch sử nước", "Retry the water history")}</button>
      )}
      {r && !r.available && <p className="doc-note">{r.message}</p>}
      {r && r.available && (
        <>
          {r.urban && <p className="wh-surface" role="note"><b>{t("Khu đô thị — radar không thấy được ngập giữa nhà cửa.", "Urban area — radar can't see flooding between buildings.")}</b> {r.urban.note}</p>}
          {r.canopy && <p className="wh-surface" role="note"><b>{t("Tán cây dày — radar không thấy được nước dưới tán.", "Dense canopy — radar can't see water beneath it.")}</b> {r.canopy.note}</p>}
          {r.cropland && <p className="wh-surface wh-crop" role="note"><b>{t("Ruộng — có thể lẫn nước tưới theo vụ.", "Cropland — may include seasonal irrigation.")}</b> {r.cropland.note}</p>}
          {r.water_surface && <p className="wh-surface" role="note"><b>{t("Khung đo có mặt nước thường xuyên.", "The frame contains permanent water.")}</b> {r.water_surface.note}</p>}
          {!!r.n_failed && <p className="wh-surface" role="note"><b>{t("Chưa đọc đủ ảnh radar.", "Not every radar image was read.")}</b> {r.failed_note}</p>}
          <p className="wh-sum"><b>{summary}</b></p>
          <Chart r={r} />
          {onScene && <MapScrubber r={r} lat={lat} lon={lon} onScene={onScene} focus={focus} />}
          <p className="eu-src">{r.flood_season
            ? t(`Đường: trung vị tán xạ VV (dB); vạch đứt: ngưỡng nước −18 dB; khối xanh lam: đợt trong mùa lũ; khối xanh rêu: đợt ngoài mùa lũ. Mùa lũ của điểm: tháng ${r.flood_season.text} — các tháng mưa nhiều nhất (ERA5 ${r.flood_season.window}) cộng tháng liền sau.`,
                `Line: median VV backscatter (dB); dashed: −18 dB water threshold; blue blocks: flood-season events; olive blocks: out-of-season events. Flood season here: months ${r.flood_season.text} — the wettest months (ERA5 ${r.flood_season.window}) plus the following month.`)
            : t("Đường: trung vị tán xạ VV (dB); vạch đứt: ngưỡng nước −18 dB; khối xanh: đợt nước phủ.",
                "Line: median VV backscatter (dB); dashed: −18 dB water threshold; blue blocks: water events.")}</p>
          {r.events.length > 0 && (
            <p className="wh-cf-note">{getToken()
              ? t("Bạn biết ruộng này? Bấm trả lời từng đợt bên dưới — mỗi câu là sự thật mặt đất để kiểm radar và lớp mùa lũ.",
                  "Know this field? Answer each event below — every answer is ground truth for checking the radar and the flood-season layer.")
              : t("Bạn biết ruộng này? Đăng nhập (góc trên) để xác nhận từng đợt có ngập thật không — mỗi câu là sự thật mặt đất để kiểm radar.",
                  "Know this field? Log in (top corner) to confirm whether each event really flooded — every answer is ground truth for the radar.")}</p>
          )}
          {r.events.length > 0 && <InviteConfirm lat={lat} lon={lon} />}
          {r.events.length > 0 && (
            <ol className="wh-list">
              {r.events.slice().reverse().map((e) => (
                <li key={e.start}>
                  <b>{e.start === e.end ? e.start : `${e.start} → ${e.end}`}</b>
                  {e.season && <span className={`wh-season ${e.season}`}>{e.season === "in" ? t("trong mùa lũ", "flood season") : t("ngoài mùa lũ", "out of season")}</span>}
                  <span>{t(`phủ ${e.peak_cover} thửa`, `${e.peak_cover} of plot covered`)} · {t(`${e.n_scenes} cảnh`, `${e.n_scenes} scenes`)} · {e.min_flag_db != null && e.flag_pct != null
                    ? t(`VV phân vị ${e.flag_pct} thấp nhất ${e.min_flag_db} dB (ngưỡng −18; trung vị ${e.min_p50_db})`,
                        `lowest VV p${e.flag_pct} ${e.min_flag_db} dB (threshold −18; median ${e.min_p50_db})`)
                    : t(`VV trung vị thấp nhất ${e.min_p50_db} dB`, `lowest median VV ${e.min_p50_db} dB`)}</span>
                  {onScene && <button type="button" className="wh-off" onClick={() => setFocus({ date: wettestOfEvent(r, e.dates ?? [e.start]), n: Date.now() })}>
                    {t("Xem ảnh radar trên bản đồ", "Show radar image on the map")}</button>}
                  <ConfirmEvent lat={lat} lon={lon} start={e.start} count={counts[e.start]} onSaved={saved} />
                </li>
              ))}
            </ol>
          )}
          {thanks && <p className="wh-thanks" role="status">{thanks}</p>}
          <p className="eu-src">{r.method}</p>
          <p className="doc-note">{r.limits}</p>
        </>
      )}
    </section>
  );
}


/** Mời NGƯỜI THẬT ở thửa xác nhận từng đợt (kiểm thực địa — water_field_protocol.json): điện thoại mở bảng chia sẻ (Zalo,
 *  Messenger…), máy tính chép link. Link mở trang thửa công khai, cuộn thẳng tới lịch sử nước. Không tự tạo tài khoản. */
function InviteConfirm({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [done, setDone] = useState<string | null>(null);
  async function invite() {
    const url = `${window.location.origin}/plot/${lat.toFixed(5)},${lon.toFixed(5)}?xac-nhan=1`;
    const text = t("Bạn biết thửa này? Radar ghi nhận các đợt nước dưới đây — bấm xác nhận đợt nào ngập thật giúp mình.",
                   "Know this plot? Radar recorded the water events below — please confirm which ones really flooded.");
    try {
      if (navigator.share) {
        await navigator.share({ title: "TerraTwin", text, url });
        setDone(t("Đã mở bảng chia sẻ.", "Share sheet opened."));
        return;
      }
      await navigator.clipboard.writeText(`${text} ${url}`);
      setDone(t("Đã chép link — dán vào Zalo hoặc tin nhắn.", "Link copied — paste it into Zalo or a message."));
    } catch {
      setDone(url);
    }
  }
  return (
    <p className="wh-invite">
      <button type="button" className="bat-btn ghost" onClick={invite}>
        {t("Mời người ở đó xác nhận (gửi qua Zalo…)", "Invite people there to confirm (send via Zalo…)")}
      </button>
      {done && <small role="status"> {done}</small>}
    </p>
  );
}
