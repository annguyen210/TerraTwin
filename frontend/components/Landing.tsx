"use client";

/**
 * TRANG ĐÓN (landing) — hiện khi CHƯA chọn thửa.
 *
 * Song ngữ VI/EN cho phần marketing (người xem quốc tế / giám khảo). Số liệu sổ
 * điểm lấy một lần ở đây, dùng cho cả ô hero lẫn khối sổ điểm bên dưới; có đủ
 * mẫu đo thật thì hero hiện số đo thật, chưa đủ thì hiện số backtest kèm nhãn.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BadgeCheck, Camera, ClipboardList, FileSignature, House, type LucideIcon,
} from "lucide-react";

import Account from "./Account";
import MyLand from "./MyLand";
import Scorecard from "./Scorecard";
import Start from "./Start";
import { getScorecard, trackEvent, type AuthUser, type ModuleInfo, type Scorecard as SC } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";
import { DataSaverToggle } from "@/lib/net";

// Bốn trụ cột THẨM ĐỊNH — mỗi câu ứng với một tính năng đang chạy thật, không hứa.
const FEATURES: { icon: LucideIcon; tvi: string; ten: string; bvi: string; ben: string }[] = [
  {
    icon: FileSignature,
    tvi: "Hồ sơ đất số có chữ ký số",
    ten: "Digitally signed land dossier",
    bvi: "Một tờ thẩm định: loại đất (ESA 10 m), cao hay trũng, mười năm hiểm hoạ, rủi ro hiện tại, nguồn dữ liệu. Ký Ed25519, nối vào sổ đăng ký công khai móc xích — quét QR là thấy bản gốc, sửa một chữ là lộ.",
    ben: "One appraisal sheet: land type (ESA 10 m), high or low ground, ten years of hazards, current risk, data sources. Ed25519-signed and chained into a public registry — scan the QR to see the original; change one word and it shows.",
  },
  {
    icon: Camera,
    tvi: "Ảnh thực địa đã kiểm",
    ten: "Verified field photos",
    bvi: "Ảnh chủ đất gửi được kiểm toạ độ chụp, khoảng cách tới thửa, thời điểm chụp, dấu phần mềm chỉnh ảnh — và đã từng dùng cho thửa khác hay chưa.",
    ben: "Photos from the owner are checked for capture location, distance to the plot, capture time, photo-editing traces — and whether they were already used for another plot.",
  },
  {
    icon: ClipboardList,
    tvi: "Thẩm định cả danh mục",
    ten: "Whole-portfolio appraisal",
    bvi: "Ngân hàng, hợp tác xã, bảo hiểm tải một tệp CSV: mỗi thửa có loại đất thật, mức rủi ro từ dữ liệu thật, số đợt ngập mười năm — gộp thành bảng rủi ro danh mục, tải về Excel.",
    ben: "Banks, co-ops and insurers upload one CSV: every plot gets its real land type, risk from real data and ten-year flood count — rolled into a portfolio risk table you can open in Excel.",
  },
  {
    icon: BadgeCheck,
    tvi: "Tự chấm điểm chính mình",
    ten: "Grades its own track record",
    bvi: "Mỗi cảnh báo được chấm lại bằng số đo thật; tỉ lệ báo bừa và bỏ sót công khai. Mô hình AI không qua ngưỡng đặt trước thì không được bật — và lần không đạt cũng được công khai.",
    ben: "Every alert is re-scored against measured data; false-alarm and miss rates are public. An AI model that misses its pre-set bar is not switched on — and the failed run is published too.",
  },
];

export default function Landing({
  user,
  onAuth,
  onStart,
  onStory,
  onLoad,
  onWorkspace,
  modules,
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
  useEffect(() => { trackEvent("open"); }, []);        // N6 — mở app
  useEffect(() => {
    let live = true;
    getScorecard(90).then((r) => live && setSc(r)).catch(() => {});
    return () => { live = false; };
  }, [lang]);                                          // lấy lại khi đổi ngôn ngữ
  const doThat = sc?.enough && sc.far_pct !== null;

  return (
    <div className="lp">
      <header className="lp-top">
        <div className="lp-brand">◵ TerraTwin</div>
        <div className="lp-top-actions">
          <LangToggle />
          <DataSaverToggle />
          <button className="lp-ws" onClick={onWorkspace}>
            ⚙️ {t("Khu làm việc", "Workspace")}
          </button>
          <Account user={user} onAuth={onAuth} />
        </div>
      </header>

      <div className="lp-body">
        {/* HERO + ô nhập */}
        <section className="lp-hero">
          <div className="lp-hero-txt">
            <span className="lp-eyebrow">
              {t("Thẩm định đất có kiểm chứng · Bản sao số đất đai Việt Nam", "Verifiable land due diligence · Vietnam's land digital twin")}
            </span>
            <h1 className="lp-h1">
              {t("Biết thửa đất ", "Know the land ")}
              <span>{t("trước khi xuống tiền", "before you put money on it")}</span>
            </h1>
            <p className="lp-lede">
              {t(
                "Chọn một thửa: TerraTwin cho biết đó là đất gì, nằm cao hay trũng, mười năm qua gặp hiểm hoạ gì và bảy ngày tới có gì đe doạ — từ dữ liệu vệ tinh và khí hậu thật, hiệu chuẩn riêng cho chính chỗ đó. Rồi phát hành Hồ sơ đất số có chữ ký số để ngân hàng, người mua tự kiểm bản gốc.",
                "Pick a plot: TerraTwin tells you what land it is, whether it sits high or low, which hazards hit it in ten years and what threatens it this week — from real satellite and climate data, calibrated to that spot. Then it issues a digitally signed Land Dossier that banks and buyers can verify themselves.",
              )}
            </p>
            <div className="lp-stats">
              <div><b>{nModules}</b><span>{t("mũi nhọn", "spearheads")}</span></div>
              <div><b>Ed25519</b><span>{t("hồ sơ ký số", "signed dossiers")}</span></div>
              <div title={doThat
                ? t("Đo trên chính những cảnh báo TerraTwin đã phát trong 90 ngày qua.",
                     "Measured on TerraTwin's own alerts over the last 90 days.")
                : t("Đo trên backtest các thiên tai lịch sử.",
                     "Measured on backtests of historical disasters.")}>
                <b>{doThat ? `${sc!.far_pct}%` : "~3%"}</b>
                <span>{doThat ? t("báo bừa · đo thật", "false alarms · measured")
                              : t("báo bừa · backtest", "false alarms · backtest")}</span>
              </div>
              <div><b>{t("0đ", "$0")}</b><span>{t("miễn phí dùng thử", "free to try")}</span></div>
            </div>
          </div>

          <div className="lp-entry">
            {user && <MyLand user={user} onOpen={onStart} />}
            <Start onPick={onStart} onStory={onStory} />
            {/* G4 — đường vào RIÊNG cho người đang định MUA/THUÊ đất, không phải
                chủ thửa. Khung "thửa của bạn" ở trên sai ngữ cảnh cho họ — cần
                một cửa khác dẫn thẳng tới Sổ tay thửa (đã viết sẵn cho người mua). */}
            <Link href="/buyer" className="lp-buyer-cta">
              <House size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Định mua/thuê đất? Kiểm tra trước khi trả tiền",
                    "Planning to buy or rent land? Check before you pay")}
            </Link>
            {/* Ngân hàng / hợp tác xã / bảo hiểm: cả danh mục một lần, không mở từng thửa. */}
            <Link href="/batch" className="lp-buyer-cta">
              <ClipboardList size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Ngân hàng, hợp tác xã: thẩm định cả danh mục từ một tệp CSV",
                    "Banks & co-ops: appraise a whole portfolio from one CSV file")}
            </Link>
          </div>
        </section>

        {/* BỐN TRỤ CỘT THẨM ĐỊNH — ngay sau hero: đây là câu chuyện chính */}
        <section className="lp-why">
          <h2 className="lp-sec-h">
            {t("Không chỉ cảnh báo: giấy tờ đất có kiểm chứng", "Not just alerts: land paperwork you can verify")}
          </h2>
          <div className="lp-feats">
            {FEATURES.map((f) => (
              <div className="lp-feat" key={f.tvi}>
                <span className="lp-feat-ic"><f.icon size={26} strokeWidth={1.7} aria-hidden="true" /></span>
                <b>{t(f.tvi, f.ten)}</b>
                <p>{t(f.bvi, f.ben)}</p>
              </div>
            ))}
          </div>
        </section>

        {/* SỔ ĐIỂM TỰ CHẤM */}
        <section className="lp-score">
          <Scorecard data={sc} />
        </section>

        {/* DẢI DỮ LIỆU THẬT */}
        <section className="lp-trust">
          <span className="lp-trust-cap">
            {t("Chạy trên dữ liệu THẬT, kiểm chứng được", "Runs on REAL, verifiable data")}
          </span>
          <div className="lp-sources">
            {["Open-Meteo", "ERA5", "GloFAS", "NASA POWER", "Sentinel-2", "OpenStreetMap"].map((s) => (
              <span key={s}>{s}</span>
            ))}
          </div>
          <p className="lp-honest">
            {t(
              "Mỗi kết luận gắn cờ 🛰️ đo được hay 🧪 ước lượng, kèm khoảng tin cậy. Chỗ nào chưa đủ dữ liệu thì nói thẳng — không bịa số.",
              "Every conclusion is flagged 🛰️ measured or 🧪 estimated, with a confidence range. Where data is insufficient, we say so plainly — no made-up numbers.",
            )}
          </p>
        </section>

        <footer className="lp-foot">
          ◵ TerraTwin · {nModules} {t("mũi nhọn · 12 ngành · dữ liệu thật, hiệu chuẩn từng thửa",
                                       "spearheads · 12 sectors · real data, calibrated per plot")}
          <div className="lp-foot-links">
            <Link href="/about">{t("Cách hoạt động", "How it works")}</Link>
            <span>·</span>
            <Link href="/pricing">{t("Bảng giá", "Pricing")}</Link>
            <span>·</span>
            <Link href="/help">{t("Trợ giúp", "Help")}</Link>
            <span>·</span>
            <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link>
            <span>·</span>
            <Link href="/terms">{t("Điều khoản", "Terms")}</Link>
            <span>·</span>
            <Link href="/status">{t("Trạng thái hệ thống", "System status")}</Link>
          </div>
        </footer>
      </div>
    </div>
  );
}
