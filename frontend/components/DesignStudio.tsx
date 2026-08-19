"use client";

/**
 * U03 Generative Design Studio — trồng gì trên thửa này, làm hạ tầng nào trước.
 *
 * Mỗi lựa chọn hiện KÈM lý do cộng và lý do trừ. Chấm điểm mà không nói vì sao
 * thì người dùng không có cách nào kiểm chứng, và một khuyến nghị không kiểm
 * chứng được thì đúng bằng lời phán của người lạ ngoài chợ.
 */

import { useState } from "react";
import { runDesign, type DesignResult } from "@/lib/api";

const PRIO: Record<string, string> = {
  cao: "#C2412E",
  "trung bình": "#B07A2E",
  thấp: "#5fcb8e",
};

export default function DesignStudio({ lat, lon }: { lat: number; lon: number }) {
  const [data, setData] = useState<DesignResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const d = await runDesign(lat, lon);
      setData(d);
      setOpen(d.recommended.code);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pan">
      <div className="pan-head">🎨 Phương án canh tác — trồng gì, làm gì trước</div>

      {!data && (
        <>
          <p className="pan-sub">
            Tổng hợp phương án từ chính các ràng buộc đo được của thửa: cao độ,
            độ dốc, mặn đỉnh, khoảng cách biển, mưa năm, nhiệt.
          </p>
          <button className="pan-go" disabled={busy} onClick={run}>
            {busy ? "Đang tổng hợp…" : "Sinh phương án"}
          </button>
        </>
      )}

      {err && <p className="pan-err">⚠️ {err}</p>}

      {data && (
        <>
          <p className="pan-line">{data.headline}</p>

          <div className="ds-opts">
            {data.options.map((o) => {
              const isOpen = open === o.code;
              return (
                <div key={o.code} className={`ds-opt ${isOpen ? "on" : ""}`}>
                  <button
                    className="ds-opt-head"
                    onClick={() => setOpen(isOpen ? null : o.code)}
                  >
                    <span className="ds-ic">{o.icon}</span>
                    <span className="ds-nm">{o.name}</span>
                    <span className="ds-score">{o.score}</span>
                    <span className="ds-bar">
                      <i style={{ width: `${o.score}%` }} />
                    </span>
                  </button>
                  {isOpen && (
                    <div className="ds-why">
                      {o.reasons.map((r, i) => (
                        <div key={`r${i}`} className="ds-plus">
                          ✓ {r}
                        </div>
                      ))}
                      {o.warnings.map((w, i) => (
                        <div key={`w${i}`} className="ds-minus">
                          ✕ {w}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="ds-infra-h">Hạ tầng nên làm, theo thứ tự</div>
          {data.infrastructure.map((it, i) => (
            <div key={i} className="ds-infra">
              <span className="ds-prio" style={{ color: PRIO[it.priority] ?? "#9fb2bf" }}>
                {it.priority}
              </span>
              <div>
                <b>{it.item}</b>
                <p>{it.why}</p>
              </div>
            </div>
          ))}

          <p className="pan-method">{data.generative_note}</p>
          <p className="pan-caveat">{data.caveat}</p>
          <button className="pan-ghost" onClick={run} disabled={busy}>
            Chạy lại
          </button>
        </>
      )}
    </div>
  );
}
