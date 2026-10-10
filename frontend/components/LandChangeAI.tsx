"use client";

/**
 * GĐ5 — ĐẤT CÓ ĐỔI KHÁC SAU 2021? AlphaEarth (Google DeepMind) + bộ phân loại đã qua kiểm định đăng ký trước
 * (mIoU 0,42 trên 4 tỉnh mô hình chưa thấy). DỰ ĐOÁN — tham khảo, không vào hồ sơ ký. Bấm mới chạy (mỗi lượt
 * tải vài MB vectơ từ kho công khai).
 */
import { useEffect, useState } from "react";
import { Sprout } from "lucide-react";
import { landcoverChange, type LandChange } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const G: { k: "tree" | "crop" | "built" | "water" | "open"; vi: string; en: string; c: string }[] = [
  { k: "tree", vi: "Cây xanh", en: "Trees", c: "#2E9E67" },
  { k: "crop", vi: "Trồng trọt", en: "Cropland", c: "#C9A227" },
  { k: "built", vi: "Xây dựng", en: "Built-up", c: "#B4473A" },
  { k: "water", vi: "Mặt nước", en: "Water", c: "#1D5E87" },
  { k: "open", vi: "Đất trống / cỏ", en: "Open land", c: "#8A8F8C" },
];

export default function LandChangeAI({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [r, setR] = useState<LandChange | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setR(null); setErr(null); }, [lat, lon]);

  async function run() {
    setBusy(true); setErr(null);
    try { setR(await landcoverChange(lat, lon)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <section className="lc2">
      <div className="wh-head">
        <Sprout size={18} aria-hidden="true" />
        <h3>{t("Đất có đổi khác sau 2021?", "Has the land changed since 2021?")}</h3>
        <span className="wh-badge lc2-badge">{t("AI · dự đoán", "AI · prediction")}</span>
      </div>
      {!r && (
        <div className="wh-start">
          <p>{t("So loại đất năm 2021 với năm mới nhất bằng mô hình nền AlphaEarth của Google DeepMind — đã qua kiểm định đặt ngưỡng trước.",
                "Compare 2021 land cover with the latest year using Google DeepMind's AlphaEarth foundation model — validated against a pre-registered threshold.")}</p>
          <button className="bat-btn ghost" onClick={run} disabled={busy}>{busy ? t("Đang đọc vectơ AlphaEarth…", "Reading AlphaEarth vectors…") : t("Xem đất có đổi khác", "Check for change")}</button>
        </div>
      )}
      {err && <p className="bat-err">{err}</p>}
      {r && !r.available && <p className="doc-note">{r.message}</p>}
      {r && r.available && (
        <>
          <p className="wh-sum"><b>{r.headline}</b></p>
          <div className="lc2-rows" role="table" aria-label={t("Tỉ lệ nhóm đất theo năm", "Land-cover share by year")}>
            {[String(r.base_year), String(r.latest_year)].map((y) => (
              <div key={y} className="lc2-row" role="row">
                <span className="lc2-y" role="rowheader">{y}</span>
                <span className="lc2-bar" role="cell" aria-label={G.map((g) => `${t(g.vi, g.en)} ${r.years[y].groups_pct[g.k] ?? 0}%`).join(", ")}>
                  {G.map((g) => (r.years[y].groups_pct[g.k] ?? 0) > 0 && (
                    <i key={g.k} style={{ width: `${r.years[y].groups_pct[g.k]}%`, background: g.c }} title={`${t(g.vi, g.en)} ${r.years[y].groups_pct[g.k]}%`} />
                  ))}
                </span>
              </div>
            ))}
          </div>
          <ul className="lc2-legend">
            {G.map((g) => (
              <li key={g.k}><i style={{ background: g.c }} aria-hidden="true" />{t(g.vi, g.en)} {r.years[String(r.latest_year)].groups_pct[g.k] ?? 0}%
                {r.delta_pts[g.k] !== 0 && <small> ({r.delta_pts[g.k] > 0 ? "+" : ""}{r.delta_pts[g.k]})</small>}</li>
            ))}
          </ul>
          <p className="eu-src">{r.caveat} {r.attribution} <a href="/mo-hinh">{t("Thẻ mô hình", "Model card")}</a></p>
        </>
      )}
    </section>
  );
}
