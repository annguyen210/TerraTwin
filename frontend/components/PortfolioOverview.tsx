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
import { useLang } from "@/lib/i18n";

const COLOR: Record<string, string> = {
  danger: "#C2412E",
  warning: "#B07A2E",
  safe: "#2E9E67",
  unknown: "#7E8D84",
};
const LABEL: Record<string, [string, string]> = {
  danger: ["nguy hiểm", "danger"],
  warning: ["cảnh báo", "warning"],
  safe: ["an toàn", "safe"],
  unknown: ["chưa rõ", "unknown"],
};

export default function PortfolioOverview({
  user,
  onOpen,
}: {
  user: AuthUser | null;
  onOpen?: (lat: number, lon: number) => void;
}) {
  const { t } = useLang();
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
        {t("Đăng nhập để xem toàn cảnh danh mục — vùng nào trong số thửa của bạn đang gặp rủi ro nặng nhất.",
           "Log in to see your portfolio overview — which of your plots is facing the heaviest risk.")}
      </p>
    );
  }

  return (
    <>
      <p className="ws-sub">
        {t("Quét đồng thời mọi thửa đã lưu rồi gộp theo vùng ~11 km. Chỉ tính những mô-đun ", "Scans every saved plot at once and groups them into ~11 km cells. Only counts modules that are ")}
        <b>{t("thật sự là mối đe doạ", "genuine threats")}</b>{t(" và ", " and ")}
        <b>{t("có dữ liệu thật", "backed by real data")}</b>
        {t(" — tiềm năng điện mặt trời kém không phải rủi ro cho mảnh đất, và “chưa đủ dữ liệu” không phải một đánh giá.",
           " — poor solar potential isn't a risk to the land, and \"not enough data\" isn't a verdict.")}
      </p>

      <button className="ws-row-btn" disabled={busy} onClick={run}>
        {busy ? t("Đang quét cả danh mục…", "Scanning the whole portfolio…") : t("Quét toàn cảnh danh mục", "Scan portfolio overview")}
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
                <span>{t(...LABEL[k])}</span>
              </div>
            ))}
            <div className="po-count">
              <b>{d.at_risk_ha}</b>
              <span>{t(`ha rủi ro / ${d.total_ha} ha`, `ha at risk / ${d.total_ha} ha`)}</span>
            </div>
          </div>

          <div className="po-sec">{t("Vùng — nặng nhất trước", "Zones — heaviest first")}</div>
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
                  {t(`${c.plots} thửa · ${c.area_ha} ha · rủi ro ${c.at_risk_pct}%`,
                     `${c.plots} plots · ${c.area_ha} ha · ${c.at_risk_pct}% at risk`)}
                  {c.top_driver && t(` · chủ yếu do ${c.top_driver}`, ` · mainly from ${c.top_driver}`)}
                </span>
              </div>
            </div>
          ))}

          <div className="po-sec">{t("Từng thửa", "Individual plots")}</div>
          {d.plots?.map((p) => (
            <div key={p.plot_id} className="po-plot">
              <button
                className="po-plot-h"
                onClick={() => onOpen?.(p.lat, p.lon)}
                title={t("Mở thửa này trên bản đồ", "Open this plot on the map")}
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
