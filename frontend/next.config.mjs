import path from "node:path";
import { fileURLToPath } from "node:url";

// Thư mục chứa file này = gốc frontend, bất kể tiến trình chạy ở đâu.
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Security headers cho MỌI phản hồi. Không thêm Content-Security-Policy ở đây:
// CSP chặt cần nonce cho script/style nội tuyến của Next + MapLibre, làm sai một
// dòng là trắng trang — để riêng, cần test kỹ. Các header dưới đây an toàn, bật
// được ngay: chống clickjacking, chống suy đoán MIME, giữ referrer, khoá quyền
// trình duyệt (chỉ cho geolocation của chính trang — tính năng "dùng vị trí").
// Content-Security-Policy. Đây là header khó nhất: sai một chỉ thị là trắng
// trang. Đã kiểm bằng trình duyệt trên cả bản đồ MapLibre trước khi bật.
//   · script/style 'unsafe-inline': Next nhúng script bootstrap nội tuyến và
//     React/MapLibre chèn style nội tuyến; không dùng nonce nên phải cho phép.
//     KHÔNG có 'unsafe-eval' — app production không cần, giữ chặt hơn.
//   · img-src https + data + blob: tile bản đồ (arcgisonline) và ảnh vệ tinh
//     tải từ nhiều host công khai; ảnh dựng tại chỗ là data:/blob:.
//   · connect-src: chỉ 'self' + đúng API backend. Không mở rộng bừa.
//   · worker-src blob:: MapLibre chạy web worker từ blob URL.
//   · frame-ancestors/base-uri/form-action/object-src: siết khung, chống chèn.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  // connect-src liệt kê ĐÚNG các host trình duyệt fetch (không mở 'https:' bừa):
  //   · terratwin-api: backend.
  //   · server.arcgisonline.com: MapLibre tải TILE bản đồ bằng fetch (không phải
  //     <img>), nên tile dính connect-src — thiếu host này là bản đồ trắng.
  //   · planetarycomputer.microsoft.com: ảnh vệ tinh Sentinel-2 /api/imagery trả về.
  // Mọi nguồn khác (Open-Meteo, NASA, Overpass, LLM…) là fetch phía SERVER, không
  // qua trình duyệt nên không cần ở đây.
  "connect-src 'self' https://terratwin-api.onrender.com https://server.arcgisonline.com https://planetarycomputer.microsoft.com",
  "worker-src 'self' blob:",
  "frame-ancestors 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(self), camera=(), microphone=()" },
  // Render phục vụ toàn bộ qua HTTPS nên HSTS an toàn. 2 năm + áp cho subdomain.
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  webpack: (config) => {
    // Khai báo alias @/ TƯỜNG MINH cho webpack thay vì trông chờ Next tự đọc
    // "paths" trong tsconfig. Việc đọc tsconfig đó nhạy cảm với phiên bản Node:
    // Node 20 (CI) và Node 22 (máy dev) phân giải được @/lib/*, nhưng Node 24
    // mặc định của Render thì KHÔNG — build đỏ "Can't resolve '@/lib/i18n'".
    // Gán thẳng ở đây thì @/ luôn trỏ về gốc frontend, đúng trên mọi Node.
    config.resolve.alias["@"] = __dirname;
    return config;
  },
};

export default nextConfig;
