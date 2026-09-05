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

import Account from "./Account";
import MyLand from "./MyLand";
import Scorecard from "./Scorecard";
import Start from "./Start";
import { getScorecard, type AuthUser, type ModuleInfo, type Scorecard as SC } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

const FEATURES = [
  {
    icon: "🎯",
    tvi: "Hiệu chuẩn tới TỪNG THỬA",
    ten: "Calibrated to EACH PLOT",
    bvi: "Ngưỡng cảnh báo so với khí hậu 10 năm của chính điểm đó — báo động giả tụt từ 46–61% xuống ~3%. Không ai làm được điều này bằng một ngưỡng chung cho cả nước.",
    ben: "Alert thresholds are set against that exact point's 10-year climatology — false alarms drop from 46–61% to ~3%. No one does this with a single nationwide threshold.",
  },
  {
    icon: "🔬",
    tvi: "Báo trước CÓ BẰNG CHỨNG",
    ten: "Early warning WITH EVIDENCE",
    bvi: "Kiểm chứng trên thiên tai thật (lũ Huế 2020, sạt lở Trà Leng…): báo trước mấy ngày, kèm tỉ lệ báo bừa — không phải lời hứa suông.",
    ben: "Backtested on real disasters (Huế 2020 flood, Trà Leng landslide…): days of lead time, with the false-alarm rate shown — not empty promises.",
  },
  {
    icon: "🛰️",
    tvi: "Ảnh vệ tinh THẬT",
    ten: "REAL satellite imagery",
    bvi: "Nhìn thấy chính mảnh đất của bạn từ Sentinel-2 (Microsoft Planetary Computer) — không cần đăng ký khoá nào.",
    ben: "See your actual plot from Sentinel-2 (Microsoft Planetary Computer) — no API key required.",
  },
  {
    icon: "🛡️",
    tvi: "Tự canh đất cho bạn",
    ten: "Guards your land for you",
    bvi: "Lưu thửa → TerraTwin tự quét nền và báo TRƯỚC khi có rủi ro, qua Zalo/email — bạn không cần nhớ mở.",
    ben: "Save a plot → TerraTwin scans in the background and warns you BEFORE risk hits, via Zalo/email — no need to remember to check.",
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
  const { t } = useLang();
  const nModules = modules.length || 18;

  const [sc, setSc] = useState<SC | null>(null);
  useEffect(() => {
    let live = true;
    getScorecard(90).then((r) => live && setSc(r)).catch(() => {});
    return () => { live = false; };
  }, []);
  const doThat = sc?.enough && sc.far_pct !== null;

  return (
    <div className="lp">
      <header className="lp-top">
        <div className="lp-brand">◵ TerraTwin</div>
        <div className="lp-top-actions">
          <LangToggle />
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
              {t("Bản sao số của đất đai Việt Nam", "The digital twin of Vietnam's land")}
            </span>
            <h1 className="lp-h1">
              {t("Biết trước điều gì sắp xảy ra với ", "Know what's about to happen to ")}
              <span>{t("mảnh đất của bạn", "your land")}</span>
            </h1>
            <p className="lp-lede">
              {t(
                "Chọn đúng thửa của bạn — TerraTwin kiểm toàn bộ rủi ro 7 ngày tới bằng dữ liệu vệ tinh & khí hậu thật, hiệu chuẩn riêng cho chính chỗ đó, rồi cho biết nên làm gì.",
                "Pick your exact plot — TerraTwin checks every risk over the next 7 days using real satellite & climate data, calibrated to that spot, then tells you what to do.",
              )}
            </p>
            <div className="lp-stats">
              <div><b>{nModules}</b><span>{t("mũi nhọn", "spearheads")}</span></div>
              <div><b>12/12</b><span>{t("ngành", "sectors")}</span></div>
              <div title={doThat
                ? t("Đo trên chính những cảnh báo TerraTwin đã phát trong 90 ngày qua.",
                     "Measured on TerraTwin's own alerts over the last 90 days.")
                : t("Đo trên backtest các thiên tai lịch sử.",
                     "Measured on backtests of historical disasters.")}>
                <b>{doThat ? `${sc!.far_pct}%` : "~3%"}</b>
                <span>{doThat ? t("báo bừa · đo thật", "false alarms · measured")
                              : t("báo bừa · backtest", "false alarms · backtest")}</span>
              </div>
              <div><b>0đ</b><span>{t("miễn phí dùng thử", "free to try")}</span></div>
            </div>
          </div>

          <div className="lp-entry">
            {user && <MyLand user={user} onOpen={onStart} />}
            <Start onPick={onStart} onStory={onStory} />
          </div>
        </section>

        {/* SỔ ĐIỂM TỰ CHẤM */}
        <section className="lp-score">
          <Scorecard data={sc} />
        </section>

        {/* VÌ SAO KHÁC BIỆT */}
        <section className="lp-why">
          <h2 className="lp-sec-h">
            {t("Vì sao TerraTwin, không phải app thời tiết", "Why TerraTwin, not a weather app")}
          </h2>
          <div className="lp-feats">
            {FEATURES.map((f) => (
              <div className="lp-feat" key={f.icon}>
                <span className="lp-feat-ic">{f.icon}</span>
                <b>{t(f.tvi, f.ten)}</b>
                <p>{t(f.bvi, f.ben)}</p>
              </div>
            ))}
          </div>
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
          </div>
        </footer>
      </div>
    </div>
  );
}
