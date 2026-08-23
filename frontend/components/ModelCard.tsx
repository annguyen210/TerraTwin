"use client";

/**
 * Thẻ mô hình — bằng chứng nhìn thấy được của phần huấn luyện.
 *
 * NGUYÊN TẮC DUY NHẤT CỦA MÀN HÌNH NÀY: hiện cả chỗ mô hình KHÔNG thắng.
 *
 * Bảng đối đầu giữ nguyên mọi mức báo động đã thử. Ở mức vận hành 2% mô hình
 * chỉ HOÀ với cách cũ, và dòng đó được tô đậm chứ không bị đẩy xuống cuối.
 * Một thẻ mô hình chỉ khoe mức thắng thì không phải thẻ mô hình, nó là quảng
 * cáo — và với phần mềm cảnh báo thiên tai thì quảng cáo là thứ nguy hiểm.
 *
 * Cũng nêu rõ sự kiện Bến Tre 2020 nằm NGOÀI TẦM và vì sao, thay vì lặng lẽ
 * bỏ nó khỏi bảng.
 */

import { useEffect, useState } from "react";
import { getModelCard, type ModelCard as Card } from "@/lib/api";

const OPERATING = 2.0;

export default function ModelCard() {
  const [d, setD] = useState<Card | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mo, setMo] = useState(false);

  useEffect(() => {
    getModelCard().then(setD).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="pan"><p className="pan-err">⚠️ {err}</p></div>;
  if (!d) return <div className="pan"><p className="pan-sub">Đang tải…</p></div>;

  if (!d.available) {
    return (
      <div className="pan">
        <div className="pan-head">🧠 Mô hình đã huấn luyện</div>
        <p className="pan-err">⚠️ {d.message}</p>
      </div>
    );
  }

  const cmp = d.comparison ?? [];
  const van = cmp.find((c) => c.alarm_rate === OPERATING);
  const nScope = van?.joint_events.filter((e) => e.in_scope).length ?? 0;

  return (
    <div className="pan">
      <div className="pan-head">🧠 Mô hình đã huấn luyện — và chỗ nó chưa hơn</div>

      <p className="pan-sub">
        Hệ thống cũ xét <b>từng biến một</b>, nên một tổ hợp xấu mà không biến
        nào cực đoan riêng lẻ thì lọt lưới. Mô hình này đo độ hiếm của{" "}
        <b>cả tổ hợp</b>, học tự giám sát trên {d.train_days?.toLocaleString("vi")} ngày
        ERA5 thật.
      </p>

      <div className="mc-stats">
        <div><b>{d.sites}</b><span>điểm khí hậu</span></div>
        <div><b>{d.train_days?.toLocaleString("vi")}</b><span>ngày huấn luyện</span></div>
        <div><b>{d.test_days?.toLocaleString("vi")}</b><span>ngày kiểm tra</span></div>
        <div><b>{d.features?.length}</b><span>đặc trưng</span></div>
      </div>

      <p className="pan-line">
        Huấn luyện <b>{d.train_period?.join(" → ")}</b>, kiểm tra trên{" "}
        <b>{d.test_period?.join(" → ")}</b> — 5 năm về sau, chưa từng thấy lúc học.
      </p>

      {/* Kết luận đặt TRƯỚC bảng, để không ai phải đọc hết mới biết */}
      <div className={van && van.joint_detected > van.baseline_detected
        ? "mc-verdict win" : "mc-verdict tie"}>
        <span className="mc-cap">Kết luận ở mức vận hành {OPERATING}%</span>
        <p>{d.verdict}</p>
        <p className="mc-role">{d.role}</p>
      </div>

      <div className="mc-tablewrap">
        <table className="mc-table">
          <thead>
            <tr>
              <th>Mức báo động</th>
              <th>Tổ hợp<br /><i>mô hình mới</i></th>
              <th>Từng biến<br /><i>cách hiện tại</i></th>
              <th>Chênh</th>
            </tr>
          </thead>
          <tbody>
            {cmp.map((c) => {
              const diff = c.joint_detected - c.baseline_detected;
              const isOp = c.alarm_rate === OPERATING;
              return (
                <tr key={c.alarm_rate} className={isOp ? "op" : ""}>
                  <td>
                    {c.alarm_rate}%{isOp && <b> ← vận hành</b>}
                  </td>
                  <td className="n">{c.joint_detected}/{nScope}</td>
                  <td className="n">{c.baseline_detected}/{nScope}</td>
                  <td className={`n ${diff > 0 ? "up" : diff < 0 ? "down" : ""}`}>
                    {diff > 0 ? `+${diff}` : diff < 0 ? diff : "hoà"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="pan-caveat">
        Cùng tỉ lệ báo động thì mới so được. Một mô hình báo nhiều hơn đương
        nhiên bắt được nhiều hơn — nên ngưỡng hai bên đều đặt sao cho báo đúng
        bằng nhau, rồi mới đếm.
      </p>

      <button className="mc-more" onClick={() => setMo(!mo)}>
        {mo ? "Thu gọn" : "Xem chi tiết từng sự kiện, vùng khí hậu và giới hạn"}
      </button>

      {mo && (
        <div className="mc-detail">
          {van && (
            <>
              <h4>Từng sự kiện, ở mức vận hành {OPERATING}%</h4>
              <ul className="mc-events">
                {van.joint_events.map((e, i) => {
                  const b = van.baseline_events[i];
                  return (
                    <li key={e.site} className={e.in_scope ? "" : "out"}>
                      <b>{e.label}</b>
                      {!e.in_scope && <em> — ngoài tầm, không tính điểm</em>}
                      <span>
                        tổ hợp: {e.detected ? `bắt, sớm ${e.lead_days} ngày` : "bỏ sót"}
                        {" · "}
                        từng biến: {b?.detected ? `bắt, sớm ${b.lead_days} ngày` : "bỏ sót"}
                      </span>
                    </li>
                  );
                })}
              </ul>
              <p className="mc-note">
                <b>Vì sao Bến Tre 2020 nằm ngoài tầm.</b> Cân bằng nước 60 ngày
                giữa tháng 3 tại Bến Tre: 2015 −269 · 2016 −284 · <b>2020 −287</b> ·
                2024 −300. Tháng 3/2020 chỉ khô thứ nhì trong mười năm, và năm
                2024 còn khô hơn. Thảm hoạ mặn năm đó do dòng chảy thượng nguồn
                Mekong, <b>không có dấu vết trong khí tượng tại chỗ</b> — nên
                một mô hình đọc thời tiết địa phương không thể và không nên bắt
                được nó. Muốn bắt thì phải đọc lưu lượng sông, đúng như module
                xâm nhập mặn đang làm.
              </p>
            </>
          )}

          {d.leave_one_out && d.leave_one_out.length > 0 && (
            <>
              <h4>Chạy ở tỉnh chưa từng huấn luyện</h4>
              <p className="mc-sub">
                Bỏ hẳn một tỉnh khỏi quá trình học rồi chấm chính tỉnh đó. Đây
                mới là câu hỏi thật, vì sản phẩm phải chạy ở 63 tỉnh chứ không
                phải {d.sites} điểm.
              </p>
              <ul className="mc-events">
                {d.leave_one_out.map((e) => (
                  <li key={e.site}>
                    <b>{e.label}</b>
                    <span>{e.detected
                      ? `bắt được, sớm ${e.lead} ngày`
                      : "bỏ sót"}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <h4>Bốn vùng khí hậu mô hình tự tìm ra</h4>
          <p className="mc-sub">
            Không ai gán nhãn vùng — thuật toán gom cụm tự tách từ chữ ký khí
            hậu 10 năm của mỗi nơi.
          </p>
          <ul className="mc-regimes">
            {d.regimes?.map((r) => (
              <li key={r.id}>
                <b>Vùng {r.id}</b>
                <span>{r.days.toLocaleString("vi")} ngày · {r.sites.join(", ")}</span>
              </li>
            ))}
          </ul>

          <h4>Cách làm</h4>
          <p className="mc-sub">{d.method}</p>
          <p className="mc-sub">
            Đặc trưng: {d.features?.join(" · ")}
          </p>
        </div>
      )}
    </div>
  );
}
