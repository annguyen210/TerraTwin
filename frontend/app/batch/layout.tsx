import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Thẩm định hàng loạt",
  description: "Thẩm định cả danh mục thửa từ một tệp CSV.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
