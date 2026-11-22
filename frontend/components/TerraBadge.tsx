"use client";

// Thẻ "7 ngày tới" ở đầu thẻ thửa — tách khỏi app/page.tsx để test được (trang Next.js không export thêm được).
import type { TerraScore } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { badgeHead } from "@/lib/terraBadge";

// Kiểm 7/11/2026 mục 4: "TerraScore 100 · Hạng A" to nhất ở đầu thẻ thửa đọc như "đất tốt" — thửa demo ngập 5 lần trong
// mùa lũ vẫn hiện 100/Hạng A. Con số này chỉ là hiểm hoạ THỜI TIẾT 7 ngày tới, nên nói đúng điều đó bằng chữ, chỉ sang
// lịch sử nước, và lùi con số về chú thích nhỏ.
export default function TerraBadge({ t }: { t: TerraScore }) {
  const { t: tr } = useLang();
  // Kiểm A–Z lần 2 (22/11/2026): lượt quét sâu có lũ từ thượng nguồn NGUY HIỂM mà thẻ vẫn "7 ngày tới: yên" (chữ to chọn
  // theo grade — chỉ chấm 5 hiểm hoạ thời tiết). Mối đe doạ khác (other_threats) đi TRƯỚC grade.
  const [color, head] = badgeHead(t, tr);
  return (
    <div className="terra terra-7d">
      <div className="terra-txt">
        <div className="terra-grade" style={{ color }}>{head}</div>
        <div className="terra-sum">{tr("Thời tiết sắp tới, KHÔNG phải lịch sử ngập. Thửa từng ngập chưa: xem Lịch sử nước ở tab Hồ sơ.",
                                       "Upcoming weather, NOT flood history. Has this plot flooded: see Water history in the Dossier tab.")}</div>
        <div className="terra-real">
          TerraScore {t.score}/100 · {tr("hạng", "grade")} {t.grade} {tr("(5 hiểm hoạ thời tiết)", "(5 weather hazards)")}
          {t.real_data_ratio != null && ` · 🛰️ ${Math.round(t.real_data_ratio * 100)}% ${tr("hiểm họa dùng dữ liệu thật", "of hazards use real data")}`}
        </div>
      </div>
    </div>
  );
}
