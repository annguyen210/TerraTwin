import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Quyền riêng tư",
  description: "Dữ liệu TerraTwin lưu và cách bảo vệ.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
