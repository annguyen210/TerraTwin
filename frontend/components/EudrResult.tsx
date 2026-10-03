"use client";

/**
 * KẾT QUẢ SÀNG LỌC PHÁ RỪNG EUDR của một thửa — dùng chung cho trang /eudr (kết
 * quả sống) và trang hồ sơ /h/<mã> (kết quả đóng băng lúc phát hành).
 *
 * Hiện ĐỦ để người đọc tự kiểm: ba bản đồ rừng 2020 (tỉ lệ + số điểm ảnh), quỹ
 * đạo tán cây từng năm, ảnh Sentinel-2 cùng mùa trước/sau mốc có vẽ ranh thửa,
 * khu bảo tồn, và các giới hạn — không chỉ một nhãn "đạt / không đạt".
 */

import { BadgeCheck, CircleHelp, ShieldAlert, TriangleAlert } from "lucide-react";
import type { EudrIssue, EudrLevel, EudrS2, EudrScreening, GeoGeometry } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const LEVEL_ICON = { low: BadgeCheck, review: TriangleAlert, high: ShieldAlert, unknown: CircleHelp };

export function LevelBadge({ level, label }: { level: EudrLevel; label: string }) {
  const Ic = LEVEL_ICON[level] ?? CircleHelp;
  return (
    <span className={`eu-badge eu-${level}`}>
      <Ic size={15} strokeWidth={2} aria-hidden="true" /> {label}
    </span>
  );
}

export function IssueList({ issues }: { issues: EudrIssue[] }) {
  const { t } = useLang();
  if (!issues.length) return <p className="eu-ok-line">{t("Không có lỗi nào theo chuẩn tệp GeoJSON của EU.", "No issues under the EU GeoJSON rules.")}</p>;
  const tag = { error: t("Lỗi EU từ chối", "EU rejects"), warning: t("Nên xem lại", "Review"), fixed: t("Đã tự sửa", "Auto-fixed") };
  return (
    <ul className="eu-issues">
      {issues.map((i, k) => (
        <li key={`${i.code}-${k}`} className={`eu-issue ${i.level}`}>
          <span className="eu-issue-tag">{tag[i.level]}</span> {i.message}
        </li>
      ))}
    </ul>
  );
}

/** Đa giác (lon/lat) → đường SVG trên khung ảnh bbox [x0,y0,x1,y1] cỡ size×size. */
function svgPaths(g: GeoGeometry | null | undefined, bbox: number[], size: number): string[] {
  if (!g) return [];
  const [x0, y0, x1, y1] = bbox;
  const px = (p: number[]) => `${(((p[0] - x0) / (x1 - x0)) * size).toFixed(1)},${(((y1 - p[1]) / (y1 - y0)) * size).toFixed(1)}`;
  const polys: number[][][][] = g.type === "Polygon" ? [g.coordinates as number[][][]]
    : g.type === "MultiPolygon" ? (g.coordinates as number[][][][]) : [];
  return polys.map((rings) => "M" + rings[0].map(px).join(" L") + " Z");
}

function PlotImage({ s2, geometry, areaHa, caption }: {
  s2: EudrS2; geometry?: GeoGeometry | null; areaHa?: number | null; caption: string;
}) {
  const { t } = useLang();
  if (!s2) {
    return <figure className="eu-img eu-img-miss"><div>{t("Không có ảnh quang mây cùng mùa", "No cloud-free same-season image")}</div>
      <figcaption>{caption}</figcaption></figure>;
  }
  const S = 512;
  const paths = svgPaths(geometry, s2.image.bbox, S);
  let circle: { cx: number; cy: number; r: number } | null = null;
  if (geometry && (geometry.type === "Point")) {
    const [lon, lat] = geometry.coordinates as number[];
    const [x0, y0, x1, y1] = s2.image.bbox;
    const mPerPx = ((y1 - y0) * 111320) / S;
    circle = { cx: ((lon - x0) / (x1 - x0)) * S, cy: ((y1 - lat) / (y1 - y0)) * S,
               r: Math.sqrt(((areaHa ?? 4) * 10000) / Math.PI) / mPerPx };
  }
  return (
    <figure className="eu-img">
      <div className="eu-img-box">
        <img src={s2.image.url} alt={`Sentinel-2 ${s2.date}`} width={S} height={S} />
        <svg viewBox={`0 0 ${S} ${S}`} aria-hidden="true">
          {paths.map((d, i) => <path key={i} d={d} />)}
          {circle && <circle cx={circle.cx} cy={circle.cy} r={circle.r} />}
        </svg>
      </div>
      <figcaption>
        <b>{caption}</b> · {s2.date.split("-").reverse().join("/")} · NDVI {s2.ndvi_mean.toFixed(2)} ·{" "}
        {t("quang mây", "cloud-free")} {s2.clear_pct.toFixed(0)}%
        <small title={s2.item}>{s2.item.slice(0, 38)}…</small>
      </figcaption>
    </figure>
  );
}

export default function EudrResult({ s, geometry, areaHa }: {
  s: EudrScreening; geometry?: GeoGeometry | null; areaHa?: number | null;
}) {
  const { t } = useLang();
  const pct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(0)}%`);
  const traj = s.io_trajectory ?? [];
  const sig = s.signals ?? {};
  const votes = new Set(sig.votes ?? []);
  return (
    <div className="eu-result">
      <div className="eu-verdict">
        <LevelBadge level={s.level} label={s.label} />
        <span className="eu-verdict-sub">{t("Mốc EUDR", "EUDR cutoff")} 31/12/2020 · {t("quy tắc", "rule")} <code>{s.method}</code></span>
      </div>
      <ul className="eu-reasons">{s.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>

      <h4>{t("Ba bản đồ rừng quanh năm 2020 (độc lập nhau)", "Three independent forest maps around 2020")}</h4>
      <div className="bat-table-wrap">
        <table className="bat-table eu-maps">
          <thead><tr>
            <th>{t("Bản đồ", "Map")}</th><th>{t("Rừng / tán cây trong ranh", "Forest / tree cover in boundary")}</th>
            <th>{t("Điểm ảnh", "Pixels")}</th><th>{t("Phiếu", "Vote")}</th>
          </tr></thead>
          <tbody>
            {s.forest_2020.map((m) => (
              <tr key={m.id}>
                <td>{m.name}{m.buffered_m ? <small>{t(`đo trên ranh nới rộng ${m.buffered_m} m`, `measured on boundary widened by ${m.buffered_m} m`)}</small> : null}</td>
                <td className="num"><b>{pct(m.pct)}</b>
                  <span className="eu-mini"><span style={{ width: `${Math.min(100, m.pct ?? 0)}%` }} /></span></td>
                <td className="num">{m.pixels ?? "—"} × {m.res_m} m</td>
                <td>{m.pct == null ? t("thiếu", "missing") : votes.has(m.id) ? t("có rừng", "forest") : t("không", "no")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {traj.length > 0 && (
        <>
          <h4>{t("Tán cây từng năm (Impact Observatory)", "Tree cover by year (Impact Observatory)")}</h4>
          <div className="eu-traj" role="img" aria-label={t("Biểu đồ tán cây theo năm", "Tree cover by year chart")}>
            {traj.map((r) => (
              <div key={r.year} className={r.year <= 2020 ? "pre" : "post"}>
                <span className="eu-traj-bar"><span style={{ height: `${r.tree_pct ?? 0}%` }} /></span>
                <b>{pct(r.tree_pct)}</b><small>{r.year}</small>
              </div>
            ))}
          </div>
          <p className="eu-src">{t("TB 2018–2020", "Avg 2018–2020")} {pct(sig.io_before_pct)} → {t("TB 2022–2023", "avg 2022–2023")} {pct(sig.io_after_pct)}.{" "}
            {t("Bản đồ này hay nhảy qua lại giữa các năm ở rừng thưa, nên so trung bình nhiều năm, không so từng năm.",
               "This map flips between years in open forest, so multi-year averages are compared, not single years.")}</p>
        </>
      )}

      <h4>{t("Ảnh Sentinel-2 cùng mùa (tháng 11 – tháng 2), viền vàng là ranh thửa", "Same-season Sentinel-2 images (Nov–Feb); yellow outline is the plot")}</h4>
      <div className="eu-imgs">
        <PlotImage s2={s.s2?.before} geometry={geometry} areaHa={areaHa} caption={t("Quanh mốc 31/12/2020", "Around 31/12/2020")} />
        <PlotImage s2={s.s2?.after} geometry={geometry} areaHa={areaHa} caption={t("Mùa gần nhất", "Latest season")} />
      </div>

      <p className="eu-src">
        <b>{t("Khu bảo tồn", "Protected areas")}:</b>{" "}
        {!s.protected?.checked ? t("chưa kiểm được (OpenStreetMap không phản hồi).", "could not be checked (OpenStreetMap did not respond).")
          : s.protected.inside.length ? s.protected.inside.join(", ")
            : t("không thấy khu bảo tồn nào chứa tâm thửa theo OpenStreetMap (OSM không phải bản đồ pháp lý).",
                "no protected area containing the plot centre per OpenStreetMap (OSM is not a legal map).")}
      </p>
      {s.wc2021 && (
        <p className="eu-src">{t("Tham khảo:", "For reference:")} {s.wc2021.name} {pct(s.wc2021.pct)} —{" "}
          {t("không dùng để kết luận mất rừng vì ESA đổi thuật toán giữa bản 2020 và 2021.",
             "not used to infer loss because ESA changed the algorithm between the 2020 and 2021 maps.")}</p>
      )}
      <ul className="eu-caveats">{s.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
    </div>
  );
}
