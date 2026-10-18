// Trung vị của N lần chạy Lighthouse cho MỘT trang (Lighthouse khuyên chạy nhiều lần vì điểm hiệu năng dao động:
// 18/10/2026 cùng một bản web, trang chủ ra 88 rồi 62). In một dòng: "perf a11y_min tóm_tắt".
//   node ops/lh/median.cjs lh-1.json lh-2.json lh-3.json
const runs = process.argv.slice(2).map((f) => { try { return require(require("path").resolve(f)); } catch { return null; } })
  .filter((r) => r && r.categories && r.categories.performance && r.categories.performance.score != null);
if (!runs.length) { console.log("NA NA không có lần chạy hợp lệ"); process.exit(0); }
const med = (xs) => { const s = [...xs].sort((a, b) => a - b); const m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const perfs = runs.map((r) => Math.round(r.categories.performance.score * 100));
const a11y = Math.min(...runs.map((r) => Math.round(r.categories.accessibility.score * 100)));   // truy cập: lấy lần TỆ nhất
const ms = (k) => med(runs.map((r) => r.audits[k].numericValue));
const fmt = (k, v) => k === "cumulative-layout-shift" ? v.toFixed(2) : k === "total-blocking-time" ? `${Math.round(v)} ms` : `${(v / 1000).toFixed(1)} s`;
const keys = ["first-contentful-paint", "largest-contentful-paint", "total-blocking-time", "cumulative-layout-shift"];
const summary = keys.map((k) => k.split("-").map((w) => w[0]).join("").toUpperCase() + " " + fmt(k, ms(k))).join(" · ");
console.log(`${Math.round(med(perfs))} ${a11y} ${summary} · ${runs.length} lần: ${perfs.join("/")}`);
