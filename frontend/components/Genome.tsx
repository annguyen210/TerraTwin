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
import { useLang } from "@/lib/i18n";

export default function Genome({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
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
      <div className="pan-head">🧬 {t("Bộ gen thửa đất — tìm vùng “song sinh”", "Plot genome — find “twin” regions")}</div>

      {!data && !busy && (
        <>
          <p className="pan-sub">
            {t("So 7 đặc trưng của thửa này với lưới toàn quốc để tìm những vùng có cùng “bộ gen” đất đai — nơi kinh nghiệm của họ dùng được cho bạn.",
               "Compares 7 traits of this plot against a nationwide grid to find regions with the same land “genome” — places whose experience applies to you.")}
          </p>
          <button className="pan-go" onClick={run}>
            {t("Tìm vùng tương đồng", "Find similar regions")}
          </button>
          <p className="pan-note">
            {t("Lần đầu có thể mất 1–2 phút vì phải dựng lưới tham chiếu; sau đó lấy từ bộ nhớ đệm.",
               "The first run can take 1–2 minutes to build the reference grid; after that it's served from cache.")}
          </p>
        </>
      )}

      {busy && <p className="pan-sub">{t("Đang quét lưới toàn quốc…", "Scanning the nationwide grid…")}</p>}
      {err && <p className="pan-err">⚠️ {err}</p>}

      {data && !data.available && (
        <p className="pan-err">⚠️ {data.message}</p>
      )}

      {data?.available && (
        <>
          <p className="pan-line">{data.headline}</p>

          {data.your_genome && data.feature_labels && (
            <div className="gen-mine">
              <div className="gen-mine-h">{t("Bộ gen thửa của bạn", "Your plot's genome")}</div>
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

          {data.twins?.map((tw, i) => (
            <div key={i} className="gen-twin">
              <div className="gen-twin-h">
                <b>{tw.similarity_pct}% {t("giống", "similar")}</b>
                <span>
                  {tw.lat.toFixed(2)}, {tw.lon.toFixed(2)} · {t("cách", "distance")} {tw.distance_km} km
                </span>
              </div>
              {tw.comparison.slice(0, 4).map((c) => (
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
