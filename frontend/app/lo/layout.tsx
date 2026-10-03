import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Lô hàng",
  description: "Ghép lô hàng, kiểm cân bằng khối lượng, chứng thư Merkle, tờ khai DDS nháp.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
