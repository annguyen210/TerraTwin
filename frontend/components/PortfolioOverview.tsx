"use client";

/**
 * C08 — nhìn cả danh mục như một VÙNG, không phải một danh sách.
 *
 * Hợp tác xã 200 thửa không hỏi "thửa số 137 thế nào". Họ hỏi "vụ này chỗ nào
 * của tôi sắp gãy" — nên thứ hiện lên trước phải là VÙNG nặng nhất, rồi mới
 * tới từng thửa. Danh sách phẳng giao lại đúng việc mà phần mềm lẽ ra phải làm.
 */

import { useCallback, useState } from "react";
import {
  getPortfolioOverview, type AuthUser, type PortfolioOverview as PO,
} from "@/lib/api";

const COLOR: Record<string, string> = {
  danger: "#C2412E",
  warning: "#B07A2E",
  safe: "#2E9E67",
  unknown: "#7E8D84",
};
const LABEL: Record<string, string> = {
  danger: "nguy hiểm",
  warning: "cảnh báo",
  safe: "an toàn",
  unknown: "chưa rõ",
};

export default function PortfolioOverview({
  user,
  onOpen,
}: {
  user: AuthUser | null;
  onOpen?: (lat: number, lon: number) => void;
}) {
  const [d, setD] = useState<PO | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      setD(await getPortfolioOverview());
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  if (!user) {
    return (
      <p className="ws-hint">
        Đăng nhập để xem toàn cảnh danh mục — vùng nào trong số thửa của bạn
        đang gặp rủi ro nặng nhất.
      </p>
    );
  }

  return (
    <>
      <p className="ws-sub">
        Quét đồng thời mọi thửa đã lưu rồi gộp theo vùng ~11 km. Chỉ tính những
        mô-đun <b>thật sự là mối đe doạ</b> và <b>có dữ liệu thật</b> — tiềm
        năng điện mặt trời kém không phải rủi ro cho mảnh đất, và “chưa đủ dữ
        liệu” không phải một đánh giá.
      </p>

      <button className="ws-row-btn" disabled={busy} onClick={run}>
        {busy ? "Đang quét cả danh mục…" : "Quét toàn cảnh danh mục"}
      </button>

      {err && <p className="ws-err">⚠️ {err}</p>}
      {d && !d.available && <p className="ws-hint">{d.message}</p>}

      {d?.available && (
        <>
          <p className="po-head">{d.headline}</p>

          <div className="po-counts">
            {(["danger", "warning", "safe", "unknown"] as const).map((k) => (
              <div key={k} className="po-count">
                <b style={{ color: COLOR[k] }}>{d.counts?.[k] ?? 0}</b>
                <span>{LABEL[k]}</span>
              </div>
            ))}
            <div className="po-count">
              <b>{d.at_risk_ha}</b>
              <span>ha rủi ro / {d.total_ha} ha</span>
            </div>
          </div>

          <div className="po-sec">Vùng — nặng nhất trước</div>
          {d.cells?.map((c) => (
            <div key={c.cell} className="po-cell">
              <div className="po-cell-bar">
                <i
                  style={{
                    width: `${c.at_risk_pct}%`,
                    background: c.danger ? COLOR.danger : COLOR.warning,
                  }}
                />
              </div>
              <div className="po-cell-txt">
                <b>{c.cell}</b>
                <span>
                  {c.plots} thửa · {c.area_ha} ha · rủi ro {c.at_risk_pct}%
                  {c.top_driver && ` · chủ yếu do ${c.top_driver}`}
                </span>
              </div>
            </div>
          ))}

          <div className="po-sec">Từng thửa</div>
          {d.plots?.map((p) => (
            <div key={p.plot_id} className="po-plot">
              <button
                className="po-plot-h"
                onClick={() => onOpen?.(p.lat, p.lon)}
                title="Mở thửa này trên bản đồ"
              >
                <i style={{ background: COLOR[p.risk_level] }} />
                <b>{p.name}</b>
                <span className="po-plot-m">
                  {p.area_ha != null && `${p.area_ha} ha · `}
                  {p.score != null && `TerraScore ${p.score} (${p.grade})`}
                </span>
              </button>
              {p.drivers.length > 0 && (
                <div className="po-drivers">
                  {p.drivers.map((dr) => (
                    <span key={dr.id} style={{ color: COLOR[dr.risk_level] }}>
                      {dr.icon} {dr.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}

          <p className="ws-note">{d.method}</p>
          <p className="ws-note">{d.caveat}</p>
        </>
      )}
    </>
  );
}
