"use client";

import type { Assessment } from "@/lib/api";

const RISK: Record<string, { label: string; color: string }> = {
  safe: { label: "AN TOÀN", color: "#2E9E67" },
  warning: { label: "CẢNH BÁO", color: "#B07A2E" },
  danger: { label: "NGUY HIỂM", color: "#C2412E" },
  unknown: { label: "CHƯA CÓ", color: "#7a8a82" },
};

const LABELS: Record<string, string> = {
  nang_suat_du_kien_t_ha: "Năng suất (tấn/ha)",
  so_ngay_toi_thu_hoach: "Ngày tới thu hoạch",
  tco2_per_ha: "CO₂ (tấn/ha)",
  gia_tri_usd_per_ha: "Giá trị ($/ha)",
  thiet_hai_pct: "Thiệt hại (%)",
  diem: "Điểm",
  cao_do_m: "Cao độ (m)",
  do_doc_deg: "Độ dốc (°)",
  dien_tich_thay_doi_m2: "Diện tích đổi (m²)",
  chi_so: "Chỉ số",
  nguong: "Ngưỡng",
  chi_tra_uoc_tinh_vnd: "Chi trả (đ)",
  buc_xa_kwh_m2_ngay: "Bức xạ (kWh/m²/ngày)",
  san_luong_kwh_kwp_nam: "Sản lượng (kWh/kWp/năm)",
};

function fmt(v: number): string {
  return Number.isInteger(v)
    ? v.toLocaleString("vi-VN")
    : v.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

export default function ResultsPanel({ a }: { a: Assessment }) {
  const r = RISK[a.risk_level] ?? RISK.unknown;
  const fc = a.forecast ?? [];
  const max = Math.max(...fc.map((f) => f.value), 1);
  const metrics = a.metrics ? Object.entries(a.metrics) : [];

  return (
    <div className="panel">
      <div className="badgerow">
        <span className="riskbadge" style={{ background: r.color }}>
          {r.label}
        </span>
        {a.is_real ? (
          <span className="databadge real">🛰️ Dữ liệu thật</span>
        ) : a.status === "need_data" ? (
          <span className="databadge need">⏳ Chờ dữ liệu</span>
        ) : a.status === "out_of_scope" ? (
          <span className="databadge need">🚫 Ngoài phạm vi</span>
        ) : (
          <span className="databadge model">🧪 Ước lượng vật lý</span>
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
          <div className="chart-title">Dự báo 7 ngày ({fc[0].unit})</div>
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
              <span className="mk">{LABELS[k] ?? k.replace(/_/g, " ")}</span>
              <span className="mv">{fmt(v as number)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="rec">
        <b>Khuyến nghị:</b> {a.recommendation}
      </div>
      <p className="detail">{a.detail}</p>
      {a.confidence != null && (
        <p className="conf">
          Độ tin cậy: <b>{(a.confidence * 100).toFixed(0)}%</b>
          {a.confidence_low != null && a.confidence_high != null && (
            <>
              {" "}
              (khoảng {(a.confidence_low * 100).toFixed(0)}–
              {(a.confidence_high * 100).toFixed(0)}%)
            </>
          )}
          {" · "}
          {a.is_real ? "dựa trên dữ liệu thật" : "ước lượng vật lý, chờ hiệu chỉnh"}
        </p>
      )}
      <p className="src">Nguồn: {a.data_sources.join(" · ")}</p>
    </div>
  );
}
