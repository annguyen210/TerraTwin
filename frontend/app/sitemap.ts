import type { MetadataRoute } from "next";

/**
 * Sitemap — để công cụ tìm kiếm index đúng các trang công khai.
 * TERRATWIN_PUBLIC_URL đặt khi deploy; mặc định localhost cho dev.
 */
const BASE = (process.env.NEXT_PUBLIC_SITE_URL || "https://terratwin-web.onrender.com").replace(/\/$/, "");

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${BASE}/`, lastModified: now, changeFrequency: "daily", priority: 1 },
    { url: `${BASE}/about`, lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${BASE}/privacy`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${BASE}/terms`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
  ];
}
