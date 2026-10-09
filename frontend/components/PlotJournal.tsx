"use client";

/**
 * GĐ6 — NHẬT KÝ THỬA: "từ lần mở trước có gì đổi". Không có thay đổi thật thì nói đúng một câu yên tâm.
 * Số đo cảm biến: gọi nhanh (chỉ CSDL) mỗi 5 giây khi thẻ đang hiện → số mới hiện trong ≤ 10 giây.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getPlotJournal, markJournalSeen, type JournalEvent, type PlotJournal as J } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const POLL_MS = 5000;
const REC: Record<string, { vi: string; en: string; cls: string }> = {
  match: { vi: "khớp", en: "consistent", cls: "pj-ok" },
  partial: { vi: "khớp một phần", en: "partly consistent", cls: "pj-mid" },
  mismatch: { vi: "lệch", en: "inconsistent", cls: "pj-bad" },
  insufficient: { vi: "chưa đủ dữ liệu", en: "not enough data", cls: "pj-na" },
};

function when(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return iso.endsWith("T00:00:00Z") ? `${p(d.getUTCDate())}/${p(d.getUTCMonth() + 1)}`
    : `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function PlotJournal({ plotId, compact = false }: { plotId: number; compact?: boolean }) {
  const { t, lang } = useLang();
  const [j, setJ] = useState<J | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [seen, setSeen] = useState(false);
  const [showCtx, setShowCtx] = useState(false);
  const live = useRef(true);

  const load = useCallback(async () => {
    try { setJ(await getPlotJournal(plotId)); } catch (e) { setErr((e as Error).message); }
  }, [plotId]);

  useEffect(() => { live.current = true; load(); return () => { live.current = false; }; }, [load, lang]);

  // Cảm biến: lượt gọi nhanh chỉ thay các sự kiện từ CSDL; mưa/radar giữ từ lượt đầy đủ.
  useEffect(() => {
    if (compact) return;
    const id = window.setInterval(async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const f = await getPlotJournal(plotId, true);
        if (!live.current) return;
        setJ((cur) => {
          if (!cur) return cur;
          const ext = cur.events.filter((e) => ["rain", "water", "radar"].includes(e.kind));
          const events = [...f.events, ...ext].sort((a, b) => (a.at < b.at ? 1 : -1));
          const sig = events.filter((e) => e.significant);
          return { ...cur, events, n_significant: sig.length, changed: sig.length > 0 };
        });
      } catch { /* mạng chập chờn: lượt sau thử lại */ }
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [plotId, compact]);

  async function ack() {
    try { await markJournalSeen(plotId); setSeen(true); } catch (e) { setErr((e as Error).message); }
  }

  if (err) return <p className="pj-err">{err}</p>;
  if (!j) return <p className="pj-note">{t("Đang xem từ lần mở trước có gì đổi…", "Checking what changed since your last visit…")}</p>;

  const sig = j.events.filter((e) => e.significant);
  const ctx = j.events.filter((e) => !e.significant);
  const row = (e: JournalEvent, i: number) => (
    <li key={`${e.kind}-${e.at}-${i}`} className={`pj-ev pj-${e.kind}`}>
      <span className="pj-when">{when(e.at)}</span>
      <span className="pj-text">{e.text}
        {e.reconcile && (
          <span className={`pj-rec ${REC[e.reconcile.verdict].cls}`}>
            {t("Đối chiếu ba chiều", "Three-way check")}: {t(REC[e.reconcile.verdict].vi, REC[e.reconcile.verdict].en)}
            {" — "}{e.reconcile.radar_water == null ? t("radar cùng tuần: chưa có", "radar same week: none")
              : e.reconcile.radar_water ? t(`radar ${e.reconcile.radar_dates.join(", ")} thấy nước`, `radar ${e.reconcile.radar_dates.join(", ")} saw water`)
              : t(`radar ${e.reconcile.radar_dates.join(", ")} không thấy nước`, `radar ${e.reconcile.radar_dates.join(", ")} no water`)}
            {"; "}{e.reconcile.rain_3d_mm == null ? t("mưa: không lấy được", "rain: unavailable") : t(`mưa 3 ngày ${e.reconcile.rain_3d_mm} mm`, `3-day rain ${e.reconcile.rain_3d_mm} mm`)}
          </span>
        )}
      </span>
      <small className="pj-src">{e.source}</small>
    </li>
  );

  return (
    <section className={`pj ${j.changed ? "pj-changed" : "pj-calm"}`} aria-live="polite">
      <p className="pj-sum"><b>{j.changed ? t("Có thay đổi", "Changes") : t("Yên", "Quiet")}</b> · {j.summary ??
        t(`${j.n_significant} thay đổi`, `${j.n_significant} change(s)`)}</p>
      {sig.length > 0 && <ul className="pj-list">{sig.map(row)}</ul>}
      {!compact && ctx.length > 0 && (
        <>
          <button type="button" className="pj-more" aria-expanded={showCtx} onClick={() => setShowCtx(!showCtx)}>
            {showCtx ? t("Ẩn bối cảnh", "Hide context") : t(`Bối cảnh (${ctx.length})`, `Context (${ctx.length})`)}</button>
          {showCtx && <ul className="pj-list pj-ctx">{ctx.map(row)}</ul>}
        </>
      )}
      {!compact && (
        <div className="pj-foot">
          <button type="button" className="pj-ack" onClick={ack} disabled={seen}>
            {seen ? t("Đã đánh dấu — lần sau chỉ kể chuyện mới", "Marked — next time only new things")
              : t("Đã xem, lần sau chỉ báo điều mới", "Seen — only show new things next time")}</button>
          <small>{j.rule}</small>
        </div>
      )}
    </section>
  );
}
