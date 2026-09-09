import path from "node:path";
import { fileURLToPath } from "node:url";

// Thư mục chứa file này = gốc frontend, bất kể tiến trình chạy ở đâu.
const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
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
