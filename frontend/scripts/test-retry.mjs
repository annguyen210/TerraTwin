// Test đọc có thử lại (lib/retry.ts) — chạy thẳng bằng Node 22, không gọi mạng thật, không chờ thật.
// Lỗi thật 21/10/2026: API khởi động lại → 502 không kèm CORS → trình duyệt "Failed to fetch", danh sách công cụ trống.
import assert from "node:assert/strict";
import { getRetry, NetworkError, RETRY_MS } from "../lib/retry.ts";

const waits = [];
const sleep = async (ms) => { waits.push(ms); };
const seq = (...xs) => { let i = 0; const calls = []; return { calls, fn: async (u) => { calls.push(u); const x = xs[Math.min(i++, xs.length - 1)];
  if (x instanceof Error) throw x; return new Response("{}", { status: x }); } }; };

// 1) mạng hỏng hai lần rồi thông → trả kết quả, đã chờ đúng 2 s rồi 5 s
let s = seq(new TypeError("Failed to fetch"), new TypeError("Failed to fetch"), 200);
let r = await getRetry("u", undefined, { fetchFn: s.fn, sleep });
assert.equal(r.status, 200); assert.equal(s.calls.length, 3); assert.deepEqual(waits, RETRY_MS);

// 2) proxy 502 rồi 200 → thử lại; 404/500 thật → KHÔNG thử lại (không che lỗi thật của máy chủ)
waits.length = 0; s = seq(502, 200); r = await getRetry("u", undefined, { fetchFn: s.fn, sleep });
assert.equal(r.status, 200); assert.equal(s.calls.length, 2);
s = seq(404); r = await getRetry("u", undefined, { fetchFn: s.fn, sleep }); assert.equal(r.status, 404); assert.equal(s.calls.length, 1);
s = seq(500); r = await getRetry("u", undefined, { fetchFn: s.fn, sleep }); assert.equal(s.calls.length, 1);

// 3) hỏng mãi → câu dễ hiểu theo ngôn ngữ, không phải "Failed to fetch"; 503 mãi → trả 503 để người gọi đọc lỗi
s = seq(new TypeError("Failed to fetch"));
await assert.rejects(getRetry("u", undefined, { fetchFn: s.fn, sleep }), (e) => e instanceof NetworkError && /khởi động lại/.test(e.message));
await assert.rejects(getRetry("u", undefined, { fetchFn: seq(new TypeError("x")).fn, sleep, lang: "en" }), /restarting/);
s = seq(503); r = await getRetry("u", undefined, { fetchFn: s.fn, sleep }); assert.equal(r.status, 503); assert.equal(s.calls.length, RETRY_MS.length + 1);

// 4) người gọi tự huỷ → ném ngay, không thử lại
const abort = Object.assign(new Error("aborted"), { name: "AbortError" });
s = seq(abort); await assert.rejects(getRetry("u", undefined, { fetchFn: s.fn, sleep }), /aborted/); assert.equal(s.calls.length, 1);

console.log("OK — đọc có thử lại: mạng hỏng / 502–504 thử lại 2 lần, lỗi thật không che, huỷ không lặp.");
