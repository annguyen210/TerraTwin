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
    "kiểm tra đất trước khi mua", "đất có bị ngập không", "tin rao bán đất", "lịch sử ngập", "radar vệ tinh",
    "EUDR", "hồ sơ vườn", "GeoJSON", "Sentinel-2", "chữ ký số", "Việt Nam", "TerraTwin",
  ],
  authors: [{ name: "TerraTwin" }],
  openGraph: {
    type: "website",
    locale: "vi_VN",
    siteName: "TerraTwin",
    title: "TerraTwin — Sự thật về một mảnh đất",
    description:
      "Định mua đất? Kiểm lời rao trước khi xuống tiền: lịch sử ngập 9 năm của đúng thửa từ radar vệ tinh, đối chiếu từng câu trong tin rao, hồ sơ ký số ai cũng kiểm lại được.",
  },
  twitter: {
    card: "summary_large_image",
    title: "TerraTwin — Sự thật về một mảnh đất",
    description: "Kiểm lời rao bán đất bằng lịch sử ngập 9 năm từ radar vệ tinh — hồ sơ ký số ai cũng kiểm lại được.",
  },
  manifest: "/manifest.webmanifest",
  applicationName: "TerraTwin",
  // Mã commit của bản đang chạy (Render đặt RENDER_GIT_COMMIT, Vercel đặt VERCEL_GIT_COMMIT_SHA lúc build). Không có quyền xem
  // log Render vẫn kiểm được deploy đã lên hay chưa: so <meta name="tt-build"> với git log.
  other: { "tt-build": (process.env.RENDER_GIT_COMMIT || process.env.VERCEL_GIT_COMMIT_SHA || "local").slice(0, 7) },
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
