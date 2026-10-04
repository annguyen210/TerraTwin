"use client";

/**
 * AI THAM KHẢO "rừng hay vườn cây?" — mô hình học từ chuỗi ảnh Sentinel-2 năm 2020, đã qua
 * ngưỡng kiểm định đặt trước trên vùng địa lý tách biệt. Chạy KHI NGƯỜI DÙNG BẤM (mỗi lần
 * ~45 giây tải chuỗi ảnh). KHÔNG thay kết luận sàng lọc, KHÔNG vào hồ sơ ký.
 */
import { useState } from "react";
import { Brain } from "lucide-react";
import { eudrForestOrCrop, type ForestOrCrop, type GeoGeometry } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function ForestOrCropHint({ geometry }: { geometry: GeoGeometry }) {
  const { t } = useLang();
  const [r, setR] = useState<ForestOrCrop | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function ask() {
    setBusy(true); setErr(null);
    try { setR(await eudrForestOrCrop(geometry)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  const p = r?.probability_forest;
  return (
    <div className="foc">
      <div className="foc-head">
        <Brain size={18} aria-hidden="true" />
        <b>{t("AI tham khảo: năm 2020 đây là rừng tự nhiên hay vườn cây?", "AI reference: was this natural forest or a tree crop in 2020?")}</b>
        {!r && <button className="bat-btn ghost" onClick={ask} disabled={busy}>{busy ? t("Đang đọc chuỗi ảnh 2020… (~45 giây)", "Reading the 2020 image series… (~45 s)") : t("Hỏi AI", "Ask the AI")}</button>}
      </div>
      {err && <p className="bat-err">{err}</p>}
      {r && (p == null ? (
        <p className="doc-note">{r.message}</p>
      ) : (
        <>
          <div className="foc-bar" role="img" aria-label={r.label}>
            <i style={{ width: `${Math.round(p * 100)}%` }} />
          </div>
          <div className="foc-legend"><span>{t("Rừng tự nhiên", "Natural forest")} {Math.round(p * 100)}%</span><span>{t("Vườn cây lâu năm", "Tree crop")} {100 - Math.round(p * 100)}%</span></div>
          {r.model && (
            <p className="eu-src">
              {t(`Mô hình ${r.model.kind} huấn luyện ${r.model.date}. Kiểm định trên ${r.model.test.n} mẫu ở vùng địa lý KHÔNG dùng để huấn luyện: độ chính xác cân bằng ${r.model.test.balanced_accuracy}, nhận đúng rừng ${r.model.test.forest_recall}, nhận đúng vườn ${r.model.test.tree_crop_recall}. `,
                 `Model ${r.model.kind} trained ${r.model.date}. Tested on ${r.model.test.n} samples from a region NOT used for training: balanced accuracy ${r.model.test.balanced_accuracy}, forest recall ${r.model.test.forest_recall}, tree-crop recall ${r.model.test.tree_crop_recall}. `)}
              {t("Đây là dự đoán THAM KHẢO — không thay kết luận sàng lọc ở trên và không đưa vào hồ sơ ký.",
                 "This is a REFERENCE prediction — it doesn't replace the screening verdict above and isn't put in the signed dossier.")}
            </p>
          )}
        </>
      ))}
    </div>
  );
}
