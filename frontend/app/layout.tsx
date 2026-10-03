import type { Metadata, Viewport } from "next";
import "./globals.css";
import RegisterSW from "@/components/RegisterSW";
import { LangProvider } from "@/lib/i18n";

const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "https://terratwin-web.onrender.com").replace(/\/$/, "");

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: {
    default: "TerraTwin — Hồ sơ vườn chuẩn EUDR, kiểm được",
    template: "%s · TerraTwin",
  },
  description:
    "Chứng minh vườn cà phê, cao su, gỗ không phá rừng trước hạn EUDR 30/12/2026: ranh thửa đúng chuẩn EU, sàng lọc phá rừng bằng dữ liệu vệ tinh đo trên đúng ranh, hồ sơ ký số và sổ minh bạch ai cũng tự kiểm được.",
  keywords: [
    "EUDR", "quy định chống phá rừng EU", "truy xuất nguồn gốc", "cà phê", "cao su", "hồ sơ vườn",
    "GeoJSON", "Sentinel-2", "chữ ký số", "Việt Nam", "TerraTwin",
  ],
  authors: [{ name: "TerraTwin" }],
  openGraph: {
    type: "website",
    locale: "vi_VN",
    siteName: "TerraTwin",
    title: "TerraTwin — Chứng minh vườn không phá rừng trước 30/12/2026",
    description:
      "Ranh chuẩn EU, sàng lọc bằng ba bản đồ rừng 2020 và ảnh vệ tinh, hồ sơ ký số nông hộ giữ, lô hàng có cân bằng khối lượng.",
  },
  twitter: {
    card: "summary_large_image",
    title: "TerraTwin — Hồ sơ vườn chuẩn EUDR",
    description: "Sàng lọc phá rừng bằng vệ tinh, hồ sơ ký số, sổ minh bạch ai cũng kiểm được.",
  },
  manifest: "/manifest.webmanifest",
  applicationName: "TerraTwin",
  appleWebApp: {
    capable: true,
    title: "TerraTwin",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [
      { url: "/favicon.png", sizes: "64x64", type: "image/png" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/icon-192.png", sizes: "192x192", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#0e1720",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body>
        <LangProvider>
          {children}
          <RegisterSW />
        </LangProvider>
      </body>
    </html>
  );
}
