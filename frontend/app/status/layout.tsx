import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Trạng thái hệ thống",
  description: "Tình trạng các thành phần của TerraTwin.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
