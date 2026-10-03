"use client";

/**
 * Phần nội dung của HỒ SƠ VƯỜN CHUẨN EUDR trên trang /h/<mã> — đóng băng lúc
 * phát hành. Ranh thửa vẽ bằng SVG ngay trên giấy (in ra vẫn thấy), kèm toạ độ
 * đúng như tệp nộp EU, kết quả chuẩn tệp, sàng lọc, nhãn đo / tính lại được.
 */

import EudrResult, { IssueList } from "@/components/EudrResult";
import type { EudrDossierFacts, GeoGeometry } from "@/lib/api";
import { useLang } from "@/lib/i18n";

function Outline({ g }: { g: GeoGeometry }) {
  const polys: number[][][][] = g.type === "Polygon" ? [g.coordinates as number[][][]]
    : g.type === "MultiPolygon" ? (g.coordinates as number[][][][]) : [];
  if (!polys.length) return null;
  const all = polys.flatMap((p) => p[0]);
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  const lat = (Math.min(...ys) + Math.max(...ys)) / 2;
  const kx = Math.cos((lat * Math.PI) / 180);
  const w = (Math.max(...xs) - Math.min(...xs)) * kx || 1e-6, h = Math.max(...ys) - Math.min(...ys) || 1e-6;
  const S = 200, pad = 12, sc = (S - 2 * pad) / Math.max(w, h);
  const pt = (p: number[]) => `${(pad + (p[0] - Math.min(...xs)) * kx * sc).toFixed(1)},${(pad + (Math.max(...ys) - p[1]) * sc).toFixed(1)}`;
  return (
    <svg className="eu-outline" viewBox={`0 0 ${S} ${S}`} role="img" aria-label="outline">
      {polys.map((p, i) => <path key={i} d={"M" + p[0].map(pt).join(" L") + " Z"} />)}
    </svg>
  );
}

export default function EudrDossierView({ f, revealed }: { f: EudrDossierFacts; revealed?: Record<string, { value: string; ok: boolean }> }) {
  const { t } = useLang();
  const p = f.plot;
  const cls = f.evidence_classes ?? {};
  const tag = (k: string) => cls[k] === "measured" ? t("ĐO", "MEASURED") : cls[k] === "derived" ? t("TÍNH LẠI ĐƯỢC", "RECOMPUTABLE") : "";
  const coords = p.geometry.type === "Polygon" ? (p.geometry.coordinates as number[][][])[0]
    : p.geometry.type === "Point" ? [p.geometry.coordinates as number[]] : [];
  return (
    <>
      <div className="dos-grid">
        <section>
          <h2>{t("Ranh vườn", "Plot boundary")} <span className="eu-class">{tag("plot.geometry")}</span></h2>
          <div className="eu-plotbox">
            {p.kind === "polygon" && <Outline g={p.geometry} />}
            <ul className="dos-list">
              <li><span>{t("Chủ hộ", "Producer")}</span><b>{p.producer ?? (revealed?.producer
                ? (revealed.producer.ok ? <>{revealed.producer.value} <span className="eu-proved">✓ {t("đã chứng minh", "proven")}</span></>
                  : <span className="eu-err-txt">{t("tên đưa kèm KHÔNG khớp cam kết đã ký", "the supplied name does NOT match the signed commitment")}</span>)
                : f.disclosure?.fields?.producer ? <span className="eu-hidden">{t("ẩn — chủ hồ sơ giữ đường link đầy đủ", "hidden — the owner holds the full link")}</span> : "—")}</b></li>
              <li><span>{t("Nông sản", "Commodity")}</span><b>{p.commodity_label ?? "—"}</b></li>
              <li><span>{t("Diện tích", "Area")}</span><b>{p.area_ha} ha</b></li>
              <li><span>{t("Kiểu khai", "Declared as")}</span><b>{p.kind === "polygon" ? t(`Đa giác ${p.n_vertices} đỉnh`, `Polygon, ${p.n_vertices} vertices`) : t("Điểm", "Point")}</b></li>
              <li><span>{t("Tâm thửa", "Centre")}</span><b>{p.centroid.lat.toFixed(6)}, {p.centroid.lon.toFixed(6)}</b></li>
              <li><span>{t("Quốc gia", "Country")}</span><b>{p.country}</b></li>
            </ul>
          </div>
          <p className="dos-src">{t("Ranh do người khai đo (vẽ trên ảnh vệ tinh, đi bộ GPS hoặc tệp). TerraTwin không xác nhận quyền sử dụng đất.",
                                    "Boundary measured by the declarant (drawn on imagery, GPS walk or file). TerraTwin does not confirm land rights.")}</p>
        </section>
        <section>
          <h2>{t("Chuẩn tệp GeoJSON của EU", "EU GeoJSON file rules")} <span className="eu-class">{tag("eu_format")}</span></h2>
          <p className={`dos-score ${f.eu_format.valid ? "" : "dos-flag"}`}><b>{f.eu_format.valid ? t("Đạt — nộp được vào hệ thống EU", "Pass — can be filed in the EU system") : t("Không đạt", "Fail")}</b></p>
          <IssueList issues={f.eu_format.issues} />
          <p className="dos-src">{f.eu_format.rules}</p>
        </section>
      </div>

      {f.land_document && (
        <section>
          <h2>{t("Giấy chứng nhận quyền sử dụng đất", "Land-use right certificate")} <span className="eu-class">{t("NGƯỜI KHAI CUNG CẤP", "DECLARED")}</span></h2>
          <p className={`dos-score ${f.land_document.verdict === "ok" ? "" : "dos-flag"}`}><b>{f.land_document.label}</b></p>
          <ul className="dos-list">
            {f.land_document.fields.so_thua && <li><span>{t("Thửa số · tờ bản đồ", "Parcel · map sheet")}</span><b>{f.land_document.fields.so_thua} · {f.land_document.fields.to_ban_do ?? "—"}</b></li>}
            {f.land_document.fields.dien_tich_m2 != null && <li><span>{t("Diện tích trên sổ", "Certificate area")}</span><b>{Number(f.land_document.fields.dien_tich_m2).toLocaleString("vi-VN")} m²</b></li>}
            {f.land_document.fields.ma_muc_dich && <li><span>{t("Mục đích", "Land use")}</span><b>{f.land_document.fields.muc_dich ?? ""} ({f.land_document.fields.ma_muc_dich})</b></li>}
            {f.land_document.fields.thoi_han && <li><span>{t("Thời hạn", "Term")}</span><b>{f.land_document.fields.thoi_han}</b></li>}
            {f.disclosure?.fields?.land_owner && <li><span>{t("Tên chủ trên sổ", "Certificate holder")}</span><b>{revealed?.land_owner
              ? (revealed.land_owner.ok ? <>{revealed.land_owner.value} <span className="eu-proved">✓</span></> : <span className="eu-err-txt">✗</span>)
              : <span className="eu-hidden">{t("ẩn", "hidden")}</span>}</b></li>}
          </ul>
          <ul className="eu-checks">
            {f.land_document.checks.map((c) => <li key={c.id} className={c.ok === true ? "ok" : c.ok === false ? "bad" : "unk"}>{c.ok === true ? "✓" : c.ok === false ? "✗" : "?"} {c.label}</li>)}
          </ul>
          <p className="dos-src">{t("Đọc bằng", "Read by")} {f.land_document.source === "manual" ? t("nhập tay", "manual entry") : f.land_document.source}
            {f.land_document.image_sha256 ? <> · SHA-256 {t("ảnh sổ", "of certificate photo")} <code>{f.land_document.image_sha256.slice(0, 16)}…</code> ({t("ảnh không lưu", "photo not stored")})</> : null}.{" "}
            {t("TerraTwin đối chiếu, KHÔNG xác minh với văn phòng đăng ký đất đai.", "TerraTwin cross-checks; it does NOT verify with the land registry.")}</p>
        </section>
      )}

      <section>
        <h2>{t("Sàng lọc phá rừng sau 31/12/2020", "Deforestation screening after 31/12/2020")} <span className="eu-class">{tag("screening.forest_2020")} + {tag("screening.level")}</span></h2>
        <EudrResult s={f.screening} geometry={p.geometry} areaHa={p.area_ha} />
      </section>

      <section>
        <h2>{t("Toạ độ đúng như tệp nộp EU", "Coordinates exactly as in the EU file")}</h2>
        <details className="eu-coords">
          <summary>{t(`${coords.length} điểm (kinh độ, vĩ độ — WGS84, 6 chữ số)`, `${coords.length} points (longitude, latitude — WGS84, 6 decimals)`)}</summary>
          <code>{coords.map((c) => `${c[0].toFixed(6)}, ${c[1].toFixed(6)}`).join("\n")}</code>
        </details>
      </section>

      <section>
        <h2>{t("Tự tính lại không cần tin TerraTwin", "Recompute without trusting TerraTwin")}</h2>
        <p className="dos-note">{f.reproduce}</p>
        <p className="dos-src">{t("Hồ sơ này KHÔNG chứa dự báo nào — chỉ số đo và số tính lại được từ số đo.",
                                  "This dossier contains NO forecasts — only measured figures and figures recomputable from them.")}</p>
      </section>
    </>
  );
}
