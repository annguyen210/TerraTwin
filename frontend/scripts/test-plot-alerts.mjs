// Danh sách thửa chỉ dùng cảnh báo CÒN HIỆU LỰC, mức theo lượt rà soát gần nhất (lib/terraBadge.ts) — quét 23/11/2026.
import assert from "node:assert/strict";
import { headOf, levelOf, observedFor, worstForecast } from "../lib/terraBadge.ts";

const row = (o) => ({ id: 1, plot_id: 7, module_id: "upstream_flood", risk_level: "danger", headline: "Trà Leng: thượng nguồn 225.3 mm",
  recommendation: "", created_at: "2026-11-11T00:00:00", acknowledged: false, ...o });
// bản ghi NGUY HIỂM 11/11, lượt rà soát mới chỉ CẢNH BÁO → "cần để ý", không "NGUY HIỂM"
const a = row({ current: true, current_level: "warning", current_headline: "Trà Leng: thượng nguồn 120 mm" });
const w = worstForecast([a], 7);
assert.equal(levelOf(w), "warning"); assert.ok(!headOf(w).includes("225.3"));
assert.equal(worstForecast([a], 8), null);
// sâu bệnh / mỏ: không vào "7 ngày tới"; "Quan sát:" gộp theo mô-đun
const pest = (id) => row({ id, module_id: "pest", risk_level: "warning", headline: "Lai Châu: NDVI giảm, ảnh ngày 2026-11-15" });
assert.equal(worstForecast([pest(2), pest(3)], 7), null);
assert.deepEqual(observedFor([pest(2), pest(3), pest(4), pest(5), pest(6)], 7), ["NDVI giảm, ảnh ngày 2026-11-15"]);
console.log("OK — danh sách thửa: mức theo lượt rà soát gần nhất, 'Quan sát:' gộp theo mô-đun.");
