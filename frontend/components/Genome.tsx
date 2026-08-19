"use client";

/**
 * S04 Twin Genome — tìm những vùng có "bộ gen" đất đai giống thửa của bạn.
 *
 * Không tự chạy khi mở thửa: lần đầu tiên trong 30 ngày phải dựng lưới tham
 * chiếu toàn quốc, mất một hai phút. Bắt người dùng chờ ngần ấy chỉ vì họ vừa
 * bấm vào bản đồ là cách nhanh nhất để họ bỏ đi.
 */

import { useState } from "react";
import { runGenome, type GenomeResult } from "@/lib/api";

export default function Genome({ lat, lon }: { lat: number; lon: number }) {
  const [data, setData] = useState<GenomeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setData(await runGenome(lat, lon, 5));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pan">
      <div className="pan-head">🧬 Bộ gen thửa đất — tìm vùng “song sinh”</div>

      {!data && !busy && (
        <>
          <p className="pan-sub">
            So 7 đặc trưng của thửa này với lưới toàn quốc để tìm những vùng có
            cùng “bộ gen” đất đai — nơi kinh nghiệm của họ dùng được cho bạn.
          </p>
          <button className="pan-go" onClick={run}>
            Tìm vùng tương đồng
          </button>
          <p className="pan-note">
            Lần đầu có thể mất 1–2 phút vì phải dựng lưới tham chiếu; sau đó lấy
            từ bộ nhớ đệm.
          </p>
        </>
      )}

      {busy && <p className="pan-sub">Đang quét lưới toàn quốc…</p>}
      {err && <p className="pan-err">⚠️ {err}</p>}

      {data && !data.available && (
        <p className="pan-err">⚠️ {data.message}</p>
      )}

      {data?.available && (
        <>
          <p className="pan-line">{data.headline}</p>

          {data.your_genome && data.feature_labels && (
            <div className="gen-mine">
              <div className="gen-mine-h">Bộ gen thửa của bạn</div>
              {Object.entries(data.your_genome).map(([k, v]) => (
                <div key={k} className="gen-row">
                  <span>{data.feature_labels![k]?.label ?? k}</span>
                  <b>
                    {v} {data.feature_labels![k]?.unit ?? ""}
                  </b>
                </div>
              ))}
            </div>
          )}

          {data.twins?.map((t, i) => (
            <div key={i} className="gen-twin">
              <div className="gen-twin-h">
                <b>{t.similarity_pct}% giống</b>
                <span>
                  {t.lat.toFixed(2)}, {t.lon.toFixed(2)} · cách {t.distance_km} km
                </span>
              </div>
              {t.comparison.slice(0, 4).map((c) => (
                <div key={c.feature} className="gen-cmp">
                  <span>{c.label}</span>
                  <span className="gen-vals">
                    {c.yours} → {c.theirs} {c.unit}
                  </span>
                </div>
              ))}
            </div>
          ))}

          <p className="pan-why">{data.why_useful}</p>
          <p className="pan-caveat">{data.caveat}</p>
          <p className="pan-method">{data.method}</p>
        </>
      )}
    </div>
  );
}
