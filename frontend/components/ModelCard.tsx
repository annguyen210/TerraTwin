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
import { useLang } from "@/lib/i18n";

const OPERATING = 2.0;

export default function ModelCard() {
  const { t, lang } = useLang();
  const [d, setD] = useState<Card | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mo, setMo] = useState(false);

  useEffect(() => {
    getModelCard().then(setD).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="pan"><p className="pan-err">⚠️ {err}</p></div>;
  if (!d) return <div className="pan"><p className="pan-sub">{t("Đang tải…", "Loading…")}</p></div>;

  if (!d.available) {
    return (
      <div className="pan">
        <div className="pan-head">🧠 {t("Mô hình đã huấn luyện", "Trained model")}</div>
        <p className="pan-err">⚠️ {d.message}</p>
      </div>
    );
  }

  const cmp = d.comparison ?? [];
  const van = cmp.find((c) => c.alarm_rate === OPERATING);
  const nScope = van?.joint_events.filter((e) => e.in_scope).length ?? 0;
  const numFmt = lang === "en" ? "en" : "vi";

  return (
    <div className="pan">
      <div className="pan-head">🧠 {t("Mô hình đã huấn luyện — và chỗ nó chưa hơn", "Trained model — and where it doesn't yet win")}</div>

      <p className="pan-sub">
        {t("Hệ thống cũ xét ", "The old system looks at ")}<b>{t("từng biến một", "one variable at a time")}</b>
        {t(", nên một tổ hợp xấu mà không biến nào cực đoan riêng lẻ thì lọt lưới. Mô hình này đo độ hiếm của ",
           ", so a bad combination where no single variable is extreme on its own slips through. This model measures the rarity of ")}
        <b>{t("cả tổ hợp", "the whole combination")}</b>
        {t(`, học tự giám sát trên ${d.train_days?.toLocaleString(numFmt)} ngày ERA5 thật.`,
           `, self-supervised on ${d.train_days?.toLocaleString(numFmt)} days of real ERA5.`)}
      </p>

      <div className="mc-stats">
        <div><b>{d.sites}</b><span>{t("điểm khí hậu", "climate points")}</span></div>
        <div><b>{d.train_days?.toLocaleString(numFmt)}</b><span>{t("ngày huấn luyện", "training days")}</span></div>
        <div><b>{d.test_days?.toLocaleString(numFmt)}</b><span>{t("ngày kiểm tra", "test days")}</span></div>
        <div><b>{d.features?.length}</b><span>{t("đặc trưng", "features")}</span></div>
      </div>

      <p className="pan-line">
        {t("Huấn luyện", "Trained")} <b>{d.train_period?.join(" → ")}</b>{t(", kiểm tra trên", ", tested on")}{" "}
        <b>{d.test_period?.join(" → ")}</b>{t(" — 5 năm về sau, chưa từng thấy lúc học.",
                                              " — 5 years ahead, never seen during training.")}
      </p>

      {/* Kết luận đặt TRƯỚC bảng, để không ai phải đọc hết mới biết */}
      <div className={van && van.joint_detected > van.baseline_detected
        ? "mc-verdict win" : "mc-verdict tie"}>
        <span className="mc-cap">{t(`Kết luận ở mức vận hành ${OPERATING}%`, `Verdict at the ${OPERATING}% operating rate`)}</span>
        <p>{d.verdict}</p>
        <p className="mc-role">{d.role}</p>
      </div>

      <div className="mc-tablewrap">
        <table className="mc-table">
          <thead>
            <tr>
              <th>{t("Mức báo động", "Alarm rate")}</th>
              <th>{t("Tổ hợp", "Combined")}<br /><i>{t("mô hình mới", "new model")}</i></th>
              <th>{t("Từng biến", "Single-variable")}<br /><i>{t("cách hiện tại", "current approach")}</i></th>
              <th>{t("Chênh", "Diff")}</th>
            </tr>
          </thead>
          <tbody>
            {cmp.map((c) => {
              const diff = c.joint_detected - c.baseline_detected;
              const isOp = c.alarm_rate === OPERATING;
              return (
                <tr key={c.alarm_rate} className={isOp ? "op" : ""}>
                  <td>
                    {c.alarm_rate}%{isOp && <b> ← {t("vận hành", "operating")}</b>}
                  </td>
                  <td className="n">{c.joint_detected}/{nScope}</td>
                  <td className="n">{c.baseline_detected}/{nScope}</td>
                  <td className={`n ${diff > 0 ? "up" : diff < 0 ? "down" : ""}`}>
                    {diff > 0 ? `+${diff}` : diff < 0 ? diff : t("hoà", "tie")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="pan-caveat">
        {t("Cùng tỉ lệ báo động thì mới so được. Một mô hình báo nhiều hơn đương nhiên bắt được nhiều hơn — nên ngưỡng hai bên đều đặt sao cho báo đúng bằng nhau, rồi mới đếm.",
           "Only comparable at the same alarm rate. A model that alarms more will naturally catch more — so both sides' thresholds are set to alarm equally often, then counted.")}
      </p>

      <button className="mc-more" onClick={() => setMo(!mo)}>
        {mo ? t("Thu gọn", "Collapse") : t("Xem chi tiết từng sự kiện, vùng khí hậu và giới hạn", "See per-event detail, climate zones, and limitations")}
      </button>

      {mo && (
        <div className="mc-detail">
          {van && (
            <>
              <h4>{t(`Từng sự kiện, ở mức vận hành ${OPERATING}%`, `Per event, at the ${OPERATING}% operating rate`)}</h4>
              <ul className="mc-events">
                {van.joint_events.map((e, i) => {
                  const b = van.baseline_events[i];
                  return (
                    <li key={e.site} className={e.in_scope ? "" : "out"}>
                      <b>{e.label}</b>
                      {!e.in_scope && <em> — {t("ngoài tầm, không tính điểm", "out of scope, not scored")}</em>}
                      <span>
                        {t("tổ hợp", "combined")}: {e.detected ? t(`bắt, sớm ${e.lead_days} ngày`, `caught, ${e.lead_days}d early`) : t("bỏ sót", "missed")}
                        {" · "}
                        {t("từng biến", "single-variable")}: {b?.detected ? t(`bắt, sớm ${b.lead_days} ngày`, `caught, ${b.lead_days}d early`) : t("bỏ sót", "missed")}
                      </span>
                    </li>
                  );
                })}
              </ul>
              <p className="mc-note">
                <b>{t("Vì sao Bến Tre 2020 nằm ngoài tầm.", "Why Bến Tre 2020 is out of scope.")}</b>{" "}
                {t("Cân bằng nước 60 ngày giữa tháng 3 tại Bến Tre: 2015 −269 · 2016 −284 · ",
                   "60-day water balance ending mid-March at Bến Tre: 2015 −269 · 2016 −284 · ")}
                <b>2020 −287</b> · 2024 −300.{" "}
                {t("Tháng 3/2020 chỉ khô thứ nhì trong mười năm, và năm 2024 còn khô hơn. Thảm hoạ mặn năm đó do dòng chảy thượng nguồn Mekong, ",
                   "March 2020 was only the second-driest in ten years, and 2024 was drier still. That year's salinity disaster was caused by upstream Mekong flow, ")}
                <b>{t("không có dấu vết trong khí tượng tại chỗ", "with no trace in local weather")}</b>
                {t(" — nên một mô hình đọc thời tiết địa phương không thể và không nên bắt được nó. Muốn bắt thì phải đọc lưu lượng sông, đúng như module xâm nhập mặn đang làm.",
                   " — so a model reading local weather cannot and should not catch it. Catching it requires reading river discharge, which is exactly what the salinity module does.")}
              </p>
            </>
          )}

          {d.leave_one_out && d.leave_one_out.length > 0 && (
            <>
              <h4>{t("Chạy ở tỉnh chưa từng huấn luyện", "Run on a province never trained on")}</h4>
              <p className="mc-sub">
                {t(`Bỏ hẳn một tỉnh khỏi quá trình học rồi chấm chính tỉnh đó. Đây mới là câu hỏi thật, vì sản phẩm phải chạy ở 63 tỉnh chứ không phải ${d.sites} điểm.`,
                   `Leaves one province entirely out of training, then scores that exact province. This is the real question, since the product must run across 63 provinces, not just the ${d.sites} training points.`)}
              </p>
              <ul className="mc-events">
                {d.leave_one_out.map((e) => (
                  <li key={e.site}>
                    <b>{e.label}</b>
                    <span>{e.detected
                      ? t(`bắt được, sớm ${e.lead} ngày`, `caught, ${e.lead}d early`)
                      : t("bỏ sót", "missed")}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <h4>{t("Bốn vùng khí hậu mô hình tự tìm ra", "Four climate regimes the model found on its own")}</h4>
          <p className="mc-sub">
            {t("Không ai gán nhãn vùng — thuật toán gom cụm tự tách từ chữ ký khí hậu 10 năm của mỗi nơi.",
               "No one labeled the zones — the clustering algorithm separated them from each place's 10-year climate signature.")}
          </p>
          <ul className="mc-regimes">
            {d.regimes?.map((r) => (
              <li key={r.id}>
                <b>{t("Vùng", "Zone")} {r.id}</b>
                <span>{r.days.toLocaleString(numFmt)} {t("ngày", "days")} · {r.sites.join(", ")}</span>
              </li>
            ))}
          </ul>

          <h4>{t("Cách làm", "Method")}</h4>
          <p className="mc-sub">{d.method}</p>
          <p className="mc-sub">
            {t("Đặc trưng:", "Features:")} {d.features?.join(" · ")}
          </p>
        </div>
      )}
    </div>
  );
}
