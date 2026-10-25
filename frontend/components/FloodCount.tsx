"use client";

/**
 * Lịch sử ngập radar CẠNH điểm hiểm hoạ 7 ngày (kiểm 24/10/2026, việc 2): Quảng Điền hiện "100/100 hạng A" trong embed
 * và danh mục dù có 7 đợt nước trong mùa lũ — điểm chỉ nói về 7 ngày tới. Mọi chỗ hiện điểm dùng chung nhãn và dòng này.
 * Số đợt lấy từ bộ nhớ đệm máy chủ (GET /api/water/summary) — không chạy radar; chưa đọc thì nói "chưa đọc".
 */
import { useEffect, useState } from "react";
import { waterSummary, type WaterSummary } from "@/lib/api";

type T = (vi: string, en: string) => string;

/** Nhãn đặt NGAY trên/cạnh con số điểm. */
export function hazardScope(t: T): string {
  return t("Hiểm hoạ 7 ngày tới — không phải lịch sử ngập", "Next-7-day hazards — not flood history");
}

/** Một dòng: "Lịch sử ngập radar 2017–nay: 7 đợt (7 trong mùa lũ)" | "0 đợt" | "chưa đọc". */
export function floodLine(s: WaterSummary | null | undefined, t: T): string {
  if (!s || !s.cached) return t("Lịch sử ngập radar: chưa đọc — mở thửa để đọc", "Radar flood history: not read yet — open the plot");
  if (!s.available) return t("Lịch sử ngập radar: không đọc được ở thửa này", "Radar flood history: unavailable for this plot");
  const y = s.first ? s.first.slice(0, 4) : "2017";
  const n = s.n_events ?? 0;
  const season = n > 0 && s.n_in != null ? t(` (${s.n_in} trong mùa lũ)`, ` (${s.n_in} in flood season)`) : "";
  return t(`Lịch sử ngập radar ${y}–nay: ${n} đợt${season}`, `Radar flood history ${y}–now: ${n} event${n === 1 ? "" : "s"}${season}`);
}

/** Tóm tắt cho nhiều thửa một lần; khoá "lat,lon" làm tròn 4 chữ số như bộ nhớ đệm máy chủ. */
export function floodKey(lat: number, lon: number): string {
  return `${lat.toFixed(4)},${lon.toFixed(4)}`;
}

/** null = đang tải, lịch sử nước chưa bật hoặc lỗi mạng → nơi gọi KHÔNG hiện dòng (không nói "chưa đọc" sai). */
export function useFloodSummaries(points: { lat: number; lon: number }[]): Map<string, WaterSummary> | null {
  const [m, setM] = useState<Map<string, WaterSummary> | null>(null);
  const sig = [...new Set(points.map((p) => floodKey(p.lat, p.lon)))].join(";");
  useEffect(() => {
    setM(null);
    if (!sig) return;
    let live = true;
    const pts = sig.split(";").map((k) => { const [a, b] = k.split(","); return { lat: Number(a), lon: Number(b) }; });
    const chunks: (typeof pts)[] = [];
    for (let i = 0; i < pts.length; i += 50) chunks.push(pts.slice(i, i + 50));     // máy chủ nhận tối đa 50 thửa/lần
    Promise.all(chunks.map((c) => waterSummary(c)))
      .then((rs) => {
        if (!live) return;
        setM(rs.every((r) => r.enabled) ? new Map(rs.flatMap((r) => r.items).map((s) => [floodKey(s.lat, s.lon), s])) : null);
      })
      .catch(() => live && setM(null));
    return () => { live = false; };
  }, [sig]);
  return m;
}
