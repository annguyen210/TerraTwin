import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Hồ sơ đã ký",
  description: "Hồ sơ TerraTwin đã ký số, kiểm chứng được.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
