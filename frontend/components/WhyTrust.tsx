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

const TEN: Record<string, string> = {
  flood: "Lũ & ngập",
  landslide: "Sạt lở",
  drought: "Hạn & thiếu nước",
  wildfire: "Cháy rừng",
};

export default function WhyTrust({ lat, lon }: { lat: number; lon: number }) {
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
  }, [lat, lon]);

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
      <span className="wt-cap">Vì sao tin được con số này</span>

      {dangKe ? (
        <>
          <p className="wt-lead">
            Ngay tại thửa này, một hệ thống dùng <b>ngưỡng chung cho cả nước</b>{" "}
            sẽ kêu báo động <b>{noiBat.fixed_days_per_year} ngày mỗi năm</b> cho{" "}
            {TEN[noiBat.module_id]?.toLowerCase()}. TerraTwin kêu{" "}
            <b>{noiBat.calibrated_days_per_year} ngày</b>.
          </p>
          <div className="wt-bars">
            <div className="wt-row">
              <span>Ngưỡng chung</span>
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
            <p className="wt-unit">ngày báo động mỗi năm · đo trên 10 năm lịch sử của chính toạ độ này</p>
          </div>
          <p className="wt-why">
            Một cảnh báo kêu {Math.round(lan)} lần nhiều hơn mức cần thiết thì
            người ta tắt nó sau tuần thứ hai — và lúc nguy hiểm thật thì không
            ai còn nghe nữa.
          </p>
        </>
      ) : (
        <p className="wt-lead">
          Ở riêng thửa này, ngưỡng chung cả nước tình cờ cho kết quả gần giống
          TerraTwin ({noiBat.fixed_days_per_year} so với{" "}
          {noiBat.calibrated_days_per_year} ngày/năm). Chỗ khác thì lệch rất
          nhiều — bấm bên dưới để xem.
        </p>
      )}

      <button className="wt-more" onClick={() => setMo(!mo)}>
        {mo ? "Thu gọn" : "Xem cả bốn hiểm hoạ và cách tính"}
      </button>

      {mo && (
        <div className="wt-detail">
          <table>
            <thead>
              <tr>
                <th>Hiểm hoạ</th>
                <th>Ngưỡng chung</th>
                <th>TerraTwin</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.module_id}>
                  <td>{TEN[r.module_id] ?? r.module_id}</td>
                  <td className="n">{r.fixed_days_per_year}</td>
                  <td className="n">{r.calibrated_days_per_year}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="wt-unit">ngày báo động mỗi năm</p>

          {cam.length > 0 && (
            <p className="wt-note">
              <b>Chú ý chiều ngược lại.</b> Với{" "}
              {cam.map((r) => TEN[r.module_id]?.toLowerCase()).join(", ")}, ngưỡng
              chung ở đây kêu <b>0 ngày/năm</b> — tức là <b>điếc hoàn toàn</b>,
              không phải an toàn. Cùng một ngưỡng cố định vừa kêu oan chỗ này
              vừa bỏ sót chỗ kia; đó mới là lý do phải hiệu chuẩn theo từng nơi,
              chứ không phải vì con số nào đẹp hơn.
            </p>
          )}

          <p className="wt-method">
            {rows[0].method} Cả hai đều đo trên {rows[0].years} năm dữ liệu ERA5
            thật tại toạ độ này — không phải con số quảng cáo.
          </p>
        </div>
      )}
    </div>
  );
}
