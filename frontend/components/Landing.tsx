"use client";

/**
 * TRANG ĐÓN (landing) — hiện khi CHƯA chọn thửa.
 *
 * Từ 3/10/2026 sản phẩm chính là HỒ SƠ VƯỜN CHUẨN EUDR: nhu cầu BẮT BUỘC có hạn
 * chót (EU áp dụng 30/12/2026), không phải "xem cho biết". 18 công cụ thẩm định /
 * theo dõi cũ vẫn còn nguyên nhưng xuống mục "tham khảo" bên dưới — cảnh báo thiên
 * tai chính thức thuộc Trung tâm Dự báo KTTV quốc gia, TerraTwin chỉ tham khảo.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BadgeCheck, ClipboardList, FileSignature, Footprints, House, ScanSearch, Settings, TreePine,
  type LucideIcon,
} from "lucide-react";

import Account from "./Account";
import MyLand from "./MyLand";
import Scorecard from "./Scorecard";
import Start from "./Start";
import { getScorecard, trackEvent, type AuthUser, type ModuleInfo, type Scorecard as SC } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";
import { DataSaverToggle } from "@/lib/net";

// Bốn trụ cột — mỗi câu ứng với một thứ đang chạy thật, không hứa.
const FEATURES: { icon: LucideIcon; tvi: string; ten: string; bvi: string; ben: string }[] = [
  {
    icon: Footprints,
    tvi: "Ranh vườn đúng chuẩn tệp EU",
    ten: "Plot boundaries in the EU file format",
    bvi: "Vẽ trên ảnh vệ tinh hoặc cầm điện thoại đi bộ quanh vườn. Kiểm đúng quy định EU: toạ độ ≥ 6 chữ số, thửa trên 4 ha phải là đa giác, không ranh hở, tự cắt hay có lỗ, hai hộ không khai chồng nhau — sửa trước khi nộp, không để lô hàng bị giữ ở cảng.",
    ben: "Draw on satellite imagery or walk the boundary with a phone. Checked against EU rules: ≥ 6-decimal coordinates, plots over 4 ha as polygons, no open, self-crossing or holed rings, no two producers declaring the same land — fixed before filing, not at the port.",
  },
  {
    icon: TreePine,
    tvi: "Sàng lọc phá rừng sau 31/12/2020",
    ten: "Deforestation screening after 31/12/2020",
    bvi: "Ba bản đồ rừng năm 2020 độc lập (ESA quang học, JAXA radar, Impact Observatory theo năm) bỏ phiếu, cộng ảnh Sentinel-2 cùng mùa trước và sau mốc. Ba mức Đạt / Cần xem lại / Rủi ro, kèm lý do, số điểm ảnh và ảnh vệ tinh để tự nhìn.",
    ben: "Three independent 2020 forest maps (ESA optical, JAXA radar, Impact Observatory yearly) vote, plus same-season Sentinel-2 images before and after the cutoff. Three levels — Passed / Review / Risk — with reasons, pixel counts and imagery to see for yourself.",
  },
  {
    icon: FileSignature,
    tvi: "Hồ sơ thuộc về nông hộ",
    ten: "A dossier the farmer owns",
    bvi: "Mỗi vườn một hồ sơ ký Ed25519 + mã QR, nối vào sổ đăng ký công khai móc xích. Nông hộ mang đi bán cho đại lý nào cũng được; doanh nghiệp, ngân hàng quét QR là tự kiểm bản gốc — không cần tài khoản, không cần tin TerraTwin.",
    ben: "Each plot gets an Ed25519-signed dossier with a QR code, chained into a public registry. The farmer can sell to any trader; exporters and banks scan the QR to verify the original — no account, no need to trust TerraTwin.",
  },
  {
    icon: BadgeCheck,
    tvi: "Tự kiểm định công khai",
    ten: "Publicly validated",
    bvi: "Quy tắc sàng lọc được đối chiếu độc lập với dữ liệu mất rừng Hansen trên 120 thửa Tây Nguyên, ngưỡng đặt trước khi chạy — kết quả công bố kể cả khi không đạt. Hồ sơ chỉ chứa số đo và số tính lại được, không chứa dự báo.",
    ben: "The screening rule is checked independently against Hansen forest-loss data on 120 Central Highlands plots, with the bar set before running — results are published even if they fail. Dossiers hold only measured and recomputable figures, no forecasts.",
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

  return (
    <div className="lp">
      <header className="lp-top">
        <div className="lp-brand">◵ TerraTwin</div>
        <div className="lp-top-actions">
          <LangToggle />
          <DataSaverToggle />
          <button className="lp-ws" onClick={onWorkspace}>
            <Settings size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Khu làm việc", "Workspace")}
          </button>
          <Account user={user} onAuth={onAuth} />
        </div>
      </header>

      <div className="lp-body">
        {/* HERO + lối vào EUDR */}
        <section className="lp-hero">
          <div className="lp-hero-txt">
            <span className="lp-eyebrow">
              {t("Sẵn sàng EUDR · Hồ sơ vườn có kiểm chứng · Bản sao số đất đai Việt Nam",
                 "EUDR-ready · Verifiable plot dossiers · Vietnam's land digital twin")}
            </span>
            <h1 className="lp-h1">
              {t("Chứng minh vườn không phá rừng ", "Prove your plot is deforestation-free ")}
              <span>{t("trước 30/12/2026", "before 30/12/2026")}</span>
            </h1>
            <p className="lp-lede">
              {t(
                "Từ 30/12/2026, mỗi lô cà phê, cao su, gỗ, ca cao bán vào EU phải kèm toạ độ từng thửa và bằng chứng không phá rừng sau 31/12/2020. TerraTwin giúp nông hộ, hợp tác xã và doanh nghiệp lấy ranh vườn đúng chuẩn tệp EU, sàng lọc phá rừng bằng dữ liệu vệ tinh công khai, và phát hành hồ sơ có chữ ký số mà ai cũng tự kiểm được.",
                "From 30/12/2026 every lot of coffee, rubber, wood or cocoa sold into the EU must carry each plot's coordinates and proof of no deforestation after 31/12/2020. TerraTwin helps farmers, co-ops and exporters capture boundaries in the EU file format, screen for deforestation with public satellite data, and issue digitally signed dossiers anyone can verify.",
              )}
            </p>
            <div className="lp-stats">
              <div><b>30/12/2026</b><span>{t("EUDR áp dụng (DN lớn, vừa)", "EUDR applies (large, medium)")}</span></div>
              <div><b>3</b><span>{t("bản đồ rừng 2020 độc lập", "independent 2020 forest maps")}</span></div>
              <div><b>Ed25519</b><span>{t("hồ sơ ký số, tự kiểm", "signed, self-verifiable")}</span></div>
              <div><b>{t("0đ", "$0")}</b><span>{t("cho nông hộ", "for farmers")}</span></div>
            </div>
          </div>

          <div className="lp-entry">
            <div className="eu-start">
              <h2>{t("Bắt đầu", "Get started")}</h2>
              <Link href="/eudr" className="eu-start-main">
                <Footprints size={18} strokeWidth={1.9} aria-hidden="true" className="ui-ic" />
                <span><b>{t("Lấy ranh và kiểm một vườn", "Map and check one plot")}</b>
                  <small>{t("Vẽ trên ảnh vệ tinh hoặc đi bộ quanh vườn bằng GPS — không cần tài khoản",
                            "Draw on imagery or walk it with GPS — no account needed")}</small></span>
              </Link>
              <Link href="/eudr?tab=lo" className="lp-buyer-cta">
                <ClipboardList size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" />{" "}
                {t("Doanh nghiệp, HTX: kiểm cả lô nhà cung cấp từ tệp GeoJSON, KML, Excel",
                   "Exporters & co-ops: check a whole supplier set from GeoJSON, KML, Excel")}
              </Link>
              <Link href="/eudr?tab=phuong-phap" className="lp-buyer-cta">
                <ScanSearch size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" />{" "}
                {t("Phương pháp và kết quả kiểm định độc lập", "Method and independent validation results")}
              </Link>
            </div>
          </div>
        </section>

        {/* BỐN TRỤ CỘT */}
        <section className="lp-why">
          <h2 className="lp-sec-h">
            {t("Không phải dự báo: bằng chứng ai cũng kiểm được", "Not forecasts: evidence anyone can check")}
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

        {/* CÔNG CỤ THẨM ĐỊNH & THEO DÕI THỬA — tham khảo */}
        <section className="lp-tools">
          <h2 className="lp-sec-h">{t("Công cụ thẩm định và theo dõi một thửa đất", "Tools to appraise and monitor a plot")}</h2>
          <p className="lp-tools-sub">{t(
            `${nModules} công cụ phân tích từ dữ liệu thật: loại đất, địa hình, mười năm hiểm hoạ, theo dõi thời tiết. Phần cảnh báo thiên tai chỉ để THAM KHẢO — cảnh báo chính thức do Trung tâm Dự báo Khí tượng Thủy văn quốc gia phát (nchmf.gov.vn).`,
            `${nModules} analysis tools on real data: land type, terrain, ten years of hazards, weather monitoring. Disaster alerts are for REFERENCE only — official warnings come from Vietnam's National Center for Hydro-Meteorological Forecasting (nchmf.gov.vn).`)}</p>
          <div className="lp-tools-grid">
            <div>
              {user && <MyLand user={user} onOpen={onStart} />}
              <Start onPick={onStart} onStory={onStory} />
            </div>
            <div className="lp-tools-links">
              <Link href="/buyer" className="lp-buyer-cta">
                <House size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Định mua/thuê đất? Kiểm tra trước khi trả tiền",
                      "Planning to buy or rent land? Check before you pay")}
              </Link>
              <Link href="/batch" className="lp-buyer-cta">
                <ClipboardList size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Ngân hàng: thẩm định cả danh mục thửa từ một tệp CSV",
                      "Banks: appraise a whole plot portfolio from one CSV file")}
              </Link>
            </div>
          </div>
        </section>

        {/* SỔ ĐIỂM TỰ CHẤM của phần cảnh báo */}
        <section className="lp-score">
          <Scorecard data={sc} />
        </section>

        {/* DẢI DỮ LIỆU THẬT */}
        <section className="lp-trust">
          <span className="lp-trust-cap">
            {t("Chạy trên dữ liệu công khai, ai cũng tự tính lại được", "Runs on public data anyone can recompute")}
          </span>
          <div className="lp-sources">
            {["ESA WorldCover", "JAXA ALOS PALSAR", "Impact Observatory", "Sentinel-2", "ERA5", "GloFAS", "OpenStreetMap"].map((s) => (
              <span key={s}>{s}</span>
            ))}
          </div>
          <p className="lp-honest">
            {t(
              "Mỗi con số gắn nhãn ĐO, TÍNH LẠI ĐƯỢC hoặc DỰ ĐOÁN. Chỉ hai loại đầu được đưa vào hồ sơ ký số dùng để mua bán, vay vốn. Chỗ nào chưa đủ dữ liệu thì nói thẳng — không bịa số.",
              "Every figure is labelled MEASURED, RECOMPUTABLE or PREDICTED. Only the first two go into signed dossiers used for trade or credit. Where data is insufficient, we say so plainly — no made-up numbers.",
            )}
          </p>
        </section>

        <footer className="lp-foot">
          ◵ TerraTwin · {t("Hồ sơ vườn chuẩn EUDR · dữ liệu vệ tinh công khai, ai cũng tự kiểm được",
                           "EUDR-ready plot dossiers · public satellite data, verifiable by anyone")}
          <div className="lp-foot-links">
            <Link href="/eudr?tab=phuong-phap">{t("Phương pháp EUDR", "EUDR method")}</Link>
            <span>·</span>
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
