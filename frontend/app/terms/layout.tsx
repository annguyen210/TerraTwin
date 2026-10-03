import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Điều khoản",
  description: "Điều khoản sử dụng TerraTwin.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
