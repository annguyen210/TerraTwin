import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Hồ sơ vườn chuẩn EUDR",
  description: "Lấy ranh vườn đúng chuẩn EU, sàng lọc phá rừng sau 31/12/2020, phát hành hồ sơ ký số.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
