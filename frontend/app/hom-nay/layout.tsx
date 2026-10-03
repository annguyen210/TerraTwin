import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Hôm nay",
  description: "Việc cần làm mỗi sáng: đợt giao hàng chờ xác nhận, vườn bị đánh dấu, đếm ngược hạn EUDR.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
