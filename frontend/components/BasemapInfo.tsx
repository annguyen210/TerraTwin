"use client";

/**
 * Ảnh nền độ phân giải cao dưới thửa là ảnh THẬT (Esri World Imagery — Vantor/Maxar ~0,3 m), nhưng KHÔNG phải ảnh hôm nay.
 * Dòng này nói rõ ảnh chụp ngày nào, nét tới đâu, của ai — để không ai lấy ảnh cũ làm hiện trạng. Ảnh mới nhất về nước và
 * cây cối là radar/Sentinel ở các thẻ bên dưới (10 m, vài ngày một lần).
 */
import { useEffect, useState } from "react";
import { basemapMeta, type BasemapMeta } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function BasemapInfo({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [m, setM] = useState<BasemapMeta | null>(null);
  useEffect(() => {
    let live = true;
    setM(null);
    basemapMeta(lat, lon).then((x) => live && setM(x)).catch(() => {});
    return () => { live = false; };
  }, [lat, lon]);
  if (!m || !m.available) return null;
  const d = m.date ? new Date(m.date + "T00:00:00").toLocaleDateString(t("vi-VN", "en-GB")) : null;
  const res = m.resolution_m != null ? `${String(m.resolution_m).replace(".", t(",", "."))} m` : null;
  const old = (m.age_years ?? 0) >= 2;
  return (
    <p className={`pw-basemap${old ? " old" : ""}`}>
      {t("Ảnh nền", "Base image")}: {[m.source, res].filter(Boolean).join(" · ")}
      {d ? t(` · chụp ${d}`, ` · taken ${d}`) : t(" · không rõ ngày chụp", " · capture date unknown")}
      {old && t(` — đã ${m.age_years} năm, không phải hiện trạng`, ` — ${m.age_years} years old, not current`)}
      <span className="pw-basemap-src"> ({m.service})</span>
    </p>
  );
}
