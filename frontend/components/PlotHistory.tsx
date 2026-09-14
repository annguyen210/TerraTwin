"use client";

/**
 * H4 + A5 — DÒNG THỜI GIAN CỦA MỘT THỬA, dùng chung cho Portfolio và MyLand.
 *
 * Đ9 — gộp câu chuyện thửa về một chỗ: trước đây timeline (H4) sống trong
 * Portfolio còn câu hỏi (H6) sống trong MyLand — hai nơi kể cùng một chuyện.
 * Tách ra file dùng chung để "Thửa của tôi" (MyLand) kể trọn: đã báo gì, đúng/
 * hụt, câu đang chờ, và nguồn gốc từng cảnh báo (A5).
 */
import { useEffect, useState } from "react";
import { getAlertLineage, getPlotTimeline, type AlertLineage, type PlotTimeline } from "@/lib/api";

/* A5 — nguồn gốc + tái lập cho MỘT cảnh báo, mở ngay dưới sự kiện. */
function LineageView({ alertId }: { alertId: number }) {
  const [d, setD] = useState<AlertLineage | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    getAlertLineage(alertId).then((r) => live && setD(r)).catch((e) => live && setErr((e as Error).message));
    return () => { live = false; };
  }, [alertId]);
  if (err) return <p className="pf-empty" style={{ margin: "2px 0" }}>{err}</p>;
  if (!d) return <p className="pf-empty" style={{ margin: "2px 0" }}>Đang tải nguồn gốc…</p>;
  return (
    <div style={{ margin: "4px 0 2px", padding: "6px 10px", fontSize: 11.5,
      background: "var(--surface, #fff)", borderRadius: 6, border: "1px solid var(--line-2, #e8ece8)" }}>
      <div><b>Nguồn dữ liệu:</b> {d.sources.join(" · ")}</div>
      <div><b>Ngưỡng:</b> chú ý {d.model.thresholds.safe} · nguy hiểm {d.model.thresholds.warning} (hiệu chuẩn theo chính điểm này)</div>
      {d.reproduce && <div><b>Chạy lại:</b> <span style={{ fontFamily: "monospace" }}>{d.reproduce.verify_api}</span></div>}
      <div style={{ color: "var(--dim, #66716a)", marginTop: 2 }}>🔏 {d.lineage_short}</div>
    </div>
  );
}

// H4 — nhãn + màu cho kết quả mỗi cảnh báo trong dòng thời gian thửa.
const OUTCOME: Record<string, [string, string]> = {
  hit: ["✓ báo đúng", "var(--ok, #3ecb83)"],
  false_alarm: ["✗ báo bừa", "var(--bad, #e5705a)"],
  miss: ["⚠ bỏ sót", "var(--clay, #a0522c)"],
  pending: ["⏳ đang chờ chấm", "var(--dim, #66716a)"],
  expired: ["— hết hạn", "var(--dim, #66716a)"],
};

export default function PlotHistory({ plotId }: { plotId: number }) {
  const [tl, setTl] = useState<PlotTimeline | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lineageOf, setLineageOf] = useState<number | null>(null);   // A5
  useEffect(() => {
    let live = true;
    getPlotTimeline(plotId)
      .then((d) => live && setTl(d))
      .catch((e) => live && setErr((e as Error).message));
    return () => { live = false; };
  }, [plotId]);

  if (err) return <p className="pf-err" style={{ margin: "4px 0 10px" }}>{err}</p>;
  if (!tl) return <p className="pf-empty" style={{ margin: "4px 0 10px" }}>Đang tải lịch sử…</p>;

  return (
    <div style={{
      margin: "0 0 10px", padding: "8px 12px",
      background: "var(--surface-2, #f8faf7)", borderRadius: 6,
      border: "1px solid var(--line, #e8ece8)",
    }}>
      <p style={{ fontSize: 11.5, color: "var(--dim, #66716a)", margin: 0 }}>
        Đang trông coi từ {new Date(tl.watching_since).toLocaleDateString("vi-VN")}
        {" · "}<b style={{ color: "var(--ok, #3ecb83)" }}>{tl.tally.hit ?? 0} đúng</b>
        {" · "}<b style={{ color: "var(--clay, #a0522c)" }}>{tl.tally.miss ?? 0} sót</b>
        {" · "}<b style={{ color: "var(--bad, #e5705a)" }}>{tl.tally.false_alarm ?? 0} bừa</b>
        {" · "}{tl.tally.pending ?? 0} chờ
      </p>
      {tl.events.length === 0 ? (
        <p className="pf-empty" style={{ margin: "6px 0 0" }}>
          Chưa có cảnh báo nào cho thửa này trong {tl.window_days} ngày qua.
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
          {tl.events.map((e) => {
            const [lbl, color] = OUTCOME[e.outcome ?? "pending"] ?? OUTCOME.pending;
            return (
              <li key={e.alert_id} style={{ borderLeft: `2px solid ${color}`, paddingLeft: 9, margin: "8px 0" }}>
                <div style={{ fontSize: 11, color: "var(--dim, #66716a)" }}>
                  {new Date(e.at).toLocaleDateString("vi-VN")} · {e.module_id}
                  {!e.was_warned && (
                    <b style={{ color: "var(--clay, #a0522c)" }}> · HỒI CỨU (phần mềm đã bỏ sót)</b>
                  )}
                </div>
                <div style={{ fontSize: 13 }}>{e.headline}</div>
                <span style={{ fontSize: 11, fontWeight: 700, color }}>{lbl}</span>
                {e.verify_note && (
                  <span style={{ fontSize: 11, color: "var(--dim, #66716a)" }}> — {e.verify_note}</span>
                )}
                <button
                  onClick={() => setLineageOf(lineageOf === e.alert_id ? null : e.alert_id)}
                  style={{ display: "block", marginTop: 3, padding: 0, border: "none",
                    background: "none", cursor: "pointer", fontSize: 11,
                    color: "var(--terra, #1f5137)", fontWeight: 600 }}>
                  🔍 {lineageOf === e.alert_id ? "ẩn nguồn gốc" : "nguồn gốc & cách kiểm chứng"}
                </button>
                {lineageOf === e.alert_id && <LineageView alertId={e.alert_id} />}
              </li>
            );
          })}
        </ul>
      )}
      {tl.questions.length > 0 && (
        <p className="pf-empty" style={{ margin: "8px 0 0", color: "var(--clay, #a0522c)" }}>
          📩 {tl.questions.length} câu đang chờ bạn xác nhận — mở thửa (bấm vào để phân tích) để trả lời.
        </p>
      )}
    </div>
  );
}
