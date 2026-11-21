// Test đọc có thử lại (lib/retry.ts) — chạy thẳng bằng Node 22, không gọi mạng thật, không chờ thật.
// Lỗi thật 21/10/2026: API khởi động lại → 502 không kèm CORS → trình duyệt "Failed to fetch", danh sách công cụ trống.
import assert from "node:assert/strict";
import { computeRetry, getRetry, isComputePost, MAX_TOTAL_MS, NetworkError, RETRY_MS, WAKE_MS, wakingCount } from "../lib/retry.ts";

const waits = [];
const sleep = async (ms) => { waits.push(ms); };
const seq = (...xs) => { let i = 0; const calls = []; return { calls, fn: async (u) => { calls.push(u); const x = xs[Math.min(i++, xs.length - 1)];
  if (x instanceof Error) throw x; return new Response("{}", { status: x }); } }; };

// 1) mạng hỏng hai lần rồi thông → trả kết quả, đã chờ đúng hai bước đầu của lịch
let s = seq(new TypeError("Failed to fetch"), new TypeError("Failed to fetch"), 200);
let r = await getRetry("u", undefined, { fetchFn: s.fn, sleep });
assert.equal(r.status, 200); assert.equal(s.calls.length, 3); assert.deepEqual(waits, RETRY_MS.slice(0, 2));

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

// 5) timeoutMs: lần thử TREO (máy chủ đang thức dậy) bị cắt và thử lại; hết lượt thì báo bằng câu dễ hiểu
const hang = (calls) => async (u, init) => { calls.push(u); return new Promise((_, rej) =>
  init.signal.addEventListener("abort", () => rej(Object.assign(new Error("aborted"), { name: "AbortError" })))); };
let n = []; let k = 0;
const hangThenOk = async (u, init) => (k++ === 0 ? hang(n)(u, init) : new Response("{}", { status: 200 }));
r = await getRetry("u", undefined, { fetchFn: hangThenOk, sleep, timeoutMs: 20 }); assert.equal(r.status, 200); assert.equal(k, 2);
n = []; await assert.rejects(getRetry("u", undefined, { fetchFn: hang(n), sleep, timeoutMs: 20 }), (e) => e instanceof NetworkError);
assert.equal(n.length, RETRY_MS.length + 1);
// người gọi tự huỷ trong lúc có timeoutMs → vẫn ném AbortError ngay, không thử lại
const ac = new AbortController(); n = [];
const p = getRetry("u", { signal: ac.signal }, { fetchFn: hang(n), sleep, timeoutMs: 5000 }); ac.abort();
await assert.rejects(p, (e) => e.name === "AbortError"); assert.equal(n.length, 1);

// 6) CHỜ MÁY CHỦ THỨC (kiểm A–Z 21/11/2026, P0-2): lịch chờ đủ cho Render thức 30–60 s, nhưng không quá ~75 s
const tong = WAKE_MS.reduce((x, y) => x + y, 0);
assert.ok(tong >= 60_000 && tong <= 75_000, tong);

// 7) POST chỉ tính toán: 503/lỗi mạng 3 lần rồi thành công → ra kết quả, không báo lỗi; trong lúc chờ có đếm "đang thức"
waits.length = 0;
let thay = [];
const sleepSee = async (ms) => { waits.push(ms); thay.push(wakingCount()); };
s = seq(new TypeError("Failed to fetch"), 503, new TypeError("Failed to fetch"), 200);
r = await computeRetry("https://api.x/api/listing/check?lang=vi", { method: "POST", body: "{}" }, { fetchFn: s.fn, sleep: sleepSee });
assert.equal(r.status, 200); assert.equal(s.calls.length, 4); assert.deepEqual(waits, WAKE_MS.slice(0, 3));
assert.ok(thay.every((x) => x === 1), thay); assert.equal(wakingCount(), 0);   // xong thì thông báo tắt

// 8) 503 JSON là lỗi THẬT của máy chủ ("mô hình chưa bật") → trả ngay, không bắt chờ 75 s
const json503 = async () => new Response('{"detail":"chưa bật"}', { status: 503, headers: { "content-type": "application/json" } });
let goi = 0; r = await getRetry("u", undefined, { fetchFn: async (...a) => { goi++; return json503(...a); }, sleep });
assert.equal(r.status, 503); assert.equal(goi, 1);

// 9) danh sách POST tính toán: đúng những đường dẫn không ghi; POST ghi dữ liệu KHÔNG thử lại
for (const u of ["/api/listing/check?lang=vi", "/api/scan", "/api/assess/flood", "/api/copilot?lang=en", "/api/passport",
  "/api/whatif/flood", "/api/heatmap/flood", "/api/plan", "/api/water/history"]) assert.ok(isComputePost("https://a.b" + u, "POST"), u);
for (const u of ["/api/pilot/feedback", "/api/plots", "/api/auth/login", "/api/genome/warm", "/api/assess/", "/api/water/confirm",
  "/api/dossier", "/api/eudr/dossier"]) assert.ok(!isComputePost("https://a.b" + u, "POST"), u);
assert.ok(!isComputePost("https://a.b/api/scan", "GET"));
await assert.rejects(computeRetry("https://a.b/api/pilot/feedback", { method: "POST" }, { fetchFn: s.fn, sleep }), /chỉ dùng cho POST tính toán/);

// 10) trần tổng 90 s: mỗi lần gọi treo 25 s (sổ điểm) → dừng trước khi vượt trần, báo bằng câu dễ hiểu
let clock = 0; let lan = 0;
const treo25 = async () => { lan++; clock += 25_000; throw new TypeError("timeout"); };
await assert.rejects(getRetry("u", undefined, { fetchFn: treo25, sleep: async (ms) => { clock += ms; }, now: () => clock, timeoutMs: 25_000 }),
  (e) => e instanceof NetworkError);
assert.ok(clock <= MAX_TOTAL_MS, clock); assert.ok(lan >= 2, lan);

console.log("OK — đọc có thử lại: chờ máy chủ thức ≤ 75 s (GET + POST tính toán), lỗi thật không che, POST ghi không lặp, huỷ không lặp.");
