import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Gán nhãn kiểm định EUDR v3",
  description: "Người giải đoán ảnh năm 2020 làm thước đo kiểm định quy tắc sàng lọc.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
