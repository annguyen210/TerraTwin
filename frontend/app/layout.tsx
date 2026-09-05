import type { Metadata, Viewport } from "next";
import "./globals.css";
import RegisterSW from "@/components/RegisterSW";
import { LangProvider } from "@/lib/i18n";

const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "https://terratwin-web.onrender.com").replace(/\/$/, "");

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: {
    default: "TerraTwin — Bản sao số của đất đai Việt Nam",
    template: "%s · TerraTwin",
  },
  description:
    "Bản sao số của đất đai Việt Nam — cảnh báo sớm mặn, hạn, lũ, sạt lở, cháy rừng cho từng thửa, bằng dữ liệu vệ tinh và thời tiết thật, hiệu chuẩn riêng cho từng điểm.",
  keywords: [
    "cảnh báo thiên tai", "bản sao số đất đai", "digital twin", "nông nghiệp",
    "xâm nhập mặn", "lũ", "sạt lở", "hạn hán", "vệ tinh", "Việt Nam", "TerraTwin",
  ],
  authors: [{ name: "TerraTwin" }],
  openGraph: {
    type: "website",
    locale: "vi_VN",
    siteName: "TerraTwin",
    title: "TerraTwin — Biết trước điều gì sắp xảy ra với mảnh đất của bạn",
    description:
      "Kiểm toàn bộ rủi ro 7 ngày tới cho đúng thửa của bạn bằng dữ liệu vệ tinh & khí hậu thật — báo động giả ~3%, kiểm chứng trên thiên tai lịch sử.",
  },
  twitter: {
    card: "summary_large_image",
    title: "TerraTwin — Bản sao số của đất đai Việt Nam",
    description: "Cảnh báo sớm từng thửa bằng dữ liệu thật. Báo động giả ~3%, có backtest.",
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
