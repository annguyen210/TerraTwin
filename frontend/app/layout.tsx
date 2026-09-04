import type { Metadata, Viewport } from "next";
import "./globals.css";
import RegisterSW from "@/components/RegisterSW";
import { LangProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "TerraTwin",
  description:
    "Bản sao số của đất đai Việt Nam — cảnh báo sớm mặn, hạn, lũ, sạt lở, cháy rừng cho từng thửa, bằng dữ liệu vệ tinh và thời tiết thật.",
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
