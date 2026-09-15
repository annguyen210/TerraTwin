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
import { useLang } from "@/lib/i18n";

// Icon theo MODULE ID (ổn định giữa hai ngôn ngữ, không theo tên hiển thị).
const ICON: Record<string, string> = {
  flood: "🌊", landslide: "⛰️", drought: "🌵", wildfire: "🔥",
};

export default function Passport({ lat, lon }: { lat: number; lon: number }) {
  const { t: tr, lang } = useLang();
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
  }, [lat, lon, lang]);

  if (busy) {
    return (
      <div className="ps ps-busy">
        <span className="ans-spin sm" />
        <p>{tr("Đang dựng hồ sơ riêng của thửa này — địa hình và 10 năm lịch sử…",
               "Building this plot's own record — terrain and 10-year history…")}</p>
      </div>
    );
  }
  if (!d || !d.available) return null;

  const t = d.terrain;
  const hz = Object.entries(d.history ?? {})
    .filter(([, h]) => h.events > 0)
    .sort(([, a], [, b]) => b.events - a.events);

  return (
    <div className="ps">
      <span className="ps-cap">{tr("Hồ sơ riêng của thửa này", "This plot's own record")}</span>

      {t && (
        <div className="ps-terrain">
          <div className="ps-bar">
            <i style={{ width: `${t.lower_than_pct}%` }} />
            <b>{t.lower_than_pct}%</b>
          </div>
          <p className="ps-lead">
            {tr("Thửa này", "This plot is")} <b>{tr(`cao ${t.elevation_m} m`, `${t.elevation_m} m high`)}</b>,{" "}
            {tr("thấp hơn", "lower than")} <b>{t.lower_than_pct}%</b>{" "}
            {tr(`đất trong bán kính ${t.radius_km} km`, `of land within ${t.radius_km} km`)}
            {t.slope_deg != null && <> · {tr(`dốc ${t.slope_deg}°`, `slope ${t.slope_deg}°`)}</>}
          </p>
          <p className="ps-mean">{t.meaning}</p>
        </div>
      )}

      {hz.length > 0 && (
        <ul className="ps-hz">
          {hz.map(([id, h]) => (
            <li key={id}>
              <span className="ps-ic">{ICON[id] ?? "•"}</span>
              <div>
                <b>
                  {tr(`${h.events} lần ${h.name}`, `${h.events} ${h.name} episode(s)`)}
                </b>{" "}
                {tr("vượt ngưỡng chung cả nước trong 10 năm", "exceeding the national threshold in 10 years")}
                {h.peak_month && (
                  <>
                    {" "}· {tr("nhiều nhất", "most in")} <b>{tr(`tháng ${h.peak_month}`, `month ${h.peak_month}`)}</b>
                  </>
                )}
                <span className="ps-sub">
                  {tr(`nặng nhất ${h.worst_date} · gần nhất ${h.latest}`,
                      `worst ${h.worst_date} · latest ${h.latest}`)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="ps-why">{d.why_unique}</p>

      <button className="ps-more" onClick={() => setMo(!mo)}>
        {mo ? tr("Thu gọn", "Collapse") : tr("Con số này đo thế nào?", "How is this measured?")}
      </button>
      {mo && <p className="ps-caveat">{d.caveat}</p>}
    </div>
  );
}
