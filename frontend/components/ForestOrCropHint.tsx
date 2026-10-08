"use client";

/**
 * AI THAM KHẢO "rừng hay vườn cây?" — HAI tín hiệu độc lập, mỗi cái chỉ hiện khi đã qua ngưỡng
 * kiểm định đặt trước của riêng nó:
 *   1. Mô hình Sentinel-2 12 tháng năm 2020 (~45 giây, tải chuỗi ảnh).
 *   2. Mô hình nền tảng AlphaEarth (Google DeepMind) — vectơ 64 chiều đã tính sẵn (vài giây).
 * Chạy KHI NGƯỜI DÙNG BẤM. KHÔNG thay kết luận sàng lọc, KHÔNG vào hồ sơ ký.
 */
import { useEffect, useState } from "react";
import { Brain, Sparkles } from "lucide-react";
import { eudrAefPredict, eudrAefStatus, eudrForestOrCrop, type AefPredict, type ForestOrCrop, type GeoGeometry } from "@/lib/api";
import { useLang } from "@/lib/i18n";

function Bar({ p, label }: { p: number; label?: string }) {
  const { t } = useLang();
  return (
    <>
      <div className="foc-bar" role="img" aria-label={label}>
        <i style={{ width: `${Math.round(p * 100)}%` }} />
      </div>
      <div className="foc-legend"><span>{t("Rừng", "Forest")} {Math.round(p * 100)}%</span><span>{t("Vườn cây / không rừng", "Tree crop / non-forest")} {100 - Math.round(p * 100)}%</span></div>
    </>
  );
}

export default function ForestOrCropHint({ geometry }: { geometry: GeoGeometry }) {
  const { t } = useLang();
  const [r, setR] = useState<ForestOrCrop | null>(null);
  const [a, setA] = useState<AefPredict | null>(null);
  const [aefOn, setAefOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { eudrAefStatus().then((s) => setAefOn(s.available)).catch(() => setAefOn(false)); }, []);

  async function ask() {
    setBusy(true); setErr(null);
    const jobs: Promise<unknown>[] = [eudrForestOrCrop(geometry).then(setR)];
    if (aefOn) jobs.push(eudrAefPredict(geometry).then(setA).catch(() => setA(null)));
    try { await Promise.all(jobs); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  const p = r?.probability_forest;
  return (
    <div className="foc">
      <div className="foc-head">
        <Brain size={18} aria-hidden="true" />
        <b>{t("AI tham khảo: năm 2020 đây là rừng hay vườn cây?", "AI reference: was this forest or a tree crop in 2020?")}</b>
        {!r && <button className="bat-btn ghost" onClick={ask} disabled={busy}>{busy ? t("Đang đọc chuỗi ảnh 2020… (~45 giây)", "Reading the 2020 image series… (~45 s)") : t("Hỏi AI", "Ask the AI")}</button>}
      </div>
      {err && <p className="bat-err">{err}</p>}
      {r && (p == null ? (
        <p className="doc-note">{r.message}</p>
      ) : (
        <>
          <p className="foc-src">{t("Mô hình Sentinel-2 (nhịp sinh trưởng 12 tháng)", "Sentinel-2 model (12-month growth rhythm)")}</p>
          <Bar p={p} label={r.label} />
          {r.model && (
            <p className="eu-src">
              {t(`Mô hình ${r.model.kind} huấn luyện ${r.model.date}. Kiểm định trên ${r.model.test.n} mẫu ở vùng địa lý KHÔNG dùng để huấn luyện: độ chính xác cân bằng ${r.model.test.balanced_accuracy}, nhận đúng rừng ${r.model.test.forest_recall}, nhận đúng vườn ${r.model.test.tree_crop_recall}.`,
                 `Model ${r.model.kind} trained ${r.model.date}. Tested on ${r.model.test.n} samples from a region NOT used for training: balanced accuracy ${r.model.test.balanced_accuracy}, forest recall ${r.model.test.forest_recall}, tree-crop recall ${r.model.test.tree_crop_recall}.`)}
            </p>
          )}
        </>
      ))}
      {a && a.probability_forest != null && (
        <>
          <p className="foc-src"><Sparkles size={14} aria-hidden="true" /> {t("Mô hình nền tảng AlphaEarth (Google DeepMind)", "AlphaEarth foundation model (Google DeepMind)")}</p>
          <Bar p={a.probability_forest} label={a.label} />
          {a.model && <p className="eu-src">{t(
            `Vectơ 64 chiều năm 2020 trên ${a.pixels} điểm ảnh 10 m. Kiểm định trên ${a.model.test.n} mẫu vùng tách biệt: độ chính xác cân bằng ${a.model.test.balanced_accuracy}, nhận đúng rừng ${a.model.test.forest_recall}.`,
            `64-dimensional 2020 embedding over ${a.pixels} 10 m pixels. Tested on ${a.model.test.n} held-out samples: balanced accuracy ${a.model.test.balanced_accuracy}, forest recall ${a.model.test.forest_recall}.`)}</p>}
          {a.change && <p className="doc-note">{a.change.label}</p>}
          <p className="eu-src">{a.attribution}</p>
        </>
      )}
      {a && a.probability_forest == null && a.message && <p className="doc-note">{a.message}</p>}
      {r && <p className="eu-src">{t("Đây là dự đoán THAM KHẢO — không thay kết luận sàng lọc ở trên và không đưa vào hồ sơ ký.",
                                     "These are REFERENCE predictions — they don't replace the screening verdict above and aren't put in the signed dossier.")}</p>}
    </div>
  );
}
