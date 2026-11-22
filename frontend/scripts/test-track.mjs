// Phễu không đếm máy chạy thử / cờ E2E / quản trị viên (lib/track.ts) — kiểm A–Z lần 2, 22/11/2026.
import assert from "node:assert/strict";
import { shouldTrack } from "../lib/track.ts";

assert.equal(shouldTrack({ webdriver: false, search: "", flags: {} }), true);           // người thật
assert.equal(shouldTrack({ webdriver: true }), false);                                  // Playwright / Selenium
assert.equal(shouldTrack({ search: "?e2e=1" }), false);
assert.equal(shouldTrack({ search: "?x=2&e2e=1" }), false);
assert.equal(shouldTrack({ search: "?e2e=10" }), true);                                 // không khớp nhầm
assert.equal(shouldTrack({ flags: { tt_e2e: "1" } }), false);
assert.equal(shouldTrack({ flags: { tt_admin: "1" } }), false);
assert.equal(shouldTrack({ flags: { tt_admin: null, tt_e2e: null } }), true);
console.log("OK — phễu: bỏ qua trình duyệt tự động, cờ E2E (?e2e=1 / tt_e2e), tài khoản quản trị.");
