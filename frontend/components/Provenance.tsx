"use client";

/**
 * SUP-12 — Hồ sơ truy xuất nguồn gốc.
 *
 * Nhà nhập khẩu và kiểm toán ESG hỏi "lô hàng này lớn lên trong điều kiện nào".
 * ERA5 trả lời được cho bất kỳ toạ độ nào ở Việt Nam, và mã băm cho bên mua tự
 * kiểm hồ sơ chưa bị sửa.
 *
 * Phần QUAN TRỌNG NHẤT của component này là dòng `scope` ở cuối: hồ sơ KHÔNG
 * chứng minh nông sản thật sự đến từ đây. Bỏ dòng đó đi là biến một công cụ
 * minh bạch thành một tờ giấy chứng nhận giả.
 */

import { useState } from "react";
import { runProvenance, type Provenance as P } from "@/lib/api";
import { useLang } from "@/lib/i18n";

function val(o: Record<string, unknown> | undefined, k: string) {
  const v = o?.[k];
  return v === null || v === undefined ? "—" : String(v);
}

function defaultRange(): [string, string] {
  const end = new Date();
  end.setDate(end.getDate() - 10);          // ERA5 chậm ~5–7 ngày
  const start = new Date(end);
  start.setDate(start.getDate() - 110);     // một vụ lúa ~110 ngày
  return [start.toISOString().slice(0, 10), end.toISOString().slice(0, 10)];
}

export default function Provenance({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [d0, d1] = defaultRange();
  const [start, setStart] = useState(d0);
  const [end, setEnd] = useState(d1);
  const [product, setProduct] = useState("");
  const [grower, setGrower] = useState("");
  const [r, setR] = useState<P | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setR(await runProvenance(lat, lon, start, end, product.trim(), grower.trim()));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const m = r?.measured;

  return (
    <div className="pan">
      <div className="pan-head">📜 {t("Hồ sơ truy xuất — điều kiện cả vụ", "Provenance record — whole-season conditions")}</div>
      <p className="pan-sub">
        {t("Điều kiện môi trường THẬT tại đúng toạ độ này suốt vụ, lấy từ ERA5. Kèm mã băm để bên mua tự kiểm hồ sơ chưa bị sửa.",
           "REAL environmental conditions at this exact coordinate for the whole season, from ERA5. Includes a hash so buyers can verify the record hasn't been altered.")}
      </p>

      <div className="mrv-form">
        <div className="pv-dates">
          <label>
            {t("Bắt đầu vụ", "Season start")}
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label>
            {t("Kết thúc vụ", "Season end")}
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        <input
          placeholder={t("Sản phẩm — vd. Gạo ST25", "Product — e.g. ST25 rice")}
          value={product}
          onChange={(e) => setProduct(e.target.value)}
        />
        <input
          placeholder={t("Người trồng / HTX", "Grower / cooperative")}
          value={grower}
          onChange={(e) => setGrower(e.target.value)}
        />
        <button className="pan-go" disabled={busy} onClick={run}>
          {busy ? t("Đang tra ERA5…", "Querying ERA5…") : t("Lập hồ sơ", "Build record")}
        </button>
      </div>

      {err && <p className="pan-err">⚠️ {err}</p>}
      {r && !r.available && <p className="pan-err">⚠️ {r.message}</p>}

      {r?.available && (
        <>
          <p className="pan-line">{r.headline}</p>

          <div className="mrv-block measured">
            <div className="mrv-b-h">📡 {t("Đo được (ERA5 / ECMWF)", "Measured (ERA5 / ECMWF)")}</div>
            <div className="mrv-kv"><span>{t("Tổng mưa cả vụ", "Total season rainfall")}</span><b>{val(m, "rain_total_mm")} mm</b></div>
            <div className="mrv-kv"><span>{t("Mưa lớn nhất một ngày", "Heaviest single-day rain")}</span><b>{val(m, "rain_max_day_mm")} mm</b></div>
            <div className="mrv-kv"><span>{t("Số ngày khô", "Dry days")}</span><b>{val(m, "dry_days")}</b></div>
            <div className="mrv-kv"><span>{t("Nhiệt tối đa trung bình", "Average max temperature")}</span><b>{val(m, "tmax_mean_c")}°C</b></div>
            <div className="mrv-kv"><span>{t("Nhiệt cao nhất", "Peak temperature")}</span><b>{val(m, "tmax_peak_c")}°C</b></div>
            <div className="mrv-kv"><span>{t("Bốc thoát hơi cả vụ", "Total season evapotranspiration")}</span><b>{val(m, "et0_total_mm")} mm</b></div>
          </div>

          <div className="mrv-block change">
            <div className="mrv-b-h">📍 {t("Bối cảnh thửa", "Plot context")}</div>
            <div className="mrv-kv"><span>{t("Cao độ", "Elevation")}</span><b>{val(r.context, "elevation_m")} m</b></div>
            <div className="mrv-kv"><span>{t("Cách biển", "Distance to sea")}</span><b>{val(r.context, "coast_km")} km</b></div>
            <div className="mrv-kv"><span>{t("Vùng mặn", "Salinity zone")}</span><b>{val(r.context, "salinity_zone")}</b></div>
          </div>

          {r.integrity && (
            <div className="mrv-hash">
              <b>🔒 {t("Mã toàn vẹn", "Integrity hash")} {String(r.integrity.algorithm)}</b>
              <code>{String(r.integrity.hash)}</code>
              <p>{String(r.integrity.note)}</p>
            </div>
          )}

          <p className="mrv-warn">⚠️ {r.scope}</p>
        </>
      )}
    </div>
  );
}
