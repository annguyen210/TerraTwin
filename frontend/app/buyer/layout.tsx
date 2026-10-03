import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Kiểm tra trước khi mua đất",
  description: "Kiểm tra thửa đất trước khi trả tiền.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
