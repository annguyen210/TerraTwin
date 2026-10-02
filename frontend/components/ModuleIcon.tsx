/**
 * Icon NÉT cho 18 mô-đun — thay emoji.
 *
 * Vì sao: emoji hiện khác nhau trên mỗi máy (Windows / Android / iOS vẽ khác hẳn),
 * và bốn mô-đun hạn hán, sâu bệnh, năng suất, xâm nhập mặn từng dùng CHUNG một
 * emoji 🌾 — người dùng không phân biệt được. Mỗi mô-đun nay có một hình riêng,
 * cùng nét, cùng cỡ, đổi màu theo chữ (currentColor) nên hợp cả hai theme.
 * Mô-đun lạ (thêm sau này) rơi về emoji backend gửi, không vỡ giao diện.
 */
import {
  Building2, Bug, Construction, DropletOff, Droplets, Fish, Flame, House, Link2,
  Mountain, MountainSnow, Pickaxe, ShieldCheck, Sun, Tornado, TreePine, Waves, Wheat,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  flood: Waves,
  upstream_flood: MountainSnow,
  landslide: Mountain,
  drought: DropletOff,
  salinity: Droplets,
  wildfire: Flame,
  pest: Bug,
  yield: Wheat,
  carbon: TreePine,
  aquaculture: Fish,
  storm_damage: Tornado,
  land_risk: House,
  illegal_build: Construction,
  parametric_insurance: ShieldCheck,
  solar: Sun,
  urban: Building2,
  mining: Pickaxe,
  supply_chain: Link2,
};

export default function ModuleIcon({ id, fallback, size = 16 }: {
  id: string; fallback?: string; size?: number;
}) {
  const I = ICONS[id];
  if (!I) return <span aria-hidden="true">{fallback}</span>;
  return <I size={size} strokeWidth={1.9} aria-hidden="true" className="mod-ic" />;
}
