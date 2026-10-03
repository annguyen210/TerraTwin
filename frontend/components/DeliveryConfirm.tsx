"use client";

/**
 * XÁC NHẬN GIAO HÀNG — chỉ hiện khi mở hồ sơ bằng ĐƯỜNG LINK ĐẦY ĐỦ của nông hộ (có khoá
 * chủ hồ sơ). Nông hộ thấy doanh nghiệp nào đang khai bao nhiêu kg từ vườn mình, và tự
 * xác nhận hoặc từ chối — không ai khai hộ được khối lượng của vườn người khác.
 */

import { useCallback, useEffect, useState } from "react";
import { confirmDelivery, dossierDeliveries, type PendingDelivery } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function DeliveryConfirm({ id, token }: { id: string; token: string }) {
  const { t } = useLang();
  const [rows, setRows] = useState<PendingDelivery[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => dossierDeliveries(id, token).then((r) => setRows(r.deliveries)).catch((e) => setErr(e.message)), [id, token]);
  useEffect(() => { load(); }, [load]);
  if (err) return null;                      // không phải link chủ hồ sơ → không hiện gì
  if (!rows) return null;
  return (
    <section className="dos-noprint">
      <h2>{t("Đợt giao hàng khai cho vườn của bạn", "Deliveries declared from your plot")}</h2>
      <p className="dos-src">{t("Chỉ bạn thấy mục này (mở bằng đường link đầy đủ). Xác nhận đợt bạn thật sự đã bán; từ chối đợt không đúng — đợt bị từ chối sẽ bị chặn khỏi lô hàng.",
        "Only you see this (opened with the full link). Confirm deliveries you actually sold; reject wrong ones — rejected deliveries are blocked from the lot.")}</p>
      {rows.length === 0 ? <p className="dos-note">{t("Chưa có doanh nghiệp nào khai giao hàng từ vườn này.", "No company has declared a delivery from this plot yet.")}</p> : (
        <div className="dos-table-wrap"><table className="dos-table">
          <thead><tr><th>{t("Lô", "Lot")}</th><th>{t("Doanh nghiệp", "Operator")}</th><th>{t("Vụ", "Season")}</th><th>kg</th><th>{t("Trạng thái", "Status")}</th><th></th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.lot_id}>
              <td>{r.lot_ref || r.lot_id}<small>{r.commodity}{r.lot_state === "certified" ? ` · ${t("đã có chứng thư", "certified")}` : ""}</small></td>
              <td>{r.operator || "—"}</td><td>{r.season}</td><td className="num">{r.kg.toLocaleString("vi-VN")}</td>
              <td>{r.confirmation ? (r.confirmation.status === "confirmed" ? t("Đã xác nhận", "Confirmed") : t("Đã từ chối", "Rejected")) : t("Chờ bạn", "Waiting for you")}</td>
              <td className="dos-actions-cell">
                <button className="bat-btn" onClick={() => confirmDelivery(id, r.lot_id, token, "confirm").then(load).catch((e) => setErr(e.message))}>{t("Xác nhận", "Confirm")}</button>
                <button className="bat-btn ghost danger" onClick={() => confirmDelivery(id, r.lot_id, token, "reject").then(load).catch((e) => setErr(e.message))}>{t("Từ chối", "Reject")}</button>
              </td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </section>
  );
}
