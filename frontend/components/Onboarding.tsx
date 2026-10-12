"use client";

/**
 * GỢI Ý LẦN ĐẦU trong khu làm việc thửa — KHÔNG CHẶN thao tác.
 *
 * Bản cũ là lớp phủ toàn màn "1. Chọn thửa của bạn" bật lên SAU KHI người dùng đã chọn thửa (vd bấm "Xem ngay: Huế")
 * và nuốt mọi cú bấm (báo cáo kiểm toàn bộ 12/10/2026, mục 3). Nay: một thẻ nhỏ ở góc dưới, nói đúng việc tiếp theo
 * khi ĐÃ có thửa; bấm đâu trên trang vẫn được; đóng một lần là thôi (cờ localStorage).
 */
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useLang } from "@/lib/i18n";

const KEY = "tt_onboarded_v2";

export default function Onboarding() {
  const { t } = useLang();
  const [show, setShow] = useState(false);

  useEffect(() => {
    try { if (!localStorage.getItem(KEY)) setShow(true); } catch { /* chế độ riêng tư: không hiện */ }
  }, []);

  function close() {
    try { localStorage.setItem(KEY, "1"); } catch { /* */ }
    setShow(false);
  }

  if (!show) return null;
  return (
    <aside className="ob-hint" role="note" aria-label={t("Gợi ý", "Tip")}>
      <button type="button" className="ob-x" onClick={close} aria-label={t("Đóng gợi ý", "Close tip")}><X size={14} /></button>
      <b>{t("Đã mở thửa — bước tiếp theo", "Plot open — what next")}</b>
      <ol>
        <li>{t("Tab Hồ sơ: lịch sử nước radar tự đọc, loại đất, rồi phát hành hồ sơ ký số.", "Dossier tab: radar water history loads by itself, land cover, then issue a signed dossier.")}</li>
        <li>{t("Tab Kiểm chứng: dán tin đăng bán đất để đối chiếu từng câu.", "Verify tab: paste a sale listing to check each claim.")}</li>
        <li>{t("Đổi thửa: kéo bản đồ cho thửa vào giữa ô ngắm rồi bấm nút xanh.", "Change plot: drag the map so the plot sits in the crosshair, then press the green button.")}</li>
      </ol>
      <button type="button" className="bat-btn ghost" onClick={close}>{t("Đã hiểu", "Got it")}</button>
    </aside>
  );
}
