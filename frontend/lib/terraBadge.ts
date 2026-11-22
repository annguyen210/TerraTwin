// Chữ to + màu của thẻ "7 ngày tới" (components/TerraBadge.tsx). Hàm thuần để test được bằng Node.
// Kiểm A–Z lần 2 (22/11/2026): lượt quét sâu có lũ từ thượng nguồn NGUY HIỂM mà thẻ vẫn "7 ngày tới: yên" — chữ to chọn
// theo grade (chỉ chấm 5 hiểm hoạ thời tiết). Mối đe doạ khác (other_threats) đi TRƯỚC grade.
import type { TerraScore } from "./api";

type Tr = (vi: string, en: string) => string;

export function badgeHead(t: Pick<TerraScore, "grade" | "other_threats">, tr: Tr): [string, string] {
  const ot = t.other_threats ?? [];
  const dn = ot.filter((x) => x.risk_level === "danger"), wn = ot.filter((x) => x.risk_level === "warning");
  const ten = (xs: typeof ot) => xs.map((x) => x.name.charAt(0).toLowerCase() + x.name.slice(1)).join(", ");
  if (dn.length) return ["#C2412E", tr(`7 ngày tới: có mối NGUY HIỂM — ${ten(dn)}`, `Next 7 days: DANGER — ${ten(dn)}`)];
  if (wn.length && t.grade !== "D") return ["#B07A2E", tr(`7 ngày tới: cần để ý — ${ten(wn)}`, `Next 7 days: watch closely — ${ten(wn)}`)];
  // Đúng thang của services/terrascore.py: chỉ A là "thấp"; B = "có vài mối cần theo dõi" — không gọi B là "yên" (kiểm lại 7/11).
  if (t.grade === "A") return ["#2E9E67", tr("7 ngày tới: yên", "Next 7 days: calm")];
  if (t.grade === "B") return ["#3aa0a0", tr("7 ngày tới: có vài điều cần theo dõi", "Next 7 days: a few things to watch")];
  if (t.grade === "C") return ["#B07A2E", tr("7 ngày tới: cần để ý", "Next 7 days: watch closely")];
  return ["#C2412E", tr("7 ngày tới: nguy cơ cao", "Next 7 days: high risk")];
}
