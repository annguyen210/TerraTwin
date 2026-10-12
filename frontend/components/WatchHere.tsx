"use client";

/**
 * TAB CANH ĐẤT — phần đầu (báo cáo kiểm toàn bộ 12/10/2026, mục 5).
 *  · Đã đăng nhập VÀ thửa đang xem đã lưu → nhật ký riêng của thửa (PlotJournal) hiện thẳng ở đây.
 *  · Chưa đăng nhập / chưa lưu → nhật ký 7 ngày của toạ độ này từ nguồn công khai (mưa, radar) + nhật ký sống của
 *    6 thửa mẫu được canh mỗi ngày (nhánh journal-log) — không còn một tab gần như trống.
 */
import { useEffect, useState } from "react";
import { getPublicJournal, listPlots, type AuthUser, type PublicJournal, type ServerPlot } from "@/lib/api";
import PlotJournal from "@/components/PlotJournal";
import { useLang } from "@/lib/i18n";

const NEAR_DEG = 0.0003;   // ~30 m: cùng một thửa

function day(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export default function WatchHere({ user, coord, onOpen }: {
  user: AuthUser | null; coord: { lat: number; lon: number } | null;
  onOpen: (lat: number, lon: number, label?: string) => void;
}) {
  const { t, lang } = useLang();
  const [saved, setSaved] = useState<ServerPlot | null | undefined>(undefined);   // undefined = đang xem
  const [pub, setPub] = useState<PublicJournal | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setSaved(undefined);
    if (!user || !coord) { setSaved(null); return; }
    listPlots().then((ps) => {
      if (!live) return;
      setSaved(ps.find((p) => Math.abs(p.lat - coord.lat) < NEAR_DEG && Math.abs(p.lon - coord.lon) < NEAR_DEG) ?? null);
    }).catch(() => live && setSaved(null));
    return () => { live = false; };
  }, [user, coord]);

  useEffect(() => {
    if (saved !== null || !coord) return;
    let live = true;
    setPub(null); setErr(null);
    getPublicJournal(coord.lat, coord.lon).then((j) => live && setPub(j)).catch((e) => live && setErr((e as Error).message));
    return () => { live = false; };
  }, [saved, coord, lang]);

  if (saved) {
    return (
      <section className="wh-here">
        <h3>{t(`Nhật ký thửa “${saved.name}”`, `Journal of “${saved.name}”`)}</h3>
        <PlotJournal plotId={saved.id} />
      </section>
    );
  }
  if (saved === undefined) return null;
  return (
    <section className="wh-here">
      <h3>{t("7 ngày qua ở thửa đang xem", "The last 7 days at this plot")}</h3>
      {err && <p className="pj-err">{err}</p>}
      {!pub && !err && <p className="pj-note">{t("Đang đọc mưa và ảnh radar mới của toạ độ này…", "Reading rain and new radar images for this spot…")}</p>}
      {pub && (
        <div className={`pj ${pub.changed ? "pj-changed" : "pj-calm"}`}>
          <p className="pj-sum"><b>{pub.changed ? t("Có thay đổi", "Changes") : t("Yên", "Quiet")}</b> · {pub.summary}</p>
          {pub.events.length > 0 && (
            <ul className="pj-list">
              {pub.events.slice(0, 8).map((e, i) => (
                <li key={`${e.kind}-${e.at}-${i}`} className={`pj-ev pj-${e.kind}`}>
                  <span className="pj-when">{day(e.at)}</span><span className="pj-text">{e.text}</span><small className="pj-src">{e.source}</small>
                </li>
              ))}
            </ul>
          )}
          <small className="pj-note">{pub.rule}</small>
        </div>
      )}
      {pub?.samples && pub.samples.plots.length > 0 && (
        <div className="wh-samples">
          <h4>{t(`6 thửa mẫu đang được canh mỗi ngày — ${pub.samples.n_days} ngày nhật ký sống`, `6 sample plots watched daily — ${pub.samples.n_days} days of live journal`)}</h4>
          <ul>
            {pub.samples.plots.map((p) => (
              <li key={p.name}>
                <div><b>{p.name}</b>
                  <small>{p.rain_total_mm == null ? t("mưa: không lấy được", "rain: unavailable") : t(`mưa 24 giờ ${p.rain_total_mm} mm`, `24 h rain ${p.rain_total_mm} mm`)}
                    {" · "}{p.n_significant ? t(`${p.n_significant} thay đổi thật`, `${p.n_significant} real change(s)`) : t("yên", "quiet")}
                    {" · "}{p.radar_ok ? t("radar có", "radar ok") : t("radar không lấy được", "radar unavailable")}</small>
                </div>
                {p.lat != null && p.lon != null && (
                  <button type="button" className="bat-btn ghost" onClick={() => onOpen(p.lat!, p.lon!, p.name)}>{t("Mở", "Open")}</button>
                )}
              </li>
            ))}
          </ul>
          <small className="pj-note">{t(`Cập nhật ${new Date(pub.samples.at).toLocaleString("vi-VN")} · `, `Updated ${new Date(pub.samples.at).toLocaleString("en-GB")} · `)}
            <a href={pub.samples.branch} target="_blank" rel="noreferrer">{t("xem toàn bộ nhật ký công khai", "see the full public log")}</a></small>
        </div>
      )}
      <p className="pj-note">{user
        ? t("Lưu thửa này (bên dưới) để có nhật ký riêng: câu trả lời của bạn, ảnh thực địa, cảm biến, báo đẩy.",
            "Save this plot (below) for its own journal: your answers, field photos, sensors, push alerts.")
        : t("Đăng nhập rồi lưu thửa để có nhật ký riêng: câu trả lời của bạn, ảnh thực địa, cảm biến, báo đẩy.",
            "Sign in and save the plot for its own journal: your answers, field photos, sensors, push alerts.")}</p>
    </section>
  );
}
