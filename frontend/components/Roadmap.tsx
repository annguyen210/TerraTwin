"use client";

/**
 * Trang trạng thái 26 luồng + trạng thái ảnh vệ tinh.
 *
 * VÌ SAO ĐỂ NGƯỜI DÙNG XEM ĐƯỢC: bảng này sinh từ mã nguồn nên không thể lệch
 * với phần mềm. Công khai nó là cách rẻ nhất để chứng minh những gì phần mềm
 * nói về chính nó là thật — và cũng là ràng buộc tự đặt lên mình, vì mọi luồng
 * ghi "xong" đều đang bị người dùng nhìn.
 */

import { useEffect, useState } from "react";
import {
  getRoadmap, getSatellite,
  type Roadmap as RoadmapData, type SatelliteStatus,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

const DOT: Record<string, { c: string; vi: string; en: string }> = {
  done: { c: "#5fcb8e", vi: "chạy thật", en: "live" },
  partial: { c: "#B07A2E", vi: "một phần", en: "partial" },
  blocked: { c: "#C2412E", vi: "bị chặn", en: "blocked" },
  declined: { c: "#7d8ea0", vi: "từ chối vì nguyên tắc", en: "declined on principle" },
};

export default function Roadmap() {
  const { t } = useLang();
  const [d, setD] = useState<RoadmapData | null>(null);
  const [sat, setSat] = useState<SatelliteStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getRoadmap().then(setD).catch((e) => setErr(e.message));
    getSatellite().then(setSat).catch(() => setSat(null));
  }, []);

  if (err) return <p className="ws-err">⚠️ {err}</p>;
  if (!d) return <p className="ws-hint">{t("Đang tải…", "Loading…")}</p>;

  const tiers = ["signature", "core", "upgrade"] as const;

  return (
    <>
      <p className="rm-head">{d.headline}</p>

      <div className="rm-tiers">
        {tiers.map((tier) => {
          const v = d.by_tier[tier];
          if (!v) return null;
          return (
            <div key={tier} className="rm-tier">
              <span>{v.name}</span>
              <b>{v.live}/{v.total}</b>
            </div>
          );
        })}
      </div>

      {sat && (
        <div className={`rm-sat ${sat.configured ? "on" : "off"}`}>
          <b>{sat.configured ? t("🛰️ Ảnh vệ tinh đã nối", "🛰️ Satellite imagery connected")
                             : t("🛰️ Chưa nối ảnh vệ tinh", "🛰️ Satellite imagery not connected")}</b>
          <p>{sat.message}</p>
          {!sat.configured && (
            <p className="ws-note">
              {t(`Nối vào sẽ mở khoá ${sat.unlocks.length} mũi nhọn đang trả “chưa đủ dữ liệu”: ${sat.unlocks.join(", ")}.`,
                 `Connecting it unlocks ${sat.unlocks.length} spearheads currently returning "not enough data": ${sat.unlocks.join(", ")}.`)}
            </p>
          )}
        </div>
      )}

      {d.sectors && (
        <div className="rm-sectors">
          <b>
            {t(`${d.sectors.covered}/${d.sectors.planned} ngành có mũi nhọn`,
               `${d.sectors.covered}/${d.sectors.planned} sectors have a spearhead`)}
            {d.modules && t(` · ${d.modules.total} mũi nhọn (${d.modules.active} chạy ngay`,
                            ` · ${d.modules.total} spearheads (${d.modules.active} live now`)}
            {d.modules?.awaiting_satellite
              ? t(`, ${d.modules.awaiting_satellite} chờ khoá vệ tinh)`,
                  `, ${d.modules.awaiting_satellite} awaiting satellite key)`)
              : d.modules && ")"}
          </b>
          <p>{d.sectors.note}</p>
        </div>
      )}

      {d.principles && (
        <section className="rm-sec">
          <h3>{t("4 nguyên lý bắt buộc", "4 mandatory principles")}</h3>
          {d.principles.map((p) => (
            <div key={p.name} className="rm-flow">
              <div className="rm-flow-h">
                <i style={{ background: DOT[p.status]?.c ?? "#9fb2bf" }} />
                <b>{p.name}</b>
                <span className="rm-st">{t(DOT[p.status]?.vi ?? p.status, DOT[p.status]?.en ?? p.status)}</span>
              </div>
              <p className="rm-note">{p.note}</p>
            </div>
          ))}
        </section>
      )}

      {tiers.map((tier) => (
        <section key={tier} className="rm-sec">
          <h3>{d.by_tier[tier]?.name}</h3>
          {d.flows
            .filter((f) => f.tier === tier)
            .map((f) => (
              <div key={f.id} className="rm-flow">
                <div className="rm-flow-h">
                  <i style={{ background: DOT[f.status]?.c ?? "#9fb2bf" }} />
                  <code>{f.id}</code>
                  <b>{f.name}</b>
                  <span className="rm-st">
                    {f.awaiting_config ? t("chờ khoá", "awaiting key")
                                       : t(DOT[f.status]?.vi ?? f.status, DOT[f.status]?.en ?? f.status)}
                  </span>
                </div>
                <p className="rm-note">{f.note}</p>
                {f.awaiting_note && (
                  <p className="rm-wait">⏳ {f.awaiting_note}</p>
                )}
              </div>
            ))}
        </section>
      ))}

      <p className="ws-note">{d.honesty_note}</p>
    </>
  );
}
