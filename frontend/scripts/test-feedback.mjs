// Test phiếu góp ý (lib/feedback.ts) — kiểm A–Z 21/11/2026: phiếu cũ đặt sẵn "sẽ dùng" + "không có chỗ khó".
import assert from "node:assert/strict";
import { blankFeedback, missingFields, missingMessage, toSubmit } from "../lib/feedback.ts";

const t = (vi) => vi;

// 1) phiếu trống: KHÔNG có đáp án nào chọn sẵn
const b = blankFeedback("buyer");
assert.equal(b.would_use, ""); assert.equal(b.hardest, ""); assert.equal(b.ease, 0); assert.equal(b.trust, 0);

// 2) chỉ chấm hai câu điểm → vẫn thiếu "có dùng không" + "chỗ khó nhất", không gửi được
const hai = { ...b, ease: 4, trust: 5 };
assert.deepEqual(missingFields(hai), ["would_use", "hardest"]);
assert.equal(toSubmit(hai), null);
assert.match(missingMessage(missingFields(hai), t), /có dùng không.*chỗ khó nhất/);

// 3) chọn đủ → gửi được, đúng giá trị người chọn (không điền hộ)
const du = { ...hai, would_use: "no", hardest: "water" };
assert.deepEqual(missingFields(du), []);
assert.deepEqual([toSubmit(du).would_use, toSubmit(du).hardest], ["no", "water"]);

// 4) có liên hệ mà chưa đồng ý → thiếu "consent"; không đồng ý thì liên hệ không được gửi
assert.deepEqual(missingFields({ ...du, contact: "0900" }), ["consent"]);
assert.equal(toSubmit({ ...du, contact: "0900", consent_contact: true }).contact, "0900");
console.log("test-feedback: đạt");
