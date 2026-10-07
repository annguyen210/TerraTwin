import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Bộ thí điểm cho hợp tác xã",
  description: "Thư mời, tờ hướng dẫn in được cho nông hộ và cán bộ HTX, phiếu góp ý thí điểm.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
