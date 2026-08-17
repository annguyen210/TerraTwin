import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TerraTwin",
  description: "Bản sao số của đất đai — nhìn, mô phỏng, dự đoán, hành động",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
