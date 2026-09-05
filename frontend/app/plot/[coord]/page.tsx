"use client";

/**
 * SỔ TAY THỬA SỐNG (Land Passport) — trang công khai, chia sẻ được.
 *
 * Ý TƯỞNG ĐỘC QUYỀN. Biến rủi ro thành một CHỨNG THƯ ĐẤT: hồ sơ dữ liệu về một
 * thửa (địa hình tương đối + 10 năm hiểm hoạ đo từ ERA5 + độ tin cậy vùng), trình
 * bày như một tài liệu đáng tin có thể đưa ngân hàng (thẩm định vay), bảo hiểm
 * (bảo hiểm tham số), hay người mua (thẩm định trước khi mua đất). Không app nào
 * dựng được vì cần đúng lõi hiệu chuẩn từng thửa của TerraTwin.
 *
 * Công khai & ẩn danh: URL chỉ chứa TOẠ ĐỘ (dữ liệu về ĐẤT, không về người) — ai
 * có link đều xem được, không lộ chủ thửa.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getPassport, type Passport } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

const MONTH = (m: number | null) => (m ? `${m}` : "—");

export default function PlotPassportPage() {
  const params = useParams();
  const raw = Array.isArray(params.coord) ? params.coord[0] : (params.coord ?? "");
  const nums = decodeURIComponent(raw).match(/-?\d+(\.\d+)?/g) || [];
  const lat = parseFloat(nums[0] ?? "");
  const lon = parseFloat(nums[1] ?? "");
  const valid = Number.isFinite(lat) && Number.isFinite(lon);

  const { t } = useLang();
  const [pp, setPp] = useState<Passport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!valid) { setErr("Toạ độ không hợp lệ."); return; }
    let live = true;
    getPassport(lat, lon)
      .then((d) => live && setPp(d))
      .catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [lat, lon, valid]);

  function share() {
    const url = window.location.href;
    navigator.clipboard?.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {});
  }

  const hist = pp?.history ? Object.entries(pp.history) : [];
  const terr = pp?.terrain;

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions">
          <LangToggle />
          <button className="pp-share" onClick={share}>
            {copied ? t("✓ Đã sao chép", "✓ Copied") : t("🔗 Chia sẻ", "🔗 Share")}
          </button>
        </div>
      </header>

      <article className="doc-body pp">
        <div className="pp-badge">{t("SỔ TAY THỬA · Hồ sơ dữ liệu", "LAND PASSPORT · Data record")}</div>
        <h1>{t("Sổ tay thửa đất", "Land Passport")}</h1>
        {valid && (
          <p className="pp-coord">📍 {lat.toFixed(4)}, {lon.toFixed(4)}</p>
        )}

        {err && <p className="doc-note">{err}</p>}
        {!pp && !err && <p className="doc-note">{t("Đang dựng hồ sơ thửa…", "Building the plot record…")}</p>}

        {pp && pp.available === false && (
          <p className="doc-note">{pp.message || t("Chưa dựng được hồ sơ cho vị trí này.", "Couldn't build a record for this location.")}</p>
        )}

        {pp && pp.available !== false && (
          <>
            {pp.headline && <p className="doc-lede">{pp.headline}</p>}

            {/* ĐỊA HÌNH */}
            {terr && (
              <>
                <h2>{t("Địa hình", "Terrain")}</h2>
                <div className="pp-grid">
                  <div className="pp-cell"><b>{terr.elevation_m} m</b><span>{t("cao độ", "elevation")}</span></div>
                  <div className="pp-cell"><b>{terr.lower_than_pct}%</b><span>{t("thấp hơn xung quanh", "lower than surroundings")}</span></div>
                  <div className="pp-cell"><b>{terr.slope_deg ?? "—"}°</b><span>{t("độ dốc", "slope")}</span></div>
                </div>
                <p className="pp-mean">{terr.meaning}</p>
              </>
            )}

            {/* 10 NĂM HIỂM HOẠ */}
            {hist.length > 0 && (
              <>
                <h2>{t("10 năm hiểm hoạ (đo từ ERA5)", "10-year hazard record (from ERA5)")}</h2>
                <div className="tw">
                  <table className="pp-table">
                    <thead>
                      <tr>
                        <th>{t("Hiểm hoạ", "Hazard")}</th>
                        <th>{t("Số đợt", "Events")}</th>
                        <th>{t("Cao điểm", "Peak")}</th>
                        <th>{t("Gần nhất", "Latest")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hist.map(([k, h]) => (
                        <tr key={k}>
                          <td>{h.name || k}</td>
                          <td className="pp-num">{h.events}</td>
                          <td className="pp-num">{h.events ? t(`tháng ${MONTH(h.peak_month)}`, `mo. ${MONTH(h.peak_month)}`) : "—"}</td>
                          <td className="pp-num">{h.latest || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {/* VÌ SAO ĐÁNG TIN */}
            <h2>{t("Vì sao hồ sơ này đáng tin", "Why this record is credible")}</h2>
            <p>{pp.why_unique}</p>
            <p className="pp-cred">
              {t("Dữ liệu đo từ vệ tinh & khí hậu thật, hiệu chuẩn riêng cho chính điểm này. Kiểm chứng độ chính xác của mô hình tại ",
                 "Measured from real satellite & climate data, calibrated to this exact point. Verify the model's accuracy at ")}
              <Link href="/about">{t("trang giới thiệu", "the about page")}</Link>.
            </p>
            {pp.caveat && <p className="doc-note">⚠️ {pp.caveat}</p>}

            <div className="doc-cta">
              <Link href={`/?lat=${lat}&lon=${lon}`} className="doc-btn">
                {t("Phân tích rủi ro 7 ngày tới cho thửa này", "Analyze the next 7 days for this plot")}
              </Link>
            </div>
          </>
        )}

        <footer className="doc-foot">
          <Link href="/about">{t("Cách hoạt động", "How it works")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </article>
    </div>
  );
}
