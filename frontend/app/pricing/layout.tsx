import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Bảng giá",
  description: "Nông hộ miễn phí; doanh nghiệp theo thửa/năm; đang thử nghiệm miễn phí.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
