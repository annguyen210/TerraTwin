"use client";

/**
 * TRANG ĐẦU — theo "Kế hoạch tổng TerraTwin" (04/10/2026): "Sự thật về một mảnh đất. Đo bằng vệ tinh, ký bằng mật mã,
 * ai cũng kiểm lại được." Thứ đầu tiên người xem gặp là Ô TÌM THỬA và các năng lực ĐÃ CHẠY (lịch sử nước radar, kiểm
 * tin đăng, hồ sơ neo Bitcoin, nhật ký thửa, so sánh…), mỗi cái có nút "Thử ngay" mở đúng chỗ. EUDR lùi thành
 * chương 2 (vẫn đủ: ranh, sàng lọc, hồ sơ vườn, lô hàng). Mọi tài khoản có đủ mọi tính năng.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  BadgeCheck, Check, ClipboardList, Cpu, FileSearch, FileSignature, Footprints, GitCompare, Link2, Minus, NotebookPen,
  Package, Radar, ScanSearch, Settings, ShieldCheck, Sprout, TreePine, Waves, X, type LucideIcon,
} from "lucide-react";

import AppShell from "./AppShell";
import Scorecard from "./Scorecard";
import Start from "./Start";
import { eudrPublicStats, getScorecard, trackEvent, type AuthUser, type ModuleInfo, type Scorecard as SC } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { DataSaverToggle } from "@/lib/net";

// Chỉ người ĐÃ đăng nhập mới thấy "Thửa của tôi" — khách mới không phải tải mã của nó (Lighthouse TBT).
const MyLand = dynamic(() => import("./MyLand"));

const HERO_IMG = "/hero-coffee-s2.png";
const HUE = { lat: 16.5751, lon: 107.4952, label: "Đồng lúa Quảng Điền, Huế" };   // thửa có lịch sử nước đã kiểm (cổng GĐ2)

type Chapter = "plan" | "mine" | "verify" | "tools";

// Ba trụ sản phẩm (kế hoạch tổng). Mỗi dòng là một thứ ĐÃ CHẠY — không có tính năng nào khoá sau gói trả phí.
const PILLARS: { tag: [string, string]; name: [string, string]; lede: [string, string]; items: [string, string][]; ch: Chapter; who: [string, string] }[] = [
  { tag: ["Trụ 1 · mua một lần", "Pillar 1 · one-off"], name: ["Hồ sơ đất", "Land dossier"], ch: "plan",
    lede: ["Chọn một thửa, nhận hồ sơ ký số trong vài chục giây.", "Pick a plot, get a signed dossier in seconds."],
    items: [["Lịch sử nước radar 2017 → nay, kéo theo năm trên bản đồ", "Radar water history 2017 → now, scrub by year on the map"],
            ["Loại đất thật + \"đất có đổi khác sau 2021?\" (AlphaEarth)", "Real land cover + \"changed since 2021?\" (AlphaEarth)"],
            ["10 năm hiểm hoạ ERA5: lũ, sạt lở, hạn", "10 years of ERA5 hazards: flood, landslide, drought"],
            ["Ký số Ed25519, QR, neo Bitcoin — mỗi câu bấm ra bằng chứng", "Ed25519 signed, QR, Bitcoin-anchored — each sentence opens its evidence"]],
    who: ["Người sắp mua/thuê đất · môi giới chứng minh đất \"sạch\"", "Buyers and renters · brokers proving land is clean"] },
  { tag: ["Trụ 2 · mở mỗi ngày", "Pillar 2 · daily"], name: ["Canh đất", "Land watch"], ch: "mine",
    lede: ["Lý do mở TerraTwin mỗi sáng.", "The reason to open TerraTwin every morning."],
    items: [["Nhật ký thửa: chỉ báo khi có thay đổi thật", "Plot journal: only real changes"],
            ["Bản tin sáng, cảnh báo đẩy về điện thoại", "Morning brief, push alerts"],
            ["Đối chiếu ba chiều: câu trả lời ↔ radar ↔ mưa", "Three-way check: your answer ↔ radar ↔ rain"],
            ["Cảm biến ký số (độ mặn, độ ẩm đất) vào nhật ký trong 10 giây", "Signed sensors (salinity, soil moisture) in the journal within 10 s"]],
    who: ["Chủ đất, nông hộ, hợp tác xã", "Landowners, farmers, co-ops"] },
  { tag: ["Trụ 3 · doanh nghiệp", "Pillar 3 · business"], name: ["Kiểm chứng", "Verification"], ch: "verify",
    lede: ["Cho tổ chức cần thẩm định nhiều thửa và kiểm hồ sơ.", "For organisations appraising many plots and checking dossiers."],
    items: [["Kiểm chứng tin đăng bán đất từng câu", "Sentence-by-sentence land-listing check"],
            ["So sánh 2–4 thửa trên một màn", "Compare 2–4 plots on one screen"],
            ["Thẩm định hàng loạt từ CSV, API có khoá", "Batch appraisal from CSV, keyed API"],
            ["Trang kiểm chứng công khai + script tự kiểm không cần tin máy chủ", "Public verify page + a script that checks without trusting us"]],
    who: ["Ngân hàng, bảo hiểm, sàn môi giới, doanh nghiệp xuất khẩu", "Banks, insurers, brokerages, exporters"] },
];

// 8 năng lực đặc trưng — mỗi cái có lối "Thử ngay" mở đúng chỗ.
const CAPS: { icon: LucideIcon; name: [string, string]; see: [string, string]; go: { ch?: Chapter; href?: string } }[] = [
  { icon: Waves, name: ["Lịch sử nước nhìn xuyên mây", "Water history through clouds"], go: { ch: "plan" },
    see: ["Radar Sentinel-1 từ 2017 của đúng thửa — kể cả giữa bão. Bấm từng đợt là thấy ảnh radar ngày đó.", "Sentinel-1 radar since 2017 for the exact plot — even mid-storm. Click an event to see that day's image."] },
  { icon: FileSearch, name: ["Kiểm chứng tin đăng bán đất", "Land-listing check"], go: { ch: "verify" },
    see: ["Dán \"cao ráo, không bao giờ ngập\" → từng câu Khớp / Mâu thuẫn / Không đủ dữ liệu, kèm số đo.", "Paste \"high ground, never floods\" → each claim Consistent / Contradicted / Not enough data, with measurements."] },
  { icon: Link2, name: ["Hồ sơ không ai sửa được, kể cả TerraTwin", "A dossier nobody can alter — us included"], go: { href: "/kiem" },
    see: ["Ký số + sổ Merkle + neo Bitcoin (OpenTimestamps). Sửa một chữ là báo đỏ.", "Signature + Merkle log + Bitcoin anchor (OpenTimestamps). Change one letter and it turns red."] },
  { icon: ScanSearch, name: ["Mỗi câu bấm vào là ra bằng chứng", "Every sentence opens its evidence"], go: { ch: "plan" },
    see: ["Số liệu gốc, nguồn, ngày đo, cách tái lập. AI chỉ viết lại lời; câu có số lạ bị loại.", "Raw value, source, date, how to reproduce. AI only rewords; sentences with unknown numbers are dropped."] },
  { icon: Radar, name: ["Đối chiếu ba chiều", "Three-way check"], go: { ch: "mine" },
    see: ["Câu trả lời \"ruộng có ngập\" ↔ radar cùng tuần ↔ mưa đo được → khớp hay lệch.", "\"Did it flood?\" answers ↔ same-week radar ↔ measured rain → consistent or not."] },
  { icon: NotebookPen, name: ["Nhật ký thửa mỗi sáng", "Plot journal every morning"], go: { ch: "mine" },
    see: ["\"Từ lần mở trước: mưa 42 mm, radar ngày 03/10 không thấy nước.\" Không có gì đổi thì im.", "\"Since last visit: 42 mm rain, 03/10 radar shows no water.\" Silent when nothing changed."] },
  { icon: GitCompare, name: ["So sánh thửa", "Compare plots"], go: { href: "/so-sanh" },
    see: ["2–4 thửa cạnh nhau: nước phủ, độ cao, sông/biển, vùng mặn, lũ và sạt lở 10 năm.", "2–4 plots side by side: water, elevation, river/sea, salinity, 10-year floods and landslides."] },
  { icon: Cpu, name: ["Cảm biến thật nối thẳng vào hồ sơ", "Real sensors wired into the record"], go: { href: "/thiet-bi" },
    see: ["ESP32 + đầu đo EC ký từng số đo; nhúng vào cốc nước muối là độ mặn hiện lên nhật ký.", "ESP32 + EC probe signs every reading; dip it in salt water and salinity shows in the journal."] },
];

// "Sao không chụp ảnh gửi ChatGPT?" — bảng của kế hoạch tổng.
const VS: [string, string, string, string][] = [
  ["Thửa này từng ngập chưa?", "Đoán theo hiểu biết chung về vùng", "Đọc 9 năm ảnh radar của đúng thửa, chỉ ra từng ngày nước phủ", "Has this plot flooded?"],
  ["Con số có đúng không?", "Không ai chấm điểm câu trả lời", "Sổ điểm công khai + thẻ mô hình, kể cả mô hình đã trượt", "Are the numbers right?"],
  ["Đưa cho ngân hàng được không?", "Một đoạn chữ ai cũng sửa được", "Hồ sơ ký số, sổ Merkle, neo Bitcoin, quét QR là biết bị sửa chưa", "Can a bank use it?"],
  ["Canh đất khi mình ngủ", "Chỉ trả lời khi được hỏi", "Radar quét định kỳ, nhật ký thửa, bản tin sáng, báo đẩy", "Watching while you sleep"],
  ["Kiểm lời môi giới", "Tóm tắt lại tin đăng", "Đối chiếu từng câu khẳng định với dữ liệu đo, tô đỏ/xanh", "Checking the broker"],
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

function ScanDemo() {
  const { t } = useLang();
  const [ok, setOk] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
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

const EUDR_STEPS: { icon: LucideIcon; vi: string; en: string }[] = [
  { icon: Footprints, vi: "Lấy ranh vườn — vẽ hoặc đi bộ GPS", en: "Capture the boundary — draw or GPS walk" },
  { icon: ScanSearch, vi: "Kiểm chuẩn EU + ba bản đồ rừng 2020 bỏ phiếu", en: "EU format + three 2020 forest maps vote" },
  { icon: FileSignature, vi: "Hồ sơ vườn ký số, tên chủ hộ ẩn", en: "Signed plot dossier, farmer name hidden" },
  { icon: Package, vi: "Lô hàng: cân bằng khối lượng, chứng thư Merkle", en: "Lots: mass balance, Merkle certificate" },
];

export default function Landing({
  user, onAuth, onStart, onStory, onWorkspace, modules,
}: {
  user: AuthUser | null;
  onAuth: (u: AuthUser | null) => void;
  onStart: (lat: number, lon: number, label?: string, chapter?: Chapter) => void;
  onStory: () => void;
  onLoad: (lat: number, lon: number) => void;
  onWorkspace: () => void;
  modules: ModuleInfo[];
}) {
  const { t, lang } = useLang();
  const nModules = modules.length || 18;
  const [sc, setSc] = useState<SC | null>(null);
  const [ps, setPs] = useState<{ log_size: number; plot_dossiers: number; lot_certificates: number } | null>(null);
  // Số ngày tới hạn EUDR tính Ở TRÌNH DUYỆT theo ngày thật — trước đây tính lúc build trang tĩnh nên hiện 0/54/73 lẫn lộn.
  const [days, setDays] = useState<number | null>(null);
  const [want, setWant] = useState<Chapter>("plan");
  const searchRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    trackEvent("open");
    eudrPublicStats().then(setPs).catch(() => {});
    setDays(Math.max(0, Math.ceil((new Date("2026-12-30T00:00:00+07:00").getTime() - Date.now()) / 86_400_000)));
  }, []);
  useEffect(() => {
    let live = true;
    getScorecard(90).then((r) => live && setSc(r)).catch(() => {});
    return () => { live = false; };
  }, [lang]);
  const logCount = useCountUp(ps?.log_size ?? 0);

  // "Thử ngay": mở thẳng thửa mẫu (Huế — thửa có lịch sử nước đã kiểm) ở đúng tab; hoặc cuộn tới ô tìm thửa của bạn.
  function tryNow(ch: Chapter) { onStart(HUE.lat, HUE.lon, HUE.label, ch); }
  function pickMine(ch: Chapter) { setWant(ch); searchRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }

  return (
    <AppShell user={user} onAuth={onAuth}>
      <div className="lp lp3">
        <section className="lp4-hero">
          <div className="lp3-copy tt-reveal">
            <span className="lp3-badge"><span className="lp3-pulse" aria-hidden="true" /> {t("Đo bằng vệ tinh · ký bằng mật mã · ai cũng kiểm lại được", "Measured by satellite · signed with cryptography · checkable by anyone")}</span>
            <h1 className="lp3-h1">{t("Sự thật về một mảnh đất.", "The truth about a plot of land.")}<br />
              <span>{t("Thửa này từng ngập chưa? Tin đăng có nói thật không?", "Has it ever flooded? Is the listing telling the truth?")}</span></h1>
            <p className="lp3-lede">{t(
              "Chọn một thửa: radar nhìn xuyên mây đọc lại 9 năm xem nước đã phủ bao nhiêu lần, loại đất thật hiện nay, hiểm hoạ 10 năm, đối chiếu từng câu trong tin đăng bán đất — rồi phát hành hồ sơ ký số mà ngân hàng, người mua quét QR là biết bị sửa hay chưa. Không điểm số hộp đen: mọi câu đều bấm ra số đo và nguồn.",
              "Pick a plot: cloud-piercing radar re-reads 9 years to count how often water covered it, today's real land cover, 10 years of hazards, each claim in a sale listing checked against measurements — then issue a signed dossier a bank or buyer can verify by scanning a QR. No black-box score: every sentence opens its measurement and source.")}</p>
            <div className="lp3-cta">
              <button type="button" className="lp3-btn" onClick={() => tryNow("plan")}><Waves size={18} aria-hidden="true" /> {t("Xem ngay: lịch sử nước thửa ở Huế", "See it now: water history of a plot in Huế")}</button>
              <button type="button" className="lp3-btn ghost" onClick={() => tryNow("verify")}><FileSearch size={18} aria-hidden="true" /> {t("Kiểm một tin đăng bán đất", "Check a land listing")}</button>
            </div>
            <p className="lp4-free">✓ {t("Mọi tài khoản có đủ mọi tính năng — không cần nâng cấp mới dùng được.", "Every account gets every feature — no upgrade needed.")}</p>
          </div>
          <div className="lp4-search" ref={searchRef} id="tim-thua">
            <p className="eu-eyebrow">{t("Thửa đất của bạn ở đâu?", "Where is your land?")}</p>
            <div className="lp4-want" role="group" aria-label={t("Mở thửa ở tab", "Open the plot on tab")}>
              {([["plan", "Hồ sơ", "Dossier"], ["mine", "Canh đất", "Watch"], ["verify", "Kiểm chứng", "Verify"]] as const).map(([k, vi, en]) => (
                <button key={k} type="button" className={want === k ? "on" : ""} aria-pressed={want === k} onClick={() => setWant(k)}>{t(vi, en)}</button>
              ))}
            </div>
            {user && <MyLand user={user} onOpen={(la, lo, lab) => onStart(la, lo, lab, want)} />}
            <Start onPick={(la, lo, lab) => onStart(la, lo, lab, want)} onStory={onStory} />
          </div>
        </section>

        <section className="lp3-sec">
          <p className="eu-eyebrow">{t("Sản phẩm", "Product")}</p>
          <h2 className="lp3-h2">{t("Ba trụ — chọn đúng việc bạn cần", "Three pillars — pick what you need")}</h2>
          <div className="lp4-pillars">
            {PILLARS.map((p) => (
              <article key={p.name[0]} className="tt-card lp4-pillar">
                <span className="lp4-tag">{t(...p.tag)}</span>
                <h3>{t(...p.name)}</h3>
                <p>{t(...p.lede)}</p>
                <ul>{p.items.map((it) => <li key={it[0]}><Check size={14} aria-hidden="true" /> {t(...it)}</li>)}</ul>
                <div className="lp4-pillar-go">
                  <button type="button" className="bat-btn" onClick={() => tryNow(p.ch)}>{t("Thử ngay với thửa mẫu", "Try with a sample plot")}</button>
                  <button type="button" className="bat-btn ghost" onClick={() => pickMine(p.ch)}>{t("Chọn thửa của tôi", "Pick my plot")}</button>
                </div>
                <small>{t(...p.who)}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="lp3-sec">
          <p className="eu-eyebrow">{t("Đang chạy, không phải bản vẽ", "Live, not a mock-up")}</p>
          <h2 className="lp3-h2">{t("8 năng lực — bấm là chạy", "8 capabilities — click to run")}</h2>
          <div className="lp4-caps">
            {CAPS.map((c, i) => {
              const body = <><span className="lp4-cap-n">{i + 1}</span><c.icon size={20} aria-hidden="true" /><b>{t(...c.name)}</b><p>{t(...c.see)}</p><span className="lp4-cap-go">{t("Thử ngay →", "Try it →")}</span></>;
              return c.go.href
                ? <Link key={c.name[0]} href={c.go.href} className="tt-card lift lp4-cap">{body}</Link>
                : <button key={c.name[0]} type="button" className="tt-card lift lp4-cap" onClick={() => tryNow(c.go.ch!)}>{body}</button>;
            })}
          </div>
          <p className="lp3-note">{t("Mô hình AI chỉ được bật khi vượt ngưỡng đặt trước; trượt thì công khai — xem ", "AI models are switched on only above pre-set thresholds; failures are published — see ")}<Link href="/mo-hinh">{t("thẻ mô hình", "model cards")}</Link>.</p>
        </section>

        <section className="lp3-sec">
          <p className="eu-eyebrow">{t("Câu giám khảo sẽ hỏi", "The question judges will ask")}</p>
          <h2 className="lp3-h2">{t("Sao không chụp ảnh gửi ChatGPT là xong?", "Why not just send a photo to ChatGPT?")}</h2>
          <div className="lp3-vs-wrap">
            <table className="lp3-vs">
              <thead><tr><th></th><th>{t("Chatbot AI", "AI chatbot")}</th><th className="tt">TerraTwin</th></tr></thead>
              <tbody>{VS.map((r) => (
                <tr key={r[0]}><td><b>{lang === "en" ? r[3] : r[0]}</b></td><td><X size={14} className="lp-no" aria-hidden="true" /> {r[1]}</td><td className="tt"><Check size={14} className="lp-yes" aria-hidden="true" /> {r[2]}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <p className="lp3-note">{t("Zillow từng gắn điểm rủi ro khí hậu vào tin đăng (9/2024) rồi phải gỡ (cuối 2025) vì không chứng minh được độ đúng. TerraTwin đi đường ngược lại: bằng chứng đo được cho từng thửa, tự công bố tỉ lệ sai, ký số để không ai sửa được.",
            "Zillow added climate-risk scores to listings (9/2024) and had to remove them (late 2025) for lack of proven accuracy. TerraTwin goes the other way: measured evidence per plot, published error rates, signatures nobody can alter.")}</p>
        </section>

        <section className="lp3-sec lp4-eudr">
          <div>
            <p className="eu-eyebrow">{t("Chương 2 · EUDR", "Chapter 2 · EUDR")}{days != null ? ` · ${t(`còn ${days} ngày tới hạn 30/12/2026`, `${days} days to 30/12/2026`)}` : ""}</p>
            <h2 className="lp3-h2">{t("Chứng minh vườn không phá rừng", "Prove a plot is deforestation-free")}</h2>
            <p className="lp3-sub">{t("Mỗi lô cà phê, cao su, gỗ, ca cao vào EU phải kèm toạ độ từng thửa và bằng chứng không phá rừng sau 31/12/2020.",
              "Every lot of coffee, rubber, wood or cocoa entering the EU needs plot coordinates and proof of no deforestation after 31/12/2020.")}</p>
            <ol className="lp4-steps">{EUDR_STEPS.map((s) => <li key={s.vi}><s.icon size={18} aria-hidden="true" /> {t(s.vi, s.en)}</li>)}</ol>
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

        <section className="lp3-sec lp3-quick">
          <Link href="/hom-nay" className="tt-card lift"><BadgeCheck size={20} aria-hidden="true" /><b>{t("Hôm nay", "Today")}</b><small>{t("Việc cần làm mỗi sáng", "Your morning to-do")}</small></Link>
          <Link href="/kiem" className="tt-card lift"><ShieldCheck size={20} aria-hidden="true" /><b>{t("Kiểm một hồ sơ", "Verify a dossier")}</b><small>{t("Mã, QR hoặc tệp JSON đã ký", "ID, QR or signed JSON")}</small></Link>
          <Link href="/so-sanh" className="tt-card lift"><GitCompare size={20} aria-hidden="true" /><b>{t("So sánh thửa", "Compare plots")}</b><small>{t("2–4 thửa trên một màn", "2–4 plots on one screen")}</small></Link>
          <Link href="/mo-hinh" className="tt-card lift"><Sprout size={20} aria-hidden="true" /><b>{t("Thẻ mô hình AI", "AI model cards")}</b><small>{t("Kể cả mô hình đã trượt", "Including the failures")}</small></Link>
        </section>

        <section className="lp3-sec">
          <div className="lp-extra-row"><DataSaverToggle />
            <button className="lp-ws" onClick={onWorkspace}><Settings size={15} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Khu làm việc", "Workspace")}</button>
            <Link href="/batch" className="lp-buyer-cta"><ClipboardList size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Ngân hàng: thẩm định cả danh mục thửa từ CSV", "Banks: appraise a portfolio from CSV")}</Link>
            <span className="lp3-note">{t(`Thêm ${nModules} công cụ chuyên sâu trong tab "Chuyên sâu" của mỗi thửa. Cảnh báo thiên tai chỉ để tham khảo — bản tin chính thức: nchmf.gov.vn.`,
              `Plus ${nModules} in-depth tools in each plot's "In depth" tab. Disaster alerts are for reference — official bulletins: nchmf.gov.vn.`)}</span>
          </div>
        </section>

        <section className="lp-score"><Scorecard data={sc} /></section>

        <footer className="lp-foot">
          TerraTwin · {t("Sự thật về một mảnh đất — hạ tầng niềm tin cho đất đai Việt Nam", "The truth about a plot of land — trust infrastructure for Vietnam's land")}
          <div className="lp-foot-links">
            <Link href="/mo-hinh">{t("Thẻ mô hình", "Model cards")}</Link><span>·</span>
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
