"use client";

/**
 * HÔM NAY — trang người dùng mở mỗi sáng. Không phải trang phân tích: là NHẬT KÝ CÁC THỬA của chính họ
 * (mưa, radar, cảnh báo, cảm biến — từ lần mở trước có gì đổi) và DANH SÁCH VIỆC xếp theo độ gấp.
 * Chưa có thửa → nhật ký sống của các thửa mẫu được canh mỗi ngày (số thửa lấy từ CHÍNH bản ghi nhật ký — kiểm 24/10/2026). Phần EUDR (đồng hồ hạn, mức sẵn sàng,
 * điều khoản mỗi ngày) chỉ hiện cho doanh nghiệp đã có bộ vườn / lô hàng (báo cáo 12/10/2026, mục 9).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertOctagon, ArrowRight, Bell, BookOpen, CheckCircle2, Columns2, Radio, ClipboardCheck, FileSearch, Footprints, Map as MapIcon, Package, ShieldCheck, Sparkles } from "lucide-react";
import AppShell from "@/components/AppShell";
import PlotJournal from "@/components/PlotJournal";
import { getJournalSamples, getToday, listPlots, type PublicJournal, type ServerPlot, type Today } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { enablePush, pushState } from "@/lib/push";

function Ring({ days, total, label, date, unit }: { days: number; total: number; label: string; date: string; unit: string }) {
  const r = 34, c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, days / total));
  return (
    <div className="hn-ring">
      <svg viewBox="0 0 84 84" aria-hidden="true">
        <circle cx="42" cy="42" r={r} className="hn-ring-bg" />
        <circle cx="42" cy="42" r={r} className="hn-ring-fg" strokeDasharray={c} strokeDashoffset={c * (1 - frac)} />
      </svg>
      <div><b>{days}</b><small>{unit}</small></div>
      <p>{label}<span>{date.split("-").reverse().join("/")}</span></p>
    </div>
  );
}

export default function TodayPage() {
  const { t, lang } = useLang();
  const [d, setD] = useState<Today | null>(null);
  const [push, setPush] = useState<string>("");
  useEffect(() => { pushState().then(setPush).catch(() => {}); }, []);
  async function turnOnPush() {
    setPush("...");
    try { setPush(await enablePush()); } catch { setPush("off"); }
  }
  const [err, setErr] = useState<string | null>(null);
  const [plots, setPlots] = useState<ServerPlot[] | null>(null);
  const [samples, setSamples] = useState<PublicJournal["samples"] | undefined>(undefined);
  const nSamples = samples?.plots.length ?? 0;     // MỘT nguồn số cho câu mở đầu, nhãn và tiêu đề
  const load = () => getToday().then((x) => {
    setD(x);
    if (x.signed_in) listPlots().then(setPlots).catch(() => setPlots([])); else setPlots([]);
  }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [lang]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (plots && plots.length === 0 && samples === undefined) getJournalSamples().then((r) => setSamples(r.samples)).catch(() => setSamples(null));
  }, [plots, samples]);
  const biz = !!d?.readiness;                       // doanh nghiệp đã có bộ vườn EUDR / lô hàng

  // Giờ/ngày tính ở TRÌNH DUYỆT (giờ Việt Nam), không ở máy chủ dựng trang (giờ UTC) —
  // tính cả hai nơi là lệch chữ khi hydrate (lỗi React #418, đã gặp trên Render).
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => { setNow(new Date()); }, []);
  const h = now?.getHours() ?? 12;
  const hello = !now ? t("Xin chào", "Hello") : h < 11 ? t("Chào buổi sáng", "Good morning") : h < 18 ? t("Chào buổi chiều", "Good afternoon") : t("Chào buổi tối", "Good evening");
  const icon = { urgent: AlertOctagon, action: ClipboardCheck, info: Sparkles };

  return (
    <AppShell onAuth={() => load()}>
      <main className="hn-wrap tt-reveal">
        <section className="hn-hero">
          <div>
            <p className="eu-eyebrow">{now ? now.toLocaleDateString(lang === "en" ? "en-GB" : "vi-VN", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : " "}</p>
            <h1>{hello}</h1>
            <p className="doc-lede">{d?.signed_in
              ? (d.items.length ? t(`Có ${d.items.length} việc đang chờ bạn.`, `${d.items.length} things are waiting for you.`)
                : t("Không có việc gì gấp. Vườn của bạn đang được canh.", "Nothing urgent. Your plots are being watched."))
              : t(`Mỗi sáng: thửa đất của bạn đêm qua có gì đổi — mưa, ảnh radar, cảnh báo, cảm biến. Đăng nhập và lưu thửa để có nhật ký riêng; dưới đây là nhật ký sống của ${nSamples ? `${nSamples} ` : "các "}thửa mẫu.`,
                  `Every morning: what changed on your land overnight — rain, radar images, alerts, sensors. Sign in and save a plot for its own journal; below is the live journal of ${nSamples ? `${nSamples} ` : "the "}sample plots.`)}</p>
          </div>
          {d && biz && <div className="hn-rings">{d.deadlines.map((x, i) => <Ring key={x.date} days={x.days} total={i === 0 ? 450 : 630} label={x.who} date={x.date} unit={t("ngày", "days")} />)}</div>}
        </section>

        {plots && plots.length > 0 && (
          <section className="hn-plots" aria-label={t("Thửa của bạn hôm nay", "Your plots today")}>
            <h2>{t("Thửa của bạn hôm nay", "Your plots today")}</h2>
            {plots.slice(0, 4).map((p) => (
              <div key={p.id} className="hn-plot tt-card">
                <div className="hn-plot-head"><b>{p.name}</b><Link prefetch={false} href={`/plot/${p.lat},${p.lon}`}>{t("Mở sổ tay thửa", "Open passport")}</Link></div>
                <PlotJournal plotId={p.id} compact />
              </div>
            ))}
            {plots.length > 4 && <Link href="/" className="doc-note">{t(`Còn ${plots.length - 4} thửa nữa — xem ở tab Canh đất`, `${plots.length - 4} more plots — see the Watch tab`)}</Link>}
          </section>
        )}
        {plots && plots.length === 0 && samples && samples.plots.length > 0 && (
          <section className="hn-plots" aria-label={t(`Nhật ký sống ${nSamples} thửa mẫu`, `Live journal of ${nSamples} sample plots`)}>
            <h2>{t(`${nSamples} thửa mẫu được canh mỗi ngày — ${samples.n_days} ngày nhật ký sống`, `${nSamples} sample plots watched daily — ${samples.n_days} days of live journal`)}</h2>
            <div className="wh-samples">
              <ul>
                {samples.plots.map((p) => (
                  <li key={p.name}>
                    <div><b>{p.name}</b>
                      <small>{p.rain_total_mm == null ? t("mưa: không lấy được", "rain: unavailable") : t(`mưa 24 giờ ${p.rain_total_mm} mm`, `24 h rain ${p.rain_total_mm} mm`)}
                        {" · "}{p.n_significant ? t(`${p.n_significant} thay đổi thật`, `${p.n_significant} real change(s)`) : t("yên", "quiet")}</small>
                    </div>
                    {p.lat != null && <Link prefetch={false} className="bat-btn ghost" href={`/plot/${p.lat},${p.lon}`}>{t("Mở", "Open")}</Link>}
                  </li>
                ))}
              </ul>
              <small className="pj-note">{t(`Cập nhật ${new Date(samples.at).toLocaleString("vi-VN")} · `, `Updated ${new Date(samples.at).toLocaleString("en-GB")} · `)}
                <a href={samples.branch} target="_blank" rel="noreferrer">{t("nhật ký công khai", "public log")}</a></small>
            </div>
          </section>
        )}

        {err && <p className="bat-err">{err}</p>}
        {!d && !err && <div className="hn-skel"><div className="tt-skel" /><div className="tt-skel" /><div className="tt-skel" /></div>}

        {d?.readiness && (
          <section className="hn-ready tt-card" aria-label={t("Doanh nghiệp — mức sẵn sàng EUDR", "Business — EUDR readiness")}>
            <div className="hn-ready-head">
              <h2>{t("Mức sẵn sàng EUDR", "EUDR readiness")}</h2>
              <small>{d.readiness.note}</small>
            </div>
            <ol className="hn-funnel">
              {d.readiness.steps.map((s) => (
                <li key={s.key}>
                  <div className="hn-funnel-row">
                    <span>{s.label}</span>
                    <b>{s.pct === null ? "—" : `${s.pct}%`}</b>
                  </div>
                  <div className="hn-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={s.pct ?? 0} aria-label={s.label}>
                    <i style={{ width: `${s.pct ?? 0}%` }} />
                  </div>
                  <small>{s.of ? `${s.n.toLocaleString("vi-VN")} / ${s.of.toLocaleString("vi-VN")}` : t("chưa có dữ liệu", "no data yet")}</small>
                </li>
              ))}
            </ol>
          </section>
        )}

        {d?.signed_in && (
          <section className="hn-list">
            <h2>{t("Việc cần làm", "To do")}</h2>
            {push && push !== "on" && push !== "unsupported" && (
              <div className="hn-push">
                <Bell size={16} aria-hidden="true" />
                <span>
                  {push === "unconfigured" ? t("Máy chủ chưa bật thông báo đẩy — việc mới vẫn hiện ở đây.", "Push isn't enabled on the server yet — new tasks still show here.")
                    : push === "denied" ? t("Trình duyệt đang chặn thông báo của TerraTwin — mở cài đặt trang để cho phép.", "Your browser blocks TerraTwin notifications — allow them in site settings.")
                    : t("Nhận thông báo ngay khi một vườn thay đổi sau phát hành, kể cả lúc không mở ứng dụng.", "Get notified the moment a plot changes after issuance, even when the app is closed.")}
                </span>
                {(push === "off" || push === "...") && (
                  <button className="doc-btn" onClick={turnOnPush} disabled={push === "..."}>{t("Bật thông báo", "Turn on")}</button>
                )}
              </div>
            )}
            {d.items.length === 0 ? (
              <div className="hn-empty"><CheckCircle2 size={22} aria-hidden="true" /> {plots && plots.length === 0
                ? t("Chưa có việc nào — bạn chưa lưu thửa nào. Mở thửa đất của bạn trên bản đồ rồi bấm Lưu ở tab Canh đất.", "Nothing yet — you haven't saved a plot. Open your land on the map, then press Save in the Watch tab.")
                : t("Mọi thứ ổn. Radar xuyên mây canh thửa của bạn cả mùa mưa; có thay đổi thật sẽ hiện ở đây.", "All clear. Cloud-piercing radar watches your plots through the rainy season; real changes show up here.")}</div>
            ) : d.items.map((it, i) => {
              const Ic = icon[it.priority];
              return (
                <Link key={i} href={it.link} className={`hn-item tt-card lift p-${it.priority}`}>
                  <span className="hn-ic"><Ic size={18} aria-hidden="true" /></span>
                  <span className="hn-txt"><b>{it.title}</b><small>{it.body}</small></span>
                  <ArrowRight size={16} aria-hidden="true" className="hn-go" />
                </Link>
              );
            })}
          </section>
        )}

        <section className="hn-quick">
          <h2>{t("Lối tắt", "Shortcuts")}</h2>
          <div className="hn-grid">
            <Link href="/" className="tt-card lift hn-tile"><MapIcon size={22} aria-hidden="true" /><b>{t("Mở hồ sơ một thửa đất", "Open a land dossier")}</b><small>{t("Lịch sử nước radar 2017→nay, loại đất, phát hành hồ sơ ký số", "Radar water history 2017→now, land cover, issue a signed dossier")}</small></Link>
            <Link href="/" className="tt-card lift hn-tile"><FileSearch size={22} aria-hidden="true" /><b>{t("Kiểm một tin đăng bán đất", "Check a land listing")}</b><small>{t("Dán tin, đối chiếu từng câu với số đo thật (tab Kiểm chứng)", "Paste a listing, check each claim against measurements (Verify tab)")}</small></Link>
            <Link href="/so-sanh" className="tt-card lift hn-tile"><Columns2 size={22} aria-hidden="true" /><b>{t("So sánh 2–4 thửa", "Compare 2–4 plots")}</b><small>{t("Cùng một bộ số đo, cạnh nhau", "Same measurements, side by side")}</small></Link>
            <Link href="/kiem" className="tt-card lift hn-tile"><ShieldCheck size={22} aria-hidden="true" /><b>{t("Kiểm một hồ sơ", "Verify a dossier")}</b><small>{t("Ngay trong trình duyệt, tắt mạng vẫn kiểm", "In your browser, works offline")}</small></Link>
            <Link href="/thiet-bi" className="tt-card lift hn-tile"><Radio size={22} aria-hidden="true" /><b>{t("Thiết bị tại vườn", "Field devices")}</b><small>{t("Cảm biến ký số Ed25519, gửi bù khi mất sóng", "Ed25519-signed sensors, back-fill offline")}</small></Link>
          </div>
        </section>

        <section className="hn-quick hn-biz">
          <h2>{t("Doanh nghiệp xuất khẩu (EUDR)", "Exporters (EUDR)")}</h2>
          <div className="hn-grid">
            <Link href="/eudr" className="tt-card lift hn-tile"><Footprints size={22} aria-hidden="true" /><b>{t("Lấy ranh một vườn", "Map a plot")}</b><small>{t("Vẽ hoặc đi bộ GPS, sàng lọc, phát hành hồ sơ", "Draw or GPS-walk, screen, issue a dossier")}</small></Link>
            <Link href="/eudr?tab=lo" className="tt-card lift hn-tile"><ClipboardCheck size={22} aria-hidden="true" /><b>{t("Kiểm cả bộ vườn nhà cung cấp", "Check a supplier set")}</b><small>{t("GeoJSON, KML, Excel → chuẩn EU + sàng lọc", "GeoJSON, KML, Excel → EU format + screening")}</small></Link>
            <Link href="/lo" className="tt-card lift hn-tile"><Package size={22} aria-hidden="true" /><b>{t("Ghép lô hàng", "Build a lot")}</b><small>{t("Cân bằng khối lượng, chứng thư Merkle, DDS", "Mass balance, Merkle certificate, DDS")}</small></Link>
          </div>
        </section>

        {biz && d?.tip && (
          <section className="hn-tip tt-card">
            <span className="hn-ic"><BookOpen size={18} aria-hidden="true" /></span>
            <div>
              <p className="eu-eyebrow">{t("Điều khoản EUDR hôm nay", "EUDR provision of the day")}</p>
              <b>{d.tip.title}</b>
              <p>{d.tip.text}</p>
              <a href={d.tip.url} target="_blank" rel="noreferrer">{d.tip.source}</a>
            </div>
          </section>
        )}
        {d && d.log_size > 0 && <p className="eu-stats-line">{t(`Sổ minh bạch công khai: ${d.log_size} hồ sơ đã ký, nhân chứng độc lập kiểm mỗi ngày.`, `Public transparency log: ${d.log_size} signed records, independently witnessed daily.`)}</p>}
      </main>
    </AppShell>
  );
}
