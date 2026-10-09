import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "So sánh thửa đất",
  description: "Đặt 2–4 thửa cạnh nhau: số lần nước phủ (radar), độ cao, khoảng cách sông/biển, vùng mặn, lũ và sạt lở 10 năm, loại đất.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
