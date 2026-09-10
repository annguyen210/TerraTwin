import path from "node:path";
import { fileURLToPath } from "node:url";

// Thư mục chứa file này = gốc frontend, bất kể tiến trình chạy ở đâu.
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Security headers cho MỌI phản hồi. Không thêm Content-Security-Policy ở đây:
// CSP chặt cần nonce cho script/style nội tuyến của Next + MapLibre, làm sai một
// dòng là trắng trang — để riêng, cần test kỹ. Các header dưới đây an toàn, bật
// được ngay: chống clickjacking, chống suy đoán MIME, giữ referrer, khoá quyền
// trình duyệt (chỉ cho geolocation của chính trang — tính năng "dùng vị trí").
const SECURITY_HEADERS = [
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
