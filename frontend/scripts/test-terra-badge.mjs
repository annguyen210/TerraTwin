// Thẻ "7 ngày tới" (lib/terraBadge.ts) — kiểm A–Z lần 2, 22/11/2026: lũ thượng nguồn NGUY HIỂM mà thẻ vẫn "yên".
import assert from "node:assert/strict";
import { probTone } from "../lib/riskScale.ts";
import { badgeHead, isForecast, observedLine } from "../lib/terraBadge.ts";

const vi = (v) => v;
// 5 hiểm hoạ thời tiết đều yên (hạng A) + lũ từ thượng nguồn NGUY HIỂM → đỏ, có "NGUY HIỂM", không "yên"
let [color, head] = badgeHead({ grade: "A", other_threats: [{ id: "upstream_flood", name: "Lũ từ thượng nguồn", risk_level: "danger" }] }, vi);
assert.equal(color, "#C2412E"); assert.equal(head, "7 ngày tới: có mối NGUY HIỂM — lũ từ thượng nguồn"); assert.ok(!head.includes("yên"));
// chỉ cảnh báo → "cần để ý"
[color, head] = badgeHead({ grade: "A", other_threats: [{ id: "upstream_flood", name: "Lũ từ thượng nguồn", risk_level: "warning" }] }, vi);
assert.equal(head, "7 ngày tới: cần để ý — lũ từ thượng nguồn"); assert.ok(!head.includes("yên"));
// không có mối nào khác → như cũ
assert.equal(badgeHead({ grade: "A" }, vi)[1], "7 ngày tới: yên");
assert.equal(badgeHead({ grade: "B", other_threats: [] }, vi)[1], "7 ngày tới: có vài điều cần theo dõi");

// Kiểm A–Z lần 3 (Huế 16.52,107.59): sâu bệnh từ ảnh (QUAN SÁT) không lên "7 ngày tới"; lũ CẢNH BÁO thì không "yên".
const pest = { id: "pest", name: "Phát hiện sâu bệnh sớm", risk_level: "danger" };
[color, head] = badgeHead({ grade: "A", other_threats: [pest] }, vi);           // bản quét cũ còn pest trong other_threats
assert.equal(head, "7 ngày tới: yên"); assert.ok(!head.includes("sâu bệnh"));
[color, head] = badgeHead({ grade: "A", hazard_alerts: [{ id: "flood", name: "Cảnh báo lũ/ngập sớm", risk_level: "warning" }] }, vi);
assert.equal(head, "7 ngày tới: cần để ý — cảnh báo lũ/ngập sớm"); assert.ok(!head.includes("yên"));
const obs = observedLine({ observed_threats: [{ ...pest, kind: "observed", headline: "NDVI 0.18, ảnh ngày 2026-11-15" }] }, vi);
assert.ok(obs.startsWith("Quan sát, không phải dự báo: Phát hiện sâu bệnh sớm — NDVI 0.18, ảnh ngày 2026-11-15"));
assert.ok(!obs.includes("7 ngày tới"));
assert.equal(observedLine({}, vi), null);
assert.ok(isForecast("upstream_flood") && isForecast("flood") && !isForecast("pest") && !isForecast("mining"));
console.log("OK — thẻ 7 ngày tới: chỉ mối DỰ BÁO; sâu bệnh/mỏ là dòng quan sát riêng; hiểm hoạ cảnh báo thì không 'yên'.");
// Màu xác suất (Insights): 0% không được đỏ (23/11/2026); cùng ngưỡng với "Xác suất 7 ngày tới".
assert.equal(probTone(0), "#2E9E67"); assert.equal(probTone(19.9), "#2E9E67");
assert.equal(probTone(20), "#B07A2E"); assert.equal(probTone(49), "#B07A2E");
assert.equal(probTone(50), "#C2412E"); assert.equal(probTone(null), "#2E9E67");
console.log("OK — màu xác suất: 0% xanh, ≥20% cam, ≥50% đỏ.");
