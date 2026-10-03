"use client";

/**
 * HÔM NAY — trang người dùng mở mỗi sáng. Không phải trang phân tích: là DANH SÁCH
 * VIỆC của chính họ (xếp theo độ gấp), đồng hồ đếm ngược tới hạn EUDR, lối tắt, và một
 * điều khoản EUDR mỗi ngày có nguồn.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertOctagon, ArrowRight, BookOpen, CheckCircle2, ClipboardCheck, Footprints, Package, ShieldCheck, Sparkles } from "lucide-react";
import AppShell from "@/components/AppShell";
import { getToday, type Today } from "@/lib/api";
import { useLang } from "@/lib/i18n";

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
  const [err, setErr] = useState<string | null>(null);
  const load = () => getToday().then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [lang]);   // eslint-disable-line react-hooks/exhaustive-deps

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
              : t("Đăng nhập để thấy việc của riêng bạn: đợt giao hàng chờ xác nhận, vườn bị đánh dấu, lô hàng bị chặn.",
                  "Sign in to see your own tasks: deliveries to confirm, flagged plots, blocked lots.")}</p>
          </div>
          {d && <div className="hn-rings">{d.deadlines.map((x, i) => <Ring key={x.date} days={x.days} total={i === 0 ? 450 : 630} label={x.who} date={x.date} unit={t("ngày", "days")} />)}</div>}
        </section>

        {err && <p className="bat-err">{err}</p>}
        {!d && !err && <div className="hn-skel"><div className="tt-skel" /><div className="tt-skel" /><div className="tt-skel" /></div>}

        {d?.signed_in && (
          <section className="hn-list">
            <h2>{t("Việc cần làm", "To do")}</h2>
            {d.items.length === 0 ? (
              <div className="hn-empty"><CheckCircle2 size={22} aria-hidden="true" /> {t("Mọi thứ ổn. Giám sát sau phát hành chạy mỗi tuần, radar xuyên mây canh cả mùa mưa.", "All clear. Post-issuance monitoring runs weekly; cloud-piercing radar watches through the rainy season.")}</div>
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
            <Link href="/eudr" className="tt-card lift hn-tile"><Footprints size={22} aria-hidden="true" /><b>{t("Lấy ranh một vườn", "Map a plot")}</b><small>{t("Vẽ hoặc đi bộ GPS, sàng lọc, phát hành hồ sơ", "Draw or GPS-walk, screen, issue a dossier")}</small></Link>
            <Link href="/eudr?tab=lo" className="tt-card lift hn-tile"><ClipboardCheck size={22} aria-hidden="true" /><b>{t("Kiểm cả lô nhà cung cấp", "Check a supplier set")}</b><small>{t("GeoJSON, KML, Excel → chuẩn EU + sàng lọc", "GeoJSON, KML, Excel → EU format + screening")}</small></Link>
            <Link href="/lo" className="tt-card lift hn-tile"><Package size={22} aria-hidden="true" /><b>{t("Ghép lô hàng", "Build a lot")}</b><small>{t("Cân bằng khối lượng, chứng thư Merkle, DDS", "Mass balance, Merkle certificate, DDS")}</small></Link>
            <Link href="/kiem" className="tt-card lift hn-tile"><ShieldCheck size={22} aria-hidden="true" /><b>{t("Kiểm một hồ sơ", "Verify a dossier")}</b><small>{t("Ngay trong trình duyệt, tắt mạng vẫn kiểm", "In your browser, works offline")}</small></Link>
          </div>
        </section>

        {d?.tip && (
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
