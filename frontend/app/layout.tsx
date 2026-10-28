import type { Metadata, Viewport } from "next";
import "./globals.css";
import RegisterSW from "@/components/RegisterSW";
import { LangProvider } from "@/lib/i18n";

const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "https://terratwin-web.vercel.app").replace(/\/$/, "");

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: {
    default: "TerraTwin — Sự thật về một mảnh đất",
    template: "%s · TerraTwin",
  },
  description:
    "Thửa đất từng ngập chưa, tin đăng có nói thật không: lịch sử nước radar Sentinel-1 từ 2017, loại đất, hiểm hoạ 10 năm, kiểm chứng tin đăng bán đất, hồ sơ ký số neo Bitcoin ai cũng tự kiểm được. Kèm hồ sơ vườn chuẩn EUDR.",
  keywords: [
    "EUDR", "quy định chống phá rừng EU", "truy xuất nguồn gốc", "cà phê", "cao su", "hồ sơ vườn",
    "GeoJSON", "Sentinel-2", "chữ ký số", "Việt Nam", "TerraTwin",
  ],
  authors: [{ name: "TerraTwin" }],
  openGraph: {
    type: "website",
    locale: "vi_VN",
    siteName: "TerraTwin",
    title: "TerraTwin — Sự thật về một mảnh đất",
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
  // Mã commit của bản đang chạy (Render đặt RENDER_GIT_COMMIT lúc build). Không có quyền xem
  // log Render vẫn kiểm được deploy đã lên hay chưa: so <meta name="tt-build"> với git log.
  other: { "tt-build": (process.env.RENDER_GIT_COMMIT || "local").slice(0, 7) },
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
