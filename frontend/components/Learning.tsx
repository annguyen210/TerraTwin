"use client";

/**
 * S05 Federated + S09 Model Engine + U04 Vòng khép kín — cả ba trên một trang,
 * vì với người dùng chúng là MỘT câu chuyện: "phần mềm học từ thực tế thế nào,
 * và hiện đã học tới đâu".
 *
 * Trang này cố ý hiển thị cả khi kho còn rỗng, kèm con số 0 rõ ràng. Giấu đi
 * khi chưa có dữ liệu sẽ tạo cảm giác mọi thứ đã chạy; hiện số 0 nói đúng rằng
 * vòng học mới bắt đầu và cần chính người đang xem góp vào.
 */

import { useCallback, useEffect, useState } from "react";
import {
  getFederated, getLoop, getModelEval,
  type AuthUser, type FederatedStatus, type LoopStatus, type ModelEval,
} from "@/lib/api";

function pct(x: number | null): string {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}

export default function Learning({ user }: { user: AuthUser | null }) {
  const [fed, setFed] = useState<FederatedStatus | null>(null);
  const [evalr, setEvalr] = useState<ModelEval | null>(null);
  const [loop, setLoop] = useState<LoopStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    // Ba nguồn độc lập: một cái hỏng không được che mất hai cái kia.
    const [f, m] = await Promise.allSettled([getFederated(), getModelEval()]);
    if (f.status === "fulfilled") setFed(f.value);
    if (m.status === "fulfilled") setEvalr(m.value);
    if (f.status === "rejected" && m.status === "rejected") {
      setErr("Không kết nối được máy chủ.");
    }
    if (user) {
      try { setLoop(await getLoop()); } catch { /* chưa đăng nhập thì bỏ qua */ }
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const maxStage = loop?.stages.length
    ? Math.max(1, ...loop.stages.map((s) => s.count))
    : 1;

  return (
    <>
      {err && <p className="ws-err">⚠️ {err}</p>}

      {/* ---------------------------------------------------------- U04 */}
      {loop && (
        <section className="lr-sec">
          <h3>U04 · Vòng khép kín của riêng bạn</h3>
          <p className="ws-sub">{loop.headline}</p>
          <div className="lr-funnel">
            {loop.stages.map((s) => (
              <div key={s.stage} className="lr-stage">
                <div className="lr-stage-bar">
                  <i style={{ width: `${(s.count / maxStage) * 100}%` }} />
                </div>
                <span className="lr-stage-l">{s.stage}</span>
                <b>{s.count}</b>
              </div>
            ))}
          </div>
          {loop.help_rate != null && (
            <p className="lr-kpi">
              Trong {loop.outcomes_verified} lần đã đối chiếu kết quả,{" "}
              <b>{loop.helped_count}</b> lần cảnh báo giúp tránh hoặc giảm được
              thiệt hại ({pct(loop.help_rate)}).
            </p>
          )}
          <p className="ws-note">{loop.note}</p>
        </section>
      )}

      {!user && (
        <p className="ws-hint">
          Đăng nhập để xem vòng khép kín của riêng bạn. Hai phần dưới là số liệu
          chung, ai cũng xem được.
        </p>
      )}

      {/* ---------------------------------------------------------- S09 */}
      {evalr && (
        <section className="lr-sec">
          <h3>S09 · Mô hình đang đúng tới đâu</h3>
          <p className="ws-sub">{evalr.headline}</p>

          <div className="lr-metrics">
            {(["csi", "pod", "far", "bias"] as const).map((k) => (
              <div key={k} className="lr-metric">
                <span className="lr-m-k">{k.toUpperCase()}</span>
                <b>{evalr.overall[k] ?? "—"}</b>
                <p>{evalr.metric_guide[k]}</p>
              </div>
            ))}
          </div>

          <div className="lr-tally">
            <span>Báo đúng: <b>{evalr.overall.hit}</b></span>
            <span>Báo hụt: <b>{evalr.overall.false_alarm}</b></span>
            <span>Bỏ sót: <b>{evalr.overall.miss}</b></span>
            <span>Yên đúng: <b>{evalr.overall.correct_negative}</b></span>
          </div>

          <p className="lr-verdict">Kết luận: {evalr.overall_verdict}</p>
          {evalr.why_csi_first && (
            <p className="ws-note">{evalr.why_csi_first}</p>
          )}
          <p className="ws-note">
            Dựa trên {evalr.dataset.observations} quan sát thực địa,{" "}
            {evalr.dataset.modules_covered} mô-đun, {evalr.dataset.cells_covered} vùng.
          </p>
        </section>
      )}

      {/* ---------------------------------------------------------- S05 */}
      {fed && (
        <section className="lr-sec">
          <h3>S05 · Hiệu chỉnh học từ cả mạng lưới</h3>
          <div className="lr-tally">
            <span>Quan sát: <b>{fed.total_observations}</b></span>
            <span>Người góp: <b>{fed.contributors}</b></span>
            <span>Vùng đã công bố: <b>{fed.cells_published}</b></span>
            <span>Vùng chờ đủ dữ liệu: <b>{fed.cells_pending}</b></span>
          </div>

          {fed.adjustments.length === 0 ? (
            <p className="ws-hint">
              Chưa vùng nào đủ {fed.min_observations} quan sát để công bố hiệu
              chỉnh. Mỗi lần bạn báo lại chuyện đã xảy ra trên thửa là một bước
              tới ngưỡng đó.
            </p>
          ) : (
            fed.adjustments.map((a, i) => (
              <div key={i} className="ws-item">
                <div>
                  <b>Vùng {a.cell} · {a.module_id}</b>
                  <p>
                    Dịch ngưỡng{" "}
                    <b style={{ color: a.threshold_shift > 0 ? "#B07A2E" : "#5fcb8e" }}>
                      {a.threshold_shift > 0 ? "+" : ""}{a.threshold_shift}
                    </b>{" "}
                    — {a.direction}
                  </p>
                  <p className="ws-when">
                    {a.observations} quan sát · đúng {a.hit} · hụt {a.false_alarm}{" "}
                    · sót {a.missed}
                  </p>
                </div>
              </div>
            ))
          )}

          <p className="ws-note">{fed.privacy}</p>
        </section>
      )}
    </>
  );
}
