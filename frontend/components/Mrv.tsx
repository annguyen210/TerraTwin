"use client";

/**
 * C07 — Báo cáo MRV carbon/ESG.
 *
 * Giao diện cố ý TÁCH ĐÔI theo đúng cách backend tách: phần ĐO ĐƯỢC từ vệ tinh
 * và phần ƯỚC LƯỢNG bằng hệ số. Trộn hai phần vào một con số đẹp là cách một
 * báo cáo carbon trở thành thứ lừa chính người lập ra nó.
 */

import { useState } from "react";
import { runMrv, type MrvReport } from "@/lib/api";
import { useLang } from "@/lib/i18n";

function num(o: Record<string, unknown> | undefined, k: string) {
  const v = o?.[k];
  return typeof v === "number" ? v : typeof v === "string" ? v : "—";
}

export default function Mrv({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [r, setR] = useState<MrvReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [agb, setAgb] = useState("");

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const v = agb.trim() ? Number(agb) : undefined;
      setR(await runMrv(lat, lon, name.trim(), Number.isFinite(v!) ? v : undefined));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const m = r?.measured;
  const e = r?.estimated;
  const ch = r?.change_vs_last_year as Record<string, unknown> | null | undefined;

  return (
    <div className="pan">
      <div className="pan-head">🌲 {t("Báo cáo carbon / ESG (MRV)", "Carbon / ESG report (MRV)")}</div>

      <div className="mrv-form">
        <input
          placeholder={t("Tên lô / dự án", "Plot / project name")}
          value={name}
          onChange={(ev) => setName(ev.target.value)}
        />
        <input
          placeholder={t("Hệ số sinh khối địa phương t/ha (nếu có khảo sát ô mẫu)",
                         "Local biomass factor t/ha (if you have plot-survey data)")}
          value={agb}
          onChange={(ev) => setAgb(ev.target.value)}
          inputMode="decimal"
        />
        <button className="pan-go" disabled={busy} onClick={run}>
          {busy ? t("Đang lập báo cáo…", "Building report…") : t("Lập báo cáo", "Build report")}
        </button>
      </div>

      {err && <p className="pan-err">⚠️ {err}</p>}

      {r && !r.available && <p className="pan-err">⚠️ {r.message}</p>}

      {r?.available && (
        <>
          <p className="pan-line">{r.headline}</p>

          <div className="mrv-block measured">
            <div className="mrv-b-h">📡 {t("Đo được từ vệ tinh", "Measured from satellite")}</div>
            <div className="mrv-kv"><span>{t("Diện tích xét", "Area assessed")}</span><b>{num(m, "aoi_ha")} ha</b></div>
            <div className="mrv-kv"><span>{t("Che phủ tán", "Canopy cover")}</span><b>{num(m, "canopy_pct")}%</b></div>
            <div className="mrv-kv"><span>{t("Diện tích có rừng", "Forested area")}</span><b>{num(m, "forest_ha")} ha</b></div>
            <div className="mrv-kv"><span>{t("NDVI trung bình", "Average NDVI")}</span><b>{num(m, "ndvi_mean")}</b></div>
            <div className="mrv-kv"><span>{t("Ảnh quang mây", "Cloud-free imagery")}</span><b>{num(m, "cloud_free_pct")}%</b></div>
          </div>

          <div className="mrv-block estimated">
            <div className="mrv-b-h">📐 {t("Ước lượng bằng hệ số — không phải số đo", "Estimated via factors — not a direct measurement")}</div>
            <div className="mrv-tier">{num(e, "tier_label")}</div>
            <div className="mrv-kv">
              <span>{t("Trữ lượng", "Stock")}</span>
              <b>{num(e, "stock_tco2")} tCO₂</b>
            </div>
            <div className="mrv-kv">
              <span>{t(`Dải sai số ±${num(e, "uncertainty_pct")}%`, `Uncertainty range ±${num(e, "uncertainty_pct")}%`)}</span>
              <b>{num(e, "stock_tco2_low")} – {num(e, "stock_tco2_high")}</b>
            </div>
            <p className="mrv-math">{num(e, "arithmetic")}</p>
          </div>

          {ch && (
            <div className="mrv-block change">
              <div className="mrv-b-h">📉 {t("So với cùng kỳ năm trước", "Compared to the same period last year")}</div>
              <div className="mrv-kv">
                <span>{t("Che phủ", "Cover")}</span>
                <b>{String(ch.previous_canopy_pct)}% → {String(ch.current_canopy_pct)}%</b>
              </div>
              <div className="mrv-kv">
                <span>{String(ch.verdict)}</span>
                <b>{String(ch.delta_ha)} ha · {String(ch.delta_tco2)} tCO₂</b>
              </div>
            </div>
          )}

          <div className="mrv-warn">
            {r.limitations?.map((l, i) => (
              <p key={i}>{i === 0 ? "⚠️ " : "· "}{l}</p>
            ))}
          </div>

          <details className="mrv-more">
            <summary>{t("Cần gì để lên chuẩn phát hành tín chỉ", "What's needed to reach credit-issuance grade")}</summary>
            <ol>
              {r.to_reach_credit_grade?.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </details>

          <details className="mrv-more">
            <summary>{t("Phương pháp luận", "Methodology")}</summary>
            {Object.values(r.methodology ?? {}).map((v, i) => <p key={i}>{v}</p>)}
          </details>

          {r.integrity && (
            <div className="mrv-hash">
              <b>🔒 {t(`Mã toàn vẹn ${String(r.integrity.algorithm)}`, `Integrity hash ${String(r.integrity.algorithm)}`)}</b>
              <code>{String(r.integrity.hash)}</code>
              <p>{String(r.integrity.note)}</p>
              <p className="ws-note">{String(r.integrity.not_a_signature)}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
