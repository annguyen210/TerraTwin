import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Dùng thử 10 phút",
  description: "Ba việc thử trong 10 phút và phiếu góp ý 2 phút cho người định mua đất và môi giới.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
