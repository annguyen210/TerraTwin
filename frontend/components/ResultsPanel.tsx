"use client";

import type { Assessment } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const RISK: Record<string, { label: string; en: string; color: string }> = {
  safe: { label: "AN TOÀN", en: "SAFE", color: "#2E9E67" },
  warning: { label: "CẢNH BÁO", en: "WARNING", color: "#B07A2E" },
  danger: { label: "NGUY HIỂM", en: "DANGER", color: "#C2412E" },
  unknown: { label: "CHƯA CÓ", en: "NO DATA", color: "#7a8a82" },
};

const LABELS: Record<string, [string, string]> = {
  nang_suat_du_kien_t_ha: ["Năng suất (tấn/ha)", "Yield (t/ha)"],
  so_ngay_toi_thu_hoach: ["Ngày tới thu hoạch", "Days to harvest"],
  tco2_per_ha: ["CO₂ (tấn/ha)", "CO₂ (t/ha)"],
  gia_tri_usd_per_ha: ["Giá trị ($/ha)", "Value ($/ha)"],
  thiet_hai_pct: ["Thiệt hại (%)", "Damage (%)"],
  diem: ["Điểm", "Score"],
  cao_do_m: ["Cao độ (m)", "Elevation (m)"],
  do_doc_deg: ["Độ dốc (°)", "Slope (°)"],
  dien_tich_thay_doi_m2: ["Diện tích đổi (m²)", "Area changed (m²)"],
  chi_so: ["Chỉ số", "Index"],
  nguong: ["Ngưỡng", "Threshold"],
  chi_tra_uoc_tinh_vnd: ["Chi trả (đ)", "Payout (₫)"],
  buc_xa_kwh_m2_ngay: ["Bức xạ (kWh/m²/ngày)", "Irradiance (kWh/m²/day)"],
  san_luong_kwh_kwp_nam: ["Sản lượng (kWh/kWp/năm)", "Output (kWh/kWp/yr)"],
  vuot_nguong: ["Vượt ngưỡng", "Over threshold"],
  // pest
  ndvi_hien_tai: ["NDVI hiện tại", "Current NDVI"],
  ndvi_nen: ["NDVI nền", "Baseline NDVI"],
  thay_doi_pct: ["Thay đổi (%)", "Change (%)"],
  z_score: ["Z-score", "Z-score"],
  do_loang_lo: ["Độ loang lổ", "Patchiness"],
  // yield
  ndvi_dinh: ["NDVI đỉnh", "Peak NDVI"],
  ngay_qua_dinh: ["Ngày qua đỉnh", "Days past peak"],
  tich_phan_ndvi: ["Tích phân NDVI", "NDVI integral"],
  suc_song_so_dinh_pct: ["Sức sống so đỉnh (%)", "Vigor vs peak (%)"],
  // carbon
  che_phu_tan_pct: ["Che phủ tán (%)", "Canopy cover (%)"],
  dien_tich_rung_ha: ["Diện tích rừng (ha)", "Forest area (ha)"],
  tru_luong_tco2: ["Trữ lượng (tCO₂)", "Stock (tCO₂)"],
  sai_so_pct: ["Sai số (%)", "Uncertainty (%)"],
  // aquaculture
  nhiet_mat_nuoc_max_c: ["Nhiệt mặt nước đỉnh (°C)", "Peak sea-surface temp (°C)"],
  song_cao_max_m: ["Sóng cao đỉnh (m)", "Peak wave height (m)"],
  // storm damage / illegal build
  ndvi_truoc: ["NDVI trước", "NDVI before"],
  ndvi_sau: ["NDVI sau", "NDVI after"],
  thay_doi: ["Thay đổi", "Change"],
  ndbi_thay_doi: ["NDBI thay đổi", "NDBI change"],
  ndvi_thay_doi: ["NDVI thay đổi", "NDVI change"],
  // flood
  luu_luong_hien_tai_m3s: ["Lưu lượng sông hiện tại (m³/s)", "River discharge now (m³/s)"],
  luu_luong_dinh_m3s: ["Lưu lượng sông đỉnh (m³/s)", "Peak river discharge (m³/s)"],
  luu_luong_tb_m3s: ["Lưu lượng sông TB (m³/s)", "Mean river discharge (m³/s)"],
  ty_so_so_binh_thuong: ["Tỉ số so bình thường", "Ratio vs normal"],
  // land risk
  mua_7ngay_mm: ["Mưa 7 ngày (mm)", "7-day rain (mm)"],
  // upstream flood
  mua_thuong_nguon_mm: ["Mưa thượng nguồn (mm)", "Upstream rain (mm)"],
  mua_tai_cho_mm: ["Mưa tại chỗ (mm)", "Local rain (mm)"],
  lech_mm: ["Lệch (mm)", "Difference (mm)"],
  diem_cao_hon: ["Điểm cao hơn", "Higher points"],
  chenh_cao_m: ["Chênh cao (m)", "Relief (m)"],
  // urban
  be_tong_hoa_pct: ["Bê tông hoá (%)", "Built-up (%)"],
  cong_trinh: ["Công trình", "Buildings"],
  mat_do_duong_km_km2: ["Mật độ đường (km/km²)", "Road density (km/km²)"],
  mang_xanh_pct: ["Mảng xanh (%)", "Green space (%)"],
  chay_tran_mm: ["Chảy tràn (mm)", "Runoff (mm)"],
  chay_tran_tu_nhien_mm: ["Chảy tràn tự nhiên (mm)", "Natural runoff (mm)"],
  // mining
  so_khu_khai_thac_15km: ["Khu khai thác trong 15km", "Mining sites within 15km"],
  khu_gan_nhat_km: ["Khu gần nhất (km)", "Nearest site (km)"],
  thay_doi_tham_thuc_vat: ["Thay đổi thảm thực vật", "Vegetation change"],
  // supply chain
  diem_kiem_tra: ["Điểm kiểm tra", "Points checked"],
  ban_kinh_km: ["Bán kính (km)", "Radius (km)"],
  ty_le_rui_ro_pct: ["Tỉ lệ rủi ro (%)", "At-risk share (%)"],
  diem_canh_bao_lu: ["Điểm cảnh báo lũ", "Flood-alert points"],
  diem_canh_bao_han: ["Điểm cảnh báo hạn", "Drought-alert points"],
  duong_truc_gan_nhat_km: ["Đường trục gần nhất (km)", "Nearest trunk road (km)"],
};

function fmt(v: number): string {
  return Number.isInteger(v)
    ? v.toLocaleString("vi-VN")
    : v.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

export default function ResultsPanel({ a }: { a: Assessment }) {
  const { t } = useLang();
  const r = RISK[a.risk_level] ?? RISK.unknown;
  const fc = a.forecast ?? [];
  const max = Math.max(...fc.map((f) => f.value), 1);
  const metrics = a.metrics ? Object.entries(a.metrics) : [];

  return (
    <div className="panel">
      <div className="badgerow">
        <span className="riskbadge" style={{ background: r.color }}>
          {t(r.label, r.en)}
        </span>
        {a.is_real ? (
          <span className="databadge real">🛰️ {t("Dữ liệu thật", "Real data")}</span>
        ) : a.status === "need_data" ? (
          <span className="databadge need">⏳ {t("Chờ dữ liệu", "Awaiting data")}</span>
        ) : a.status === "out_of_scope" ? (
          <span className="databadge need">🚫 {t("Ngoài phạm vi", "Out of scope")}</span>
        ) : (
          <span className="databadge model">🧪 {t("Ước lượng vật lý", "Physical estimate")}</span>
        )}
      </div>
      <h2>{a.module_name}</h2>
      <p className="headline">{a.headline}</p>

      {a.score != null && (
        <div className="bigscore" style={{ color: r.color }}>
          {a.score}
          <span>/100</span>
        </div>
      )}

      {fc.length > 0 && (
        <>
          <div className="chart-title">{t("Dự báo 7 ngày", "7-day forecast")} ({fc[0].unit})</div>
          <div className="chart">
            {fc.map((f) => (
              <div
                className="bar-wrap"
                key={f.day}
                title={`${f.date}: ${f.value} ${f.unit}`}
              >
                <div
                  className="bar"
                  style={{
                    height: `${(f.value / max) * 100}%`,
                    background: (RISK[f.risk] ?? RISK.unknown).color,
                  }}
                />
                <span className="bar-label">{f.date.slice(5)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {metrics.length > 0 && (
        <div className="metrics">
          {metrics.map(([k, v]) => (
            <div className="metric" key={k}>
              <span className="mk">{LABELS[k] ? t(LABELS[k][0], LABELS[k][1]) : k.replace(/_/g, " ")}</span>
              <span className="mv">{fmt(v as number)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="rec">
        <b>{t("Khuyến nghị:", "Recommendation:")}</b> {a.recommendation}
      </div>
      <p className="detail">{a.detail}</p>
      {a.confidence != null && (
        <p className="conf">
          {t("Độ tin cậy:", "Confidence:")} <b>{(a.confidence * 100).toFixed(0)}%</b>
          {a.confidence_low != null && a.confidence_high != null && (
            <>
              {" "}
              ({t("khoảng", "range")} {(a.confidence_low * 100).toFixed(0)}–
              {(a.confidence_high * 100).toFixed(0)}%)
            </>
          )}
          {" · "}
          {a.is_real ? t("dựa trên dữ liệu thật", "based on real data")
                     : t("ước lượng vật lý, chờ hiệu chỉnh", "physical estimate, pending calibration")}
        </p>
      )}
      <p className="src">{t("Nguồn:", "Source:")} {a.data_sources.join(" · ")}</p>
    </div>
  );
}
