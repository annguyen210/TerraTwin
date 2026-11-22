// Chữ to + màu của thẻ "7 ngày tới" (components/TerraBadge.tsx). Hàm thuần để test được bằng Node.
// Kiểm A–Z lần 2 (22/11/2026): lượt quét sâu có lũ từ thượng nguồn NGUY HIỂM mà thẻ vẫn "7 ngày tới: yên" — chữ to chọn
// theo grade (chỉ chấm 5 hiểm hoạ thời tiết). Mối đe doạ khác (other_threats) đi TRƯỚC grade.
// Kiểm A–Z lần 3 (22/11/2026): Huế — "phát hiện sâu bệnh sớm" (QUAN SÁT từ ảnh cũ) lên chữ đỏ "7 ngày tới: có mối NGUY
// HIỂM"; lũ CẢNH BÁO mà hạng A vẫn "yên". "7 ngày tới" chỉ nhận mối DỰ BÁO (5 hiểm hoạ thời tiết + FORECAST_THREATS, cùng
// danh sách với services/terrascore.py); mối quan sát / cố định đi một dòng riêng, nhỏ, không đỏ.
import type { TerraScore } from "./api";

type Tr = (vi: string, en: string) => string;

export const WEATHER_HAZARDS = ["salinity", "drought", "flood", "landslide", "wildfire"];
export const FORECAST_THREATS = ["upstream_flood", "aquaculture", "urban"];

/** Mối này có phải DỰ BÁO 7 ngày tới không (5 hiểm hoạ thời tiết hoặc mối dự báo khác). */
export function isForecast(moduleId: string): boolean {
  return WEATHER_HAZARDS.includes(moduleId) || FORECAST_THREATS.includes(moduleId);
}

type Threat = { id: string; name: string; risk_level: string };

export function badgeHead(t: Pick<TerraScore, "grade" | "other_threats" | "hazard_alerts">, tr: Tr): [string, string] {
  // Lọc lại ở giao diện: bản quét cũ (nhớ đệm) có thể còn sâu bệnh / mỏ trong other_threats.
  const ot: Threat[] = [...(t.other_threats ?? []).filter((x) => isForecast(x.id)), ...(t.hazard_alerts ?? [])];
  const dn = ot.filter((x) => x.risk_level === "danger"), wn = ot.filter((x) => x.risk_level === "warning");
  const ten = (xs: Threat[]) => xs.map((x) => x.name.charAt(0).toLowerCase() + x.name.slice(1)).join(", ");
  if (dn.length) return ["#C2412E", tr(`7 ngày tới: có mối NGUY HIỂM — ${ten(dn)}`, `Next 7 days: DANGER — ${ten(dn)}`)];
  if (wn.length && t.grade !== "D") return ["#B07A2E", tr(`7 ngày tới: cần để ý — ${ten(wn)}`, `Next 7 days: watch closely — ${ten(wn)}`)];
  // Đúng thang của services/terrascore.py: chỉ A là "thấp"; B = "có vài mối cần theo dõi" — không gọi B là "yên" (kiểm lại 7/11).
  if (t.grade === "A") return ["#2E9E67", tr("7 ngày tới: yên", "Next 7 days: calm")];
  if (t.grade === "B") return ["#3aa0a0", tr("7 ngày tới: có vài điều cần theo dõi", "Next 7 days: a few things to watch")];
  if (t.grade === "C") return ["#B07A2E", tr("7 ngày tới: cần để ý", "Next 7 days: watch closely")];
  return ["#C2412E", tr("7 ngày tới: nguy cơ cao", "Next 7 days: high risk")];
}

/** Dòng riêng cho mối QUAN SÁT / CỐ ĐỊNH (sâu bệnh từ ảnh vệ tinh, mỏ gần thửa) — không gắn "7 ngày tới". */
export function observedLine(t: Pick<TerraScore, "observed_threats" | "other_threats">, tr: Tr): string | null {
  const obs = [
    ...(t.observed_threats ?? []),
    ...(t.other_threats ?? []).filter((x) => !isForecast(x.id)).map((x) => ({ ...x, kind: "observed", headline: "" })),
  ];
  if (!obs.length) return null;
  const one = (o: { name: string; headline?: string; kind?: string }) =>
    `${o.name}${o.headline ? ` — ${o.headline}` : ""}`;
  return tr(`Quan sát, không phải dự báo: ${obs.map(one).join(" · ")}`, `Observed, not a forecast: ${obs.map(one).join(" · ")}`);
}
