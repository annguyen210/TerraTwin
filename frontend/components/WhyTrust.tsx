"use client";

/**
 * "Vì sao tin được" — làm cho cái vô hình hiện lên.
 *
 * VẤN ĐỀ CỐT LÕI MÀ KHỐI NÀY GIẢI. Điểm mạnh nhất của TerraTwin là thứ không
 * nhìn thấy được theo đúng nghĩa đen: báo động giả 3% nghĩa là những lần kêu
 * oan ĐÃ KHÔNG XẢY RA — mà không ai nhìn thấy được thứ không xảy ra. Người dùng
 * mở app lên chỉ thấy "hôm nay an toàn", y hệt mọi phần mềm khác. Họ không có
 * cơ sở nào để tin cái này hơn cái kia, và họ nói đúng: chúng tôi chưa đưa ra
 * cơ sở nào cả.
 *
 * Cách duy nhất là cho xem ĐỐI CHỨNG, tính tại chính toạ độ họ vừa bấm: một hệ
 * thống dùng ngưỡng chung cả nước sẽ báo động bao nhiêu ngày một năm ở đây.
 *
 * HAI KIỂU HỎNG, và cả hai đều phải nói ra — không chỉ khoe kiểu có lợi:
 *   · KÊU OAN  — Trà Leng, sạt lở: ngưỡng chung kêu 125 ngày/năm.
 *   · ĐIẾC HẲN — cũng Trà Leng, hạn: ngưỡng chung kêu 0 ngày/năm.
 * Cùng một ngưỡng, cùng một chỗ, hỏng theo hai hướng ngược nhau. Đó mới là lý
 * lẽ thật, chứ không phải "của chúng tôi tốt hơn".
 */

import { useEffect, useState } from "react";
import { getContrast, type ModuleContrast } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const TEN: Record<string, [string, string]> = {
  flood: ["Lũ & ngập", "Flood"],
  landslide: ["Sạt lở", "Landslide"],
  drought: ["Hạn & thiếu nước", "Drought"],
  wildfire: ["Cháy rừng", "Wildfire"],
};

export default function WhyTrust({ lat, lon }: { lat: number; lon: number }) {
  const { t, lang } = useLang();
  const nameOf = (id: string) => (TEN[id] ? t(TEN[id][0], TEN[id][1]) : id);
  const [rows, setRows] = useState<ModuleContrast[] | null>(null);
  const [mo, setMo] = useState(false);

  useEffect(() => {
    let huy = false;
    setRows(null);
    getContrast(lat, lon)
      .then((r) => !huy && setRows(r.available ? r.modules : []))
      .catch(() => !huy && setRows([]));
    return () => {
      huy = true;
    };
  }, [lat, lon, lang]);

  if (!rows || rows.length === 0) return null;

  // Chọn ví dụ nổi bật nhất — nhưng ưu tiên trường hợp KÊU OAN vì nó dễ hiểu
  // ngay; trường hợp điếc hẳn nêu ở phần mở rộng.
  const co = rows.filter((r) => r.calibrated_days_per_year > 0);
  if (co.length === 0) return null;
  const noiBat = co.reduce((a, b) =>
    b.fixed_days_per_year / Math.max(b.calibrated_days_per_year, 0.1) >
    a.fixed_days_per_year / Math.max(a.calibrated_days_per_year, 0.1)
      ? b
      : a,
  );
  const lan =
    noiBat.fixed_days_per_year /
    Math.max(noiBat.calibrated_days_per_year, 0.1);

  // Nếu ở đây ngưỡng chung tình cờ không tệ thì nói thật, đừng bịa ra chênh lệch.
  const dangKe = lan >= 1.6;
  const cam = rows.filter(
    (r) => r.fixed_days_per_year === 0 && r.calibrated_days_per_year > 0,
  );

  return (
    <div className="wt">
      <span className="wt-cap">{t("Vì sao tin được con số này", "Why you can trust this number")}</span>

      {dangKe ? (
        <>
          <p className="wt-lead">
            {t("Ngay tại thửa này, một hệ thống dùng", "Right at this plot, a system using a")}{" "}
            <b>{t("ngưỡng chung cho cả nước", "nationwide threshold")}</b>{" "}
            {t("sẽ kêu báo động", "would raise alerts")}{" "}
            <b>{noiBat.fixed_days_per_year} {t("ngày mỗi năm", "days a year")}</b> {t("cho", "for")}{" "}
            {nameOf(noiBat.module_id).toLowerCase()}. {t("TerraTwin kêu", "TerraTwin raises")}{" "}
            <b>{noiBat.calibrated_days_per_year} {t("ngày", "days")}</b>.
          </p>
          <div className="wt-bars">
            <div className="wt-row">
              <span>{t("Ngưỡng chung", "Nationwide")}</span>
              <div className="wt-bar">
                <i
                  className="bad"
                  style={{
                    width: `${Math.min(100, (noiBat.fixed_days_per_year / 365) * 100 * 3)}%`,
                  }}
                />
              </div>
              <b>{noiBat.fixed_days_per_year}</b>
            </div>
            <div className="wt-row">
              <span>TerraTwin</span>
              <div className="wt-bar">
                <i
                  className="ok"
                  style={{
                    width: `${Math.min(100, (noiBat.calibrated_days_per_year / 365) * 100 * 3)}%`,
                  }}
                />
              </div>
              <b>{noiBat.calibrated_days_per_year}</b>
            </div>
            <p className="wt-unit">{t("ngày báo động mỗi năm · đo trên 10 năm lịch sử của chính toạ độ này",
                                      "alert days per year · measured over 10 years of history at this exact point")}</p>
          </div>
          <p className="wt-why">
            {t(`Một cảnh báo kêu ${Math.round(lan)} lần nhiều hơn mức cần thiết thì người ta tắt nó sau tuần thứ hai — và lúc nguy hiểm thật thì không ai còn nghe nữa.`,
               `An alert that fires ${Math.round(lan)}× more than needed gets muted by week two — and when real danger comes, no one is listening.`)}
          </p>
        </>
      ) : (
        <p className="wt-lead">
          {t(`Ở riêng thửa này, ngưỡng chung cả nước tình cờ cho kết quả gần giống TerraTwin (${noiBat.fixed_days_per_year} so với ${noiBat.calibrated_days_per_year} ngày/năm). Chỗ khác thì lệch rất nhiều — bấm bên dưới để xem.`,
             `At this particular plot, the nationwide threshold happens to match TerraTwin closely (${noiBat.fixed_days_per_year} vs ${noiBat.calibrated_days_per_year} days/year). Elsewhere it diverges a lot — tap below to see.`)}
        </p>
      )}

      <button className="wt-more" onClick={() => setMo(!mo)}>
        {mo ? t("Thu gọn", "Collapse") : t("Xem cả bốn hiểm hoạ và cách tính", "See all four hazards and the method")}
      </button>

      {mo && (
        <div className="wt-detail">
          <table>
            <thead>
              <tr>
                <th>{t("Hiểm hoạ", "Hazard")}</th>
                <th>{t("Ngưỡng chung", "Nationwide")}</th>
                <th>TerraTwin</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.module_id}>
                  <td>{nameOf(r.module_id)}</td>
                  <td className="n">{r.fixed_days_per_year}</td>
                  <td className="n">{r.calibrated_days_per_year}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="wt-unit">{t("ngày báo động mỗi năm", "alert days per year")}</p>

          {cam.length > 0 && (
            <p className="wt-note">
              <b>{t("Chú ý chiều ngược lại.", "Note the opposite direction.")}</b> {t("Với", "For")}{" "}
              {cam.map((r) => nameOf(r.module_id).toLowerCase()).join(", ")}, {t("ngưỡng chung ở đây kêu", "the nationwide threshold here fires")} <b>{t("0 ngày/năm", "0 days/year")}</b> — {t("tức là", "i.e.")} <b>{t("điếc hoàn toàn", "totally deaf")}</b>, {t("không phải an toàn. Cùng một ngưỡng cố định vừa kêu oan chỗ này vừa bỏ sót chỗ kia; đó mới là lý do phải hiệu chuẩn theo từng nơi, chứ không phải vì con số nào đẹp hơn.",
                 "not safe. The same fixed threshold both over-warns here and misses there; that's why it must be calibrated per place, not because one number looks nicer.")}
            </p>
          )}

          <p className="wt-method">
            {rows[0].method} {t(`Cả hai đều đo trên ${rows[0].years} năm dữ liệu ERA5 thật tại toạ độ này — không phải con số quảng cáo.`,
                                `Both are measured over ${rows[0].years} years of real ERA5 data at this point — not marketing figures.`)}
          </p>
        </div>
      )}
    </div>
  );
}
