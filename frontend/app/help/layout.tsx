import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Trợ giúp",
  description: "Câu hỏi thường gặp về EUDR và TerraTwin.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
