import type { MetadataRoute } from "next";

const BASE = (process.env.NEXT_PUBLIC_SITE_URL || "https://terratwin-web.onrender.com").replace(/\/$/, "");

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Liên kết một-chạm chứa token ký số — không cho index để token không lọt
      // vào kết quả tìm kiếm.
      disallow: ["/tap/"],
    },
    sitemap: `${BASE}/sitemap.xml`,
  };
}
