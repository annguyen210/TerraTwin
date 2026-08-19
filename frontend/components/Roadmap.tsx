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

const DOT: Record<string, { c: string; t: string }> = {
  done: { c: "#5fcb8e", t: "chạy thật" },
  partial: { c: "#B07A2E", t: "một phần" },
  blocked: { c: "#C2412E", t: "bị chặn" },
};

export default function Roadmap() {
  const [d, setD] = useState<RoadmapData | null>(null);
  const [sat, setSat] = useState<SatelliteStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getRoadmap().then(setD).catch((e) => setErr(e.message));
    getSatellite().then(setSat).catch(() => setSat(null));
  }, []);

  if (err) return <p className="ws-err">⚠️ {err}</p>;
  if (!d) return <p className="ws-hint">Đang tải…</p>;

  const tiers = ["signature", "core", "upgrade"] as const;

  return (
    <>
      <p className="rm-head">{d.headline}</p>

      <div className="rm-tiers">
        {tiers.map((t) => {
          const v = d.by_tier[t];
          if (!v) return null;
          return (
            <div key={t} className="rm-tier">
              <span>{v.name}</span>
              <b>{v.live}/{v.total}</b>
            </div>
          );
        })}
      </div>

      {sat && (
        <div className={`rm-sat ${sat.configured ? "on" : "off"}`}>
          <b>{sat.configured ? "🛰️ Ảnh vệ tinh đã nối" : "🛰️ Chưa nối ảnh vệ tinh"}</b>
          <p>{sat.message}</p>
          {!sat.configured && (
            <p className="ws-note">
              Nối vào sẽ mở khoá {sat.unlocks.length} mũi nhọn đang trả “chưa đủ
              dữ liệu”: {sat.unlocks.join(", ")}.
            </p>
          )}
        </div>
      )}

      {d.sectors && (
        <div className="rm-sectors">
          <b>
            {d.sectors.covered}/{d.sectors.planned} ngành có mũi nhọn
            {d.modules && ` · ${d.modules.total} mũi nhọn (${d.modules.active} chạy ngay`}
            {d.modules?.awaiting_satellite
              ? `, ${d.modules.awaiting_satellite} chờ khoá vệ tinh)`
              : d.modules && ")"}
          </b>
          <p>{d.sectors.note}</p>
        </div>
      )}

      {d.principles && (
        <section className="rm-sec">
          <h3>4 nguyên lý bắt buộc</h3>
          {d.principles.map((p) => (
            <div key={p.name} className="rm-flow">
              <div className="rm-flow-h">
                <i style={{ background: DOT[p.status]?.c ?? "#9fb2bf" }} />
                <b>{p.name}</b>
                <span className="rm-st">{DOT[p.status]?.t ?? p.status}</span>
              </div>
              <p className="rm-note">{p.note}</p>
            </div>
          ))}
        </section>
      )}

      {tiers.map((t) => (
        <section key={t} className="rm-sec">
          <h3>{d.by_tier[t]?.name}</h3>
          {d.flows
            .filter((f) => f.tier === t)
            .map((f) => (
              <div key={f.id} className="rm-flow">
                <div className="rm-flow-h">
                  <i style={{ background: DOT[f.status]?.c ?? "#9fb2bf" }} />
                  <code>{f.id}</code>
                  <b>{f.name}</b>
                  <span className="rm-st">
                    {f.awaiting_config ? "chờ khoá" : DOT[f.status]?.t}
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
