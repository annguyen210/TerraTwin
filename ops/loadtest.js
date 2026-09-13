// P6 — KIỂM THỬ TẢI bằng k6 (https://k6.io). Đo ngưỡng gãy: 50 · 200 · 500
// người dùng đồng thời trên các endpoint ĐỌC quan trọng.
//
// VÌ SAO chỉ endpoint đọc: /api/scan gọi mạng ra Open-Meteo — nện 500 lượt vào
// đó vừa đốt hạn mức của cả hệ thống vừa đo nhầm (đo Open-Meteo, không đo mình).
// Đo /api/health, /api/scorecard, /api/modules, /api/backtest: phản ánh đúng
// sức chịu của MÁY CHỦ TerraTwin, không kéo theo nguồn ngoài.
//
// CÁCH CHẠY (bước vận hành — KHÔNG chạy vào gói free Render đang phục vụ thật;
// dùng môi trường staging hoặc chấp nhận nó chậm/ngủ):
//   k6 run -e BASE=https://terratwin-api.onrender.com ops/loadtest.js
//   k6 run -e BASE=http://localhost:8000 ops/loadtest.js      # an toàn nhất
//
// Ghi lại: ở mức người-đồng-thời nào thì p95 vượt 2s hoặc lỗi > 1% → đó là
// ngưỡng gãy, ghi vào DEPLOY.md để biết khi nào phải nâng cấp hạ tầng.

import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE || "http://localhost:8000";

const READS = [
  "/api/health",
  "/api/scorecard",
  "/api/modules",
  "/api/backtest",
];

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 50 },   // 50 người đồng thời
        { duration: "1m", target: 50 },
        { duration: "30s", target: 200 },   // 200
        { duration: "1m", target: 200 },
        { duration: "30s", target: 500 },   // 500
        { duration: "1m", target: 500 },
        { duration: "30s", target: 0 },     // hạ tải
      ],
    },
  },
  thresholds: {
    // Ngưỡng "đạt": 95% request < 2s, tỉ lệ lỗi < 1%.
    http_req_duration: ["p(95)<2000"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const path = READS[Math.floor(Math.random() * READS.length)];
  const res = http.get(`${BASE}${path}`, { timeout: "30s" });
  check(res, {
    "status 200": (r) => r.status === 200,
    "< 2s": (r) => r.timings.duration < 2000,
  });
  sleep(1);
}
