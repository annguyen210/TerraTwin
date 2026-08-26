"use client";

/**
 * HỒ SƠ THỬA ĐẤT — câu trả lời cho "phần mềm này hơn app thời tiết ở chỗ nào".
 *
 * Người dùng nói các tính năng nghe giống mọi phần mềm khác: cảnh báo lũ, cảnh
 * báo hạn, bản đồ nhiệt. Họ so sánh xong không thấy hơn ở đâu — và họ nói
 * đúng, những thứ đó KHÔNG hơn ở đâu cả.
 *
 * Khối này nói ba điều mà không ứng dụng dự báo nào nói được, vì chúng không
 * biết thửa của bạn nằm ở đâu trong địa hình và đã trải qua những gì:
 *
 *   "Thửa này trũng hơn 78% đất trong bán kính 3 km — nước dồn về đây trước."
 *   "Mười năm qua chỗ này có 274 lần mưa vượt ngưỡng chung cả nước."
 *   "Tháng nguy hiểm nhất của thửa là tháng 10."
 *
 * Câu cuối quan trọng hơn vẻ ngoài: lịch mùa vụ dạy chung cho cả tỉnh, còn
 * thửa đất thì không theo lịch tỉnh.
 */

import { useEffect, useState } from "react";
import { getPassport, type Passport as P } from "@/lib/api";

const ICON: Record<string, string> = {
  "ngập lụt": "🌊", "sạt lở": "⛰️", "hạn thiếu nước": "🌵", "cháy": "🔥",
};

export default function Passport({ lat, lon }: { lat: number; lon: number }) {
  const [d, setD] = useState<P | null>(null);
  const [busy, setBusy] = useState(false);
  const [mo, setMo] = useState(false);

  useEffect(() => {
    let huy = false;
    setBusy(true);
    setD(null);
    getPassport(lat, lon)
      .then((r) => !huy && setD(r))
      .catch(() => !huy && setD(null))
      .finally(() => !huy && setBusy(false));
    return () => {
      huy = true;
    };
  }, [lat, lon]);

  if (busy) {
    return (
      <div className="ps ps-busy">
        <span className="ans-spin sm" />
        <p>Đang dựng hồ sơ riêng của thửa này — địa hình và 10 năm lịch sử…</p>
      </div>
    );
  }
  if (!d || !d.available) return null;

  const t = d.terrain;
  const hz = Object.values(d.history ?? {}).filter((h) => h.events > 0);
  hz.sort((a, b) => b.events - a.events);

  return (
    <div className="ps">
      <span className="ps-cap">Hồ sơ riêng của thửa này</span>

      {t && (
        <div className="ps-terrain">
          <div className="ps-bar">
            <i style={{ width: `${t.lower_than_pct}%` }} />
            <b>{t.lower_than_pct}%</b>
          </div>
          <p className="ps-lead">
            Thửa này <b>cao {t.elevation_m} m</b>, thấp hơn{" "}
            <b>{t.lower_than_pct}%</b> đất trong bán kính {t.radius_km} km
            {t.slope_deg != null && <> · dốc {t.slope_deg}°</>}
          </p>
          <p className="ps-mean">{t.meaning}</p>
        </div>
      )}

      {hz.length > 0 && (
        <ul className="ps-hz">
          {hz.map((h) => (
            <li key={h.name}>
              <span className="ps-ic">{ICON[h.name] ?? "•"}</span>
              <div>
                <b>
                  {h.events} lần {h.name}
                </b>{" "}
                vượt ngưỡng chung cả nước trong 10 năm
                {h.peak_month && (
                  <>
                    {" "}· nhiều nhất <b>tháng {h.peak_month}</b>
                  </>
                )}
                <span className="ps-sub">
                  nặng nhất {h.worst_date} · gần nhất {h.latest}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="ps-why">{d.why_unique}</p>

      <button className="ps-more" onClick={() => setMo(!mo)}>
        {mo ? "Thu gọn" : "Con số này đo thế nào?"}
      </button>
      {mo && <p className="ps-caveat">{d.caveat}</p>}
    </div>
  );
}
