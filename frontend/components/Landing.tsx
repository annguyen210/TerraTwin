"use client";

/**
 * TRANG ĐẦU — theo "Kế hoạch tổng TerraTwin" (04/10/2026): "Sự thật về một mảnh đất. Đo bằng vệ tinh, ký bằng mật mã,
 * ai cũng kiểm lại được." Thứ đầu tiên người xem gặp là Ô TÌM THỬA và các năng lực ĐÃ CHẠY (lịch sử nước radar, kiểm
 * tin đăng, hồ sơ neo Bitcoin, nhật ký thửa, so sánh…), mỗi cái có nút "Thử ngay" mở đúng chỗ. EUDR lùi thành
 * chương 2 (vẫn đủ: ranh, sàng lọc, hồ sơ vườn, lô hàng). Mọi tài khoản có đủ mọi tính năng.
 *
 * 29/10/2026 — gọt quanh MỘT câu chuyện: "định mua đất → kiểm lời rao trước khi xuống tiền". Ba trụ + tám năng lực +
 * EUDR + sổ điểm xếp liền nhau làm người xem không nhớ nổi TerraTwin là gì; bỏ khối "Ba trụ" (trùng tám năng lực),
 * đưa ba bước + bốn con số kiểm chứng độc lập lên ngay dưới phần đầu, thửa mẫu là ruộng ngập bão Yagi UNOSAT đã ghi.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  BadgeCheck, Check, ClipboardList, Cpu, FileSearch, FileSignature, Footprints, GitCompare, Link2, NotebookPen,
  Package, Radar, ScanSearch, Settings, ShieldCheck, Sprout, TreePine, Waves, X, type LucideIcon,
} from "lucide-react";

import AppShell from "./AppShell";
import Scorecard from "./Scorecard";
import Start from "./Start";
import { eudrPublicStats, getScorecard, trackEvent, type AuthUser, type ModuleInfo, type Scorecard as SC } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { DataSaverToggle } from "@/lib/net";
import { DEMO_LISTING, DEMO_PLOT } from "@/lib/demo";
import { saveListingDraft } from "@/lib/listingDraft";

// Chỉ người ĐÃ đăng nhập mới thấy "Thửa của tôi" — khách mới không phải tải mã của nó (Lighthouse TBT).
const MyLand = dynamic(() => import("./MyLand"));

const HERO_IMG = "/hero-coffee-s2.png";

type Chapter = "plan" | "mine" | "verify" | "tools";

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

// Luồng chính — ba bước của người định mua đất.
const STEPS: { icon: LucideIcon; vi: string; en: string }[] = [
  { icon: ClipboardList, vi: "Dán tin rao — hoặc chọn thửa trên bản đồ", en: "Paste the listing — or pick the plot on the map" },
  { icon: FileSearch, vi: "Từng câu: Khớp · Mâu thuẫn · Không đủ dữ liệu, kèm số đo và ngày", en: "Each claim: Consistent · Contradicted · Not enough data, with measurements and dates" },
  { icon: FileSignature, vi: "Hồ sơ ký số — người bán, ngân hàng quét QR là kiểm lại được", en: "A signed dossier — the seller or a bank scans the QR to re-check it" },
];

// Ba con số chấm MỘT lần, khoá trong repo (backend/data/eval/water_unosat_result.json,
// listing_gate_v9_result.json) + cơ chế ký — đổi số ở đây phải đổi từ tệp kết quả, không làm tròn đẹp.
const PROOF: { b: string; vi: string; en: string }[] = [
  { b: "60/80", vi: "điểm ngập trên bản đồ UNOSAT (10 trận 2020–2025) radar thấy đợt nước", en: "flooded points on UNOSAT maps (10 floods 2020–2025) where radar saw the water" },
  { b: "0/73", vi: "điểm khô (cách vùng nước ≥ 500 m) bị báo nhầm là có đợt nước", en: "dry points (≥ 500 m from water) falsely flagged with a water event" },
  { b: "0,98", vi: "F1 nhận câu khẳng định trên 30 tin rao Facebook thật, nhãn người (lần 9)", en: "F1 for spotting claims in 30 real Facebook ads, human labels (run 9)" },
  { b: "Ed25519", vi: "chữ ký số + sổ minh bạch + neo Bitcoin: sửa một chữ là lộ", en: "signature + transparency log + Bitcoin anchor: one changed letter shows" },
];

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

  // "Thử ngay": mở thẳng thửa mẫu (ruộng ngập bão Yagi, UNOSAT đã ghi) ở đúng tab. Tab Kiểm chứng thì điền sẵn TIN MẪU
  // (ô kiểm tin ghi rõ là tin soạn để minh hoạ).
  function tryNow(ch: Chapter) {
    if (ch === "verify") saveListingDraft(DEMO_LISTING);
    onStart(DEMO_PLOT.lat, DEMO_PLOT.lon, DEMO_PLOT.label, ch);
  }

  return (
    <AppShell user={user} onAuth={onAuth}>
      <div className="lp lp3">
        <section className="lp4-hero">
          <div className="lp3-copy tt-reveal">
            <span className="lp3-badge"><span className="lp3-pulse" aria-hidden="true" /> {t("Đo bằng vệ tinh · ký bằng mật mã · ai cũng kiểm lại được", "Measured by satellite · signed with cryptography · checkable by anyone")}</span>
            <h1 className="lp3-h1">{t("Sự thật về một mảnh đất.", "The truth about a plot of land.")}<br />
              <span>{t("Định mua đất? Kiểm lời rao trước khi xuống tiền.", "Buying land? Check the listing before you pay.")}</span></h1>
            <p className="lp3-lede">{t(
              "Người bán viết \"cao ráo, không bao giờ ngập\". TerraTwin đặt từng câu đó cạnh số đo của đúng thửa: ảnh radar Sentinel-1 nhìn xuyên mây từ 2017, độ cao địa hình, khoảng cách tới sông và biển. Câu nào trái với dữ liệu thì tô đỏ, kèm ngày và nguồn.",
              "The seller writes \"high ground, never floods\". TerraTwin puts each claim next to measurements of that exact plot: cloud-piercing Sentinel-1 radar since 2017, terrain height, distance to rivers and the sea. Claims the data contradicts turn red, with dates and sources.")}</p>
            <ol className="lp4-steps">{STEPS.map((x, n) => <li key={x.vi}><x.icon size={18} aria-hidden="true" /> <b>{n + 1}.</b> {t(x.vi, x.en)}</li>)}</ol>
            <div className="lp3-cta">
              <button type="button" className="lp3-btn" onClick={() => tryNow("verify")}><FileSearch size={18} aria-hidden="true" /> {t("Kiểm một tin đăng mẫu — ruộng ngập bão Yagi", "Check a sample listing — a field flooded by Typhoon Yagi")}</button>
              <button type="button" className="lp3-btn ghost" onClick={() => tryNow("plan")}><Waves size={18} aria-hidden="true" /> {t("Xem ngay: 9 năm nước của thửa đó", "See it now: 9 years of water on that plot")}</button>
            </div>
            <p className="lp3-note">{t("Tin mẫu do TerraTwin soạn để minh hoạ. Thửa là thật: bản đồ ngập UNOSAT ngày 10/9/2024 (bão Yagi) ghi điểm này ngập.",
              "The sample ad is written by TerraTwin for illustration. The plot is real: the UNOSAT flood map of 10/9/2024 (Typhoon Yagi) marks it flooded.")}</p>
            <p className="lp4-free">✓ {t("Mọi tài khoản có đủ mọi tính năng — không cần nâng cấp mới dùng được.", "Every account gets every feature — no upgrade needed.")}</p>
          </div>
          <div className="lp4-search" id="tim-thua">
            <p className="eu-eyebrow">{t("Mảnh đất bạn định mua — hoặc đang có — ở đâu?", "Where is the land you are buying — or own?")}</p>
            <div className="lp4-want" role="group" aria-label={t("Mở thửa ở tab", "Open the plot on tab")}>
              {([["plan", "Hồ sơ", "Dossier"], ["mine", "Canh đất", "Watch"], ["verify", "Kiểm chứng", "Verify"]] as const).map(([k, vi, en]) => (
                <button key={k} type="button" className={want === k ? "on" : ""} aria-pressed={want === k} onClick={() => setWant(k)}>{t(vi, en)}</button>
              ))}
            </div>
            {user && <MyLand user={user} onOpen={(la, lo, lab) => onStart(la, lo, lab, want)} />}
            <Start onPick={(la, lo, lab) => onStart(la, lo, lab, want)} onStory={onStory} onListing={() => setWant("verify")} />
          </div>
        </section>

        <section className="lp3-sec">
          <p className="eu-eyebrow">{t("Vì sao tin được", "Why you can trust it")}</p>
          <h2 className="lp3-h2">{t("Chấm bằng dữ liệu người khác làm ra — kể cả chỗ còn yếu", "Scored against data made by others — weak spots included")}</h2>
          <div className="lp3-stats">{PROOF.map((x) => <div key={x.b}><b>{x.b}</b><span>{t(x.vi, x.en)}</span></div>)}</div>
          <p className="lp3-note">{t("Bản đồ UNOSAT từ vệ tinh khác Sentinel-1 chỉ khớp 6/16 điểm ngập; tin rao lần 9 do chủ dự án tự gán. Đầy đủ ở ", "UNOSAT maps from satellites other than Sentinel-1 match only 6/16 flooded points; run-9 ads were labelled by the project owner. Full details in the ")}<Link href="/mo-hinh">{t("thẻ mô hình", "model cards")}</Link>.</p>
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
