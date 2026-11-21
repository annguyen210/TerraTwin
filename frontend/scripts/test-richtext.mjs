// Test lib/richtext.ts — kiểm 21/11/2026: câu trả lời trợ lý không được lộ "**" trên màn hình.
import assert from "node:assert/strict";
import { boldParts } from "../lib/richtext.ts";

const s = "Thửa này đã có **5 đợt** nước phủ … và **15 đợt** điều kiện thời tiết ERA5.";
const p = boldParts(s);
assert.deepEqual(p.filter((x) => x.bold).map((x) => x.text), ["5 đợt", "15 đợt"]);
assert.ok(!p.map((x) => x.text).join("").includes("**"));
assert.equal(p.map((x) => x.text).join(""), "Thửa này đã có 5 đợt nước phủ … và 15 đợt điều kiện thời tiết ERA5.");
// dấu ** lẻ và tiêu đề markdown bị bỏ, chữ thường giữ nguyên
assert.equal(boldParts("## Kết luận\nmưa **nhiều").map((x) => x.text).join(""), "Kết luận\nmưa nhiều");
assert.deepEqual(boldParts("không có định dạng"), [{ text: "không có định dạng", bold: false }]);
console.log("OK — chữ đậm của trợ lý vẽ bằng phần tử React, không còn lộ **.");
