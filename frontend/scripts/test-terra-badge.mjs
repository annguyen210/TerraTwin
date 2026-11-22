// Thẻ "7 ngày tới" (lib/terraBadge.ts) — kiểm A–Z lần 2, 22/11/2026: lũ thượng nguồn NGUY HIỂM mà thẻ vẫn "yên".
import assert from "node:assert/strict";
import { badgeHead } from "../lib/terraBadge.ts";

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
console.log("OK — thẻ 7 ngày tới: mối NGUY HIỂM ngoài 5 hiểm hoạ thời tiết đi trước hạng, không còn 'yên' nhầm.");
