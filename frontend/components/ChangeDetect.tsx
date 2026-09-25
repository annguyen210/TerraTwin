"use client";

/**
 * A7 — phát hiện mất tán cây bền vững trên chuỗi NDVI theo tháng (BFAST/CUSUM
 * rút gọn), gắn vào màn kết quả của mô-đun carbon — đây là nơi câu hỏi "tán
 * cây có đang mất đi thật không, hay chỉ là mùa vụ" có ý nghĩa nhất.
 */

import { useEffect, useState } from "react";
import { changeDetect, type ChangeDetectResult } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function ChangeDetect({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [d, setD] = useState<ChangeDetectResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setD(null);
    setErr(null);
    changeDetect(lat, lon, 24)
      .then((r) => live && setD(r))
      .catch((e) => live && setErr((e as Error).message));
    return () => { live = false; };
  }, [lat, lon]);

  if (err) return null;   // im lặng — đây là khối bổ sung, hỏng không được chặn kết quả carbon chính
  if (!d) return (
    <div className="pan">
      <p className="pan-sub">{t("Đang dò biến động tán cây 24 tháng…", "Scanning 24 months of canopy change…")}</p>
    </div>
  );

  if (!d.available) {
    return (
      <div className="pan">
        <div className="pan-head">🌲 {t("Biến động tán cây (A7)", "Canopy change (A7)")}</div>
        <p className="pan-sub">{d.message}</p>
      </div>
    );
  }

  return (
    <div className="pan">
      <div className="pan-head">🌲 {t("Biến động tán cây (A7)", "Canopy change (A7)")}</div>
      <p className="pan-sub">
        {t("Phân tích", "Analyzed")} <b>{d.n_scenes}</b> {t("tháng có ảnh quang mây", "months with clear imagery")}
        {d.window && <> ({d.window[0]} → {d.window[1]})</>}.
      </p>
      <div className={d.change_detected ? "mc-verdict win" : "mc-verdict tie"}>
        <p>{d.message}</p>
      </div>
      {d.change_detected && d.change_date && (
        <p className="pan-line">
          {t("Mốc phát hiện:", "Detected around:")} <b>{d.change_date}</b>
          {" · "}{t("NDVI giảm", "NDVI dropped")} <b>{Math.abs(d.level_shift_ndvi ?? 0).toFixed(3)}</b>
        </p>
      )}
      <p className="pan-caveat">
        {t("Dựa trên trung vị NDVI theo tháng (BFAST/CUSUM rút gọn) — phân biệt mất tán bền vững với dao động mùa vụ (vd lúa ba vụ), khác so sánh hai lát cắt năm-nay-vs-năm-ngoái.",
           "Based on monthly median NDVI (simplified BFAST/CUSUM) — separates sustained canopy loss from seasonal fluctuation (e.g. triple-crop rice), unlike a simple this-year-vs-last-year comparison.")}
      </p>
    </div>
  );
}
