import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Cách hoạt động",
  description: "TerraTwin hoạt động thế nào và vì sao tin được.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
