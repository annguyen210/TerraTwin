"use client";

/**
 * TRANG ĐẦU — hiện khi CHƯA chọn thửa.
 *
 * Kể câu chuyện bằng CHÍNH sản phẩm đang chạy: màn "quét vệ tinh" dùng ảnh Sentinel-2
 * THẬT của một vườn cà phê gần Buôn Ma Thuột (01/01/2026), ranh vườn tự vẽ ra, ba bản đồ
 * rừng 2020 lần lượt bỏ phiếu, rồi kết luận — đúng số liệu sàng lọc thật của vườn đó
 * (WorldCover 76% tán cây, ALOS 0%, Impact Observatory 0% → Đạt sàng lọc).
 * Rồi trả lời thẳng câu giám khảo sẽ hỏi: "sao không chụp ảnh gửi một AI khác?".
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  BadgeCheck, Check, ClipboardList, FileSignature, Footprints, House, Minus, Package, Radar, ScanSearch, Settings,
  ShieldCheck, TreePine, X, type LucideIcon,
} from "lucide-react";

import AppShell from "./AppShell";
import Scorecard from "./Scorecard";
import Start from "./Start";
import { eudrPublicStats, getScorecard, trackEvent, type AuthUser, type ModuleInfo, type Scorecard as SC } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { DataSaverToggle } from "@/lib/net";

// Chỉ người ĐÃ đăng nhập mới thấy "Thửa của tôi" — khách mới không phải tải mã của nó (Lighthouse TBT).
const MyLand = dynamic(() => import("./MyLand"));

// Ảnh lưu sẵn trong /public (tải từ Planetary Computer): trang đầu không phải chờ máy chủ dựng ảnh.
const HERO_IMG = "/hero-coffee-s2.png";

const STEPS: { icon: LucideIcon; vi: string; en: string; dvi: string; den: string }[] = [
  { icon: Footprints, vi: "Lấy ranh vườn", en: "Capture the boundary", dvi: "Vẽ trên ảnh vệ tinh hoặc cầm điện thoại đi bộ quanh vườn; mất sóng vẫn lưu.", den: "Draw on imagery or walk it with a phone; saved even offline." },
  { icon: ScanSearch, vi: "Kiểm chuẩn EU + sàng lọc", en: "EU format + screening", dvi: "Bắt lỗi tệp EU từ chối; ba bản đồ rừng 2020 bỏ phiếu, ảnh cùng mùa trước/sau mốc.", den: "Catch errors the EU rejects; three 2020 forest maps vote, same-season imagery before/after." },
  { icon: FileSignature, vi: "Hồ sơ ký số", en: "Signed dossier", dvi: "Ed25519 + QR + sổ minh bạch; tên chủ hộ ẩn, nông hộ giữ link đầy đủ.", den: "Ed25519 + QR + transparency log; the farmer's name hidden, they keep the full link." },
  { icon: Package, vi: "Lô hàng & giám sát", en: "Lots & monitoring", dvi: "Cân bằng khối lượng, nông hộ xác nhận giao hàng, radar xuyên mây canh mỗi tuần.", den: "Mass balance, farmer-confirmed deliveries, cloud-piercing radar every week." },
];

// "Sao không chụp ảnh gửi một AI khác?" — trả lời bằng việc làm được, không bằng tính từ.
const VS: { vi: string; en: string; chat: 0 | 1 | 2; trace: 0 | 1 | 2 }[] = [
  { vi: "Đo trên ĐÚNG ranh thửa từ kho ảnh vệ tinh 2017–2026 (Sentinel-2, radar ALOS, Sentinel-1)", en: "Measures on the EXACT boundary from the 2017–2026 satellite archive (Sentinel-2, ALOS radar, Sentinel-1)", chat: 0, trace: 1 },
  { vi: "Kiểm chuẩn tệp GeoJSON của EU, chỉ đúng toạ độ chỗ sai", en: "Checks the EU GeoJSON rules and pinpoints the bad coordinate", chat: 0, trace: 2 },
  { vi: "Hồ sơ ký số, sổ minh bạch có nhân chứng độc lập, kiểm offline", en: "Signed dossiers, independently witnessed transparency log, offline verification", chat: 0, trace: 1 },
  { vi: "Cân bằng khối lượng giữa MỌI doanh nghiệp — chặn rửa hàng", en: "Mass balance across ALL companies — blocks laundering", chat: 0, trace: 1 },
  { vi: "Nông hộ tự xác nhận từng đợt giao hàng, không cần tài khoản", en: "Farmers confirm each delivery themselves, no account needed", chat: 0, trace: 0 },
  { vi: "Giám sát sau phát hành mỗi tuần, radar nhìn xuyên mây mùa mưa", en: "Weekly post-issuance monitoring, radar that sees through rainy-season clouds", chat: 0, trace: 1 },
  { vi: "Trả lời luật kèm số điều khoản, không biết thì nói không biết", en: "Answers on the law cite the article; says so when it doesn't know", chat: 1, trace: 0 },
  { vi: "Tự kiểm định công khai, ngưỡng đặt trước, công bố cả lần trượt", en: "Public self-validation with pre-set bars, failures published too", chat: 0, trace: 0 },
];

function useCountUp(target: number, ms = 1200) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!target) return;
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / ms);
      setV(Math.round(target * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

function Mark({ v }: { v: 0 | 1 | 2 }) {
  return v === 2 ? <Check size={16} className="lp-yes" aria-label="có" />
    : v === 1 ? <Minus size={16} className="lp-part" aria-label="một phần" />
      : <X size={16} className="lp-no" aria-label="không" />;
}

function ScanDemo() {
  const { t } = useLang();
  const [ok, setOk] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  // Ảnh có sẵn trong bộ nhớ đệm có thể tải xong TRƯỚC khi React gắn onLoad → kiểm `complete`.
  useEffect(() => { if (imgRef.current?.complete && imgRef.current.naturalWidth > 0) setOk(true); }, []);
  return (
    <figure className="lp-scan" aria-label={t("Minh hoạ sàng lọc một vườn cà phê thật", "Screening a real coffee plot")}>
      <div className="lp-scan-img">
        <img ref={imgRef} src={HERO_IMG} alt={t("Ảnh Sentinel-2 vườn cà phê gần Buôn Ma Thuột, 01/01/2026", "Sentinel-2 image of a coffee plot near Buôn Ma Thuột, 01/01/2026")}
             width={512} height={512} onLoad={() => setOk(true)} className={ok ? "on" : ""} />
        <svg viewBox="0 0 512 512" aria-hidden="true">
          <path className="lp-scan-poly" d="M210 208 L302 208 L302 304 L210 304 Z" />
          <circle className="lp-scan-dot" cx="256" cy="256" r="6" />
        </svg>
        <span className="lp-scan-line" aria-hidden="true" />
      </div>
      <div className="lp-scan-votes">
        <span className="v v1"><TreePine size={14} aria-hidden="true" /> WorldCover 2020 · 76% {t("tán cây", "tree cover")}</span>
        <span className="v v2"><Radar size={14} aria-hidden="true" /> ALOS radar 2020 · 0% {t("rừng", "forest")}</span>
        <span className="v v3"><ScanSearch size={14} aria-hidden="true" /> Impact Observatory · 0%</span>
        <span className="v v4 ok"><BadgeCheck size={15} aria-hidden="true" /> {t("Đạt sàng lọc — 1/3 phiếu, cây lâu năm che bóng", "Passed — 1/3 votes, shaded tree crop")}</span>
      </div>
      <figcaption>{t("Số liệu thật của một vườn cà phê gần Buôn Ma Thuột · ảnh chứa dữ liệu Copernicus Sentinel-2 ngày 01/01/2026 đã xử lý", "Real figures for a coffee plot near Buôn Ma Thuột · contains modified Copernicus Sentinel-2 data, 01/01/2026")}</figcaption>
    </figure>
  );
}

export default function Landing({
  user, onAuth, onStart, onStory, onWorkspace, modules,
}: {
  user: AuthUser | null;
  onAuth: (u: AuthUser | null) => void;
  onStart: (lat: number, lon: number, label?: string) => void;
  onStory: () => void;
  onLoad: (lat: number, lon: number) => void;
  onWorkspace: () => void;
  modules: ModuleInfo[];
}) {
  const { t, lang } = useLang();
  const nModules = modules.length || 18;
  const [sc, setSc] = useState<SC | null>(null);
  const [ps, setPs] = useState<{ log_size: number; plot_dossiers: number; lot_certificates: number } | null>(null);
  useEffect(() => { trackEvent("open"); eudrPublicStats().then(setPs).catch(() => {}); }, []);
  useEffect(() => {
    let live = true;
    getScorecard(90).then((r) => live && setSc(r)).catch(() => {});
    return () => { live = false; };
  }, [lang]);
  const days = Math.max(0, Math.ceil((new Date("2026-12-30T00:00:00").getTime() - Date.now()) / 86_400_000));
  const dCount = useCountUp(days);
  const logCount = useCountUp(ps?.log_size ?? 0);

  return (
    <AppShell user={user} onAuth={onAuth}>
      <div className="lp lp3">
        <section className="lp3-hero">
          <div className="lp3-copy tt-reveal">
            <span className="lp3-badge"><span className="lp3-pulse" aria-hidden="true" /> {t(`Còn ${dCount} ngày tới hạn EUDR 30/12/2026`, `${dCount} days to the EUDR deadline, 30/12/2026`)}</span>
            <h1 className="lp3-h1">{t("Chứng minh vườn không phá rừng.", "Prove the plot is deforestation-free.")}<br /><span>{t("Bằng vệ tinh, chữ ký số và sổ ai cũng kiểm được.", "With satellites, signatures and a log anyone can check.")}</span></h1>
            <p className="lp3-lede">{t(
              "Từ 30/12/2026, mỗi lô cà phê, cao su, gỗ, ca cao vào EU phải kèm toạ độ từng thửa và bằng chứng không phá rừng sau 31/12/2020. TerraTwin biến một mảnh vườn thành bằng chứng: ranh đúng chuẩn EU, sàng lọc bằng dữ liệu vệ tinh đo trên đúng ranh, hồ sơ ký số nông hộ giữ, lô hàng không thể bị rửa.",
              "From 30/12/2026 every lot of coffee, rubber, wood or cocoa entering the EU needs each plot's coordinates and proof of no deforestation after 31/12/2020. TerraTwin turns a farm into evidence: EU-compliant boundaries, screening measured on the exact boundary, a signed dossier the farmer owns, lots that can't be laundered.")}</p>
            <div className="lp3-cta">
              <Link href="/eudr" className="lp3-btn"><Footprints size={18} aria-hidden="true" /> {t("Lấy ranh và kiểm một vườn", "Map and check a plot")}</Link>
              <Link href="/eudr?tab=lo" className="lp3-btn ghost"><ClipboardList size={18} aria-hidden="true" /> {t("Doanh nghiệp: kiểm cả lô", "Exporters: check a set")}</Link>
            </div>
            <div className="lp3-stats">
              <div><b>3</b><span>{t("bản đồ rừng 2020 bỏ phiếu", "2020 forest maps vote")}</span></div>
              <div><b>RFC 6962</b><span>{t("sổ minh bạch có nhân chứng", "witnessed transparency log")}</span></div>
              <div><b>{ps ? logCount : "—"}</b><span>{t("hồ sơ đã ký trong sổ", "signed records in the log")}</span></div>
              <div><b>{t("0đ", "$0")}</b><span>{t("cho nông hộ", "for farmers")}</span></div>
            </div>
          </div>
          <ScanDemo />
        </section>

        <section className="lp3-sec">
          <p className="eu-eyebrow">{t("Cách hoạt động", "How it works")}</p>
          <h2 className="lp3-h2">{t("Bốn bước, từ vườn tới cảng châu Âu", "Four steps, from farm to EU port")}</h2>
          <ol className="lp3-steps">
            {STEPS.map((s, i) => (
              <li key={s.vi} className="tt-card lift">
                <span className="lp3-step-n">{i + 1}</span>
                <s.icon size={22} aria-hidden="true" className="lp3-step-ic" />
                <b>{t(s.vi, s.en)}</b>
                <p>{t(s.dvi, s.den)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="lp3-sec">
          <p className="eu-eyebrow">{t("Câu giám khảo sẽ hỏi", "The question judges will ask")}</p>
          <h2 className="lp3-h2">{t("Sao không chụp ảnh gửi một AI khác?", "Why not just send a photo to another AI?")}</h2>
          <p className="lp3-sub">{t("Vì việc cần làm không phải là nhận xét một bức ảnh. Là đo trên kho dữ liệu, nộp đúng định dạng, ký được, kiểm được, và giữ được chuỗi khối lượng giữa nhiều bên.",
            "Because the job isn't commenting on a photo. It is measuring an archive, filing the right format, signing, verifying, and holding a quantity chain across many parties.")}</p>
          <div className="lp3-vs-wrap">
            <table className="lp3-vs">
              <thead><tr><th></th><th>{t("Chatbot AI tổng quát", "General AI chatbot")}</th><th>{t("Phần mềm truy xuất thông thường", "Typical traceability software")}</th><th className="tt">TerraTwin</th></tr></thead>
              <tbody>{VS.map((r) => (
                <tr key={r.vi}><td>{t(r.vi, r.en)}</td><td><Mark v={r.chat} /></td><td><Mark v={r.trace} /></td><td className="tt"><Mark v={2} /></td></tr>
              ))}</tbody>
            </table>
          </div>
          <p className="lp3-note">{t("Cột phần mềm truy xuất dựa trên tính năng công bố của các nền tảng EUDR phổ biến năm 2026: nhiều nền tảng có thu thập ranh và tờ khai DDS, ít nền tảng có sổ minh bạch hay xác nhận của nông hộ.",
            "The traceability column is based on published features of common EUDR platforms in 2026: many capture polygons and DDS, few offer a transparency log or farmer confirmation.")}</p>
        </section>

        <section className="lp3-sec lp3-quick">
          <Link href="/hom-nay" className="tt-card lift"><BadgeCheck size={20} aria-hidden="true" /><b>{t("Hôm nay", "Today")}</b><small>{t("Việc cần làm mỗi sáng", "Your morning to-do")}</small></Link>
          <Link href="/lo" className="tt-card lift"><Package size={20} aria-hidden="true" /><b>{t("Lô hàng", "Lots")}</b><small>{t("Chứng thư Merkle, DDS nháp", "Merkle certificate, draft DDS")}</small></Link>
          <Link href="/kiem" className="tt-card lift"><ShieldCheck size={20} aria-hidden="true" /><b>{t("Kiểm offline", "Verify offline")}</b><small>{t("Nhận hồ sơ? Kiểm trong trình duyệt", "Got a dossier? Check it in-browser")}</small></Link>
          <Link href="/eudr?tab=hoi-dap" className="tt-card lift"><ScanSearch size={20} aria-hidden="true" /><b>{t("Hỏi đáp EUDR", "EUDR Q&A")}</b><small>{t("Trả lời kèm số điều khoản", "Answers cite the article")}</small></Link>
        </section>

        <section className="lp3-sec">
          <p className="eu-eyebrow">{t("Thẩm định & theo dõi thửa đất", "Appraise & monitor land")}</p>
          <h2 className="lp3-h2">{t("Công cụ cho một thửa đất bất kỳ", "Tools for any plot of land")}</h2>
          <p className="lp3-sub">{t(
            `${nModules} công cụ từ dữ liệu thật: loại đất, địa hình, mười năm hiểm hoạ, theo dõi thời tiết. Cảnh báo thiên tai chỉ để THAM KHẢO — bản tin chính thức do Trung tâm Dự báo KTTV quốc gia phát (nchmf.gov.vn).`,
            `${nModules} tools on real data: land type, terrain, ten years of hazards, weather watch. Disaster alerts are for REFERENCE only — official bulletins come from Vietnam's national forecasting centre (nchmf.gov.vn).`)}</p>
          <div className="lp-tools-grid">
            <div>
              {user && <MyLand user={user} onOpen={onStart} />}
              <Start onPick={onStart} onStory={onStory} />
            </div>
            <div className="lp-tools-links">
              <div className="lp-extra-row"><DataSaverToggle />
                <button className="lp-ws" onClick={onWorkspace}><Settings size={15} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Khu làm việc", "Workspace")}</button></div>
              <Link href="/buyer" className="lp-buyer-cta"><House size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Định mua/thuê đất? Kiểm tra trước khi trả tiền", "Planning to buy or rent land? Check before you pay")}</Link>
              <Link href="/batch" className="lp-buyer-cta"><ClipboardList size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Ngân hàng: thẩm định cả danh mục thửa từ một tệp CSV", "Banks: appraise a whole plot portfolio from one CSV")}</Link>
            </div>
          </div>
        </section>

        <section className="lp-score"><Scorecard data={sc} /></section>

        <footer className="lp-foot">
          TerraTwin · {t("Hạ tầng niềm tin cho đất nông nghiệp Việt Nam", "Trust infrastructure for Vietnam's farmland")}
          <div className="lp-foot-links">
            <Link href="/eudr?tab=phuong-phap">{t("Phương pháp & kiểm định", "Method & validation")}</Link><span>·</span>
            <Link href="/about">{t("Cách hoạt động", "How it works")}</Link><span>·</span>
            <Link href="/pricing">{t("Bảng giá", "Pricing")}</Link><span>·</span>
            <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link><span>·</span>
            <Link href="/terms">{t("Điều khoản", "Terms")}</Link><span>·</span>
            <Link href="/status">{t("Trạng thái hệ thống", "System status")}</Link>
          </div>
        </footer>
      </div>
    </AppShell>
  );
}
