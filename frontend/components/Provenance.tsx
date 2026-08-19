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
      <div className="pan-head">📜 Hồ sơ truy xuất — điều kiện cả vụ</div>
      <p className="pan-sub">
        Điều kiện môi trường THẬT tại đúng toạ độ này suốt vụ, lấy từ ERA5. Kèm
        mã băm để bên mua tự kiểm hồ sơ chưa bị sửa.
      </p>

      <div className="mrv-form">
        <div className="pv-dates">
          <label>
            Bắt đầu vụ
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label>
            Kết thúc vụ
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        <input
          placeholder="Sản phẩm — vd. Gạo ST25"
          value={product}
          onChange={(e) => setProduct(e.target.value)}
        />
        <input
          placeholder="Người trồng / HTX"
          value={grower}
          onChange={(e) => setGrower(e.target.value)}
        />
        <button className="pan-go" disabled={busy} onClick={run}>
          {busy ? "Đang tra ERA5…" : "Lập hồ sơ"}
        </button>
      </div>

      {err && <p className="pan-err">⚠️ {err}</p>}
      {r && !r.available && <p className="pan-err">⚠️ {r.message}</p>}

      {r?.available && (
        <>
          <p className="pan-line">{r.headline}</p>

          <div className="mrv-block measured">
            <div className="mrv-b-h">📡 Đo được (ERA5 / ECMWF)</div>
            <div className="mrv-kv"><span>Tổng mưa cả vụ</span><b>{val(m, "rain_total_mm")} mm</b></div>
            <div className="mrv-kv"><span>Mưa lớn nhất một ngày</span><b>{val(m, "rain_max_day_mm")} mm</b></div>
            <div className="mrv-kv"><span>Số ngày khô</span><b>{val(m, "dry_days")}</b></div>
            <div className="mrv-kv"><span>Nhiệt tối đa trung bình</span><b>{val(m, "tmax_mean_c")}°C</b></div>
            <div className="mrv-kv"><span>Nhiệt cao nhất</span><b>{val(m, "tmax_peak_c")}°C</b></div>
            <div className="mrv-kv"><span>Bốc thoát hơi cả vụ</span><b>{val(m, "et0_total_mm")} mm</b></div>
          </div>

          <div className="mrv-block change">
            <div className="mrv-b-h">📍 Bối cảnh thửa</div>
            <div className="mrv-kv"><span>Cao độ</span><b>{val(r.context, "elevation_m")} m</b></div>
            <div className="mrv-kv"><span>Cách biển</span><b>{val(r.context, "coast_km")} km</b></div>
            <div className="mrv-kv"><span>Vùng mặn</span><b>{val(r.context, "salinity_zone")}</b></div>
          </div>

          {r.integrity && (
            <div className="mrv-hash">
              <b>🔒 Mã toàn vẹn {String(r.integrity.algorithm)}</b>
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
